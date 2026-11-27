//! Bibliotheque interne du binaire `checkmate`.
//!
//! Les integrations systeme (icone, notifications, autostart) sont portees par
//! `checkmate-platform`; ce crate ne fait que les relier a la ligne de commande.

pub mod integrations;
pub mod tray_runner;
