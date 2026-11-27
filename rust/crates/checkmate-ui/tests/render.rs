//! Tests de rendu `gpui::test` et captures textuelles de reference.
//!
//! GPUI 0.2.2 ne fournit pas d'API de capture d'image. Les captures sont donc
//! textuelles : elles figent l'ecran, le focus et les donnees affichees. Une
//! derive echoue avec un diff explicite. Pour regenerer volontairement :
//!
//! ```text
//! UPDATE_SNAPSHOTS=1 cargo test -p checkmate-ui --test render
//! ```

#![cfg(any(target_os = "linux", target_os = "freebsd"))]

use std::sync::Arc;

use gpui::{Modifiers, TestAppContext};

use checkmate_core::actions::ActionRequest;
use checkmate_core::setup::{
    Credentials, FinishPayload, SchedulePayload, SetupResult, SetupState, SetupStep,
    SignaturePayload,
};
use checkmate_core::status::{ActionResult, StatusSnapshot};
use checkmate_ui::app::CheckmateApp;
use checkmate_ui::client::{ApiError, Backend};
use checkmate_ui::state::{FormState, Loadable, Overlay};
use checkmate_ui::views;

struct Fake;

impl Fake {
    fn status() -> StatusSnapshot {
        serde_json::from_str(include_str!("../../../fixtures/api/status.json")).unwrap()
    }

    fn setup() -> SetupState {
        serde_json::from_str(include_str!("../../../fixtures/api/setup-state.json")).unwrap()
    }
}

impl Backend for Fake {
    fn status(&self) -> Result<StatusSnapshot, ApiError> {
        Ok(Self::status())
    }
    fn action(&self, _: &ActionRequest) -> Result<ActionResult, ApiError> {
        Ok(ActionResult {
            ok: true,
            ..ActionResult::default()
        })
    }
    fn setup_state(&self) -> Result<SetupState, ApiError> {
        Ok(Self::setup())
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

type Harness<'a> = (gpui::Entity<CheckmateApp>, &'a mut gpui::VisualTestContext);

fn harness(cx: &mut TestAppContext) -> Harness<'_> {
    let (view, visual) = cx.add_window_view(|_, cx| CheckmateApp::with_backend(cx, Arc::new(Fake)));
    view.update(&mut visual.cx, |app, cx| {
        app.state.status = Loadable::Ready(Fake::status());
        app.state.ensure_focus();
        cx.notify();
    });
    (view, visual)
}

fn draw(cx: &mut gpui::VisualTestContext) {
    cx.update(|window, app| {
        let _ = window.draw(app);
    });
}

fn snapshot(state: &checkmate_ui::state::AppState, name: &str) {
    let expected = views::reference_lines(state).join("\n") + "\n";
    let path = std::path::Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("tests")
        .join("snapshots")
        .join(format!("{name}-{}.txt", std::env::consts::OS));
    if std::env::var("UPDATE_SNAPSHOTS").is_ok_and(|value| value == "1") {
        std::fs::create_dir_all(path.parent().unwrap()).unwrap();
        std::fs::write(&path, &expected).unwrap();
        return;
    }
    let actual = std::fs::read_to_string(&path).unwrap_or_else(|_| {
        panic!(
            "capture absente : {}. Lance UPDATE_SNAPSHOTS=1 cargo test -p checkmate-ui --test render",
            path.display()
        )
    });
    assert_eq!(actual, expected, "derive de rendu dans {}", path.display());
}

#[gpui::test]
fn le_tableau_de_bord_se_rend(cx: &mut TestAppContext) {
    let (view, visual) = harness(cx);
    draw(visual);
    assert!(visual.debug_bounds("dashboard").is_some());
    assert!(visual.debug_bounds("header").is_some());
    for action in checkmate_core::actions::ActionKind::dashboard_actions() {
        let selector = match action {
            checkmate_core::actions::ActionKind::TestNotification => "action-test-notification",
            checkmate_core::actions::ActionKind::CheckUpdate => "action-check-update",
            checkmate_core::actions::ActionKind::OpenLogs => "action-open-logs",
            checkmate_core::actions::ActionKind::Configure => "action-configure",
            checkmate_core::actions::ActionKind::Quit => "action-quit",
            _ => continue,
        };
        assert!(
            visual.debug_bounds(selector).is_some(),
            "bouton absent : {selector}"
        );
    }
    view.update(&mut visual.cx, |app, _| snapshot(&app.state, "dashboard"));
}

#[gpui::test]
fn chaque_etape_de_l_assistant_se_rend(cx: &mut TestAppContext) {
    let (view, visual) = harness(cx);
    view.update(&mut visual.cx, |app, cx| {
        app.state.open_onboarding();
        app.state.setup = Some(Fake::setup());
        app.state.form = FormState::from_setup(&Fake::setup());
        cx.notify();
    });
    for step in SetupStep::ALL {
        view.update(&mut visual.cx, |app, cx| {
            app.state.step = step;
            app.state.ensure_focus();
            cx.notify();
        });
        draw(visual);
        let selector = match step {
            SetupStep::Presentation => "step-0",
            SetupStep::Credentials => "step-1",
            SetupStep::Signature => "step-2",
            SetupStep::Schedule => "step-3",
            SetupStep::Finish => "step-4",
        };
        assert!(
            visual.debug_bounds(selector).is_some(),
            "etape absente : {selector}"
        );
        if step == SetupStep::Signature {
            assert!(visual.debug_bounds("signature-pad").is_some());
        }
        view.update(&mut visual.cx, |app, _| {
            snapshot(&app.state, &format!("assistant-{}", step.index() + 1));
        });
    }
}

#[gpui::test]
fn la_modale_piege_le_focus(cx: &mut TestAppContext) {
    let (view, visual) = harness(cx);
    let note = Fake::status().release_note.unwrap();
    view.update(&mut visual.cx, |app, cx| {
        app.state.overlay = Some(Overlay::ReleaseNotes(note));
        app.state.ensure_focus();
        cx.notify();
    });
    draw(visual);
    assert!(visual.debug_bounds("modal").is_some(), "fond modal absent");
    assert!(
        visual.debug_bounds("modal-card").is_some(),
        "carte modale absente"
    );
    view.update(&mut visual.cx, |app, _| {
        assert_eq!(
            app.state.focus_order().len(),
            1,
            "focus piege dans la modale"
        );
    });
    view.update(&mut visual.cx, |app, _| {
        snapshot(&app.state, "modale-nouveautes");
    });
}

#[gpui::test]
fn echap_ferme_la_modale_au_clavier(cx: &mut TestAppContext) {
    let (view, visual) = harness(cx);
    view.update(&mut visual.cx, |app, cx| {
        app.state.overlay = Some(Overlay::SignatureConfirmation);
        app.state.ensure_focus();
        cx.notify();
    });
    let focus = view.read_with(&visual.cx, |app, _| app.focus_handle());
    visual.update(|window, _| window.focus(&focus));
    draw(visual);
    visual.simulate_event(gpui::KeyDownEvent {
        keystroke: gpui::Keystroke {
            key: "escape".to_owned(),
            key_char: None,
            modifiers: Modifiers::default(),
        },
        is_held: false,
    });
    view.update(&mut visual.cx, |app, _| {
        assert!(app.state.overlay.is_none(), "Echap doit fermer la modale");
    });
}

#[gpui::test]
fn le_focus_se_deplace_au_clavier(cx: &mut TestAppContext) {
    let (view, visual) = harness(cx);
    draw(visual);
    let focus = view.read_with(&visual.cx, |app, _| app.focus_handle());
    visual.update(|window, _| window.focus(&focus));
    visual.simulate_keystrokes("tab");
    view.update(&mut visual.cx, |app, _| {
        assert_eq!(
            app.state.focus,
            checkmate_ui::state::FocusId::DashboardAction(
                checkmate_core::actions::ActionKind::CheckUpdate
            )
        );
    });
}
