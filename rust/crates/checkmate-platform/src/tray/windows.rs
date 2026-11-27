//! Icone Windows dans la zone de notification.
//!
//! `tray-icon` dessine l'icone native et son menu. `winit` fournit la boucle
//! de messages Win32 exigeE par la zone de notification, sans unsafe dans
//! notre crate. Un double-clic ouvre le tableau de bord.

use std::sync::mpsc::Sender;
use std::time::Duration;

use tray_icon::menu::{Menu, MenuEvent, MenuItem, PredefinedMenuItem};
use tray_icon::{Icon, TrayIcon, TrayIconBuilder, TrayIconEvent};
use winit::application::ApplicationHandler;
use winit::event::WindowEvent;
use winit::event_loop::{ActiveEventLoop, EventLoop, EventLoopProxy};

use super::{TRAY_ACTIONS, TrayError, TrayEvent, TrayState};
use crate::icon;

const ICON_ID: &str = "checkmate-tray";
const OPEN_ID: &str = "checkmate.open";
const QUIT_ID: &str = "checkmate.quit";
const ACTION_PREFIX: &str = "checkmate.action.";

enum UserEvent {
    Update(TrayState),
    Shutdown,
}

/// Poignee d'une icone Windows en cours.
pub struct TrayHandle {
    proxy: EventLoopProxy<UserEvent>,
    thread: Option<std::thread::JoinHandle<()>>,
}

impl TrayHandle {
    /// Met a jour l'icone et son infobulle sans recreer l'item.
    pub fn set_state(&self, state: TrayState) -> bool {
        self.proxy.send_event(UserEvent::Update(state)).is_ok()
    }

    /// Retire l'icone de la zone de notification puis attend la boucle.
    pub fn shutdown(mut self) {
        let _ = self.proxy.send_event(UserEvent::Shutdown);
        if let Some(thread) = self.thread.take() {
            let _ = thread.join();
        }
    }
}

impl Drop for TrayHandle {
    fn drop(&mut self) {
        let _ = self.proxy.send_event(UserEvent::Shutdown);
    }
}

struct TrayApp {
    state: TrayState,
    tray: Option<TrayIcon>,
    #[allow(dead_code)]
    menu_items: Vec<MenuItem>,
    #[allow(dead_code)]
    separator: Option<PredefinedMenuItem>,
    proxy: EventLoopProxy<UserEvent>,
}

impl TrayApp {
    fn build_menu(&mut self) -> Menu {
        let open = MenuItem::with_id(OPEN_ID, "Ouvrir le statut", true, None);
        self.menu_items.push(open);
        for kind in TRAY_ACTIONS {
            let id = format!("{ACTION_PREFIX}{}", kind.name());
            self.menu_items
                .push(MenuItem::with_id(id, kind.label(), true, None));
        }
        let separator = PredefinedMenuItem::separator();
        let quit = MenuItem::with_id(QUIT_ID, "Quitter", true, None);
        self.menu_items.push(quit);
        let menu = Menu::new();
        let mut refs: Vec<&dyn tray_icon::menu::IsMenuItem> = Vec::new();
        if let Some(first) = self.menu_items.first() {
            refs.push(first);
        }
        for item in self.menu_items.iter().skip(1).take(TRAY_ACTIONS.len()) {
            refs.push(item);
        }
        refs.push(&separator);
        if let Some(last) = self.menu_items.last() {
            refs.push(last);
        }
        let _ = menu.append_items(&refs);
        self.separator = Some(separator);
        menu
    }

    fn create_tray(&mut self) -> Result<(), String> {
        if self.tray.is_some() {
            return Ok(());
        }
        let menu = self.build_menu();
        let icon = Icon::from_rgba(
            icon::rgba(self.state.mode),
            icon::ICON_SIZE,
            icon::ICON_SIZE,
        )
        .map_err(|error| format!("icone Windows invalide : {error}"))?;
        let tray = TrayIconBuilder::new()
            .with_id(ICON_ID)
            .with_icon(icon)
            .with_tooltip(self.state.title())
            .with_menu(Box::new(menu))
            .with_menu_on_left_click(false)
            .with_menu_on_right_click(true)
            .build()
            .map_err(|error| format!("zone de notification Windows : {error}"))?;
        self.tray = Some(tray);
        Ok(())
    }

    fn apply(&mut self, state: TrayState) {
        self.state = state;
        let Some(tray) = &self.tray else {
            return;
        };
        if let Ok(icon) = Icon::from_rgba(
            icon::rgba(self.state.mode),
            icon::ICON_SIZE,
            icon::ICON_SIZE,
        ) {
            let _ = tray.set_icon(Some(icon));
        }
        let _ = tray.set_tooltip(Some(self.state.title()));
    }
}

impl ApplicationHandler<UserEvent> for TrayApp {
    fn resumed(&mut self, event_loop: &ActiveEventLoop) {
        event_loop.set_control_flow(winit::event_loop::ControlFlow::Wait);
        if self.tray.is_none()
            && let Err(error) = self.create_tray()
        {
            crate::log::warn(&error);
            event_loop.exit();
        }
    }

    fn user_event(&mut self, event_loop: &ActiveEventLoop, event: UserEvent) {
        match event {
            UserEvent::Update(state) => self.apply(state),
            UserEvent::Shutdown => {
                self.tray = None;
                self.menu_items.clear();
                self.separator = None;
                event_loop.exit();
            }
        }
    }

    fn window_event(
        &mut self,
        _event_loop: &ActiveEventLoop,
        _window_id: winit::window::WindowId,
        _event: WindowEvent,
    ) {
    }
}

/// Demarre l'icone Windows et rend la main une fois l'item cree.
pub fn start(initial: TrayState, events: Sender<TrayEvent>) -> Result<TrayHandle, TrayError> {
    let (ready_tx, ready_rx) = std::sync::mpsc::channel();
    let thread = std::thread::Builder::new()
        .name("checkmate-tray".to_owned())
        .spawn(move || run(initial, &events, &ready_tx))
        .map_err(|error| TrayError::unavailable(format!("thread icone : {error}")))?;
    match ready_rx.recv_timeout(Duration::from_secs(5)) {
        Ok(Ok(proxy)) => Ok(TrayHandle {
            proxy,
            thread: Some(thread),
        }),
        Ok(Err(message)) => {
            let _ = thread.join();
            Err(TrayError::unavailable(message))
        }
        Err(error) => Err(TrayError::unavailable(format!(
            "zone de notification sans reponse : {error}"
        ))),
    }
}

fn run(
    initial: TrayState,
    events: &Sender<TrayEvent>,
    ready: &std::sync::mpsc::Sender<Result<EventLoopProxy<UserEvent>, String>>,
) {
    let event_loop = match EventLoop::<UserEvent>::with_user_event().build() {
        Ok(event_loop) => event_loop,
        Err(error) => {
            let _ = ready.send(Err(format!("boucle Windows indisponible : {error}")));
            return;
        }
    };
    let proxy = event_loop.create_proxy();
    let menu_events = events.clone();
    MenuEvent::set_event_handler(Some(std::sync::Arc::new(move |event: MenuEvent| {
        let id = event.id().0.as_str();
        let mapped = match id {
            OPEN_ID => Some(TrayEvent::OpenDashboard),
            QUIT_ID => Some(TrayEvent::Quit),
            _ => id
                .strip_prefix(ACTION_PREFIX)
                .and_then(action_from_name)
                .map(TrayEvent::Action),
        };
        if let Some(mapped) = mapped {
            let _ = menu_events.send(mapped);
        }
    })));
    let tray_events = events.clone();
    TrayIconEvent::set_event_handler(Some(move |event: TrayIconEvent| {
        if matches!(event, TrayIconEvent::DoubleClick { .. }) {
            let _ = tray_events.send(TrayEvent::OpenDashboard);
        }
    }));
    let mut app = TrayApp {
        state: initial,
        tray: None,
        menu_items: Vec::new(),
        separator: None,
        proxy,
    };
    if let Err(error) = app.create_tray() {
        let _ = ready.send(Err(error));
        return;
    }
    let _ = ready.send(Ok(app.proxy.clone()));
    if let Err(error) = event_loop.run_app(&mut app) {
        crate::log::warn(&format!("boucle Windows arretee : {error}"));
    }
}

fn action_from_name(name: &str) -> Option<checkmate_core::actions::ActionKind> {
    TRAY_ACTIONS.into_iter().find(|kind| kind.name() == name)
}
