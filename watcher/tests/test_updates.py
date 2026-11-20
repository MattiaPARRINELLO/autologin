from __future__ import annotations

from checkmate_watcher.updates import (
    Release,
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
    assert parse_version("watcher-v1.2.3") == (1, 2, 3)
    assert parse_version("watcher-0.1.0") == (0, 1, 0)
    assert parse_version("v1.6.0") == (1, 6, 0)
    assert parse_version("pas une version") is None


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


def test_parse_release_ignore_les_tags_de_l_extension():
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
    assert parsed.version == (0, 2, 0)
    assert parsed.prerelease is True


def test_select_latest_avec_prereleases():
    releases = [
        release("watcher-0.1.0"),
        release("watcher-v0.2.0", prerelease=True),
        release("watcher-v0.1.5"),
    ]
    assert select_latest(releases).tag == "watcher-v0.2.0"
    assert select_latest(releases, include_prerelease=False).tag == "watcher-v0.1.5"


def test_check_for_update():
    releases = [release("watcher-0.1.0"), release("watcher-v0.2.0")]
    update = check_for_update("0.1.0", releases=releases)
    assert update is not None
    assert update.version == (0, 2, 0)


def test_check_for_update_deja_a_jour():
    releases = [release("watcher-0.1.0")]
    assert check_for_update("0.1.0", releases=releases) is None
    assert check_for_update("0.2.0", releases=releases) is None


def test_check_for_update_refuse_les_prereleases():
    releases = [release("watcher-0.1.0"), release("watcher-v0.2.0", prerelease=True)]
    assert (
        check_for_update("0.1.0", include_prerelease=False, releases=releases) is None
    )
