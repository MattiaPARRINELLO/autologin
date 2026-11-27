//! Demarrage automatique : unite systemd utilisateur ou entree RUN Windows.
//!
//! Reprend exactement `autostart.py` : meme nom d'unite, meme commande, meme
//! entree de registre et suppression de l'ancienne tache planifiee.

use std::path::{Path, PathBuf};
use std::process::{Command, Output};

/// Nom de l'unite systemd utilisateur.
pub const UNIT_NAME: &str = "checkmate-watcher.service";
/// Valeur historique du registre et ancienne tache planifiee.
pub const RUN_VALUE: &str = "CheckMate";

#[cfg(target_os = "windows")]
const RUN_KEY: &str = r"Software\Microsoft\Windows\CurrentVersion\Run";

/// Commande a relancer au demarrage.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct AutostartSpec {
    /// Binaire `checkmate-watcher`.
    pub executable: PathBuf,
    /// Chemin de `config.toml`.
    pub config: PathBuf,
}

impl AutostartSpec {
    /// Construit la specification.
    #[must_use]
    pub fn new(executable: impl Into<PathBuf>, config: impl Into<PathBuf>) -> Self {
        Self {
            executable: executable.into(),
            config: config.into(),
        }
    }

    /// Ligne `ExecStart` commune a Linux et Windows.
    #[must_use]
    pub fn command(&self) -> String {
        format!(
            "{} --config {} run",
            quote(&self.executable),
            quote(&self.config)
        )
    }
}

/// Erreur d'installation ou de retrait.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct AutostartError {
    /// Raison lisible.
    pub message: String,
}

impl AutostartError {
    fn new(message: impl Into<String>) -> Self {
        Self {
            message: message.into(),
        }
    }
}

impl std::fmt::Display for AutostartError {
    fn fmt(&self, formatter: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        formatter.write_str(&self.message)
    }
}

impl std::error::Error for AutostartError {}

/// Installe et active le demarrage automatique.
pub fn enable(spec: &AutostartSpec) -> Result<(), AutostartError> {
    #[cfg(target_os = "linux")]
    {
        linux::enable(spec)
    }
    #[cfg(target_os = "windows")]
    {
        windows::enable(spec)
    }
    #[cfg(not(any(target_os = "linux", target_os = "windows")))]
    {
        let _ = spec;
        Err(AutostartError::new(
            "demarrage automatique non pris en charge sur cette plateforme",
        ))
    }
}

/// Desactive le demarrage automatique.
pub fn disable() -> Result<(), AutostartError> {
    #[cfg(target_os = "linux")]
    {
        linux::disable()
    }
    #[cfg(target_os = "windows")]
    {
        windows::disable()
    }
    #[cfg(not(any(target_os = "linux", target_os = "windows")))]
    {
        Err(AutostartError::new(
            "demarrage automatique non pris en charge sur cette plateforme",
        ))
    }
}

/// Vrai si le demarrage automatique est actif.
#[must_use]
pub fn is_enabled() -> bool {
    #[cfg(target_os = "linux")]
    {
        linux::is_enabled()
    }
    #[cfg(target_os = "windows")]
    {
        windows::is_enabled()
    }
    #[cfg(not(any(target_os = "linux", target_os = "windows")))]
    {
        false
    }
}

/// Relance le service apres un changement de configuration.
pub fn restart() -> Result<(), AutostartError> {
    #[cfg(target_os = "linux")]
    {
        linux::restart()
    }
    #[cfg(target_os = "windows")]
    {
        Ok(())
    }
    #[cfg(not(any(target_os = "linux", target_os = "windows")))]
    {
        Err(AutostartError::new(
            "demarrage automatique non pris en charge sur cette plateforme",
        ))
    }
}

fn quote(path: &Path) -> String {
    let text = path.display().to_string();
    if text.contains(' ') {
        format!("\"{text}\"")
    } else {
        text
    }
}

#[cfg(target_os = "linux")]
fn env_file() -> PathBuf {
    crate::config_dir()
        .unwrap_or_else(|| PathBuf::from("."))
        .join("env")
}

#[cfg(target_os = "linux")]
fn home_dir() -> Option<PathBuf> {
    std::env::var_os("HOME").map(PathBuf::from)
}

#[cfg(any(target_os = "linux", target_os = "windows"))]
fn run(program: &str, arguments: &[&str]) -> Option<Output> {
    Command::new(program).args(arguments).output().ok()
}

#[cfg(any(target_os = "linux", target_os = "windows"))]
fn failure(action: &str, output: &Output) -> AutostartError {
    let stderr = String::from_utf8_lossy(&output.stderr).trim().to_owned();
    let stdout = String::from_utf8_lossy(&output.stdout).trim().to_owned();
    let detail = if stderr.is_empty() { stdout } else { stderr };
    AutostartError::new(format!("{action} : {detail}"))
}

#[cfg(target_os = "linux")]
mod linux {
    use std::path::PathBuf;

    #[cfg(test)]
    use std::path::Path;

    use super::{
        AutostartError, AutostartSpec, UNIT_NAME, env_file, failure, home_dir, quote, run,
    };

    const TEMPLATE: &str = "[Unit]\n\
        Description=CheckMate watcher (surveillance emargement CESAR)\n\
        After=graphical-session.target\n\
        PartOf=graphical-session.target\n\
        \n\
        [Service]\n\
        Type=simple\n\
        WorkingDirectory=%h\n\
        EnvironmentFile=-{env_file}\n\
        ExecStart={command}\n\
        Restart=always\n\
        RestartSec=10\n\
        \n\
        [Install]\n\
        WantedBy=graphical-session.target\n";

    pub(super) fn unit_path() -> Option<PathBuf> {
        home_dir().map(|home| home.join(".config/systemd/user").join(UNIT_NAME))
    }

    fn unit_contents(spec: &AutostartSpec) -> String {
        TEMPLATE
            .replace("{env_file}", &quote(&env_file()))
            .replace("{command}", &spec.command())
    }

    pub(super) fn enable(spec: &AutostartSpec) -> Result<(), AutostartError> {
        let path = unit_path().ok_or_else(|| AutostartError::new("dossier personnel absent"))?;
        if let Some(parent) = path.parent() {
            std::fs::create_dir_all(parent)
                .map_err(|error| AutostartError::new(format!("creation de l'unite : {error}")))?;
        }
        std::fs::write(&path, unit_contents(spec))
            .map_err(|error| AutostartError::new(format!("ecriture de l'unite : {error}")))?;
        let Some(reload) = run("systemctl", &["--user", "daemon-reload"]) else {
            return Err(AutostartError::new("systemctl introuvable"));
        };
        if !reload.status.success() {
            return Err(failure("daemon-reload", &reload));
        }
        let Some(output) = run("systemctl", &["--user", "enable", "--now", UNIT_NAME]) else {
            return Err(AutostartError::new("systemctl introuvable"));
        };
        if output.status.success() {
            Ok(())
        } else {
            Err(failure("activation systemd", &output))
        }
    }

    pub(super) fn disable() -> Result<(), AutostartError> {
        let Some(output) = run("systemctl", &["--user", "disable", "--now", UNIT_NAME]) else {
            return Err(AutostartError::new("systemctl introuvable"));
        };
        if output.status.success() {
            if let Some(path) = unit_path() {
                let _ = std::fs::remove_file(path);
            }
            Ok(())
        } else {
            Err(failure("desactivation systemd", &output))
        }
    }

    pub(super) fn is_enabled() -> bool {
        run("systemctl", &["--user", "is-enabled", UNIT_NAME]).is_some_and(|output| {
            output.status.success() && String::from_utf8_lossy(&output.stdout).trim() == "enabled"
        })
    }

    pub(super) fn restart() -> Result<(), AutostartError> {
        let Some(output) = run("systemctl", &["--user", "restart", UNIT_NAME]) else {
            return Err(AutostartError::new("systemctl introuvable"));
        };
        if output.status.success() {
            Ok(())
        } else {
            Err(failure("redemarrage systemd", &output))
        }
    }

    #[cfg(test)]
    pub(super) fn contents_for(path: &Path, config: &Path) -> String {
        unit_contents(&AutostartSpec::new(path, config))
    }
}

#[cfg(target_os = "windows")]
mod windows {
    #[cfg(test)]
    use std::path::Path;

    use super::{AutostartError, AutostartSpec, RUN_KEY, RUN_VALUE, failure, run};

    const LEGACY_TASK: &str = "CheckMate";

    fn remove_legacy_task() {
        let _ = run("schtasks", &["/Delete", "/F", "/TN", LEGACY_TASK]);
    }

    pub(super) fn enable(spec: &AutostartSpec) -> Result<(), AutostartError> {
        remove_legacy_task();
        let command = spec.command();
        let key = format!("HKCU\\{RUN_KEY}");
        let Some(output) = run(
            "reg",
            &[
                "add", &key, "/v", RUN_VALUE, "/t", "REG_SZ", "/d", &command, "/f",
            ],
        ) else {
            return Err(AutostartError::new("reg.exe introuvable"));
        };
        if output.status.success() {
            Ok(())
        } else {
            Err(failure("ecriture du demarrage automatique", &output))
        }
    }

    pub(super) fn disable() -> Result<(), AutostartError> {
        remove_legacy_task();
        if !is_enabled() {
            return Ok(());
        }
        let key = format!("HKCU\\{RUN_KEY}");
        let Some(output) = run("reg", &["delete", &key, "/v", RUN_VALUE, "/f"]) else {
            return Err(AutostartError::new("reg.exe introuvable"));
        };
        if output.status.success() {
            Ok(())
        } else {
            Err(failure("suppression du demarrage automatique", &output))
        }
    }

    pub(super) fn is_enabled() -> bool {
        let key = format!("HKCU\\{RUN_KEY}");
        run("reg", &["query", &key, "/v", RUN_VALUE]).is_some_and(|output| output.status.success())
    }

    #[cfg(test)]
    pub(super) fn command_for(path: &Path, config: &Path) -> String {
        AutostartSpec::new(path, config).command()
    }
}

#[cfg(test)]
mod tests {
    use super::AutostartSpec;

    #[test]
    fn la_commande_reprend_les_chemins_entre_guillemets() {
        let spec = AutostartSpec::new(
            std::path::Path::new("C:/Program Files/CheckMate/checkmate-watcher.exe"),
            std::path::Path::new("C:/Users/test/AppData/Local/config.toml"),
        );
        assert!(
            spec.command()
                .contains("\"C:/Program Files/CheckMate/checkmate-watcher.exe\"")
        );
        assert!(spec.command().contains("--config"));
        assert!(spec.command().ends_with(" run"));
    }

    #[cfg(target_os = "linux")]
    #[test]
    fn l_unite_reprend_le_modele_python() {
        let unit = super::linux::contents_for(
            std::path::Path::new("/opt/checkmate/checkmate-watcher"),
            std::path::Path::new("/home/test/.config/checkmate-watcher/config.toml"),
        );
        assert!(unit.contains("EnvironmentFile=-"));
        assert!(unit.contains("Restart=always"));
        assert!(unit.contains("WantedBy=graphical-session.target"));
        assert!(unit.contains("ExecStart=/opt/checkmate/checkmate-watcher --config"));
    }

    #[cfg(target_os = "windows")]
    #[test]
    fn la_commande_windows_reprend_le_modele_python() {
        let command = super::windows::command_for(
            std::path::Path::new(r"C:\CheckMate\checkmate-watcher.exe"),
            std::path::Path::new(r"C:\Users\test\config.toml"),
        );
        assert_eq!(
            command,
            r#""C:\CheckMate\checkmate-watcher.exe" --config "C:\Users\test\config.toml" run"#
        );
    }
}
