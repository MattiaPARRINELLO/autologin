// =============================================
// Pointage Auto — Content Script (content.js)
// S'injecte sur https://cesar.emineo-education.fr/*
// Fournit les fonctions d'interaction avec le DOM
// =============================================

(() => {
  'use strict';

  // =============================================
  // CONFIG — Sélecteurs CSS du site cible (avec fallback)
  // Modifier uniquement cet objet si le site évolue.
  // =============================================

  const SITE_SELECTORS = {
    signatureButton: [
      'button.buttonPresent',
      'button[class*="buttonPresent"]',
      'button[data-live-action-param*="present"]'
    ],
    signatureCanvas: [
      'canvas[data-written-signature-target="canvas"]',
      'canvas[data-written-signature-target]',
      '.swal2-container canvas'
    ],
    signatureSaveButton: [
      'button[data-live-action-param="signed"]',
      'button[data-live-action-param*="sign"]',
      '.swal2-container button.btn-primary'
    ],
    confirmationPopup: [
      '.swal2-html-container',
      '.swal2-popup .swal2-html-container'
    ]
  };

  // =============================================
  // UTILITAIRES — Délais et attentes
  // =============================================

  /**
   * Normalise une entrée de sélecteurs en tableau
   * @param {string|string[]} selecteurs
   * @returns {string[]}
   */
  function normaliserSelecteurs(selecteurs) {
    return Array.isArray(selecteurs) ? selecteurs : [selecteurs];
  }

  /**
   * Retourne le premier élément trouvé selon l'ordre de priorité des sélecteurs
   * @param {string|string[]} selecteurs
   * @returns {Element|null}
   */
  function trouverPremierElement(selecteurs) {
    const liste = normaliserSelecteurs(selecteurs);
    for (const selecteur of liste) {
      const element = document.querySelector(selecteur);
      if (element) {
        return element;
      }
    }
    return null;
  }

  /**
   * Attendre un certain nombre de millisecondes
   * @param {number} ms - Durée en millisecondes
   * @returns {Promise<void>}
   */
  function attendre(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
  }

  /**
   * Attend que le rectangle du canvas se stabilise (popup/animation).
   * @param {HTMLCanvasElement} canvas
   * @param {number} timeout
   * @returns {Promise<DOMRect>}
   */
  async function attendreCanvasStable(canvas, timeout = 1500) {
    const start = performance.now();
    let stableCount = 0;
    let previousRect = canvas.getBoundingClientRect();

    while (performance.now() - start < timeout) {
      await attendre(80);
      const rect = canvas.getBoundingClientRect();
      const deltaX = Math.abs(rect.left - previousRect.left);
      const deltaY = Math.abs(rect.top - previousRect.top);
      const deltaW = Math.abs(rect.width - previousRect.width);
      const deltaH = Math.abs(rect.height - previousRect.height);

      if (deltaX < 0.5 && deltaY < 0.5 && deltaW < 0.5 && deltaH < 0.5) {
        stableCount += 1;
        if (stableCount >= 3) {
          return rect;
        }
      } else {
        stableCount = 0;
      }

      previousRect = rect;
    }

    return canvas.getBoundingClientRect();
  }

  /**
   * Attendre qu'un élément soit présent dans le DOM
   * Utilise un MutationObserver avec un fallback setTimeout
   * @param {string|string[]} selecteurs - Sélecteur(s) CSS de l'élément attendu
   * @param {number} timeout - Timeout maximal en millisecondes (défaut : 10000)
   * @returns {Promise<Element>} L'élément trouvé
   */
  function attendreElement(selecteurs, timeout = 10000) {
    return new Promise((resolve, reject) => {
      const liste = normaliserSelecteurs(selecteurs);

      // Vérifier si l'élément existe déjà
      const element = trouverPremierElement(liste);
      if (element) {
        resolve(element);
        return;
      }

      // Timer de timeout
      const timer = setTimeout(() => {
        observer.disconnect();
        reject(new Error(`Élément introuvable après ${timeout}ms : ${liste.join(' | ')}`));
      }, timeout);

      // Observer les mutations du DOM
      const observer = new MutationObserver(() => {
        const el = trouverPremierElement(liste);
        if (el) {
          clearTimeout(timer);
          observer.disconnect();
          resolve(el);
        }
      });

      observer.observe(document.body, {
        childList: true,
        subtree: true
      });
    });
  }

  // =============================================
  // HELPERS — Dispatch d'événements multi-API
  // =============================================

  /**
   * Dispatch un PointerEvent sur un élément (silencieux si non supporté)
   */
  function dispatchPointerEvent(target, type, options) {
    try {
      const event = new PointerEvent(type, {
        ...options,
        pointerId: 1,
        pointerType: 'mouse',
        isPrimary: true
      });
      hydrateEventCoordinates(event, options);
      target.dispatchEvent(event);
    } catch (e) { /* PointerEvent non supporté */ }
  }

  /**
   * Certains canvas lisent offsetX/offsetY ou pageX/pageY, mais ces propriétés
   * ne sont pas initialisables via MouseEventInit/PointerEventInit.
   */
  function hydrateEventCoordinates(event, options) {
    const coordinateOverrides = {
      offsetX: options.offsetX,
      offsetY: options.offsetY,
      layerX: options.offsetX,
      layerY: options.offsetY,
      pageX: options.pageX,
      pageY: options.pageY,
      x: options.clientX,
      y: options.clientY
    };

    for (const [key, value] of Object.entries(coordinateOverrides)) {
      if (typeof value !== 'number') {
        continue;
      }

      try {
        Object.defineProperty(event, key, {
          configurable: true,
          get: () => value
        });
      } catch (e) {
        // Certaines implémentations verrouillent déjà ces propriétés.
      }
    }
  }

  /**
   * Crée un MouseEvent synthétique avec les alias de coordonnées utilisés
   * par les librairies de signature les plus courantes.
   */
  function dispatchMouseEvent(target, type, options) {
    const event = new MouseEvent(type, options);
    hydrateEventCoordinates(event, options);
    target.dispatchEvent(event);
  }

  /**
   * Dispatch un TouchEvent sur un élément (silencieux si non supporté)
   * @param {boolean} isEnd - true pour touchend (touches vides)
   */
  function dispatchTouchEvent(target, type, clientX, clientY, isEnd = false) {
    try {
      const touch = new Touch({
        identifier: 0,
        target,
        clientX,
        clientY,
        screenX: window.screenX + clientX,
        screenY: window.screenY + clientY,
        pageX: window.scrollX + clientX,
        pageY: window.scrollY + clientY
      });
      target.dispatchEvent(new TouchEvent(type, {
        bubbles: true,
        cancelable: true,
        touches: isEnd ? [] : [touch],
        targetTouches: isEnd ? [] : [touch],
        changedTouches: [touch]
      }));
    } catch (e) { /* TouchEvent non supporté */ }
  }

  // =============================================
  // REPLAY DE SIGNATURE SUR CANVAS DISTANT
  // =============================================

  /**
   * Rejoue une signature sur un canvas cible en simulant les événements souris
   * Calcule automatiquement le ratio entre le canvas du popup (320x150) et le canvas cible
   *
   * @param {string|string[]} canvasSelectors - Sélecteur(s) CSS du canvas cible
   * @param {Array<{x: number, y: number, type: string}>} signatureData - Coordonnées de la signature
   * @returns {Promise<boolean>} true si la signature a été rejouée avec succès
   */
  async function replaySignature(canvasSelectors, signatureData) {
    try {
      // Récupérer le canvas cible
      const canvasCible = trouverPremierElement(canvasSelectors);
      if (!canvasCible) {
        throw new Error(`Canvas cible introuvable : ${normaliserSelecteurs(canvasSelectors).join(' | ')}`);
      }

      // Dimensions du canvas source (popup) et cible
      const SOURCE_WIDTH_DEFAULT = 320;
      const SOURCE_HEIGHT_DEFAULT = 150;

      // Robustesse legacy: d'anciennes signatures peuvent avoir été capturées
      // dans des dimensions CSS différentes. On adapte la source si nécessaire.
      let inferredMaxX = 0;
      let inferredMaxY = 0;
      for (const point of signatureData) {
        if (typeof point.x === 'number' && point.x > inferredMaxX) inferredMaxX = point.x;
        if (typeof point.y === 'number' && point.y > inferredMaxY) inferredMaxY = point.y;
      }

      const sourceWidth = Math.max(SOURCE_WIDTH_DEFAULT, Math.ceil(inferredMaxX));
      const sourceHeight = Math.max(SOURCE_HEIGHT_DEFAULT, Math.ceil(inferredMaxY));
      const rect = await attendreCanvasStable(canvasCible);

      // IMPORTANT : utiliser les dimensions CSS d'affichage (rect), pas la résolution
      // interne du canvas (canvasCible.width). Les coordonnées d'événements (clientX,
      // offsetX…) sont en pixels CSS — le navigateur/la librairie fait la conversion
      // vers la résolution interne si nécessaire.
      const displayWidth = rect.width;
      const displayHeight = rect.height;

      // Calculer la boîte englobante réelle du tracé pour centrer la signature
      let minX = Number.POSITIVE_INFINITY;
      let minY = Number.POSITIVE_INFINITY;
      let maxX = 0;
      let maxY = 0;

      for (const point of signatureData) {
        if (typeof point.x !== 'number' || typeof point.y !== 'number') continue;
        if (point.x < minX) minX = point.x;
        if (point.y < minY) minY = point.y;
        if (point.x > maxX) maxX = point.x;
        if (point.y > maxY) maxY = point.y;
      }

      if (!Number.isFinite(minX) || !Number.isFinite(minY)) {
        minX = 0;
        minY = 0;
        maxX = sourceWidth;
        maxY = sourceHeight;
      }

      const sourceBoxWidth = Math.max(1, maxX - minX);
      const sourceBoxHeight = Math.max(1, maxY - minY);

      // Conserver le ratio du tracé et le centrer avec une petite marge
      const TARGET_PADDING_RATIO = 0.9;
      const scale = Math.min(
        (displayWidth * TARGET_PADDING_RATIO) / sourceBoxWidth,
        (displayHeight * TARGET_PADDING_RATIO) / sourceBoxHeight
      );

      const drawWidth = sourceBoxWidth * scale;
      const drawHeight = sourceBoxHeight * scale;
      const offsetX = (displayWidth - drawWidth) / 2;
      const offsetY = (displayHeight - drawHeight) / 2;

      console.log(`[Signature] Scale: ${scale}`);
      console.log(`[Signature] Source bbox: min(${minX},${minY}) max(${maxX},${maxY})`);
      console.log(`[Signature] Canvas source estimé: ${sourceWidth}x${sourceHeight}`);
      console.log(`[Signature] Canvas cible (affichage CSS): ${displayWidth}x${displayHeight}`);
      console.log(`[Signature] Canvas cible (résolution interne): ${canvasCible.width}x${canvasCible.height}`);
      console.log(`[Signature] Nombre de points: ${signatureData.length}`);

      // Rejouer chaque point de la signature
      for (let i = 0; i < signatureData.length; i++) {
        const point = signatureData[i];
        const normalizedX = (point.x - minX) * scale;
        const normalizedY = (point.y - minY) * scale;
        const x = Math.max(0, Math.min(displayWidth, offsetX + normalizedX));
        const y = Math.max(0, Math.min(displayHeight, offsetY + normalizedY));

        // Le popup peut encore bouger légèrement : recalcul à chaque point.
        const rectCourant = canvasCible.getBoundingClientRect();

        // Coordonnées dans la page (pour clientX/clientY)
        const clientX = rectCourant.left + x;
        const clientY = rectCourant.top + y;

        // Options communes pour les événements
        const eventOptions = {
          bubbles: true,
          cancelable: true,
          clientX: clientX,
          clientY: clientY,
          pageX: window.scrollX + clientX,
          pageY: window.scrollY + clientY,
          screenX: window.screenX + clientX,
          screenY: window.screenY + clientY,
          offsetX: x,
          offsetY: y,
          button: 0,
          which: point.type === 'end' ? 0 : 1,
          buttons: point.type === 'end' ? 0 : 1
        };

        if (point.type === 'start') {
          dispatchMouseEvent(canvasCible, 'mousedown', eventOptions);
          dispatchPointerEvent(canvasCible, 'pointerdown', eventOptions);
          dispatchTouchEvent(canvasCible, 'touchstart', clientX, clientY);

        } else if (point.type === 'move') {
          dispatchMouseEvent(canvasCible, 'mousemove', eventOptions);
          dispatchPointerEvent(canvasCible, 'pointermove', eventOptions);
          dispatchTouchEvent(canvasCible, 'touchmove', clientX, clientY);
          await attendre(10 + Math.random() * 5);

        } else if (point.type === 'end') {
          dispatchMouseEvent(canvasCible, 'mouseup', eventOptions);
          dispatchPointerEvent(canvasCible, 'pointerup', eventOptions);
          dispatchTouchEvent(canvasCible, 'touchend', clientX, clientY, true);
        }
      }

      console.log('[Signature] Replay terminé avec succès');
      return true;

    } catch (erreur) {
      console.error('[Signature] Erreur lors du replay:', erreur.message);
      throw erreur;
    }
  }

  // =============================================
  // VALIDATION DU POINTAGE
  // =============================================

  /**
   * Affiche une alerte modale dans la page quand l'extension est obsolète.
   * @param {string} currentVersion
   * @param {string} latestVersion
   */
  function afficherAlerteMiseAJourPage(currentVersion, latestVersion, latestUrl) {
    const ancienBackdrop = document.getElementById('checkmate-update-backdrop');
    if (ancienBackdrop) {
      ancienBackdrop.remove();
    }

    const backdrop = document.createElement('div');
    backdrop.id = 'checkmate-update-backdrop';
    backdrop.style.cssText = [
      'position: fixed',
      'inset: 0',
      'background: rgba(5, 8, 24, 0.78)',
      'display: flex',
      'align-items: center',
      'justify-content: center',
      'padding: 20px',
      'z-index: 2147483647'
    ].join(';');

    const card = document.createElement('div');
    card.style.cssText = [
      'width: min(720px, 100%)',
      'background: linear-gradient(165deg, #ffffff 0%, #fff7ed 100%)',
      'border: 3px solid #ef4444',
      'border-radius: 18px',
      'box-shadow: 0 30px 70px rgba(0,0,0,0.45)',
      'padding: 28px',
      'font-family: system-ui, -apple-system, Segoe UI, Roboto, Arial, sans-serif',
      'color: #111827',
      'text-align: center'
    ].join(';');

    const badge = document.createElement('div');
    badge.textContent = 'ACTION REQUISE';
    badge.style.cssText = [
      'display:inline-block',
      'background:#ef4444',
      'color:#fff',
      'font-weight:800',
      'font-size:12px',
      'letter-spacing:1px',
      'padding:7px 12px',
      'border-radius:999px',
      'margin-bottom:14px'
    ].join(';');

    const title = document.createElement('h2');
    title.textContent = 'Votre extension CheckMate n\'est pas a jour';
    title.style.cssText = 'margin:0 0 12px 0; font-size:34px; line-height:1.15; color:#7f1d1d; font-weight:900;';

    const desc = document.createElement('p');
    desc.textContent = `Version installee: ${currentVersion || 'inconnue'} | Derniere version: ${latestVersion || 'inconnue'}`;
    desc.style.cssText = 'margin:0 0 10px 0; color:#1f2937; font-size:18px; line-height:1.5; font-weight:700;';

    const hint = document.createElement('p');
    hint.textContent = 'Mettez a jour maintenant pour corriger les bugs et garantir la fiabilite du pointage.';
    hint.style.cssText = 'margin:0 0 22px 0; color:#374151; font-size:17px; line-height:1.45;';

    const actions = document.createElement('div');
    actions.style.cssText = 'display:flex; justify-content:center; gap:12px; flex-wrap:wrap;';

    const linkBtn = document.createElement('a');
    linkBtn.textContent = 'Mettre a jour maintenant';
    linkBtn.href = latestUrl || 'https://github.com';
    linkBtn.target = '_blank';
    linkBtn.rel = 'noopener noreferrer';
    linkBtn.style.cssText = [
      'background:#dc2626',
      'text-decoration:none',
      'border:2px solid #991b1b',
      'color:#fff',
      'border-radius:12px',
      'padding:14px 22px',
      'font-weight:800',
      'font-size:18px',
      'cursor:pointer',
      'box-shadow: 0 10px 24px rgba(220,38,38,0.35)'
    ].join(';');

    const closeBtn = document.createElement('button');
    closeBtn.type = 'button';
    closeBtn.textContent = 'Plus tard';
    closeBtn.style.cssText = [
      'background:#1f2937',
      'border:none',
      'color:#fff',
      'border-radius:12px',
      'padding:14px 22px',
      'font-weight:700',
      'font-size:17px',
      'cursor:pointer'
    ].join(';');

    closeBtn.addEventListener('click', () => backdrop.remove());

    actions.appendChild(linkBtn);
    actions.appendChild(closeBtn);
    card.appendChild(badge);
    card.appendChild(title);
    card.appendChild(desc);
    card.appendChild(hint);
    card.appendChild(actions);
    backdrop.appendChild(card);
    document.body.appendChild(backdrop);
  }

  /**
   * Demande une confirmation explicite avant de lancer la signature
   * si l'extension n'est pas a jour.
   * @param {string} currentVersion
   * @param {string} latestVersion
   * @param {string} latestUrl
   * @returns {Promise<boolean>} true si l'utilisateur accepte de continuer
   */
  function demanderConfirmationSignatureVersionObsolete(currentVersion, latestVersion, latestUrl) {
    return new Promise((resolve) => {
      const ancienBackdrop = document.getElementById('checkmate-update-confirm-backdrop');
      if (ancienBackdrop) {
        ancienBackdrop.remove();
      }

      const backdrop = document.createElement('div');
      backdrop.id = 'checkmate-update-confirm-backdrop';
      backdrop.style.cssText = [
        'position: fixed',
        'inset: 0',
        'background: rgba(5, 8, 24, 0.84)',
        'display: flex',
        'align-items: center',
        'justify-content: center',
        'padding: 20px',
        'z-index: 2147483647'
      ].join(';');

      const card = document.createElement('div');
      card.style.cssText = [
        'width: min(760px, 100%)',
        'background: linear-gradient(165deg, #ffffff 0%, #fef2f2 100%)',
        'border: 3px solid #dc2626',
        'border-radius: 18px',
        'box-shadow: 0 30px 70px rgba(0,0,0,0.45)',
        'padding: 28px',
        'font-family: system-ui, -apple-system, Segoe UI, Roboto, Arial, sans-serif',
        'color: #111827',
        'text-align: center'
      ].join(';');

      const title = document.createElement('h2');
      title.textContent = 'Confirmation requise avant signature';
      title.style.cssText = 'margin:0 0 10px 0; font-size:34px; line-height:1.15; color:#7f1d1d; font-weight:900;';

      const desc = document.createElement('p');
      desc.textContent = `Votre version (${currentVersion || 'inconnue'}) est depassee. Derniere version disponible: ${latestVersion || 'inconnue'}.`;
      desc.style.cssText = 'margin:0 0 8px 0; color:#1f2937; font-size:18px; line-height:1.45; font-weight:700;';

      const risk = document.createElement('p');
      risk.textContent = 'Continuer peut provoquer des erreurs de signature ou un pointage invalide.';
      risk.style.cssText = 'margin:0 0 18px 0; color:#991b1b; font-size:18px; line-height:1.45; font-weight:800;';

      const actions = document.createElement('div');
      actions.style.cssText = 'display:flex; justify-content:center; gap:12px; flex-wrap:wrap;';

      const updateBtn = document.createElement('a');
      updateBtn.textContent = 'Mettre a jour maintenant';
      updateBtn.href = latestUrl || 'https://github.com';
      updateBtn.target = '_blank';
      updateBtn.rel = 'noopener noreferrer';
      updateBtn.style.cssText = [
        'background:#dc2626',
        'text-decoration:none',
        'border:2px solid #991b1b',
        'color:#fff',
        'border-radius:12px',
        'padding:14px 22px',
        'font-weight:800',
        'font-size:18px',
        'cursor:pointer'
      ].join(';');

      const continueBtn = document.createElement('button');
      continueBtn.type = 'button';
      continueBtn.textContent = 'Continuer quand meme';
      continueBtn.style.cssText = [
        'background:#f59e0b',
        'border:none',
        'color:#111827',
        'border-radius:12px',
        'padding:14px 22px',
        'font-weight:800',
        'font-size:18px',
        'cursor:pointer'
      ].join(';');

      const cancelBtn = document.createElement('button');
      cancelBtn.type = 'button';
      cancelBtn.textContent = 'Annuler la signature';
      cancelBtn.style.cssText = [
        'background:#1f2937',
        'border:none',
        'color:#fff',
        'border-radius:12px',
        'padding:14px 22px',
        'font-weight:700',
        'font-size:17px',
        'cursor:pointer'
      ].join(';');

      const closeWith = (value) => {
        backdrop.remove();
        resolve(value);
      };

      continueBtn.addEventListener('click', () => closeWith(true));
      cancelBtn.addEventListener('click', () => closeWith(false));

      actions.appendChild(updateBtn);
      actions.appendChild(continueBtn);
      actions.appendChild(cancelBtn);
      card.appendChild(title);
      card.appendChild(desc);
      card.appendChild(risk);
      card.appendChild(actions);
      backdrop.appendChild(card);
      document.body.appendChild(backdrop);
    });
  }

  /**
   * Clique sur le bouton de validation du pointage
   * @param {string|string[]} buttonSelectors - Sélecteur(s) CSS du bouton de validation
   * @returns {Promise<boolean>} true si le clic a réussi
   */
  async function clickValidation(buttonSelectors) {
    try {
      const bouton = await attendreElement(buttonSelectors, 5000);
      if (!bouton) {
        throw new Error(`Bouton de validation introuvable : ${normaliserSelecteurs(buttonSelectors).join(' | ')}`);
      }

      // Simuler un survol puis un clic réaliste
      bouton.dispatchEvent(new MouseEvent('mouseenter', { bubbles: true }));
      await attendre(100);
      bouton.dispatchEvent(new MouseEvent('mouseover', { bubbles: true }));
      await attendre(50);
      bouton.click();
      bouton.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }));
      bouton.dispatchEvent(new MouseEvent('mouseup', { bubbles: true }));
      bouton.dispatchEvent(new MouseEvent('click', { bubbles: true }));

      console.log('[Validation] Bouton de validation cliqué');
      return true;

    } catch (erreur) {
      console.error('[Validation] Erreur:', erreur.message);
      throw erreur;
    }
  }

  // =============================================
  // ÉCOUTEUR DE MESSAGES DU BACKGROUND
  // =============================================

  chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {

    // --- Action : lancerSignature — Flux complet de signature automatique ---
    if (message.action === 'lancerSignature') {
      (async () => {
        try {
          // Fonction de log horodaté locale
          const log = (msg) => {
            const t = new Date().toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit', second: '2-digit', fractionalSecondDigits: 3 });
            console.log(`[${t}][Signature] ${msg}`);
          };

          log('Message lancerSignature reçu — démarrage du flux');

          // 1. Chercher le bouton signature (timeout 30s — site lent)
          log(`Étape 1/8 — Recherche du bouton signature (${SITE_SELECTORS.signatureButton[0]}, timeout 30s)...`);
          let boutonSignature;
          try {
            boutonSignature = await attendreElement(SITE_SELECTORS.signatureButton, 30000);
            log('Étape 1/8 — Bouton signature trouvé');
          } catch (e) {
            log('Étape 1/8 — Bouton signature introuvable après 30s, aucun cours à signer');
            sendResponse({ success: false, error: 'Aucun bouton de signature trouvé sur la page' });
            return;
          }

          // 2. Cliquer sur le bouton pour ouvrir le popup de signature
          boutonSignature.click();
          log('Étape 2/8 — Clic sur le bouton signature effectué, attente du canvas...');

          // 3. Attendre l'apparition du canvas de signature (timeout 15s — popup lent)
          const canvasSelectors = SITE_SELECTORS.signatureCanvas;
          log('Étape 3/8 — Attente du canvas de signature (timeout 15s)...');
          await attendreElement(canvasSelectors, 15000);
          log('Étape 3/8 — Canvas de signature détecté dans le DOM');

          // 4. Récupérer les données de signature depuis le storage
          log('Étape 4/8 — Récupération des données de signature depuis chrome.storage.local...');
          const result = await new Promise(resolve => {
            chrome.storage.local.get(['signatureData'], resolve);
          });

          if (!result.signatureData || result.signatureData.length === 0) {
            log('Étape 4/8 — ERREUR: aucune donnée de signature dans le storage');
            sendResponse({ success: false, error: 'Aucune donnée de signature enregistrée dans le storage' });
            return;
          }
          log(`Étape 4/8 — ${result.signatureData.length} points de signature récupérés`);

          // 5. Rejouer la signature sur le canvas
          log('Étape 5/8 — Replay de la signature sur le canvas...');
          await replaySignature(canvasSelectors, result.signatureData);
          log('Étape 5/8 — Signature rejouée avec succès');

          // 6. Attendre que le canvas enregistre le tracé
          log('Étape 6/8 — Pause de 500ms pour laisser le canvas enregistrer le tracé...');
          await attendre(500);
          log('Étape 6/8 — Pause terminée');

          // 7. Cliquer sur le bouton "Enregistrer"
          log(`Étape 7/8 — Clic sur le bouton Enregistrer (${SITE_SELECTORS.signatureSaveButton[0]})...`);
          // Capturer le contenu actuel du swal2 AVANT le clic pour détecter le changement
          const swalAvant = trouverPremierElement(SITE_SELECTORS.confirmationPopup);
          const texteAvant = swalAvant ? swalAvant.textContent.trim() : '';
          log(`Étape 7/8 — Contenu swal2 avant clic: "${texteAvant.substring(0, 80)}..."`);
          await clickValidation(SITE_SELECTORS.signatureSaveButton);
          log('Étape 7/8 — Bouton Enregistrer cliqué');

          // 8. Attendre que le popup de confirmation change (nouveau swal2 ou contenu différent)
          log('Étape 8/8 — Attente du changement de popup (timeout 15s)...');
          const POLL_INTERVAL = 300;
          const MAX_POLLS = 50; // 50 × 300ms = 15s
          let texteConfirmation = '';
          let confirmationTrouvee = false;

          for (let i = 0; i < MAX_POLLS; i++) {
            await attendre(POLL_INTERVAL);
            const swalActuel = trouverPremierElement(SITE_SELECTORS.confirmationPopup);
            if (!swalActuel) continue; // le popup a disparu, attendre le nouveau

            const texteCourant = swalActuel.textContent.trim();
            // Le contenu a changé → c'est le popup de confirmation
            if (texteCourant && texteCourant !== texteAvant) {
              texteConfirmation = texteCourant;
              confirmationTrouvee = true;
              log(`Étape 8/8 — Nouveau popup détecté (tentative ${i + 1}), contenu: "${texteCourant}"`);
              break;
            }
          }

          if (!confirmationTrouvee) {
            log('Étape 8/8 — Timeout: aucun changement de popup détecté après 15s');
            sendResponse({ success: false, error: 'Aucune confirmation reçue après la signature' });
            return;
          }

          if (texteConfirmation.includes('présence') || texteConfirmation.includes('prise en compte') || texteConfirmation.includes('présent')) {
            log('SUCCÈS — Présence confirmée !');
            sendResponse({ success: true });
          } else {
            log(`ÉCHEC — Texte de confirmation inattendu: "${texteConfirmation}"`);
            sendResponse({ success: false, error: `Confirmation inattendue : "${texteConfirmation}"` });
          }

        } catch (erreur) {
          const t = new Date().toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
          console.error(`[${t}][Signature] ERREUR FATALE: ${erreur.message}`);
          console.error(`[${t}][Signature] Stack:`, erreur.stack);
          sendResponse({ success: false, error: erreur.message });
        }
      })();
      return true; // Réponse asynchrone
    }

    // --- Action : ping — Vérification que le content script est bien chargé ---
    if (message.action === 'ping') {
      sendResponse({ success: true, message: 'Content script actif' });
      return false;
    }

    // --- Action : afficherAlerteMiseAJour — Affiche une modale dans la page ---
    if (message.action === 'afficherAlerteMiseAJour') {
      afficherAlerteMiseAJourPage(message.currentVersion, message.latestVersion, message.latestUrl);
      sendResponse({ success: true });
      return false;
    }

    // --- Action : confirmerSignatureVersionObsolete — confirmation utilisateur bloquante ---
    if (message.action === 'confirmerSignatureVersionObsolete') {
      demanderConfirmationSignatureVersionObsolete(
        message.currentVersion,
        message.latestVersion,
        message.latestUrl
      ).then((confirmed) => {
        sendResponse({ success: true, confirmed: !!confirmed });
      }).catch((erreur) => {
        sendResponse({ success: false, confirmed: false, error: erreur.message });
      });
      return true;
    }
  });

  // Log de chargement pour le debug
  console.log('[Pointage Auto] Content script chargé sur:', window.location.href);

})();
