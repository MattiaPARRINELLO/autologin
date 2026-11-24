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
        Self::request_status(self.status_tx.clone());
        context.request_repaint();
    }

    fn request_status(sender: Sender<Result<Status, String>>) {
        std::thread::spawn(move || {
            let result = api::fetch_status().map_err(|error| error.to_string());
            let _ = sender.send(result);
        });
    }

    fn run_action(&mut self, context: egui::Context, action: &str) {
        if self.busy {
            return;
        }
        self.busy = true;
        self.message = Some("En cours...".to_string());
        Self::request_action(self.action_tx.clone(), action.to_string());
        context.request_repaint();
    }

    fn request_action(sender: Sender<Result<ActionResponse, String>>, action: String) {
        std::thread::spawn(move || {
            let result = api::action(&action).map_err(|error| error.to_string());
            let _ = sender.send(result);
        });
    }

    fn start_backend(&mut self, context: egui::Context) {
        if self.busy {
            return;
        }
        self.busy = true;
        self.error = None;
        self.message = Some("Verification du service...".to_string());
        Self::request_start(self.action_tx.clone());
        context.request_repaint();
    }

    fn request_start(sender: Sender<Result<ActionResponse, String>>) {
        std::thread::spawn(move || {
            let result = api::start_backend().map(|()| ActionResponse {
                message: Some("Service demarre. Actualisation...".to_string()),
                ..ActionResponse::default()
            });
            let _ = sender.send(result);
        });
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
            Self::draw_title(ui);
            Self::draw_version(ui, self.status.as_ref());
        });
        ui.add_space(16.0);
    }

    fn draw_title(ui: &mut egui::Ui) {
        ui.vertical(|ui| {
            ui.label(RichText::new("CheckMate").size(22.0).strong().color(INK));
            let subtitle = RichText::new("Tableau de bord natif")
                .size(12.0)
                .color(MUTED);
            ui.label(subtitle);
        });
    }

    fn draw_version(ui: &mut egui::Ui, status: Option<&Status>) {
        ui.with_layout(Layout::right_to_left(Align::Center), |ui| {
            let Some(status) = status else { return };
            let label = format!("Version {} - build {}", status.version, status.build);
            ui.label(RichText::new(label).size(12.0).color(MUTED));
        });
    }

    fn card_frame() -> egui::Frame {
        egui::Frame::new()
            .fill(CARD)
            .stroke(Stroke::new(1.0, LINE))
            .corner_radius(16)
            .inner_margin(24)
    }

    fn draw_status(&mut self, ui: &mut egui::Ui, status: &Status) {
        Self::card_frame().show(ui, |ui| {
            Self::draw_monitor(ui, status);
            Self::draw_restart_notice(ui, status);
            Self::draw_windows(ui, status);
            Self::draw_counters(ui, status);
            Self::draw_dates(ui, status);
            self.draw_actions(ui);
        });
    }

    fn draw_monitor(ui: &mut egui::Ui, status: &Status) {
        ui.horizontal(|ui| {
            let color = Self::mode_color(&status.mode);
            ui.label(RichText::new("●").size(22.0).color(color));
            ui.vertical(|ui| Self::monitor_text(ui, status));
        });
    }

    fn monitor_text(ui: &mut egui::Ui, status: &Status) {
        ui.label(RichText::new("SURVEILLANCE").size(11.0).color(MUTED));
        ui.label(RichText::new(&status.label).size(30.0).color(INK));
        let detail = Self::detail(status);
        ui.label(RichText::new(detail).size(14.0).color(INK_2));
    }

    fn detail(status: &Status) -> String {
        if !status.schedule.enabled {
            return "Le planning est desactive, la surveillance est continue.".to_string();
        }
        let mut detail = String::new();
        Self::push_window(&mut detail, status);
        Self::push_next_window(&mut detail, status);
        detail
    }

    fn push_window(detail: &mut String, status: &Status) {
        if let Some(window) = &status.window {
            detail.push_str(&format!("Creneau {window}. "));
        }
    }

    fn push_next_window(detail: &mut String, status: &Status) {
        if let Some(next) = &status.next_window {
            detail.push_str(&format!("Prochaine ouverture {}.", Self::short_date(next)));
        }
    }

    fn draw_restart_notice(ui: &mut egui::Ui, status: &Status) {
        if !status.restart_required {
            return;
        }
        ui.add_space(16.0);
        let message =
            "La configuration a change. Quitte CheckMate puis relance-le pour l'appliquer.";
        ui.label(RichText::new(message).size(13.0).color(WARN));
    }

    fn draw_windows(ui: &mut egui::Ui, status: &Status) {
        Self::section_title(ui, "Creneaux surveilles");
        ui.horizontal_wrapped(|ui| {
            for window in &status.schedule.windows {
                let current = status.window.as_deref() == Some(window.as_str());
                Self::window_chip(ui, window, current);
            }
        });
    }

    fn section_title(ui: &mut egui::Ui, title: &str) {
        ui.add_space(20.0);
        ui.separator();
        ui.add_space(10.0);
        ui.label(RichText::new(title).size(12.0).color(MUTED));
    }

    fn chip_frame(current: bool) -> egui::Frame {
        egui::Frame::new()
            .fill(if current { RAISED } else { CARD })
            .stroke(Stroke::new(1.0, if current { ACCENT } else { LINE }))
            .corner_radius(8)
            .inner_margin(egui::Margin::symmetric(10, 6))
    }

    fn window_chip(ui: &mut egui::Ui, window: &str, current: bool) {
        Self::chip_frame(current).show(ui, |ui| {
            let color = if current { INK } else { INK_2 };
            ui.label(RichText::new(window).monospace().size(13.0).color(color));
        });
    }

    fn counter_rows(status: &Status) -> [(&'static str, u64); 4] {
        [
            ("Demarrages", status.counters.starts),
            ("Detections", status.counters.detections),
            ("Signatures", status.counters.signed),
            ("Erreurs", status.counters.errors),
        ]
    }

    fn draw_counters(ui: &mut egui::Ui, status: &Status) {
        Self::section_title(ui, "");
        Self::counter_grid(ui, Self::counter_rows(status));
    }

    fn counter_grid(ui: &mut egui::Ui, rows: [(&str, u64); 4]) {
        egui::Grid::new("counters")
            .num_columns(4)
            .spacing([28.0, 8.0])
            .show(ui, |ui| {
                for (label, value) in rows {
                    Self::counter(ui, label, value);
                }
                ui.end_row();
            });
    }

    fn counter(ui: &mut egui::Ui, label: &str, value: u64) {
        ui.vertical(|ui| {
            ui.label(RichText::new(label).size(12.0).color(MUTED));
            let text = RichText::new(value.to_string())
                .monospace()
                .size(24.0)
                .color(INK);
            ui.label(text);
        });
    }

    fn date_rows(status: &Status) -> [(&'static str, &str); 3] {
        [
            ("Demarre le", status.started_at.as_str()),
            (
                "Derniere detection",
                status.last_detection_at.as_deref().unwrap_or(""),
            ),
            (
                "Derniere signature",
                status.last_signed_at.as_deref().unwrap_or(""),
            ),
        ]
    }

    fn draw_dates(ui: &mut egui::Ui, status: &Status) {
        ui.add_space(16.0);
        ui.separator();
        ui.add_space(8.0);
        for (label, value) in Self::date_rows(status) {
            Self::date_row(ui, label, value);
        }
    }

    fn date_row(ui: &mut egui::Ui, label: &str, value: &str) {
        ui.horizontal(|ui| {
            ui.label(RichText::new(label).size(13.0).color(INK_2));
            let right = Layout::right_to_left(Align::Center);
            ui.with_layout(right, |ui| {
                let text = Self::short_date(value);
                let rich = RichText::new(text).monospace().size(13.0).color(INK);
                ui.label(rich);
            });
        });
    }

    fn draw_actions(&mut self, ui: &mut egui::Ui) {
        let busy = self.busy;
        ui.add_space(20.0);
        ui.horizontal_wrapped(|ui| {
            self.draw_action_buttons(ui, busy);
            self.draw_quit(ui, busy);
        });
    }

    fn draw_action_buttons(&mut self, ui: &mut egui::Ui, busy: bool) {
        if Self::action_button(ui, !busy, "Tester la notification", RAISED, None) {
            self.run_action(ui.ctx().clone(), "test-notification");
        }
        if Self::action_button(ui, !busy, "Verifier les mises a jour", CARD, Some(LINE)) {
            self.run_action(ui.ctx().clone(), "check-update");
        }
        if Self::action_button(ui, !busy, "Ouvrir les logs", CARD, Some(LINE)) {
            self.run_action(ui.ctx().clone(), "open-logs");
        }
    }

    fn action_button(
        ui: &mut egui::Ui,
        enabled: bool,
        label: &str,
        fill: Color32,
        stroke: Option<Color32>,
    ) -> bool {
        let mut button = egui::Button::new(RichText::new(label).color(INK)).fill(fill);
        if let Some(color) = stroke {
            button = button.stroke(Stroke::new(1.0, color));
        }
        let size = Vec2::new(0.0, 38.0);
        ui.add_enabled(enabled, button.min_size(size)).clicked()
    }

    fn draw_quit(&mut self, ui: &mut egui::Ui, busy: bool) {
        if self.confirm_quit {
            self.draw_quit_confirmation(ui, busy);
            return;
        }
        if Self::action_button(ui, !busy, "Quitter CheckMate", Color32::TRANSPARENT, None) {
            self.confirm_quit = true;
        }
    }

    fn quit_button() -> egui::Button<'static> {
        let label = RichText::new("Confirmer l'arret").color(Color32::WHITE);
        egui::Button::new(label)
            .fill(ERR)
            .min_size(Vec2::new(0.0, 38.0))
    }

    fn draw_quit_confirmation(&mut self, ui: &mut egui::Ui, busy: bool) {
        if ui.add_enabled(!busy, Self::quit_button()).clicked() {
            self.confirm_quit = false;
            self.run_action(ui.ctx().clone(), "quit");
        }
        if ui.button("Annuler").clicked() {
            self.confirm_quit = false;
        }
    }
    fn draw_offline(&mut self, ui: &mut egui::Ui) {
        let mut start = false;
        Self::card_frame().show(ui, |ui| {
            Self::draw_offline_text(ui, self.error.as_deref());
            start = Self::start_button(ui);
        });
        if start {
            self.start_backend(ui.ctx().clone());
        }
    }

    fn draw_offline_text(ui: &mut egui::Ui, error: Option<&str>) {
        ui.label(RichText::new("●").size(22.0).color(ERR));
        ui.label(RichText::new("Service arrete").size(30.0).color(INK));
        let message = "Le moteur CheckMate ne repond pas. Demarre-le pour afficher l'etat.";
        ui.label(RichText::new(message).size(14.0).color(INK_2));
        Self::draw_offline_error(ui, error);
    }

    fn draw_offline_error(ui: &mut egui::Ui, error: Option<&str>) {
        if let Some(error) = error {
            ui.add_space(8.0);
            ui.label(RichText::new(error).size(12.0).color(MUTED));
        }
    }

    fn start_button(ui: &mut egui::Ui) -> bool {
        ui.add_space(16.0);
        let label = RichText::new("Demarrer le service").color(Color32::WHITE);
        let size = Vec2::new(0.0, 40.0);
        let button = egui::Button::new(label).fill(ACCENT).min_size(size);
        ui.add(button).clicked()
    }
}

impl eframe::App for App {
    fn ui(&mut self, root: &mut egui::Ui, _frame: &mut eframe::Frame) {
        let context = root.ctx().clone();
        self.drain_status();
        self.drain_actions();
        if self.last_refresh.elapsed() > Duration::from_secs(3) && !self.refreshing {
            self.refresh(context.clone());
        }
        self.draw_root(root);
        root.ctx().request_repaint_after(Duration::from_millis(500));
    }
}

impl App {
    fn drain_status(&mut self) {
        while let Ok(event) = self.status_rx.try_recv() {
            self.refreshing = false;
            self.apply_status(event);
        }
    }

    fn apply_status(&mut self, event: Result<Status, String>) {
        match event {
            Ok(status) => self.set_status(status),
            Err(error) => self.set_error(error),
        }
    }

    fn set_status(&mut self, status: Status) {
        self.status = Some(status);
        self.error = None;
    }

    fn set_error(&mut self, error: String) {
        self.status = None;
        self.error = Some(error);
    }

    fn drain_actions(&mut self) {
        while let Ok(event) = self.action_rx.try_recv() {
            self.busy = false;
            self.message = Some(match event {
                Ok(response) => Self::action_message(response),
                Err(error) => error,
            });
        }
    }

    fn action_message(response: ActionResponse) -> String {
        let mut message = response.message.unwrap_or_default();
        if response.available == Some(true)
            && let Some(url) = response.url
        {
            message = format!("{message} {url}");
        }
        message
    }

    fn draw_root(&mut self, root: &mut egui::Ui) {
        egui::Frame::new()
            .fill(PAPER)
            .inner_margin(28)
            .show(root, |ui| {
                self.draw_header(ui);
                self.draw_body(ui);
                Self::draw_footer(ui, self.message.as_deref());
            });
    }

    fn draw_body(&mut self, ui: &mut egui::Ui) {
        if let Some(status) = self.status.clone() {
            self.draw_status(ui, &status);
        } else {
            self.draw_offline(ui);
        }
    }

    fn draw_footer(ui: &mut egui::Ui, message: Option<&str>) {
        if let Some(message) = message {
            ui.add_space(12.0);
            ui.label(RichText::new(message).size(13.0).color(INK_2));
        }
        ui.add_space(12.0);
        let text = "Local uniquement, aucun serveur.";
        ui.label(RichText::new(text).size(12.0).color(MUTED));
    }
}

fn configure_style(context: &egui::Context) {
    apply_visuals(context);
    apply_text_style(context);
}

fn apply_visuals(context: &egui::Context) {
    let mut visuals = base_visuals();
    apply_widget_colors(&mut visuals);
    context.set_visuals(visuals);
}

fn base_visuals() -> egui::Visuals {
    let mut visuals = egui::Visuals::light();
    visuals.panel_fill = PAPER;
    visuals.window_fill = CARD;
    visuals.extreme_bg_color = Color32::WHITE;
    visuals.faint_bg_color = RAISED;
    visuals
}

fn apply_widget_colors(visuals: &mut egui::Visuals) {
    visuals.override_text_color = Some(INK);
    visuals.selection.bg_fill = ACCENT;
    visuals.widgets.inactive.bg_fill = RAISED;
    visuals.widgets.inactive.fg_stroke.color = INK;
    visuals.widgets.hovered.bg_fill = Color32::from_rgb(230, 223, 212);
    visuals.widgets.active.bg_fill = Color32::from_rgb(220, 212, 199);
}

fn apply_text_style(context: &egui::Context) {
    let mut style = (*context.style_of(egui::Theme::Light)).clone();
    style.spacing.item_spacing = egui::vec2(10.0, 8.0);
    let heading = FontId::proportional(28.0);
    style.text_styles.insert(TextStyle::Heading, heading);
    context.set_style_of(egui::Theme::Light, style);
}

fn main() -> eframe::Result<()> {
    let options = native_options();
    eframe::run_native(
        "CheckMate",
        options,
        Box::new(|context| Ok(Box::new(App::new(context)))),
    )
}

fn native_options() -> eframe::NativeOptions {
    eframe::NativeOptions {
        viewport: egui::ViewportBuilder::default()
            .with_inner_size([940.0, 760.0])
            .with_min_inner_size([680.0, 560.0]),
        ..Default::default()
    }
}
