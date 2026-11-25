"""Interface web locale de l'onboarding."""

from .ui_shared import API_JS

SETUP_HTML = """<!doctype html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>CheckMate - Configuration</title>
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
    --accent-hover: #275c41;
    --ok: #2f6f4f;
    --err: #b3261e;
    --ease: cubic-bezier(0.22, 1, 0.36, 1);
    --pen-cursor: url("data:image/svg+xml;charset=utf-8,%3Csvg\
 xmlns='http://www.w3.org/2000/svg'\
 width='20'\
 height='20'%3E%3Cpath\
 d='M10\
 3v4M10\
 13v4M3\
 10h4M13\
 10h4'\
 stroke='%23ffffff'\
 stroke-width='4'\
 stroke-linecap='round'/%3E%3Cpath\
 d='M10\
 3v4M10\
 13v4M3\
 10h4M13\
 10h4'\
 stroke='%231f1b16'\
 stroke-width='1.5'\
 stroke-linecap='round'/%3E%3C/svg%3E") 10 10, crosshair;
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
    line-height: 1.55;
    -webkit-font-smoothing: antialiased;
  }
  .shell {
    max-width: 1120px;
    margin: 0 auto;
    padding: 48px 32px 64px;
    display: grid;
    grid-template-columns: 280px minmax(0, 1fr);
    gap: 40px;
    align-items: start;
  }

  /* Rail */
  .rail {
    display: flex;
    flex-direction: column;
    min-height: 0;
  }
  .brand { display: flex; align-items: center; gap: 12px; }
  .mark { width: 32px; height: 32px; color: var(--accent); flex: none; }
  .brand-text { display: flex; flex-direction: column; gap: 1px; }
  .wordmark { font-size: 17px; font-weight: 600; letter-spacing: 0; }
  .tagline { font-size: 12px; color: var(--muted); }
  .steps {
    list-style: none;
    margin: 32px 0 0;
    padding: 0;
    display: flex;
    flex-direction: column;
    gap: 4px;
  }
  .steps li {
    min-height: 36px;
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 0 10px;
    border-radius: 10px;
    color: var(--ink-2);
    font-size: 14px;
    transition: background-color 150ms var(--ease), color 150ms var(--ease);
  }
  .steps li.active { background: var(--raised); color: var(--ink); }
  .step-mark {
    width: 20px;
    height: 20px;
    display: grid;
    place-items: center;
    flex: none;
  }
  .step-num {
    font-family: ui-monospace, "SFMono-Regular", "Cascadia Mono", monospace;
    font-size: 11px;
    color: var(--muted);
  }
  .step-check { display: none; width: 14px; height: 14px; color: var(--accent);
  }
  .steps li.done .step-num { display: none; }
  .steps li.done .step-check { display: block; }
  .steps li.active .step-num { color: var(--ink); }

  .timetable {
    margin-top: 40px;
    padding-top: 20px;
    border-top: 1px solid var(--line);
  }
  .timetable-label {
    margin: 0 0 8px;
    font-size: 12px;
    color: var(--muted);
  }
  .slot {
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    gap: 12px;
    padding: 7px 0;
    color: var(--ink-2);
    font-family: ui-monospace, "SFMono-Regular", "Cascadia Mono", monospace;
    font-size: 13px;
    font-variant-numeric: tabular-nums;
  }
  .slot.active { color: var(--ink); }
  .slot-state { font-family: inherit; font-size: 11px; color: var(--muted); }
  .slot.active .time::before {
    content: "";
    display: inline-block;
    width: 6px;
    height: 6px;
    border-radius: 50%;
    background: var(--ink);
    margin-right: 8px;
    vertical-align: 1px;
  }
  .rail-foot {
    margin: 20px 0 0;
    font-size: 12px;
    line-height: 1.5;
    color: var(--muted);
  }

  /* Panel */
  .panel {
    background: var(--card);
    border: 1px solid var(--line);
    border-radius: 16px;
    padding: 32px;
    min-height: 480px;
    box-shadow: 0 1px 2px rgba(31, 27, 22, 0.04);
    animation: rise 320ms var(--ease) both;
  }
  @keyframes rise {
    from { opacity: 0; transform: translateY(8px); }
    to { opacity: 1; transform: none; }
  }
  @media (prefers-reduced-motion: reduce) {
    .panel { animation: none; }
    * { transition: none !important; }
  }
  .panel-meta {
    display: flex;
    gap: 8px;
    align-items: center;
    margin-bottom: 24px;
    font-family: ui-monospace, "SFMono-Regular", "Cascadia Mono", monospace;
    font-size: 12px;
    color: var(--muted);
  }
  .panel-meta .current { color: var(--ink-2); }
  section { display: none; }
  section.active { display: block; }
  h2 {
    margin: 0 0 12px;
    font-size: 28px;
    line-height: 1.2;
    font-weight: 500;
    letter-spacing: 0;
  }
  .lede {
    margin: 0 0 24px;
    max-width: 62ch;
    color: var(--ink-2);
  }
  .facts {
    list-style: none;
    margin: 24px 0 0;
    padding: 0;
    display: flex;
    flex-direction: column;
    gap: 10px;
  }
  .facts li { display: flex; gap: 10px; align-items: flex-start; color:
  var(--ink-2); font-size: 14px; }
  .facts svg { width: 16px; height: 16px; color: var(--muted); flex: none;
  margin-top: 2px; }

  .field { margin-top: 20px; }
  .field:first-of-type { margin-top: 0; }
  label { display: block; font-size: 13px; color: var(--ink-2); margin-bottom:
  8px; }
  input[type=text], input[type=password], input[type=url] {
    width: 100%;
    height: 44px;
    padding: 0 12px;
    border: 1px solid var(--line);
    border-radius: 10px;
    background: #ffffff;
    color: var(--ink);
    font: inherit;
    font-size: 15px;
    transition: border-color 150ms var(--ease), background-color 150ms
    var(--ease);
  }
  input[type=text]:hover, input[type=password]:hover, input[type=url]:hover {
    border-color: rgba(31, 27, 22, 0.24);
  }
  input:focus-visible, button:focus-visible, .days label:focus-within {
    outline: 2px solid var(--accent);
    outline-offset: 2px;
  }
  .hint { margin: 10px 0 0; font-size: 12.5px; color: var(--muted); }

  .status {
    min-height: 20px;
    margin-top: 12px;
    font-size: 13.5px;
    color: var(--ink-2);
  }
  .status:not(:empty)::before {
    content: "";
    display: inline-block;
    width: 6px;
    height: 6px;
    border-radius: 50%;
    background: currentColor;
    margin-right: 8px;
    vertical-align: 1px;
  }
  .status.ok { color: var(--ok); }
  .status.err { color: var(--err); }

  .actions {
    display: flex;
    align-items: center;
    gap: 12px;
    flex-wrap: wrap;
    margin-top: 28px;
  }
  .actions-spacer { flex: 1; }
  button {
    height: 44px;
    padding: 0 20px;
    border: 1px solid transparent;
    border-radius: 10px;
    font: inherit;
    font-size: 15px;
    font-weight: 500;
    cursor: pointer;
    transition: background-color 150ms var(--ease), border-color 150ms
    var(--ease),
                color 150ms var(--ease), transform 120ms var(--ease);
  }
  button:active { transform: scale(0.98); }
  button:disabled { opacity: 0.45; cursor: not-allowed; }
  .primary { background: var(--accent); color: var(--paper); }
  .primary:hover:not(:disabled) { background: var(--accent-hover); }
  .secondary { background: var(--card); border-color: var(--line); color:
  var(--ink); }
  .secondary:hover:not(:disabled) { background: var(--raised); }

  .days-field { border: 0; padding: 0; margin: 24px 0 0; }
  .days-field legend { padding: 0; font-size: 13px; color: var(--ink-2);
  margin-bottom: 8px; }
  .days { display: flex; flex-wrap: wrap; gap: 8px; }
  .days label {
    margin: 0;
    min-width: 60px;
    height: 40px;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    padding: 0 14px;
    border: 1px solid var(--line);
    border-radius: 9px;
    background: var(--card);
    color: var(--ink-2);
    font-size: 14px;
    cursor: pointer;
    user-select: none;
    transition: background-color 150ms var(--ease), border-color 150ms
    var(--ease);
  }
  .days input { position: absolute; opacity: 0; pointer-events: none; }
  .days label:has(input:checked) {
    background: var(--raised);
    border-color: rgba(31, 27, 22, 0.28);
    color: var(--ink);
  }

  .sig-head { display: flex; align-items: center; justify-content:
  space-between; gap: 16px; }
  .sig-existing {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    font-size: 12px;
    color: var(--ink-2);
  }
  .sig-existing svg { width: 14px; height: 14px; color: var(--accent); }
  canvas {
    display: block;
    width: 100%;
    height: auto;
    margin-top: 8px;
    background: #ffffff;
    border: 1px solid var(--line);
    border-radius: 12px;
    cursor: var(--pen-cursor);
    touch-action: none;
  }
  .import-line {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
    margin-top: 14px;
    font-size: 12.5px;
    color: var(--muted);
  }
  .file-button {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    height: 34px;
    padding: 0 14px;
    margin: 0;
    border: 1px solid var(--line);
    border-radius: 8px;
    background: var(--card);
    color: var(--ink-2);
    font-size: 12.5px;
    cursor: pointer;
  }
  .file-button:hover { background: var(--raised); }
  .file-button input { position: absolute; width: 0; height: 0; opacity: 0; }

  .notice {
    margin: 0 0 20px;
    padding: 12px 16px;
    background: var(--accent-soft);
    border-left: 3px solid var(--accent);
    border-radius: 0 8px 8px 0;
  }
  .notice strong {
    display: block;
    margin-bottom: 4px;
    font-size: 13px;
    color: var(--ink);
  }
  .notice p {
    margin: 0;
    font-size: 12.5px;
    line-height: 1.45;
    color: var(--ink-2);
  }

  .checkline {
    display: flex;
    align-items: center;
    gap: 10px;
    margin-top: 28px;
    font-size: 14px;
    color: var(--ink-2);
    cursor: pointer;
  }
  .checkline input { width: 16px; height: 16px; accent-color: var(--accent); }

  .done { padding: 16px 0 0; }
  .done-check { width: 44px; height: 44px; color: var(--accent); margin-bottom:
  20px; }
  .done h2 { margin-bottom: 8px; }
  .done .lede { margin-bottom: 0; }
  .summary {
    margin: 28px 0 0;
    border-top: 1px solid var(--line);
  }
  .summary > div {
    display: flex;
    justify-content: space-between;
    gap: 24px;
    padding: 12px 0;
    border-bottom: 1px solid var(--line);
  }
  .summary dt { margin: 0; font-size: 13px; color: var(--ink-2); }
  .summary dd {
    margin: 0;
    font-family: ui-monospace, "SFMono-Regular", "Cascadia Mono", monospace;
    font-size: 13px;
    color: var(--ink);
    text-align: right;
    font-variant-numeric: tabular-nums;
  }

  @media (max-width: 860px) {
    .shell { grid-template-columns: 1fr; padding: 24px 16px 40px; gap: 24px; }
    .rail { min-height: 0; }
    .steps, .timetable, .rail-foot { display: none; }
    .panel { padding: 24px; min-height: 0; }
    .panel-meta { margin-bottom: 16px; }
    h2 { font-size: 24px; }
    .actions > button { flex: 1 1 auto; }
    .actions-spacer { display: none; }
    .primary { margin-left: auto; }
  }
</style>
</head>
<body>
<div class="shell">
  <aside class="rail">
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
      <div class="brand-text">
        <span class="wordmark">CheckMate</span>
        <span class="tagline">Configuration locale</span>
      </div>
    </div>

    <ol class="steps" id="steps">
      <li class="active"><span class="step-mark"><span
      class="step-num">1</span><svg class="step-check" viewBox="0 0 16 16"
      fill="none" aria-hidden="true"><path d="M3 8.5l3 3 7-7"
      stroke="currentColor" stroke-width="1.8" stroke-linecap="round"
      stroke-linejoin="round"/></svg></span><span>Mise en route</span></li>
      <li><span class="step-mark"><span class="step-num">2</span><svg
      class="step-check" viewBox="0 0 16 16" fill="none"
      aria-hidden="true"><path d="M3 8.5l3 3 7-7" stroke="currentColor"
      stroke-width="1.8" stroke-linecap="round"
      stroke-linejoin="round"/></svg></span><span>Connexion</span></li>
      <li><span class="step-mark"><span class="step-num">3</span><svg
      class="step-check" viewBox="0 0 16 16" fill="none"
      aria-hidden="true"><path d="M3 8.5l3 3 7-7" stroke="currentColor"
      stroke-width="1.8" stroke-linecap="round"
      stroke-linejoin="round"/></svg></span><span>Signature</span></li>
      <li><span class="step-mark"><span class="step-num">4</span><svg
      class="step-check" viewBox="0 0 16 16" fill="none"
      aria-hidden="true"><path d="M3 8.5l3 3 7-7" stroke="currentColor"
      stroke-width="1.8" stroke-linecap="round"
      stroke-linejoin="round"/></svg></span><span>Planning</span></li>
      <li><span class="step-mark"><span class="step-num">5</span><svg
      class="step-check" viewBox="0 0 16 16" fill="none"
      aria-hidden="true"><path d="M3 8.5l3 3 7-7" stroke="currentColor"
      stroke-width="1.8" stroke-linecap="round"
      stroke-linejoin="round"/></svg></span><span>Finition</span></li>
    </ol>

    <div class="timetable">
      <p class="timetable-label">Créneaux surveillés</p>
      <div class="slot" data-slot="0"><span
      class="time">09:00–12:00</span><span class="slot-state"></span></div>
      <div class="slot" data-slot="1"><span
      class="time">13:30–16:30</span><span class="slot-state"></span></div>
    </div>
    <p class="rail-foot">CheckMate __VERSION__<br>Identifiants et signature
    restent sur cet ordinateur.</p>
  </aside>

  <main class="panel">
    <div class="panel-meta" id="panelMeta">
      <span class="current" id="stepLabel">Étape 1 sur 5</span>
      <span>/</span>
      <span>CESAR Emineo</span>
    </div>

    <section class="active" data-step="0">
      <h2>Mise en route</h2>
      <p class="lede">CheckMate surveille CESAR pendant tes créneaux et te
      propose de signer dès que l'émargement s'ouvre. Aucune fenêtre pendant
      l'attente, une fenêtre uniquement pour signer.</p>
      <ul class="facts">
        <li><svg viewBox="0 0 16 16" fill="none" aria-hidden="true"><path d="M3
        8.5l3 3 7-7" stroke="currentColor" stroke-width="1.8"
        stroke-linecap="round" stroke-linejoin="round"/></svg><span>Les
        identifiants restent sur cet ordinateur.</span></li>
        <li><svg viewBox="0 0 16 16" fill="none" aria-hidden="true"><path d="M3
        8.5l3 3 7-7" stroke="currentColor" stroke-width="1.8"
        stroke-linecap="round" stroke-linejoin="round"/></svg><span>Le mot de
        passe va dans le trousseau du système quand c'est possible.</span></li>
        <li><svg viewBox="0 0 16 16" fill="none" aria-hidden="true"><path d="M3
        8.5l3 3 7-7" stroke="currentColor" stroke-width="1.8"
        stroke-linecap="round" stroke-linejoin="round"/></svg><span>Aucune
        donnée n'est envoyée à un serveur tiers.</span></li>
      </ul>
      <div class="actions">
        <div class="actions-spacer"></div>
        <button type="button" class="primary"
        onclick="go(1)">Configurer</button>
      </div>
    </section>

    <section data-step="1">
      <h2>Connexion CESAR</h2>
      <p class="lede">Utilise les mêmes identifiants que sur le site. Le test
      ouvre un navigateur invisible et vérifie que la connexion fonctionne.</p>
      <div class="field">
        <label for="baseUrl">Adresse du site</label>
        <input id="baseUrl" type="url"
        value="https://cesar.emineo-education.fr">
      </div>
      <div class="field">
        <label for="username">Identifiant</label>
        <input id="username" type="text" autocomplete="username"
        placeholder="ton identifiant">
      </div>
      <div class="field">
        <label for="password">Mot de passe</label>
        <input id="password" type="password" autocomplete="current-password"
        placeholder="ton mot de passe">
      </div>
      <div class="status" id="loginStatus" aria-live="polite"></div>
      <div class="actions">
        <button type="button" class="secondary" onclick="testLogin()"
        id="testBtn">Tester la connexion</button>
        <div class="actions-spacer"></div>
        <button type="button" class="primary" onclick="saveCredentials()"
        id="loginNext" disabled>Continuer</button>
      </div>
      <p class="hint">Le bouton Continuer s'active après un test réussi.</p>
    </section>

    <section data-step="2">
      <div class="sig-head">
        <h2>Signature</h2>
        <span class="sig-existing" id="signatureBadge" hidden>
          <svg viewBox="0 0 16 16" fill="none" aria-hidden="true"><path d="M3
          8.5l3 3 7-7" stroke="currentColor" stroke-width="1.8"
          stroke-linecap="round" stroke-linejoin="round"/></svg>
          Signature enregistrée
        </span>
      </div>
      <p class="lede">Dessine ta signature à la souris ou au doigt. Elle sera
      rejouée telle quelle dans le canvas de CESAR.</p>
      <canvas id="pad" width="640" height="240" aria-label="Zone de
      signature"></canvas>
      <div class="import-line">
        <span>Signature deja existante ?</span>
        <label class="file-button" for="signatureFile">Importer le JSON
          <input id="signatureFile" type="file"
          accept=".json,application/json">
        </label>
      </div>
      <div class="status" id="signatureStatus" aria-live="polite"></div>
      <div class="actions">
        <button type="button" class="secondary"
        onclick="clearPad()">Effacer</button>
        <button type="button" class="secondary" onclick="saveSignature()"
        id="signatureBtn">Enregistrer la signature</button>
        <div class="actions-spacer"></div>
        <button type="button" class="primary" onclick="go(3)"
        id="signatureNext" disabled>Continuer</button>
      </div>
    </section>

    <section data-step="3">
      <h2>Planning</h2>
      <p class="lede">CheckMate ne surveille que pendant ces créneaux. Une fois
      signé sur un créneau, il ne vérifie plus rien jusqu'au suivant.</p>
      <fieldset class="days-field">
        <legend>Jours</legend>
        <div class="days" id="days">
__DAYS__
        </div>
      </fieldset>
      <div class="field">
        <label for="windows">Créneaux</label>
        <input id="windows" type="text" value="__WINDOWS__">
      </div>
      <p class="hint">Format HH:MM-HH:MM, séparés par des virgules.</p>
      <div class="status" id="scheduleStatus" aria-live="polite"></div>
      <div class="actions">
        <div class="actions-spacer"></div>
        <button type="button" class="primary"
        onclick="saveSchedule()">Continuer</button>
      </div>
    </section>

    <section data-step="4">
      <h2>Finition</h2>
      <p class="lede">Vérifie que la notification s'affiche, puis installe le
      démarrage automatique pour ne plus y penser.</p>
      <div class="notice">
        <strong>Coupe le mode silencieux</strong>
        <p>Désactive le mode silencieux ou "Ne pas déranger" avant de tester.
        Vérifie aussi que "CheckMate" est activé dans Paramètres > Système >
        Notifications. Sinon la notification peut ne pas s'afficher, même si
        CheckMate l'a bien envoyée.</p>
      </div>
      <div class="actions">
        <button type="button" class="secondary" onclick="testNotification()"
        id="notifyBtn">Tester la notification</button>
      </div>
      <div class="status" id="notifyStatus" aria-live="polite"></div>
      <label class="checkline">
        <input type="checkbox" id="notificationsSeen">
        <span>J'ai vérifié que la notification s'affiche, mode silencieux
        désactivé</span>
      </label>
      <label class="checkline">
        <input type="checkbox" id="autostart" checked>
        <span>Démarrer automatiquement à l'ouverture de session</span>
      </label>
      <div class="status" id="finishStatus" aria-live="polite"></div>
      <div class="actions">
        <div class="actions-spacer"></div>
        <button type="button" class="primary" onclick="finish()" id="finishBtn"
        disabled>Terminer</button>
      </div>
    </section>

    <section data-step="5">
      <div class="done">
        <svg class="done-check" viewBox="0 0 44 44" fill="none"
        aria-hidden="true">
          <circle cx="22" cy="22" r="20" stroke="currentColor"
          stroke-width="1.6" opacity="0.35"/>
          <path d="M13 22.5l6 6 12-13" stroke="currentColor" stroke-width="2.4"
          stroke-linecap="round" stroke-linejoin="round"/>
        </svg>
        <h2>Configuration terminée</h2>
        <p class="lede" id="doneText">CheckMate est configuré.</p>
        <dl class="summary">
          <div><dt>Identifiant</dt><dd id="doneUser">—</dd></div>
          <div><dt>Créneaux</dt><dd id="doneWindows">—</dd></div>
          <div><dt>Démarrage auto</dt><dd id="doneAutostart">—</dd></div>
        </dl>
        <p class="hint">Tu peux fermer cette fenêtre.</p>
      </div>
    </section>
  </main>
</div>

<script>
const TOKEN = "__TOKEN__";
const state = { credentialsSaved: false, signatureSaved: false };
const STEP_LABELS = [
  "Mise en route", "Connexion", "Signature", "Planning", "Finition"
];

__API_JS__

function go(step) {
  document.querySelectorAll("section").forEach((section) => {
    section.classList.toggle("active", Number(section.dataset.step) === step);
  });

  const steps = [...document.querySelectorAll("#steps li")];
  const activeIndex = Math.min(step, steps.length - 1);
  steps.forEach((item, index) => {
    item.classList.toggle("active", index === activeIndex && step < 5);
    item.classList.toggle("done", index < step);
  });

  const meta = document.getElementById("panelMeta");
  if (step === 5) {
    meta.style.display = "none";
  } else {
    meta.style.display = "flex";
    document.getElementById("stepLabel").textContent =
      `Étape ${step + 1} sur 5`;
  }

  if (step === 2) loadState();
}

function setStatus(id, message, kind) {
  const el = document.getElementById(id);
  el.textContent = message || "";
  el.className = "status" + (kind ? " " + kind : "");
}

async function loadState() {
  try {
    const data = await api("/api/state");
    document.getElementById("username").value = data.username || "";
    document.getElementById("baseUrl").value = data.base_url;
    if (data.days && data.days.length) {
      document.querySelectorAll("#days input").forEach((box) => {
        box.checked = data.days.includes(box.value);
      });
    }
    if (data.windows && data.windows.length) {
      document.getElementById("windows").value = data.windows.join(", ");
    }
    if (data.has_signature) {
      document.getElementById("signatureBadge").hidden = false;
      document.getElementById("signatureNext").disabled = false;
      state.signatureSaved = true;
    }
  } catch (error) {
    setStatus("loginStatus", error.message, "err");
  }
}

async function testLogin() {
  const button = document.getElementById("testBtn");
  button.disabled = true;
  setStatus("loginStatus", "Test en cours, cela peut prendre 30 secondes...");
  try {
    const data = await api("/api/test-login", {
      base_url: document.getElementById("baseUrl").value.trim(),
      username: document.getElementById("username").value.trim(),
      password: document.getElementById("password").value,
    });
    setStatus("loginStatus", data.message || "Connexion réussie", "ok");
    document.getElementById("loginNext").disabled = false;
  } catch (error) {
    setStatus("loginStatus", error.message, "err");
    document.getElementById("loginNext").disabled = true;
  } finally {
    button.disabled = false;
  }
}

async function saveCredentials() {
  try {
    const data = await api("/api/credentials", {
      base_url: document.getElementById("baseUrl").value.trim(),
      username: document.getElementById("username").value.trim(),
      password: document.getElementById("password").value,
    });
    state.credentialsSaved = true;
    setStatus("loginStatus", data.message || "Identifiants enregistrés", "ok");
    document.getElementById("password").value = "";
    go(2);
  } catch (error) {
    setStatus("loginStatus", error.message, "err");
  }
}

const canvas = document.getElementById("pad");
const context = canvas.getContext("2d");
context.lineWidth = 2.4;
context.lineCap = "round";
context.lineJoin = "round";
context.strokeStyle = "#1f1b16";
let drawing = false;
let points = [];

function position(event) {
  const rect = canvas.getBoundingClientRect();
  return {
    x: (event.clientX - rect.left) * (canvas.width / rect.width),
    y: (event.clientY - rect.top) * (canvas.height / rect.height),
  };
}

canvas.addEventListener("pointerdown", (event) => {
  drawing = true;
  canvas.setPointerCapture(event.pointerId);
  const point = position(event);
  points.push({ x: point.x, y: point.y, type: "start" });
  context.beginPath();
  context.moveTo(point.x, point.y);
});

canvas.addEventListener("pointermove", (event) => {
  if (!drawing) return;
  const point = position(event);
  points.push({ x: point.x, y: point.y, type: "move" });
  context.lineTo(point.x, point.y);
  context.stroke();
});

function endStroke(event) {
  if (!drawing) return;
  drawing = false;
  const point = position(event);
  points.push({ x: point.x, y: point.y, type: "end" });
  context.stroke();
}
canvas.addEventListener("pointerup", endStroke);
canvas.addEventListener("pointercancel", endStroke);

function clearPad() {
  points = [];
  context.clearRect(0, 0, canvas.width, canvas.height);
  context.strokeStyle = "#1f1b16";
  context.lineWidth = 2.4;
  context.lineCap = "round";
  context.lineJoin = "round";
  setStatus("signatureStatus", "");
}

function pointsExtent(list) {
  let minX = Infinity;
  let minY = Infinity;
  let maxX = -Infinity;
  let maxY = -Infinity;
  for (const point of list) {
    if (point.x < minX) minX = point.x;
    if (point.y < minY) minY = point.y;
    if (point.x > maxX) maxX = point.x;
    if (point.y > maxY) maxY = point.y;
  }
  if (!Number.isFinite(minX) || !Number.isFinite(minY)) return 0;
  return Math.max(maxX - minX, maxY - minY);
}

async function saveSignature() {
  if (points.length < 2 || pointsExtent(points) < 2) {
    setStatus(
      "signatureStatus",
      "Dessine d'abord une vraie signature.",
      "err"
    );
    return;
  }
  try {
    await api("/api/signature", { points });
    state.signatureSaved = true;
    document.getElementById("signatureNext").disabled = false;
    document.getElementById("signatureBadge").hidden = false;
    setStatus("signatureStatus", "");
  } catch (error) {
    setStatus("signatureStatus", error.message, "err");
  }
}

document.getElementById("signatureFile")
  .addEventListener("change", async (event) => {
  const file = event.target.files[0];
  if (!file) return;
  const raw = await file.text();
  try {
    const data = await api("/api/import-signature", { raw });
    state.signatureSaved = true;
    document.getElementById("signatureNext").disabled = false;
    document.getElementById("signatureBadge").hidden = false;
    setStatus("signatureStatus", data.message, "ok");
  } catch (error) {
    setStatus("signatureStatus", error.message, "err");
  } finally {
    event.target.value = "";
  }
});

async function saveSchedule() {
  const days = [...document.querySelectorAll("#days input:checked")]
    .map((box) => box.value);
  const windows = document.getElementById("windows").value
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
  try {
    await api("/api/schedule", { days, windows });
    go(4);
  } catch (error) {
    setStatus("scheduleStatus", error.message, "err");
  }
}

async function testNotification() {
  const button = document.getElementById("notifyBtn");
  button.disabled = true;
  setStatus("notifyStatus", "Envoi en cours...");
  try {
    await api("/api/test-notification", {});
    setStatus(
      "notifyStatus",
      "Notification envoyée. Si tu ne la vois pas, coupe le mode " +
      `silencieux et vérifie l'interrupteur "CheckMate" dans les ` +
      "notifications système, puis relance le test.",
      "ok"
    );
  } catch (error) {
    setStatus("notifyStatus", error.message, "err");
  } finally {
    button.disabled = false;
  }
}

async function finish() {
  const button = document.getElementById("finishBtn");
  button.disabled = true;
  setStatus("finishStatus", "Installation du démarrage automatique...");
  try {
    const data = await api("/api/finish", {
      autostart: document.getElementById("autostart").checked,
    });
    document.getElementById("doneText").textContent = data.message;
    document.getElementById("doneUser").textContent = data.username || "—";
    document.getElementById("doneWindows").textContent =
      (data.windows || []).join(" · ") || "—";
    const autostartLabels = {
      installed: "Installé",
      disabled: "Désactivé",
      failed: "Échec",
    };
    document.getElementById("doneAutostart").textContent =
      autostartLabels[data.autostart] || "—";
    go(5);
  } catch (error) {
    setStatus("finishStatus", error.message, "err");
    button.disabled = false;
  }
}

function updateTimetable() {
  const now = new Date();
  const minutes = now.getHours() * 60 + now.getMinutes();
  const weekday = now.getDay();
  const windows = [[540, 720], [810, 990]];
  const active = weekday >= 1 && weekday <= 5
    ? windows.findIndex(([start, end]) => minutes >= start && minutes < end)
    : -1;
  document.querySelectorAll("[data-slot]").forEach((slot, index) => {
    slot.classList.toggle("active", index === active);
    slot.querySelector(".slot-state").textContent =
      index === active ? "en cours" : "";
  });
}

const notificationsSeen = document.getElementById("notificationsSeen");
const finishButton = document.getElementById("finishBtn");
notificationsSeen.addEventListener("change", () => {
  finishButton.disabled = !notificationsSeen.checked;
});

updateTimetable();
setInterval(updateTimetable, 60000);
loadState();
</script>
</body>
</html>
""".replace("__API_JS__", API_JS)
