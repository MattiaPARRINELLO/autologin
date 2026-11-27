//! Processus d'icone : `checkmate-ui --tray`.
//!
//! L'icone native et le moteur Python vivent dans deux processus. Ce runner
//! interroge `/api/status`, met a jour l'icone sans la recreer et traduit les
//! clics en actions de `/api/action` ou en ouverture du tableau de bord.

use std::sync::mpsc::{RecvTimeoutError, channel};
use std::time::{Duration, Instant};

use checkmate_core::actions::{ActionKind, ActionRequest};
use checkmate_platform::notify::{self, Notice, NoticeUrgency};
use checkmate_platform::tray::{TrayEvent, TrayMode, TrayState};
use checkmate_ui::client::{Backend, LiveBackend};

const REFRESH_SECONDS: u64 = 10;
/// Apres six lectures muettes, le moteur Python est considere arrete.
const MAX_FAILURES: u32 = 6;

/// Lance l'icone et boucle jusqu'a « Quitter » ou disparition du moteur.
pub fn run() -> i32 {
    let (event_tx, event_rx) = channel();
    let handle =
        match checkmate_platform::tray::start(TrayState::new(TrayMode::Active, ""), event_tx) {
            Ok(handle) => handle,
            Err(error) => {
                checkmate_platform::log::warn(&format!("icone indisponible : {error}"));
                return 1;
            }
        };
    let backend = LiveBackend::discover();
    let mut failures = 0;
    let mut next_poll = Instant::now();
    loop {
        if Instant::now() >= next_poll {
            failures = poll(
                &backend,
                |state| {
                    handle.set_state(state);
                },
                failures,
            );
            if failures >= MAX_FAILURES {
                checkmate_platform::log::warn("service local muet, arret de l'icone");
                break;
            }
            next_poll = Instant::now() + Duration::from_secs(REFRESH_SECONDS);
        }
        match event_rx.recv_timeout(Duration::from_millis(500)) {
            Ok(event) => match handle_event(event, &backend) {
                Flow::Continue => {}
                Flow::Quit => break,
            },
            Err(RecvTimeoutError::Timeout) => {}
            Err(RecvTimeoutError::Disconnected) => break,
        }
    }
    handle.shutdown();
    0
}

enum Flow {
    Continue,
    Quit,
}

fn handle_event(event: TrayEvent, backend: &dyn Backend) -> Flow {
    match event {
        TrayEvent::OpenDashboard => {
            checkmate_platform::spawn_dashboard();
            Flow::Continue
        }
        TrayEvent::Action(kind) => {
            run_action(backend, kind);
            Flow::Continue
        }
        TrayEvent::Quit => {
            run_action(backend, ActionKind::Quit);
            Flow::Quit
        }
    }
}

fn run_action(backend: &dyn Backend, kind: ActionKind) {
    match backend.action(&ActionRequest::new(kind)) {
        Ok(response) => {
            if let Some(message) = response
                .message
                .as_deref()
                .map(str::trim)
                .filter(|message| !message.is_empty())
            {
                let notice = Notice::new("CheckMate", message).with_urgency(NoticeUrgency::Normal);
                let _ = notify::send(&notice);
            }
        }
        Err(error) => {
            checkmate_platform::log::warn(&format!("action {} echouee : {error}", kind.name()));
        }
    }
}

fn poll(backend: &dyn Backend, mut set_state: impl FnMut(TrayState), failures: u32) -> u32 {
    match backend.status() {
        Ok(status) => {
            set_state(TrayState::new(
                TrayMode::from_status(&status.mode),
                status.label,
            ));
            0
        }
        Err(error) => {
            if !error.is_stale() {
                checkmate_platform::log::warn(&format!("lecture du statut : {error}"));
            }
            failures + 1
        }
    }
}

#[cfg(test)]
mod tests {
    use super::{MAX_FAILURES, poll};
    use checkmate_ui::client::{ApiError, Backend};
    use std::sync::atomic::{AtomicU32, Ordering};

    struct ToujoursEnPanne;

    impl Backend for ToujoursEnPanne {
        fn status(&self) -> Result<checkmate_core::status::StatusSnapshot, ApiError> {
            Err(ApiError::Unreachable("test".to_owned()))
        }
        fn action(
            &self,
            _: &checkmate_core::actions::ActionRequest,
        ) -> Result<checkmate_core::status::ActionResult, ApiError> {
            Err(ApiError::Unreachable("test".to_owned()))
        }
        fn setup_state(&self) -> Result<checkmate_core::setup::SetupState, ApiError> {
            Err(ApiError::Unreachable("test".to_owned()))
        }
        fn test_login(
            &self,
            _: &checkmate_core::setup::Credentials,
        ) -> Result<checkmate_core::setup::SetupResult, ApiError> {
            Err(ApiError::Unreachable("test".to_owned()))
        }
        fn save_credentials(
            &self,
            _: &checkmate_core::setup::Credentials,
        ) -> Result<checkmate_core::setup::SetupResult, ApiError> {
            Err(ApiError::Unreachable("test".to_owned()))
        }
        fn save_signature(
            &self,
            _: &checkmate_core::setup::SignaturePayload,
        ) -> Result<checkmate_core::setup::SetupResult, ApiError> {
            Err(ApiError::Unreachable("test".to_owned()))
        }
        fn import_signature(
            &self,
            _: serde_json::Value,
        ) -> Result<checkmate_core::setup::SetupResult, ApiError> {
            Err(ApiError::Unreachable("test".to_owned()))
        }
        fn save_schedule(
            &self,
            _: &checkmate_core::setup::SchedulePayload,
        ) -> Result<checkmate_core::setup::SetupResult, ApiError> {
            Err(ApiError::Unreachable("test".to_owned()))
        }
        fn test_notification(&self) -> Result<checkmate_core::setup::SetupResult, ApiError> {
            Err(ApiError::Unreachable("test".to_owned()))
        }
        fn finish_setup(
            &self,
            _: &checkmate_core::setup::FinishPayload,
        ) -> Result<checkmate_core::setup::SetupResult, ApiError> {
            Err(ApiError::Unreachable("test".to_owned()))
        }
    }

    struct EtatFactice(AtomicU32);

    impl Backend for EtatFactice {
        fn status(&self) -> Result<checkmate_core::status::StatusSnapshot, ApiError> {
            self.0.fetch_add(1, Ordering::SeqCst);
            Ok(checkmate_core::status::StatusSnapshot {
                mode: "signed".to_owned(),
                label: "Creneau signe".to_owned(),
                ..Default::default()
            })
        }
        fn action(
            &self,
            _: &checkmate_core::actions::ActionRequest,
        ) -> Result<checkmate_core::status::ActionResult, ApiError> {
            Ok(checkmate_core::status::ActionResult::default())
        }
        fn setup_state(&self) -> Result<checkmate_core::setup::SetupState, ApiError> {
            Ok(checkmate_core::setup::SetupState::default())
        }
        fn test_login(
            &self,
            _: &checkmate_core::setup::Credentials,
        ) -> Result<checkmate_core::setup::SetupResult, ApiError> {
            Ok(checkmate_core::setup::SetupResult::default())
        }
        fn save_credentials(
            &self,
            _: &checkmate_core::setup::Credentials,
        ) -> Result<checkmate_core::setup::SetupResult, ApiError> {
            Ok(checkmate_core::setup::SetupResult::default())
        }
        fn save_signature(
            &self,
            _: &checkmate_core::setup::SignaturePayload,
        ) -> Result<checkmate_core::setup::SetupResult, ApiError> {
            Ok(checkmate_core::setup::SetupResult::default())
        }
        fn import_signature(
            &self,
            _: serde_json::Value,
        ) -> Result<checkmate_core::setup::SetupResult, ApiError> {
            Ok(checkmate_core::setup::SetupResult::default())
        }
        fn save_schedule(
            &self,
            _: &checkmate_core::setup::SchedulePayload,
        ) -> Result<checkmate_core::setup::SetupResult, ApiError> {
            Ok(checkmate_core::setup::SetupResult::default())
        }
        fn test_notification(&self) -> Result<checkmate_core::setup::SetupResult, ApiError> {
            Ok(checkmate_core::setup::SetupResult::default())
        }
        fn finish_setup(
            &self,
            _: &checkmate_core::setup::FinishPayload,
        ) -> Result<checkmate_core::setup::SetupResult, ApiError> {
            Ok(checkmate_core::setup::SetupResult::default())
        }
    }

    #[test]
    fn six_echecs_arretent_l_icone() {
        let mut failures = 0;
        for _ in 0..MAX_FAILURES {
            failures = poll(&ToujoursEnPanne, |_state| {}, failures);
        }
        assert_eq!(failures, MAX_FAILURES);
    }

    #[test]
    fn une_lecture_reussie_remet_le_compteur_a_zero() {
        let backend = EtatFactice(AtomicU32::new(0));
        let mut updated = None;
        let failures = poll(&backend, |state| updated = Some(state), 4);
        assert_eq!(failures, 0);
        assert_eq!(
            updated.expect("etat transmis").label,
            "Creneau signe".to_owned()
        );
    }
}
