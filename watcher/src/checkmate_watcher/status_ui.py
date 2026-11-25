"""Page locale du tableau de bord CheckMate."""

from .ui_shared import API_JS

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
  .event-row strong { font-family: ui-monospace, "SFMono-Regular",
  "Cascadia Mono", monospace; font-weight: 400; color: var(--ink);
  text-align: right; }
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
  var(--ink-2); white-space: pre-line; }
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
  .release-layer {
    position: fixed; inset: 0; z-index: 50; display: grid; place-items: center;
    padding: 24px; overflow: auto; background:
    radial-gradient(circle at 18% 12%, rgba(111, 61, 103, 0.78), transparent 38%),
    radial-gradient(circle at 88% 88%, rgba(150, 96, 40, 0.58), transparent 34%),
    rgba(20, 14, 19, 0.88); backdrop-filter: blur(14px);
    animation: release-layer-in 420ms var(--ease) both;
  }
  .release-layer[hidden] { display: none; }
  .release-atmosphere { position: fixed; inset: 0; overflow: hidden;
  pointer-events: none; }
  .release-orb { position: absolute; border-radius: 50%; filter: blur(70px);
  opacity: 0.5; animation: release-drift 12s ease-in-out infinite alternate; }
  .release-orb.one { width: 360px; height: 360px; left: 8%; top: 4%;
  background: #b87932; }
  .release-orb.two { width: 420px; height: 420px; right: 4%; bottom: -8%;
  background: #71466c; animation-delay: -4s; }
  .release-dialog {
    position: relative; width: min(900px, 100%); max-height: calc(100vh - 48px);
    overflow: auto; padding: 42px 46px 34px; border-radius: 32px;
    color: #241c19; background: linear-gradient(145deg, #fffaf2, #f3e9dc);
    box-shadow: 0 40px 120px rgba(0, 0, 0, 0.38), inset 0 1px #fff;
    animation: release-dialog-in 720ms cubic-bezier(0.16, 1, 0.3, 1) both;
  }
  .release-close { position: absolute; right: 18px; top: 18px; width: 38px;
  height: 38px; padding: 0; border-radius: 50%; color: #6f6157;
  background: rgba(255, 255, 255, 0.55); border-color: rgba(31, 27, 22, 0.1); }
  .release-close:hover { background: #fff; color: #241c19; }
  .release-check { width: 66px; height: 66px; margin: 0 0 24px; display: grid;
  place-items: center; border-radius: 50%; color: #fffaf2; background: #2f6f4f;
  box-shadow: 0 16px 36px rgba(47, 111, 79, 0.28);
  animation: release-check-in 620ms 120ms cubic-bezier(0.16, 1, 0.3, 1) both; }
  .release-check svg { width: 34px; height: 34px; }
  .release-check path { stroke-dasharray: 30; stroke-dashoffset: 30;
  animation: release-check-draw 480ms 380ms var(--ease) forwards; }
  .release-kicker { display: flex; align-items: center; gap: 10px; margin: 0 0 12px;
  color: #8a6236; font-size: 11px; font-weight: 800; letter-spacing: 0.15em;
  text-transform: uppercase; }
  .release-kicker::before { content: ""; width: 26px; height: 2px;
  background: #b67a32; }
  .release-dialog h2 { max-width: 690px; margin: 0; color: #241c19;
  font-size: clamp(40px, 6vw, 62px); line-height: 0.98; letter-spacing: -0.055em;
  font-weight: 650; }
  .release-summary { max-width: 670px; margin: 18px 0 28px; color: #6f6157;
  font-size: 17px; line-height: 1.55; }
  .release-metrics { display: grid; grid-template-columns: repeat(3, 1fr);
  gap: 12px; }
  .release-metric { padding: 18px 18px 16px; border: 1px solid #dac9b5;
  border-radius: 18px; background: rgba(255, 255, 255, 0.56);
  animation: release-item-in 560ms var(--ease) both;
  animation-delay: var(--delay, 0ms); }
  .release-metric strong { display: block; color: #2f6f4f; font-size: 32px;
  line-height: 1; letter-spacing: -0.045em; font-variant-numeric: tabular-nums; }
  .release-metric span { display: block; margin-top: 7px; color: #4e443c;
  font-size: 13px; font-weight: 700; }
  .release-metric small { display: block; margin-top: 5px; color: #7b6e63;
  font-size: 11px; line-height: 1.4; }
  .release-performance { margin: 18px 0 24px; padding: 18px 20px;
  border: 1px solid #dac9b5; border-radius: 18px;
  background: rgba(255, 255, 255, 0.4);
  animation: release-item-in 560ms 220ms var(--ease) both; }
  .release-performance[hidden] { display: none; }
  .release-performance-head { display: flex; align-items: flex-start;
  justify-content: space-between; gap: 18px; margin-bottom: 16px; }
  .release-performance h3 { margin: 0; color: #332a24; font-size: 15px; }
  .release-performance-description { margin: 4px 0 0; color: #7b6e63;
  font-size: 11px; line-height: 1.45; }
  .release-performance-legend { display: flex; flex: none; gap: 12px;
  color: #7b6e63; font-size: 10px; }
  .release-performance-legend span { display: flex; align-items: center; gap: 5px; }
  .release-performance-legend i { width: 8px; height: 8px; border-radius: 50%;
  background: #cdbba5; }
  .release-performance-legend span:last-child i { background: #2f6f4f; }
  .release-performance-item + .release-performance-item { margin-top: 14px; }
  .release-performance-row { display: flex; align-items: baseline;
  justify-content: space-between; gap: 12px; margin-bottom: 7px; }
  .release-performance-label { color: #4e443c; font-size: 12px; font-weight: 700; }
  .release-performance-values { display: flex; align-items: baseline; gap: 7px;
  font-variant-numeric: tabular-nums; }
  .release-performance-values span { color: #8b7d70; font-size: 11px;
  text-decoration: line-through; }
  .release-performance-values strong { min-width: 72px; color: #2f6f4f;
  font-size: 14px; text-align: right; }
  .release-performance-track { position: relative; height: 12px; overflow: hidden;
  border-radius: 999px; background: #e7dccd; }
  .release-performance-before { position: absolute; inset: 0 auto 0 0;
  width: 100%; background: #cdbba5; }
  .release-performance-after { position: absolute; inset: 0 auto 0 0;
  width: var(--after); border-radius: inherit; background: linear-gradient(90deg,
  #2f6f4f, #4f9a70); box-shadow: 0 0 18px rgba(47, 111, 79, 0.3);
  animation: release-performance-drop 1100ms var(--ease) both;
  animation-delay: var(--delay, 0ms); }
  .release-performance-gain { display: block; margin-top: 5px; color: #2f6f4f;
  font-size: 10px; font-weight: 700; text-align: right; }
  .release-features { display: grid; grid-template-columns: 1fr 1fr;
  gap: 16px 26px; margin: 26px 0 22px; }
  .release-feature { position: relative; padding-left: 24px;
  animation: release-item-in 560ms var(--ease) both;
  animation-delay: var(--delay, 0ms); }
  .release-feature::before { content: ""; position: absolute; left: 0; top: 5px;
  width: 9px; height: 9px; border-radius: 50%; background: #2f6f4f;
  box-shadow: 0 0 0 4px rgba(47, 111, 79, 0.1); }
  .release-feature:last-child { grid-column: 1 / -1; }
  .release-feature strong { display: block; color: #332a24; font-size: 14px; }
  .release-feature p { margin: 4px 0 0; color: #74675c; font-size: 12px;
  line-height: 1.5; }
  .release-measurement { margin: 0; padding-top: 16px; border-top: 1px solid
  rgba(31, 27, 22, 0.12); color: #817367; font-size: 11px; line-height: 1.5; }
  .release-actions { display: flex; align-items: center; gap: 14px;
  margin-top: 24px; }
  .release-actions .primary { height: 46px; padding: 0 22px;
  background: #241c19; color: #fff8ef; }
  .release-actions .primary:hover { background: #3a2e27; }
  .release-link { color: #6f6157; font-size: 13px; font-weight: 650;
  text-decoration-color: rgba(47, 111, 79, 0.45); text-underline-offset: 4px; }
  .release-link:hover { color: #2f6f4f; }
  .release-spark { position: absolute; width: 7px; height: 14px; border-radius: 2px;
  opacity: 0; background: #d7a14e; animation: release-spark 1500ms var(--ease)
  both; animation-delay: var(--delay, 0ms); }
  .release-spark.s1 { left: 12%; top: 16%; --rotate: 24deg; }
  .release-spark.s2 { right: 13%; top: 12%; --rotate: -32deg;
  background: #6fa586; }
  .release-spark.s3 { left: 17%; bottom: 14%; --rotate: 48deg;
  background: #6fa586; }
  .release-spark.s4 { right: 16%; bottom: 16%; --rotate: -18deg; }
  body.release-open { overflow: hidden; }
  @keyframes release-layer-in { from { opacity: 0; } to { opacity: 1; } }
  @keyframes release-dialog-in { from { opacity: 0; transform: translateY(26px)
  scale(0.97); } to { opacity: 1; transform: none; } }
  @keyframes release-check-in { from { opacity: 0; transform: scale(0.6); }
  to { opacity: 1; transform: none; } }
  @keyframes release-check-draw { to { stroke-dashoffset: 0; } }
  @keyframes release-item-in { from { opacity: 0; transform: translateY(12px); }
  to { opacity: 1; transform: none; } }
  @keyframes release-performance-drop { from { width: 100%; }
  to { width: var(--after); } }
  @keyframes release-drift { to { transform: translate(24px, -18px) scale(1.08); } }
  @keyframes release-spark { 0% { opacity: 0; transform: translateY(16px)
  rotate(var(--rotate)) scale(0.6); } 35% { opacity: 0.85; } 100% { opacity: 0;
  transform: translateY(-70px) rotate(var(--rotate)) scale(1); } }
  @media (max-width: 720px) {
    .shell { padding: 20px 14px 32px; }
    .panel { padding: 22px; }
    h1 { font-size: 26px; }
    .grid { grid-template-columns: repeat(2, 1fr); }
    .actions button { flex: 1 1 100%; }
    footer { flex-direction: column; }
    .release-layer { padding: 12px; }
    .release-dialog { max-height: calc(100vh - 24px); padding: 34px 24px 26px;
    border-radius: 24px; }
    .release-dialog h2 { font-size: 42px; }
    .release-summary { font-size: 15px; }
    .release-metrics { grid-template-columns: 1fr; }
    .release-metric { display: grid; grid-template-columns: 90px 1fr; align-items: center;
    column-gap: 12px; }
    .release-metric strong { grid-row: 1 / 3; }
    .release-metric span, .release-metric small { margin-top: 0; }
    .release-performance { padding: 16px; }
    .release-performance-head { flex-direction: column; gap: 8px; }
    .release-features { grid-template-columns: 1fr; }
    .release-feature:last-child { grid-column: auto; }
    .release-actions { align-items: stretch; flex-direction: column; }
    .release-link { text-align: center; }
  }
  @media (prefers-reduced-motion: reduce) {
    *, *::before, *::after { animation-duration: 0.01ms !important;
    animation-iteration-count: 1 !important; transition-duration: 0.01ms !important; }
    .release-atmosphere { display: none; }
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

<div class="release-layer" id="releaseLayer" hidden>
  <div class="release-atmosphere" aria-hidden="true">
    <span class="release-orb one"></span>
    <span class="release-orb two"></span>
    <i class="release-spark s1" style="--delay: 420ms"></i>
    <i class="release-spark s2" style="--delay: 560ms"></i>
    <i class="release-spark s3" style="--delay: 700ms"></i>
    <i class="release-spark s4" style="--delay: 840ms"></i>
  </div>
  <section class="release-dialog" id="releaseDialog" role="dialog"
  aria-modal="true" aria-labelledby="releaseTitle" aria-describedby="releaseSummary"
  tabindex="-1">
    <button type="button" class="release-close" id="releaseClose"
    aria-label="Fermer les nouveautés">
      <svg width="18" height="18" viewBox="0 0 18 18" fill="none"
      aria-hidden="true">
        <path d="M4 4l10 10M14 4L4 14" stroke="currentColor" stroke-width="1.8"
        stroke-linecap="round"/>
      </svg>
    </button>
    <div class="release-check" aria-hidden="true">
      <svg viewBox="0 0 34 34" fill="none">
        <path d="M8 17.5l6 6L26 11" stroke="currentColor" stroke-width="3"
        stroke-linecap="round" stroke-linejoin="round"/>
      </svg>
    </div>
    <p class="release-kicker" id="releaseKicker"></p>
    <h2 id="releaseTitle"></h2>
    <p class="release-summary" id="releaseSummary"></p>
    <div class="release-metrics" id="releaseMetrics"></div>
    <section class="release-performance" id="releasePerformance"
    aria-label="Comparatif des performances" hidden>
      <div class="release-performance-head">
        <div>
          <h3 id="releasePerformanceTitle"></h3>
          <p class="release-performance-description"
          id="releasePerformanceDescription"></p>
        </div>
        <div class="release-performance-legend" aria-hidden="true">
          <span><i></i>Avant</span><span><i></i>Maintenant</span>
        </div>
      </div>
      <div id="releasePerformanceItems"></div>
    </section>
    <div class="release-features" id="releaseFeatures"></div>
    <p class="release-measurement" id="releaseMeasurement"></p>
    <div class="release-actions">
      <button type="button" class="primary" id="releaseDone">C'est parti</button>
      <a class="release-link" id="releaseLink" target="_blank"
      rel="noopener noreferrer" hidden>Voir les notes complètes</a>
    </div>
  </section>
</div>

<script>
const TOKEN = "__TOKEN__";
let timer = null;
let stopped = false;

__API_JS__

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

let currentRelease = null;
let releaseHandledVersion = null;
let releaseReturnFocus = null;
let releasePerformanceFrame = null;

function appendText(parent, tag, className, text) {
  const element = document.createElement(tag);
  element.className = className;
  element.textContent = text || "";
  parent.appendChild(element);
  return element;
}

function formatPerformance(value, unit) {
  const number = new Intl.NumberFormat("fr-FR", {
    maximumFractionDigits: 0
  }).format(value);
  return number + (unit ? " " + unit : "");
}

function animatePerformance(rows, reduced) {
  if (releasePerformanceFrame !== null) {
    cancelAnimationFrame(releasePerformanceFrame);
    releasePerformanceFrame = null;
  }
  if (reduced) {
    rows.forEach((row) => {
      row.value.textContent = formatPerformance(row.after, row.unit);
    });
    return;
  }
  const started = performance.now() + 320;
  const duration = 1000;
  const stagger = 140;
  function frame(now) {
    rows.forEach((row, index) => {
      const progress = Math.min(1, Math.max(
        0, (now - started - index * stagger) / duration
      ));
      const eased = 1 - Math.pow(1 - progress, 3);
      const value = row.before + (row.after - row.before) * eased;
      row.value.textContent = formatPerformance(value, row.unit);
    });
    const total = duration + Math.max(0, rows.length - 1) * stagger;
    if (now - started < total) {
      releasePerformanceFrame = requestAnimationFrame(frame);
    } else {
      releasePerformanceFrame = null;
    }
  }
  releasePerformanceFrame = requestAnimationFrame(frame);
}

function renderPerformance(note) {
  const panel = document.getElementById("releasePerformance");
  const data = note.performance;
  const items = data && Array.isArray(data.items) ? data.items.filter((item) =>
    item && Number.isFinite(item.before) && Number.isFinite(item.after) &&
    item.before > 0 && item.after >= 0
  ) : [];
  panel.hidden = items.length === 0;
  const container = document.getElementById("releasePerformanceItems");
  container.replaceChildren();
  if (panel.hidden) return;
  document.getElementById("releasePerformanceTitle").textContent =
    data.title || "Gains de performance";
  document.getElementById("releasePerformanceDescription").textContent =
    data.description || "";
  const rows = items.map((item, index) => {
    const article = document.createElement("article");
    article.className = "release-performance-item";
    const labels = document.createElement("div");
    labels.className = "release-performance-row";
    appendText(labels, "span", "release-performance-label", item.label);
    const values = document.createElement("div");
    values.className = "release-performance-values";
    appendText(values, "span", "", formatPerformance(item.before, item.unit));
    const value = appendText(
      values, "strong", "", formatPerformance(item.before, item.unit)
    );
    labels.appendChild(values);
    article.appendChild(labels);
    const track = document.createElement("div");
    track.className = "release-performance-track";
    appendText(track, "span", "release-performance-before", "");
    const after = appendText(track, "span", "release-performance-after", "");
    after.style.setProperty(
      "--after", Math.min(100, item.after / item.before * 100) + "%"
    );
    after.style.setProperty("--delay", (320 + index * 140) + "ms");
    article.appendChild(track);
    const gain = Math.round((1 - item.after / item.before) * 100);
    if (gain > 0) {
      appendText(
        article, "small", "release-performance-gain", gain + " % en moins"
      );
    }
    container.appendChild(article);
    return {value, before: item.before, after: item.after, unit: item.unit || ""};
  });
  const reduced = window.matchMedia(
    "(prefers-reduced-motion: reduce)"
  ).matches;
  animatePerformance(rows, reduced);
}

function renderRelease(note) {
  if (!note || !note.version || note.version === releaseHandledVersion) return;
  releaseHandledVersion = note.version;
  currentRelease = note;
  document.getElementById("releaseKicker").textContent =
    "CheckMate " + note.version + " - mise à jour importante";
  document.getElementById("releaseTitle").textContent =
    note.title || "Mise à jour terminée.";
  document.getElementById("releaseSummary").textContent =
    note.summary || "Découvre ce qui change.";
  document.getElementById("releaseMeasurement").textContent =
    note.measurement || "";

  const metrics = document.getElementById("releaseMetrics");
  metrics.replaceChildren();
  (Array.isArray(note.metrics) ? note.metrics : []).forEach((metric, index) => {
    const item = document.createElement("div");
    item.className = "release-metric";
    item.style.setProperty("--delay", (160 + index * 90) + "ms");
    appendText(item, "strong", "", metric.value);
    appendText(item, "span", "", metric.label);
    appendText(item, "small", "", metric.detail);
    metrics.appendChild(item);
  });

  renderPerformance(note);

  const features = document.getElementById("releaseFeatures");
  features.replaceChildren();
  (Array.isArray(note.features) ? note.features : []).forEach((feature, index) => {
    const item = document.createElement("article");
    item.className = "release-feature";
    item.style.setProperty("--delay", (260 + index * 70) + "ms");
    appendText(item, "strong", "", feature.title);
    appendText(item, "p", "", feature.description);
    features.appendChild(item);
  });

  const link = document.getElementById("releaseLink");
  link.hidden = typeof note.url !== "string" || !note.url;
  if (!link.hidden) link.href = note.url;
  releaseReturnFocus = document.activeElement;
  document.getElementById("releaseLayer").hidden = false;
  document.body.classList.add("release-open");
  document.getElementById("releaseDone").focus();
}

function closeRelease() {
  if (releasePerformanceFrame !== null) {
    cancelAnimationFrame(releasePerformanceFrame);
    releasePerformanceFrame = null;
  }
  document.getElementById("releaseLayer").hidden = true;
  document.body.classList.remove("release-open");
  currentRelease = null;
  if (releaseReturnFocus && typeof releaseReturnFocus.focus === "function") {
    releaseReturnFocus.focus();
  }
  releaseReturnFocus = null;
}

async function dismissRelease() {
  const version = currentRelease ? currentRelease.version : null;
  if (version) releaseHandledVersion = version;
  closeRelease();
  if (!version) return;
  try {
    await api("/api/action", { action: "dismiss-release" });
  } catch (error) {
    console.debug("Fermeture des nouveautés non synchronisée", error);
  }
}

document.getElementById("releaseClose")
  .addEventListener("click", dismissRelease);
document.getElementById("releaseDone")
  .addEventListener("click", dismissRelease);
document.getElementById("releaseLayer")
  .addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      event.preventDefault();
      dismissRelease();
      return;
    }
    if (event.key !== "Tab") return;
    const focusable = Array.from(document.querySelectorAll(
      "#releaseDialog button, #releaseDialog a[href]"
    )).filter((element) => !element.hidden);
    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  });

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
  renderRelease(snapshot.release_note);
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
""".replace("__API_JS__", API_JS)
