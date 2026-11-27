//! Types de l'API d'onboarding, alignes sur `setup_server.py`.
//!
//! Aucun secret n'est conserve cote Rust : le mot de passe ne quitte le champ
//! que pour la requete en cours, et Python seul l'ecrit dans le trousseau ou
//! le fichier prive.

use serde::{Deserialize, Serialize};

/// Etat initial de l'assistant.
#[derive(Debug, Clone, Default, Deserialize, Serialize, PartialEq, Eq)]
pub struct SetupState {
    #[serde(default)]
    pub username: String,
    #[serde(default)]
    pub base_url: String,
    #[serde(default)]
    pub has_signature: bool,
    #[serde(default)]
    pub days: Vec<String>,
    #[serde(default)]
    pub windows: Vec<String>,
    #[serde(default)]
    pub notifications: bool,
    #[serde(default)]
    pub keyring: bool,
}

/// Identifiants soumis au test ou a l'enregistrement.
#[derive(Debug, Clone, Serialize)]
pub struct Credentials {
    pub base_url: String,
    pub username: String,
    pub password: String,
}

/// Point de signature au format Python.
#[derive(Debug, Clone, Copy, PartialEq, Serialize, Deserialize)]
pub struct SignaturePoint {
    pub x: f32,
    pub y: f32,
    #[serde(rename = "type")]
    pub kind: PointKind,
}

/// Type d'un point, comme `signature.Point.kind`.
#[derive(Debug, Clone, Copy, Default, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum PointKind {
    Start,
    #[default]
    Move,
    End,
}

/// Corps de `/api/signature`.
#[derive(Debug, Clone, Serialize)]
pub struct SignaturePayload {
    pub points: Vec<SignaturePoint>,
}

/// Corps de `/api/schedule`.
#[derive(Debug, Clone, Serialize)]
pub struct SchedulePayload {
    pub days: Vec<String>,
    pub windows: Vec<String>,
}

/// Corps de `/api/finish`.
#[derive(Debug, Clone, Serialize)]
pub struct FinishPayload {
    pub autostart: bool,
}

/// Reponse commune des routes d'onboarding.
#[derive(Debug, Clone, Default, Deserialize, Serialize, PartialEq, Eq)]
pub struct SetupResult {
    #[serde(default)]
    pub ok: bool,
    #[serde(default)]
    pub message: String,
    #[serde(default)]
    pub username: Option<String>,
    #[serde(default)]
    pub windows: Option<Vec<String>>,
    #[serde(default)]
    pub autostart: Option<String>,
}

/// Etapes de l'assistant, dans l'ordre.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum SetupStep {
    Presentation,
    Credentials,
    Signature,
    Schedule,
    Finish,
}

impl SetupStep {
    pub const ALL: [Self; 5] = [
        Self::Presentation,
        Self::Credentials,
        Self::Signature,
        Self::Schedule,
        Self::Finish,
    ];

    pub fn index(self) -> usize {
        match self {
            Self::Presentation => 0,
            Self::Credentials => 1,
            Self::Signature => 2,
            Self::Schedule => 3,
            Self::Finish => 4,
        }
    }

    pub fn title(self) -> &'static str {
        match self {
            Self::Presentation => "Bienvenue",
            Self::Credentials => "Identifiants",
            Self::Signature => "Signature",
            Self::Schedule => "Planning",
            Self::Finish => "Termine",
        }
    }

    pub fn next(self) -> Option<Self> {
        Self::ALL.get(self.index() + 1).copied()
    }

    pub fn previous(self) -> Option<Self> {
        self.index()
            .checked_sub(1)
            .and_then(|index| Self::ALL.get(index).copied())
    }
}

/// Jours dans l'ordre de la semaine, avec leur libelle court.
pub const DAYS: [(&str, &str); 7] = [
    ("mon", "Lun"),
    ("tue", "Mar"),
    ("wed", "Mer"),
    ("thu", "Jeu"),
    ("fri", "Ven"),
    ("sat", "Sam"),
    ("sun", "Dim"),
];

/// Creneaux par defaut, comme `schedule.DEFAULT_WINDOWS`.
pub const DEFAULT_WINDOWS: [&str; 2] = ["08:00-12:30", "13:30-17:30"];

/// Jours par defaut, comme `schedule.DEFAULT_DAYS`.
pub const DEFAULT_DAYS: [&str; 5] = ["mon", "tue", "wed", "thu", "fri"];

#[cfg(test)]
mod tests {
    use super::{PointKind, SetupStep, SignaturePoint};

    #[test]
    fn les_etapes_se_suivent() {
        assert_eq!(SetupStep::Presentation.next(), Some(SetupStep::Credentials));
        assert_eq!(SetupStep::Finish.next(), None);
        assert_eq!(
            SetupStep::Credentials.previous(),
            Some(SetupStep::Presentation)
        );
        assert_eq!(SetupStep::Presentation.previous(), None);
        assert_eq!(SetupStep::Signature.index(), 2);
    }

    #[test]
    fn serialise_les_points_comme_python() {
        let point = SignaturePoint {
            x: 12.5,
            y: 44.0,
            kind: PointKind::End,
        };
        assert_eq!(
            serde_json::to_string(&point).unwrap(),
            r#"{"x":12.5,"y":44.0,"type":"end"}"#
        );
    }

    #[test]
    fn lit_un_etat_reel_sanitise() {
        let raw = include_str!("../../../fixtures/api/setup-state.json");
        let state: super::SetupState = serde_json::from_str(raw).unwrap();
        assert_eq!(state.username, "etudiant.exemple");
        assert!(!state.has_signature);
        assert_eq!(state.days, ["mon", "tue", "wed", "thu", "fri"]);
    }
}
