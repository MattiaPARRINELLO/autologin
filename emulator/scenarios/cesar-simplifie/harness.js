/* Script de liaison du scenario.

   Le JavaScript du vrai CESAR ne connait pas les routes de l'emulateur :
   ce fichier est injecte a la fin de chaque page servie pour rebrancher
   l'affichage de la modale, le trace de la signature et l'enregistrement
   sur /api/signature. Il ne fait rien sur une page sans bouton. */
(function () {
  const trigger = document.querySelector('.buttonPresent');
  const modal = document.getElementById('attendance-modal');
  const canvas = document.getElementById('signature-pad');
  const save = document.getElementById('save-signature');
  const feedback = document.querySelector('.swal2-html-container');
  const points = [];
  let drawing = false;
  let context = null;

  function position(event) {
    const rect = canvas.getBoundingClientRect();
    return {
      x: (event.clientX - rect.left) * (canvas.width / rect.width),
      y: (event.clientY - rect.top) * (canvas.height / rect.height)
    };
  }

  function startDraw(event) {
    drawing = true;
    const point = position(event);
    points.push({ x: point.x, y: point.y, type: 'start' });
    context.beginPath();
    context.moveTo(point.x, point.y);
  }

  function moveDraw(event) {
    if (!drawing) return;
    const point = position(event);
    points.push({ x: point.x, y: point.y, type: 'move' });
    context.lineTo(point.x, point.y);
    context.stroke();
  }

  function endDraw(event) {
    if (!drawing) return;
    drawing = false;
    const point = position(event);
    points.push({ x: point.x, y: point.y, type: 'end' });
    context.stroke();
  }

  function wireCanvas() {
    context = canvas.getContext('2d');
    context.lineWidth = 2.5;
    context.lineCap = 'round';
    context.strokeStyle = '#0f172a';
    canvas.addEventListener('pointerdown', startDraw);
    canvas.addEventListener('pointermove', moveDraw);
    canvas.addEventListener('pointerup', endDraw);
  }

  function openModal() {
    if (!modal) return;
    modal.classList.add('visible');
    modal.setAttribute('aria-hidden', 'false');
  }

  function closeAttendance() {
    if (trigger) trigger.remove();
    if (canvas) canvas.remove();
  }

  async function submitSignature() {
    const response = await fetch('/api/signature', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ points: points })
    });
    const data = await response.json();
    if (feedback) feedback.textContent = data.message;
    if (save) save.disabled = true;
    window.setTimeout(closeAttendance, __ATTENDANCE_CLOSE_DELAY_MS__);
  }

  if (trigger && modal) trigger.addEventListener('click', openModal);
  if (canvas) wireCanvas();
  if (save) save.addEventListener('click', submitSignature);
})();
