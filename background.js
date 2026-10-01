// =============================================
// Pointage Auto — Service Worker (background.js)
// Orchestre les étapes du pointage automatisé
// =============================================

// --- Constantes ---
const URL_CONNEXION = 'https://cesar.emineo-education.fr/connexion';
const URL_TABLEAU_BORD = 'https://cesar.emineo-education.fr/';
const TIMEOUT_CHARGEMENT = 30000; // 30 secondes (site lent)
const TIMEOUT_REDIRECTION = 30000; // 30 secondes (site lent)
const EXECUTION_LOG_KEY = 'executionLogs';
const MAX_EXECUTION_LOGS = 40;
const NOTIFICATION_STATUS_ID = 'checkmate-pointage-status';
const NOTIFICATION_PROGRESS_ID = 'checkmate-pointage-progress';
const NOTIFICATION_DEDUPE_MS = 1800;
const PROGRESS_STORAGE_KEY = 'pointageProgress';
const GITHUB_REPO = 'MattiaPARRINELLO/CheckMate';
const GITHUB_API_HEADERS = {
  Accept: 'application/vnd.github+json',
  'X-GitHub-Api-Version': '2022-11-28'
};

let derniereNotification = {
  titre: '',
  message: '',
  ts: 0
};

const SITE_SELECTORS = {
  calendrierJour: [
    'div.toastui-calendar-layout.toastui-calendar-day-view',
    '.toastui-calendar-day-view',
    '[class*="toastui-calendar-day-view"]'
  ]
};

/**
 * Persist un log pour affichage dans le popup
 * @param {string} tag
 * @param {string} message
 * @param {'info'|'success'|'error'} level
 */
function appendExecutionLog(tag, message, level = 'info') {
  const entry = {
    id: `${Date.now()}-${Math.random().toString(16).slice(2, 8)}`,
    ts: new Date().toISOString(),
    source: 'background',
    tag,
    message,
    level
  };

  chrome.storage.local.get([EXECUTION_LOG_KEY], (result) => {
    const logs = Array.isArray(result[EXECUTION_LOG_KEY]) ? result[EXECUTION_LOG_KEY] : [];
    logs.unshift(entry);
    chrome.storage.local.set({ [EXECUTION_LOG_KEY]: logs.slice(0, MAX_EXECUTION_LOGS) });
  });
}

/**
 * Log horodaté pour faciliter le debug
 * @param {string} tag - Catégorie du log (ex: 'Étape 1')
 * @param {string} message - Message à afficher
 */
function log(tag, message, level = 'info') {
  const now = new Date().toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit', second: '2-digit', fractionalSecondDigits: 3 });
  console.log(`[${now}][${tag}] ${message}`);
  appendExecutionLog(tag, message, level);
}

/**
 * Compare deux versions x.y.z
 * @param {string} a
 * @param {string} b
 * @returns {number} 1 si a>b, -1 si a<b, 0 si égal
 */
function comparerVersions(a, b) {
  const pa = String(a || '').split('.').map((n) => Number(n) || 0);
  const pb = String(b || '').split('.').map((n) => Number(n) || 0);
  const len = Math.max(pa.length, pb.length);

  for (let i = 0; i < len; i++) {
    const va = pa[i] || 0;
    const vb = pb[i] || 0;
    if (va > vb) return 1;
    if (va < vb) return -1;
  }
  return 0;
}

/**
 * Récupère la dernière version publiée sur GitHub Releases
 * @returns {Promise<string|null>}
 */
async function getDerniereVersionGithub() {
  const repoWebUrl = `https://github.com/${GITHUB_REPO}`;
  const latestUrl = `https://api.github.com/repos/${GITHUB_REPO}/releases/latest`;
  const releasesUrl = `https://api.github.com/repos/${GITHUB_REPO}/releases?per_page=1`;
  const tagsUrl = `https://api.github.com/repos/${GITHUB_REPO}/tags?per_page=1`;
  try {
    log('Mise à jour', `Appel GitHub releases/latest: ${latestUrl}`);

    const response = await fetch(latestUrl, {
      cache: 'no-store',
      headers: GITHUB_API_HEADERS
    });

    if (response.ok) {
      const data = await response.json();
      log('Mise à jour', `Réponse GitHub reçue (id=${data.id || 'n/a'})`);
      const tag = String(data.tag_name || '').trim();
      if (tag) {
        const normalizedTag = tag.replace(/^v/i, '');
        log('Mise à jour', `tag_name brut='${tag}' -> normalisé='${normalizedTag}'`);
        return {
          version: normalizedTag,
          url: data.html_url || `${repoWebUrl}/releases/tag/${tag}`
        };
      }
      log('Mise à jour', 'Aucun tag_name trouvé dans la release GitHub latest', 'error');
    }

    // 404 fréquent si aucune release "latest" n'est publiée (draft/prerelease uniquement)
    let errorBody = '';
    try {
      errorBody = await response.text();
    } catch (_) {
      // ignorer lecture body
    }
    log('Mise à jour', `releases/latest indisponible (${response.status}) pour ${GITHUB_REPO}${errorBody ? ` | body=${errorBody}` : ''}`, 'error');

    // Fallback 1 : première release retournée par /releases
    log('Mise à jour', `Fallback vers releases: ${releasesUrl}`);
    const releasesResponse = await fetch(releasesUrl, {
      cache: 'no-store',
      headers: GITHUB_API_HEADERS
    });
    if (releasesResponse.ok) {
      const releases = await releasesResponse.json();
      if (Array.isArray(releases) && releases.length > 0) {
        // Aligner le fallback sur la logique "latest": publication pleine, pas draft/prerelease.
        const release = releases.find((r) => r && !r.draft && !r.prerelease);
        if (!release) {
          log('Mise à jour', 'Fallback releases: uniquement des drafts/prereleases detectees', 'error');
        } else {
          const releaseTag = String(release.tag_name || '').trim();
          if (releaseTag) {
            const normalizedReleaseTag = releaseTag.replace(/^v/i, '');
            log('Mise à jour', `Fallback releases OK: tag='${releaseTag}' -> '${normalizedReleaseTag}'`);
            return {
              version: normalizedReleaseTag,
              url: release.html_url || `${repoWebUrl}/releases/tag/${releaseTag}`
            };
          }
        }
      }
      log('Mise à jour', 'Fallback releases: aucune release exploitable trouvée', 'error');
    } else {
      log('Mise à jour', `Fallback releases indisponible (${releasesResponse.status})`, 'error');
    }

    // Fallback 2 : premier tag Git
    log('Mise à jour', `Fallback vers tags: ${tagsUrl}`);
    const tagsResponse = await fetch(tagsUrl, {
      cache: 'no-store',
      headers: GITHUB_API_HEADERS
    });
    if (!tagsResponse.ok) {
      log('Mise à jour', `Fallback tags indisponible (${tagsResponse.status})`, 'error');
      return null;
    }

    const tags = await tagsResponse.json();
    if (!Array.isArray(tags) || tags.length === 0) {
      log('Mise à jour', 'Fallback tags: aucun tag trouvé', 'error');
      return null;
    }

    const firstTag = String((tags[0] && tags[0].name) || '').trim();
    if (!firstTag) {
      log('Mise à jour', 'Fallback tags: premier tag invalide', 'error');
      return null;
    }

    const normalizedFirstTag = firstTag.replace(/^v/i, '');
    log('Mise à jour', `Fallback tags OK: tag='${firstTag}' -> '${normalizedFirstTag}'`);
    return {
      version: normalizedFirstTag,
      url: `${repoWebUrl}/tags`
    };
  } catch (e) {
    log('Mise à jour', `Erreur réseau pendant le check version: ${e.message}`, 'error');
    return null;
  }
}

/**
 * Vérifie si l'extension locale est obsolète
 * @returns {Promise<{outdated:boolean,currentVersion:string,latestVersion:string|null,latestUrl:string|null}>}
 */
async function verifierMiseAJour() {
  const currentVersion = chrome.runtime.getManifest().version;
  log('Mise à jour', `Début check version (repo=${GITHUB_REPO}, locale=${currentVersion})`);

  const latestInfo = await getDerniereVersionGithub();
  const latestVersion = latestInfo ? latestInfo.version : null;
  const latestUrl = latestInfo ? latestInfo.url : null;

  if (!latestVersion) {
    log('Mise à jour', 'Check version terminé sans version distante exploitable', 'error');
    return {
      outdated: false,
      currentVersion,
      latestVersion: null,
      latestUrl: null
    };
  }

  const outdated = comparerVersions(latestVersion, currentVersion) > 0;
  log('Mise à jour', `Comparaison versions: locale=${currentVersion}, distante=${latestVersion}, outdated=${outdated}`);

  return {
    outdated,
    currentVersion,
    latestVersion,
    latestUrl
  };
}

// =============================================
// UTILITAIRES
// =============================================

/**
 * Affiche une notification Chrome
 * @param {string} titre - Titre de la notification
 * @param {string} message - Corps de la notification
 * @param {{id?: string, dedupeMs?: number}} options
 */
function afficherNotification(titre, message, options = {}) {
  const id = options.id || NOTIFICATION_STATUS_ID;
  const dedupeMs = typeof options.dedupeMs === 'number' ? options.dedupeMs : NOTIFICATION_DEDUPE_MS;
  const now = Date.now();

  if (
    derniereNotification.titre === titre
    && derniereNotification.message === message
    && (now - derniereNotification.ts) < dedupeMs
  ) {
    log('Notification', `Doublon ignore: ${titre} | ${message}`);
    return;
  }

  derniereNotification = {
    titre,
    message,
    ts: now
  };

  chrome.notifications.create(id, {
    type: 'basic',
    iconUrl: 'icons/icon128.png',
    title: titre,
    message: message
  }, (notificationId) => {
    if (chrome.runtime.lastError) {
      console.warn('Notification échouée:', chrome.runtime.lastError.message);
    }
  });
}

let notificationProgressionCreee = false;

/**
 * Met à jour la notification de progression du pointage.
 * Une seule notification est créée puis mise à jour à chaque étape (pas de spam).
 * L'état est aussi publié dans le storage pour que le popup l'affiche en direct.
 * @param {string} message - Étape en cours
 * @param {number} pourcentage - Avancement (0-100)
 */
function notifierProgression(message, pourcentage) {
  const progress = Math.max(0, Math.min(100, Math.round(pourcentage)));

  chrome.storage.local.set({
    [PROGRESS_STORAGE_KEY]: { message, pourcentage: progress, enCours: true, ts: Date.now() }
  });

  const options = {
    type: 'progress',
    iconUrl: 'icons/icon128.png',
    title: '🕐 Pointage Auto',
    message: message,
    progress: progress,
    silent: true
  };

  if (notificationProgressionCreee) {
    chrome.notifications.update(NOTIFICATION_PROGRESS_ID, options, (maj) => {
      if (chrome.runtime.lastError) return;
      // La notification a été fermée par l'utilisateur → la recréer
      if (!maj) {
        notificationProgressionCreee = false;
        notifierProgression(message, progress);
      }
    });
    return;
  }

  chrome.notifications.create(NOTIFICATION_PROGRESS_ID, options, () => {
    if (chrome.runtime.lastError) {
      console.warn('Notification de progression échouée:', chrome.runtime.lastError.message);
      return;
    }
    notificationProgressionCreee = true;
  });
}

/**
 * Retire la notification de progression et clôt l'état partagé avec le popup.
 */
function terminerProgression() {
  notificationProgressionCreee = false;
  chrome.notifications.clear(NOTIFICATION_PROGRESS_ID, () => {});
  chrome.storage.local.set({
    [PROGRESS_STORAGE_KEY]: { message: '', pourcentage: 0, enCours: false, ts: Date.now() }
  });
}

/**
 * Attend qu'un onglet soit complètement chargé
 * @param {number} tabId - ID de l'onglet
 * @param {number} timeout - Timeout en millisecondes
 * @returns {Promise<void>}
 */
function attendreChargementOnglet(tabId, timeout = TIMEOUT_CHARGEMENT) {
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => {
      chrome.tabs.onUpdated.removeListener(listener);
      reject(new Error('Timeout : la page n\'a pas fini de charger'));
    }, timeout);

    function listener(updatedTabId, changeInfo) {
      if (updatedTabId === tabId && changeInfo.status === 'complete') {
        clearTimeout(timer);
        chrome.tabs.onUpdated.removeListener(listener);
        // Petit délai supplémentaire pour que le DOM soit bien prêt
        setTimeout(resolve, 500);
      }
    }

    chrome.tabs.onUpdated.addListener(listener);
  });
}

/**
 * Attend que l'URL d'un onglet change (redirection post-connexion)
 * @param {number} tabId - ID de l'onglet
 * @param {string} urlActuelle - URL avant la redirection
 * @param {number} timeout - Timeout en millisecondes
 * @returns {Promise<string>} La nouvelle URL
 */
function attendreRedirection(tabId, urlActuelle, timeout = TIMEOUT_REDIRECTION) {
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => {
      chrome.tabs.onUpdated.removeListener(listener);
      reject(new Error('Connexion échouée, vérifiez vos identifiants'));
    }, timeout);

    function listener(updatedTabId, changeInfo, tab) {
      if (updatedTabId === tabId && changeInfo.status === 'complete') {
        // Vérifier que l'URL a changé (n'est plus la page de connexion)
        if (tab.url && !tab.url.includes('/connexion')) {
          clearTimeout(timer);
          chrome.tabs.onUpdated.removeListener(listener);
          // Délai pour que le DOM de la nouvelle page soit prêt
          setTimeout(() => resolve(tab.url), 500);
        }
      }
    }

    chrome.tabs.onUpdated.addListener(listener);
  });
}

/**
 * Attend qu'un sélecteur soit présent dans un onglet, en interrogeant périodiquement le DOM.
 * @param {number} tabId - ID de l'onglet
 * @param {string} selector - Sélecteur CSS à attendre
 * @param {number} timeout - Timeout global en millisecondes
 * @param {number} intervalMs - Intervalle entre deux vérifications
 * @returns {Promise<boolean>} true si trouvé, false sinon
 */
async function attendreSelecteurDansOnglet(tabId, selector, timeout = 45000, intervalMs = 1000) {
  const startedAt = Date.now();
  let tentatives = 0;

  while (Date.now() - startedAt < timeout) {
    tentatives += 1;
    try {
      const found = await executerScript(tabId, (sel) => !!document.querySelector(sel), [selector]);
      if (found) {
        log('Pré-signature', `Sélecteur trouvé: ${selector} (tentative ${tentatives})`);
        return true;
      }
      log('Pré-signature', `Sélecteur non trouvé (${selector}) — tentative ${tentatives}`);
    } catch (e) {
      log('Pré-signature', `Injection indisponible (tentative ${tentatives}) : ${e.message}`);
    }

    await new Promise((resolve) => setTimeout(resolve, intervalMs));
  }

  log('Pré-signature', `Timeout atteint sans trouver: ${selector}`);
  return false;
}

/**
 * Lance le message de signature vers le content script.
 * @param {number} tabId - ID de l'onglet
 * @param {{outdated:boolean,currentVersion:string,latestVersion:string|null,latestUrl:string|null}} updateInfo
 * @returns {Promise<{success: boolean, error?: string}>}
 */
async function lancerSignatureViaContentScript(tabId, updateInfo) {
  const payload = {
    action: 'lancerSignature'
  };

  log('Pointage', `Payload lancerSignature: ${JSON.stringify(payload)}`);

  return new Promise((resolve) => {
    chrome.tabs.sendMessage(tabId, payload, (response) => {
      if (chrome.runtime.lastError) {
        log('Pointage', `Erreur sendMessage: ${chrome.runtime.lastError.message}`);
        resolve({ success: false, error: chrome.runtime.lastError.message });
      } else {
        log('Pointage', `Réponse du content script: ${JSON.stringify(response)}`);
        resolve(response || { success: false, error: 'Aucune réponse du content script' });
      }
    });
  });
}

/**
 * Demande au content script d'afficher l'alerte de mise à jour dans la page.
 * @param {number} tabId
 * @param {{outdated:boolean,currentVersion:string,latestVersion:string|null,latestUrl:string|null}} updateInfo
 */
async function afficherAlerteMiseAJourDansPage(tabId, updateInfo) {
  if (!tabId || !updateInfo || !updateInfo.outdated) {
    return;
  }

  try {
    await new Promise((resolve) => {
      chrome.tabs.sendMessage(tabId, {
        action: 'afficherAlerteMiseAJour',
        currentVersion: updateInfo.currentVersion,
        latestVersion: updateInfo.latestVersion,
        latestUrl: updateInfo.latestUrl
      }, () => {
        if (chrome.runtime.lastError) {
          log('Mise à jour', `Impossible d'afficher la modale en page: ${chrome.runtime.lastError.message}`, 'error');
        } else {
          log('Mise à jour', 'Modale de mise à jour affichée dans la page');
        }
        resolve();
      });
    });
  } catch (e) {
    log('Mise à jour', `Erreur lors de l'affichage de la modale en page: ${e.message}`, 'error');
  }
}

/**
 * Demande une confirmation explicite avant la signature si version obsolete.
 * @param {number} tabId
 * @param {{outdated:boolean,currentVersion:string,latestVersion:string|null,latestUrl:string|null}} updateInfo
 * @returns {Promise<boolean>} true pour continuer, false pour annuler
 */
async function confirmerSignatureSiVersionObsolete(tabId, updateInfo) {
  if (!tabId || !updateInfo || !updateInfo.outdated) {
    return true;
  }

  try {
    const response = await new Promise((resolve) => {
      chrome.tabs.sendMessage(tabId, {
        action: 'confirmerSignatureVersionObsolete',
        currentVersion: updateInfo.currentVersion,
        latestVersion: updateInfo.latestVersion,
        latestUrl: updateInfo.latestUrl
      }, (res) => {
        if (chrome.runtime.lastError) {
          log('Mise à jour', `Impossible d'ouvrir la confirmation en page: ${chrome.runtime.lastError.message}`, 'error');
          resolve({ success: false, confirmed: false });
          return;
        }
        resolve(res || { success: false, confirmed: false });
      });
    });

    const confirmed = !!(response && response.success && response.confirmed);
    log('Mise à jour', `Confirmation utilisateur avant signature: ${confirmed ? 'CONTINUER' : 'ANNULER'}`);
    return confirmed;
  } catch (e) {
    log('Mise à jour', `Erreur confirmation avant signature: ${e.message}`, 'error');
    return false;
  }
}

/**
 * Attend que le content script soit joignable dans l'onglet (ping répété).
 * @param {number} tabId
 * @param {number} timeout - Timeout total en ms (défaut 6000ms)
 * @returns {Promise<boolean>} true si joignable, false si timeout
 */
async function attendrePingContentScript(tabId, timeout = 6000) {
  const startedAt = Date.now();
  while (Date.now() - startedAt < timeout) {
    await new Promise((r) => setTimeout(r, 300));
    try {
      const ok = await new Promise((resolve) => {
        chrome.tabs.sendMessage(tabId, { action: 'ping' }, (res) => {
          if (chrome.runtime.lastError) resolve(false);
          else resolve(!!(res && res.success));
        });
      });
      if (ok) return true;
    } catch (_) {
      // pas encore prêt
    }
  }
  log('Mise à jour', `Content script non joignable après ${timeout}ms (tabId=${tabId})`, 'error');
  return false;
}

/**
 * Exécute un script dans un onglet via chrome.scripting.executeScript
 * @param {number} tabId - ID de l'onglet
 * @param {Function} func - Fonction à exécuter
 * @param {Array} args - Arguments à passer à la fonction
 * @returns {Promise<any>} Résultat de l'exécution
 */
async function executerScript(tabId, func, args = []) {
  try {
    const results = await chrome.scripting.executeScript({
      target: { tabId: tabId },
      func: func,
      args: args
    });
    if (results && results[0]) {
      return results[0].result;
    }
    return null;
  } catch (erreur) {
    console.error('Erreur d\'exécution de script:', erreur);
    throw new Error(`Erreur d'injection de script : ${erreur.message}`);
  }
}

// =============================================
// DÉTECTION DE SESSION ACTIVE
// =============================================

/**
 * Vérifie si l'utilisateur est déjà connecté après chargement de la page de connexion.
 * Contrôle deux indicateurs :
 *  - L'URL de l'onglet (si elle n'est plus /connexion → redirection serveur immédiate)
 *  - La présence du calendrier TOASTUI dans le DOM (indicateur côté client)
 * Attend jusqu'à 4 secondes pour laisser le temps à la redirection de s'opérer.
 * @param {number} tabId - ID de l'onglet
 * @returns {Promise<boolean>} true si déjà connecté
 */
async function verifierSiDejaConnecte(tabId) {
  // Vérification 1 : l'URL a-t-elle déjà changé immédiatement ?
  try {
    const tab = await chrome.tabs.get(tabId);
    log('Session', `URL actuelle: ${tab.url}`);
    if (!tab.url.includes('/connexion')) {
      log('Session', `Redirection immédiate détectée vers: ${tab.url}`);
      return true;
    }
  } catch (e) {
    log('Session', `Erreur lors de la vérification d'URL: ${e.message}`);
    return false;
  }

  // Vérification 2 : attendre jusqu'à 4 secondes et surveiller le DOM
  // Le calendrier TOASTUI peut apparaître après quelques secondes si la session est encore active
  const INTERVALLE_MS = 500;  // vérification toutes les 500ms
  const MAX_TENTATIVES = 8;   // 8 × 500ms = 4 secondes max

  log('Session', `Surveillance DOM pendant ${MAX_TENTATIVES * INTERVALLE_MS}ms (${MAX_TENTATIVES} tentatives)...`);
  for (let i = 0; i < MAX_TENTATIVES; i++) {
    await new Promise(resolve => setTimeout(resolve, INTERVALLE_MS));

    // Vérifier si l'URL a changé (redirection serveur différée)
    try {
      const tabActuelle = await chrome.tabs.get(tabId);
      if (!tabActuelle.url.includes('/connexion')) {
        log('Session', `Tentative ${i + 1}/${MAX_TENTATIVES} — redirection détectée vers: ${tabActuelle.url}`);
        return true;
      }
    } catch (e) {
      log('Session', `Tentative ${i + 1}/${MAX_TENTATIVES} — onglet fermé ou inaccessible`);
      return false;
    }

    // Vérifier la présence du calendrier TOASTUI dans le DOM
    try {
      const calendrierSelectors = SITE_SELECTORS.calendrierJour;
      const calendrierPresent = await executerScript(tabId, (selectors) => {
        return selectors.some((selector) => !!document.querySelector(selector));
      }, [calendrierSelectors]);
      if (calendrierPresent) {
        log('Session', `Tentative ${i + 1}/${MAX_TENTATIVES} — calendrier TOASTUI détecté, session active`);
        return true;
      }
    } catch (e) {
      log('Session', `Tentative ${i + 1}/${MAX_TENTATIVES} — injection impossible (page en chargement)`);
    }
  }

  log('Session', 'Aucun indicateur de session active trouvé après toutes les tentatives');
  return false;
}

// =============================================
// ÉTAPES DU POINTAGE
// =============================================

/**
 * ÉTAPE 1 — Ouvrir la page de connexion dans un nouvel onglet
 * @returns {Promise<number>} ID de l'onglet créé
 */
async function etape1_ouvrirPageConnexion() {
  try {
    log('Étape 1', `Création onglet vers ${URL_CONNEXION}...`);
    const tab = await chrome.tabs.create({ url: URL_CONNEXION, active: true });
    log('Étape 1', `Onglet créé (tabId=${tab.id}), attente du chargement complet (timeout ${TIMEOUT_CHARGEMENT}ms)...`);
    await attendreChargementOnglet(tab.id);
    log('Étape 1', 'Page de connexion chargée');
    return tab.id;
  } catch (erreur) {
    throw new Error(`Étape 1 — Impossible d'ouvrir la page : ${erreur.message}`);
  }
}

/**
 * ÉTAPE 2 — Remplir les champs et soumettre le formulaire de connexion
 * Fonction exécutée DANS l'onglet via chrome.scripting.executeScript
 * @param {string} username - Identifiant
 * @param {string} password - Mot de passe
 * @returns {boolean} true si le formulaire a été soumis
 */
function scriptRemplirFormulaire(username, password) {
  try {
    // Récupérer le setter natif pour contourner les frameworks JS (React, etc.)
    const nativeInputValueSetter = Object.getOwnPropertyDescriptor(
      window.HTMLInputElement.prototype, 'value'
    ).set;

    // --- Champ identifiant ---
    const champUsername = document.querySelector('input#username');
    if (!champUsername) {
      throw new Error('Champ identifiant introuvable (input#username)');
    }
    champUsername.focus();
    champUsername.dispatchEvent(new Event('focus', { bubbles: true }));
    nativeInputValueSetter.call(champUsername, username);
    champUsername.dispatchEvent(new Event('input', { bubbles: true }));
    champUsername.dispatchEvent(new Event('change', { bubbles: true }));
    champUsername.dispatchEvent(new Event('blur', { bubbles: true }));

    // --- Champ mot de passe ---
    const champPassword = document.querySelector('input#password');
    if (!champPassword) {
      throw new Error('Champ mot de passe introuvable (input#password)');
    }
    champPassword.focus();
    champPassword.dispatchEvent(new Event('focus', { bubbles: true }));
    nativeInputValueSetter.call(champPassword, password);
    champPassword.dispatchEvent(new Event('input', { bubbles: true }));
    champPassword.dispatchEvent(new Event('change', { bubbles: true }));
    champPassword.dispatchEvent(new Event('blur', { bubbles: true }));

    // --- Bouton de connexion ---
    const boutonConnexion = document.querySelector('button[type="submit"].btn-primary');
    if (!boutonConnexion) {
      throw new Error('Bouton de connexion introuvable (button[type="submit"].btn-primary)');
    }
    boutonConnexion.click();

    return true;
  } catch (erreur) {
    return { error: erreur.message };
  }
}

/**
 * ÉTAPE 2 — Remplir et soumettre le formulaire
 * @param {number} tabId - ID de l'onglet
 * @param {string} username - Identifiant
 * @param {string} password - Mot de passe
 */
async function etape2_remplirFormulaire(tabId, username, password) {
  try {
    log('Étape 2', 'Injection du script de remplissage...');
    const resultat = await executerScript(tabId, scriptRemplirFormulaire, [username, password]);
    if (resultat && resultat.error) {
      log('Étape 2', `Erreur côté page: ${resultat.error}`);
      throw new Error(resultat.error);
    }
    log('Étape 2', 'Formulaire rempli et soumis avec succès');
  } catch (erreur) {
    throw new Error(`Étape 2 — Échec du remplissage : ${erreur.message}`);
  }
}

/**
 * ÉTAPE 3 — Attendre la redirection après connexion
 * @param {number} tabId - ID de l'onglet
 */
async function etape3_attendreRedirection(tabId) {
  try {
    log('Étape 3', `Attente de la redirection (timeout ${TIMEOUT_REDIRECTION}ms)...`);
    const nouvelleUrl = await attendreRedirection(tabId, URL_CONNEXION);
    log('Étape 3', `Redirection réussie vers: ${nouvelleUrl}`);
    return nouvelleUrl;
  } catch (erreur) {
    throw new Error(`Étape 3 — ${erreur.message}`);
  }
}


// =============================================
// ORCHESTRATEUR PRINCIPAL
// =============================================

/**
 * Exécute toutes les étapes du pointage séquentiellement
 * @returns {Promise<{success: boolean, message: string}>}
 */
async function lancerPointage() {
  let tabId = null;
  let updateInfo = {
    outdated: false,
    currentVersion: chrome.runtime.getManifest().version,
    latestVersion: null,
    latestUrl: null
  };

  try {
    // Vérifier la version au début de chaque pointage
    log('Pointage', 'Pré-étape: vérification de la mise à jour avant toute action');
    updateInfo = await verifierMiseAJour();
    log('Pointage', `Pré-étape: résultat mise à jour -> outdated=${updateInfo.outdated}, locale=${updateInfo.currentVersion}, distante=${updateInfo.latestVersion || 'n/a'}`);

    // Récupérer les identifiants depuis le stockage
    const data = await chrome.storage.local.get(['username', 'password', 'signatureData']);

    if (!data.username || !data.password) {
      throw new Error('Identifiants non configurés');
    }

    // ÉTAPE 1 — Ouvrir la page de connexion
    log('Pointage', 'Démarrage — Étape 1 : ouverture de la page de connexion');
    notifierProgression('Ouverture de la page de connexion…', 10);
    tabId = await etape1_ouvrirPageConnexion();
    log('Pointage', `Étape 1 terminée — onglet créé (tabId=${tabId})`);
    notifierProgression('Page de connexion chargée', 20);

    // Si version obsolète : bloquer immédiatement dès l'ouverture de la page, avant tout login.
    if (updateInfo.outdated) {
      log('Pointage', 'Version obsolète — attente du content script puis confirmation utilisateur...');
      await attendrePingContentScript(tabId);
      const continuer = await confirmerSignatureSiVersionObsolete(tabId, updateInfo);
      if (!continuer) {
        log('Pointage', "Processus annulé par l'utilisateur (version non à jour)", 'error');
        try { chrome.tabs.remove(tabId); } catch (_) { }
        return {
          success: false,
          error: "Signature annulée : version de l'extension non à jour",
          outdated: true,
          currentVersion: updateInfo.currentVersion,
          latestVersion: updateInfo.latestVersion,
          latestUrl: updateInfo.latestUrl
        };
      }
      log('Pointage', 'Utilisateur a confirmé la poursuite malgré la version obsolète');
    }

    // VÉRIFICATION — Session déjà active ?
    log('Pointage', 'Vérification de la session existante...');
    const dejaConnecte = await verifierSiDejaConnecte(tabId);
    log('Pointage', `Résultat vérification session : ${dejaConnecte ? 'CONNECTÉ' : 'NON CONNECTÉ'}`);

    if (dejaConnecte) {
      // L'utilisateur est déjà connecté → passer directement à la signature
      log('Pointage', 'Session active détectée — étapes 2 et 3 ignorées, passage à la signature');
      notifierProgression('Session déjà active — connexion ignorée', 50);
    } else {

      // ÉTAPE 2 — Remplir le formulaire et le soumettre (uniquement si pas encore connecté)
      log('Pointage', 'Étape 2 — Remplissage du formulaire de connexion...');
      notifierProgression('Connexion en cours…', 35);
      await etape2_remplirFormulaire(tabId, data.username, data.password);
      log('Pointage', 'Étape 2 terminée — formulaire soumis');
      notifierProgression('Identifiants envoyés — attente de la redirection…', 45);

      // ÉTAPE 3 — Attendre la redirection post-connexion
      log('Pointage', 'Étape 3 — Attente de la redirection post-connexion (timeout 30s)...');
      await etape3_attendreRedirection(tabId);

      log('Pointage', 'Étape 3 terminée — redirection détectée, connexion réussie');
      notifierProgression('Connexion réussie', 55);
    } // fin du else (connexion nécessaire)

    // ÉTAPE 4 — Préparer la page de signature (site potentiellement lent)
    log('Pointage', 'Étape 4 — Préparation de la page de signature (attente du bouton)...');
    notifierProgression('Recherche du bouton de signature…', 70);
    const boutonPret = await attendreSelecteurDansOnglet(tabId, 'button.buttonPresent', 45000, 1000);
    if (!boutonPret) {
      throw new Error('Le bouton de signature est resté introuvable après attente prolongée (45s)');
    }
    notifierProgression('Bouton de signature détecté', 80);

    // ÉTAPE 5 — Lancer la signature automatique via le content script
    // La confirmation utilisateur de version obsolète est gérée DANS ce flux message.
    log('Pointage', `Étape 5 — Envoi du message 'lancerSignature' au content script (tabId=${tabId})...`);
    notifierProgression('Signature en cours…', 85);

    let resultatSignature = await lancerSignatureViaContentScript(tabId, updateInfo);

    // Retry ciblé: cas fréquent juste après login où le DOM met encore quelques secondes à stabiliser.
    if (!resultatSignature.success && resultatSignature.error && resultatSignature.error.includes('Aucun bouton de signature trouvé')) {
      log('Pointage', 'Étape 5 — Premier essai sans bouton trouvé, attente supplémentaire de 10s puis retry...');
      notifierProgression('Bouton absent — nouvel essai…', 75);
      await new Promise((resolve) => setTimeout(resolve, 10000));
      const boutonRetryPret = await attendreSelecteurDansOnglet(tabId, 'button.buttonPresent', 20000, 1000);
      if (boutonRetryPret) {
        notifierProgression('Signature en cours… (2e essai)', 85);
        resultatSignature = await lancerSignatureViaContentScript(tabId, updateInfo);
      }
    }

    if (!resultatSignature.success) {
      log('Pointage', `Étape 5 échouée: ${resultatSignature.error}`);
      throw new Error(resultatSignature.error || 'Échec de la signature');
    }

    // Signature réussie — Notification finale
    log('Pointage', 'Étape 5 terminée — Signature validée avec succès !', 'success');
    terminerProgression();
    afficherNotification('✅ Pointage Auto', 'Présence pointée et signée avec succès !');

    return {
      success: true,
      message: 'Présence pointée et signée avec succès !',
      outdated: updateInfo.outdated,
      currentVersion: updateInfo.currentVersion,
      latestVersion: updateInfo.latestVersion,
      latestUrl: updateInfo.latestUrl
    };

  } catch (erreur) {
    log('Pointage', `ERREUR FATALE: ${erreur.message}`, 'error');
    console.error('[Pointage] Stack:', erreur.stack);
    terminerProgression();
    afficherNotification('❌ Pointage Auto — Erreur', erreur.message);

    return {
      success: false,
      error: erreur.message,
      outdated: updateInfo.outdated,
      currentVersion: updateInfo.currentVersion,
      latestVersion: updateInfo.latestVersion,
      latestUrl: updateInfo.latestUrl
    };
  }
}

// =============================================
// ÉCOUTEUR DE MESSAGES
// =============================================

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.action === 'lancerPointage') {
    // Exécuter le pointage de manière asynchrone et répondre au popup
    lancerPointage().then((resultat) => {
      sendResponse(resultat);
    }).catch((erreur) => {
      sendResponse({ success: false, error: erreur.message });
    });

    // Retourner true pour indiquer qu'on enverra la réponse de manière asynchrone
    return true;
  }
});
