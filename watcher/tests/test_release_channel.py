from __future__ import annotations

import pytest

from checkmate_watcher.release_channel import channel_for_tag, main


def test_tag_beta():
    channel = channel_for_tag("watcher-v0.6.0-beta.1")
    assert channel.name == "beta"
    assert channel.expected_branch == "beta"
    assert channel.prerelease is True


def test_tag_stable():
    channel = channel_for_tag("watcher-v0.6.0")
    assert channel.name == "stable"
    assert channel.expected_branch == "main"
    assert channel.prerelease is False


def test_tag_hors_prefixe_refuse():
    with pytest.raises(ValueError):
        channel_for_tag("v0.6.0")


def test_tag_illisible_refuse():
    with pytest.raises(ValueError):
        channel_for_tag("watcher-")


def test_suffixe_inconnu_refuse():
    with pytest.raises(ValueError):
        channel_for_tag("watcher-v0.6.0-rc.1")


def _sortie_pour_tag(capsys, tag):
    assert main([tag]) == 0
    return capsys.readouterr().out


def _assert_lignes(out, channel, branch, version, prerelease):
    assert f"channel={channel}" in out
    assert f"branch={branch}" in out
    assert f"version={version}" in out
    assert f"prerelease={prerelease}" in out


def test_sortie_github(capsys):
    tag = "watcher-v0.7.0-beta.2"
    _assert_lignes(_sortie_pour_tag(capsys, tag), "beta", "beta", "0.7.0", "true")
    tag = "watcher-v0.7.0"
    _assert_lignes(_sortie_pour_tag(capsys, tag), "stable", "main", "0.7.0", "false")


def test_tag_invalide_retourne_une_erreur(capsys):
    assert main(["pas-un-tag"]) == 1
    assert "erreur" in capsys.readouterr().err
    assert main([]) == 2
