//! Rendu des ecrans : tableau de bord, assistant, fenetres modales.
//!
//! Les vues ne prennent aucune decision : elles lisent `AppState` et
//! delèguent les actions a `CheckmateApp`.

use gpui::prelude::*;
use gpui::{
    App, ClickEvent, Context, Div, MouseDownEvent, MouseMoveEvent, MouseUpEvent, SharedString, div,
    px,
};

use checkmate_core::actions::ActionKind;
use checkmate_core::setup::{DAYS, SetupStep, SignaturePoint};
use checkmate_core::status::StatusSnapshot;
use checkmate_core::timefmt;

use crate::app::CheckmateApp;
use crate::components::{self, ButtonKind};
use crate::signature;
use crate::state::{AppState, Field, FocusId, Loadable, Overlay, Screen};
use crate::theme::Theme;

/// Gestionnaires de la zone de signature, fournis par l'application.
pub struct SignatureHandlers<S, D, U> {
    pub start: S,
    pub draw: D,
    pub end: U,
}

/// En-tete commun.
pub fn header(state: &AppState, theme: &Theme, cx: &mut Context<CheckmateApp>) -> Div {
    let version = state.status.ready().map_or_else(
        || checkmate_core::VERSION.to_owned(),
        |status| status.version.clone(),
    );
    let channel = state
        .status
        .ready()
        .map_or_else(String::new, |status| status.channel.clone());
    div()
        .debug_selector(|| "header".to_owned())
        .flex()
        .items_center()
        .justify_between()
        .w_full()
        .px(theme.spacing.xl)
        .py(theme.spacing.md)
        .border_b_1()
        .border_color(theme.border)
        .bg(theme.surface)
        .child(
            div()
                .flex()
                .items_center()
                .gap(theme.spacing.md)
                .child(
                    div()
                        .text_size(px(18.0))
                        .font_weight(Theme::weight_bold())
                        .child(checkmate_core::NAME),
                )
                .child(components::muted(theme, format!("version {version}")))
                .when(!channel.is_empty(), |header| {
                    header.child(components::badge(
                        theme,
                        format!("canal {channel}"),
                        checkmate_core::status::Tone::Neutral,
                    ))
                })
                .child(components::muted(theme, describe_focus(state))),
        )
        .child(
            components::button(
                theme,
                "header-setup",
                "Assistant",
                ButtonKind::Secondary,
                true,
            )
            .on_click(cx.listener(|this, _: &ClickEvent, window, cx| {
                this.open_onboarding(window, cx);
            })),
        )
}

fn describe_focus(state: &AppState) -> String {
    match &state.focus {
        FocusId::DashboardAction(action) => format!("focus : {}", action.label()),
        FocusId::Retry => "focus : Reessayer".to_owned(),
        FocusId::Channel(channel) => format!("focus : canal {channel}"),
        FocusId::Field(field) => format!("focus : {}", field_label(field)),
        FocusId::Next => "focus : Continuer".to_owned(),
        FocusId::Back => "focus : Retour".to_owned(),
        FocusId::Day(index) => format!(
            "focus : {}",
            DAYS.get(*index).map_or("jour", |(_, label)| *label)
        ),
        FocusId::Autostart => "focus : demarrage automatique".to_owned(),
        FocusId::SignatureClear => "focus : effacer".to_owned(),
        FocusId::SignatureConfirm => "focus : valider".to_owned(),
        FocusId::ImportSignature => "focus : importer".to_owned(),
        FocusId::Window(index) => format!("focus : creneau {}", index + 1),
        FocusId::Step(step) => format!("focus : {}", step.title()),
        FocusId::DialogAccept | FocusId::DialogCancel => "focus : fenetre".to_owned(),
    }
}

fn field_label(field: &Field) -> &'static str {
    match field {
        Field::BaseUrl => "adresse du site",
        Field::Username => "identifiant",
        Field::Password => "mot de passe",
        Field::ImportPath => "chemin de l'image",
    }
}

/// Pied de page.
pub fn footer(state: &AppState, theme: &Theme) -> Div {
    div()
        .flex()
        .flex_col()
        .gap(px(4.0))
        .w_full()
        .px(theme.spacing.xl)
        .py(theme.spacing.sm)
        .border_t_1()
        .border_color(theme.border)
        .bg(theme.surface)
        .child(components::hint(
            theme,
            "Tab et Maj+Tab deplacent le focus, Entree active, Echap ferme.",
        ))
        .when(state.overlay.is_some(), |footer| {
            footer.child(components::hint(
                theme,
                "Fenetre modale : le focus reste a l'interieur.",
            ))
        })
}

/// Tableau de bord.
pub fn dashboard(
    state: &AppState,
    theme: &Theme,
    cx: &mut Context<CheckmateApp>,
) -> gpui::Stateful<Div> {
    div()
        .flex()
        .flex_col()
        .debug_selector(|| "dashboard".to_owned())
        .items_center()
        .w_full()
        .flex_1()
        .id("dashboard-scroll")
        .overflow_y_scroll()
        .child(
            components::content_column(theme)
                .py(theme.spacing.xl)
                .when_some(state.error.clone(), |column, error| {
                    column.child(components::error_banner(theme, error))
                })
                .when_some(state.message.clone(), |column, message| {
                    column.child(info_banner(theme, message))
                })
                .child(match &state.status {
                    Loadable::Loading => components::card(theme)
                        .child(components::empty_state(
                            theme,
                            "Connexion au service...",
                            "Lecture de runtime.json",
                        ))
                        .into_any_element(),
                    Loadable::Failed(_) => error_screen(state, theme, cx).into_any_element(),
                    Loadable::Ready(status) => {
                        dashboard_ready(state, status, theme, cx).into_any_element()
                    }
                }),
        )
}

fn info_banner(theme: &Theme, message: String) -> Div {
    div()
        .p(theme.spacing.md)
        .rounded(theme.radius_sm())
        .border_1()
        .border_color(theme.border)
        .bg(theme.surface_raised)
        .text_size(px(13.0))
        .child(message)
}

fn error_screen(state: &AppState, theme: &Theme, cx: &mut Context<CheckmateApp>) -> Div {
    let (detail, guidance) = state
        .error_explanation()
        .unwrap_or_else(|| ("Erreur inconnue".to_owned(), ""));
    components::card(theme)
        .items_center()
        .child(components::heading(theme, "CheckMate n'est pas joignable"))
        .child(components::body(theme, detail))
        .child(components::muted(theme, guidance))
        .child(
            components::button(theme, "retry", "Reessayer", ButtonKind::Primary, true)
                .when(state.focus == FocusId::Retry, |button| {
                    button.border_2().border_color(theme.focus_ring)
                })
                .on_click(cx.listener(|this, _: &ClickEvent, window, cx| {
                    this.retry(window, cx);
                })),
        )
}

fn dashboard_ready(
    state: &AppState,
    status: &StatusSnapshot,
    theme: &Theme,
    cx: &mut Context<CheckmateApp>,
) -> Div {
    let tone = status.tone();
    let mut column = components::content_column(theme)
        .child(
            components::card(theme)
                .child(
                    div()
                        .flex()
                        .items_center()
                        .justify_between()
                        .child(components::title(theme, status.label.clone()))
                        .child(components::badge(theme, mode_label(&status.mode), tone)),
                )
                .child(components::muted(
                    theme,
                    format!(
                        "Depuis {} ({})",
                        timefmt::date_time(&status.started_at),
                        timefmt::uptime(status.uptime_seconds)
                    ),
                ))
                .child(components::divider(theme))
                .child(
                    div()
                        .flex()
                        .gap(theme.spacing.xl)
                        .child(detail(
                            theme,
                            "Creneau en cours",
                            status.window.clone().unwrap_or_else(|| "aucun".to_owned()),
                        ))
                        .child(detail(
                            theme,
                            "Prochaine ouverture",
                            status
                                .next_window
                                .as_deref()
                                .map_or_else(|| "aucune".to_owned(), timefmt::date_time),
                        )),
                ),
        )
        .when(status.restart_required, |column| {
            column.child(components::info_banner(
                theme,
                "Configuration modifiee. Relance CheckMate pour appliquer les changements.",
            ))
        })
        .when_some(status.blocked.clone(), |column, blocked| {
            column.child(components::info_banner(
                theme,
                format!(
                    "Mise a jour obligatoire : {}. {}",
                    blocked.tag,
                    blocked.reason.unwrap_or_default()
                ),
            ))
        });

    column = column
        .child(schedule_card(status, theme))
        .child(counters_card(status, theme))
        .child(events_card(status, theme))
        .child(actions_row(state, theme, cx))
        .child(channel_card(state, status, theme, cx));
    column
}

fn detail(theme: &Theme, label: &str, value: String) -> Div {
    div()
        .flex()
        .flex_col()
        .gap(px(2.0))
        .child(components::section_label(theme, label.to_owned()))
        .child(
            div()
                .text_size(px(15.0))
                .font_weight(Theme::weight_medium())
                .child(value),
        )
}

fn mode_label(mode: &str) -> String {
    match mode {
        "active" | "disabled" => "Surveillance active",
        "outside" => "Hors creneau",
        "signed" => "Creneau signe",
        "absent" => "Creneau absent",
        "error" => "Erreur recente",
        "blocked" => "Mise a jour obligatoire",
        other => other,
    }
    .to_owned()
}

fn schedule_card(status: &StatusSnapshot, theme: &Theme) -> Div {
    components::card(theme)
        .child(components::section_label(theme, "Creneaux surveilles"))
        .child(div().flex().flex_wrap().gap(theme.spacing.xs).children(
            status.schedule.days.iter().map(|day| {
                components::chip(theme, format!("schedule-day-{day}"), day_label(day), true)
            }),
        ))
        .child(components::muted(
            theme,
            status.schedule.windows.join("   "),
        ))
}

fn day_label(day: &str) -> String {
    DAYS.iter()
        .find(|(name, _)| *name == day)
        .map_or_else(|| day.to_owned(), |(_, label)| (*label).to_owned())
}

fn counters_card(status: &StatusSnapshot, theme: &Theme) -> Div {
    components::card(theme)
        .child(components::section_label(theme, "Compteurs"))
        .child(
            div()
                .flex()
                .justify_between()
                .gap(theme.spacing.md)
                .children(
                    status
                        .counters
                        .series()
                        .into_iter()
                        .map(|(label, value)| components::stat(theme, label, value.to_string())),
                ),
        )
}

fn events_card(status: &StatusSnapshot, theme: &Theme) -> Div {
    let error = status
        .last_error_message
        .clone()
        .filter(|message| !message.is_empty());
    components::card(theme)
        .child(components::section_label(theme, "Derniers evenements"))
        .child(event_row(
            theme,
            "Demarre le",
            timefmt::date_time(&status.started_at),
        ))
        .child(event_row(
            theme,
            "Derniere signature",
            status
                .last_signed_at
                .as_deref()
                .map_or_else(|| "aucune".to_owned(), timefmt::date_time),
        ))
        .child(event_row(
            theme,
            "Derniere detection",
            status
                .last_detection_at
                .as_deref()
                .map_or_else(|| "aucune".to_owned(), timefmt::date_time),
        ))
        .when_some(error, |card, message| {
            card.child(components::error_banner(theme, message))
        })
}

fn event_row(theme: &Theme, label: &str, value: String) -> Div {
    div()
        .flex()
        .justify_between()
        .child(components::muted(theme, label.to_owned()))
        .child(components::body(theme, value))
}

fn actions_row(state: &AppState, theme: &Theme, cx: &mut Context<CheckmateApp>) -> Div {
    div().flex().flex_wrap().gap(theme.spacing.sm).children(
        ActionKind::dashboard_actions().iter().map(|action| {
            let kind = *action;
            let focused = state.focus == FocusId::DashboardAction(kind);
            let busy = state.busy == Some(kind);
            let style = if kind == ActionKind::Quit {
                ButtonKind::Danger
            } else if kind == ActionKind::TestNotification {
                ButtonKind::Primary
            } else {
                ButtonKind::Secondary
            };
            let label = if busy { "En cours..." } else { kind.label() };
            components::button(
                theme,
                format!("action-{}", kind.name()),
                label,
                style,
                !busy,
            )
            .debug_selector(move || format!("action-{}", kind.name()))
            .when(focused, |button| {
                button.border_2().border_color(theme.focus_ring)
            })
            .on_click(cx.listener(move |this, _: &ClickEvent, window, cx| {
                this.activate_dashboard(kind, window, cx);
            }))
        }),
    )
}

fn channel_card(
    state: &AppState,
    status: &StatusSnapshot,
    theme: &Theme,
    cx: &mut Context<CheckmateApp>,
) -> Div {
    let current = state
        .channel_saved
        .clone()
        .unwrap_or_else(|| status.channel.clone());
    components::card(theme)
        .child(components::section_label(theme, "Canal de mise a jour"))
        .child(
            div()
                .flex()
                .gap(theme.spacing.xs)
                .children(["stable", "beta"].into_iter().map(|channel| {
                    let focused = state.focus == FocusId::Channel(channel.to_owned());
                    let selected = current == channel;
                    components::chip(
                        theme,
                        format!("channel-{channel}"),
                        channel.to_owned(),
                        selected,
                    )
                    .when(focused, |chip| {
                        chip.border_2().border_color(theme.focus_ring)
                    })
                    .on_click(cx.listener(
                        move |this, _: &ClickEvent, _, cx| {
                            this.set_channel(channel.to_owned(), cx);
                        },
                    ))
                })),
        )
}

/// Assistant en cinq etapes.
pub fn onboarding<S, D, U>(
    state: &AppState,
    theme: &Theme,
    cx: &mut Context<CheckmateApp>,
    handlers: SignatureHandlers<S, D, U>,
) -> Div
where
    S: Fn(&MouseDownEvent, &mut gpui::Window, &mut App) + 'static,
    D: Fn(&MouseMoveEvent, &mut gpui::Window, &mut App) + 'static,
    U: Fn(&MouseUpEvent, &mut gpui::Window, &mut App) + 'static,
{
    let mut column = components::content_column(theme)
        .debug_selector(move || format!("step-{}", state.step.index()))
        .py(theme.spacing.xl)
        .child(stepper(state, theme))
        .when_some(state.error.clone(), |column, error| {
            column.child(components::error_banner(theme, error))
        })
        .when_some(state.message.clone(), |column, message| {
            column.child(info_banner(theme, message))
        });

    column = match state.step {
        SetupStep::Presentation => column.child(presentation(state, theme)),
        SetupStep::Credentials => column.child(credentials(state, theme, cx)),
        SetupStep::Signature => column.child(signature_step(state, theme, cx, handlers)),
        SetupStep::Schedule => column.child(schedule_step(state, theme, cx)),
        SetupStep::Finish => column.child(finish_step(state, theme)),
    };
    column.child(navigation(state, theme, cx))
}

fn stepper(state: &AppState, theme: &Theme) -> Div {
    div()
        .flex()
        .items_center()
        .gap(theme.spacing.md)
        .children(SetupStep::ALL.into_iter().map(|step| {
            let active = step == state.step;
            let done = step.index() < state.step.index();
            let color = if active || done {
                theme.accent
            } else {
                theme.text_muted
            };
            div()
                .flex()
                .items_center()
                .gap(px(6.0))
                .text_size(px(12.0))
                .text_color(color)
                .when(active, |item| item.font_weight(Theme::weight_bold()))
                .child(
                    div()
                        .flex()
                        .items_center()
                        .justify_center()
                        .size(px(22.0))
                        .rounded(px(999.0))
                        .border_1()
                        .border_color(color)
                        .child(if done {
                            "ok".to_owned()
                        } else {
                            (step.index() + 1).to_string()
                        }),
                )
                .child(step.title())
        }))
}

fn presentation(state: &AppState, theme: &Theme) -> Div {
    let _ = state;
    components::card(theme)
        .child(components::title(theme, "Bienvenue dans CheckMate"))
        .child(components::body(
            theme,
            "CheckMate surveille tes creneaux CESAR et signe ta presence a ta place.",
        ))
        .child(components::muted(
            theme,
            "Cet assistant configure le compte, la signature et le planning. Rien n'est envoye avant la fin.",
        ))
        .child(components::muted(
            theme,
            "Deux minutes suffisent. Tab et Maj+Tab naviguent, Entree valide.",
        ))
}

fn credentials(state: &AppState, theme: &Theme, cx: &mut Context<CheckmateApp>) -> Div {
    components::card(theme)
        .child(components::heading(theme, "Identifiants CESAR"))
        .child(text_field(
            state,
            theme,
            cx,
            Field::BaseUrl,
            "Adresse du site",
            &state.form.base_url,
            false,
        ))
        .child(text_field(
            state,
            theme,
            cx,
            Field::Username,
            "Identifiant",
            &state.form.username,
            false,
        ))
        .child(text_field(
            state,
            theme,
            cx,
            Field::Password,
            "Mot de passe",
            &state.form.password,
            true,
        ))
        .child(components::muted(
            theme,
            "Le mot de passe part directement au service local Python. Il n'est jamais ecrit par cette interface.",
        ))
        .child(
            div()
                .flex()
                .gap(theme.spacing.sm)
                .child(
                    components::button(
                        theme,
                        "test-login",
                        "Tester la connexion",
                        ButtonKind::Secondary,
                        true,
                    )
                    .on_click(cx.listener(|this, _: &ClickEvent, window, cx| {
                        this.test_login_action(window, cx);
                    })),
                )
                .child(
                    components::button(
                        theme,
                        "save-credentials",
                        "Enregistrer",
                        ButtonKind::Primary,
                        true,
                    )
                    .on_click(cx.listener(|this, _: &ClickEvent, window, cx| {
                        this.save_credentials_action(window, cx);
                    })),
                ),
        )
}

fn text_field(
    state: &AppState,
    theme: &Theme,
    cx: &mut Context<CheckmateApp>,
    field: Field,
    label: &str,
    value: &str,
    masked: bool,
) -> Div {
    let focused = state.focus == FocusId::Field(field.clone());
    let display = if masked {
        "*".repeat(value.chars().count())
    } else {
        value.to_owned()
    };
    let display = if focused {
        format!("{display}|")
    } else if display.is_empty() {
        field_label(&field).to_owned()
    } else {
        display
    };
    let dim = value.is_empty() && !focused;
    let id = format!("field-{}", field_label(&field).replace(' ', "-"));
    div()
        .flex()
        .flex_col()
        .gap(px(4.0))
        .child(components::field_label(theme, label.to_owned()))
        .child(
            div()
                .id(SharedString::from(id))
                .h(px(36.0))
                .px(theme.spacing.md)
                .flex()
                .items_center()
                .rounded(theme.radius_sm())
                .border_1()
                .border_color(if focused {
                    theme.focus_ring
                } else {
                    theme.border
                })
                .bg(theme.surface_raised)
                .text_size(px(14.0))
                .when(dim, |input| input.text_color(theme.text_muted))
                .cursor_text()
                .on_click(cx.listener(move |this, _: &ClickEvent, window, cx| {
                    this.set_focus(FocusId::Field(field.clone()), window, cx);
                }))
                .child(display),
        )
}

fn signature_step<S, D, U>(
    state: &AppState,
    theme: &Theme,
    cx: &mut Context<CheckmateApp>,
    handlers: SignatureHandlers<S, D, U>,
) -> Div
where
    S: Fn(&MouseDownEvent, &mut gpui::Window, &mut App) + 'static,
    D: Fn(&MouseMoveEvent, &mut gpui::Window, &mut App) + 'static,
    U: Fn(&MouseUpEvent, &mut gpui::Window, &mut App) + 'static,
{
    components::card(theme)
        .child(components::heading(theme, "Signature"))
        .child(components::muted(
            theme,
            "Dessine ta signature au doigt ou a la souris, ou importe une image PNG ou JPG.",
        ))
        .child(signature_pad(state, theme, cx, handlers))
        .child(signature_preview(state, theme))
        .child(signature_tools(state, theme, cx))
        .child(signature_buttons(state, theme, cx))
}

fn signature_pad<S, D, U>(
    state: &AppState,
    theme: &Theme,
    cx: &mut Context<CheckmateApp>,
    handlers: SignatureHandlers<S, D, U>,
) -> gpui::Stateful<Div>
where
    S: Fn(&MouseDownEvent, &mut gpui::Window, &mut App) + 'static,
    D: Fn(&MouseMoveEvent, &mut gpui::Window, &mut App) + 'static,
    U: Fn(&MouseUpEvent, &mut gpui::Window, &mut App) + 'static,
{
    let pad_focused = state.focus == FocusId::SignatureConfirm;
    div()
        .id("signature-pad")
        .debug_selector(|| "signature-pad".to_owned())
        .flex()
        .items_center()
        .justify_center()
        .h(px(140.0))
        .w_full()
        .rounded(theme.radius_md())
        .border_1()
        .border_color(if pad_focused {
            theme.focus_ring
        } else {
            theme.border
        })
        .bg(theme.surface_raised)
        .text_color(theme.text_muted)
        .text_size(px(13.0))
        .when(state.form.signature.is_empty(), |pad| {
            pad.child("Dessine ici")
        })
        .on_mouse_down(gpui::MouseButton::Left, handlers.start)
        .on_mouse_move(handlers.draw)
        .on_mouse_up(gpui::MouseButton::Left, handlers.end)
        .on_click(cx.listener(|this, _: &ClickEvent, window, cx| {
            this.set_focus(FocusId::SignatureConfirm, window, cx);
        }))
}

fn signature_tools(state: &AppState, theme: &Theme, cx: &mut Context<CheckmateApp>) -> Div {
    div()
        .flex()
        .items_end()
        .gap(theme.spacing.sm)
        .child(
            div()
                .flex()
                .flex_col()
                .gap(px(4.0))
                .flex_1()
                .child(text_field(
                    state,
                    theme,
                    cx,
                    Field::ImportPath,
                    "Importer une image",
                    &state.form.import_path,
                    false,
                )),
        )
        .child(
            components::button(
                theme,
                "signature-import",
                "Importer",
                ButtonKind::Secondary,
                true,
            )
            .when(state.focus == FocusId::ImportSignature, |button| {
                button.border_2().border_color(theme.focus_ring)
            })
            .on_click(cx.listener(|this, _: &ClickEvent, window, cx| {
                this.import_signature_action(window, cx);
            })),
        )
}

fn signature_buttons(state: &AppState, theme: &Theme, cx: &mut Context<CheckmateApp>) -> Div {
    div()
        .flex()
        .gap(theme.spacing.sm)
        .child(
            components::button(theme, "signature-clear", "Effacer", ButtonKind::Ghost, true)
                .when(state.focus == FocusId::SignatureClear, |button| {
                    button.border_2().border_color(theme.focus_ring)
                })
                .on_click(cx.listener(|this, _: &ClickEvent, window, cx| {
                    this.clear_signature(window, cx);
                })),
        )
        .child(
            components::button(
                theme,
                "signature-confirm",
                "Valider la signature",
                ButtonKind::Primary,
                signature::is_usable(&state.form.signature),
            )
            .when(state.focus == FocusId::SignatureConfirm, |button| {
                button.border_2().border_color(theme.focus_ring)
            })
            .on_click(cx.listener(|this, _: &ClickEvent, window, cx| {
                this.confirm_signature(window, cx);
            })),
        )
}

fn signature_preview(state: &AppState, theme: &Theme) -> Div {
    let points = signature::fit_points(
        &state.form.signature,
        signature::PREVIEW_WIDTH,
        signature::PREVIEW_HEIGHT,
    );
    div()
        .relative()
        .w_full()
        .h(px(signature::PREVIEW_HEIGHT))
        .rounded(theme.radius_sm())
        .bg(theme.surface_raised)
        .when(points.is_empty(), |preview| {
            preview
                .flex()
                .items_center()
                .justify_center()
                .child(components::muted(theme, "Apercu de la signature"))
        })
        .children(points.into_iter().map(|(x, y)| {
            div()
                .absolute()
                .left(px(x))
                .top(px(y))
                .size(px(2.5))
                .rounded(px(999.0))
                .bg(theme.accent)
        }))
}

fn schedule_step(state: &AppState, theme: &Theme, cx: &mut Context<CheckmateApp>) -> Div {
    components::card(theme)
        .child(components::heading(theme, "Planning"))
        .child(components::section_label(theme, "Jours surveilles"))
        .child(div().flex().flex_wrap().gap(theme.spacing.xs).children(
            DAYS.iter().enumerate().map(|(index, (name, label))| {
                let focused = state.focus == FocusId::Day(index);
                let selected = state.form.days.iter().any(|day| day == name);
                components::chip(
                    theme,
                    format!("toggle-{name}"),
                    (*label).to_owned(),
                    selected,
                )
                .when(focused, |chip| {
                    chip.border_2().border_color(theme.focus_ring)
                })
                .on_click(cx.listener(move |this, _: &ClickEvent, window, cx| {
                    this.toggle_day(index, window, cx);
                }))
            }),
        ))
        .child(components::section_label(theme, "Creneaux"))
        .child(div().flex().flex_col().gap(theme.spacing.sm).children(
            (0..state.form.windows.len().max(2)).map(|index| {
                let value = state.form.windows.get(index).cloned().unwrap_or_default();
                window_field(state, theme, cx, index, &value)
            }),
        ))
        .child(components::muted(
            theme,
            "Format attendu : 08:00-12:30, plusieurs creneaux separes par une virgule.",
        ))
        .child(
            div()
                .flex()
                .items_center()
                .gap(theme.spacing.sm)
                .child(components::body(theme, "Demarrer avec la session"))
                .child(toggle(
                    state,
                    theme,
                    &FocusId::Autostart,
                    state.form.autostart,
                ))
                .child(
                    components::button(
                        theme,
                        "test-notification",
                        "Tester la notification",
                        ButtonKind::Secondary,
                        true,
                    )
                    .on_click(cx.listener(
                        |this, _: &ClickEvent, window, cx| {
                            this.test_notification_action(window, cx);
                        },
                    )),
                ),
        )
}

fn window_field(
    state: &AppState,
    theme: &Theme,
    cx: &mut Context<CheckmateApp>,
    index: usize,
    value: &str,
) -> Div {
    let focused = state.focus == FocusId::Window(index);
    let display = if focused {
        format!("{value}|")
    } else {
        value.to_owned()
    };
    div()
        .flex()
        .flex_col()
        .gap(px(4.0))
        .child(components::field_label(
            theme,
            format!("Creneau {}", index + 1),
        ))
        .child(
            div()
                .id(SharedString::from(format!("window-{index}")))
                .h(px(34.0))
                .px(theme.spacing.md)
                .flex()
                .items_center()
                .rounded(theme.radius_sm())
                .border_1()
                .border_color(if focused {
                    theme.focus_ring
                } else {
                    theme.border
                })
                .bg(theme.surface_raised)
                .text_size(px(14.0))
                .cursor_text()
                .on_click(cx.listener(move |this, _: &ClickEvent, window, cx| {
                    this.set_focus(FocusId::Window(index), window, cx);
                }))
                .child(display),
        )
}

fn toggle(state: &AppState, theme: &Theme, id: &FocusId, value: bool) -> gpui::Stateful<Div> {
    let focused = state.focus == *id;
    div()
        .id("autostart-toggle")
        .flex()
        .items_center()
        .justify_center()
        .w(px(44.0))
        .h(px(24.0))
        .rounded(px(999.0))
        .border_1()
        .border_color(if value { theme.accent } else { theme.border })
        .bg(if value {
            theme.accent
        } else {
            theme.surface_raised
        })
        .when(focused, |element| {
            element.border_2().border_color(theme.focus_ring)
        })
        .child(div().size(px(16.0)).rounded(px(999.0)).bg(if value {
            theme.on_accent
        } else {
            theme.text_muted
        }))
}

fn finish_step(state: &AppState, theme: &Theme) -> Div {
    components::card(theme)
        .child(components::heading(theme, "Tout est pret"))
        .child(components::body(
            theme,
            format!(
                "Compte {} : {} creneaux sur {} jours.",
                state.form.username,
                state.form.windows.len(),
                state.form.days.len()
            ),
        ))
        .child(
            div()
                .flex()
                .items_center()
                .gap(theme.spacing.sm)
                .child(components::body(
                    theme,
                    "Ouvrir CheckMate a l'ouverture de session",
                ))
                .child(toggle(
                    state,
                    theme,
                    &FocusId::Autostart,
                    state.form.autostart,
                )),
        )
        .child(components::muted(
            theme,
            "Le demarrage automatique est propose et son resultat est affiche apres validation.",
        ))
}

fn navigation(state: &AppState, theme: &Theme, cx: &mut Context<CheckmateApp>) -> Div {
    let next_label = match state.step {
        SetupStep::Presentation => "Commencer",
        SetupStep::Credentials => "Tester et continuer",
        SetupStep::Signature => "Valider",
        SetupStep::Schedule => "Enregistrer le planning",
        SetupStep::Finish => "Terminer",
    };
    div()
        .flex()
        .justify_between()
        .child(
            components::button(theme, "step-back", "Retour", ButtonKind::Ghost, true)
                .when(state.step.previous().is_none(), |button| {
                    button.opacity(0.4)
                })
                .when(state.focus == FocusId::Back, |button| {
                    button.border_2().border_color(theme.focus_ring)
                })
                .on_click(cx.listener(|this, _: &ClickEvent, window, cx| {
                    this.previous_step(window, cx);
                })),
        )
        .child(
            components::button(theme, "step-next", next_label, ButtonKind::Primary, true)
                .when(state.focus == FocusId::Next, |button| {
                    button.border_2().border_color(theme.focus_ring)
                })
                .on_click(cx.listener(|this, _: &ClickEvent, window, cx| {
                    this.next_step(window, cx);
                })),
        )
}

/// Fenetre modale, seule zone interactive tant qu'elle est ouverte.
pub fn modal(
    state: &AppState,
    theme: &Theme,
    overlay: &Overlay,
    cx: &mut Context<CheckmateApp>,
) -> Div {
    let content = match overlay {
        Overlay::ReleaseNotes(note) => release_card(state, theme, note, cx),
        Overlay::SignatureConfirmation => signature_confirmation(state, theme, cx),
        Overlay::ConfirmAction {
            action,
            title,
            body,
        } => confirm_card(state, theme, *action, title.clone(), body.clone(), cx),
    };
    div()
        .debug_selector(|| "modal".to_owned())
        .absolute()
        .top_0()
        .left_0()
        .size_full()
        .flex()
        .items_center()
        .justify_center()
        .bg(gpui::rgba(0x0000_00AA))
        .child(content)
}

fn modal_card(theme: &Theme) -> gpui::Stateful<Div> {
    components::card(theme)
        .w(px(560.0))
        .max_h(px(600.0))
        .id("modal-card")
        .overflow_y_scroll()
        .debug_selector(|| "modal-card".to_owned())
}

fn release_card(
    state: &AppState,
    theme: &Theme,
    note: &checkmate_core::status::ReleaseNote,
    cx: &mut Context<CheckmateApp>,
) -> gpui::Stateful<Div> {
    let focused = state.focus == FocusId::DialogCancel;
    let mut card = modal_card(theme)
        .child(components::section_label(
            theme,
            format!("Nouveautes {}", note.version),
        ))
        .child(components::title(
            theme,
            note.title
                .clone()
                .unwrap_or_else(|| "Mise a jour terminee.".to_owned()),
        ))
        .when_some(note.summary.clone(), |card, summary| {
            card.child(components::body(theme, summary))
        })
        .when_some(note.teaser.clone(), |card, teaser| {
            card.child(components::muted(theme, teaser))
        });
    if !note.metrics.is_empty() {
        card = card.child(
            div()
                .flex()
                .gap(theme.spacing.md)
                .children(note.metrics.iter().map(|metric| {
                    components::stat(
                        theme,
                        metric.label.clone(),
                        format!(
                            "{} {}",
                            metric.value,
                            metric.detail.clone().unwrap_or_default()
                        ),
                    )
                })),
        );
    }
    for feature in &note.features {
        card = card.child(
            div()
                .flex()
                .flex_col()
                .gap(px(2.0))
                .child(components::body(theme, feature.title.clone()))
                .child(components::muted(theme, feature.description.clone())),
        );
    }
    card.child(
        components::button(
            theme,
            "release-close",
            "Fermer les nouveautes",
            ButtonKind::Primary,
            true,
        )
        .when(focused, |button| {
            button.border_2().border_color(theme.focus_ring)
        })
        .on_click(cx.listener(|this, _: &ClickEvent, window, cx| {
            this.dismiss_release(window, cx);
        })),
    )
}

fn signature_confirmation(
    state: &AppState,
    theme: &Theme,
    cx: &mut Context<CheckmateApp>,
) -> gpui::Stateful<Div> {
    new_modal(theme)
        .child(components::heading(theme, "Signature prete"))
        .child(components::body(
            theme,
            format!(
                "{} points dessines. Utiliser cette signature pour les prochains emargements ?",
                state.form.signature.len()
            ),
        ))
        .child(modal_buttons(
            state,
            theme,
            cx,
            "Utiliser cette signature".to_owned(),
            "Recommencer".to_owned(),
        ))
}

fn confirm_card(
    state: &AppState,
    theme: &Theme,
    action: ActionKind,
    title: String,
    body: String,
    cx: &mut Context<CheckmateApp>,
) -> gpui::Stateful<Div> {
    let accept = match action {
        ActionKind::Quit => "Quitter".to_owned(),
        ActionKind::InstallUpdate => "Installer".to_owned(),
        _ => "Confirmer".to_owned(),
    };
    new_modal(theme)
        .child(components::heading(theme, title))
        .child(components::body(theme, body))
        .child(modal_buttons(
            state,
            theme,
            cx,
            accept,
            "Annuler".to_owned(),
        ))
}

fn new_modal(theme: &Theme) -> gpui::Stateful<Div> {
    modal_card(theme)
}

fn modal_buttons(
    state: &AppState,
    theme: &Theme,
    cx: &mut Context<CheckmateApp>,
    accept_label: String,
    cancel_label: String,
) -> Div {
    div()
        .flex()
        .justify_end()
        .gap(theme.spacing.sm)
        .child(
            components::button(theme, "modal-cancel", cancel_label, ButtonKind::Ghost, true)
                .when(state.focus == FocusId::DialogCancel, |button| {
                    button.border_2().border_color(theme.focus_ring)
                })
                .on_click(cx.listener(|this, _: &ClickEvent, window, cx| {
                    this.cancel_modal(window, cx);
                })),
        )
        .child(
            components::button(
                theme,
                "modal-accept",
                accept_label,
                ButtonKind::Primary,
                true,
            )
            .when(state.focus == FocusId::DialogAccept, |button| {
                button.border_2().border_color(theme.focus_ring)
            })
            .on_click(cx.listener(|this, _: &ClickEvent, window, cx| {
                this.accept_modal(window, cx);
            })),
        )
}

/// Lignes de reference deterministes, utilisees par les tests de rendu.
pub fn reference_lines(state: &AppState) -> Vec<String> {
    let mut lines = vec![format!("ecran: {}", screen_name(state))];
    lines.push(format!("focus: {}", describe_focus(state)));
    if let Some(status) = state.status.ready() {
        lines.push(format!("titre: {}", status.label));
        lines.push(format!("version: {} ({})", status.version, status.channel));
        lines.push(format!("creneaux: {}", status.schedule.windows.join(", ")));
        lines.push(format!("jours: {}", status.schedule.days.join(",")));
        lines.push(format!("compteurs: {}", counters_line(status)));
    }
    if matches!(state.status, Loadable::Failed(_)) {
        lines.push("erreur: service injoignable".to_owned());
    }
    if state.screen == Screen::Onboarding {
        lines.push(format!(
            "etape: {} ({})",
            state.step.title(),
            state.step.index() + 1
        ));
        lines.push(format!("compte: {}", state.form.username));
        lines.push(format!("signature: {} points", state.form.signature.len()));
    }
    lines
}

/// Nom court de l'ecran.
pub fn screen_name(state: &AppState) -> String {
    if let Some(overlay) = &state.overlay {
        return match overlay {
            Overlay::ReleaseNotes(_) => "nouveautes".to_owned(),
            Overlay::SignatureConfirmation => "confirmation-signature".to_owned(),
            Overlay::ConfirmAction { .. } => "confirmation".to_owned(),
        };
    }
    match state.screen {
        Screen::Dashboard => "tableau-de-bord".to_owned(),
        Screen::Onboarding => "assistant".to_owned(),
    }
}

fn counters_line(status: &StatusSnapshot) -> String {
    status
        .counters
        .series()
        .into_iter()
        .map(|(label, value)| format!("{label}={value}"))
        .collect::<Vec<_>>()
        .join(" ")
}

/// Points utilises par les tests d'apercu.
pub fn preview_points(points: &[SignaturePoint]) -> Vec<(f32, f32)> {
    signature::fit_points(points, signature::PREVIEW_WIDTH, signature::PREVIEW_HEIGHT)
}
