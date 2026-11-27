//! Point d'entree du binaire `checkmate`.
//!
//! Le squelette se contente d'afficher l'identite de l'application. Les
//! commandes `run`, `setup`, `status`, `capture`, `self-test`, `update` et
//! `support-bundle` arrivent avec la tranche T4.
//!
//! `--bench-hold-ms` retient le processus le temps de mesurer son pic memoire.
//! Ce drapeau interne au harnais disparaitra avec le vrai mode daemon.

use std::time::Duration;

const HOLD_FLAG: &str = "--bench-hold-ms=";

fn bench_hold() -> Option<u64> {
    std::env::args().find_map(|argument| argument.strip_prefix(HOLD_FLAG)?.parse().ok())
}

fn main() {
    println!(
        "{} [{}]",
        checkmate_ui::title(),
        checkmate_platform::target()
    );
    if let Some(milliseconds) = bench_hold() {
        std::thread::sleep(Duration::from_millis(milliseconds));
    }
}
