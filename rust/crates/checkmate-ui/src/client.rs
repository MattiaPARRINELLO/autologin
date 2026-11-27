//! Client typé de l'API locale ecrite par Python.
//!
//! T1 : Python reste proprietaire de `runtime.json`, `config.toml` et
//! `state.json`. La coquille Rust lit `runtime.json`, envoie le jeton dans
//! `X-CheckMate-Token` et ne persiste rien.

use std::fmt;
use std::io::Read;
use std::path::{Path, PathBuf};
use std::sync::Arc;
use std::time::Duration;

use checkmate_core::actions::{ActionKind, ActionRequest};
use checkmate_core::setup::{
    Credentials, FinishPayload, SchedulePayload, SetupResult, SetupState, SignaturePayload,
};
use checkmate_core::status::{ActionResult, StatusSnapshot};
use serde::Deserialize;
use serde::de::DeserializeOwned;

/// En-tete d'authentification des deux serveurs locaux.
pub const TOKEN_HEADER: &str = "X-CheckMate-Token";
const STATUS_TIMEOUT: Duration = Duration::from_secs(2);
const ACTION_TIMEOUT: Duration = Duration::from_secs(30);

/// Contenu de `runtime.json`.
#[derive(Debug, Clone, Deserialize)]
pub struct RuntimeFile {
    #[serde(default)]
    pub pid: Option<u32>,
    pub port: u16,
    pub token: String,
    #[serde(default)]
    pub url: Option<String>,
    #[serde(default)]
    pub started_at: Option<String>,
}

impl RuntimeFile {
    /// Lit et valide un fichier de runtime.
    pub fn load(path: &Path) -> Result<Self, ApiError> {
        let raw = match std::fs::read_to_string(path) {
            Ok(raw) => raw,
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => {
                return Err(ApiError::RuntimeMissing(path.to_path_buf()));
            }
            Err(error) => {
                return Err(ApiError::RuntimeInvalid(format!(
                    "{} illisible : {error}",
                    path.display()
                )));
            }
        };
        let runtime: Self = serde_json::from_str(&raw).map_err(|error| {
            ApiError::RuntimeInvalid(format!("{} invalide : {error}", path.display()))
        })?;
        runtime.validate(path)?;
        Ok(runtime)
    }

    fn validate(&self, path: &Path) -> Result<(), ApiError> {
        if self.port == 0 || self.token.trim().is_empty() {
            return Err(ApiError::RuntimeInvalid(format!(
                "{} sans port ni jeton",
                path.display()
            )));
        }
        if let Some(pid) = self.pid
            && !checkmate_platform::process_alive(pid)
        {
            return Err(ApiError::RuntimeStale(pid));
        }
        Ok(())
    }

    fn base_url(&self) -> String {
        format!("http://127.0.0.1:{}/api", self.port)
    }
}

/// Erreur d'appel de l'API locale.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum ApiError {
    /// Aucun service local n'a encore ecrit `runtime.json`.
    RuntimeMissing(PathBuf),
    /// Le fichier existe mais n'est pas exploitable.
    RuntimeInvalid(String),
    /// Le processus indique dans `runtime.json` n'existe plus.
    RuntimeStale(u32),
    /// Le service ne repond pas (arrete, port ferme, delai depasse).
    Unreachable(String),
    /// Jeton refuse par Python.
    Unauthorized,
    /// Action refusee avec un message.
    Rejected { status: u16, message: String },
    /// Reponse illisible.
    Decode(String),
}

impl ApiError {
    /// Vrai si l'utilisateur doit relancer CheckMate.
    pub fn is_stale(&self) -> bool {
        matches!(
            self,
            Self::RuntimeMissing(_) | Self::RuntimeStale(_) | Self::Unreachable(_)
        )
    }

    /// Explication courte destinee a l'ecran.
    pub fn guidance(&self) -> &'static str {
        match self {
            Self::RuntimeMissing(_) | Self::RuntimeStale(_) | Self::Unreachable(_) => {
                "Relance CheckMate depuis le menu Demarrer."
            }
            Self::RuntimeInvalid(_) => "Le fichier d'etat local est illisible. Relance CheckMate.",
            Self::Unauthorized => "Le jeton local a ete refuse. Relance CheckMate.",
            Self::Rejected { .. } | Self::Decode(_) => "",
        }
    }
}

impl fmt::Display for ApiError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::RuntimeMissing(path) => {
                write!(formatter, "service arrete : {} absent", path.display())
            }
            Self::RuntimeInvalid(message) => write!(formatter, "{message}"),
            Self::RuntimeStale(pid) => {
                write!(formatter, "service arrete : processus {pid} disparu")
            }
            Self::Unreachable(message) => write!(formatter, "service injoignable : {message}"),
            Self::Unauthorized => write!(formatter, "acces local refuse"),
            Self::Rejected { status, message } => write!(formatter, "{message} ({status})"),
            Self::Decode(message) => write!(formatter, "reponse illisible : {message}"),
        }
    }
}

impl std::error::Error for ApiError {}

/// Operations exposees a l'interface.
///
/// Une implementation de test remplace l'API locale sans ouvrir de socket.
pub trait Backend: Send + Sync + 'static {
    fn status(&self) -> Result<StatusSnapshot, ApiError>;
    fn action(&self, request: &ActionRequest) -> Result<ActionResult, ApiError>;
    fn setup_state(&self) -> Result<SetupState, ApiError>;
    fn test_login(&self, credentials: &Credentials) -> Result<SetupResult, ApiError>;
    fn save_credentials(&self, credentials: &Credentials) -> Result<SetupResult, ApiError>;
    fn save_signature(&self, payload: &SignaturePayload) -> Result<SetupResult, ApiError>;
    fn import_signature(&self, raw: serde_json::Value) -> Result<SetupResult, ApiError>;
    fn save_schedule(&self, payload: &SchedulePayload) -> Result<SetupResult, ApiError>;
    fn test_notification(&self) -> Result<SetupResult, ApiError>;
    fn finish_setup(&self, payload: &FinishPayload) -> Result<SetupResult, ApiError>;
}

/// Client HTTP des deux serveurs locaux de Python.
#[derive(Debug, Clone)]
pub struct LiveBackend {
    runtime_path: PathBuf,
    setup_runtime_path: PathBuf,
    agent: ureq::Agent,
}

impl LiveBackend {
    /// Construit le client a partir des chemins ecrits par Python.
    pub fn new(runtime_path: PathBuf, setup_runtime_path: PathBuf) -> Self {
        let config = ureq::Agent::config_builder()
            .http_status_as_error(false)
            .timeout_global(Some(ACTION_TIMEOUT))
            .build();
        Self {
            runtime_path,
            setup_runtime_path,
            agent: config.into(),
        }
    }

    /// Client avec les chemins par defaut de la plateforme.
    pub fn discover() -> Self {
        Self::new(
            checkmate_platform::runtime_path().unwrap_or_else(|| PathBuf::from("runtime.json")),
            checkmate_platform::setup_runtime_path()
                .unwrap_or_else(|| PathBuf::from("setup-runtime.json")),
        )
    }

    fn status_runtime(&self) -> Result<RuntimeFile, ApiError> {
        RuntimeFile::load(&self.runtime_path)
    }

    fn setup_runtime(&self) -> Result<RuntimeFile, ApiError> {
        RuntimeFile::load(&self.setup_runtime_path)
    }

    fn get<T: DeserializeOwned>(&self, runtime: &RuntimeFile, path: &str) -> Result<T, ApiError> {
        let response = self
            .agent
            .get(&format!("{}{path}", runtime.base_url()))
            .header(TOKEN_HEADER, &runtime.token)
            .config()
            .timeout_global(Some(STATUS_TIMEOUT))
            .build()
            .call()
            .map_err(transport)?;
        decode(response)
    }

    fn post<T: DeserializeOwned, B: serde::Serialize>(
        &self,
        runtime: &RuntimeFile,
        path: &str,
        body: &B,
    ) -> Result<T, ApiError> {
        let response = self
            .agent
            .post(&format!("{}{path}", runtime.base_url()))
            .header(TOKEN_HEADER, &runtime.token)
            .send_json(body)
            .map_err(transport)?;
        decode(response)
    }

    fn dashboard_action(&self, request: &ActionRequest) -> Result<ActionResult, ApiError> {
        let runtime = self.status_runtime()?;
        self.post(&runtime, "/action", request)
    }

    fn setup_action<T: DeserializeOwned, B: serde::Serialize>(
        &self,
        path: &str,
        body: &B,
    ) -> Result<T, ApiError> {
        let runtime = self.setup_runtime()?;
        self.post(&runtime, path, body)
    }
}

fn transport(error: ureq::Error) -> ApiError {
    match error {
        ureq::Error::StatusCode(403) => ApiError::Unauthorized,
        ureq::Error::StatusCode(status) => ApiError::Rejected {
            status,
            message: "action refusee".to_owned(),
        },
        ureq::Error::Io(error) => ApiError::Unreachable(error.to_string()),
        ureq::Error::Timeout(_) => ApiError::Unreachable("delai depasse".to_owned()),
        other => ApiError::Unreachable(other.to_string()),
    }
}

fn decode<T: DeserializeOwned>(
    mut response: ureq::http::Response<ureq::Body>,
) -> Result<T, ApiError> {
    let status = response.status().as_u16();
    if status == 403 {
        return Err(ApiError::Unauthorized);
    }
    if !(200..300).contains(&status) {
        return Err(ApiError::Rejected {
            status,
            message: read_error(response.body_mut()),
        });
    }
    response
        .body_mut()
        .read_json::<T>()
        .map_err(|error| ApiError::Decode(error.to_string()))
}

#[derive(Deserialize)]
struct ErrorEnvelope {
    #[serde(default)]
    error: String,
}

fn read_error(body: &mut ureq::Body) -> String {
    let mut raw = String::new();
    if body
        .as_reader()
        .take(4096)
        .read_to_string(&mut raw)
        .is_err()
    {
        return "action refusee".to_owned();
    }
    serde_json::from_str::<ErrorEnvelope>(&raw)
        .ok()
        .map(|envelope| envelope.error)
        .filter(|message| !message.is_empty())
        .unwrap_or_else(|| "action refusee".to_owned())
}

impl Backend for LiveBackend {
    fn status(&self) -> Result<StatusSnapshot, ApiError> {
        let runtime = self.status_runtime()?;
        self.get(&runtime, "/status")
    }

    fn action(&self, request: &ActionRequest) -> Result<ActionResult, ApiError> {
        self.dashboard_action(request)
    }

    fn setup_state(&self) -> Result<SetupState, ApiError> {
        let runtime = self.setup_runtime()?;
        self.get(&runtime, "/state")
    }

    fn test_login(&self, credentials: &Credentials) -> Result<SetupResult, ApiError> {
        self.setup_action("/test-login", credentials)
    }

    fn save_credentials(&self, credentials: &Credentials) -> Result<SetupResult, ApiError> {
        self.setup_action("/credentials", credentials)
    }

    fn save_signature(&self, payload: &SignaturePayload) -> Result<SetupResult, ApiError> {
        self.setup_action("/signature", payload)
    }

    fn import_signature(&self, raw: serde_json::Value) -> Result<SetupResult, ApiError> {
        self.setup_action("/import-signature", &serde_json::json!({ "raw": raw }))
    }

    fn save_schedule(&self, payload: &SchedulePayload) -> Result<SetupResult, ApiError> {
        self.setup_action("/schedule", payload)
    }

    fn test_notification(&self) -> Result<SetupResult, ApiError> {
        self.setup_action("/test-notification", &serde_json::json!({}))
    }

    fn finish_setup(&self, payload: &FinishPayload) -> Result<SetupResult, ApiError> {
        self.setup_action("/finish", payload)
    }
}

/// Raccourci pour partager un backend entre l'UI et les taches de fond.
pub fn shared(backend: LiveBackend) -> Arc<dyn Backend> {
    Arc::new(backend)
}

/// Envoie une action simple depuis un backend partage.
pub fn dispatch(backend: &Arc<dyn Backend>, kind: ActionKind) -> Result<ActionResult, ApiError> {
    backend.action(&ActionRequest::new(kind))
}

#[cfg(test)]
mod tests {
    use super::{ApiError, Backend, RuntimeFile, TOKEN_HEADER};
    use std::io::{Read, Write};
    use std::net::TcpListener;
    use std::path::PathBuf;

    fn write_runtime(dir: &std::path::Path, name: &str, port: u16) -> PathBuf {
        let path = dir.join(name);
        let payload = format!(
            r#"{{"pid":{},"port":{port},"token":"jeton-test"}}"#,
            std::process::id()
        );
        std::fs::write(&path, payload).unwrap();
        path
    }

    #[test]
    fn signale_un_runtime_absent() {
        let error = RuntimeFile::load(&PathBuf::from("/tmp/checkmate-absent.json")).unwrap_err();
        assert!(matches!(error, ApiError::RuntimeMissing(_)));
        assert!(error.is_stale());
    }

    #[test]
    fn refuse_un_runtime_incomplet() {
        let dir = std::env::temp_dir().join("checkmate-runtime-test");
        std::fs::create_dir_all(&dir).unwrap();
        let path = dir.join("invalide.json");
        std::fs::write(&path, r#"{"port":0,"token":""}"#).unwrap();
        let error = RuntimeFile::load(&path).unwrap_err();
        assert!(matches!(error, ApiError::RuntimeInvalid(_)));
        assert!(!error.is_stale());
    }

    #[test]
    fn signale_un_processus_disparu() {
        let dir = std::env::temp_dir().join("checkmate-runtime-test");
        std::fs::create_dir_all(&dir).unwrap();
        let path = dir.join("mort.json");
        std::fs::write(&path, r#"{"pid":4294967295,"port":8080,"token":"x"}"#).unwrap();
        let error = RuntimeFile::load(&path).unwrap_err();
        assert!(matches!(error, ApiError::RuntimeStale(_)));
    }

    #[test]
    fn lit_le_status_envoye_par_le_serveur_local() {
        let dir = std::env::temp_dir().join("checkmate-http-test");
        std::fs::create_dir_all(&dir).unwrap();
        let listener = TcpListener::bind("127.0.0.1:0").unwrap();
        let port = listener.local_addr().unwrap().port();
        let runtime = write_runtime(&dir, "runtime.json", port);
        let worker = std::thread::spawn(move || {
            let (mut stream, _) = listener.accept().unwrap();
            let mut buffer = [0_u8; 2048];
            let read = stream.read(&mut buffer).unwrap();
            let request = String::from_utf8_lossy(&buffer[..read]).into_owned();
            assert!(
                request
                    .to_lowercase()
                    .contains(&format!("{}: jeton-test", TOKEN_HEADER.to_lowercase()))
            );
            let body = include_str!("../../../fixtures/api/status.json");
            let response = format!(
                "HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: {}\r\n\r\n{body}",
                body.len()
            );
            stream.write_all(response.as_bytes()).unwrap();
        });

        let backend = super::LiveBackend::new(runtime, dir.join("setup-runtime.json"));
        let status = backend.status().unwrap();
        assert_eq!(status.mode, "signed");
        assert_eq!(status.counters.signed, 12);
        worker.join().unwrap();
    }

    #[test]
    fn lit_le_message_d_erreur_de_python() {
        let dir = std::env::temp_dir().join("checkmate-http-test-error");
        std::fs::create_dir_all(&dir).unwrap();
        let listener = TcpListener::bind("127.0.0.1:0").unwrap();
        let port = listener.local_addr().unwrap().port();
        let runtime = write_runtime(&dir, "runtime.json", port);
        let worker = std::thread::spawn(move || {
            let (mut stream, _) = listener.accept().unwrap();
            let mut buffer = [0_u8; 2048];
            let _ = stream.read(&mut buffer).unwrap();
            let body = r#"{"error":"notification impossible sur ce systeme"}"#;
            let response = format!(
                "HTTP/1.1 409 Conflict\r\nContent-Type: application/json\r\nContent-Length: {}\r\n\r\n{body}",
                body.len()
            );
            stream.write_all(response.as_bytes()).unwrap();
        });

        let backend = super::LiveBackend::new(runtime, dir.join("setup-runtime.json"));
        let error = backend
            .action(&checkmate_core::actions::ActionRequest::new(
                checkmate_core::actions::ActionKind::TestNotification,
            ))
            .unwrap_err();
        assert_eq!(
            error,
            ApiError::Rejected {
                status: 409,
                message: "notification impossible sur ce systeme".to_owned()
            }
        );
        worker.join().unwrap();
    }

    #[test]
    fn refuse_un_jeton_invalide() {
        let dir = std::env::temp_dir().join("checkmate-http-test-token");
        std::fs::create_dir_all(&dir).unwrap();
        let listener = TcpListener::bind("127.0.0.1:0").unwrap();
        let port = listener.local_addr().unwrap().port();
        let runtime = write_runtime(&dir, "runtime.json", port);
        let worker = std::thread::spawn(move || {
            let (mut stream, _) = listener.accept().unwrap();
            let mut buffer = [0_u8; 2048];
            let _ = stream.read(&mut buffer).unwrap();
            stream
                .write_all(b"HTTP/1.1 403 Forbidden\r\nContent-Length: 0\r\n\r\n")
                .unwrap();
        });

        let backend = super::LiveBackend::new(runtime, dir.join("setup-runtime.json"));
        assert_eq!(backend.status().unwrap_err(), ApiError::Unauthorized);
        worker.join().unwrap();
    }
}
