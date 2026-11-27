//! Application GPUI : fenetre, boucle de rafraichissement et effets.

use std::sync::Arc;
use std::time::Duration;

use gpui::prelude::*;
use gpui::{
    App, Application, Context, FocusHandle, IntoElement, KeyDownEvent, MouseButton, MouseDownEvent,
    MouseMoveEvent, MouseUpEvent, Render, Task, Window, WindowOptions,
};

use checkmate_core::actions::{ActionKind, ActionRequest};
use checkmate_core::setup::{
    Credentials, FinishPayload, SchedulePayload, SetupResult, SignaturePayload, SignaturePoint,
};
use checkmate_core::status::StatusSnapshot;

use crate::client::{ApiError, Backend, LiveBackend};
use crate::components;
use crate::signature;
use crate::state::{AppState, Effect, FocusId, Key, Loadable, Overlay, Screen};
use crate::theme::{Motion, Theme};
use crate::views;

/// Intervalle de rafraichissement du tableau de bord.
const REFRESH_INTERVAL: Duration = Duration::from_secs(5);

/// Application racine.
pub struct CheckmateApp {
    pub state: AppState,
    pub theme: Theme,
    focus: FocusHandle,
    backend: Arc<dyn Backend>,
    refresh: Option<Task<()>>,
    drawing_signature: bool,
}

impl CheckmateApp {
    /// Construit l'application avec le backend local.
    pub fn new(cx: &mut Context<Self>) -> Self {
        Self::with_backend(cx, Arc::new(LiveBackend::discover()))
    }

    /// Construit l'application avec un backend injecte (tests).
    pub fn with_backend(cx: &mut Context<Self>, backend: Arc<dyn Backend>) -> Self {
        let motion = Motion::from_environment();
        let mut app = Self {
            state: AppState::default(),
            theme: Theme::light(motion),
            focus: cx.focus_handle(),
            backend,
            refresh: None,
            drawing_signature: false,
        };
        app.state.ensure_focus();
        app
    }

    /// Demarre le chargement initial et la boucle de rafraichissement.
    pub fn start(&mut self, cx: &mut Context<Self>) {
        self.refresh_status(cx);
        self.refresh = Some(cx.spawn(async move |this, cx| {
            loop {
                cx.background_executor().timer(REFRESH_INTERVAL).await;
                let running = this
                    .update(cx, |app, cx| {
                        app.refresh_status(cx);
                        true
                    })
                    .unwrap_or(false);
                if !running {
                    break;
                }
            }
        }));
    }

    fn refresh_status(&mut self, cx: &mut Context<Self>) {
        let backend = self.backend.clone();
        if self.state.status.ready().is_none() {
            self.state.status = Loadable::Loading;
        }
        cx.notify();
        cx.spawn(async move |this, cx| {
            let result = cx
                .background_executor()
                .spawn(async move { backend.status() })
                .await;
            let _ = this.update(cx, |app, cx| {
                app.apply_status(result);
                cx.notify();
            });
        })
        .detach();
    }

    fn apply_status(&mut self, result: Result<StatusSnapshot, ApiError>) {
        self.state.status = match result {
            Ok(status) => {
                self.state.error = None;
                Loadable::Ready(status)
            }
            Err(error) => Loadable::Failed(error),
        };
        self.show_release_note();
        self.state.ensure_focus();
    }

    /// Ouvre les nouveautes une seule fois, au premier instantane qui les porte.
    fn show_release_note(&mut self) {
        if self.state.screen != Screen::Dashboard || self.state.overlay.is_some() {
            return;
        }
        let note = match self.state.status.ready() {
            Some(status) => status.release_note.clone(),
            None => None,
        };
        if let Some(note) = note {
            self.state.overlay = Some(Overlay::ReleaseNotes(note));
            self.state.focus = FocusId::DialogCancel;
        }
    }

    fn apply_key(&mut self, event: &KeyDownEvent, window: &mut Window, cx: &mut Context<Self>) {
        let effect = self.state.handle_key(translate_key(event));
        self.state.ensure_focus();
        cx.notify();
        self.run_effect(effect, window, cx);
    }

    fn run_effect(&mut self, effect: Effect, window: &mut Window, cx: &mut Context<Self>) {
        match effect {
            Effect::None | Effect::CloseOverlay => {}
            Effect::Refresh => self.refresh_status(cx),
            Effect::Run(kind) => self.run_action(kind, cx),
            Effect::SetChannel(channel) => self.run_channel(channel, cx),
            Effect::DismissRelease => self.run_action(ActionKind::DismissRelease, cx),
            Effect::SaveCredentials => self.save_credentials(cx),
            Effect::TestLogin => self.test_login(cx),
            Effect::SaveSignature => self.save_signature(cx),
            Effect::ImportSignature => self.import_signature(cx),
            Effect::SaveSchedule => self.save_schedule(cx),
            Effect::TestNotification => self.test_notification(cx),
            Effect::Finish => self.finish_setup(cx),
            Effect::ShowSignatureConfirmation => {
                self.state.overlay = Some(Overlay::SignatureConfirmation);
                self.state.focus = FocusId::DialogAccept;
                cx.notify();
            }
            Effect::OpenOnboarding => {
                self.state.open_onboarding();
                self.load_setup(cx);
                window.focus(&self.focus);
            }
            Effect::Quit => cx.quit(),
        }
    }

    fn run_action(&mut self, kind: ActionKind, cx: &mut Context<Self>) {
        let backend = self.backend.clone();
        self.state.busy = Some(kind);
        self.state.error = None;
        cx.notify();
        cx.spawn(async move |this, cx| {
            let request = ActionRequest::new(kind);
            let result = cx
                .background_executor()
                .spawn(async move { backend.action(&request) })
                .await;
            let _ = this.update(cx, |app, cx| {
                app.state.busy = None;
                match result {
                    Ok(response) => {
                        app.state.message = Some(response.display_message());
                        if kind == ActionKind::Quit {
                            cx.quit();
                        } else if kind == ActionKind::DismissRelease {
                            app.state.overlay = None;
                        }
                    }
                    Err(error) => app.state.error = Some(error.to_string()),
                }
                cx.notify();
            });
        })
        .detach();
    }

    fn run_channel(&mut self, channel: String, cx: &mut Context<Self>) {
        let backend = self.backend.clone();
        self.state.error = None;
        cx.notify();
        cx.spawn(async move |this, cx| {
            let request = AppState::channel_request(&channel);
            let result = cx
                .background_executor()
                .spawn(async move { backend.action(&request) })
                .await;
            let _ = this.update(cx, |app, cx| {
                match result {
                    Ok(response) => {
                        app.state.channel_saved = Some(channel);
                        app.state.message = Some(response.display_message());
                    }
                    Err(error) => app.state.error = Some(error.to_string()),
                }
                cx.notify();
            });
        })
        .detach();
    }

    fn load_setup(&mut self, cx: &mut Context<Self>) {
        let backend = self.backend.clone();
        cx.spawn(async move |this, cx| {
            let result = cx
                .background_executor()
                .spawn(async move { backend.setup_state() })
                .await;
            let _ = this.update(cx, |app, cx| {
                match result {
                    Ok(setup) => {
                        app.state.form = crate::state::FormState::from_setup(&setup);
                        if setup.has_signature {
                            app.state.message =
                                Some("Une signature est deja enregistree.".to_owned());
                        }
                        app.state.setup = Some(setup);
                        app.state.ensure_focus();
                    }
                    Err(error) => {
                        app.state.error = Some(format!(
                            "{error}. L'assistant n'est pas ouvert : lance `checkmate-watcher setup`."
                        ));
                    }
                }
                cx.notify();
            });
        })
        .detach();
    }

    fn credentials(&self) -> Credentials {
        Credentials {
            base_url: self.state.form.base_url.clone(),
            username: self.state.form.username.clone(),
            password: self.state.form.password.clone(),
        }
    }

    fn test_login(&mut self, cx: &mut Context<Self>) {
        let backend = self.backend.clone();
        let credentials = self.credentials();
        self.state.error = None;
        self.state.message = Some("Test de connexion en cours...".to_owned());
        cx.notify();
        cx.spawn(async move |this, cx| {
            let result = cx
                .background_executor()
                .spawn(async move {
                    backend
                        .test_login(&credentials)
                        .and_then(|_| backend.save_credentials(&credentials))
                })
                .await;
            let _ = this.update(cx, |app, cx| {
                app.state.form.password.clear();
                match result {
                    Ok(response) => {
                        app.state.message = Some(response.message);
                        if let Some(next) = app.state.step.next() {
                            app.state.step = next;
                        }
                        app.state.ensure_focus();
                    }
                    Err(error) => app.state.error = Some(error.to_string()),
                }
                cx.notify();
            });
        })
        .detach();
    }

    fn save_credentials(&mut self, cx: &mut Context<Self>) {
        let backend = self.backend.clone();
        let credentials = self.credentials();
        self.state.error = None;
        cx.notify();
        cx.spawn(async move |this, cx| {
            let result = cx
                .background_executor()
                .spawn(async move { backend.save_credentials(&credentials) })
                .await;
            let _ = this.update(cx, |app, cx| {
                app.state.form.password.clear();
                match result {
                    Ok(response) => app.state.message = Some(response.message),
                    Err(error) => app.state.error = Some(error.to_string()),
                }
                cx.notify();
            });
        })
        .detach();
    }

    fn save_signature(&mut self, cx: &mut Context<Self>) {
        let backend = self.backend.clone();
        let points = self.state.form.signature.clone();
        let payload = SignaturePayload { points };
        self.state.error = None;
        cx.notify();
        cx.spawn(async move |this, cx| {
            let result = cx
                .background_executor()
                .spawn(async move { backend.save_signature(&payload) })
                .await;
            let _ = this.update(cx, |app, cx| {
                match result {
                    Ok(response) => {
                        app.state.message = Some(response.message);
                        app.state.ensure_focus();
                    }
                    Err(error) => app.state.error = Some(error.to_string()),
                }
                cx.notify();
            });
        })
        .detach();
    }

    fn import_signature(&mut self, cx: &mut Context<Self>) {
        let path = self.state.form.import_path.trim().to_owned();
        if path.is_empty() {
            self.state.error = Some("Indique le chemin d'une image PNG ou JPG.".to_owned());
            cx.notify();
            return;
        }
        let points = match signature::points_from_path(std::path::Path::new(&path)) {
            Ok(points) => points,
            Err(error) => {
                self.state.error = Some(error.to_string());
                cx.notify();
                return;
            }
        };
        self.state.form.signature.clone_from(&points);
        let payload = serde_json::json!({ "points": points });
        let backend = self.backend.clone();
        self.state.error = None;
        cx.notify();
        cx.spawn(async move |this, cx| {
            let result = cx
                .background_executor()
                .spawn(async move { backend.import_signature(payload) })
                .await;
            let _ = this.update(cx, |app, cx| {
                match result {
                    Ok(response) => app.state.message = Some(response.message),
                    Err(error) => app.state.error = Some(error.to_string()),
                }
                cx.notify();
            });
        })
        .detach();
    }

    fn save_schedule(&mut self, cx: &mut Context<Self>) {
        let backend = self.backend.clone();
        let payload = SchedulePayload {
            days: self.state.form.days.clone(),
            windows: self.state.form.windows.clone(),
        };
        self.state.error = None;
        cx.notify();
        cx.spawn(async move |this, cx| {
            let result = cx
                .background_executor()
                .spawn(async move { backend.save_schedule(&payload) })
                .await;
            let _ = this.update(cx, |app, cx| {
                match result {
                    Ok(response) => {
                        app.state.message = Some(response.message);
                        if let Some(next) = app.state.step.next() {
                            app.state.step = next;
                        }
                        app.state.ensure_focus();
                    }
                    Err(error) => app.state.error = Some(error.to_string()),
                }
                cx.notify();
            });
        })
        .detach();
    }

    fn test_notification(&mut self, cx: &mut Context<Self>) {
        let backend = self.backend.clone();
        self.state.error = None;
        cx.spawn(async move |this, cx| {
            let result = cx
                .background_executor()
                .spawn(async move { backend.test_notification() })
                .await;
            let _ = this.update(cx, |app, cx| {
                match result {
                    Ok(response) => app.state.message = Some(response.message),
                    Err(error) => app.state.error = Some(error.to_string()),
                }
                cx.notify();
            });
        })
        .detach();
    }

    fn finish_setup(&mut self, cx: &mut Context<Self>) {
        let backend = self.backend.clone();
        let payload = FinishPayload {
            autostart: self.state.form.autostart,
        };
        self.state.error = None;
        cx.notify();
        cx.spawn(async move |this, cx| {
            let result = cx
                .background_executor()
                .spawn(async move { backend.finish_setup(&payload) })
                .await;
            let _ = this.update(cx, |app, cx| {
                match result {
                    Ok(response) => {
                        app.state.message = Some(finish_message(&response));
                        app.state.finish_onboarding();
                    }
                    Err(error) => app.state.error = Some(error.to_string()),
                }
                cx.notify();
            });
        })
        .detach();
    }

    /// Ouvre l'assistant au demarrage, sans fenetre deja affichee.
    pub fn open_onboarding_initial(&mut self, cx: &mut Context<Self>) {
        self.state.open_onboarding();
        self.load_setup(cx);
    }

    /// Ouvre l'assistant et charge son etat.
    pub fn open_onboarding(&mut self, window: &mut Window, cx: &mut Context<Self>) {
        self.run_effect(Effect::OpenOnboarding, window, cx);
    }

    /// Relance le chargement du tableau de bord.
    pub fn retry(&mut self, window: &mut Window, cx: &mut Context<Self>) {
        self.drawing_signature = false;
        self.run_effect(Effect::Refresh, window, cx);
    }

    /// Active une action du tableau de bord comme si Entree etait pressee.
    pub fn activate_dashboard(
        &mut self,
        kind: ActionKind,
        window: &mut Window,
        cx: &mut Context<Self>,
    ) {
        self.state.focus = FocusId::DashboardAction(kind);
        let effect = self.state.handle_key(Key::Enter);
        self.state.ensure_focus();
        self.run_effect(effect, window, cx);
    }

    /// Change de canal de mise a jour.
    pub fn set_channel(&mut self, channel: String, cx: &mut Context<Self>) {
        self.state.message = Some(format!("Canal {channel} demande."));
        self.run_channel(channel, cx);
    }

    /// Place le focus sur une cible.
    pub fn set_focus(&mut self, target: FocusId, window: &mut Window, cx: &mut Context<Self>) {
        self.focus(target, window, cx);
    }

    /// Lance le test de connexion.
    pub fn test_login_action(&mut self, window: &mut Window, cx: &mut Context<Self>) {
        self.run_effect(Effect::TestLogin, window, cx);
    }

    /// Enregistre les identifiants sans tester.
    pub fn save_credentials_action(&mut self, window: &mut Window, cx: &mut Context<Self>) {
        self.run_effect(Effect::SaveCredentials, window, cx);
    }

    /// Importe une image de signature.
    pub fn import_signature_action(&mut self, window: &mut Window, cx: &mut Context<Self>) {
        self.run_effect(Effect::ImportSignature, window, cx);
    }

    /// Efface le trace courant.
    pub fn clear_signature(&mut self, window: &mut Window, cx: &mut Context<Self>) {
        self.state.form.signature.clear();
        self.drawing_signature = false;
        self.set_focus(FocusId::SignatureClear, window, cx);
    }

    /// Demande la confirmation de signature.
    pub fn confirm_signature(&mut self, window: &mut Window, cx: &mut Context<Self>) {
        self.run_effect(Effect::ShowSignatureConfirmation, window, cx);
    }

    /// Bascule un jour du planning.
    pub fn toggle_day(&mut self, index: usize, window: &mut Window, cx: &mut Context<Self>) {
        self.state.focus = FocusId::Day(index);
        self.state.toggle_day(index);
        self.state.ensure_focus();
        window.focus(&self.focus);
        cx.notify();
    }

    /// Declenche le test de notification.
    pub fn test_notification_action(&mut self, window: &mut Window, cx: &mut Context<Self>) {
        self.run_effect(Effect::TestNotification, window, cx);
    }

    /// Revient a l'etape precedente.
    pub fn previous_step(&mut self, window: &mut Window, cx: &mut Context<Self>) {
        if let Some(previous) = self.state.step.previous() {
            self.state.step = previous;
            self.state.focus = FocusId::Next;
            self.state.ensure_focus();
            window.focus(&self.focus);
            cx.notify();
        }
    }

    /// Avance d'une etape, comme Entree sur Continuer.
    pub fn next_step(&mut self, window: &mut Window, cx: &mut Context<Self>) {
        self.state.focus = FocusId::Next;
        let effect = self.state.handle_key(Key::Enter);
        self.state.ensure_focus();
        self.run_effect(effect, window, cx);
    }

    /// Ferme les nouveautes et marque le resume comme vu.
    pub fn dismiss_release(&mut self, window: &mut Window, cx: &mut Context<Self>) {
        self.state.focus = FocusId::DialogCancel;
        self.run_effect(Effect::DismissRelease, window, cx);
    }

    /// Refuse la fenetre modale courante.
    pub fn cancel_modal(&mut self, window: &mut Window, cx: &mut Context<Self>) {
        self.state.focus = FocusId::DialogCancel;
        let effect = self.state.handle_key(Key::Enter);
        self.state.ensure_focus();
        self.run_effect(effect, window, cx);
    }

    /// Accepte la fenetre modale courante.
    pub fn accept_modal(&mut self, window: &mut Window, cx: &mut Context<Self>) {
        self.state.focus = FocusId::DialogAccept;
        let effect = self.state.handle_key(Key::Enter);
        self.state.ensure_focus();
        self.run_effect(effect, window, cx);
    }

    /// Poignee de focus racine, pour les tests de rendu.
    pub fn focus_handle(&self) -> FocusHandle {
        self.focus.clone()
    }

    fn focus(&mut self, target: FocusId, window: &mut Window, cx: &mut Context<Self>) {
        self.state.focus = target;
        window.focus(&self.focus);
        cx.notify();
    }

    fn start_signature(
        &mut self,
        event: &MouseDownEvent,
        window: &mut Window,
        cx: &mut Context<Self>,
    ) {
        if event.button != MouseButton::Left {
            return;
        }
        self.drawing_signature = true;
        self.state.form.signature.clear();
        self.state.form.signature.push(SignaturePoint {
            x: f32::from(event.position.x),
            y: f32::from(event.position.y),
            kind: checkmate_core::setup::PointKind::Start,
        });
        window.focus(&self.focus);
        cx.notify();
    }

    fn draw_signature(&mut self, event: &MouseMoveEvent, cx: &mut Context<Self>) {
        if !self.drawing_signature {
            return;
        }
        self.state.form.signature.push(SignaturePoint {
            x: f32::from(event.position.x),
            y: f32::from(event.position.y),
            kind: checkmate_core::setup::PointKind::Move,
        });
        cx.notify();
    }

    fn end_signature(&mut self, event: &MouseUpEvent, cx: &mut Context<Self>) {
        if !self.drawing_signature {
            return;
        }
        self.drawing_signature = false;
        self.state.form.signature.push(SignaturePoint {
            x: f32::from(event.position.x),
            y: f32::from(event.position.y),
            kind: checkmate_core::setup::PointKind::End,
        });
        cx.notify();
    }
}

fn to_f32(value: u32) -> f32 {
    f32::from(u16::try_from(value).unwrap_or(u16::MAX))
}

fn finish_message(response: &SetupResult) -> String {
    match response.autostart.as_deref() {
        Some("installed") => {
            "Configuration terminee. Le demarrage automatique est actif.".to_owned()
        }
        Some("failed") => {
            "Configuration terminee, mais le demarrage automatique a echoue.".to_owned()
        }
        Some("disabled") => {
            "Configuration terminee. Le demarrage automatique est desactive.".to_owned()
        }
        _ => response.message.clone(),
    }
}

fn translate_key(event: &KeyDownEvent) -> Key {
    let keystroke = &event.keystroke;
    match keystroke.key.as_str() {
        "tab" => {
            if keystroke.modifiers.shift {
                Key::BackTab
            } else {
                Key::Tab
            }
        }
        "enter" | "return" => Key::Enter,
        "space" => Key::Space,
        "escape" => Key::Escape,
        "backspace" => Key::Backspace,
        _ if keystroke.modifiers.control || keystroke.modifiers.alt => Key::Char(String::new()),
        _ => match &keystroke.key_char {
            Some(text) if !text.is_empty() => Key::Char(text.clone()),
            _ => Key::Char(keystroke.key.clone()),
        },
    }
}

impl Render for CheckmateApp {
    fn render(&mut self, window: &mut Window, cx: &mut Context<Self>) -> impl IntoElement {
        let motion = Motion::from_environment();
        let theme = Theme::for_appearance(window.appearance(), motion);
        if theme != self.theme {
            self.theme = theme;
        }
        let theme = &self.theme;
        let mut root = components::page(theme)
            .relative()
            .debug_selector(|| "app-root".to_owned())
            .track_focus(&self.focus)
            .on_key_down(cx.listener(|this, event: &KeyDownEvent, window, cx| {
                this.apply_key(event, window, cx);
            }))
            .child(views::header(&self.state, theme, cx));

        root = match self.state.overlay.clone() {
            Some(overlay) => root.child(views::modal(&self.state, theme, &overlay, cx)),
            None => match self.state.screen {
                Screen::Dashboard => root.child(views::dashboard(&self.state, theme, cx)),
                Screen::Onboarding => root.child(views::onboarding(
                    &self.state,
                    theme,
                    cx,
                    views::SignatureHandlers {
                        start: cx.listener(|this, event: &MouseDownEvent, window, cx| {
                            this.start_signature(event, window, cx);
                        }),
                        draw: cx.listener(|this, event: &MouseMoveEvent, _, cx| {
                            this.draw_signature(event, cx);
                        }),
                        end: cx.listener(|this, event: &MouseUpEvent, _, cx| {
                            this.end_signature(event, cx);
                        }),
                    },
                )),
            },
        };
        root.child(views::footer(&self.state, theme))
    }
}

/// Lance l'application en fenetre sur le tableau de bord.
pub fn run() {
    run_screen(false);
}

/// Lance l'application directement sur l'assistant.
pub fn run_setup() {
    run_screen(true);
}

fn run_screen(setup: bool) {
    Application::new().run(move |cx: &mut App| {
        let spec = checkmate_platform::DASHBOARD_WINDOW;
        let options = WindowOptions {
            app_id: Some(checkmate_platform::APP_ID.to_owned()),
            window_min_size: Some(gpui::Size {
                width: gpui::px(to_f32(spec.min_width)),
                height: gpui::px(to_f32(spec.min_height)),
            }),
            ..WindowOptions::default()
        };
        let window = cx.open_window(options, |window, cx| {
            let app = cx.new(CheckmateApp::new);
            if setup {
                app.update(cx, CheckmateApp::open_onboarding_initial);
            } else {
                app.update(cx, CheckmateApp::start);
            }
            let focus = app.read(cx).focus.clone();
            window.focus(&focus);
            app
        });
        if let Err(error) = window {
            eprintln!("fenetre indisponible : {error}");
            cx.quit();
        }
        cx.on_window_closed(|cx| cx.quit()).detach();
        cx.activate(true);
    });
}

/// Resume sans fenetre, pour le mode headless et les diagnostics.
pub fn headless_summary(backend: &dyn Backend) -> Result<String, ApiError> {
    let status = backend.status()?;
    Ok(format!(
        "{} {} mode={} creneau={} prochain={}",
        checkmate_core::NAME,
        status.version,
        status.mode,
        status.window.as_deref().unwrap_or("-"),
        status.next_window.as_deref().unwrap_or("-")
    ))
}

/// Libelle accessible de la fenetre courante, utile aux tests et aux journaux.
pub fn describe(state: &AppState) -> String {
    match &state.overlay {
        Some(Overlay::ReleaseNotes(_)) => "Nouveautes".to_owned(),
        Some(Overlay::SignatureConfirmation) => "Confirmation de signature".to_owned(),
        Some(Overlay::ConfirmAction { title, .. }) => title.clone(),
        None => match state.screen {
            Screen::Dashboard => "Tableau de bord".to_owned(),
            Screen::Onboarding => format!("Assistant : {}", state.step.title()),
        },
    }
}

/// Re-export pour les tests de rendu.
pub use crate::views::reference_lines;

#[cfg(test)]
mod tests {
    use super::{describe, headless_summary};
    use crate::client::{ApiError, Backend};
    use crate::state::{AppState, Screen};
    use checkmate_core::setup::{
        Credentials, FinishPayload, SchedulePayload, SetupResult, SetupState, SignaturePayload,
    };
    use checkmate_core::status::StatusSnapshot;
    use gpui::{KeyDownEvent, Keystroke, Modifiers};

    struct Fake;

    impl Backend for Fake {
        fn status(&self) -> Result<StatusSnapshot, ApiError> {
            let raw = include_str!("../../../fixtures/api/status.json");
            Ok(serde_json::from_str(raw).unwrap())
        }
        fn action(
            &self,
            _: &checkmate_core::actions::ActionRequest,
        ) -> Result<checkmate_core::status::ActionResult, ApiError> {
            Ok(checkmate_core::status::ActionResult {
                ok: true,
                ..Default::default()
            })
        }
        fn setup_state(&self) -> Result<SetupState, ApiError> {
            Ok(SetupState::default())
        }
        fn test_login(&self, _: &Credentials) -> Result<SetupResult, ApiError> {
            Ok(SetupResult::default())
        }
        fn save_credentials(&self, _: &Credentials) -> Result<SetupResult, ApiError> {
            Ok(SetupResult::default())
        }
        fn save_signature(&self, _: &SignaturePayload) -> Result<SetupResult, ApiError> {
            Ok(SetupResult::default())
        }
        fn import_signature(&self, _: serde_json::Value) -> Result<SetupResult, ApiError> {
            Ok(SetupResult::default())
        }
        fn save_schedule(&self, _: &SchedulePayload) -> Result<SetupResult, ApiError> {
            Ok(SetupResult::default())
        }
        fn test_notification(&self) -> Result<SetupResult, ApiError> {
            Ok(SetupResult::default())
        }
        fn finish_setup(&self, _: &FinishPayload) -> Result<SetupResult, ApiError> {
            Ok(SetupResult::default())
        }
    }

    fn key(key: &str) -> KeyDownEvent {
        KeyDownEvent {
            keystroke: Keystroke {
                key: key.to_owned(),
                key_char: Some(key.to_owned()),
                modifiers: Modifiers::default(),
            },
            is_held: false,
        }
    }

    #[test]
    fn traduit_les_touches_de_navigation() {
        assert_eq!(super::translate_key(&key("tab")), crate::state::Key::Tab);
        assert_eq!(
            super::translate_key(&key("escape")),
            crate::state::Key::Escape
        );
        assert_eq!(
            super::translate_key(&key("enter")),
            crate::state::Key::Enter
        );
        assert_eq!(
            super::translate_key(&key("e")),
            crate::state::Key::Char("e".to_owned())
        );
    }

    #[test]
    fn decrit_l_ecran_courant() {
        let mut state = AppState::default();
        assert_eq!(describe(&state), "Tableau de bord");
        state.screen = Screen::Onboarding;
        assert_eq!(describe(&state), "Assistant : Bienvenue");
    }

    #[test]
    fn le_mode_headless_resume_l_etat() {
        let summary = headless_summary(&Fake).unwrap();
        assert!(summary.contains("mode=signed"));
        assert!(summary.contains("creneau=08:00-12:30"));
    }
}
