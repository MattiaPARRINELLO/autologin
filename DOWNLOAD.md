# Download CheckMate

CheckMate is a local desktop app for students using CESAR Emineo. It watches
your class windows, detects when a teacher opens attendance, and signs after
your confirmation.

## Windows

- Windows 10 or 11
- Microsoft Edge or Google Chrome
- Download the current desktop pre-release:
  [CheckMate desktop 0.3.0](https://github.com/MattiaPARRINELLO/autologin/releases/tag/watcher-v0.3.0)
- Run the installer, then follow the onboarding

## Linux

- systemd
- [uv](https://docs.astral.sh/uv/)
- Download `CheckMate-linux-0.3.0.tar.gz` from the same release
- Extract it and run `./install.sh`

## Code signing

Windows builds are code-signed by the
[SignPath Foundation](https://signpath.org/). The current `watcher-v0.3.0`
pre-release was built before signing was enabled and is unsigned.
