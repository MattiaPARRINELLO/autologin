# Privacy Policy

CheckMate runs entirely on the user's computer. There is no CheckMate server,
no account, no telemetry, and no analytics.

## Data stored locally

- CESAR username, in the configuration file
- CESAR password, in the operating system keychain when available, otherwise in
  a private local file
- Signature points, in `signature.json`
- CESAR session cookies, in a local Chromium profile
- Class schedule and processed attendance state
- Rotating logs, without passwords

## Network

The only service contacted is the CESAR Emineo instance configured by the user.
No data is sent to the maintainers or to any third party.

## Deletion

Uninstalling the application leaves configuration and signature in place. Users
can delete them from:

- Windows: `%LOCALAPPDATA%\checkmate-watcher`
- Linux: `~/.config/checkmate-watcher` and `~/.local/share/checkmate-watcher`

## Contact

Open an issue on the GitHub repository. Never attach a password or the Chromium
profile folder.
