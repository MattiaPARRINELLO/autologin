//! Integrations systeme de CheckMate.
//!
//! Tranche T1 : identite de l'application, emplacements des fichiers Python et
//! description de la fenetre. Aucune ecriture, aucun secret, aucune API
//! reservee a une seule plateforme.
//!
//! Les emplacements reproduisent `watcher/src/checkmate_watcher/paths.py`
//! (platformdirs) pour que la coquille Rust lise le `runtime.json` ecrit par
//! Python au meme endroit.

use std::path::PathBuf;

/// Plateforme de compilation, pour les journaux et le diagnostic.
#[must_use]
pub fn target() -> &'static str {
    std::env::consts::OS
}

/// Nom du dossier de donnees, comme `paths.APP_NAME`.
pub const APP_NAME: &str = "checkmate-watcher";

/// Identifiant de bureau, utilise pour regrouper la fenetre.
pub const APP_ID: &str = "fr.checkmate.CheckMate";

/// Icone de l'application, partagee avec l'installeur Python.
pub const ICON_PNG: &[u8] = include_bytes!("../../../../watcher/assets/checkmate.png");

/// Racine des donnees locales.
pub fn data_dir() -> Option<PathBuf> {
    platform_dirs().map(|dirs| dirs.data)
}

/// Racine de la configuration.
pub fn config_dir() -> Option<PathBuf> {
    platform_dirs().map(|dirs| dirs.config)
}

/// Racine des journaux.
pub fn log_dir() -> Option<PathBuf> {
    platform_dirs().map(|dirs| dirs.log)
}

/// `runtime.json` ecrit par Python.
pub fn runtime_path() -> Option<PathBuf> {
    data_dir().map(|dir| dir.join("runtime.json"))
}

/// `setup-runtime.json` ecrit par Python pendant l'assistant.
pub fn setup_runtime_path() -> Option<PathBuf> {
    data_dir().map(|dir| dir.join("setup-runtime.json"))
}

/// Emplacements resolus pour la plateforme courante.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct PlatformDirs {
    pub data: PathBuf,
    pub config: PathBuf,
    pub log: PathBuf,
}

/// Description d'une fenetre, sans dependance a GPUI.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct WindowSpec {
    pub title: &'static str,
    pub width: u32,
    pub height: u32,
    pub min_width: u32,
    pub min_height: u32,
}

/// Fenetre du tableau de bord, alignee sur `window.py`.
pub const DASHBOARD_WINDOW: WindowSpec = WindowSpec {
    title: "CheckMate",
    width: 1000,
    height: 880,
    min_width: 720,
    min_height: 620,
};

/// Fenetre de l'assistant, un peu plus compacte.
pub const SETUP_WINDOW: WindowSpec = WindowSpec {
    title: "Configuration CheckMate",
    width: 960,
    height: 820,
    min_width: 720,
    min_height: 620,
};

fn platform_dirs() -> Option<PlatformDirs> {
    dirs_for(std::env::var_os("HOME"), std::env::var_os("XDG_DATA_HOME"))
}

fn dirs_for(
    home: Option<std::ffi::OsString>,
    xdg_data: Option<std::ffi::OsString>,
) -> Option<PlatformDirs> {
    dirs_for_os(std::env::consts::OS, home, xdg_data, |name| {
        std::env::var_os(name)
    })
}

fn dirs_for_os(
    os: &str,
    home: Option<std::ffi::OsString>,
    xdg_data: Option<std::ffi::OsString>,
    env: impl Fn(&str) -> Option<std::ffi::OsString>,
) -> Option<PlatformDirs> {
    match os {
        "windows" => windows_dirs(&env),
        "macos" => macos_dirs(home),
        _ => unix_dirs(home, xdg_data, &env),
    }
}

fn windows_dirs(env: &impl Fn(&str) -> Option<std::ffi::OsString>) -> Option<PlatformDirs> {
    let local = env("LOCALAPPDATA")?;
    let root = PathBuf::from(local).join(APP_NAME);
    Some(PlatformDirs {
        data: root.clone(),
        config: root.clone(),
        log: root.join("Logs"),
    })
}

fn macos_dirs(home: Option<std::ffi::OsString>) -> Option<PlatformDirs> {
    let home = PathBuf::from(home?);
    let support = home
        .join("Library")
        .join("Application Support")
        .join(APP_NAME);
    Some(PlatformDirs {
        data: support.clone(),
        config: support,
        log: home.join("Library").join("Logs").join(APP_NAME),
    })
}

fn unix_dirs(
    home: Option<std::ffi::OsString>,
    xdg_data: Option<std::ffi::OsString>,
    env: &impl Fn(&str) -> Option<std::ffi::OsString>,
) -> Option<PlatformDirs> {
    let home = PathBuf::from(home?);
    let data_root = xdg_data
        .map(PathBuf::from)
        .filter(|path| path.is_absolute())
        .unwrap_or_else(|| home.join(".local").join("share"));
    let config_root = absolute(env("XDG_CONFIG_HOME")).unwrap_or_else(|| home.join(".config"));
    let state_root =
        absolute(env("XDG_STATE_HOME")).unwrap_or_else(|| home.join(".local").join("state"));
    Some(PlatformDirs {
        data: data_root.join(APP_NAME),
        config: config_root.join(APP_NAME),
        log: state_root.join(APP_NAME).join("log"),
    })
}

fn absolute(value: Option<std::ffi::OsString>) -> Option<PathBuf> {
    value.map(PathBuf::from).filter(|path| path.is_absolute())
}

/// Vrai si le processus existe encore.
///
/// Sous Linux, `/proc/<pid>` est la source fiable sans appel systeme. Ailleurs,
/// l'absence de reponse HTTP reste le signal d'expiration.
pub fn process_alive(pid: u32) -> bool {
    if cfg!(target_os = "linux") {
        return std::path::Path::new("/proc").join(pid.to_string()).exists();
    }
    true
}

/// Vrai si l'environnement interdit d'ouvrir une fenetre.
/// `CHECKMATE_HEADLESS=1` force le mode sans fenetre. Sous Linux sans
/// `DISPLAY` ni `WAYLAND_DISPLAY`, une fenetre ne peut pas s'ouvrir.
pub fn headless_by_environment() -> bool {
    headless_from(std::env::consts::OS, |name| std::env::var_os(name))
}

fn headless_from(os: &str, env: impl Fn(&str) -> Option<std::ffi::OsString>) -> bool {
    if env("CHECKMATE_HEADLESS").is_some_and(|value| value == "1") {
        return true;
    }
    if os != "linux" && os != "freebsd" {
        return false;
    }
    env("DISPLAY").is_none() && env("WAYLAND_DISPLAY").is_none()
}

#[cfg(test)]
mod tests {
    use super::{PlatformDirs, dirs_for_os, headless_from};
    use std::collections::HashMap;
    use std::ffi::OsString;
    use std::path::PathBuf;

    fn env(values: &[(&str, &str)]) -> impl Fn(&str) -> Option<OsString> {
        let map: HashMap<String, OsString> = values
            .iter()
            .map(|(key, value)| ((*key).to_owned(), OsString::from(value)))
            .collect();
        move |key| map.get(key).cloned()
    }

    #[test]
    fn linux_suit_le_xdg() {
        let dirs = dirs_for_os(
            "linux",
            Some(OsString::from("/home/test")),
            Some(OsString::from("/data")),
            env(&[("XDG_CONFIG_HOME", "/config"), ("XDG_STATE_HOME", "/state")]),
        )
        .unwrap();
        assert_eq!(
            dirs,
            PlatformDirs {
                data: PathBuf::from("/data/checkmate-watcher"),
                config: PathBuf::from("/config/checkmate-watcher"),
                log: PathBuf::from("/state/checkmate-watcher/log"),
            }
        );
    }

    #[test]
    fn linux_replie_sur_le_dossier_personnel() {
        let dirs =
            dirs_for_os("linux", Some(OsString::from("/home/test")), None, env(&[])).unwrap();
        assert_eq!(
            dirs.data,
            PathBuf::from("/home/test/.local/share/checkmate-watcher")
        );
        assert_eq!(
            dirs.config,
            PathBuf::from("/home/test/.config/checkmate-watcher")
        );
        assert_eq!(
            dirs.log,
            PathBuf::from("/home/test/.local/state/checkmate-watcher/log")
        );
    }

    #[test]
    fn windows_utilise_localappdata() {
        let dirs = dirs_for_os(
            "windows",
            None,
            None,
            env(&[("LOCALAPPDATA", r"C:\Users\test\AppData\Local")]),
        )
        .unwrap();
        assert_eq!(
            dirs.data,
            PathBuf::from(r"C:\Users\test\AppData\Local").join("checkmate-watcher")
        );
        assert!(dirs.log.ends_with("Logs"));
    }

    #[test]
    fn headless_sur_linux_sans_affichage() {
        assert!(headless_from("linux", env(&[])));
        assert!(!headless_from(
            "linux",
            env(&[("WAYLAND_DISPLAY", "wayland-0")])
        ));
        assert!(!headless_from("windows", env(&[])));
        assert!(headless_from("linux", env(&[("CHECKMATE_HEADLESS", "1")])));
    }
}
