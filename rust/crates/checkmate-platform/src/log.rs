//! Journal minimal des integrations systeme.
//!
//! Python possede encore le journal principal en T2. Les processus natifs
//! courts (notification, autostart) ecrivent ici pour qu'une panne reste
//! diagnosticable meme quand leur sortie standard est fermee.

use std::io::Write;
use std::path::Path;

const LOG_NAME: &str = "checkmate-native.log";

/// Ecrit une ligne horodatee, sur la sortie d'erreur et dans le journal local.
pub fn write(level: &str, message: &str) {
    let line = format!("[{level}] {message}");
    eprintln!("{line}");
    if let Some(directory) = crate::log_dir() {
        append(&directory.join(LOG_NAME), &line);
    }
}

/// Signale un avertissement.
pub fn warn(message: &str) {
    write("warn", message);
}

/// Signale une information.
pub fn info(message: &str) {
    write("info", message);
}

fn append(path: &Path, line: &str) {
    if let Some(parent) = path.parent() {
        let _ = std::fs::create_dir_all(parent);
    }
    let Ok(mut file) = std::fs::OpenOptions::new()
        .create(true)
        .append(true)
        .open(path)
    else {
        return;
    };
    let _ = writeln!(file, "{line}");
}

#[cfg(test)]
mod tests {
    #[test]
    fn le_nom_du_journal_reste_stable() {
        assert_eq!(super::LOG_NAME, "checkmate-native.log");
    }
}
