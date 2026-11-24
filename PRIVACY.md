# Privacy Policy

CheckMate runs entirely on the user's computer. There is no CheckMate account,
no advertising, and no tracking of what users do on CESAR.

## Anonymous usage statistics

CheckMate sends two small events to a self-hosted counter:

- `install`, once per computer;
- `signature`, one per successful attendance signature.

Each event carries only:

- a random installation identifier (32 hexadecimal characters), generated on
  first launch and stored locally in `install-id`;
- the CheckMate version;
- the operating system family (`windows`, `linux`, `macos`, `other`);
- the event name.

The counter stores no IP address, no CESAR username, no password, no signature
content, and no class schedule. Events are used only to count installations and
signatures.

Statistics can be disabled at any time in `config.toml`:

```toml
[analytics]
enabled = false
```

or with the environment variable `CHECKMATE_ANALYTICS=0`. The installation
identifier stays on the computer; deleting the data directory removes it.

## Data stored locally

- CESAR username, in the configuration file
- CESAR password, in the operating system keychain when available, otherwise in
  a private local file
- Signature points, in `signature.json`
- CESAR session cookies, in a local Chromium profile
- Class schedule and processed attendance state
- Rotating logs, without passwords

## Network

The services contacted are:

- the CESAR Emineo instance configured by the user;
- the GitHub releases API, when update checks are enabled;
- the statistics endpoint (`main.mprnl.fr/cm-stats`), when statistics are
  enabled.

## Deletion

Uninstalling the application leaves configuration and signature in place. Users
can delete them from:

- Windows: `%LOCALAPPDATA%\checkmate-watcher`
- Linux: `~/.config/checkmate-watcher` and `~/.local/share/checkmate-watcher`

## Contact

Open an issue on the GitHub repository. Never attach a password or the Chromium
profile folder.
