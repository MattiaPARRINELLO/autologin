"""Page locale du tableau de bord CheckMate."""

STATUS_HTML = """<!doctype html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>CheckMate - Statut</title>
<style>
  :root {
    color-scheme: light;
    --paper: #f7f4ee;
    --card: #fdfbf7;
    --raised: #efe9df;
    --ink: #1f1b16;
    --ink-2: #5e554a;
    --muted: #7b7266;
    --line: rgba(31, 27, 22, 0.12);
    --accent: #2f6f4f;
    --accent-soft: #e3ece5;
    --warn: #9a6b2f;
    --err: #b3261e;
    --ease: cubic-bezier(0.22, 1, 0.36, 1);
  }
  * { box-sizing: border-box; }
  body {
    margin: 0;
    min-height: 100vh;
    background: var(--paper);
    color: var(--ink);
    font-family: ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto,
    sans-serif;
    font-size: 15px;
    line-height: 1.5;
  }
  .shell { max-width: 1040px; margin: 0 auto; padding: 32px 24px 48px; }
  header { display: flex; align-items: center; justify-content: space-between;
  gap: 16px; margin-bottom: 24px; }
  .brand { display: flex; align-items: center; gap: 12px; }
  .mark { width: 32px; height: 32px; color: var(--accent); }
  .wordmark { font-size: 17px; font-weight: 600; }
  .tagline { font-size: 12px; color: var(--muted); }
  .meta { font-family: ui-monospace, "SFMono-Regular", "Cascadia Mono",
  monospace; font-size: 12px; color: var(--muted); text-align: right; }
  .panel {
    background: var(--card);
    border: 1px solid var(--line);
    border-radius: 16px;
    padding: 32px;
    box-shadow: 0 1px 2px rgba(31, 27, 22, 0.04);
  }
  .status-head { display: flex; gap: 16px; align-items: flex-start; }
  .state-dot {
    width: 12px; height: 12px; border-radius: 50%;
    background: var(--accent); flex: none; margin-top: 9px;
  }
  .state-dot.outside { background: var(--warn); }
  .state-dot.signed { background: var(--ink); }
  .state-dot.error { background: var(--err); }
  .kicker { margin: 0 0 4px; font-family: ui-monospace, "SFMono-Regular",
  "Cascadia Mono", monospace; font-size: 12px; color: var(--muted); }
  h1 { margin: 0; font-size: 32px; line-height: 1.15; font-weight: 500;
  letter-spacing: -0.01em; }
  .detail { margin: 8px 0 0; color: var(--ink-2); max-width: 62ch; }
  .restart {
    margin-top: 20px; padding: 12px 16px; border-radius: 0 8px 8px 0;
    border-left: 3px solid var(--warn); background: #f3ead9; color:
    var(--ink-2);
    font-size: 13px;
  }
  .state-dot.blocked { background: var(--err); }
  .blocked {
    margin-top: 20px; padding: 14px 16px; border-radius: 12px;
    border: 1px solid rgba(179, 38, 30, 0.35); background: #f8e7e5;
    color: var(--ink);
  }
  .blocked strong { display: block; margin-bottom: 4px; color: var(--err); }
  .blocked span { font-size: 13px; color: var(--ink-2); }
  .migration {
    margin-top: 20px; padding: 14px 16px; border-radius: 12px;
    border: 1px solid rgba(154, 107, 47, 0.35); background: #f3ead9;
    color: var(--ink);
  }
  .migration strong { display: block; margin-bottom: 4px; color: var(--warn); }
  .migration span { font-size: 13px; color: var(--ink-2); }
  .schedule { margin-top: 28px; padding-top: 20px; border-top: 1px solid
  var(--line); }
  .schedule-label { margin: 0 0 8px; font-size: 12px; color: var(--muted); }
  .slots { display: flex; gap: 10px; flex-wrap: wrap; }
  .slot {
    display: flex; align-items: baseline; gap: 10px;
    padding: 8px 12px; border: 1px solid var(--line); border-radius: 9px;
    font-family: ui-monospace, "SFMono-Regular", "Cascadia Mono", monospace;
    font-size: 13px; color: var(--ink-2); font-variant-numeric: tabular-nums;
  }
  .slot.active { border-color: var(--accent); background: var(--accent-soft);
  color: var(--ink); }
  .slot .state { font-family: inherit; font-size: 11px; color: var(--muted); }
  .grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px;
  margin-top: 28px; }
  .stat { border-top: 1px solid var(--line); padding-top: 12px; }
  .stat span { display: block; font-size: 12px; color: var(--muted); }
  .stat strong { display: block; margin-top: 6px; font-family: ui-monospace,
  "SFMono-Regular", "Cascadia Mono", monospace; font-size: 24px; font-weight:
  500; font-variant-numeric: tabular-nums; }
  .events { margin-top: 24px; border-top: 1px solid var(--line); }
  .event-row { display: flex; justify-content: space-between; gap: 16px;
  padding: 10px 0; border-bottom: 1px solid var(--line); font-size: 13px;
  color: var(--ink-2); }
  .event-row strong { font-family: ui-monospace, "SFMono-Regular", "Cascadia
  Mono", monospace; font-weight: 400; color: var(--ink); text-align: right; }
  .actions { display: flex; gap: 10px; flex-wrap: wrap; margin-top: 28px; }
  button { font: inherit; font-size: 14px; font-weight: 500; height: 42px;
  padding: 0 16px; border-radius: 9px; border: 1px solid transparent; cursor:
  pointer; transition: background-color 150ms var(--ease), border-color 150ms
  var(--ease); }
  button:disabled { opacity: 0.45; cursor: not-allowed; }
  button:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px;
  }
  .primary { background: var(--accent); color: var(--paper); }
  .primary:hover { background: #275c41; }
  .secondary { background: var(--card); border-color: var(--line); color:
  var(--ink); }
  .secondary:hover { background: var(--raised); }
  .ghost { background: transparent; color: var(--muted); }
  .ghost:hover { background: var(--raised); color: var(--ink); }
  .message { min-height: 20px; margin-top: 16px; font-size: 13px; color:
  var(--ink-2); }
  .message:not(:empty)::before { content: ""; display: inline-block; width:
  6px; height: 6px; border-radius: 50%; background: currentColor; margin-right:
  8px; vertical-align: 1px; }
  .message.ok { color: var(--accent); }
  .message.err { color: var(--err); }
  .channel { margin-top: 24px; padding-top: 18px; border-top: 1px solid
  var(--line); }
  .channel-toggle { display: flex; align-items: center; gap: 10px; font-size:
  14px; cursor: pointer; }
  .channel-toggle input { width: 18px; height: 18px; accent-color:
  var(--accent); }
  .channel-warning { margin: 8px 0 0 28px; font-size: 12px; color: var(--warn);
  max-width: 62ch; }
  footer { display: flex; justify-content: space-between; gap: 16px;
  margin-top: 16px; font-size: 12px; color: var(--muted); }
  @media (max-width: 720px) {
    .shell { padding: 20px 14px 32px; }
    .panel { padding: 22px; }
    h1 { font-size: 26px; }
    .grid { grid-template-columns: repeat(2, 1fr); }
    .actions button { flex: 1 1 100%; }
    footer { flex-direction: column; }
  }
</style>
</head>
<body>
<div class="shell">
  <header>
    <div class="brand">
      <svg class="mark" viewBox="0 0 32 32" fill="none" aria-hidden="true">
        <rect x="3.5" y="5.5" width="25" height="21" rx="5"
        stroke="currentColor" stroke-width="1.8"/>
        <path d="M3.5 11.5h25" stroke="currentColor" stroke-width="1.8"/>
        <rect x="8" y="15" width="7" height="3" rx="1.5" fill="currentColor"/>
        <rect x="8" y="21" width="10" height="3" rx="1.5" fill="currentColor"
        opacity="0.4"/>
        <path d="M19.5 18.5l2.6 2.6 4.4-5.2" stroke="currentColor"
        stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
      </svg>
      <div>
        <div class="wordmark">CheckMate</div>
        <div class="tagline">Tableau de bord local</div>
      </div>
    </div>
    <div class="meta" id="version">Version -</div>
  </header>

  <main class="panel">
    <div class="status-head">
      <span class="state-dot" id="stateDot"></span>
      <div>
        <p class="kicker" id="stateKicker">ETAT</p>
        <h1 id="stateLabel">Connexion au service...</h1>
        <p class="detail" id="stateDetail">Lecture de l'état local.</p>
      </div>
    </div>

    <div class="restart" id="restartBanner" hidden>
      La configuration a changé depuis le démarrage. Quitte CheckMate puis
      relance-le
      depuis le menu Démarrer pour appliquer les nouveaux réglages.
    </div>

    <div class="blocked" id="blockedBanner" hidden>
      <strong>Mise à jour obligatoire</strong>
      <span id="blockedDetail"></span>
    </div>

    <div class="migration" id="migrationBanner" hidden>
      <strong>Migration intermédiaire requise</strong>
      <span id="migrationDetail"></span>
    </div>

    <section class="schedule">
      <p class="schedule-label">Créneaux surveillés</p>
      <div class="slots" id="slots"></div>
    </section>

    <div class="grid">
      <div class="stat"><span>Démarrages</span><strong
      id="statStarts">-</strong></div>
      <div class="stat"><span>Détections</span><strong
      id="statDetections">-</strong></div>
      <div class="stat"><span>Signatures</span><strong
      id="statSigned">-</strong></div>
      <div class="stat"><span>Erreurs</span><strong
      id="statErrors">-</strong></div>
    </div>

    <div class="events">
      <div class="event-row"><span>Démarré le</span><strong
      id="startedAt">-</strong></div>
      <div class="event-row"><span>Dernière détection</span><strong
      id="lastDetection">-</strong></div>
      <div class="event-row"><span>Dernière signature</span><strong
      id="lastSigned">-</strong></div>
      <div class="event-row"><span>Dernière erreur</span><strong
      id="lastError">-</strong></div>
    </div>

    <div class="actions">
      <button type="button" class="primary"
      data-action="configure">Reconfigurer</button>
      <button type="button" class="secondary"
      data-action="test-notification">Tester la notification</button>
      <button type="button" class="secondary"
      data-action="check-update">Vérifier les mises à jour</button>
      <button type="button" class="primary" data-action="install-update"
      id="updateButton" hidden>Installer la mise à jour</button>
      <button type="button" class="secondary" data-action="open-logs">Ouvrir
      les logs</button>
      <button type="button" class="ghost" data-action="quit">Quitter
      CheckMate</button>
    </div>
    <section class="channel">
      <label class="channel-toggle">
        <input type="checkbox" id="betaChannel">
        <span>Recevoir les mises à jour beta</span>
      </label>
      <p class="channel-warning">
        Les betas sortent souvent. La stabilité du projet n'est pas garantie,
        même si elle progresse avant la version 1.0.
      </p>
    </section>
    <div class="message" id="message" aria-live="polite"></div>
  </main>

  <footer>
    <span>CheckMate __VERSION__</span>
    <span>Local uniquement, aucun serveur.</span>
  </footer>
</div>

<script>
const TOKEN = "__TOKEN__";
let timer = null;
let stopped = false;

async function api(path, body) {
  const options = {
    method: body ? "POST" : "GET",
    headers: { "X-CheckMate-Token": TOKEN },
  };
  if (body) {
    options.headers["Content-Type"] = "application/json";
    options.body = JSON.stringify(body);
  }
  const response = await fetch(path, options);
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(data.error || ("erreur " + response.status));
  }
  return data;
}

function formatDate(value) {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "-";
  return date.toLocaleString("fr-FR", {
    weekday: "short", day: "2-digit", month: "2-digit",
    hour: "2-digit", minute: "2-digit"
  });
}

function setMessage(text, kind) {
  const element = document.getElementById("message");
  element.textContent = text || "";
  element.className = "message" + (kind ? " " + kind : "");
}

function renderBlocked(blocked, migration) {
  document.getElementById("blockedBanner").hidden = !blocked;
  if (!blocked) return;
  const first = migration ? migration.version : blocked.version;
  const reason = migration ? migration.reason : blocked.reason;
  let text = "Installe " + first + " pour continuer. Raison : " + reason + ".";
  if (migration) text += " Ensuite, " + blocked.version + " sera proposée.";
  document.getElementById("blockedDetail").textContent = text;
  const button = document.getElementById("updateButton");
  button.textContent = "Installer " + first;
  button.hidden = false;
}

function renderMigration(migration, blocked) {
  document.getElementById("migrationBanner").hidden = !migration;
  if (!migration) return;
  document.getElementById("migrationDetail").textContent =
    "Installe " + migration.version +
    " avant les versions suivantes. Raison : " +
    migration.reason + ".";
  if (blocked) return;
  const button = document.getElementById("updateButton");
  button.textContent = "Installer " + migration.version;
  button.hidden = false;
}

function render(snapshot) {
  const dot = document.getElementById("stateDot");
  dot.className = "state-dot " + snapshot.mode;
  const stateKicker = document.getElementById("stateKicker");
  stateKicker.textContent = snapshot.schedule.enabled
    ? "Surveillance"
    : "Surveillance continue";
  document.getElementById("stateLabel").textContent = snapshot.label;

  let detail = "";
  if (snapshot.mode === "error" && snapshot.last_error_message) {
    detail = snapshot.last_error_message;
    if (snapshot.last_error_at) {
      detail += " (" + formatDate(snapshot.last_error_at) + ")";
    }
    detail += " ";
  }
  if (snapshot.window) detail += "Créneau " + snapshot.window + ". ";
  if (snapshot.next_window) {
    detail += "Prochaine ouverture " +
      formatDate(snapshot.next_window) + ".";
  }
  if (!snapshot.schedule.enabled) {
    detail = "Le planning est désactivé, " +
      "la surveillance est continue.";
  }
  document.getElementById("stateDetail").textContent = detail;

  document.getElementById("restartBanner").hidden = !snapshot.restart_required;
  renderBlocked(snapshot.blocked, snapshot.migration);
  renderMigration(snapshot.migration, snapshot.blocked);
  document.getElementById("version").textContent =
    "Version " + snapshot.version + " - canal " + snapshot.channel +
    " - build " + snapshot.build;
  document.getElementById("betaChannel").checked = snapshot.channel === "beta";

  const slots = document.getElementById("slots");
  slots.innerHTML = "";
  snapshot.schedule.windows.forEach((window) => {
    const element = document.createElement("div");
    element.className = "slot" + (snapshot.window === window ? " active" : "");
    const time = document.createElement("span");
    time.textContent = window;
    element.appendChild(time);
    if (snapshot.window === window) {
      const state = document.createElement("span");
      state.className = "state";
      state.textContent = snapshot.mode === "signed" ? "signé" : "en cours";
      element.appendChild(state);
    }
    slots.appendChild(element);
  });

  document.getElementById("statStarts").textContent = snapshot.counters.starts;
  document.getElementById("statDetections").textContent =
    snapshot.counters.detections;
  document.getElementById("statSigned").textContent = snapshot.counters.signed;
  document.getElementById("statErrors").textContent = snapshot.counters.errors;
  document.getElementById("startedAt").textContent =
    formatDate(snapshot.started_at);
  document.getElementById("lastDetection").textContent =
    formatDate(snapshot.last_detection_at);
  document.getElementById("lastSigned").textContent =
    formatDate(snapshot.last_signed_at);
  document.getElementById("lastError").textContent =
    formatDate(snapshot.last_error_at);
}

async function refresh() {
  if (stopped) return;
  try {
    const snapshot = await api("/api/status");
    render(snapshot);
  } catch (error) {
    if (stopped) return;
    document.getElementById("stateDot").className = "state-dot error";
    document.getElementById("stateLabel").textContent = "Service arrêté";
    document.getElementById("stateDetail").textContent =
      "CheckMate ne repond plus. Relance-le depuis le menu Démarrer.";
    document.querySelectorAll("[data-action]").forEach((button) => {
      button.disabled = button.dataset.action !== "configure";
    });
  }
}

async function runAction(action) {
  if (action === "quit") {
    if (!window.confirm(
      "Quitter CheckMate ? La surveillance sera arretee."
    )) return;
  }
  if (action === "install-update" && !window.confirm(
    "Installer la mise a jour ? CheckMate va s'arreter puis redemarrer."
  )) return;
  setMessage("En cours...");
  try {
    const result = await api("/api/action", { action });
    setMessage(result.message || "Fait.", "ok");
    if (action === "check-update" && result.available) {
      const button = document.getElementById("updateButton");
      button.textContent = "Installer " + result.version;
      button.hidden = false;
    }
    if (action === "install-update") {
      stopped = true;
      clearInterval(timer);
      document.querySelectorAll("[data-action]").forEach((button) => {
        button.disabled = true;
      });
    } else if (action === "quit") {
      stopped = true;
      clearInterval(timer);
      document.getElementById("stateDot").className = "state-dot outside";
      document.getElementById("stateLabel").textContent = "CheckMate arrêté";
      document.getElementById("stateDetail").textContent =
        "Tu peux fermer cette page. Relance CheckMate " +
        "depuis le menu Démarrer.";
      document.querySelectorAll("[data-action]").forEach((button) => {
        button.disabled = true;
      });
    } else {
      refresh();
    }
  } catch (error) {
    setMessage(error.message, "err");
  }
}

document.querySelectorAll("[data-action]").forEach((button) => {
  button.addEventListener("click", () => runAction(button.dataset.action));
});

document.getElementById("betaChannel")
  .addEventListener("change", async (event) => {
  const enabled = event.target.checked;
  if (!enabled && !window.confirm(
    "Revenir au canal stable ? Tu restes sur cette version beta, " +
    "mais les prochaines betas ne seront plus proposees."
  )) {
    event.target.checked = true;
    return;
  }
  if (enabled && !window.confirm(
    "Activer le canal beta ? Les mises a jour arrivent souvent " +
    "et la stabilite n'est pas garantie."
  )) {
    event.target.checked = false;
    return;
  }
  const channel = enabled ? "beta" : "stable";
  try {
    const result = await api("/api/action", {
      action: "set-channel",
      channel,
    });
    setMessage(result.message || "Canal mis a jour.", "ok");
    refresh();
  } catch (error) {
    event.target.checked = !enabled;
    setMessage(error.message, "err");
  }
});

refresh();
timer = setInterval(refresh, 3000);
</script>
</body>
</html>
"""
