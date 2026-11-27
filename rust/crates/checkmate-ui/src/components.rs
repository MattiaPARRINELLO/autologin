//! Composants partages, tous alimentes par `Theme`.
//!
//! Les composants ne portent pas de logique : ils rendent un style et des
//! libelles. Les gestionnaires d'evenements et la navigation clavier restent
//! dans les vues.

use gpui::prelude::*;
use gpui::{div, px, Div, Pixels, SharedString};

use checkmate_core::status::Tone;

use crate::theme::Theme;

/// Variantes visuelles d'un bouton.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ButtonKind {
    Primary,
    Secondary,
    Danger,
    Ghost,
}

/// Conteneur de page.
pub fn page(theme: &Theme) -> Div {
    div()
        .flex()
        .flex_col()
        .w_full()
        .h_full()
        .bg(theme.background)
        .text_color(theme.text)
        .font_family(theme.font_family.clone())
}

/// Carte de contenu.
pub fn card(theme: &Theme) -> Div {
    div()
        .flex()
        .flex_col()
        .gap(theme.spacing.md)
        .p(theme.spacing.lg)
        .bg(theme.surface)
        .border_1()
        .border_color(theme.border)
        .rounded(theme.radius_md())
}

/// Titre de page.
pub fn title(theme: &Theme, text: impl Into<SharedString>) -> Div {
    div()
        .text_size(px(24.0))
        .font_weight(Theme::weight_bold())
        .text_color(theme.text)
        .child(text.into())
}

/// Titre de section.
pub fn heading(theme: &Theme, text: impl Into<SharedString>) -> Div {
    div()
        .text_size(px(17.0))
        .font_weight(Theme::weight_bold())
        .text_color(theme.text)
        .child(text.into())
}

/// Libelle de section en petites majuscules.
pub fn section_label(theme: &Theme, text: impl Into<SharedString>) -> Div {
    div()
        .text_size(px(11.0))
        .font_weight(Theme::weight_bold())
        .text_color(theme.text_muted)
        .child(text.into())
}

/// Texte courant.
pub fn body(theme: &Theme, text: impl Into<SharedString>) -> Div {
    div()
        .text_size(px(14.0))
        .text_color(theme.text)
        .child(text.into())
}

/// Texte discret.
pub fn muted(theme: &Theme, text: impl Into<SharedString>) -> Div {
    div()
        .text_size(px(13.0))
        .text_color(theme.text_muted)
        .child(text.into())
}

/// Libelle de champ.
pub fn field_label(theme: &Theme, text: impl Into<SharedString>) -> Div {
    div()
        .text_size(px(12.0))
        .font_weight(Theme::weight_medium())
        .text_color(theme.text_muted)
        .child(text.into())
}

/// Bouton pret a recevoir un gestionnaire de clic.
pub fn button(
    theme: &Theme,
    id: impl Into<SharedString>,
    label: impl Into<SharedString>,
    kind: ButtonKind,
    enabled: bool,
) -> gpui::Stateful<Div> {
    let (background, text, border) = button_colors(theme, kind, enabled);
    div()
        .id(id.into())
        .flex()
        .items_center()
        .justify_center()
        .h(px(36.0))
        .px(theme.spacing.md)
        .rounded(theme.radius_sm())
        .bg(background)
        .text_color(text)
        .border_1()
        .border_color(border)
        .text_size(px(13.0))
        .font_weight(Theme::weight_medium())
        .when(enabled, gpui::Styled::cursor_pointer)
        .when(enabled, |button| {
            button.hover(move |style| style.bg(hover_color(theme, kind)))
        })
        .child(label.into())
}

fn button_colors(
    theme: &Theme,
    kind: ButtonKind,
    enabled: bool,
) -> (gpui::Rgba, gpui::Rgba, gpui::Rgba) {
    if !enabled {
        return (theme.surface_raised, theme.text_muted, theme.border);
    }
    match kind {
        ButtonKind::Primary => (theme.accent, theme.on_accent, theme.accent),
        ButtonKind::Secondary => (theme.surface_raised, theme.text, theme.border),
        ButtonKind::Danger => (theme.surface_raised, theme.error, theme.error),
        ButtonKind::Ghost => (theme.surface, theme.accent, theme.surface),
    }
}

fn hover_color(theme: &Theme, kind: ButtonKind) -> gpui::Rgba {
    match kind {
        ButtonKind::Primary => blend(theme.accent, theme.on_accent, 0.12),
        ButtonKind::Secondary | ButtonKind::Ghost => theme.border,
        ButtonKind::Danger => blend(theme.surface_raised, theme.error, 0.12),
    }
}

fn blend(base: gpui::Rgba, overlay: gpui::Rgba, amount: f32) -> gpui::Rgba {
    gpui::Rgba {
        r: base.r + (overlay.r - base.r) * amount,
        g: base.g + (overlay.g - base.g) * amount,
        b: base.b + (overlay.b - base.b) * amount,
        a: base.a,
    }
}

/// Pastille d'etat.
pub fn badge(theme: &Theme, text: impl Into<SharedString>, tone: Tone) -> Div {
    let color = theme.tone_color(tone);
    div()
        .flex()
        .items_center()
        .gap(theme.spacing.xs)
        .px(theme.spacing.sm)
        .py(px(2.0))
        .rounded(px(999.0))
        .bg(blend(theme.surface, color, 0.12))
        .text_color(color)
        .text_size(px(12.0))
        .font_weight(Theme::weight_bold())
        .child(div().size(px(7.0)).rounded(px(999.0)).bg(color))
        .child(text.into())
}

/// Compteur d'une statistique.
pub fn stat(theme: &Theme, label: impl Into<SharedString>, value: impl Into<SharedString>) -> Div {
    div()
        .flex()
        .flex_col()
        .gap(px(2.0))
        .child(section_label(theme, label))
        .child(
            div()
                .text_size(px(22.0))
                .font_weight(Theme::weight_bold())
                .text_color(theme.text)
                .child(value.into()),
        )
}

/// Bandeau d'erreur.
pub fn error_banner(theme: &Theme, message: impl Into<SharedString>) -> Div {
    div()
        .flex()
        .flex_col()
        .gap(px(2.0))
        .p(theme.spacing.md)
        .rounded(theme.radius_sm())
        .border_1()
        .border_color(theme.error)
        .bg(blend(theme.surface, theme.error, 0.08))
        .text_color(theme.error)
        .child(
            div()
                .text_size(px(13.0))
                .font_weight(Theme::weight_bold())
                .child(message.into()),
        )
}

/// Bandeau d'information.
pub fn info_banner(theme: &Theme, message: impl Into<SharedString>) -> Div {
    div()
        .p(theme.spacing.md)
        .rounded(theme.radius_sm())
        .border_1()
        .border_color(theme.warning)
        .bg(blend(theme.surface, theme.warning, 0.08))
        .text_size(px(13.0))
        .text_color(theme.warning)
        .child(message.into())
}

/// Etat vide.
pub fn empty_state(
    theme: &Theme,
    title: impl Into<SharedString>,
    detail: impl Into<SharedString>,
) -> Div {
    div()
        .flex()
        .flex_col()
        .items_center()
        .gap(theme.spacing.sm)
        .p(theme.spacing.xl)
        .child(heading(theme, title))
        .child(muted(theme, detail))
}

/// Puce selectionnable (jour, canal, option).
pub fn chip(theme: &Theme, label: impl Into<SharedString>, selected: bool) -> Div {
    div()
        .flex()
        .items_center()
        .justify_center()
        .min_w(px(44.0))
        .h(px(32.0))
        .px(theme.spacing.sm)
        .rounded(theme.radius_sm())
        .border_1()
        .border_color(if selected { theme.accent } else { theme.border })
        .bg(if selected {
            blend(theme.surface, theme.accent, 0.16)
        } else {
            theme.surface
        })
        .text_color(if selected {
            theme.accent
        } else {
            theme.text_muted
        })
        .text_size(px(13.0))
        .font_weight(Theme::weight_medium())
        .cursor_pointer()
        .child(label.into())
}

/// Barre de progression before/after, sans animation.
pub fn ratio_bar(theme: &Theme, ratio: f32) -> Div {
    let ratio = ratio.clamp(0.0, 1.0);
    div()
        .w_full()
        .h(px(8.0))
        .rounded(px(999.0))
        .bg(theme.surface_raised)
        .child(
            div()
                .h_full()
                .w(gpui::relative(ratio))
                .rounded(px(999.0))
                .bg(theme.accent),
        )
}

/// Separateur.
pub fn divider(theme: &Theme) -> Div {
    div().w_full().h(px(1.0)).bg(theme.border)
}

/// Indication de raccourci clavier.
pub fn hint(theme: &Theme, text: impl Into<SharedString>) -> Div {
    div()
        .text_size(px(11.0))
        .text_color(theme.text_muted)
        .child(text.into())
}

/// Largeur maximale du contenu pour rester lisible.
pub fn content_column(theme: &Theme) -> Div {
    div()
        .flex()
        .flex_col()
        .gap(theme.spacing.md)
        .w_full()
        .max_w(px(860.0))
}

/// Aide-memoire des rayons, pour les tests de style.
pub fn radii(theme: &Theme) -> [Pixels; 3] {
    [theme.radius_sm(), theme.radius_md(), theme.radius_lg()]
}

#[cfg(test)]
mod tests {
    use super::{button_colors, ButtonKind};
    use crate::theme::{Motion, Theme};

    #[test]
    fn un_bouton_desactive_reste_lisible() {
        let theme = Theme::light(Motion::default());
        let (_, text, _) = button_colors(&theme, ButtonKind::Primary, false);
        assert_eq!(text, theme.text_muted);
    }

    #[test]
    fn chaque_variante_a_ses_couleurs() {
        let theme = Theme::dark(Motion::default());
        let primary = button_colors(&theme, ButtonKind::Primary, true);
        let secondary = button_colors(&theme, ButtonKind::Secondary, true);
        assert_ne!(primary.0, secondary.0);
        assert_eq!(primary.0, theme.accent);
        assert_eq!(primary.1, theme.on_accent);
    }
}
