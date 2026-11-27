//! Icone d'etat dessinee en memoire.
//!
//! Les memes pixels servent au StatusNotifierItem Linux et a l'icone Windows :
//! un carre arrondi colore et une coche claire, comme `tray.py`. Aucun fichier
//! temporaire, aucune dependance graphique.

/// Cote de l'icone, identique a `tray.status_image`.
pub const ICON_SIZE: u32 = 64;

/// Etat visuel de l'icone.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Default)]
pub enum TrayMode {
    /// Surveillance normale.
    #[default]
    Active,
    /// Hors creneau ou attention douce.
    Outside,
    /// Creneau deja signe.
    Signed,
    /// Absence detectee.
    Absent,
    /// Erreur de surveillance.
    Error,
    /// Mise a jour requise.
    Blocked,
    /// Mise a jour disponible.
    Updating,
}

impl TrayMode {
    /// Convertit le `mode` de `/api/status`.
    #[must_use]
    pub fn from_status(mode: &str) -> Self {
        match mode {
            "outside" | "attention" => Self::Outside,
            "signed" | "paused" => Self::Signed,
            "absent" => Self::Absent,
            "error" => Self::Error,
            "blocked" => Self::Blocked,
            "updating" | "update" => Self::Updating,
            _ => Self::Active,
        }
    }

    fn color(self) -> [u8; 4] {
        match self {
            Self::Active => [47, 111, 79, 255],
            Self::Outside | Self::Updating => [154, 107, 47, 255],
            Self::Signed => [31, 27, 22, 255],
            Self::Absent => [107, 114, 128, 255],
            Self::Error | Self::Blocked => [179, 38, 30, 255],
        }
    }

    /// Vrai si la zone de notification doit attirer l'attention.
    #[must_use]
    pub fn needs_attention(self) -> bool {
        matches!(self, Self::Error | Self::Blocked | Self::Updating)
    }
}

/// Icone RGBA, prete pour un `tray_icon::Icon` ou une conversion ARGB.
#[must_use]
pub fn rgba(mode: TrayMode) -> Vec<u8> {
    let color = mode.color();
    let mut pixels = vec![0_u8; (ICON_SIZE * ICON_SIZE * 4) as usize];
    for y in 0..ICON_SIZE {
        for x in 0..ICON_SIZE {
            let index = ((y * ICON_SIZE + x) * 4) as usize;
            let pixel = pixel_at(x, y, color);
            pixels[index..index + 4].copy_from_slice(&pixel);
        }
    }
    pixels
}

/// Icone ARGB32 en ordre reseau, format attendu par `ksni`.
#[must_use]
pub fn argb32(mode: TrayMode) -> Vec<u8> {
    let mut pixels = rgba(mode);
    for pixel in pixels.as_chunks_mut::<4>().0 {
        let [red, green, blue, alpha] = *pixel;
        *pixel = [alpha, red, green, blue];
    }
    pixels
}

fn pixel_at(x: u32, y: u32, color: [u8; 4]) -> [u8; 4] {
    let point = (f64::from(x) + 0.5, f64::from(y) + 0.5);
    if !inside_rounded_rectangle(point) {
        return [0, 0, 0, 0];
    }
    if near_check(point) {
        return [247, 244, 238, 255];
    }
    color
}

fn inside_rounded_rectangle((x, y): (f64, f64)) -> bool {
    const LEFT: f64 = 4.0;
    const TOP: f64 = 4.0;
    const RIGHT: f64 = 60.0;
    const BOTTOM: f64 = 60.0;
    const RADIUS: f64 = 16.0;
    if x < LEFT || x > RIGHT || y < TOP || y > BOTTOM {
        return false;
    }
    let closest_x = x.clamp(LEFT + RADIUS, RIGHT - RADIUS);
    let closest_y = y.clamp(TOP + RADIUS, BOTTOM - RADIUS);
    let dx = x - closest_x;
    let dy = y - closest_y;
    dx * dx + dy * dy <= RADIUS * RADIUS
}

fn near_check(point: (f64, f64)) -> bool {
    const HALF_WIDTH: f64 = 3.0;
    distance_to_segment(point, (18.0, 33.0), (28.0, 43.0)) <= HALF_WIDTH
        || distance_to_segment(point, (28.0, 43.0), (46.0, 21.0)) <= HALF_WIDTH
}

fn distance_to_segment(point: (f64, f64), start: (f64, f64), end: (f64, f64)) -> f64 {
    let (px, py) = point;
    let (sx, sy) = start;
    let (ex, ey) = end;
    let dx = ex - sx;
    let dy = ey - sy;
    let length_squared = dx * dx + dy * dy;
    if length_squared == 0.0 {
        return ((px - sx).powi(2) + (py - sy).powi(2)).sqrt();
    }
    let projection = ((px - sx) * dx + (py - sy) * dy) / length_squared;
    let clamped = projection.clamp(0.0, 1.0);
    let closest_x = sx + clamped * dx;
    let closest_y = sy + clamped * dy;
    ((px - closest_x).powi(2) + (py - closest_y).powi(2)).sqrt()
}

#[cfg(test)]
mod tests {
    use super::{ICON_SIZE, TrayMode, argb32, rgba};

    #[test]
    fn les_quatre_coins_sont_transparents() {
        let pixels = rgba(TrayMode::Active);
        for (x, y) in [(0, 0), (ICON_SIZE - 1, 0), (0, ICON_SIZE - 1)] {
            let index = ((y * ICON_SIZE + x) * 4) as usize;
            assert_eq!(pixels[index + 3], 0);
        }
    }

    #[test]
    fn le_centre_est_colore_puis_la_coche_est_claire() {
        let pixels = rgba(TrayMode::Error);
        let center = ((52 * ICON_SIZE + 32) * 4) as usize;
        assert_eq!(&pixels[center..center + 4], &[179, 38, 30, 255]);
        let check = ((33 * ICON_SIZE + 18) * 4) as usize;
        assert_eq!(&pixels[check..check + 4], &[247, 244, 238, 255]);
    }

    #[test]
    fn argb_place_l_alpha_en_tete() {
        let pixels = argb32(TrayMode::Active);
        let center = ((52 * ICON_SIZE + 32) * 4) as usize;
        assert_eq!(pixels[center], 255);
        assert_eq!(pixels[center + 1], 47);
        assert_eq!(pixels[center + 2], 111);
        assert_eq!(pixels[center + 3], 79);
    }

    #[test]
    fn les_modes_python_sont_reconnus() {
        assert_eq!(TrayMode::from_status("outside"), TrayMode::Outside);
        assert_eq!(TrayMode::from_status("signed"), TrayMode::Signed);
        assert_eq!(TrayMode::from_status("error"), TrayMode::Error);
        assert_eq!(TrayMode::from_status("inconnu"), TrayMode::Active);
        assert!(TrayMode::Error.needs_attention());
        assert!(!TrayMode::Active.needs_attention());
    }
}
