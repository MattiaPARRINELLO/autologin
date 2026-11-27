//! Etat de l'interface, navigation clavier et effets.
//!
//! Tout est testable sans fenetre : les vues lisent cet etat, les tests
//! simulent des touches et verifient les effets produits.

use checkmate_core::actions::{ActionKind, ActionRequest};
use checkmate_core::setup::{
    DAYS, DEFAULT_DAYS, DEFAULT_WINDOWS, SetupState, SetupStep, SignaturePoint,
};
use checkmate_core::status::ReleaseNote;

use crate::client::ApiError;

/// Ecran principal.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Screen {
    Dashboard,
    Onboarding,
}

/// Fenetre modale au premier plan.
#[derive(Debug, Clone, PartialEq)]
pub enum Overlay {
    ReleaseNotes(ReleaseNote),
    SignatureConfirmation,
    ConfirmAction {
        action: ActionKind,
        title: String,
        body: String,
    },
}

/// Etat d'un chargement.
#[derive(Debug, Clone, PartialEq)]
pub enum Loadable<T> {
    Loading,
    Ready(T),
    Failed(ApiError),
}

impl<T> Loadable<T> {
    pub fn ready(&self) -> Option<&T> {
        match self {
            Self::Ready(value) => Some(value),
            _ => None,
        }
    }
}

/// Cible de focus, dans l'ordre de tabulation.
#[derive(Debug, Clone, PartialEq, Eq, Hash)]
pub enum FocusId {
    DashboardAction(ActionKind),
    Retry,
    Channel(String),
    Step(SetupStep),
    Back,
    Next,
    Field(Field),
    Day(usize),
    Window(usize),
    Autostart,
    SignatureClear,
    SignatureConfirm,
    ImportSignature,
    DialogAccept,
    DialogCancel,
}

/// Champ de saisie.
#[derive(Debug, Clone, PartialEq, Eq, Hash)]
pub enum Field {
    BaseUrl,
    Username,
    Password,
    ImportPath,
}

/// Evenement clavier normalise.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum Key {
    Tab,
    BackTab,
    Enter,
    Space,
    Escape,
    Backspace,
    Char(String),
}

/// Effet demande par une touche.
#[derive(Debug, Clone, PartialEq)]
pub enum Effect {
    None,
    Refresh,
    Run(ActionKind),
    SetChannel(String),
    SaveCredentials,
    TestLogin,
    SaveSignature,
    ShowSignatureConfirmation,
    ImportSignature,
    SaveSchedule,
    TestNotification,
    Finish,
    DismissRelease,
    OpenOnboarding,
    CloseOverlay,
    Quit,
}

/// Saisie de l'assistant.
#[derive(Debug, Clone, PartialEq)]
pub struct FormState {
    pub base_url: String,
    pub username: String,
    pub password: String,
    pub days: Vec<String>,
    pub windows: Vec<String>,
    pub autostart: bool,
    pub signature: Vec<SignaturePoint>,
    pub import_path: String,
}

impl Default for FormState {
    fn default() -> Self {
        Self {
            base_url: "https://cesar.emineo-education.fr".to_owned(),
            username: String::new(),
            password: String::new(),
            days: DEFAULT_DAYS.iter().map(|day| (*day).to_owned()).collect(),
            windows: DEFAULT_WINDOWS
                .iter()
                .map(|window| (*window).to_owned())
                .collect(),
            autostart: true,
            signature: Vec::new(),
            import_path: String::new(),
        }
    }
}

impl FormState {
    /// Reprend l'etat deja enregistre par Python.
    pub fn from_setup(state: &SetupState) -> Self {
        let mut form = Self::default();
        if !state.base_url.is_empty() {
            form.base_url.clone_from(&state.base_url);
        }
        form.username.clone_from(&state.username);
        if !state.days.is_empty() {
            form.days.clone_from(&state.days);
        }
        if !state.windows.is_empty() {
            form.windows.clone_from(&state.windows);
        }
        form
    }

    /// Vrai si la signature contient un trace exploitable.
    pub fn has_signature(&self) -> bool {
        self.signature.len() >= 2
    }
}

/// Etat complet de la coquille.
#[derive(Debug, Clone)]
pub struct AppState {
    pub screen: Screen,
    pub overlay: Option<Overlay>,
    pub status: Loadable<checkmate_core::status::StatusSnapshot>,
    pub setup: Option<SetupState>,
    pub step: SetupStep,
    pub form: FormState,
    pub focus: FocusId,
    pub busy: Option<ActionKind>,
    pub message: Option<String>,
    pub error: Option<String>,
    pub channel_saved: Option<String>,
}

impl Default for AppState {
    fn default() -> Self {
        Self {
            screen: Screen::Dashboard,
            overlay: None,
            status: Loadable::Loading,
            setup: None,
            step: SetupStep::Presentation,
            form: FormState::default(),
            focus: FocusId::DashboardAction(ActionKind::TestNotification),
            busy: None,
            message: None,
            error: None,
            channel_saved: None,
        }
    }
}

impl AppState {
    /// Cibles de focus de l'ecran courant, dans l'ordre.
    pub fn focus_order(&self) -> Vec<FocusId> {
        if let Some(overlay) = &self.overlay {
            return match overlay {
                Overlay::ReleaseNotes(_) => vec![FocusId::DialogCancel],
                Overlay::SignatureConfirmation | Overlay::ConfirmAction { .. } => {
                    vec![FocusId::DialogAccept, FocusId::DialogCancel]
                }
            };
        }
        match self.screen {
            Screen::Dashboard => self.dashboard_focus(),
            Screen::Onboarding => self.onboarding_focus(),
        }
    }

    fn dashboard_focus(&self) -> Vec<FocusId> {
        let mut order: Vec<FocusId> = ActionKind::dashboard_actions()
            .iter()
            .map(|action| FocusId::DashboardAction(*action))
            .collect();
        if self.status_is_failed() {
            order.insert(0, FocusId::Retry);
        }
        if self.status.ready().is_some() {
            order.push(FocusId::Channel("stable".to_owned()));
            order.push(FocusId::Channel("beta".to_owned()));
        }
        order
    }

    fn onboarding_focus(&self) -> Vec<FocusId> {
        let mut order = vec![FocusId::Step(self.step)];
        match self.step {
            SetupStep::Presentation => {}
            SetupStep::Credentials => {
                order.push(FocusId::Field(Field::BaseUrl));
                order.push(FocusId::Field(Field::Username));
                order.push(FocusId::Field(Field::Password));
            }
            SetupStep::Signature => {
                order.push(FocusId::SignatureClear);
                order.push(FocusId::Field(Field::ImportPath));
                order.push(FocusId::ImportSignature);
                order.push(FocusId::SignatureConfirm);
            }
            SetupStep::Schedule => {
                for index in 0..DAYS.len() {
                    order.push(FocusId::Day(index));
                }
                for index in 0..self.form.windows.len() {
                    order.push(FocusId::Window(index));
                }
                order.push(FocusId::Autostart);
            }
            SetupStep::Finish => {
                order.push(FocusId::Autostart);
            }
        }
        if self.step.previous().is_some() {
            order.push(FocusId::Back);
        }
        order.push(FocusId::Next);
        order
    }

    /// Vrai si la coquille n'a pas pu joindre le service.
    pub fn status_is_failed(&self) -> bool {
        matches!(self.status, Loadable::Failed(_))
    }

    /// Ecran d'erreur explicite a la place du tableau de bord.
    pub fn error_explanation(&self) -> Option<(String, &'static str)> {
        match &self.status {
            Loadable::Failed(error) => Some((error.to_string(), error.guidance())),
            _ => None,
        }
    }

    /// Fait avancer ou reculer le focus.
    pub fn move_focus(&mut self, forward: bool) {
        let order = self.focus_order();
        if order.is_empty() {
            return;
        }
        let current = order.iter().position(|item| item == &self.focus);
        let next = match (current, forward) {
            (Some(index), true) => (index + 1) % order.len(),
            (Some(0) | None, false) => order.len() - 1,
            (Some(index), false) => index - 1,
            (None, true) => 0,
        };
        self.focus = order[next].clone();
    }

    /// Applique une touche et renvoie l'effet a executer.
    pub fn handle_key(&mut self, key: Key) -> Effect {
        match key {
            Key::Tab => {
                self.move_focus(true);
                Effect::None
            }
            Key::BackTab => {
                self.move_focus(false);
                Effect::None
            }
            Key::Escape => self.escape(),
            Key::Enter => self.activate(),
            Key::Space => {
                if self.edits_text() {
                    self.edit_text(|text| text.push(' '));
                    Effect::None
                } else {
                    self.activate()
                }
            }
            Key::Backspace => {
                self.edit_text(|text| {
                    text.pop();
                });
                Effect::None
            }
            Key::Char(text) => {
                self.edit_text(|field| field.push_str(&text));
                Effect::None
            }
        }
    }

    fn escape(&mut self) -> Effect {
        if self.overlay.is_some() {
            self.overlay = None;
            self.focus = self
                .focus_order()
                .first()
                .cloned()
                .unwrap_or(FocusId::Retry);
            return Effect::CloseOverlay;
        }
        Effect::None
    }

    fn edits_text(&self) -> bool {
        matches!(&self.focus, FocusId::Field(_) | FocusId::Window(_))
    }

    fn edit_text(&mut self, edit: impl FnOnce(&mut String)) {
        match &self.focus {
            FocusId::Field(field) => {
                let target = match field {
                    Field::BaseUrl => &mut self.form.base_url,
                    Field::Username => &mut self.form.username,
                    Field::Password => &mut self.form.password,
                    Field::ImportPath => &mut self.form.import_path,
                };
                edit(target);
            }
            FocusId::Window(index) => {
                if let Some(window) = self.form.windows.get_mut(*index) {
                    edit(window);
                }
            }
            _ => {}
        }
    }

    fn activate(&mut self) -> Effect {
        if let Some(overlay) = &self.overlay {
            return match (overlay.clone(), self.focus.clone()) {
                (Overlay::ReleaseNotes(_), _) => {
                    self.overlay = None;
                    Effect::DismissRelease
                }
                (Overlay::SignatureConfirmation, FocusId::DialogAccept) => {
                    self.overlay = None;
                    self.step = SetupStep::Schedule;
                    self.reset_focus();
                    Effect::SaveSignature
                }
                (Overlay::SignatureConfirmation, _) => {
                    self.overlay = None;
                    self.form.signature.clear();
                    Effect::CloseOverlay
                }
                (Overlay::ConfirmAction { action, .. }, FocusId::DialogAccept) => {
                    self.overlay = None;
                    Effect::Run(action)
                }
                (Overlay::ConfirmAction { .. }, _) => {
                    self.overlay = None;
                    Effect::CloseOverlay
                }
            };
        }
        match self.focus.clone() {
            FocusId::DashboardAction(action) => self.dashboard_action(action),
            FocusId::Retry => Effect::Refresh,
            FocusId::Channel(channel) => Effect::SetChannel(channel),
            FocusId::Back => {
                if let Some(previous) = self.step.previous() {
                    self.step = previous;
                    self.reset_focus();
                }
                Effect::None
            }
            FocusId::Next => self.next_step(),
            FocusId::Day(index) => {
                self.toggle_day(index);
                Effect::None
            }
            FocusId::Autostart => {
                self.form.autostart = !self.form.autostart;
                Effect::None
            }
            FocusId::SignatureClear => {
                self.form.signature.clear();
                Effect::None
            }
            FocusId::SignatureConfirm => {
                if self.form.has_signature() && crate::signature::is_usable(&self.form.signature) {
                    Effect::ShowSignatureConfirmation
                } else {
                    self.error = Some("Dessine ou importe d'abord une signature.".to_owned());
                    Effect::None
                }
            }
            FocusId::ImportSignature => Effect::ImportSignature,
            FocusId::Step(_)
            | FocusId::Field(_)
            | FocusId::Window(_)
            | FocusId::DialogAccept
            | FocusId::DialogCancel => Effect::None,
        }
    }

    fn dashboard_action(&mut self, action: ActionKind) -> Effect {
        if action.needs_confirmation() {
            self.overlay = Some(Overlay::ConfirmAction {
                action,
                title: match action {
                    ActionKind::Quit => "Quitter CheckMate ?".to_owned(),
                    _ => "Installer la mise a jour ?".to_owned(),
                },
                body: match action {
                    ActionKind::Quit => {
                        "La surveillance s'arrete jusqu'au prochain demarrage.".to_owned()
                    }
                    _ => "CheckMate redemarre apres l'installation.".to_owned(),
                },
            });
            self.focus = FocusId::DialogCancel;
            Effect::None
        } else {
            Effect::Run(action)
        }
    }

    fn next_step(&mut self) -> Effect {
        match self.step {
            SetupStep::Presentation => {
                self.step = SetupStep::Credentials;
                self.reset_focus();
                Effect::None
            }
            SetupStep::Credentials => Effect::TestLogin,
            SetupStep::Signature => Effect::ShowSignatureConfirmation,
            SetupStep::Schedule => Effect::SaveSchedule,
            SetupStep::Finish => Effect::Finish,
        }
    }

    /// Bascule un jour du planning.
    pub fn toggle_day(&mut self, index: usize) {
        let Some((name, _)) = DAYS.get(index) else {
            return;
        };
        if let Some(position) = self.form.days.iter().position(|day| day == name) {
            self.form.days.remove(position);
        } else {
            self.form.days.push((*name).to_owned());
        }
    }

    fn reset_focus(&mut self) {
        self.focus = self.focus_order().first().cloned().unwrap_or(FocusId::Next);
    }

    /// Passe a l'ecran d'onboarding et charge son etat.
    pub fn open_onboarding(&mut self) {
        self.screen = Screen::Onboarding;
        self.step = SetupStep::Presentation;
        self.overlay = None;
        self.reset_focus();
    }

    /// Revient au tableau de bord apres la fin de l'assistant.
    pub fn finish_onboarding(&mut self) {
        self.screen = Screen::Dashboard;
        self.overlay = None;
        self.step = SetupStep::Finish;
        self.reset_focus();
    }

    /// Corrige le focus s'il n'existe plus sur l'ecran courant.
    pub fn ensure_focus(&mut self) {
        let order = self.focus_order();
        if !order.contains(&self.focus) {
            self.focus = order.first().cloned().unwrap_or(FocusId::Retry);
        }
    }

    /// Corps d'action pour le canal courant.
    pub fn channel_request(channel: &str) -> ActionRequest {
        ActionRequest::channel(ActionKind::SetChannel, channel)
    }
}

#[cfg(test)]
mod tests {
    #![allow(clippy::field_reassign_with_default)]
    use super::{AppState, Effect, Field, FocusId, Key, Overlay, SetupStep};
    use checkmate_core::actions::ActionKind;

    #[test]
    fn le_focus_suit_l_ordre_de_tabulation() {
        let mut state = AppState::default();
        assert_eq!(
            state.focus,
            FocusId::DashboardAction(ActionKind::TestNotification)
        );
        state.handle_key(Key::Tab);
        assert_eq!(
            state.focus,
            FocusId::DashboardAction(ActionKind::CheckUpdate)
        );
        state.handle_key(Key::BackTab);
        assert_eq!(
            state.focus,
            FocusId::DashboardAction(ActionKind::TestNotification)
        );
        state.handle_key(Key::BackTab);
        assert_eq!(state.focus, FocusId::DashboardAction(ActionKind::Quit));
    }

    #[test]
    fn escape_ferme_la_modale_sans_agir() {
        let mut state = AppState::default();
        state.overlay = Some(Overlay::SignatureConfirmation);
        state.focus = FocusId::DialogAccept;
        assert_eq!(state.handle_key(Key::Escape), Effect::CloseOverlay);
        assert!(state.overlay.is_none());
    }

    #[test]
    fn l_acceptation_de_la_signature_avance() {
        let mut state = AppState::default();
        state.screen = super::Screen::Onboarding;
        state.step = SetupStep::Signature;
        state.form.signature = vec![
            checkmate_core::setup::SignaturePoint {
                x: 0.0,
                y: 0.0,
                kind: checkmate_core::setup::PointKind::Start,
            },
            checkmate_core::setup::SignaturePoint {
                x: 10.0,
                y: 10.0,
                kind: checkmate_core::setup::PointKind::End,
            },
        ];
        state.overlay = Some(Overlay::SignatureConfirmation);
        state.focus = FocusId::DialogAccept;
        assert_eq!(state.handle_key(Key::Enter), Effect::SaveSignature);
        assert_eq!(state.step, SetupStep::Schedule);
    }

    #[test]
    fn le_refus_de_la_signature_efface_le_trace() {
        let mut state = AppState::default();
        state.form.signature = vec![checkmate_core::setup::SignaturePoint {
            x: 1.0,
            y: 2.0,
            kind: checkmate_core::setup::PointKind::Move,
        }];
        state.overlay = Some(Overlay::SignatureConfirmation);
        state.focus = FocusId::DialogCancel;
        assert_eq!(state.handle_key(Key::Enter), Effect::CloseOverlay);
        assert_eq!(state.form.signature.len(), 0);
        assert_eq!(state.step, SetupStep::Presentation);
    }

    #[test]
    fn la_saisie_alimente_le_champ_focus() {
        let mut state = AppState::default();
        state.screen = super::Screen::Onboarding;
        state.step = SetupStep::Credentials;
        state.focus = FocusId::Field(Field::Username);
        for character in "etudiant".chars() {
            state.handle_key(Key::Char(character.to_string()));
        }
        state.handle_key(Key::Backspace);
        assert_eq!(state.form.username, "etudian");
    }

    #[test]
    fn une_action_risquee_ouvre_une_confirmation() {
        let mut state = AppState::default();
        state.focus = FocusId::DashboardAction(ActionKind::Quit);
        assert_eq!(state.handle_key(Key::Enter), Effect::None);
        assert!(matches!(state.overlay, Some(Overlay::ConfirmAction { .. })));
        assert_eq!(state.focus, FocusId::DialogCancel);
    }

    #[test]
    fn la_confirmation_renvoie_la_bonne_action() {
        let mut state = AppState::default();
        state.overlay = Some(Overlay::ConfirmAction {
            action: ActionKind::InstallUpdate,
            title: String::new(),
            body: String::new(),
        });
        state.focus = FocusId::DialogAccept;
        assert_eq!(
            state.handle_key(Key::Enter),
            Effect::Run(ActionKind::InstallUpdate)
        );
        assert!(state.overlay.is_none());
    }

    #[test]
    fn les_jours_se_basculent_au_clavier() {
        let mut state = AppState::default();
        state.screen = super::Screen::Onboarding;
        state.step = SetupStep::Schedule;
        state.focus = FocusId::Day(5);
        state.handle_key(Key::Enter);
        assert!(state.form.days.contains(&"sat".to_owned()));
        state.handle_key(Key::Enter);
        assert!(!state.form.days.contains(&"sat".to_owned()));
    }

    #[test]
    fn l_espace_s_ecrit_dans_un_champ() {
        let mut state = AppState::default();
        state.screen = super::Screen::Onboarding;
        state.step = SetupStep::Credentials;
        state.focus = FocusId::Field(Field::Username);
        state.handle_key(Key::Char("a".to_owned()));
        state.handle_key(Key::Space);
        assert_eq!(state.form.username, "a ");
    }

    #[test]
    fn un_creneau_se_modifie_au_clavier() {
        let mut state = AppState::default();
        state.screen = super::Screen::Onboarding;
        state.step = SetupStep::Schedule;
        state.focus = FocusId::Window(0);
        state.form.windows[0].clear();
        for character in "09:00-10:00".chars() {
            state.handle_key(Key::Char(character.to_string()));
        }
        assert_eq!(state.form.windows[0], "09:00-10:00");
    }

    #[test]
    fn une_signature_vide_n_ouvre_pas_la_confirmation() {
        let mut state = AppState::default();
        state.screen = super::Screen::Onboarding;
        state.step = SetupStep::Signature;
        state.focus = FocusId::SignatureConfirm;
        assert_eq!(state.handle_key(Key::Enter), Effect::None);
        assert!(state.overlay.is_none());
        assert!(state.error.is_some());
    }

    #[test]
    fn un_ecran_vide_ne_perd_pas_le_focus() {
        let mut state = AppState::default();
        state.focus = FocusId::DialogAccept;
        state.ensure_focus();
        assert_eq!(
            state.focus,
            FocusId::DashboardAction(ActionKind::TestNotification)
        );
    }

    #[test]
    fn l_etat_initial_reprend_les_valeurs_de_python() {
        let raw = include_str!("../../../fixtures/api/setup-state.json");
        let setup: checkmate_core::setup::SetupState = serde_json::from_str(raw).unwrap();
        let form = super::FormState::from_setup(&setup);
        assert_eq!(form.username, "etudiant.exemple");
        assert_eq!(form.days, ["mon", "tue", "wed", "thu", "fri"]);
        assert_eq!(form.windows.len(), 2);
    }
}
