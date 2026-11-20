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


def test_sortie_github(capsys):
    assert main(["watcher-v0.7.0-beta.2"]) == 0
    out = capsys.readouterr().out
    assert "channel=beta" in out
    assert "branch=beta" in out
    assert "prerelease=true" in out

    assert main(["watcher-v0.7.0"]) == 0
    out = capsys.readouterr().out
    assert "channel=stable" in out
    assert "branch=main" in out
    assert "prerelease=false" in out


def test_tag_invalide_retourne_une_erreur(capsys):
    assert main(["pas-un-tag"]) == 1
    assert "erreur" in capsys.readouterr().err
    assert main([]) == 2
