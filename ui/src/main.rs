mod api;

use api::{ActionResponse, Status};
use eframe::egui::{self, Align, Color32, FontId, Layout, RichText, Stroke, TextStyle, Vec2};
use std::sync::mpsc::{Receiver, Sender, channel};
use std::time::{Duration, Instant};

const PAPER: Color32 = Color32::from_rgb(247, 244, 238);
const CARD: Color32 = Color32::from_rgb(253, 251, 247);
const RAISED: Color32 = Color32::from_rgb(239, 233, 223);
const INK: Color32 = Color32::from_rgb(31, 27, 22);
const INK_2: Color32 = Color32::from_rgb(94, 85, 74);
const MUTED: Color32 = Color32::from_rgb(123, 114, 102);
const LINE: Color32 = Color32::from_rgb(224, 218, 208);
const ACCENT: Color32 = Color32::from_rgb(47, 111, 79);
const WARN: Color32 = Color32::from_rgb(154, 107, 47);
const ERR: Color32 = Color32::from_rgb(179, 38, 30);

struct App {
    status: Option<Status>,
    error: Option<String>,
    message: Option<String>,
    status_tx: Sender<Result<Status, String>>,
    status_rx: Receiver<Result<Status, String>>,
    action_tx: Sender<Result<ActionResponse, String>>,
    action_rx: Receiver<Result<ActionResponse, String>>,
    refreshing: bool,
    busy: bool,
    last_refresh: Instant,
    confirm_quit: bool,
}

impl App {
    fn new(context: &eframe::CreationContext<'_>) -> Self {
        configure_style(&context.egui_ctx);
        let (status_tx, status_rx) = channel();
        let (action_tx, action_rx) = channel();
        let mut app = Self {
            status: None,
            error: None,
            message: None,
            status_tx,
            status_rx,
            action_tx,
            action_rx,
            refreshing: false,
            busy: false,
            last_refresh: Instant::now() - Duration::from_secs(10),
            confirm_quit: false,
        };
        app.refresh(context.egui_ctx.clone());
        app
    }

    fn refresh(&mut self, context: egui::Context) {
        if self.refreshing {
            return;
        }
        self.refreshing = true;
        self.last_refresh = Instant::now();
        let sender = self.status_tx.clone();
        std::thread::spawn(move || {
            let _ = sender.send(api::fetch_status().map_err(|error| error.to_string()));
        });
        context.request_repaint();
    }

    fn run_action(&mut self, context: egui::Context, action: &str) {
        if self.busy {
            return;
        }
        self.busy = true;
        self.message = Some("En cours...".to_string());
        let sender = self.action_tx.clone();
        let action = action.to_string();
        std::thread::spawn(move || {
            let _ = sender.send(api::action(&action).map_err(|error| error.to_string()));
        });
        context.request_repaint();
    }

    fn start_backend(&mut self, context: egui::Context) {
        if self.busy {
            return;
        }
        self.busy = true;
        self.error = None;
        self.message = Some("Verification du service...".to_string());
        let sender = self.action_tx.clone();
        std::thread::spawn(move || {
            let result = api::start_backend().map(|()| ActionResponse {
                message: Some("Service demarre. Actualisation...".to_string()),
                ..ActionResponse::default()
            });
            let _ = sender.send(result);
        });
        context.request_repaint();
    }

    fn mode_color(mode: &str) -> Color32 {
        match mode {
            "outside" => WARN,
            "signed" => INK,
            "error" => ERR,
            _ => ACCENT,
        }
    }

    fn short_date(value: &str) -> String {
        if value.is_empty() {
            return "-".to_string();
        }
        value.replace('T', " ").chars().take(16).collect()
    }

    fn draw_header(&self, ui: &mut egui::Ui) {
        ui.horizontal(|ui| {
            ui.vertical(|ui| {
                ui.label(RichText::new("CheckMate").size(22.0).strong().color(INK));
                ui.label(
                    RichText::new("Tableau de bord natif")
                        .size(12.0)
                        .color(MUTED),
                );
            });
            ui.with_layout(Layout::right_to_left(Align::Center), |ui| {
                if let Some(status) = &self.status {
                    ui.label(
                        RichText::new(format!(
                            "Version {} - build {}",
                            status.version, status.build
                        ))
                        .size(12.0)
                        .color(MUTED),
                    );
                }
            });
        });
        ui.add_space(16.0);
    }

    fn draw_status(&mut self, ui: &mut egui::Ui, status: &Status) {
        egui::Frame::new()
            .fill(CARD)
            .stroke(Stroke::new(1.0, LINE))
            .corner_radius(16)
            .inner_margin(24)
            .show(ui, |ui| {
                ui.horizontal(|ui| {
                    ui.label(
                        RichText::new("●")
                            .size(22.0)
                            .color(Self::mode_color(&status.mode)),
                    );
                    ui.vertical(|ui| {
                        ui.label(
                            RichText::new("SURVEILLANCE")
                                .size(11.0)
                                .color(MUTED),
                        );
                        ui.label(
                            RichText::new(&status.label)
                                .size(30.0)
                                .color(INK),
                        );
                        let mut detail = String::new();
                        if let Some(window) = &status.window {
                            detail.push_str(&format!("Creneau {window}. "));
                        }
                        if let Some(next) = &status.next_window {
                            detail.push_str(&format!(
                                "Prochaine ouverture {}.",
                                Self::short_date(next)
                            ));
                        }
                        if !status.schedule.enabled {
                            detail = "Le planning est desactive, la surveillance est continue."
                                .to_string();
                        }
                        ui.label(RichText::new(detail).size(14.0).color(INK_2));
                    });
                });

                if status.restart_required {
                    ui.add_space(16.0);
                    ui.label(
                        RichText::new(
                            "La configuration a change. Quitte CheckMate puis relance-le pour l'appliquer.",
                        )
                        .size(13.0)
                        .color(WARN),
                    );
                }

                ui.add_space(20.0);
                ui.separator();
                ui.add_space(10.0);
                ui.label(RichText::new("Creneaux surveilles").size(12.0).color(MUTED));
                ui.horizontal_wrapped(|ui| {
                    for window in &status.schedule.windows {
                        let current = status.window.as_deref() == Some(window.as_str());
                        egui::Frame::new()
                            .fill(if current { RAISED } else { CARD })
                            .stroke(Stroke::new(1.0, if current { ACCENT } else { LINE }))
                            .corner_radius(8)
                            .inner_margin(egui::Margin::symmetric(10, 6))
                            .show(ui, |ui| {
                                ui.label(
                                    RichText::new(window)
                                        .monospace()
                                        .size(13.0)
                                        .color(if current { INK } else { INK_2 }),
                                );
                            });
                    }
                });

                ui.add_space(20.0);
                ui.separator();
                ui.add_space(10.0);
                egui::Grid::new("counters")
                    .num_columns(4)
                    .spacing([28.0, 8.0])
                    .show(ui, |ui| {
                        for (label, value) in [
                            ("Demarrages", status.counters.starts),
                            ("Detections", status.counters.detections),
                            ("Signatures", status.counters.signed),
                            ("Erreurs", status.counters.errors),
                        ] {
                            ui.vertical(|ui| {
                                ui.label(RichText::new(label).size(12.0).color(MUTED));
                                ui.label(
                                    RichText::new(value.to_string())
                                        .monospace()
                                        .size(24.0)
                                        .color(INK),
                                );
                            });
                        }
                        ui.end_row();
                    });

                ui.add_space(16.0);
                ui.separator();
                ui.add_space(8.0);
                for (label, value) in [
                    ("Demarre le", status.started_at.as_str()),
                    ("Derniere detection", status.last_detection_at.as_deref().unwrap_or("")),
                    ("Derniere signature", status.last_signed_at.as_deref().unwrap_or("")),
                ] {
                    ui.horizontal(|ui| {
                        ui.label(RichText::new(label).size(13.0).color(INK_2));
                        ui.with_layout(Layout::right_to_left(Align::Center), |ui| {
                            ui.label(
                                RichText::new(Self::short_date(value))
                                    .monospace()
                                    .size(13.0)
                                    .color(INK),
                            );
                        });
                    });
                }

                ui.add_space(20.0);
                ui.horizontal_wrapped(|ui| {
                    let busy = self.busy;
                    if ui
                        .add_enabled(
                            !busy,
                            egui::Button::new(
                                RichText::new("Tester la notification").color(INK),
                            )
                            .fill(RAISED)
                            .min_size(Vec2::new(0.0, 38.0)),
                        )
                        .clicked()
                    {
                        self.run_action(ui.ctx().clone(), "test-notification");
                    }
                    if ui
                        .add_enabled(
                            !busy,
                            egui::Button::new(
                                RichText::new("Verifier les mises a jour").color(INK),
                            )
                            .fill(CARD)
                            .stroke(Stroke::new(1.0, LINE))
                            .min_size(Vec2::new(0.0, 38.0)),
                        )
                        .clicked()
                    {
                        self.run_action(ui.ctx().clone(), "check-update");
                    }
                    if ui
                        .add_enabled(
                            !busy,
                            egui::Button::new(RichText::new("Ouvrir les logs").color(INK))
                                .fill(CARD)
                                .stroke(Stroke::new(1.0, LINE))
                                .min_size(Vec2::new(0.0, 38.0)),
                        )
                        .clicked()
                    {
                        self.run_action(ui.ctx().clone(), "open-logs");
                    }
                    if self.confirm_quit {
                        if ui
                            .add_enabled(
                                !busy,
                                egui::Button::new(
                                    RichText::new("Confirmer l'arret").color(Color32::WHITE),
                                )
                                .fill(ERR)
                                .min_size(Vec2::new(0.0, 38.0)),
                            )
                            .clicked()
                        {
                            self.confirm_quit = false;
                            self.run_action(ui.ctx().clone(), "quit");
                        }
                        if ui.button("Annuler").clicked() {
                            self.confirm_quit = false;
                        }
                    } else if ui
                        .add_enabled(
                            !busy,
                            egui::Button::new(RichText::new("Quitter CheckMate").color(MUTED))
                                .fill(Color32::TRANSPARENT),
                        )
                        .clicked()
                    {
                        self.confirm_quit = true;
                    }
                });
            });
    }

    fn draw_offline(&mut self, ui: &mut egui::Ui) {
        egui::Frame::new()
            .fill(CARD)
            .stroke(Stroke::new(1.0, LINE))
            .corner_radius(16)
            .inner_margin(24)
            .show(ui, |ui| {
                ui.label(RichText::new("●").size(22.0).color(ERR));
                ui.label(RichText::new("Service arrete").size(30.0).color(INK));
                ui.label(
                    RichText::new(
                        "Le moteur CheckMate ne repond pas. Demarre-le pour afficher l'etat.",
                    )
                    .size(14.0)
                    .color(INK_2),
                );
                if let Some(error) = &self.error {
                    ui.add_space(8.0);
                    ui.label(RichText::new(error).size(12.0).color(MUTED));
                }
                ui.add_space(16.0);
                if ui
                    .add(
                        egui::Button::new(
                            RichText::new("Demarrer le service").color(Color32::WHITE),
                        )
                        .fill(ACCENT)
                        .min_size(Vec2::new(0.0, 40.0)),
                    )
                    .clicked()
                {
                    self.start_backend(ui.ctx().clone());
                }
            });
    }
}

impl eframe::App for App {
    fn ui(&mut self, root: &mut egui::Ui, _frame: &mut eframe::Frame) {
        let context = root.ctx().clone();
        while let Ok(event) = self.status_rx.try_recv() {
            self.refreshing = false;
            match event {
                Ok(status) => {
                    self.status = Some(status);
                    self.error = None;
                }
                Err(error) => {
                    self.status = None;
                    self.error = Some(error);
                }
            }
        }
        while let Ok(event) = self.action_rx.try_recv() {
            self.busy = false;
            match event {
                Ok(response) => {
                    let mut message = response.message.unwrap_or_default();
                    if response.available == Some(true)
                        && let Some(url) = response.url
                    {
                        message = format!("{message} {url}");
                    }
                    self.message = Some(message);
                }
                Err(error) => self.message = Some(error),
            }
        }

        if self.last_refresh.elapsed() > Duration::from_secs(3) && !self.refreshing {
            self.refresh(context.clone());
        }

        egui::Frame::new()
            .fill(PAPER)
            .inner_margin(28)
            .show(root, |ui| {
                self.draw_header(ui);
                if let Some(status) = self.status.clone() {
                    self.draw_status(ui, &status);
                } else {
                    self.draw_offline(ui);
                }
                if let Some(message) = &self.message {
                    ui.add_space(12.0);
                    ui.label(RichText::new(message).size(13.0).color(INK_2));
                }
                ui.add_space(12.0);
                ui.label(
                    RichText::new("Local uniquement, aucun serveur.")
                        .size(12.0)
                        .color(MUTED),
                );
            });

        root.ctx().request_repaint_after(Duration::from_millis(500));
    }
}

fn configure_style(context: &egui::Context) {
    let mut visuals = egui::Visuals::light();
    visuals.panel_fill = PAPER;
    visuals.window_fill = CARD;
    visuals.extreme_bg_color = Color32::WHITE;
    visuals.faint_bg_color = RAISED;
    visuals.override_text_color = Some(INK);
    visuals.selection.bg_fill = ACCENT;
    visuals.widgets.inactive.bg_fill = RAISED;
    visuals.widgets.inactive.fg_stroke.color = INK;
    visuals.widgets.hovered.bg_fill = Color32::from_rgb(230, 223, 212);
    visuals.widgets.active.bg_fill = Color32::from_rgb(220, 212, 199);
    context.set_visuals(visuals);

    let mut style = (*context.style_of(egui::Theme::Light)).clone();
    style.spacing.item_spacing = egui::vec2(10.0, 8.0);
    style
        .text_styles
        .insert(TextStyle::Heading, FontId::proportional(28.0));
    context.set_style_of(egui::Theme::Light, style);
}

fn main() -> eframe::Result<()> {
    let options = eframe::NativeOptions {
        viewport: egui::ViewportBuilder::default()
            .with_inner_size([940.0, 760.0])
            .with_min_inner_size([680.0, 560.0]),
        ..Default::default()
    };
    eframe::run_native(
        "CheckMate",
        options,
        Box::new(|context| Ok(Box::new(App::new(context)))),
    )
}
