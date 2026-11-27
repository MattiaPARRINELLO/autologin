//! Integrations systeme de CheckMate.
//!
//! Tout ce qui touche l'OS atterrit ici : fenetre native, icone de notification,
//! notifications, autostart, trousseau, chemins de donnees. Cette crate peut
//! dependre de `checkmate-core`, jamais de `checkmate-ui` ni de
//! `checkmate-cli`.

/// Nom de la plateforme cible, utile aux diagnostics.
#[must_use]
pub fn target() -> &'static str {
    std::env::consts::OS
}

#[cfg(test)]
mod tests {
    use super::target;

    #[test]
    fn la_plateforme_est_connue() {
        assert_ne!(target(), "");
    }
}
