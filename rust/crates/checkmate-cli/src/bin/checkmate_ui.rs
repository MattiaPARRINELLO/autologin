//! Binaire de la coquille GPUI.
//!
//! Sans argument, il ouvre la fenetre. `--tray` lance l'icone native sans
//! fenetre, `notify` et `autostart` sont les commandes internes appelees par
//! Python. `--headless` ou `CHECKMATE_HEADLESS=1` interdit toute fenetre :
//! le binaire lit l'API locale et affiche un resume. `--check` fait la meme
//! chose et sort en erreur si le service est absent.

use checkmate_ui::app::{headless_summary, run, run_setup};
use checkmate_ui::client::LiveBackend;

fn main() {
    let args: Vec<String> = std::env::args().skip(1).collect();
    if args
        .iter()
        .any(|argument| argument == "--help" || argument == "-h")
    {
        println!(
            "checkmate-ui : coquille native de CheckMate\n\n\
             --setup      ouvre directement l'assistant\n\
             --tray       lance l'icone de zone de notification\n\
             --headless   ne cree aucune fenetre, affiche l'etat\n\
             --check      comme --headless, code 1 si le service est absent\n\
             --version    affiche la version\n\n\
             Commandes internes :\n\
             notify       envoie une notification bureau\n\
             autostart    installe, retire ou interroge le demarrage automatique"
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
    if args.first().is_some_and(|argument| argument == "--tray") {
        std::process::exit(checkmate_cli::tray_runner::run());
    }
    if args.first().is_some_and(|argument| argument == "notify") {
        std::process::exit(checkmate_cli::integrations::notify(&args[1..]));
    }
    if args.first().is_some_and(|argument| argument == "autostart") {
        std::process::exit(checkmate_cli::integrations::autostart_command(&args[1..]));
    }
    let headless = args
        .iter()
        .any(|argument| argument == "--headless" || argument == "--check")
        || checkmate_platform::headless_by_environment();
    if !headless {
        if args.iter().any(|argument| argument == "--setup") {
            run_setup();
        } else {
            run();
        }
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
