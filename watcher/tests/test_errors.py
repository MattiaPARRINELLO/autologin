from __future__ import annotations

from checkmate_watcher.cesar import CesarError, LoginError, SignError
from checkmate_watcher.errors import MAX_MESSAGE, describe_error


def test_dns_failure_est_expliquee():
    error = Exception(
        "Page.goto: net::ERR_NAME_NOT_RESOLVED at https://cesar.emineo-education.fr/\n"
        'Call log:\n  - navigating to "https://cesar.emineo-education.fr/"'
    )
    kind, message = describe_error(error)
    assert kind == "reseau"
    assert "nom de domaine" in message


def test_connexion_refusee_est_expliquee():
    kind, message = describe_error(
        Exception("net::ERR_CONNECTION_REFUSED at https://cesar.emineo-education.fr/")
    )
    assert kind == "reseau"
    assert "refuse la connexion" in message


def test_certificat_invalide_est_signale():
    kind, message = describe_error(Exception("net::ERR_CERT_DATE_INVALID"))
    assert kind == "securite"
    assert "certificat" in message


def test_timeout_asyncio():
    kind, message = describe_error(TimeoutError())
    assert kind == "reseau"
    assert "trop de temps" in message


def test_cause_curl_timeout_est_expliquee():
    error = CesarError("transport HTTP impossible")
    error.__cause__ = TimeoutError("curl timed out")

    kind, message = describe_error(error)

    assert kind == "reseau"
    assert "trop de temps" in message


def test_cause_curl_certificat_est_signalee():
    error = CesarError("transport HTTP impossible")
    error.__cause__ = ValueError("SSL certificate problem")

    kind, message = describe_error(error)

    assert kind == "securite"
    assert "certificat" in message


def test_echec_de_connexion_cesar():
    kind, message = describe_error(LoginError("champs de connexion introuvables"))
    assert kind == "connexion"
    assert "champs de connexion introuvables" in message


def test_echec_de_signature():
    kind, message = describe_error(SignError("canvas de signature sans dimensions"))
    assert kind == "signature"
    assert "signature" in message


def test_erreur_inconnue_garde_la_premiere_ligne():
    kind, message = describe_error(ValueError("boum\nligne suivante"))
    assert kind == "inconnue"
    assert message == "Erreur inattendue : boum"


def test_erreur_inconnue_est_tronquee():
    kind, message = describe_error(ValueError("x" * 500))
    assert kind == "inconnue"
    assert len(message) <= MAX_MESSAGE + len("Erreur inattendue : ")
