//! Point d'entree du binaire `checkmate`.
//!
//! Le squelette se contente d'afficher l'identite de l'application. Les
//! commandes `run`, `setup`, `status`, `capture`, `self-test`, `update` et
//! `support-bundle` arrivent avec la tranche T4.

fn main() {
    println!(
        "{} [{}]",
        checkmate_ui::title(),
        checkmate_platform::target()
    );
}
