"""Point d'entree utilise par PyInstaller."""

import multiprocessing

from checkmate_watcher.cli import main

if __name__ == "__main__":
    multiprocessing.freeze_support()
    raise SystemExit(main())
