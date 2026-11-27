//! Commandes internes pour les integrations systeme.
//!
//! Python les appelle par `checkmate-ui` : `notify` et `autostart`. Chaque
//! commande rend un code de sortie stable : 0 succes, 3 indisponible, 1 echec.

use checkmate_platform::autostart::{self, AutostartSpec};
use checkmate_platform::notify::{self, Notice, NoticeUrgency, NotifyOutcome};

const EXIT_OK: i32 = 0;
const EXIT_FAILED: i32 = 1;
const EXIT_UNAVAILABLE: i32 = 3;

/// Envoie une notification. Arguments : `--title`, `--body`, `--urgency`,
/// `--replace-id`, `--action`.
pub fn notify(arguments: &[String]) -> i32 {
    let title = value(arguments, "--title").unwrap_or("CheckMate");
    let body = value(arguments, "--body").unwrap_or_default();
    let urgency = NoticeUrgency::parse(value(arguments, "--urgency").unwrap_or("normal"));
    let mut notice = Notice::new(title, body).with_urgency(urgency);
    if let Some(id) = value(arguments, "--replace-id").and_then(|id| id.parse::<u32>().ok()) {
        notice = notice.with_replace_id(id);
    }
    if let Some(action) = action(value(arguments, "--action")) {
        notice = notice.with_action(action.0, action.1);
    } else if cfg!(target_os = "windows") {
        notice = notice.with_action("open", "Ouvrir le tableau de bord");
    }
    match notify::send_and_wait(&notice) {
        NotifyOutcome::Shown => {
            println!("shown");
            EXIT_OK
        }
        NotifyOutcome::FallbackShown => {
            println!("fallback");
            EXIT_OK
        }
        NotifyOutcome::Unavailable(reason) => {
            eprintln!("notification indisponible : {reason}");
            EXIT_UNAVAILABLE
        }
    }
}

/// Gere `autostart enable|disable|status|restart`.
pub fn autostart_command(arguments: &[String]) -> i32 {
    let Some(action) = arguments.first().map(String::as_str) else {
        eprintln!("usage : checkmate-ui autostart enable|disable|status|restart");
        return EXIT_FAILED;
    };
    match action {
        "enable" => enable_autostart(arguments),
        "disable" => disable_autostart(),
        "status" => status_autostart(),
        "restart" => restart_autostart(),
        other => {
            eprintln!("action autostart inconnue : {other}");
            EXIT_FAILED
        }
    }
}

fn enable_autostart(arguments: &[String]) -> i32 {
    let executable = value(arguments, "--executable");
    let config = value(arguments, "--config");
    let (Some(executable), Some(config)) = (executable, config) else {
        eprintln!("--executable et --config sont obligatoires");
        return EXIT_FAILED;
    };
    match autostart::enable(&AutostartSpec::new(executable, config)) {
        Ok(()) => {
            println!("installed");
            EXIT_OK
        }
        Err(error) => {
            eprintln!("demarrage automatique impossible : {error}");
            EXIT_FAILED
        }
    }
}

fn disable_autostart() -> i32 {
    match autostart::disable() {
        Ok(()) => {
            println!("disabled");
            EXIT_OK
        }
        Err(error) => {
            eprintln!("desactivation impossible : {error}");
            EXIT_FAILED
        }
    }
}

fn status_autostart() -> i32 {
    if autostart::is_enabled() {
        println!("enabled");
    } else {
        println!("disabled");
    }
    EXIT_OK
}

fn restart_autostart() -> i32 {
    match autostart::restart() {
        Ok(()) => {
            println!("restarted");
            EXIT_OK
        }
        Err(error) => {
            eprintln!("redemarrage impossible : {error}");
            EXIT_FAILED
        }
    }
}

fn value<'a>(arguments: &'a [String], flag: &str) -> Option<&'a str> {
    arguments
        .iter()
        .position(|argument| argument == flag)
        .and_then(|index| arguments.get(index + 1))
        .map(String::as_str)
}

fn action(value: Option<&str>) -> Option<(String, String)> {
    let value = value?;
    let (id, label) = value.split_once(':')?;
    Some((id.to_owned(), label.to_owned()))
}

#[cfg(test)]
mod tests {
    use super::{action, value};

    fn args(values: &[&str]) -> Vec<String> {
        values.iter().map(|value| (*value).to_owned()).collect()
    }

    #[test]
    fn lit_une_valeur_apres_le_drapeau() {
        assert_eq!(
            value(&args(&["--title", "CheckMate"]), "--title"),
            Some("CheckMate")
        );
        assert_eq!(value(&args(&["--title"]), "--title"), None);
    }

    #[test]
    fn separe_l_identifiant_et_le_libelle_d_action() {
        assert_eq!(
            action(Some("open:Ouvrir")),
            Some(("open".to_owned(), "Ouvrir".to_owned()))
        );
        assert_eq!(action(Some("invalide")), None);
        assert_eq!(action(None), None);
    }
}
