//! Theme clair et sombre, espacements, typographie et mouvement.
//!
//! Aucune vue ne code une couleur en dur : tout passe par `Theme`. Les
//! contrastes texte/fond visent au moins le niveau AA (4,5:1).

use std::time::Duration;

use gpui::SharedString;
use gpui::{px, rgb, FontWeight, Pixels, Rgba, WindowAppearance};

/// Palette complete d'une apparence.
#[derive(Debug, Clone, PartialEq)]
pub struct Theme {
    pub dark: bool,
    pub background: Rgba,
    pub surface: Rgba,
    pub surface_raised: Rgba,
    pub border: Rgba,
    pub text: Rgba,
    pub text_muted: Rgba,
    pub accent: Rgba,
    pub on_accent: Rgba,
    pub focus_ring: Rgba,
    pub active: Rgba,
    pub idle: Rgba,
    pub warning: Rgba,
    pub error: Rgba,
    pub font_family: SharedString,
    pub mono_family: SharedString,
    pub motion: Motion,
    pub spacing: Spacing,
}

/// Echelle d'espacement, en pixels logiques.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct Spacing {
    pub xs: Pixels,
    pub sm: Pixels,
    pub md: Pixels,
    pub lg: Pixels,
    pub xl: Pixels,
}

impl Default for Spacing {
    fn default() -> Self {
        Self {
            xs: px(4.0),
            sm: px(8.0),
            md: px(12.0),
            lg: px(20.0),
            xl: px(32.0),
        }
    }
}

/// Reglages de mouvement. Le mode reduit supprime transitions et animations.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct Motion {
    pub reduced: bool,
    pub fast: Duration,
    pub normal: Duration,
}

impl Motion {
    /// Lit `CHECKMATE_REDUCED_MOTION=1`.
    pub fn from_environment() -> Self {
        let reduced = std::env::var("CHECKMATE_REDUCED_MOTION").is_ok_and(|value| value == "1");
        Self::new(reduced)
    }

    pub fn new(reduced: bool) -> Self {
        if reduced {
            Self {
                reduced,
                fast: Duration::ZERO,
                normal: Duration::ZERO,
            }
        } else {
            Self {
                reduced,
                fast: Duration::from_millis(120),
                normal: Duration::from_millis(220),
            }
        }
    }

    /// Duree a appliquer, nulle en mouvement reduit.
    pub fn duration(&self, normal: Duration) -> Duration {
        if self.reduced {
            Duration::ZERO
        } else {
            normal
        }
    }
}

impl Default for Motion {
    fn default() -> Self {
        Self::new(false)
    }
}

impl Theme {
    /// Theme par defaut selon l'apparence de la fenetre.
    pub fn for_appearance(appearance: WindowAppearance, motion: Motion) -> Self {
        match appearance {
            WindowAppearance::Dark | WindowAppearance::VibrantDark => Self::dark(motion),
            WindowAppearance::Light | WindowAppearance::VibrantLight => Self::light(motion),
        }
    }

    /// Theme clair.
    pub fn light(motion: Motion) -> Self {
        Self {
            dark: false,
            background: rgb(0x00F4_F4F1),
            surface: rgb(0x00FF_FFFE),
            surface_raised: rgb(0x00FF_FFFF),
            border: rgb(0x00D8_D8D2),
            text: rgb(0x001A_1A18),
            text_muted: rgb(0x0055_554F),
            accent: rgb(0x001B_6B54),
            on_accent: rgb(0x00FF_FFFF),
            focus_ring: rgb(0x001B_6B54),
            active: rgb(0x001B_6B54),
            idle: rgb(0x006B_6B63),
            warning: rgb(0x008A_5200),
            error: rgb(0x00A3_231B),
            font_family: font_family(),
            mono_family: mono_family(),
            motion,
            spacing: Spacing::default(),
        }
    }

    /// Theme sombre.
    pub fn dark(motion: Motion) -> Self {
        Self {
            dark: true,
            background: rgb(0x0012_120F),
            surface: rgb(0x001D_1D19),
            surface_raised: rgb(0x0026_2621),
            border: rgb(0x003A_3A33),
            text: rgb(0x00F1_F1EC),
            text_muted: rgb(0x00AD_ADA2),
            accent: rgb(0x0059_C7A4),
            on_accent: rgb(0x0006_231B),
            focus_ring: rgb(0x008C_E3C6),
            active: rgb(0x0059_C7A4),
            idle: rgb(0x009C_9C92),
            warning: rgb(0x00F0_B44C),
            error: rgb(0x00FF_8A80),
            font_family: font_family(),
            mono_family: mono_family(),
            motion,
            spacing: Spacing::default(),
        }
    }

    /// Couleur d'un ton d'etat.
    pub fn tone_color(&self, tone: checkmate_core::status::Tone) -> Rgba {
        use checkmate_core::status::Tone;
        match tone {
            Tone::Active => self.active,
            Tone::Idle => self.idle,
            Tone::Warning => self.warning,
            Tone::Error => self.error,
            Tone::Neutral => self.text_muted,
        }
    }

    pub fn radius_sm(&self) -> Pixels {
        px(6.0)
    }

    pub fn radius_md(&self) -> Pixels {
        px(10.0)
    }

    pub fn radius_lg(&self) -> Pixels {
        px(16.0)
    }

    pub fn weight_regular() -> FontWeight {
        FontWeight::NORMAL
    }

    pub fn weight_medium() -> FontWeight {
        FontWeight::MEDIUM
    }

    pub fn weight_bold() -> FontWeight {
        FontWeight::SEMIBOLD
    }
}

#[cfg(target_os = "windows")]
fn font_family() -> SharedString {
    "Segoe UI".into()
}

#[cfg(target_os = "macos")]
fn font_family() -> SharedString {
    ".AppleSystemUIFont".into()
}

#[cfg(not(any(target_os = "windows", target_os = "macos")))]
fn font_family() -> SharedString {
    "Inter".into()
}

#[cfg(any(target_os = "windows", target_os = "macos"))]
fn mono_family() -> SharedString {
    "Consolas".into()
}

#[cfg(not(any(target_os = "windows", target_os = "macos")))]
fn mono_family() -> SharedString {
    "JetBrains Mono".into()
}

#[cfg(test)]
mod tests {
    use super::{Motion, Theme};
    use gpui::WindowAppearance;
    use std::time::Duration;

    fn luminance(color: gpui::Rgba) -> f32 {
        let channels = [color.r, color.g, color.b];
        let linear: Vec<f32> = channels
            .iter()
            .map(|value| {
                if *value <= 0.039_28 {
                    value / 12.92
                } else {
                    ((value + 0.055) / 1.055).powf(2.4)
                }
            })
            .collect();
        0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]
    }

    fn contrast(a: gpui::Rgba, b: gpui::Rgba) -> f32 {
        let first = luminance(a);
        let second = luminance(b);
        let (light, dark) = if first > second {
            (first, second)
        } else {
            (second, first)
        };
        (light + 0.05) / (dark + 0.05)
    }

    #[test]
    fn le_texte_respecte_le_contraste_aa() {
        for theme in [
            Theme::light(Motion::default()),
            Theme::dark(Motion::default()),
        ] {
            assert!(
                contrast(theme.text, theme.surface) >= 4.5,
                "texte sur surface"
            );
            assert!(
                contrast(theme.text_muted, theme.surface) >= 4.5,
                "texte discret"
            );
            assert!(
                contrast(theme.on_accent, theme.accent) >= 4.5,
                "bouton accent"
            );
        }
    }

    #[test]
    fn le_theme_suit_l_apparence() {
        assert!(!Theme::for_appearance(WindowAppearance::Light, Motion::default()).dark);
        assert!(Theme::for_appearance(WindowAppearance::Dark, Motion::default()).dark);
    }

    #[test]
    fn le_mouvement_reduit_supprime_les_durees() {
        let motion = Motion::new(true);
        assert!(motion.reduced);
        assert_eq!(motion.duration(Duration::from_millis(200)), Duration::ZERO);
        assert_eq!(
            Motion::default().duration(Duration::from_millis(200)),
            Duration::from_millis(200)
        );
    }
}
