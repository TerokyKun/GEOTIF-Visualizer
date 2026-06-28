const els = {
  canvas: document.getElementById('mapCanvas'),
  stage: document.getElementById('mapStage'),
  loader: document.getElementById('loader'),
  emptyState: document.getElementById('emptyState'),
  statusText: document.getElementById('statusText'),
  filesText: document.getElementById('filesText'),
  modeText: document.getElementById('modeText'),
  coordsText: document.getElementById('coordsText'),
  bestAngle: document.getElementById('bestAngle'),
  bestCorr: document.getElementById('bestCorr'),
  topAngles: document.getElementById('topAngles'),
  zoomSlider: document.getElementById('zoomSlider'),
  zoomValue: document.getElementById('zoomValue'),
  reloadBtn: document.getElementById('reloadBtn'),
  mapModeSwitch: document.getElementById('mapModeSwitch'),
  modeSwitch: document.getElementById('modeSwitch'),
  applyUploadBtn: document.getElementById('applyUploadBtn'),
  resetDemoBtn: document.getElementById('resetDemoBtn'),
  analyzeBtn: document.getElementById('analyzeBtn'),
  fitBtn: document.getElementById('fitBtn'),
  tiffInput: document.getElementById('tiffInput'),
  txtInput: document.getElementById('txtInput'),
  tiffName: document.getElementById('tiffName'),
  txtName: document.getElementById('txtName'),
  mapBadge: document.getElementById('mapBadge'),
  toast: document.getElementById('toast'),
  uploadPanel: document.getElementById('uploadPanel'),
  analysisHint: document.getElementById('analysisHint'),
  analysisArea: document.getElementById('analysisArea'),
  corrCanvas: document.getElementById('corrCanvas'),
  profileCanvas: document.getElementById('profileCanvas'),
};

const ctx = els.canvas.getContext('2d', { alpha: true });
const corrCtx = els.corrCanvas.getContext('2d', { alpha: true });
const profileCtx = els.profileCanvas.getContext('2d', { alpha: true });

const state = {
  project: null,
  image: null,
  analysis: null,
  destination: null,
  view: {
    scale: 1,
    panX: 0,
    panY: 0,
    fitScale: 1,
    minScale: 1,
    maxScale: 1,
  },
  requestId: 0,
  pendingController: null,
  pointers: new Map(),
  gesture: null,
  mapMode: false,
  mode: 'demo',
  analysisVisible: false,
};

function clamp(v, min, max) {
  return Math.min(max, Math.max(min, v));
}

function round1(v) {
  return Math.round(v * 10) / 10;
}

function normalizeAngleDeg(angle) {
  const value = Number(angle);
  if (!Number.isFinite(value)) return null;
  return ((value % 360) + 360) % 360;
}

function displayAngleDeg(angle) {
  const value = normalizeAngleDeg(angle);
  if (value == null) return null;
  return (value + 180) % 360;
}

function rotatePolarValues(values, shift = 180) {
  if (!Array.isArray(values) || !values.length) return [];
  const len = values.length;
  const offset = ((Math.round(shift) % len) + len) % len;
  return values.map((_, index) => values[(index + offset) % len]);
}

function baseName(path) {
  return String(path || '').split('/').pop();
}

function setText(el, text) { if (!el) return; el.textContent = text; }
function setHtml(el, html) { if (!el) return; el.innerHTML = html; }
function setStatus(text) { setText(els.statusText, text); }
function setFiles(text) { setText(els.filesText, text); }
function setMode(text) { setText(els.modeText, text); }
function setCoords(text) { setText(els.coordsText, text); }
function showLoader(show) { if (els.loader) els.loader.classList.toggle('hidden', !show); }

let layoutRaf = 0;
let chartRaf = 0;
let toastTimer = 0;
let resizeObserver = null;

function showToast(message, duration = 2800) {
  if (!els.toast) return;
  setText(els.toast, message);
  els.toast.classList.remove('hidden');
  clearTimeout(toastTimer);
  toastTimer = window.setTimeout(() => {
    if (els.toast) els.toast.classList.add('hidden');
  }, duration);
}

function scheduleLayoutUpdate() {
  if (layoutRaf) cancelAnimationFrame(layoutRaf);
  layoutRaf = requestAnimationFrame(() => {
    layoutRaf = 0;
    resizeAll();
    render();
  });
}

function scheduleChartUpdate() {
  if (chartRaf) cancelAnimationFrame(chartRaf);
  chartRaf = requestAnimationFrame(() => {
    chartRaf = 0;
    renderCharts();
  });
}

function setAnalysisVisible(visible) {
  state.analysisVisible = Boolean(visible);
  if (els.analysisArea) els.analysisArea.classList.toggle('hidden', !visible);
  if (els.analysisHint) els.analysisHint.classList.toggle('hidden', visible);
  if (visible) scheduleLayoutUpdate();
  else scheduleChartUpdate();
}

function updateAnalyzeState() {
  const projectReady = Boolean(state.project && state.image);
  const destinationReady = Boolean(state.destination);
  const modeReady = state.mode === 'demo' || state.project?.mode === 'upload';
  const enabled = projectReady && destinationReady && modeReady;
  els.analyzeBtn.disabled = !enabled;
  els.analyzeBtn.title = enabled
    ? ''
    : (state.mode === 'upload' && state.project?.mode !== 'upload'
      ? 'Сначала загрузите свои файлы'
      : 'Сначала выберите точку 2 на карте');
}

function setZoomUI() {
  if (!els.zoomSlider || !els.zoomValue) return;
  const min = state.view.minScale || 1;
  const max = state.view.maxScale || 1;
  const scale = clamp(state.view.scale || min, min, max);
  const ratio = max > min ? (scale - min) / (max - min) : 0;
  els.zoomSlider.value = String(Math.round(ratio * 100));
  els.zoomValue.textContent = `${Math.round(scale * 100)}%`;
}

function affineToWorld(transform, row, col) {
  const [a, b, c, d, e, f] = transform;
  return { x: a * col + b * row + c, y: d * col + e * row + f };
}

function worldToPixel(transform, x, y) {
  const [a, b, c, d, e, f] = transform;
  const det = a * e - b * d;
  if (Math.abs(det) < 1e-12) return null;
  return {
    col: (e * (x - c) - b * (y - f)) / det,
    row: (-d * (x - c) + a * (y - f)) / det,
  };
}

function sourceToPreviewPixel(point) {
  if (!state.project?.preview_scale) return { row: point.row, col: point.col };
  return {
    row: point.row * state.project.preview_scale.y,
    col: point.col * state.project.preview_scale.x,
  };
}

function previewToSourcePixel(point) {
  if (!state.project?.preview_scale) return { row: point.row, col: point.col };
  return {
    row: point.row / state.project.preview_scale.y,
    col: point.col / state.project.preview_scale.x,
  };
}

function pointerPosition(event) {
  const rect = els.canvas.getBoundingClientRect();
  return { x: event.clientX - rect.left, y: event.clientY - rect.top };
}

function fitView() {
  if (!state.image) return;
  const rect = els.stage.getBoundingClientRect();
  const base = Math.min(rect.width / state.image.width, rect.height / state.image.height);
  state.view.fitScale = clamp(base * 1.02, 0.55, 10);
  state.view.minScale = clamp(state.view.fitScale * 0.68, 0.40, state.view.fitScale);
  state.view.maxScale = clamp(state.view.fitScale * 3.8, state.view.fitScale, 12);
  state.view.scale = clamp(state.view.fitScale, state.view.minScale, state.view.maxScale);
  state.view.panX = 0;
  state.view.panY = 0;
  setZoomUI();
  render();
}

function imageToScreen(x, y) {
  const rect = els.canvas.getBoundingClientRect();
  const centerX = rect.width / 2 + state.view.panX;
  const centerY = rect.height / 2 + state.view.panY;
  return {
    x: centerX + (x - state.image.width / 2) * state.view.scale,
    y: centerY + (y - state.image.height / 2) * state.view.scale,
  };
}

function screenToImage(x, y) {
  const rect = els.canvas.getBoundingClientRect();
  const centerX = rect.width / 2 + state.view.panX;
  const centerY = rect.height / 2 + state.view.panY;
  return {
    x: (x - centerX) / state.view.scale + state.image.width / 2,
    y: (y - centerY) / state.view.scale + state.image.height / 2,
  };
}

function resizeCanvas(canvas, context) {
  const rect = canvas.getBoundingClientRect();
  const dpr = window.devicePixelRatio || 1;
  canvas.width = Math.max(1, Math.round(rect.width * dpr));
  canvas.height = Math.max(1, Math.round(rect.height * dpr));
  context.setTransform(dpr, 0, 0, dpr, 0, 0);
}

function resizeAll() {
  resizeCanvas(els.canvas, ctx);
  resizeCanvas(els.corrCanvas, corrCtx);
  resizeCanvas(els.profileCanvas, profileCtx);
  if (state.image) render();
}

function roundRect(context, x, y, w, h, r) {
  const radius = Math.min(r, w / 2, h / 2);
  context.beginPath();
  context.moveTo(x + radius, y);
  context.arcTo(x + w, y, x + w, y + h, radius);
  context.arcTo(x + w, y + h, x, y + h, radius);
  context.arcTo(x, y + h, x, y, radius);
  context.arcTo(x, y, x + w, y, radius);
  context.closePath();
}

function drawMarker(context, point, fill, stroke, radius, label) {
  context.save();
  context.beginPath();
  context.arc(point.x, point.y, radius, 0, Math.PI * 2);
  context.fillStyle = fill;
  context.fill();
  context.lineWidth = 2;
  context.strokeStyle = stroke;
  context.stroke();

  if (label) {
    const x = point.x + 12;
    const y = point.y - 12;
    context.font = '700 12px Inter, system-ui, sans-serif';
    const w = context.measureText(label).width + 16;
    roundRect(context, x, y - 22, w, 22, 10);
    context.fillStyle = 'rgba(255,255,255,0.92)';
    context.fill();
    context.fillStyle = '#14212a';
    context.textBaseline = 'middle';
    context.fillText(label, x + 8, y - 11);
  }

  context.restore();
}

function drawLine(context, a, b, color, width, alpha = 1) {
  context.save();
  context.globalAlpha = alpha;
  context.beginPath();
  context.moveTo(a.x, a.y);
  context.lineTo(b.x, b.y);
  context.lineWidth = width;
  context.strokeStyle = color;
  context.lineCap = 'round';
  context.stroke();
  context.restore();
}

function drawEmptyChart(context, canvas, title, subtitle = 'Анализ появится после запуска') {
  const rect = canvas.getBoundingClientRect();
  if (rect.width < 2 || rect.height < 2) return;
  context.clearRect(0, 0, rect.width, rect.height);
  context.fillStyle = 'rgba(255,255,255,0.08)';
  context.font = '700 14px Inter, system-ui, sans-serif';
  context.fillText(title, 16, 24);
  context.fillStyle = 'rgba(255,255,255,0.45)';
  context.font = '500 13px Inter, system-ui, sans-serif';
  context.fillText(subtitle, 16, 50);
}

function drawPolarChart(context, canvas, values, options = {}) {
  const rect = canvas.getBoundingClientRect();
  if (rect.width < 2 || rect.height < 2) return;
  context.clearRect(0, 0, rect.width, rect.height);

  if (!values || values.length < 2) return drawEmptyChart(context, canvas, options.title || 'Круг корреляций 360°');

  const finite = values.map((v) => Number(v)).filter((v) => Number.isFinite(v));
  if (!finite.length) return drawEmptyChart(context, canvas, options.title || 'Круг корреляций 360°');

  const displayValues = rotatePolarValues(values, 180);

  const cx = rect.width / 2;
  const cy = rect.height / 2 + 8;
  const outer = Math.max(60, Math.min(Math.min(rect.width, rect.height) * 0.36, 210));
  const inner = outer * 0.14;
  const startColor = getComputedStyle(document.documentElement).getPropertyValue('--accent').trim() || '#60b7db';
  const accent2 = getComputedStyle(document.documentElement).getPropertyValue('--accent-2').trim() || '#8fc7b0';

  const angleStep = 360 / displayValues.length;
  const normalize = (v) => clamp((v + 1) / 2, 0, 1);

  context.save();
  context.translate(cx, cy);

  for (let i = 1; i <= 4; i += 1) {
    const r = inner + ((outer - inner) * i) / 4;
    context.beginPath();
    context.arc(0, 0, r, 0, Math.PI * 2);
    context.strokeStyle = i === 2 ? 'rgba(255,255,255,0.12)' : 'rgba(255,255,255,0.07)';
    context.lineWidth = 1;
    context.stroke();
  }

  for (let deg = 0; deg < 360; deg += 15) {
    const rad = (deg - 90) * Math.PI / 180;
    const major = deg % 30 === 0;
    const r1 = inner * 0.75;
    const r2 = outer * (major ? 1 : 0.95);
    context.beginPath();
    context.moveTo(Math.cos(rad) * r1, Math.sin(rad) * r1);
    context.lineTo(Math.cos(rad) * r2, Math.sin(rad) * r2);
    context.strokeStyle = major ? 'rgba(255,255,255,0.16)' : 'rgba(255,255,255,0.07)';
    context.lineWidth = major ? 1.1 : 1;
    context.stroke();
  }

  const first = displayValues.findIndex((v) => Number.isFinite(Number(v)));
  if (first >= 0) {
    context.beginPath();
    displayValues.forEach((value, index) => {
      const corr = Number(value);
      if (!Number.isFinite(corr)) return;
      const angle = (index * angleStep - 90) * Math.PI / 180;
      const radius = inner + (outer - inner) * normalize(corr);
      const x = Math.cos(angle) * radius;
      const y = Math.sin(angle) * radius;
      if (index === first) context.moveTo(x, y); else context.lineTo(x, y);
    });
    context.closePath();
    context.strokeStyle = startColor;
    context.lineWidth = 2.4;
    context.stroke();
    context.fillStyle = 'rgba(96,183,219,0.16)';
    context.fill();
  }

  const internalBestIndex = Number.isInteger(options.bestIndex) ? ((options.bestIndex % 360) + 360) % 360 : null;
  const bestIndex = internalBestIndex == null ? null : (internalBestIndex + 180) % 360;
  if (bestIndex != null) {
    const bestCorr = Number(displayValues[bestIndex]);
    const angle = (bestIndex - 90) * Math.PI / 180;
    const ray = outer - 6;
    const x = Math.cos(angle) * ray;
    const y = Math.sin(angle) * ray;

    context.beginPath();
    context.moveTo(0, 0);
    context.lineTo(x, y);
    context.strokeStyle = accent2;
    context.lineWidth = 4;
    context.shadowColor = 'rgba(143,199,176,0.25)';
    context.shadowBlur = 10;
    context.stroke();
    context.shadowBlur = 0;

    context.beginPath();
    context.arc(x, y, 6, 0, Math.PI * 2);
    context.fillStyle = accent2;
    context.fill();
    context.strokeStyle = '#fff';
    context.lineWidth = 2;
    context.stroke();
  }

  context.textAlign = 'center';
  context.fillStyle = 'rgba(255,255,255,0.9)';
  context.font = '800 16px Inter, system-ui, sans-serif';
  context.fillText('360°', 0, -10);

  context.font = '700 13px Inter, system-ui, sans-serif';
  context.fillStyle = 'rgba(255,255,255,0.68)';
  const bestLabel = bestIndex != null ? `${bestIndex}°` : '—';
  const bestCorrLabel = bestIndex != null && Number.isFinite(Number(displayValues[bestIndex])) ? Number(displayValues[bestIndex]).toFixed(4) : '—';
  context.fillText(`Лучший ${bestLabel}`, 0, 12);
  context.fillText(`Корреляция ${bestCorrLabel}`, 0, 30);

  context.font = '700 12px Inter, system-ui, sans-serif';
  const labelR = outer + 18;
  [
    [0, '0°'],
    [90, '90°'],
    [180, '180°'],
    [270, '270°'],
  ].forEach(([deg, label]) => {
    const rad = (deg - 90) * Math.PI / 180;
    const x = Math.cos(rad) * labelR;
    const y = Math.sin(rad) * labelR;
    context.fillText(label, x, y + 4);
  });

  context.restore();
}

function drawProfileChart(context, canvas, analysis) {
  const rect = canvas.getBoundingClientRect();
  context.clearRect(0, 0, rect.width, rect.height);

  const ref = analysis?.reference_profile;
  const best = analysis?.best_profile;
  if (!ref?.heights_m?.length || !best?.heights_m?.length) {
    return drawEmptyChart(context, canvas, 'Профили');
  }

  const pad = { left: 18, right: 18, top: 16, bottom: 22 };
  const width = rect.width - pad.left - pad.right;
  const height = rect.height - pad.top - pad.bottom;
  const merged = [ref.heights_m, best.heights_m].flat().filter((v) => Number.isFinite(v));
  if (!merged.length) return drawEmptyChart(context, canvas, 'Профили');

  const minV = Math.min(...merged);
  const maxV = Math.max(...merged);
  const range = Math.max(1e-6, maxV - minV);
  const colors = [
    getComputedStyle(document.documentElement).getPropertyValue('--accent').trim() || '#60b7db',
    getComputedStyle(document.documentElement).getPropertyValue('--dest').trim() || '#d6a05c',
  ];

  context.save();
  context.fillStyle = 'rgba(255,255,255,0.08)';
  context.font = '700 14px Inter, system-ui, sans-serif';
  context.fillText('Профиль высот', pad.left, 24);

  for (let i = 0; i < 5; i += 1) {
    const y = pad.top + (height * i) / 4;
    context.strokeStyle = 'rgba(255,255,255,0.06)';
    context.beginPath();
    context.moveTo(pad.left, y);
    context.lineTo(pad.left + width, y);
    context.stroke();
  }

  [ref.heights_m, best.heights_m].forEach((series, idx) => {
    context.beginPath();
    series.forEach((v, i) => {
      const x = pad.left + (i / Math.max(1, series.length - 1)) * width;
      const y = pad.top + height - ((v - minV) / range) * height;
      if (i === 0) context.moveTo(x, y); else context.lineTo(x, y);
    });
    context.strokeStyle = colors[idx];
    context.lineWidth = idx === 0 ? 2.4 : 2.8;
    context.stroke();
  });

  context.fillStyle = 'rgba(255,255,255,0.72)';
  context.font = '600 12px Inter, system-ui, sans-serif';
  context.fillText(String(Math.round(maxV * 1000) / 1000), pad.left, pad.top + 12);
  context.fillText(String(Math.round(minV * 1000) / 1000), pad.left, pad.top + height - 4);
  context.fillStyle = 'rgba(255,255,255,0.7)';
  context.fillText('референс', pad.left + 66, 24);
  context.fillText('лучший', pad.left + 138, 24);
  context.restore();
}

function renderCharts() {
  const corrRect = els.corrCanvas?.getBoundingClientRect?.();
  const profileRect = els.profileCanvas?.getBoundingClientRect?.();
  if ((corrRect && (corrRect.width < 2 || corrRect.height < 2)) || (profileRect && (profileRect.width < 2 || profileRect.height < 2))) {
    return;
  }
  if (!state.analysis || !state.analysisVisible) {
    drawEmptyChart(corrCtx, els.corrCanvas, 'Круг корреляций 360°');
    drawEmptyChart(profileCtx, els.profileCanvas, 'Профили');
    return;
  }
  drawPolarChart(corrCtx, els.corrCanvas, state.analysis.correlations || [], { bestIndex: state.analysis.best_angle });
  drawProfileChart(profileCtx, els.profileCanvas, state.analysis);
}

function clearAnalysis() {
  state.analysis = null;
  setAnalysisVisible(false);
  if (els.bestAngle) els.bestAngle.textContent = '—';
  if (els.bestCorr) els.bestCorr.textContent = '—';
  if (els.topAngles) els.topAngles.innerHTML = '';
  scheduleChartUpdate();
}

function setResultSummary(result) {
  if (!result) {
    clearAnalysis();
    return;
  }
  state.analysisVisible = true;
  setAnalysisVisible(true);
  const displayBest = displayAngleDeg(result.best_angle);
  if (els.bestAngle) els.bestAngle.textContent = displayBest != null ? `${displayBest}°` : '—';
  if (els.bestCorr) els.bestCorr.textContent = Number.isFinite(result.best_correlation) ? result.best_correlation.toFixed(4) : '—';
  if (els.topAngles) els.topAngles.innerHTML = '';
  for (const item of (result.top_angles || [])) {
    const row = document.createElement('div');
    row.className = 'top-item';
    const corr = Number(item.correlation);
    const display = displayAngleDeg(item.angle);
    row.innerHTML = `<span>${display != null ? `${display}°` : '—'}</span><span>${Number.isFinite(corr) ? corr.toFixed(4) : '—'}</span>`;
    if (els.topAngles) els.topAngles.appendChild(row);
  }
  scheduleLayoutUpdate();
}

function setMapMode(active) {
  state.mapMode = Boolean(active);
  if (els.stage) els.stage.classList.toggle('is-active', state.mapMode);
  if (els.mapBadge) {
    els.mapBadge.classList.toggle('is-active', state.mapMode);
    els.mapBadge.textContent = state.mapMode ? 'Карта активна' : 'Свайп страницы';
  }
  if (els.mapModeSwitch) {
    els.mapModeSwitch.classList.toggle('switch-on', state.mapMode);
    els.mapModeSwitch.setAttribute('aria-checked', state.mapMode ? 'true' : 'false');
  }
}

function setModeUI(mode) {
  state.mode = mode;
  const activeDemo = mode === 'demo';
  if (els.modeSwitch) {
    els.modeSwitch.classList.toggle('switch-on', activeDemo);
    els.modeSwitch.setAttribute('aria-checked', activeDemo ? 'true' : 'false');
  }
  if (els.uploadPanel) els.uploadPanel.classList.toggle('is-open', !activeDemo);
  setMode(activeDemo ? 'Демо' : 'Свои файлы');
  updateAnalyzeState();
  scheduleLayoutUpdate();
}

function resetState() {
  if (state.pendingController) {
    try { state.pendingController.abort(); } catch (_) {}
  }
  state.analysis = null;
  state.destination = null;
  state.pointers.clear();
  state.gesture = null;
  state.view.scale = 1;
  state.view.panX = 0;
  state.view.panY = 0;
  clearAnalysis();
  setCoords('Точка 2 не выбрана');
  updateAnalyzeState();
  scheduleLayoutUpdate();
}

async function fetchBundle(endpoint = '/api/project', method = 'GET') {
  const response = await fetch(endpoint, { method });
  const bundle = await response.json().catch(() => null);
  if (!bundle) throw new Error('Некорректный ответ сервера');
  return { response, bundle };
}

function drawMap() {
  if (!state.image || !state.project) return;
  const rect = els.canvas.getBoundingClientRect();
  ctx.clearRect(0, 0, rect.width, rect.height);

  const centerX = rect.width / 2 + state.view.panX;
  const centerY = rect.height / 2 + state.view.panY;

  ctx.save();
  ctx.translate(centerX, centerY);
  ctx.scale(state.view.scale, state.view.scale);
  ctx.translate(-state.image.width / 2, -state.image.height / 2);
  ctx.drawImage(state.image, 0, 0);
  ctx.restore();

  const startSource = sourceToPreviewPixel(state.project.start_pixel);
  const start = imageToScreen(startSource.col, startSource.row);
  const dest = state.destination ? imageToScreen(state.destination.col, state.destination.row) : null;
  const startColor = getComputedStyle(document.documentElement).getPropertyValue('--start').trim() || '#c06179';
  const destColor = getComputedStyle(document.documentElement).getPropertyValue('--dest').trim() || '#d6a05c';
  const corrColor = getComputedStyle(document.documentElement).getPropertyValue('--corr').trim() || '#8c9eaa';

  if (dest) {
    drawLine(ctx, start, dest, getComputedStyle(document.documentElement).getPropertyValue('--route').trim() || '#7aa7bf', 4.2, 0.95);
    drawLine(ctx, start, dest, 'rgba(255,255,255,0.18)', 1.2, 0.95);
    drawMarker(ctx, dest, destColor, '#fff', 13, '2');
  }

  drawMarker(ctx, start, startColor, '#fff', 14, '1');

  if (state.analysis?.path?.destination?.pixel) {
    const previewDest = sourceToPreviewPixel(state.analysis.path.destination.pixel);
    const analyzed = imageToScreen(previewDest.col, previewDest.row);
    drawLine(ctx, start, analyzed, corrColor, 2.2, 0.75);
  }
}

function render() {
  if (!els.canvas) return;
  const rect = els.canvas.getBoundingClientRect();
  if (rect.width < 2 || rect.height < 2) return;
  if (!state.image || !state.project) {
    ctx.clearRect(0, 0, rect.width, rect.height);
    renderCharts();
    return;
  }

  drawMap();
  renderCharts();
}

function setDestinationFromScreen(screenX, screenY) {
  if (!state.image) return;
  const imagePoint = screenToImage(screenX, screenY);
  state.destination = {
    row: clamp(imagePoint.y, 0, state.image.height - 1),
    col: clamp(imagePoint.x, 0, state.image.width - 1),
  };
  clearAnalysis();
  updateCoords();
  updateAnalyzeState();
  render();
}

function pointHitTest(screenX, screenY, point, radius = 28) {
  if (!point) return false;
  const screen = imageToScreen(point.col, point.row);
  return Math.hypot(screenX - screen.x, screenY - screen.y) <= radius;
}

function startDrag(event) {
  if (!state.image) return;

  const pos = pointerPosition(event);
  const startSource = sourceToPreviewPixel(state.project.start_pixel);
  const destPoint = state.destination;
  const onDest = pointHitTest(pos.x, pos.y, destPoint);
  const onStart = pointHitTest(pos.x, pos.y, startSource);

  els.canvas.setPointerCapture(event.pointerId);
  state.pointers.set(event.pointerId, { x: event.clientX, y: event.clientY });

  if (onDest) {
    state.gesture = { type: 'drag-destination', pointerId: event.pointerId, startX: event.clientX, startY: event.clientY };
    return;
  }

  if (state.mapMode && state.pointers.size >= 2) {
    const pts = [...state.pointers.values()];
    const a = pts[0];
    const b = pts[1];
    state.gesture = {
      type: 'pinch',
      initialDistance: Math.hypot(a.x - b.x, a.y - b.y),
      initialScale: state.view.scale,
      panX: state.view.panX,
      panY: state.view.panY,
      anchorX: (a.x + b.x) / 2 - els.canvas.getBoundingClientRect().left,
      anchorY: (a.y + b.y) / 2 - els.canvas.getBoundingClientRect().top,
    };
    return;
  }

  if (state.mapMode) {
    state.gesture = {
      type: 'pan',
      startX: event.clientX,
      startY: event.clientY,
      panX: state.view.panX,
      panY: state.view.panY,
    };
    return;
  }

  state.gesture = {
    type: 'tap',
    startX: event.clientX,
    startY: event.clientY,
    onStart,
    onDest,
  };
}

function moveDrag(event) {
  if (!state.image || !state.pointers.has(event.pointerId)) return;
  state.pointers.set(event.pointerId, { x: event.clientX, y: event.clientY });
  if (!state.gesture) return;

  if (state.gesture.type === 'pan') {
    state.view.panX = state.gesture.panX + (event.clientX - state.gesture.startX);
    state.view.panY = state.gesture.panY + (event.clientY - state.gesture.startY);
    render();
    return;
  }

  if (state.gesture.type === 'drag-destination') {
    const pos = pointerPosition(event);
    setDestinationFromScreen(pos.x, pos.y);
    return;
  }

  if (state.gesture.type === 'pinch' && state.pointers.size >= 2) {
    const pts = [...state.pointers.values()];
    const a = pts[0];
    const b = pts[1];
    const currentDistance = Math.hypot(a.x - b.x, a.y - b.y);
    if (currentDistance > 0) {
      const scale = state.gesture.initialScale * (currentDistance / state.gesture.initialDistance);
      const rect = els.canvas.getBoundingClientRect();
      const anchorX = state.gesture.anchorX;
      const anchorY = state.gesture.anchorY;
      const before = screenToImage(anchorX, anchorY);
      state.view.scale = clamp(scale, state.view.minScale, state.view.maxScale);
      const after = imageToScreen(before.x, before.y);
      state.view.panX += anchorX - after.x;
      state.view.panY += anchorY - after.y;
      setZoomUI();
      render();
    }
  }
}

async function endDrag(event) {
  const start = state.pointers.get(event.pointerId) || { x: event.clientX, y: event.clientY };
  const moved = Math.hypot(event.clientX - start.x, event.clientY - start.y);
  if (state.pointers.has(event.pointerId)) state.pointers.delete(event.pointerId);

  if (state.gesture?.type === 'drag-destination') {
    state.gesture = null;
    setStatus('Точка 2 выбрана. Нажмите анализ.');
    return;
  }

  if (state.gesture?.type === 'tap') {
    state.gesture = null;
    if (moved <= 8) {
      const pos = pointerPosition(event);
      setDestinationFromScreen(pos.x, pos.y);
      setStatus('Точка 2 выбрана. Нажмите анализ.');
    }
    return;
  }

  if (state.gesture?.type === 'pinch' && state.pointers.size < 2) {
    state.gesture = null;
    return;
  }

  if (state.gesture?.type === 'pan' && state.pointers.size === 0) {
    state.gesture = null;
  }
}

function setZoomScale(nextScale, anchorX = null, anchorY = null) {
  if (!state.image) return;
  const rect = els.canvas.getBoundingClientRect();
  const ax = anchorX ?? rect.width / 2;
  const ay = anchorY ?? rect.height / 2;
  const before = screenToImage(ax, ay);
  state.view.scale = clamp(nextScale, state.view.minScale, state.view.maxScale);
  const after = imageToScreen(before.x, before.y);
  state.view.panX += ax - after.x;
  state.view.panY += ay - after.y;
  setZoomUI();
  render();
}

function zoomBy(factor, anchorX = null, anchorY = null) {
  setZoomScale(state.view.scale * factor, anchorX, anchorY);
}

function onWheel(event) {
  if (!state.image || !state.mapMode) return;
  event.preventDefault();
  const factor = event.deltaY < 0 ? 1.08 : 1 / 1.08;
  const rect = els.canvas.getBoundingClientRect();
  zoomBy(factor, event.clientX - rect.left, event.clientY - rect.top);
}

function updateFileLabels() {
  setText(els.tiffName, baseName(els.tiffInput?.files?.[0]?.name || 'terrain.tif'));
  setText(els.txtName, baseName(els.txtInput?.files?.[0]?.name || 'heights.txt'));
}

async function applyUpload() {
  const tiff = els.tiffInput.files?.[0];
  const profile = els.txtInput.files?.[0];
  if (!tiff || !profile) {
    setStatus('Сначала загрузите GeoTIFF и TXT');
    return;
  }

  setStatus('Загружаю пользовательские файлы…');
  showLoader(true);
  const body = new FormData();
  body.append('tiff', tiff);
  body.append('profile', profile);

  try {
    const response = await fetch('/api/upload', { method: 'POST', body });
    const data = await response.json().catch(() => null);
    if (!response.ok || !data?.ready) {
      throw new Error(data?.detail || 'Не удалось загрузить файлы');
    }
    setModeUI('upload');
    await loadProject(true);
  } catch (error) {
    const message = error?.message || 'Ошибка загрузки файлов';
    setStatus(message);
    showToast(message);
    showLoader(false);
  }
}

async function switchToDemo() {
  try {
    await fetch('/api/demo', { method: 'POST' });
  } catch (_) {}
  setModeUI('demo');
  await loadProject(false);
}

async function loadProject(force = false) {
  showLoader(true);
  setStatus('Проверяю файлы…');
  setFiles('Читаю архив');
  clearAnalysis();
  state.destination = null;
  updateAnalyzeState();

  const endpoint = force ? '/api/reload' : '/api/project';
  const method = force ? 'POST' : 'GET';

  let response;
  let bundle;
  try {
    ({ response, bundle } = await fetchBundle(endpoint, method));
  } catch (error) {
    setStatus('Не удалось связаться с сервером');
    showLoader(false);
    return;
  }

  if (!response.ok || !bundle.ready) {
    state.project = null;
    state.image = null;
    if (els.emptyState) els.emptyState.classList.remove('hidden');
    setFiles((bundle.missing || []).map((x) => x.replaceAll('\\', '/')).join(' · ') || 'Нет данных');
    showToast(bundle.message || 'Файлы проекта не найдены');
    setStatus(bundle.message || 'Файлы проекта не найдены');
    setModeUI(bundle.mode || 'demo');
    showLoader(false);
    updateAnalyzeState();
    return;
  }

  state.project = bundle;
  state.destination = null;
  state.analysis = null;
  state.analysisVisible = false;
  setModeUI(bundle.mode || 'demo');
  setFiles(`${baseName(bundle.files.map)} · ${baseName(bundle.files.heights)}${bundle.files.config ? ` · ${baseName(bundle.files.config)}` : ''}`);
  setStatus(bundle.message || 'Карта готова');
  setCoords('Выберите точку 2 на карте');
  if (els.emptyState) els.emptyState.classList.add('hidden');
  updateAnalyzeState();

  const img = new Image();
  img.onload = () => {
    state.image = img;
    requestAnimationFrame(() => {
      resizeAll();
      fitView();
      render();
      showLoader(false);
      setStatus('Карта готова. Выберите точку 2 и нажмите анализ.');
    });
  };
  img.onerror = () => {
    setStatus('Не удалось загрузить превью карты');
    showLoader(false);
  };
  img.src = `${bundle.preview_url}?t=${Date.now()}`;
}

function updateCoords() {
  if (!state.project || !state.destination) {
    setCoords('Точка 2 не выбрана');
    updateAnalyzeState();
    return;
  }
  const sourceDestination = previewToSourcePixel(state.destination);
  const world = affineToWorld(state.project.raster.transform, sourceDestination.row, sourceDestination.col);
  const start = state.project.start_pixel;
  const startWorld = affineToWorld(state.project.raster.transform, start.row, start.col);
  setCoords(`Старт: ${round1(startWorld.x)}, ${round1(startWorld.y)} · Точка 2: ${round1(world.x)}, ${round1(world.y)}`);
  updateAnalyzeState();
}

async function analyze() {
  if (!state.project || !state.image) return;
  if (!state.destination) {
    setStatus('Сначала выберите точку 2 на карте');
    return;
  }
  if (state.mode === 'upload' && state.project.mode !== 'upload') {
    setStatus('Сначала загрузите файлы в режиме «Свои файлы»');
    return;
  }

  const sourceDestination = previewToSourcePixel(state.destination);
  const world = affineToWorld(state.project.raster.transform, sourceDestination.row, sourceDestination.col);

  if (state.pendingController) {
    try { state.pendingController.abort(); } catch (_) {}
  }
  const controller = new AbortController();
  state.pendingController = controller;
  const currentRequest = ++state.requestId;

  setStatus('Анализирую маршрут…');

  try {
    const response = await fetch('/api/analyze', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        destination_x: world.x,
        destination_y: world.y,
        ...state.project.analysis_defaults,
      }),
      signal: controller.signal,
    });

    const data = await response.json().catch(() => null);
    if (!data) throw new Error('Некорректный ответ анализа');
    if (currentRequest !== state.requestId) return;

    if (!response.ok || !data.ok) {
      setStatus(data.detail || data.message || 'Ошибка анализа');
      showLoader(false);
      return;
    }

    state.analysis = data.analysis;
    state.analysisVisible = true;
    setResultSummary(data.analysis);
    setStatus(data.message || 'Анализ завершён');
    showLoader(false);
    scheduleLayoutUpdate();
  } catch (error) {
    if (error.name === 'AbortError') return;
    setStatus(error.message || 'Ошибка анализа');
    showLoader(false);
  }
}

function initObservers() {
  if (resizeObserver || typeof ResizeObserver === 'undefined') return;
  resizeObserver = new ResizeObserver(() => scheduleLayoutUpdate());
  [els.stage, els.analysisArea, els.corrCanvas, els.profileCanvas].forEach((el) => {
    if (el) resizeObserver.observe(el);
  });
}

function bindUI() {
  els.fitBtn.addEventListener('click', () => fitView());
  els.reloadBtn.addEventListener('click', async () => { await loadProject(true); });
  if (els.mapModeSwitch) {
    const toggleMapMode = () => setMapMode(!state.mapMode);
    els.mapModeSwitch.addEventListener('click', toggleMapMode);
    els.mapModeSwitch.addEventListener('keydown', (event) => {
      if (event.key === 'Enter' || event.key === ' ') {
        event.preventDefault();
        toggleMapMode();
      }
    });
  }
  if (els.modeSwitch) {
    const toggleMode = async () => {
      if (state.mode === 'demo') {
        setModeUI('upload');
        setStatus('Загрузите GeoTIFF и TXT для своего режима');
      } else {
        await switchToDemo();
      }
    };
    els.modeSwitch.addEventListener('click', toggleMode);
    els.modeSwitch.addEventListener('keydown', (event) => {
      if (event.key === 'Enter' || event.key === ' ') {
        event.preventDefault();
        toggleMode();
      }
    });
  }
  els.applyUploadBtn.addEventListener('click', applyUpload);
  els.resetDemoBtn.addEventListener('click', async () => { await switchToDemo(); });
  els.analyzeBtn.addEventListener('click', analyze);
  els.tiffInput.addEventListener('change', updateFileLabels);
  els.txtInput.addEventListener('change', updateFileLabels);
  els.zoomSlider.addEventListener('input', () => {
    if (!state.image) return;
    const ratio = Number(els.zoomSlider.value) / 100;
    const nextScale = state.view.minScale + (state.view.maxScale - state.view.minScale) * ratio;
    setZoomScale(nextScale);
  });

  els.canvas.addEventListener('pointerdown', startDrag);
  els.canvas.addEventListener('pointermove', moveDrag);
  els.canvas.addEventListener('pointerup', endDrag);
  els.canvas.addEventListener('pointercancel', endDrag);
  els.canvas.addEventListener('pointerleave', endDrag);
  els.canvas.addEventListener('wheel', onWheel, { passive: false });

  window.addEventListener('resize', () => resizeAll());
  window.addEventListener('orientationchange', () => setTimeout(() => {
    resizeAll();
    if (state.image) fitView();
  }, 120));
}

function initialMapMode() {
  setMapMode(false);
}

window.addEventListener('load', async () => {
  bindUI();
  initObservers();
  initialMapMode();
  resizeAll();
  updateFileLabels();
  setCoords('Точка 2 не выбрана');
  setAnalysisVisible(false);
  setResultSummary(null);
  showLoader(true);
  setFiles('Ожидание архива');
  setModeUI('demo');
  setMapMode(false);
  await loadProject(false);
});
