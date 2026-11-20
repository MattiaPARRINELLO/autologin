use serde::Deserialize;
use serde_json::json;
use std::fmt;
use std::path::PathBuf;
use std::process::{Command, Stdio};
use std::time::Duration;

pub const APP_NAME: &str = "checkmate-watcher";

#[derive(Debug, Clone, Deserialize, Default)]
pub struct Schedule {
    pub enabled: bool,
    pub windows: Vec<String>,
}

#[derive(Debug, Clone, Deserialize, Default)]
pub struct Counters {
    pub starts: u64,
    pub detections: u64,
    pub signed: u64,
    pub errors: u64,
}

#[derive(Debug, Clone, Deserialize, Default)]
pub struct Status {
    pub version: String,
    pub build: String,
    pub started_at: String,
    pub mode: String,
    pub label: String,
    pub window: Option<String>,
    pub next_window: Option<String>,
    #[serde(default)]
    pub schedule: Schedule,
    #[serde(default)]
    pub counters: Counters,
    pub last_signed_at: Option<String>,
    pub last_detection_at: Option<String>,
    pub restart_required: bool,
}

#[derive(Debug, Clone, Deserialize)]
pub struct Runtime {
    pub port: u16,
    pub token: String,
}

#[derive(Debug, Clone, Deserialize, Default)]
pub struct ActionResponse {
    pub message: Option<String>,
    pub available: Option<bool>,
    pub url: Option<String>,
}

#[derive(Debug)]
pub enum ApiError {
    NoService,
    Http(String),
}

impl fmt::Display for ApiError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            ApiError::NoService => write!(formatter, "service arrete"),
            ApiError::Http(message) => write!(formatter, "{message}"),
        }
    }
}

fn data_dir() -> PathBuf {
    dirs::data_local_dir()
        .unwrap_or_else(|| PathBuf::from("."))
        .join(APP_NAME)
}

pub fn read_runtime() -> Option<Runtime> {
    let path = data_dir().join("runtime.json");
    let raw = std::fs::read_to_string(path).ok()?;
    serde_json::from_str(&raw).ok()
}

fn request_header(runtime: &Runtime) -> (&'static str, String) {
    ("X-CheckMate-Token", runtime.token.clone())
}

pub fn fetch_status() -> Result<Status, ApiError> {
    let runtime = read_runtime().ok_or(ApiError::NoService)?;
    let url = format!("http://127.0.0.1:{}/api/status", runtime.port);
    let (header, token) = request_header(&runtime);
    let mut response = ureq::get(&url)
        .header(header, &token)
        .config()
        .timeout_global(Some(Duration::from_secs(2)))
        .build()
        .call()
        .map_err(|error| ApiError::Http(error.to_string()))?;
    response
        .body_mut()
        .read_json::<Status>()
        .map_err(|error| ApiError::Http(error.to_string()))
}

pub fn action(name: &str) -> Result<ActionResponse, ApiError> {
    let runtime = read_runtime().ok_or(ApiError::NoService)?;
    let url = format!("http://127.0.0.1:{}/api/action", runtime.port);
    let (header, token) = request_header(&runtime);
    let mut response = ureq::post(&url)
        .header(header, &token)
        .config()
        .timeout_global(Some(Duration::from_secs(15)))
        .build()
        .send_json(json!({ "action": name }))
        .map_err(|error| ApiError::Http(error.to_string()))?;
    response
        .body_mut()
        .read_json::<ActionResponse>()
        .map_err(|error| ApiError::Http(error.to_string()))
}

fn backend_candidates() -> Vec<PathBuf> {
    let mut candidates = Vec::new();
    if let Ok(path) = std::env::var("CHECKMATE_BACKEND") {
        candidates.push(PathBuf::from(path));
    }

    if cfg!(windows) {
        if let Ok(local) = std::env::var("LOCALAPPDATA") {
            candidates.push(
                PathBuf::from(local)
                    .join("Programs")
                    .join("CheckMate")
                    .join("CheckMate.exe"),
            );
        }
        if let Ok(current) = std::env::current_exe() {
            candidates.extend(current.parent().map(|folder| folder.join("CheckMate.exe")));
        }
    } else {
        if let Ok(current) = std::env::current_exe() {
            candidates.extend(
                current
                    .parent()
                    .map(|folder| folder.join("checkmate-watcher")),
            );
        }
        candidates.push(PathBuf::from("checkmate-watcher"));
    }
    candidates
}

pub fn start_backend() -> Result<(), String> {
    if fetch_status().is_ok() {
        return Ok(());
    }

    let backend = backend_candidates()
        .into_iter()
        .find(|path| path.exists() || path.components().count() == 1)
        .ok_or_else(|| "moteur CheckMate introuvable".to_string())?;

    let mut command = Command::new(&backend);
    command
        .arg("run")
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::null());

    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        command.creation_flags(0x08000000);
    }

    command
        .spawn()
        .map(|_| ())
        .map_err(|error| format!("impossible de demarrer {} : {error}", backend.display()))
}

#[cfg(test)]
mod tests {
    #[test]
    #[ignore]
    fn live_status() {
        let status = super::fetch_status().expect("service local accessible");
        println!("{} {} - {}", status.version, status.build, status.label);
        assert!(!status.version.is_empty());
    }
}
