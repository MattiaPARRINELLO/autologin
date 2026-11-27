//! Icone de zone de notification.
//!
//! L'icone vit hors de GPUI, conformement a la decision T2. Linux utilise
//! StatusNotifierItem (`ksni`), Windows la zone de notification native.
//! Les clics remontent au processus appelant par un canal, jamais par fork de
//! la boucle GPUI.

use checkmate_core::actions::ActionKind;

pub use crate::icon::TrayMode;

/// Etat affiche par l'icone.
#[derive(Debug, Clone, PartialEq, Eq, Default)]
pub struct TrayState {
    /// Mode visuel.
    pub mode: TrayMode,
    /// Libelle court, par exemple « Creneau signe ».
    pub label: String,
}

impl TrayState {
    /// Construit un etat.
    #[must_use]
    pub fn new(mode: TrayMode, label: impl Into<String>) -> Self {
        Self {
            mode,
            label: label.into(),
        }
    }

    /// Titre de l'item, aligne sur `tray._icon_title`.
    #[must_use]
    pub fn title(&self) -> String {
        if self.label.is_empty() {
            "CheckMate".to_owned()
        } else {
            format!("CheckMate - {}", self.label)
        }
    }

    /// Infobulle : le libelle s'il existe, sinon le titre.
    #[must_use]
    pub fn tooltip(&self) -> String {
        if self.label.is_empty() {
            "CheckMate".to_owned()
        } else {
            self.label.clone()
        }
    }
}

/// Evenement emis par l'icone vers le processus appelant.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum TrayEvent {
    /// Ouvrir le tableau de bord.
    OpenDashboard,
    /// Executer une action de `/api/action`.
    Action(ActionKind),
    /// Quitter CheckMate.
    Quit,
}

/// Actions presentes dans le menu, dans l'ordre de `tray.py`.
pub const TRAY_ACTIONS: [ActionKind; 3] = [
    ActionKind::Configure,
    ActionKind::TestNotification,
    ActionKind::CheckUpdate,
];

/// Erreur de demarrage de l'icone.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct TrayError {
    /// Raison lisible, journalisee par l'appelant.
    pub message: String,
}

impl TrayError {
    pub(crate) fn unavailable(message: impl Into<String>) -> Self {
        Self {
            message: message.into(),
        }
    }
}

impl std::fmt::Display for TrayError {
    fn fmt(&self, formatter: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        formatter.write_str(&self.message)
    }
}

impl std::error::Error for TrayError {}

#[cfg(target_os = "linux")]
mod linux;
#[cfg(target_os = "linux")]
pub use linux::{TrayHandle, start};

#[cfg(target_os = "windows")]
mod windows;
#[cfg(target_os = "windows")]
pub use windows::{TrayHandle, start};

#[cfg(not(any(target_os = "linux", target_os = "windows")))]
mod unsupported;
#[cfg(not(any(target_os = "linux", target_os = "windows")))]
pub use unsupported::{TrayHandle, start};

#[cfg(test)]
mod tests {
    use super::{TrayEvent, TrayState};
    use crate::icon::TrayMode;
    use checkmate_core::actions::ActionKind;

    #[test]
    fn le_titre_suit_le_libelle() {
        assert_eq!(TrayState::new(TrayMode::Active, "").title(), "CheckMate");
        assert_eq!(
            TrayState::new(TrayMode::Signed, "Creneau signe").title(),
            "CheckMate - Creneau signe"
        );
    }

    #[test]
    fn le_menu_reprend_les_trois_actions_de_python() {
        assert_eq!(
            super::TRAY_ACTIONS,
            [
                ActionKind::Configure,
                ActionKind::TestNotification,
                ActionKind::CheckUpdate
            ]
        );
        assert_ne!(TrayEvent::OpenDashboard, TrayEvent::Quit);
    }
}
