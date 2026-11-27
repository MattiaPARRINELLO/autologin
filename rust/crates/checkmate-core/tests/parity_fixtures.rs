//! Verifie que les fixtures de parite partagees sont completes et lisibles.
//!
//! Les valeurs attendues sont rejouees par le test Python
//! `watcher/tests/test_parity_fixtures.py`. Ici on garantit seulement que le
//! cote Rust peut lire les memes fichiers et que leur structure reste stable.

use std::collections::HashSet;
use std::path::{Path, PathBuf};

use serde_json::Value;

const DOMAINS: [&str; 4] = ["config", "schedule", "release_notes", "updates"];

fn fixture_path(domain: &str) -> PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("../../fixtures/parity")
        .join(format!("{domain}.json"))
}

fn load(domain: &str) -> Value {
    let content = std::fs::read_to_string(fixture_path(domain))
        .unwrap_or_else(|error| panic!("lecture de {domain} impossible : {error}"));
    serde_json::from_str(&content)
        .unwrap_or_else(|error| panic!("JSON de {domain} invalide : {error}"))
}

fn cases(domain: &str) -> Vec<Value> {
    let payload = load(domain);
    assert_eq!(payload["domain"], domain, "domaine incoherent");
    payload["cases"]
        .as_array()
        .unwrap_or_else(|| panic!("{domain} sans tableau cases"))
        .clone()
}

#[test]
fn les_quatre_fixtures_existent() {
    for domain in DOMAINS {
        assert!(fixture_path(domain).is_file(), "{domain}.json absent");
    }
}

#[test]
fn chaque_cas_a_un_nom_unique() {
    for domain in DOMAINS {
        let names: Vec<String> = cases(domain)
            .iter()
            .map(|case| case["name"].as_str().unwrap_or_default().to_owned())
            .collect();
        let unique: HashSet<&String> = names.iter().collect();
        assert!(!names.is_empty(), "{domain} sans cas");
        assert_eq!(names.len(), unique.len(), "{domain} a des noms doubles");
        assert!(
            names.iter().all(|name| !name.is_empty()),
            "{domain} sans nom"
        );
    }
}

#[test]
fn chaque_cas_porte_une_attente() {
    for domain in DOMAINS {
        for case in cases(domain) {
            assert!(
                case["expect"].is_object(),
                "{domain} : {} sans attente",
                case["name"]
            );
        }
    }
}

#[test]
fn les_operations_sont_connues() {
    let expected = [
        (
            "schedule",
            &[
                "parse_window",
                "parse_windows",
                "parse_days",
                "active_window",
                "window_key",
                "next_start",
                "seconds_until_next",
            ][..],
        ),
        ("release_notes", &["significant", "note", "celebration"][..]),
        (
            "updates",
            &[
                "parse_version",
                "parse_release",
                "select_latest",
                "check_for_update",
                "platform_asset",
                "parse_checksums",
                "update_policy",
            ][..],
        ),
    ];
    for (domain, allowed) in expected {
        for case in cases(domain) {
            let op = case["op"].as_str().unwrap_or_default();
            assert!(allowed.contains(&op), "{domain} : operation {op} inconnue");
        }
    }
}

#[test]
fn les_cas_de_config_ont_une_entree() {
    for case in cases("config") {
        let has_error = case["expect"]["error"].is_string();
        let has_values = case["expect"]["values"].is_object();
        assert!(has_error ^ has_values, "config : attente ambigue");
        let has_toml = case["toml"].is_string() || case["toml_lines"].is_array();
        let missing_file = case["file"].as_bool() == Some(false);
        assert!(has_toml || missing_file, "config : entree absente");
    }
}
