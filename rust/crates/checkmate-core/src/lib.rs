//! Coeur metier de CheckMate.
//!
//! Cette crate ne fait aucune entree/sortie : pas de fichier, pas de reseau,
//! pas d'horloge systeme, pas de dependance a une plateforme. Le temps, les
//! sockets, le trousseau et le systeme de fichiers sont fournis par les autres
//! crates. Les regles de frontiere sont verifiees par
//! `scripts/check-boundaries.py`.

/// Nom affiche du produit.
pub const NAME: &str = "CheckMate";

/// Version du workspace Rust.
pub const VERSION: &str = env!("CARGO_PKG_VERSION");

pub mod actions;
pub mod setup;
pub mod status;
pub mod timefmt;

#[cfg(test)]
mod tests {
    use super::{NAME, VERSION};

    #[test]
    fn le_nom_est_renseigne() {
        assert_ne!(NAME, "");
    }

    #[test]
    fn la_version_suit_le_workspace() {
        assert_eq!(VERSION, env!("CARGO_PKG_VERSION"));
    }
}
