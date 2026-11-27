//! Icone Linux via StatusNotifierItem.
//!
//! `ksni` publie l'item et son menu D-Bus. Un thread dedie porte la boucle
//! tokio demandee par `ksni` ; les mises a jour passent par un canal pour ne
//! jamais recreer l'item.

use std::sync::mpsc::Sender;
use std::time::Duration;

use ksni::menu::{MenuItem as KsniMenuItem, StandardItem};
use ksni::{Icon, Status, ToolTip, Tray, TrayMethods};
use tokio::sync::mpsc::{UnboundedSender, unbounded_channel};

use super::{TRAY_ACTIONS, TrayError, TrayEvent, TrayState};
use crate::icon;

enum Command {
    Update(TrayState),
    Shutdown,
}

/// Poignee d'une icone Linux en cours.
pub struct TrayHandle {
    sender: UnboundedSender<Command>,
    thread: Option<std::thread::JoinHandle<()>>,
}

impl TrayHandle {
    /// Met a jour l'etat sans recreer l'item.
    pub fn set_state(&self, state: TrayState) -> bool {
        self.sender.send(Command::Update(state)).is_ok()
    }

    /// Retire l'icone et attend la fin du thread.
    pub fn shutdown(mut self) {
        let _ = self.sender.send(Command::Shutdown);
        if let Some(thread) = self.thread.take() {
            let _ = thread.join();
        }
    }
}

impl Drop for TrayHandle {
    fn drop(&mut self) {
        let _ = self.sender.send(Command::Shutdown);
    }
}

struct SniTray {
    state: TrayState,
    events: Sender<TrayEvent>,
}

impl SniTray {
    fn emit(&self, event: TrayEvent) {
        let _ = self.events.send(event);
    }

    fn item<F>(label: &str, activate: F) -> KsniMenuItem<Self>
    where
        F: Fn(&mut Self) + Send + 'static,
    {
        StandardItem {
            label: label.to_owned(),
            activate: Box::new(activate),
            ..Default::default()
        }
        .into()
    }
}

impl Tray for SniTray {
    const MENU_ON_ACTIVATE: bool = false;

    fn id(&self) -> String {
        "checkmate".to_owned()
    }

    fn title(&self) -> String {
        self.state.title()
    }

    fn status(&self) -> Status {
        if self.state.mode.needs_attention() {
            Status::NeedsAttention
        } else {
            Status::Active
        }
    }

    fn icon_pixmap(&self) -> Vec<Icon> {
        [64_u32, 32]
            .into_iter()
            .map(|size| Icon {
                width: i32::try_from(size).unwrap_or(i32::MAX),
                height: i32::try_from(size).unwrap_or(i32::MAX),
                data: resized_argb(self.state.mode, size),
            })
            .collect()
    }

    fn tool_tip(&self) -> ToolTip {
        ToolTip {
            icon_name: String::new(),
            icon_pixmap: self.icon_pixmap(),
            title: self.state.title(),
            description: self.state.label.clone(),
        }
    }

    fn activate(&mut self, _x: i32, _y: i32) {
        self.emit(TrayEvent::OpenDashboard);
    }

    fn secondary_activate(&mut self, _x: i32, _y: i32) {
        self.emit(TrayEvent::OpenDashboard);
    }

    fn menu(&self) -> Vec<KsniMenuItem<Self>> {
        let mut items = vec![Self::item("Ouvrir le statut", |tray| {
            tray.emit(TrayEvent::OpenDashboard);
        })];
        for kind in TRAY_ACTIONS {
            items.push(Self::item(kind.label(), move |tray| {
                tray.emit(TrayEvent::Action(kind));
            }));
        }
        items.push(KsniMenuItem::Separator);
        items.push(Self::item("Quitter", |tray| {
            tray.emit(TrayEvent::Quit);
        }));
        items
    }
}

/// Demarre l'icone et rend la main une fois l'enregistrement D-Bus termine.
pub fn start(initial: TrayState, events: Sender<TrayEvent>) -> Result<TrayHandle, TrayError> {
    let (command_tx, command_rx) = unbounded_channel();
    let (ready_tx, ready_rx) = std::sync::mpsc::channel();
    let thread = std::thread::Builder::new()
        .name("checkmate-tray".to_owned())
        .spawn(move || run(initial, events, command_rx, &ready_tx))
        .map_err(|error| TrayError::unavailable(format!("thread icone : {error}")))?;
    match ready_rx.recv_timeout(Duration::from_secs(5)) {
        Ok(Ok(())) => Ok(TrayHandle {
            sender: command_tx,
            thread: Some(thread),
        }),
        Ok(Err(message)) => {
            let _ = thread.join();
            Err(TrayError::unavailable(message))
        }
        Err(error) => {
            let _ = command_tx.send(Command::Shutdown);
            Err(TrayError::unavailable(format!(
                "enregistrement D-Bus sans reponse : {error}"
            )))
        }
    }
}

fn run(
    initial: TrayState,
    events: Sender<TrayEvent>,
    mut commands: tokio::sync::mpsc::UnboundedReceiver<Command>,
    ready: &std::sync::mpsc::Sender<Result<(), String>>,
) {
    let runtime = match tokio::runtime::Builder::new_multi_thread()
        .enable_all()
        .build()
    {
        Ok(runtime) => runtime,
        Err(error) => {
            let _ = ready.send(Err(format!("boucle tokio indisponible : {error}")));
            return;
        }
    };
    runtime.block_on(async move {
        let tray = SniTray {
            state: initial,
            events,
        };
        let handle = match tray.spawn().await {
            Ok(handle) => handle,
            Err(error) => {
                let _ = ready.send(Err(format!("icone StatusNotifierItem : {error}")));
                return;
            }
        };
        let _ = ready.send(Ok(()));
        while let Some(command) = commands.recv().await {
            match command {
                Command::Update(state) => {
                    let _ = handle.update(|tray| tray.state = state).await;
                }
                Command::Shutdown => {
                    handle.shutdown().await;
                    break;
                }
            }
        }
    });
}

fn resized_argb(mode: crate::icon::TrayMode, size: u32) -> Vec<u8> {
    if size == icon::ICON_SIZE {
        return icon::argb32(mode);
    }
    let source = icon::argb32(mode);
    let mut output = vec![0_u8; (size * size * 4) as usize];
    let ratio = icon::ICON_SIZE / size;
    for y in 0..size {
        for x in 0..size {
            let source_x = x * ratio;
            let source_y = y * ratio;
            let source_index = ((source_y * icon::ICON_SIZE + source_x) * 4) as usize;
            let target_index = ((y * size + x) * 4) as usize;
            output[target_index..target_index + 4]
                .copy_from_slice(&source[source_index..source_index + 4]);
        }
    }
    output
}
