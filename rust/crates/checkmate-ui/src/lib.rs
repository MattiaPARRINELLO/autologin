//! Interface native de CheckMate.
//!
//! Les vues GPUI arrivent avec la tranche T1. Cette crate peut dependre de
//! `checkmate-core` et de `checkmate-platform`, jamais de `checkmate-cli`.

/// Titre de la fenetre principale.
#[must_use]
pub fn title() -> String {
    format!("{} {}", checkmate_core::NAME, checkmate_core::VERSION)
}

#[cfg(test)]
mod tests {
    use super::title;

    #[test]
    fn le_titre_contient_le_nom() {
        assert!(title().contains(checkmate_core::NAME));
    }
}
