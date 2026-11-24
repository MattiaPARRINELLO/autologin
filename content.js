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
      '.swal2-html-container'
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

      const element = trouverPremierElement(liste);
      if (element) {
        resolve(element);
        return;
      }

      const timer = setTimeout(() => {
        observer.disconnect();
        reject(new Error(`Élément introuvable après ${timeout}ms : ${liste.join(' | ')}`));
      }, timeout);

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
      const canvasCible = trouverPremierElement(canvasSelectors);
      if (!canvasCible) {
        throw new Error(`Canvas cible introuvable : ${normaliserSelecteurs(canvasSelectors).join(' | ')}`);
      }

      const SOURCE_WIDTH_DEFAULT = 320;
      const SOURCE_HEIGHT_DEFAULT = 150;
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
        maxX = SOURCE_WIDTH_DEFAULT;
        maxY = SOURCE_HEIGHT_DEFAULT;
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

      console.log(
        `[Signature] ${signatureData.length} points, canvas ${displayWidth}x${displayHeight}, echelle ${scale.toFixed(3)}`
      );

      for (let i = 0; i < signatureData.length; i++) {
        const point = signatureData[i];
        const normalizedX = (point.x - minX) * scale;
        const normalizedY = (point.y - minY) * scale;
        const x = Math.max(0, Math.min(displayWidth, offsetX + normalizedX));
        const y = Math.max(0, Math.min(displayHeight, offsetY + normalizedY));

        // Le popup peut encore bouger légèrement : recalcul à chaque point.
        const rectCourant = canvasCible.getBoundingClientRect();

          const clientX = rectCourant.left + x;
        const clientY = rectCourant.top + y;

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
   * Construit le cadre commun d'une modale (fond, carte, zone d'actions).
   * @param {{id:string, width:string, cardBackground:string, borderColor:string, overlay:string}} options
   */
  function creerModale({ id, width, cardBackground, borderColor, overlay }) {
    const ancienBackdrop = document.getElementById(id);
    if (ancienBackdrop) {
      ancienBackdrop.remove();
    }

    const backdrop = document.createElement('div');
    backdrop.id = id;
    backdrop.style.cssText = [
      'position: fixed',
      'inset: 0',
      `background: ${overlay}`,
      'display: flex',
      'align-items: center',
      'justify-content: center',
      'padding: 20px',
      'z-index: 2147483647'
    ].join(';');

    const card = document.createElement('div');
    card.style.cssText = [
      `width: ${width}`,
      `background: ${cardBackground}`,
      `border: 3px solid ${borderColor}`,
      'border-radius: 18px',
      'box-shadow: 0 30px 70px rgba(0,0,0,0.45)',
      'padding: 28px',
      'font-family: system-ui, -apple-system, Segoe UI, Roboto, Arial, sans-serif',
      'color: #111827',
      'text-align: center'
    ].join(';');

    const actions = document.createElement('div');
    actions.style.cssText = 'display:flex; justify-content:center; gap:12px; flex-wrap:wrap;';

    return { backdrop, card, actions };
  }

  /**
   * Cree un paragraphe ou titre style pour une modale.
   */
  function creerTexte(tag, text, style) {
    const element = document.createElement(tag);
    element.textContent = text;
    element.style.cssText = style;
    return element;
  }

  /**
   * Cree un bouton ou lien d'action de modale.
   */
  function creerAction({ tag = 'button', text, background, color, border, weight, fontSize, href, onClick }) {
    const element = document.createElement(tag);
    element.textContent = text;
    if (tag === 'button') {
      element.type = 'button';
    } else {
      element.href = href || 'https://github.com';
      element.target = '_blank';
      element.rel = 'noopener noreferrer';
    }
    element.style.cssText = [
      `background:${background}`,
      `border:${border || 'none'}`,
      `color:${color}`,
      'border-radius:12px',
      'padding:14px 22px',
      `font-weight:${weight}`,
      `font-size:${fontSize}`,
      'cursor:pointer'
    ].join(';');
    if (tag !== 'button') {
      element.style.textDecoration = 'none';
    }
    if (onClick) {
      element.addEventListener('click', onClick);
    }
    return element;
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
      const { backdrop, card, actions } = creerModale({
        id: 'checkmate-update-confirm-backdrop',
        width: 'min(760px, 100%)',
        cardBackground: 'linear-gradient(165deg, #ffffff 0%, #fef2f2 100%)',
        borderColor: '#dc2626',
        overlay: 'rgba(5, 8, 24, 0.84)'
      });

      const closeWith = (value) => {
        backdrop.remove();
        resolve(value);
      };

      const title = creerTexte(
        'h2',
        'Confirmation requise avant signature',
        'margin:0 0 10px 0; font-size:34px; line-height:1.15; color:#7f1d1d; font-weight:900;'
      );
      const desc = creerTexte(
        'p',
        `Votre version (${currentVersion || 'inconnue'}) est depassee. Derniere version disponible: ${latestVersion || 'inconnue'}.`,
        'margin:0 0 8px 0; color:#1f2937; font-size:18px; line-height:1.45; font-weight:700;'
      );
      const risk = creerTexte(
        'p',
        'Continuer peut provoquer des erreurs de signature ou un pointage invalide.',
        'margin:0 0 18px 0; color:#991b1b; font-size:18px; line-height:1.45; font-weight:800;'
      );

      actions.appendChild(
        creerAction({
          tag: 'a',
          text: 'Mettre a jour maintenant',
          href: latestUrl,
          background: '#dc2626',
          color: '#fff',
          border: '2px solid #991b1b',
          weight: 800,
          fontSize: '18px'
        })
      );
      actions.appendChild(
        creerAction({
          text: 'Continuer quand meme',
          background: '#f59e0b',
          color: '#111827',
          weight: 800,
          fontSize: '18px',
          onClick: () => closeWith(true)
        })
      );
      actions.appendChild(
        creerAction({
          text: 'Annuler la signature',
          background: '#1f2937',
          color: '#fff',
          weight: 700,
          fontSize: '17px',
          onClick: () => closeWith(false)
        })
      );

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
    const bouton = await attendreElement(buttonSelectors, 5000);

    bouton.dispatchEvent(new MouseEvent('mouseenter', { bubbles: true }));
    await attendre(100);
    bouton.dispatchEvent(new MouseEvent('mouseover', { bubbles: true }));
    await attendre(50);
    bouton.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }));
    bouton.dispatchEvent(new MouseEvent('mouseup', { bubbles: true }));
    bouton.click();

    return true;
  }

  // =============================================
  // OVERLAY DE SIGNATURE — Branding CheckMate (violet + échiquier)
  // =============================================

  const OVERLAY_STYLE_ID = 'checkmate-signature-overlay-style';
  const OVERLAY_ID = 'checkmate-signature-overlay';

  function injecterStyleOverlay() {
    if (document.getElementById(OVERLAY_STYLE_ID)) return;
    const style = document.createElement('style');
    style.id = OVERLAY_STYLE_ID;
    style.textContent = `
      #${OVERLAY_ID} {
        position: fixed;
        inset: 0;
        z-index: 2147483647;
        pointer-events: none;
        opacity: 0;
        transition: opacity 0.3s ease;
        background:
          repeating-linear-gradient(0deg, rgba(139, 92, 246, 0.05) 0 20px, transparent 20px 40px),
          repeating-linear-gradient(90deg, rgba(139, 92, 246, 0.05) 0 20px, transparent 20px 40px);
        animation: cm-bg-shift 6s linear infinite;
      }
      #${OVERLAY_ID}.cm-visible { opacity: 1; }
      @keyframes cm-bg-shift {
        from { background-position: 0 0, 0 0; }
        to { background-position: 40px 40px, 40px 40px; }
      }
      #${OVERLAY_ID} .cm-badge {
        position: absolute;
        right: 18px;
        bottom: 18px;
        animation: cm-badge-float 1.8s ease-in-out infinite;
        display: flex;
        align-items: center;
        gap: 10px;
        padding: 10px 14px;
        border-radius: 14px;
        background: rgba(30, 20, 60, 0.78);
        border: 1px solid rgba(139, 92, 246, 0.55);
        color: #e9d5ff;
        font-family: system-ui, -apple-system, Segoe UI, Roboto, sans-serif;
        font-size: 13px;
        font-weight: 600;
        letter-spacing: 0.02em;
        backdrop-filter: blur(6px);
        box-shadow: 0 8px 24px rgba(88, 28, 135, 0.35);
      }
      #${OVERLAY_ID} .cm-board {
        width: 26px;
        height: 26px;
        border-radius: 6px;
        background-image:
          linear-gradient(45deg, #a78bfa 25%, transparent 25%),
          linear-gradient(-45deg, #a78bfa 25%, transparent 25%),
          linear-gradient(45deg, transparent 75%, #a78bfa 75%),
          linear-gradient(-45deg, transparent 75%, #a78bfa 75%);
        background-size: 13px 13px;
        background-position: 0 0, 0 6.5px, 6.5px -6.5px, -6.5px 0;
        animation: cm-board-spin 4s linear infinite;
      }
      @keyframes cm-board-spin {
        from { transform: rotate(0deg); }
        to { transform: rotate(360deg); }
      }
      @keyframes cm-badge-float {
        0%, 100% { transform: translateY(0); }
        50% { transform: translateY(-6px); }
      }
      #${OVERLAY_ID} .cm-text { display: flex; flex-direction: column; line-height: 1.1; }
      #${OVERLAY_ID} .cm-title { font-size: 13px; color: #f5f3ff; }
      #${OVERLAY_ID} .cm-sub { font-size: 11px; color: #c4b5fd; font-weight: 400; }
    `;
    document.head.appendChild(style);
  }

  function afficherOverlaySignature() {
    injecterStyleOverlay();
    if (document.getElementById(OVERLAY_ID)) return;
    const overlay = document.createElement('div');
    overlay.id = OVERLAY_ID;
    overlay.innerHTML = `
      <div class="cm-badge">
        <div class="cm-board"></div>
        <div class="cm-text">
          <span class="cm-title">CheckMate</span>
          <span class="cm-sub">Signature en cours…</span>
        </div>
      </div>
    `;
    document.body.appendChild(overlay);

    // Animation GSAP si disponible, sinon fallback CSS
    if (window.gsap) {
      try {
        window.gsap.fromTo(overlay, { opacity: 0 }, { opacity: 1, duration: 0.3, ease: 'power2.out' });
      } catch (e) {
        overlay.classList.add('cm-visible');
      }
    } else {
      // déclencher la transition CSS
      requestAnimationFrame(() => overlay.classList.add('cm-visible'));
    }
  }

  function percerTrouSignature() {
    const overlay = document.getElementById(OVERLAY_ID);
    if (!overlay) return;
    const canvas = trouverPremierElement(SITE_SELECTORS.signatureCanvas);
    if (!canvas) return;
    const r = canvas.getBoundingClientRect();
    const m = 24;
    const x1 = Math.max(0, r.left - m);
    const y1 = Math.max(0, r.top - m);
    const x2 = Math.min(window.innerWidth, r.right + m);
    const y2 = Math.min(window.innerHeight, r.bottom + m);
    const W = window.innerWidth;
    const H = window.innerHeight;
    overlay.style.clipPath =
      `polygon(evenodd, 0 0, ${W}px 0, ${W}px ${H}px, 0 ${H}px, ` +
      `0 0, ${x1}px ${y1}px, ${x1}px ${y2}px, ${x2}px ${y2}px, ${x2}px ${y1}px, ${x1}px ${y1}px)`;
  }

  function masquerOverlaySignature() {
    const overlay = document.getElementById(OVERLAY_ID);
    if (!overlay) return;
    if (window.gsap) {
      try {
        window.gsap.to(overlay, {
          opacity: 0,
          duration: 0.3,
          ease: 'power2.in',
          onComplete: () => { overlay.remove(); }
        });
        return;
      } catch (e) { /* fallback */ }
    }
    overlay.remove();
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
          afficherOverlaySignature();

          log(`Étape 1/8 — Recherche du bouton signature (${SITE_SELECTORS.signatureButton[0]}, timeout 30s)...`);
          let boutonSignature;
          try {
            boutonSignature = await attendreElement(SITE_SELECTORS.signatureButton, 30000);
            log('Étape 1/8 — Bouton signature trouvé');
          } catch (e) {
            log('Étape 1/8 — Bouton signature introuvable après 30s, aucun cours à signer');
            sendResponse({
              success: false,
              code: 'button-missing',
              error: 'Aucun bouton de signature trouvé sur la page'
            });
            return;
          }

          boutonSignature.click();
          log('Étape 2/8 — Clic sur le bouton signature effectué, attente du canvas...');

          const canvasSelectors = SITE_SELECTORS.signatureCanvas;
          log('Étape 3/8 — Attente du canvas de signature (timeout 15s)...');
          await attendreElement(canvasSelectors, 15000);
          log('Étape 3/8 — Canvas de signature détecté dans le DOM');
          percerTrouSignature();

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

          log('Étape 5/8 — Replay de la signature sur le canvas...');
          await replaySignature(canvasSelectors, result.signatureData);
          log('Étape 5/8 — Signature rejouée avec succès');

          log('Étape 6/8 — Pause de 500ms pour laisser le canvas enregistrer le tracé...');
          await attendre(500);
          log('Étape 6/8 — Pause terminée');

          log(`Étape 7/8 — Clic sur le bouton Enregistrer (${SITE_SELECTORS.signatureSaveButton[0]})...`);
          // Capturer le contenu actuel du swal2 AVANT le clic pour détecter le changement
          const swalAvant = trouverPremierElement(SITE_SELECTORS.confirmationPopup);
          const texteAvant = swalAvant ? swalAvant.textContent.trim() : '';
          log(`Étape 7/8 — Contenu swal2 avant clic: "${texteAvant.substring(0, 80)}..."`);
          await clickValidation(SITE_SELECTORS.signatureSaveButton);
          log('Étape 7/8 — Bouton Enregistrer cliqué');

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
        } finally {
          // S'assurer que l'overlay est retiré dans tous les cas
          setTimeout(masquerOverlaySignature, 600);
        }
      })();
      return true; // Réponse asynchrone
    }

    // --- Action : ping — Vérification que le content script est bien chargé ---
    if (message.action === 'ping') {
      sendResponse({ success: true, message: 'Content script actif' });
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

  console.log('[Pointage Auto] Content script chargé sur:', window.location.href);

})();
