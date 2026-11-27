//! Interface native de CheckMate.
//!
//! La coquille lit `runtime.json` et l'API locale ecrite par Python. Elle
//! n'ecrit aucun fichier de donnees et ne depend jamais de `checkmate-cli`.

pub mod client;
pub mod components;
pub mod state;
pub mod theme;

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
