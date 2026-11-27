//! Types de l'instantane expose par `/api/status`.
//!
//! Ils suivent exactement `watcher/src/checkmate_watcher/status_data.py`. Le
//! cote Rust ne calcule rien : il affiche ce que Python envoie. Les champs
//! inconnus sont ignores pour rester tolerant aux ajouts de Python.

use serde::{Deserialize, Serialize};

/// Etat du service local, tel que l'affiche le tableau de bord.
#[derive(Debug, Clone, Default, Deserialize, Serialize, PartialEq)]
pub struct StatusSnapshot {
    #[serde(default)]
    pub version: String,
    #[serde(default)]
    pub channel: String,
    #[serde(default)]
    pub build: String,
    #[serde(default)]
    pub started_at: String,
    #[serde(default)]
    pub now: String,
    #[serde(default)]
    pub uptime_seconds: u64,
    #[serde(default)]
    pub mode: String,
    #[serde(default)]
    pub label: String,
    #[serde(default)]
    pub window: Option<String>,
    #[serde(default)]
    pub next_window: Option<String>,
    #[serde(default)]
    pub schedule: ScheduleView,
    #[serde(default)]
    pub counters: CountersView,
    #[serde(default)]
    pub last_signed_at: Option<String>,
    #[serde(default)]
    pub last_detection_at: Option<String>,
    #[serde(default)]
    pub last_error_at: Option<String>,
    #[serde(default)]
    pub last_error_kind: Option<String>,
    #[serde(default)]
    pub last_error_message: Option<String>,
    #[serde(default)]
    pub restart_required: bool,
    #[serde(default)]
    pub blocked: Option<UpdateNotice>,
    #[serde(default)]
    pub migration: Option<UpdateNotice>,
    #[serde(default)]
    pub release_note: Option<ReleaseNote>,
    #[serde(default)]
    pub log_file: String,
}

impl StatusSnapshot {
    /// Ton visuel deduit du mode, sans dependre d'une liste fermee.
    pub fn tone(&self) -> Tone {
        match self.mode.as_str() {
            "active" | "disabled" | "signed" => Tone::Active,
            "outside" | "absent" => Tone::Idle,
            "error" => Tone::Error,
            "blocked" => Tone::Warning,
            _ => Tone::Neutral,
        }
    }
}

/// Famille de couleur d'un etat.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Tone {
    Active,
    Idle,
    Warning,
    Error,
    Neutral,
}

/// Planning affiche par le tableau de bord.
#[derive(Debug, Clone, Default, Deserialize, Serialize, PartialEq, Eq)]
pub struct ScheduleView {
    #[serde(default)]
    pub enabled: bool,
    #[serde(default)]
    pub days: Vec<String>,
    #[serde(default)]
    pub windows: Vec<String>,
}

/// Compteurs cumules.
#[derive(Debug, Clone, Default, Deserialize, Serialize, PartialEq, Eq)]
pub struct CountersView {
    #[serde(default)]
    pub starts: u64,
    #[serde(default)]
    pub detections: u64,
    #[serde(default)]
    pub signed: u64,
    #[serde(default)]
    pub errors: u64,
}

impl CountersView {
    /// Les quatre compteurs dans l'ordre d'affichage.
    pub fn series(&self) -> [(&'static str, u64); 4] {
        [
            ("Demarrages", self.starts),
            ("Detections", self.detections),
            ("Signatures", self.signed),
            ("Erreurs", self.errors),
        ]
    }
}

/// Mise a jour obligatoire ou migration annoncee.
#[derive(Debug, Clone, Default, Deserialize, Serialize, PartialEq, Eq)]
pub struct UpdateNotice {
    #[serde(default)]
    pub tag: String,
    #[serde(default)]
    pub version: String,
    #[serde(default)]
    pub reason: Option<String>,
}

/// Resume de version affiche apres une mise a jour importante.
#[derive(Debug, Clone, Default, Deserialize, Serialize, PartialEq)]
pub struct ReleaseNote {
    #[serde(default)]
    pub version: String,
    #[serde(default)]
    pub importance: Option<String>,
    #[serde(default)]
    pub title: Option<String>,
    #[serde(default)]
    pub summary: Option<String>,
    #[serde(default)]
    pub teaser: Option<String>,
    #[serde(default)]
    pub metrics: Vec<ReleaseMetric>,
    #[serde(default)]
    pub performance: Option<PerformanceSection>,
    #[serde(default)]
    pub features: Vec<ReleaseFeature>,
}

/// Chiffre cle d'un resume de version.
#[derive(Debug, Clone, Default, Deserialize, Serialize, PartialEq, Eq)]
pub struct ReleaseMetric {
    #[serde(default)]
    pub value: String,
    #[serde(default)]
    pub label: String,
    #[serde(default)]
    pub detail: Option<String>,
}

/// Comparatif avant/apres.
#[derive(Debug, Clone, Default, Deserialize, Serialize, PartialEq)]
pub struct PerformanceSection {
    #[serde(default)]
    pub title: String,
    #[serde(default)]
    pub description: String,
    #[serde(default)]
    pub items: Vec<PerformanceItem>,
}

/// Une barre du comparatif.
#[derive(Debug, Clone, Default, Deserialize, Serialize, PartialEq)]
pub struct PerformanceItem {
    #[serde(default)]
    pub label: String,
    #[serde(default)]
    pub before: f64,
    #[serde(default)]
    pub after: f64,
    #[serde(default)]
    pub unit: String,
}

impl PerformanceItem {
    /// Proportion de la valeur apres par rapport a avant, entre 0 et 1.
    pub fn ratio(&self) -> f32 {
        if self.before <= 0.0 {
            return 1.0;
        }
        let ratio = self.after / self.before;
        #[allow(clippy::cast_possible_truncation)]
        let ratio = ratio as f32;
        ratio.clamp(0.0, 1.0)
    }
}

/// Nouveaute listee dans un resume de version.
#[derive(Debug, Clone, Default, Deserialize, Serialize, PartialEq, Eq)]
pub struct ReleaseFeature {
    #[serde(default)]
    pub title: String,
    #[serde(default)]
    pub description: String,
}

/// Reponse d'une action `/api/action`.
#[derive(Debug, Clone, Default, Deserialize, Serialize, PartialEq, Eq)]
pub struct ActionResult {
    #[serde(default)]
    pub ok: bool,
    #[serde(default)]
    pub message: Option<String>,
    #[serde(default)]
    pub available: Option<bool>,
    #[serde(default)]
    pub channel: Option<String>,
    #[serde(default)]
    pub version: Option<String>,
    #[serde(default)]
    pub url: Option<String>,
    #[serde(default)]
    pub teaser: Option<String>,
}

impl ActionResult {
    /// Message a afficher, avec un repli si Python n'en fournit pas.
    pub fn display_message(&self) -> String {
        match (&self.message, self.available) {
            (Some(message), _) if !message.is_empty() => message.clone(),
            (_, Some(true)) => "Mise a jour disponible.".to_owned(),
            _ => "Action terminee.".to_owned(),
        }
    }
}

#[cfg(test)]
mod tests {
    use super::StatusSnapshot;

    fn snapshot(mode: &str) -> StatusSnapshot {
        StatusSnapshot {
            mode: mode.to_owned(),
            ..StatusSnapshot::default()
        }
    }

    #[test]
    fn lit_un_instantane_reel() {
        let raw = include_str!("../../../fixtures/api/status.json");
        let status: StatusSnapshot = serde_json::from_str(raw).unwrap();
        assert_eq!(status.mode, "signed");
        assert_eq!(status.counters.signed, 12);
        assert_eq!(status.schedule.days, ["mon", "tue", "wed", "thu", "fri"]);
        assert!(status.next_window.is_some());
        assert!(status.release_note.is_some());
    }

    #[test]
    fn ignore_les_champs_inconnus() {
        let raw = r#"{"mode":"active","label":"Surveillance active","futur":true}"#;
        let status: StatusSnapshot = serde_json::from_str(raw).unwrap();
        assert_eq!(status.mode, "active");
        assert_eq!(status.label, "Surveillance active");
    }

    #[test]
    fn classe_les_modes_connus() {
        use super::Tone;
        assert_eq!(snapshot("active").tone(), Tone::Active);
        assert_eq!(snapshot("outside").tone(), Tone::Idle);
        assert_eq!(snapshot("error").tone(), Tone::Error);
        assert_eq!(snapshot("blocked").tone(), Tone::Warning);
        assert_eq!(snapshot("inconnu").tone(), Tone::Neutral);
    }
}
