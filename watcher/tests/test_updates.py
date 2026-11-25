from __future__ import annotations

import hashlib
from dataclasses import replace

import pytest

from checkmate_watcher.updates import (
    Asset,
    Release,
    Version,
    check_for_update,
    parse_release,
    parse_version,
    platform_asset,
    select_latest,
    update_policy,
)


def _parsed_version(tag: str) -> Version:
    version = parse_version(tag)
    assert version is not None
    return version


def release(tag: str, *, prerelease: bool = False, assets: tuple = ()) -> Release:
    return Release(
        tag=tag,
        version=_parsed_version(tag),
        url=f"https://example.com/{tag}",
        name=tag,
        prerelease=prerelease,
        assets=assets,
    )


def _paquet(tmp_path, contenu=b"archive"):
    path = tmp_path / "CheckMate-linux-0.4.2.tar.gz"
    path.write_bytes(contenu)
    return path


def _sommes(tmp_path, contenu=b"archive"):
    digest = hashlib.sha256(contenu).hexdigest()
    path = tmp_path / "SHA256SUMS.txt"
    path.write_text(f"{digest}  CheckMate-linux-0.4.2.tar.gz\n", encoding="utf-8")
    return path


def _platform_assets() -> tuple:
    return (
        Asset("CheckMate-Setup-0.4.2.exe", "u"),
        Asset("CheckMate-linux-0.4.2.tar.gz", "v"),
        Asset("SHA256SUMS.txt", "w"),
    )


def _marked(tag: str, *, migration=None, required=None) -> Release:
    return replace(
        release(tag),
        migration_reason=migration,
        required_reason=required,
        markers_declared=True,
    )


def test_parse_release_lit_les_marqueurs():
    body = "CHECKMATE-MIGRATION: 0\nCHECKMATE-REQUIRED: 0"
    parsed = parse_release({"tag_name": "watcher-v0.7.0", "body": body})
    assert parsed is not None and parsed.markers_declared
    assert parsed.migration_reason is None
    assert parsed.required_reason is None


def test_parse_release_conserve_les_raisons():
    body = "CHECKMATE-MIGRATION: format v2\nCHECKMATE-REQUIRED: securite"
    parsed = parse_release({"tag_name": "watcher-v0.7.0", "body": body})
    assert parsed.migration_reason == "format v2"
    assert parsed.required_reason == "securite"


def test_update_policy_detecte_migration_et_obligation():
    releases = [
        _marked("watcher-v0.7.0-beta.1", migration="format v2"),
        _marked("watcher-v0.7.0", required="securite"),
    ]
    policy = update_policy("0.6.6", channel="beta", releases=releases)
    assert policy.available
    assert policy.migration.tag == "watcher-v0.7.0-beta.1"
    assert policy.required.tag == "watcher-v0.7.0"
    assert policy.install_target is policy.migration


def test_parse_version():
    assert parse_version("watcher-v1.2.3") == Version(1, 2, 3)
    assert parse_version("watcher-0.1.0") == Version(0, 1, 0)
    assert parse_version("v1.6.0") == Version(1, 6, 0)
    assert parse_version("pas une version") is None


def test_parse_version_ordonne_les_betas_avant_la_stable():
    beta1 = parse_version("watcher-v0.6.0-beta.1")
    beta2 = parse_version("watcher-v0.6.0-beta.2")
    stable = parse_version("watcher-v0.6.0")
    assert beta1 is not None and beta2 is not None and stable is not None
    assert beta1 < beta2 and beta2 < stable
    assert parse_version("watcher-v0.6.0-beta1") == beta1
    assert str(stable) == "0.6.0"
    assert str(beta1) == "0.6.0-beta.1"


def test_parse_version_garde_les_tags_sans_suffixe():
    assert parse_version("watcher-v0.1.3") == Version(0, 1, 3)
    assert parse_version("watcher-v0.5.9") == Version(0, 5, 9)
    assert parse_version("watcher-v0.5.9") < parse_version("watcher-v0.6.0")


def test_parse_release_compte_les_telechargements():
    parsed = parse_release(
        {
            "tag_name": "watcher-v0.2.0",
            "html_url": "https://example.com/release",
            "name": "CheckMate 0.2.0",
            "assets": [{"download_count": 5}, {"download_count": 7}],
        }
    )
    assert parsed is not None
    assert parsed.downloads == 12


def _payload(tag: str, name: str, *, prerelease: bool = False) -> dict:
    return {
        "tag_name": tag,
        "html_url": "https://example.com/release",
        "name": name,
        "prerelease": prerelease,
    }


def _assert_release(tag: str, name: str, version: Version, *, prerelease=False):
    parsed = parse_release(_payload(tag, name, prerelease=prerelease))
    assert parsed is not None
    assert parsed.version == version
    assert parsed.prerelease is prerelease


def test_parse_release_ignore_les_tags_legacy():
    assert parse_release({"tag_name": "v1.6.0"}) is None
    _assert_release(
        "watcher-v0.2.0", "CheckMate 0.2.0", Version(0, 2, 0), prerelease=True
    )


def test_select_latest_avec_prereleases():
    releases = [
        release("watcher-0.1.0"),
        release("watcher-v0.2.0", prerelease=True),
        release("watcher-v0.1.5"),
    ]
    assert select_latest(releases, channel="beta").tag == "watcher-v0.2.0"
    assert select_latest(releases, channel="stable").tag == "watcher-v0.1.5"


def test_select_latest_respecte_le_canal():
    releases = [
        release("watcher-v0.6.0", prerelease=False),
        release("watcher-v0.7.0-beta.1", prerelease=True),
        release("watcher-v0.7.0-beta.2", prerelease=True),
    ]
    stable = select_latest(releases, channel="stable")
    beta = select_latest(releases, channel="beta")
    assert stable is not None and stable.tag == "watcher-v0.6.0"
    assert beta is not None and beta.tag == "watcher-v0.7.0-beta.2"


def test_check_for_update():
    releases = [release("watcher-0.1.0"), release("watcher-v0.2.0")]
    update = check_for_update("0.1.0", releases=releases)
    assert update is not None
    assert update.version == Version(0, 2, 0)


def test_check_for_update_deja_a_jour():
    releases = [release("watcher-0.1.0")]
    assert check_for_update("0.1.0", releases=releases) is None
    assert check_for_update("0.2.0", releases=releases) is None


def test_check_for_update_refuse_les_prereleases():
    releases = [release("watcher-0.1.0"), release("watcher-v0.2.0", prerelease=True)]
    assert check_for_update("0.1.0", channel="stable", releases=releases) is None


def test_check_for_update_accepte_les_prereleases_en_beta():
    releases = [
        release("watcher-v0.1.0"),
        release("watcher-v0.2.0-beta.1", prerelease=True),
    ]
    update = check_for_update("0.1.0", channel="beta", releases=releases)
    assert update is not None
    assert update.version_text == "0.2.0-beta.1"


def test_une_beta_du_meme_numero_est_proposee_avant_la_stable():
    releases = [release("watcher-v0.6.0-beta.1", prerelease=True)]
    beta = check_for_update("0.5.0", channel="beta", releases=releases)
    assert beta is not None and beta.tag == "watcher-v0.6.0-beta.1"
    assert check_for_update("0.5.0", channel="stable", releases=releases) is None
    assert check_for_update("0.6.0", channel="beta", releases=releases) is None


def _asset(name: str, url: str = "u", **extra: object) -> dict[str, object]:
    return {"name": name, "browser_download_url": url, **extra}


def test_parse_release_collecte_les_assets():
    setup = _asset("CheckMate-Setup-0.4.2.exe", size=42)
    sums = _asset("SHA256SUMS.txt")
    parsed = parse_release({"tag_name": "watcher-v0.4.2", "assets": [setup, sums]})
    assert parsed is not None
    assert len(parsed.assets) == 2
    found = parsed.find_asset("CheckMate-Setup-", ".exe")
    assert found is not None
    assert found.size == 42
    assert parsed.asset("SHA256SUMS.txt") is not None


def test_platform_asset():
    parsed = release("watcher-v0.4.2", prerelease=True, assets=_platform_assets())
    assert platform_asset(parsed, "win32").name.endswith(".exe")
    assert platform_asset(parsed, "linux").name.endswith(".tar.gz")
    assert platform_asset(parsed, "darwin") is None


def test_parse_checksums():
    from checkmate_watcher.updates import parse_checksums

    digest = "a" * 64
    text = (
        f"{digest}  CheckMate-linux-0.4.2.tar.gz\nb"
        + "b" * 63
        + " *autre.zip\nignore\n"
    )
    parsed = parse_checksums(text)
    assert parsed["CheckMate-linux-0.4.2.tar.gz"] == digest
    assert parsed["autre.zip"] == "b" * 64


def test_verify_checksum(tmp_path):
    import hashlib

    from checkmate_watcher.updates import UpdateError, verify_checksum

    file = tmp_path / "paquet.bin"
    file.write_bytes(b"contenu")
    digest = hashlib.sha256(b"contenu").hexdigest()
    verify_checksum(file, {"paquet.bin": digest})
    with pytest.raises(UpdateError):
        verify_checksum(file, {"paquet.bin": "0" * 64})
    with pytest.raises(UpdateError):
        verify_checksum(file, {})


def test_download_update(tmp_path):
    from checkmate_watcher.updates import download_update

    paquet = _paquet(tmp_path)
    sommes = _sommes(tmp_path)
    assets = tuple(Asset(f.name, f.as_uri()) for f in (paquet, sommes))
    release_obj = release("watcher-v0.4.2", prerelease=True, assets=assets)
    archive = download_update(release_obj, tmp_path / "download", platform="linux")
    assert archive.name == "CheckMate-linux-0.4.2.tar.gz"
    assert archive.read_bytes() == b"archive"


def test_download_update_somme_invalide(tmp_path):
    from checkmate_watcher.updates import UpdateError, download_update

    paquet, sommes = _paquet(tmp_path), _sommes(tmp_path, b"autre")
    assets = tuple(Asset(f.name, f.as_uri()) for f in (paquet, sommes))
    release_obj = release("watcher-v0.4.2", prerelease=True, assets=assets)
    with pytest.raises(UpdateError):
        download_update(release_obj, tmp_path / "download", platform="linux")
