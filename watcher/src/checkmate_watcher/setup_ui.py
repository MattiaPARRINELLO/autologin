"""Interface web locale de l'onboarding."""

SETUP_HTML = """<!doctype html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>CheckMate - Configuration</title>
<style>
  :root { color-scheme: dark; --bg:#0b1220; --card:#151f33; --line:#25324a;
          --text:#e6edf7; --muted:#93a4bd; --accent:#38bdf8; --ok:#22c55e; --err:#ef4444; }
  * { box-sizing: border-box; }
  body { margin:0; min-height:100vh; background:
         radial-gradient(1200px 600px at 20% -10%, #16324a 0%, transparent 60%), var(--bg);
         color:var(--text); font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif; }
  .wrap { max-width:760px; margin:0 auto; padding:40px 20px 80px; }
  header { display:flex; align-items:center; gap:12px; margin-bottom:26px; }
  .logo { width:40px; height:40px; border-radius:12px; background:linear-gradient(135deg,#22c55e,#38bdf8);
          display:grid; place-items:center; font-size:22px; }
  h1 { font-size:22px; margin:0; }
  .sub { color:var(--muted); font-size:14px; margin:2px 0 0; }
  .steps { display:flex; gap:8px; margin:0 0 22px; }
  .steps div { flex:1; height:5px; border-radius:99px; background:var(--line); transition:background .2s; }
  .steps div.on { background:var(--accent); }
  .card { background:var(--card); border:1px solid var(--line); border-radius:18px; padding:28px;
          box-shadow:0 20px 60px rgba(0,0,0,.35); }
  section { display:none; }
  section.active { display:block; }
  h2 { margin:0 0 8px; font-size:24px; }
  p { color:var(--muted); line-height:1.55; }
  ul { color:var(--muted); line-height:1.6; padding-left:20px; }
  label { display:block; font-size:14px; color:var(--muted); margin:16px 0 6px; }
  input[type=text], input[type=password], input[type=url] {
    width:100%; padding:12px 14px; border-radius:10px; border:1px solid var(--line);
    background:#0d1728; color:var(--text); font-size:15px; }
  input:focus { outline:2px solid rgba(56,189,248,.35); border-color:var(--accent); }
  canvas { background:#fff; border-radius:12px; display:block; width:100%; touch-action:none; cursor:crosshair; }
  .actions { display:flex; gap:12px; margin-top:24px; flex-wrap:wrap; }
  button { font:inherit; font-weight:700; border:0; border-radius:11px; padding:13px 22px; cursor:pointer; }
  .primary { background:var(--accent); color:#062033; }
  .ghost { background:#233148; color:var(--text); }
  .ok { background:var(--ok); color:#05230f; }
  button:disabled { opacity:.45; cursor:not-allowed; }
  .spacer { flex:1; }
  .status { margin-top:14px; font-size:14px; min-height:20px; }
  .status.ok { color:var(--ok); }
  .status.err { color:var(--err); }
  .days { display:flex; gap:8px; flex-wrap:wrap; margin-top:8px; }
  .days label { margin:0; padding:9px 14px; border:1px solid var(--line); border-radius:10px;
                background:#0d1728; color:var(--text); cursor:pointer; user-select:none; }
  .days input { display:none; }
  .days label:has(input:checked) { border-color:var(--accent); background:#12304a; }
  .hint { font-size:13px; color:var(--muted); margin-top:8px; }
  .badge { display:inline-block; padding:4px 10px; border-radius:99px; font-size:12px; font-weight:700;
           background:#12304a; color:#bae6fd; }
  .done { text-align:center; padding:20px 0; }
  .done .big { font-size:56px; }
  code { background:#0d1728; padding:2px 6px; border-radius:6px; color:#bae6fd; }
</style>
</head>
<body>
<div class="wrap">
  <header>
    <div class="logo">&#9822;</div>
    <div>
      <h1>CheckMate</h1>
      <p class="sub">Configuration en quelques minutes</p>
    </div>
  </header>

  <div class="steps" id="steps">
    <div class="on"></div><div></div><div></div><div></div><div></div>
  </div>

  <div class="card">
    <section class="active" data-step="0">
      <h2>Bienvenue</h2>
      <p>CheckMate surveille CESAR Emineo pendant tes cours et te propose de signer
      l'emargement des qu'il s'ouvre. Aucune fenetre pendant l'attente, une fenetre
      uniquement pour signer.</p>
      <ul>
        <li>Tes identifiants restent sur cet ordinateur.</li>
        <li>Le mot de passe va dans le trousseau du systeme quand c'est possible.</li>
        <li>Aucune donnee n'est envoyee a un serveur tiers.</li>
      </ul>
      <div class="actions"><button class="primary" onclick="go(1)">Commencer</button></div>
    </section>

    <section data-step="1">
      <h2>Connexion CESAR</h2>
      <p>Utilise les memes identifiants que sur le site. Le test ouvre un navigateur
      invisible et verifie que la connexion fonctionne.</p>
      <label for="baseUrl">Adresse du site</label>
      <input id="baseUrl" type="url" value="https://cesar.emineo-education.fr">
      <label for="username">Identifiant</label>
      <input id="username" type="text" autocomplete="username" placeholder="ton identifiant">
      <label for="password">Mot de passe</label>
      <input id="password" type="password" autocomplete="current-password" placeholder="ton mot de passe">
      <div class="status" id="loginStatus"></div>
      <div class="actions">
        <button class="ghost" onclick="testLogin()" id="testBtn">Tester la connexion</button>
        <div class="spacer"></div>
        <button class="primary" onclick="saveCredentials()" id="loginNext" disabled>Continuer</button>
      </div>
      <p class="hint">Le bouton Continuer s'active apres un test reussi.</p>
    </section>

    <section data-step="2">
      <h2>Signature</h2>
      <p>Dessine ta signature a la souris ou au doigt. Elle sera rejouee telle quelle
      dans le canvas de CESAR.</p>
      <div class="badge" id="signatureBadge" style="display:none">Signature deja enregistree</div>
      <canvas id="pad" width="640" height="240"></canvas>
      <div class="status" id="signatureStatus"></div>
      <div class="actions">
        <button class="ghost" onclick="clearPad()">Effacer</button>
        <button class="ghost" onclick="saveSignature()" id="signatureBtn">Enregistrer la signature</button>
        <div class="spacer"></div>
        <button class="primary" onclick="go(3)" id="signatureNext" disabled>Continuer</button>
      </div>
    </section>

    <section data-step="3">
      <h2>Planning</h2>
      <p>CheckMate ne surveille que pendant ces creneaux. Une fois signe sur un
      creneau, il ne verifie plus rien jusqu'au suivant.</p>
      <label>Jours</label>
      <div class="days" id="days">
        <label><input type="checkbox" value="mon" checked>Lun</label>
        <label><input type="checkbox" value="tue" checked>Mar</label>
        <label><input type="checkbox" value="wed" checked>Mer</label>
        <label><input type="checkbox" value="thu" checked>Jeu</label>
        <label><input type="checkbox" value="fri" checked>Ven</label>
        <label><input type="checkbox" value="sat">Sam</label>
        <label><input type="checkbox" value="sun">Dim</label>
      </div>
      <label for="windows">Creneaux (HH:MM-HH:MM, separes par des virgules)</label>
      <input id="windows" type="text" value="09:00-12:00, 13:30-16:30">
      <div class="status" id="scheduleStatus"></div>
      <div class="actions">
        <div class="spacer"></div>
        <button class="primary" onclick="saveSchedule()">Continuer</button>
      </div>
    </section>

    <section data-step="4">
      <h2>Derniere etape</h2>
      <p>Verifie que la notification s'affiche, puis installe le demarrage
      automatique pour ne plus y penser.</p>
      <div class="actions">
        <button class="ghost" onclick="testNotification()" id="notifyBtn">Tester la notification</button>
      </div>
      <div class="status" id="notifyStatus"></div>
      <label style="display:flex; gap:10px; align-items:center; margin-top:22px">
        <input type="checkbox" id="autostart" checked>
        <span>Demarrer automatiquement a l'ouverture de session</span>
      </label>
      <div class="status" id="finishStatus"></div>
      <div class="actions">
        <div class="spacer"></div>
        <button class="ok" onclick="finish()" id="finishBtn">Terminer</button>
      </div>
    </section>

    <section data-step="5">
      <div class="done">
        <div class="big">&#9989;</div>
        <h2>Tout est pret</h2>
        <p id="doneText">CheckMate est configure et demarre automatiquement.</p>
        <p class="hint">Tu peux fermer cette fenetre.</p>
      </div>
    </section>
  </div>
</div>

<script>
const TOKEN = "__TOKEN__";
const state = { credentialsSaved: false, signatureSaved: false };

async function api(path, body) {
  const options = { method: body ? "POST" : "GET", headers: { "X-CheckMate-Token": TOKEN } };
  if (body) {
    options.headers["Content-Type"] = "application/json";
    options.body = JSON.stringify(body);
  }
  const response = await fetch(path, options);
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.error || ("erreur " + response.status));
  return data;
}

function go(step) {
  document.querySelectorAll("section").forEach((section) => {
    section.classList.toggle("active", Number(section.dataset.step) === step);
  });
  document.querySelectorAll("#steps div").forEach((dot, index) => {
    dot.classList.toggle("on", index <= Math.min(step, 4));
  });
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
      document.getElementById("signatureBadge").style.display = "inline-block";
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
    setStatus("loginStatus", data.message || "Connexion reussie", "ok");
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
    setStatus("loginStatus", data.message || "Identifiants enregistres", "ok");
    document.getElementById("password").value = "";
    go(2);
  } catch (error) {
    setStatus("loginStatus", error.message, "err");
  }
}

const canvas = document.getElementById("pad");
const context = canvas.getContext("2d");
context.lineWidth = 2.5;
context.lineCap = "round";
context.strokeStyle = "#0b1220";
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
  setStatus("signatureStatus", "");
}

async function saveSignature() {
  if (points.length < 2) {
    setStatus("signatureStatus", "Dessine d'abord une signature.", "err");
    return;
  }
  try {
    await api("/api/signature", { points });
    state.signatureSaved = true;
    document.getElementById("signatureNext").disabled = false;
    document.getElementById("signatureBadge").style.display = "inline-block";
    document.getElementById("signatureBadge").textContent = "Signature enregistree";
    setStatus("signatureStatus", "Signature enregistree.", "ok");
  } catch (error) {
    setStatus("signatureStatus", error.message, "err");
  }
}

async function saveSchedule() {
  const days = [...document.querySelectorAll("#days input:checked")].map((box) => box.value);
  const windows = document.getElementById("windows").value.split(",").map((item) => item.trim()).filter(Boolean);
  try {
    await api("/api/schedule", { days, windows });
    setStatus("scheduleStatus", "Planning enregistre.", "ok");
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
    const data = await api("/api/test-notification", {});
    setStatus("notifyStatus", data.message || "Notification envoyee.", "ok");
  } catch (error) {
    setStatus("notifyStatus", error.message, "err");
  } finally {
    button.disabled = false;
  }
}

async function finish() {
  const button = document.getElementById("finishBtn");
  button.disabled = true;
  setStatus("finishStatus", "Installation du demarrage automatique...");
  try {
    const data = await api("/api/finish", {
      autostart: document.getElementById("autostart").checked,
    });
    document.getElementById("doneText").textContent = data.message;
    go(5);
    document.getElementById("steps").style.display = "none";
  } catch (error) {
    setStatus("finishStatus", error.message, "err");
    button.disabled = false;
  }
}

loadState();
</script>
</body>
</html>
"""
