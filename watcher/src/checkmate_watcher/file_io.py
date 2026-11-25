"""Ecriture atomique de fichiers JSON locaux reserves a l'utilisateur."""

from __future__ import annotations

import json
import os
from pathlib import Path


def _replace_private_json(temporary: Path, path: Path, data) -> None:
    temporary.unlink(missing_ok=True)
    descriptor = os.open(
        temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600
    )
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        json.dump(data, handle)
    temporary.replace(path)
    path.chmod(0o600)


def write_private_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    try:
        _replace_private_json(temporary, path, data)
    except OSError:
        temporary.unlink(missing_ok=True)
        raise
