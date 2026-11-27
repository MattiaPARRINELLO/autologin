//! Repli des plateformes sans icone native.
//!
//! T2 couvre Linux et Windows. Ailleurs, l'appelant garde l'icone Python
//! jusqu'a la tranche suivante.

use std::sync::mpsc::Sender;

use super::{TrayError, TrayEvent, TrayState};

/// Poignee inerte.
pub struct TrayHandle;

impl TrayHandle {
    /// Aucune icone a mettre a jour.
    pub fn set_state(&self, _state: TrayState) -> bool {
        false
    }

    /// Rien a arreter.
    pub fn shutdown(self) {}
}

/// Signale que la plateforme n'a pas d'icone native.
pub fn start(_initial: TrayState, _events: Sender<TrayEvent>) -> Result<TrayHandle, TrayError> {
    Err(TrayError::unavailable(
        "icone native non prise en charge sur cette plateforme",
    ))
}
