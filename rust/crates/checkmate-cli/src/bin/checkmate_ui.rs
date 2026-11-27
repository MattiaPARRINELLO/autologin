//! Binaire de la coquille GPUI.
//!
//! Sans argument, il ouvre la fenetre. `--headless` ou `CHECKMATE_HEADLESS=1`
//! interdit toute fenetre : le binaire lit l'API locale et affiche un resume.
//! `--check` fait la meme chose et sort en erreur si le service est absent.

use checkmate_ui::app::{headless_summary, run};
use checkmate_ui::client::LiveBackend;

fn main() {
    let args: Vec<String> = std::env::args().skip(1).collect();
    if args
        .iter()
        .any(|argument| argument == "--help" || argument == "-h")
    {
        println!(
            "checkmate-ui : coquille native de CheckMate\n\n\
             --headless   ne cree aucune fenetre, affiche l'etat\n\
             --check      comme --headless, code 1 si le service est absent\n\
             --version    affiche la version"
        );
        return;
    }
    if args
        .iter()
        .any(|argument| argument == "--version" || argument == "-V")
    {
        println!("checkmate-ui {}", checkmate_core::VERSION);
        return;
    }
    let headless = args
        .iter()
        .any(|argument| argument == "--headless" || argument == "--check")
        || checkmate_platform::headless_by_environment();
    if !headless {
        run();
        return;
    }
    let backend = LiveBackend::discover();
    match headless_summary(&backend) {
        Ok(summary) => println!("{summary}"),
        Err(error) => {
            eprintln!("{error}");
            std::process::exit(1);
        }
    }
}
