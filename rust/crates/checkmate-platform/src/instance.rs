//! Instance unique de la coquille.
//!
//! Un second lancement ne doit pas ouvrir une deuxieme fenetre : il demande a
//! la premiere de revenir au premier plan, puis sort. Le verrou est le port
//! d'ecoute lui-meme : un seul processus peut lier un port de la plage derivee
//! du dossier de donnees. Aucun fichier temporaire, donc aucun verrou perime
//! apres un plantage.

use std::collections::hash_map::DefaultHasher;
use std::hash::{Hash, Hasher};
use std::io::{BufRead, BufReader, Write};
use std::net::{Ipv4Addr, SocketAddr, TcpListener, TcpStream};
use std::sync::Arc;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::mpsc::{Receiver, Sender, TryRecvError, channel};
use std::time::Duration;

/// Message qu'un second lancement envoie pour demander le premier plan.
const FOCUS_MESSAGE: &str = "checkmate-focus";
/// Reponse du processus qui possede la fenetre.
const FOCUS_REPLY: &str = "ok";
/// Debut de la plage de ports reservee a l'instance unique.
const PORT_BASE: u16 = 39_000;
/// Nombre de ports essayes avant de renoncer au verrou.
const PORT_COUNT: u16 = 32;
/// Delai maximal d'une demande de focalisation.
const CONNECT_TIMEOUT: Duration = Duration::from_millis(250);

/// Resultat d'une tentative d'instance unique.
pub enum Acquisition {
    /// Ce processus possede la fenetre et doit ecouter les demandes de focus.
    Primary(InstanceGuard),
    /// Une autre instance possede deja la fenetre.
    Existing,
    /// Aucun port n'est disponible, le lancement continue sans verrou.
    Unavailable,
}

/// Verrou vivant tant que la fenetre existe.
///
/// Le champ `events` remonte une demande de focalisation ; le `Drop` arrete le
/// thread d'ecoute et libere le port.
pub struct InstanceGuard {
    events: Receiver<()>,
    stop: Arc<AtomicBool>,
}

impl InstanceGuard {
    /// Vrai si une autre instance a demande le premier plan.
    #[must_use]
    pub fn take_focus_request(&self) -> bool {
        match self.events.try_recv() {
            Ok(()) => true,
            Err(TryRecvError::Empty | TryRecvError::Disconnected) => false,
        }
    }
}

impl Drop for InstanceGuard {
    fn drop(&mut self) {
        self.stop.store(true, Ordering::Release);
    }
}

/// Tente de devenir l'instance unique de la coquille.
#[must_use]
pub fn acquire() -> Acquisition {
    acquire_on(&candidate_ports())
}

/// Demande a l'instance existante de revenir au premier plan.
///
/// Rend `true` quand un processus a repondu, `false` si aucun ne repond.
#[must_use]
pub fn request_focus() -> bool {
    candidate_ports().iter().any(|port| focus_on(*port))
}

/// Ports derives du dossier de donnees, stables d'un lancement a l'autre.
#[must_use]
pub fn candidate_ports() -> Vec<u16> {
    let seed = crate::data_dir().map_or_else(
        || std::env::consts::OS.to_owned(),
        |dir| dir.display().to_string(),
    );
    ports_for(&seed)
}

fn ports_for(seed: &str) -> Vec<u16> {
    let mut hasher = DefaultHasher::new();
    seed.hash(&mut hasher);
    let offset = u16::try_from(hasher.finish() % u64::from(PORT_COUNT)).unwrap_or(0);
    (0..PORT_COUNT)
        .map(|index| PORT_BASE + (offset + index) % PORT_COUNT)
        .collect()
}

fn acquire_on(ports: &[u16]) -> Acquisition {
    if ports.iter().any(|port| focus_on(*port)) {
        return Acquisition::Existing;
    }
    for port in ports {
        if let Ok(listener) = bind(*port) {
            let (events, receiver) = channel();
            let stop = Arc::new(AtomicBool::new(false));
            spawn_listener(listener, events, stop.clone());
            return Acquisition::Primary(InstanceGuard {
                events: receiver,
                stop,
            });
        }
    }
    Acquisition::Unavailable
}

fn bind(port: u16) -> std::io::Result<TcpListener> {
    let address = SocketAddr::from((Ipv4Addr::LOCALHOST, port));
    let listener = TcpListener::bind(address)?;
    listener.set_nonblocking(true)?;
    Ok(listener)
}

fn spawn_listener(listener: TcpListener, events: Sender<()>, stop: Arc<AtomicBool>) {
    std::thread::spawn(move || {
        while !stop.load(Ordering::Acquire) {
            match listener.accept() {
                Ok((stream, _)) => {
                    if serve(stream, &events) {
                        continue;
                    }
                }
                Err(error) if error.kind() == std::io::ErrorKind::WouldBlock => {}
                Err(_) => {
                    std::thread::sleep(Duration::from_millis(100));
                }
            }
            std::thread::sleep(Duration::from_millis(50));
        }
    });
}

fn serve(mut stream: TcpStream, events: &Sender<()>) -> bool {
    let _ = stream.set_read_timeout(Some(CONNECT_TIMEOUT));
    let _ = stream.set_write_timeout(Some(CONNECT_TIMEOUT));
    let mut line = String::new();
    let mut reader = BufReader::new(match stream.try_clone() {
        Ok(clone) => clone,
        Err(_) => return false,
    });
    if reader.read_line(&mut line).is_err() {
        return false;
    }
    if line.trim() != FOCUS_MESSAGE {
        return false;
    }
    if events.send(()).is_err() {
        return false;
    }
    stream
        .write_all(format!("{FOCUS_REPLY}\n").as_bytes())
        .is_ok()
}

fn focus_on(port: u16) -> bool {
    let address = SocketAddr::from((Ipv4Addr::LOCALHOST, port));
    let Ok(mut stream) = TcpStream::connect_timeout(&address, CONNECT_TIMEOUT) else {
        return false;
    };
    let _ = stream.set_read_timeout(Some(CONNECT_TIMEOUT));
    let _ = stream.set_write_timeout(Some(CONNECT_TIMEOUT));
    if stream
        .write_all(format!("{FOCUS_MESSAGE}\n").as_bytes())
        .is_err()
    {
        return false;
    }
    let mut reply = String::new();
    match BufReader::new(stream).read_line(&mut reply) {
        Ok(_) => reply.trim() == FOCUS_REPLY,
        Err(_) => false,
    }
}

#[cfg(test)]
mod tests {
    use super::{Acquisition, FOCUS_MESSAGE, acquire_on, focus_on, ports_for, serve};
    use std::io::{BufRead, BufReader, Write};
    use std::net::{Ipv4Addr, SocketAddr, TcpListener, TcpStream};
    use std::sync::mpsc::channel;
    use std::time::Duration;

    #[test]
    fn les_ports_derives_sont_stables_et_dans_la_plage() {
        let first = ports_for("checkmate-instance-test");
        assert_eq!(first, ports_for("checkmate-instance-test"));
        assert_eq!(first.len(), super::PORT_COUNT as usize);
        assert!(
            first.iter().all(
                |port| (super::PORT_BASE..super::PORT_BASE + super::PORT_COUNT).contains(port)
            )
        );
        let mut sorted = first.clone();
        sorted.sort_unstable();
        sorted.dedup();
        assert_eq!(sorted.len(), first.len());
        assert_ne!(first, ports_for("un-autre-dossier"));
    }

    fn free_port() -> u16 {
        let listener = TcpListener::bind((Ipv4Addr::LOCALHOST, 0)).expect("port libre");
        listener.local_addr().expect("adresse").port()
    }

    #[test]
    fn un_second_lancement_focalise_le_premier() {
        let port = free_port();
        let Acquisition::Primary(guard) = acquire_on(&[port]) else {
            panic!("le premier processus doit posseder le verrou");
        };
        assert!(!guard.take_focus_request());
        let second = acquire_on(&[port]);
        assert!(matches!(second, Acquisition::Existing));
        assert!(guard.take_focus_request());
        drop(guard);
        let after = acquire_on(&[port]);
        assert!(matches!(after, Acquisition::Primary(_)));
    }

    #[test]
    fn le_focus_ignore_un_port_etranger() {
        let listener = TcpListener::bind((Ipv4Addr::LOCALHOST, 0)).expect("port libre");
        let port = listener.local_addr().expect("adresse").port();
        std::thread::spawn(move || {
            if let Ok((mut stream, _)) = listener.accept() {
                let mut line = String::new();
                let _ = BufReader::new(stream.try_clone().expect("clone")).read_line(&mut line);
                let _ = stream.write_all(b"non\n");
            }
        });
        assert!(!focus_on(port));
    }

    #[test]
    fn une_requete_valide_est_acceptee() {
        let listener = TcpListener::bind((Ipv4Addr::LOCALHOST, 0)).expect("port libre");
        let port = listener.local_addr().expect("adresse").port();
        let (events, receiver) = channel();
        std::thread::spawn(move || {
            let (stream, _) = listener.accept().expect("connexion");
            assert!(serve(stream, &events));
        });
        let mut stream = TcpStream::connect_timeout(
            &SocketAddr::from((Ipv4Addr::LOCALHOST, port)),
            Duration::from_secs(1),
        )
        .expect("connexion");
        stream
            .write_all(format!("{FOCUS_MESSAGE}\n").as_bytes())
            .expect("envoi");
        let mut reply = String::new();
        BufReader::new(stream)
            .read_line(&mut reply)
            .expect("lecture");
        assert_eq!(reply.trim(), "ok");
        assert!(receiver.recv_timeout(Duration::from_secs(1)).is_ok());
    }
}
