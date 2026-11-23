# Contributing to CheckMate

This is the English summary of [CONTRIBUTING.md](CONTRIBUTING.md). If the two
disagree, the French guide is authoritative.

By participating, you agree to the [Code of Conduct](CODE_OF_CONDUCT.md). For a
security issue, do not open a public issue: follow the
[security policy](SECURITY.md).

## Contribution licence

CheckMate is released under the MIT licence (see [LICENSE](LICENSE)). By opening
a pull request, you agree that your contribution is published under that same
MIT licence.

No DCO or CLA is required. By submitting a contribution, you simply certify that
you wrote it or have the right to submit it.

## Scope and status

- `watcher/`: the Python watcher, CLI and local dashboard. Actively maintained.
- `emulator/`: the CESAR test server. Maintained as a testing tool.
- Extension at the repository root (`manifest.json`, `background.js`,
  `content.js`, `popup.*`): historical Chrome extension, frozen. No new features.
- `ui/`: experimental Rust/egui dashboard. Not maintained for release; changes
  are welcome but it is not part of the shipped product.

Pull requests must stay within this scope. Problems with the CESAR website itself
are out of scope.

## Development environment

Requirements:

- Python 3.11 or newer;
- [uv](https://docs.astral.sh/uv/getting-started/installation/);
- Chromium, Google Chrome or Microsoft Edge for browser tests;
- on Windows, Inno Setup only to build the installer.

Install and check:

```bash
cd watcher
uv sync
uv run checkmate-watcher --version
uvx ruff check src tests
uvx ruff format --check src tests
uv run pytest -q
```

To iterate on a real page without an attendance slot,
`./scripts/dev-scenario.sh path/to/capture` serves a capture and runs a full
watcher cycle: see [Tester avec une capture CESAR](emulator/docs/tester-sans-cesar.md).

End-to-end tests (`tests/test_emulator_e2e.py`) are skipped by default. They
need Chromium and start the CESAR emulator themselves:

```bash
cd watcher
uv run playwright install chromium   # or install a system Chromium/Chrome/Edge
CHECKMATE_E2E=1 uv run pytest -q tests/test_emulator_e2e.py
```

CI does not run the e2e tests.

## Capturing a real CESAR session

Bugs that only show up in real conditions (a signature reduced to a single
point, clicks interrupting the stroke, Windows animations) are reproduced from
captures of real pages. This is a maintainer task: it needs a CESAR account and
an attendance slot whose presence does not matter.

```bash
cd watcher
uv run python -m checkmate_watcher.capture \
  --base-url https://cesar.example.fr \
  --output captures/2026-11-20 \
  --mask ".student-name"
```

Five steps are captured, each confirmed with Enter: login page, dashboard with
the attendance button, signature popup opened, confirmation message shown, then
the dashboard after closing the message. The script stores the page HTML, static
resources in `assets/`, a `network.har` file and a Playwright `trace.zip`.

In the real flow, the page without the button is the same before attendance is
launched and after signing. It is therefore used as the default (closed) state
and as the signed state; the page with the button is the "attendance open" state.
`pages/signature.html` and `pages/confirmation.html` are kept as reference for
writing the `harness.js`, but they are not served as routes.

Storage rules:

- `captures/` is git-ignored: a raw capture is never committed;
- never capture or commit a page showing other students' attendance unmasked,
  use `--mask`;
- sanitizing runs right after capture: asset references rewritten to
  `/assets/`, the login form action rewritten to `/connexion`, cookies and
  tokens removed from the HAR, response bodies dropped;
- only the sanitized `scenario.json`, `pages/`, `assets/` and `harness.js` may be
  versioned, and only as a test fixture;
- captures are dated: CESAR can change without notice, capture again when the
  default selectors stop matching.

Replay with `python emulator/server.py --scenario captures/<date>`.

The generated `harness.js` is a template: on a real CESAR, adapt it to open the
modal, draw and post to `/api/signature`.

## Workflow

1. Create a branch from `main`: `feat/...`, `fix/...`, `docs/...`, `ci/...` or
   `chore/...`.
2. Develop and verify locally.
3. Push to your fork and open a pull request against `main`.
4. Fill in the PR template: describe the change and list the checks you ran.
5. Address review comments and failing checks. The maintainer merges after
   review.

A feature is first merged into `beta`, then stabilised into `main`. Never push
directly to `main` and never rewrite its history.

## Commit conventions

Each commit is one coherent unit and starts with a prefix: `feat:`, `fix:`,
`docs:`, `style:`, `refactor:`, `perf:`, `test:`, `build:`, `ci:`, `chore:` or
`revert:`.

Pull request titles follow the same format, for example
`feat: add the beta channel to the dashboard`. The `PR title` workflow rejects
non-conforming titles.

## What a pull request should contain

- a description of the problem and the solution;
- the commands you ran and their result;
- documentation updates when behaviour changes;
- tests for any new behaviour;
- no secret, personal data or real identifier.

## AI disclosure

If an issue, pull request or comment is written by an AI assistant, say so
explicitly. State what a human actually ran, tested or verified. Never imply
human validation that did not happen.

## Release channels and tags

- `main`: stable releases, used by the `stable` channel.
- `beta`: upcoming releases, published as prereleases, used by the `beta`
  channel.

Release tags use the `watcher-v` prefix:

- beta: `watcher-v0.6.0-beta.1`, then `watcher-v0.6.0-beta.2`
- stable: `watcher-v0.6.0`

Never create a tag or release without human validation.
