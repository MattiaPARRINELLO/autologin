//! Notifications bureau et repli sans service.
//!
//! Linux passe par D-Bus (`org.freedesktop.Notifications`), Windows par WinRT.
//! Le titre, le corps et l'urgence reprennent `notifications.py`. Si le service
//! manque, une fenetre de confirmation s'affiche et l'absence est journalisee,
//! sans nouvelle tentative en boucle.

use notify_rust::{Notification, Urgency};

/// Urgence d'une notification.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Default)]
pub enum NoticeUrgency {
    /// Information discrete.
    Low,
    /// Information normale.
    #[default]
    Normal,
    /// Alerte qui doit attirer l'attention.
    Critical,
}

impl NoticeUrgency {
    /// Convertit l'urgence textuelle de la configuration Python.
    #[must_use]
    pub fn parse(value: &str) -> Self {
        match value {
            "low" => Self::Low,
            "critical" => Self::Critical,
            _ => Self::Normal,
        }
    }

    fn to_notify(self) -> Urgency {
        match self {
            Self::Low => Urgency::Low,
            Self::Normal => Urgency::Normal,
            Self::Critical => Urgency::Critical,
        }
    }
}

/// Contenu d'une notification.
#[derive(Debug, Clone)]
pub struct Notice {
    /// Titre.
    pub title: String,
    /// Corps.
    pub body: String,
    /// Urgence.
    pub urgency: NoticeUrgency,
    /// Identifiant de remplacement cote Linux.
    pub replace_id: Option<u32>,
    /// Action proposee, identifiant et libelle.
    pub action: Option<(String, String)>,
}

impl Notice {
    /// Construit une notification simple.
    #[must_use]
    pub fn new(title: impl Into<String>, body: impl Into<String>) -> Self {
        Self {
            title: title.into(),
            body: body.into(),
            urgency: NoticeUrgency::Normal,
            replace_id: None,
            action: None,
        }
    }

    /// Change l'urgence.
    #[must_use]
    pub fn with_urgency(mut self, urgency: NoticeUrgency) -> Self {
        self.urgency = urgency;
        self
    }

    /// Remplace la notification portant cet identifiant sous Linux.
    #[must_use]
    pub fn with_replace_id(mut self, id: u32) -> Self {
        self.replace_id = Some(id);
        self
    }

    /// Ajoute une action cliquable.
    #[must_use]
    pub fn with_action(mut self, id: impl Into<String>, label: impl Into<String>) -> Self {
        self.action = Some((id.into(), label.into()));
        self
    }
}

/// Resultat d'un envoi.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum NotifyOutcome {
    /// Notification affichee par le service du bureau.
    Shown,
    /// Service absent, fenetre de confirmation affichee.
    FallbackShown,
    /// Ni notification ni fenetre possible.
    Unavailable(String),
}

/// Envoie une notification sans attendre un clic.
pub fn send(notice: &Notice) -> NotifyOutcome {
    match build(notice).show() {
        Ok(_handle) => NotifyOutcome::Shown,
        Err(error) => unavailable(notice, &error.to_string()),
    }
}

/// Envoie une notification puis attend l'action sur Windows.
///
/// Sur Linux, `notify-rust` ne rend pas la main avant un clic : l'envoi simple
/// suffit et l'appelant garde son propre cycle de vie.
#[cfg(target_os = "windows")]
pub fn send_and_wait(notice: &Notice) -> NotifyOutcome {
    match build(notice).show() {
        Ok(handle) => {
            if notice.action.is_some() {
                handle.wait_for_action(|action| {
                    if action != "__closed" {
                        crate::spawn_dashboard();
                    }
                });
            }
            NotifyOutcome::Shown
        }
        Err(error) => unavailable(notice, &error.to_string()),
    }
}

/// Variante hors Windows : l'envoi simple est deja bloquant ou suffisant.
#[cfg(not(target_os = "windows"))]
pub fn send_and_wait(notice: &Notice) -> NotifyOutcome {
    send(notice)
}

fn build(notice: &Notice) -> Notification {
    let mut notification = Notification::new();
    notification
        .summary(&notice.title)
        .body(&notice.body)
        .appname(checkmate_core::NAME)
        .icon("dialog-information")
        .urgency(notice.urgency.to_notify());
    if let Some(id) = notice.replace_id {
        notification.id(id);
    }
    if let Some((id, label)) = &notice.action {
        notification.action(id, label);
    }
    #[cfg(target_os = "windows")]
    notification.app_id(crate::APP_ID);
    notification
}

fn unavailable(notice: &Notice, reason: &str) -> NotifyOutcome {
    crate::log::warn(&format!(
        "service de notification indisponible ({reason}), repli sur une fenetre"
    ));
    if show_dialog(&notice.title, &notice.body) {
        return NotifyOutcome::FallbackShown;
    }
    NotifyOutcome::Unavailable(reason.to_owned())
}

#[cfg(target_os = "linux")]
fn show_dialog(title: &str, body: &str) -> bool {
    use std::process::{Command, Stdio};

    if std::env::var_os("DISPLAY").is_none() && std::env::var_os("WAYLAND_DISPLAY").is_none() {
        crate::log::warn("aucun affichage disponible pour la fenetre de confirmation");
        return false;
    }
    let attempts: [(&str, Vec<&str>); 3] = [
        ("zenity", vec!["--info", "--title", title, "--text", body]),
        ("kdialog", vec!["--title", title, "--msgbox", body]),
        ("xmessage", vec!["-center", body]),
    ];
    for (binary, arguments) in attempts {
        let Ok(child) = Command::new(binary)
            .args(&arguments)
            .stdin(Stdio::null())
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            .status()
        else {
            continue;
        };
        if child.success() {
            return true;
        }
    }
    false
}

#[cfg(target_os = "windows")]
fn show_dialog(title: &str, body: &str) -> bool {
    use std::process::{Command, Stdio};

    const SCRIPT: &str = "Add-Type -AssemblyName PresentationFramework;\
        [System.Windows.MessageBox]::Show($env:CHECKMATE_DIALOG_BODY, \
        $env:CHECKMATE_DIALOG_TITLE) | Out-Null";
    for binary in ["powershell", "pwsh"] {
        let Ok(status) = Command::new(binary)
            .args(["-NoProfile", "-NonInteractive", "-Command", SCRIPT])
            .env("CHECKMATE_DIALOG_TITLE", title)
            .env("CHECKMATE_DIALOG_BODY", body)
            .stdin(Stdio::null())
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            .status()
        else {
            continue;
        };
        if status.success() {
            return true;
        }
    }
    false
}

#[cfg(target_os = "macos")]
fn show_dialog(title: &str, body: &str) -> bool {
    use std::process::{Command, Stdio};

    let script = format!(
        "display dialog {} with title {}",
        applescript(body),
        applescript(title)
    );
    Command::new("osascript")
        .args(["-e", &script])
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .status()
        .is_ok_and(|status| status.success())
}

#[cfg(target_os = "macos")]
fn applescript(value: &str) -> String {
    format!("\"{}\"", value.replace('\\', "\\\\").replace('"', "\\\""))
}

#[cfg(not(any(target_os = "linux", target_os = "windows", target_os = "macos")))]
fn show_dialog(_title: &str, _body: &str) -> bool {
    false
}

#[cfg(test)]
mod tests {
    use super::{Notice, NoticeUrgency, NotifyOutcome};

    #[test]
    fn l_urgence_python_est_reconnue() {
        assert_eq!(NoticeUrgency::parse("critical"), NoticeUrgency::Critical);
        assert_eq!(NoticeUrgency::parse("normal"), NoticeUrgency::Normal);
        assert_eq!(NoticeUrgency::parse("low"), NoticeUrgency::Low);
        assert_eq!(NoticeUrgency::parse("inconnu"), NoticeUrgency::Normal);
    }

    #[test]
    fn le_contenu_reprend_titre_corps_et_action() {
        let notice = Notice::new("CheckMate", "Test")
            .with_urgency(NoticeUrgency::Critical)
            .with_replace_id(7)
            .with_action("open", "Ouvrir");
        assert_eq!(notice.title, "CheckMate");
        assert_eq!(notice.body, "Test");
        assert_eq!(notice.replace_id, Some(7));
        assert_eq!(
            notice.action,
            Some(("open".to_owned(), "Ouvrir".to_owned()))
        );
        assert_ne!(NotifyOutcome::Shown, NotifyOutcome::FallbackShown);
    }
}
