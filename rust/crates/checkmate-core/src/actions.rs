//! Actions du tableau de bord, alignees sur `status_server.ACTIONS`.

use serde::Serialize;

/// Action envoyee a `/api/action`.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize)]
#[serde(rename_all = "kebab-case")]
pub enum ActionKind {
    Configure,
    TestNotification,
    CheckUpdate,
    InstallUpdate,
    DismissRelease,
    OpenLogs,
    SetChannel,
    Quit,
}

impl ActionKind {
    /// Nom attendu par Python.
    pub fn name(self) -> &'static str {
        match self {
            Self::Configure => "configure",
            Self::TestNotification => "test-notification",
            Self::CheckUpdate => "check-update",
            Self::InstallUpdate => "install-update",
            Self::DismissRelease => "dismiss-release",
            Self::OpenLogs => "open-logs",
            Self::SetChannel => "set-channel",
            Self::Quit => "quit",
        }
    }

    /// Libelle affiche.
    pub fn label(self) -> &'static str {
        match self {
            Self::Configure => "Reconfigurer",
            Self::TestNotification => "Tester la notification",
            Self::CheckUpdate => "Verifier les mises a jour",
            Self::InstallUpdate => "Installer la mise a jour",
            Self::DismissRelease => "Fermer les nouveautes",
            Self::OpenLogs => "Ouvrir les logs",
            Self::SetChannel => "Changer de canal",
            Self::Quit => "Quitter",
        }
    }

    /// Vrai si l'action demande une confirmation avant execution.
    pub fn needs_confirmation(self) -> bool {
        matches!(self, Self::Quit | Self::InstallUpdate)
    }

    /// Toutes les actions du tableau de bord, dans l'ordre d'affichage.
    pub fn dashboard_actions() -> &'static [Self] {
        &[
            Self::TestNotification,
            Self::CheckUpdate,
            Self::OpenLogs,
            Self::Configure,
            Self::Quit,
        ]
    }
}

/// Corps envoye a `/api/action`.
#[derive(Debug, Clone, Serialize)]
pub struct ActionRequest {
    pub action: &'static str,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub channel: Option<String>,
}

impl ActionRequest {
    pub fn new(kind: ActionKind) -> Self {
        Self {
            action: kind.name(),
            channel: None,
        }
    }

    pub fn channel(kind: ActionKind, channel: &str) -> Self {
        Self {
            action: kind.name(),
            channel: Some(channel.to_owned()),
        }
    }
}

#[cfg(test)]
mod tests {
    use super::{ActionKind, ActionRequest};

    #[test]
    fn les_noms_correspondent_a_python() {
        assert_eq!(ActionKind::TestNotification.name(), "test-notification");
        assert_eq!(ActionKind::DismissRelease.name(), "dismiss-release");
        assert_eq!(ActionKind::Quit.name(), "quit");
    }

    #[test]
    fn seules_les_actions_risquees_demandent_confirmation() {
        assert!(ActionKind::Quit.needs_confirmation());
        assert!(ActionKind::InstallUpdate.needs_confirmation());
        assert!(!ActionKind::OpenLogs.needs_confirmation());
    }

    #[test]
    fn serialise_le_corps_attendu() {
        let body = serde_json::to_string(&ActionRequest::new(ActionKind::CheckUpdate)).unwrap();
        assert_eq!(body, r#"{"action":"check-update"}"#);

        let body =
            serde_json::to_string(&ActionRequest::channel(ActionKind::SetChannel, "beta")).unwrap();
        assert_eq!(body, r#"{"action":"set-channel","channel":"beta"}"#);
    }
}
