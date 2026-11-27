//! Signature : mise a l'echelle pour l'apercu et import PNG/JPG.

use std::fmt;
use std::path::Path;

use checkmate_core::setup::{PointKind, SignaturePoint};

/// Echec d'import d'une signature.
#[derive(Debug)]
pub enum ImportError {
    Read(String),
    Decode(String),
    Empty,
}

impl fmt::Display for ImportError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::Read(message) => write!(formatter, "image illisible : {message}"),
            Self::Decode(message) => write!(formatter, "format non pris en charge : {message}"),
            Self::Empty => write!(formatter, "l'image ne contient aucun trait"),
        }
    }
}

impl std::error::Error for ImportError {}

/// Taille maximale de l'apercu, en pixels logiques.
pub const PREVIEW_WIDTH: f32 = 520.0;
pub const PREVIEW_HEIGHT: f32 = 180.0;

/// Centre et met a l'echelle le trace, comme `signature.fit_points`.
pub fn fit_points(points: &[SignaturePoint], width: f32, height: f32) -> Vec<(f32, f32)> {
    if points.is_empty() || width <= 0.0 || height <= 0.0 {
        return Vec::new();
    }
    let padding = 0.9;
    let min_x = points.iter().map(|point| point.x).fold(f32::MAX, f32::min);
    let max_x = points.iter().map(|point| point.x).fold(f32::MIN, f32::max);
    let min_y = points.iter().map(|point| point.y).fold(f32::MAX, f32::min);
    let max_y = points.iter().map(|point| point.y).fold(f32::MIN, f32::max);
    let box_width = (max_x - min_x).max(1.0);
    let box_height = (max_y - min_y).max(1.0);
    let scale = ((width * padding) / box_width).min((height * padding) / box_height);
    let offset_x = (width - box_width * scale) / 2.0;
    let offset_y = (height - box_height * scale) / 2.0;
    points
        .iter()
        .map(|point| {
            let x = offset_x + (point.x - min_x) * scale;
            let y = offset_y + (point.y - min_y) * scale;
            (x.clamp(0.0, width), y.clamp(0.0, height))
        })
        .collect()
}

/// Vrai si le trace a une etendue suffisante, comme `MIN_EXTENT` en Python.
pub fn is_usable(points: &[SignaturePoint]) -> bool {
    if points.len() < 2 {
        return false;
    }
    let min_x = points.iter().map(|point| point.x).fold(f32::MAX, f32::min);
    let max_x = points.iter().map(|point| point.x).fold(f32::MIN, f32::max);
    let min_y = points.iter().map(|point| point.y).fold(f32::MAX, f32::min);
    let max_y = points.iter().map(|point| point.y).fold(f32::MIN, f32::max);
    (max_x - min_x).max(max_y - min_y) >= 2.0
}

/// Importe une image PNG ou JPG en points de signature.
pub fn points_from_path(path: &Path) -> Result<Vec<SignaturePoint>, ImportError> {
    let bytes = std::fs::read(path).map_err(|error| ImportError::Read(error.to_string()))?;
    points_from_bytes(&bytes)
}

/// Decode une image et convertit les pixels sombres en points.
///
/// Le pas d'echantillonnage borne le nombre de points et garde la forme du
/// trait. Le format envoye a Python reste une liste `{x, y, type}`.
#[allow(clippy::cast_precision_loss)]
pub fn points_from_bytes(bytes: &[u8]) -> Result<Vec<SignaturePoint>, ImportError> {
    let image =
        image::load_from_memory(bytes).map_err(|error| ImportError::Decode(error.to_string()))?;
    let luma = image.to_luma8();
    let (width, height) = luma.dimensions();
    if width == 0 || height == 0 {
        return Err(ImportError::Empty);
    }
    let step = (width.max(height) / 220).max(1);
    let mut points = Vec::new();
    for (x, y, pixel) in luma.enumerate_pixels() {
        if x % step != 0 || y % step != 0 {
            continue;
        }
        if pixel[0] >= 128 {
            continue;
        }
        points.push(SignaturePoint {
            x: (x as f32 / width as f32) * 1000.0,
            y: (y as f32 / height as f32) * 1000.0,
            kind: PointKind::Move,
        });
    }
    if points.len() < 2 {
        return Err(ImportError::Empty);
    }
    if let Some(first) = points.first_mut() {
        first.kind = PointKind::Start;
    }
    if let Some(last) = points.last_mut() {
        last.kind = PointKind::End;
    }
    Ok(points)
}

#[cfg(test)]
mod tests {
    use super::{fit_points, is_usable, points_from_bytes, points_from_path};
    use checkmate_core::setup::{PointKind, SignaturePoint};

    fn point(x: f32, y: f32) -> SignaturePoint {
        SignaturePoint {
            x,
            y,
            kind: PointKind::Move,
        }
    }

    #[test]
    fn le_trace_est_centre_dans_l_apercu() {
        let points = vec![point(0.0, 0.0), point(100.0, 50.0)];
        let fitted = fit_points(&points, 520.0, 180.0);
        assert_eq!(fitted.len(), 2);
        for (x, y) in fitted {
            assert!((0.0..=520.0).contains(&x));
            assert!((0.0..=180.0).contains(&y));
        }
    }

    #[test]
    fn un_trace_vide_ne_produit_rien() {
        assert_eq!(fit_points(&[], 520.0, 180.0).len(), 0);
    }

    #[test]
    fn un_point_unique_est_inutilisable() {
        assert!(!is_usable(&[point(1.0, 1.0)]));
        assert!(is_usable(&[point(0.0, 0.0), point(40.0, 20.0)]));
    }

    #[test]
    fn refuse_un_fichier_absent() {
        let error = points_from_path(std::path::Path::new("/tmp/checkmate-absent.png"));
        assert!(error.is_err());
    }

    #[test]
    fn importe_un_png_sombre() {
        let mut image = image::GrayImage::new(40, 20);
        for (x, y, pixel) in image.enumerate_pixels_mut() {
            *pixel = if (10..30).contains(&x) && (5..15).contains(&y) {
                image::Luma([0])
            } else {
                image::Luma([255])
            };
        }
        let mut bytes = std::io::Cursor::new(Vec::new());
        image.write_to(&mut bytes, image::ImageFormat::Png).unwrap();
        let points = points_from_bytes(bytes.get_ref()).unwrap();
        assert!(points.len() >= 2);
        assert_eq!(points.first().unwrap().kind, PointKind::Start);
        assert_eq!(points.last().unwrap().kind, PointKind::End);
    }
}
