from __future__ import annotations

import pytest

from checkmate_watcher.updates import (
    Release,
    Version,
    check_for_update,
    parse_release,
    parse_version,
    select_latest,
)


def release(tag: str, *, prerelease: bool = False) -> Release:
    version = parse_version(tag)
    assert version is not None
    return Release(
        tag=tag,
        version=version,
        url=f"https://example.com/{tag}",
        name=tag,
        prerelease=prerelease,
    )


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
    assert beta1 < beta2 < stable
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


def test_parse_release_ignore_les_tags_legacy():
    assert parse_release({"tag_name": "v1.6.0"}) is None
    parsed = parse_release(
        {
            "tag_name": "watcher-v0.2.0",
            "html_url": "https://example.com/release",
            "name": "CheckMate 0.2.0",
            "prerelease": True,
        }
    )
    assert parsed is not None
    assert parsed.version == Version(0, 2, 0)
    assert parsed.prerelease is True


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


def test_parse_release_collecte_les_assets():
    parsed = parse_release(
        {
            "tag_name": "watcher-v0.4.2",
            "assets": [
                {
                    "name": "CheckMate-Setup-0.4.2.exe",
                    "browser_download_url": "https://example.com/setup.exe",
                    "size": 42,
                },
                {"name": "SHA256SUMS.txt", "browser_download_url": "u"},
            ],
        }
    )
    assert parsed is not None
    assert len(parsed.assets) == 2
    setup = parsed.find_asset("CheckMate-Setup-", ".exe")
    assert setup is not None
    assert setup.size == 42
    assert parsed.asset("SHA256SUMS.txt") is not None


def test_platform_asset():
    from checkmate_watcher.updates import Asset, platform_asset

    assets = (
        Asset("CheckMate-Setup-0.4.2.exe", "u"),
        Asset("CheckMate-linux-0.4.2.tar.gz", "v"),
        Asset("SHA256SUMS.txt", "w"),
    )
    parsed = Release(
        tag="watcher-v0.4.2",
        version=Version(0, 4, 2),
        url="",
        name="",
        prerelease=True,
        assets=assets,
    )
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
    import hashlib

    from checkmate_watcher.updates import Asset, download_update

    payload = tmp_path / "CheckMate-linux-0.4.2.tar.gz"
    payload.write_bytes(b"archive")
    digest = hashlib.sha256(b"archive").hexdigest()
    sums = tmp_path / "SHA256SUMS.txt"
    sums.write_text(f"{digest}  CheckMate-linux-0.4.2.tar.gz\n", encoding="utf-8")
    release = Release(
        tag="watcher-v0.4.2",
        version=Version(0, 4, 2),
        url="",
        name="",
        prerelease=True,
        assets=(
            Asset("CheckMate-linux-0.4.2.tar.gz", payload.as_uri()),
            Asset("SHA256SUMS.txt", sums.as_uri()),
        ),
    )
    target_dir = tmp_path / "download"
    archive = download_update(release, target_dir, platform="linux")
    assert archive.name == "CheckMate-linux-0.4.2.tar.gz"
    assert archive.read_bytes() == b"archive"


def test_download_update_somme_invalide(tmp_path):
    import hashlib

    from checkmate_watcher.updates import Asset, UpdateError, download_update

    payload = tmp_path / "CheckMate-linux-0.4.2.tar.gz"
    payload.write_bytes(b"archive")
    sums = tmp_path / "SHA256SUMS.txt"
    sums.write_text(
        hashlib.sha256(b"autre").hexdigest() + "  CheckMate-linux-0.4.2.tar.gz\n"
    )
    release = Release(
        tag="watcher-v0.4.2",
        version=Version(0, 4, 2),
        url="",
        name="",
        prerelease=True,
        assets=(
            Asset("CheckMate-linux-0.4.2.tar.gz", payload.as_uri()),
            Asset("SHA256SUMS.txt", sums.as_uri()),
        ),
    )
    with pytest.raises(UpdateError):
        download_update(release, tmp_path / "download", platform="linux")
