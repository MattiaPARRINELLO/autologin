"""Traduction des erreurs techniques en messages compréhensibles."""

from __future__ import annotations

from .cesar import CesarError, LoginError, SignError

MAX_MESSAGE = 200

TIMEOUT_MESSAGE = "CESAR met trop de temps à répondre. Vérifie la connexion internet."

DNS_MESSAGE = (
    "CESAR est injoignable : le nom de domaine ne se résout pas. "
    "Vérifie la connexion internet ou le VPN."
)
INTERRUPTED_MESSAGE = (
    "La connexion à CESAR a été interrompue. Réessaie dans quelques instants."
)
UNREACHABLE_MESSAGE = "CESAR est injoignable pour le moment."

# Les motifs sont testés dans l'ordre : les plus spécifiques d'abord, les
# génériques en dernier.
HINTS = (
    ("ERR_NAME_NOT_RESOLVED", "reseau", DNS_MESSAGE),
    ("ERR_NAME_RESOLUTION_FAILED", "reseau", DNS_MESSAGE),
    (
        "ERR_INTERNET_DISCONNECTED",
        "reseau",
        "Aucune connexion internet. Vérifie le réseau puis réessaie.",
    ),
    (
        "ERR_CONNECTION_REFUSED",
        "reseau",
        "CESAR refuse la connexion. Réessaie dans quelques instants.",
    ),
    ("ERR_CONNECTION_RESET", "reseau", INTERRUPTED_MESSAGE),
    ("ERR_CONNECTION_CLOSED", "reseau", INTERRUPTED_MESSAGE),
    ("ERR_CONNECTION_TIMED_OUT", "reseau", TIMEOUT_MESSAGE),
    ("ERR_TIMED_OUT", "reseau", TIMEOUT_MESSAGE),
    (
        "ERR_PROXY_CONNECTION_FAILED",
        "reseau",
        "Le proxy configuré ne répond pas. Vérifie sa configuration.",
    ),
    (
        "ERR_CERT_",
        "securite",
        (
            "Le certificat de CESAR n'est pas valide. "
            "Ne saisis pas tes identifiants tant que le problème persiste."
        ),
    ),
    (
        "Executable doesn't exist",
        "navigateur",
        "Le navigateur intégré est introuvable. Réinstalle CheckMate.",
    ),
    (
        "Target page, context or browser has been closed",
        "navigateur",
        "Le navigateur a été fermé. CheckMate le relance automatiquement.",
    ),
    ("net::ERR", "reseau", UNREACHABLE_MESSAGE),
    ("ERR_FAILED", "reseau", UNREACHABLE_MESSAGE),
)


def _first_line(exc: BaseException) -> str:
    text = str(exc).strip() or exc.__class__.__name__
    return text.splitlines()[0].strip()[:MAX_MESSAGE]


def _match(text: str) -> tuple[str, str] | None:
    lowered = text.casefold()
    for marker, kind, message in HINTS:
        if marker.casefold() in lowered:
            return kind, message
    return None


def describe_error(exc: BaseException) -> tuple[str, str]:
    """Retourne la catégorie et le message lisible d'une exception."""
    text = _first_line(exc)
    hint = _match(text)
    if hint is not None:
        return hint
    if isinstance(exc, LoginError):
        return "connexion", f"La connexion à CESAR a échoué : {text}"
    if isinstance(exc, SignError):
        return "signature", f"La signature a échoué : {text}"
    if isinstance(exc, CesarError):
        return "cesar", text
    if isinstance(exc, TimeoutError):
        return "reseau", TIMEOUT_MESSAGE
    return "inconnue", f"Erreur inattendue : {text}"
