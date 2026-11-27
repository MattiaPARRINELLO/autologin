"""Verifie que les installeurs embarquent la coquille native `checkmate-ui`."""

from pathlib import Path

PACKAGING = Path(__file__).resolve().parents[1] / "packaging"


def test_le_spec_pyinstaller_embarque_checkmate_ui():
    spec = (PACKAGING / "checkmate.spec").read_text(encoding="utf-8")

    assert 'native_name = "checkmate-ui.exe"' in spec
    assert "native_binary.is_file()" in spec
    assert "native_binaries" in spec
    assert "cargo build --release" in spec


def test_l_archive_linux_copie_le_binaire_dans_le_venv():
    script = (PACKAGING / "build-linux.sh").read_text(encoding="utf-8")

    assert "rust/target/release/checkmate-ui" in script
    assert ".venv/bin/checkmate-ui" in script
