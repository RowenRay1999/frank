/**
 * Frank 识别预览窗口 — 渲染脚本
 * Canvas 视觉识别可视化 + 音频频谱可视化
 */

const $ = (id) => document.getElementById(id);

// ─── DOM refs ─────────────────────────────────────────────
const videoCanvas = $('videoCanvas');
const ctx = videoCanvas?.getContext('2d');
const waveformBars = $('waveformBars');
const overlayBars = $('overlayBars');
const voiceprintMatches = $('voiceprintMatches');
const voiceprintSpectrum = $('voiceprintSpectrum');
const inputMeter = $('inputMeter');
const vadMeter = $('vadMeter');
const hudRes = $('hudRes');
const hudFps = $('hudFps');
const hudObj = $('hudObj');
const hudFace = $('hudFace');
const algoLatency = $('algoLatency');

// ─── State ────────────────────────────────────────────────
let latestFrame = null;
let latestDetections = null;
let latestSpectrum = null;
let frameCount = 0;
let lastFpsTime = performance.now();
let currentFps = 0;

// ─── Canvas resize ────────────────────────────────────────
function resizeCanvas() {
  const container = $('visionCanvas');
  if (!container || !videoCanvas) return;
  videoCanvas.width = container.clientWidth;
  videoCanvas.height = container.clientHeight;
}
window.addEventListener('resize', resizeCanvas);

// ─── IPC listeners ────────────────────────────────────────
if (window.frankAPI) {
  window.frankAPI.onPreviewFrame(data => {
    latestFrame = data;
    frameCount++;
    const now = performance.now();
    if (now - lastFpsTime >= 1000) {
      currentFps = Math.round(frameCount / ((now - lastFpsTime) / 1000));
      frameCount = 0;
      lastFpsTime = now;
    }
    drawFrame();
  });

  window.frankAPI.onPreviewDetections(data => {
    latestDetections = data;
  });

  window.frankAPI.onPreviewAudioSpectrum(data => {
    latestSpectrum = data;
    updateAudioVisuals(data);
  });
}

// ─── Canvas rendering ─────────────────────────────────────
let frameImg = new Image();

function drawFrame() {
  if (!latestFrame?.jpeg_base64) return;
  // 快照当前帧和检测结果，防止 onload 异步回调时读取到更新的全局变量
  const snapFrame = latestFrame;
  const snapDetections = latestDetections;
  frameImg.onload = () => {
    if (!ctx || !videoCanvas) return;
    ctx.clearRect(0, 0, videoCanvas.width, videoCanvas.height);
    ctx.drawImage(frameImg, 0, 0, videoCanvas.width, videoCanvas.height);
    drawDetections(snapDetections);
    updateHud(snapFrame, snapDetections);
  };
  frameImg.src = 'data:image/jpeg;base64,' + snapFrame.jpeg_base64;
}

function drawDetections(detections) {
  if (!ctx || !videoCanvas || !detections) return;
  const latestDetections = detections;
  const w = videoCanvas.width;
  const h = videoCanvas.height;

  // Face bounding boxes
  const faces = latestDetections.faces || [];
  faces.forEach(face => {
    const b = face.bbox;
    if (!b) return;
    const x = b.x * w, y = b.y * h, fw = b.width * w, fh = b.height * h;

    ctx.shadowColor = 'oklch(68% 0.22 55 / 50%)';
    ctx.shadowBlur = 14;

    ctx.strokeStyle = 'oklch(68% 0.22 55 / 80%)';
    ctx.lineWidth = 2;
    ctx.strokeRect(x, y, fw, fh);

    ctx.shadowColor = 'transparent';
    ctx.shadowBlur = 0;

    const label = face.identity || 'FACE';
    const conf = face.confidence ? (face.confidence * 100).toFixed(1) + '%' : '';
    ctx.fillStyle = 'rgba(0,0,0,0.8)';
    ctx.fillRect(x, y - 26, Math.max(80, ctx.measureText(label + ' ' + conf).width + 20), 22);

    ctx.fillStyle = 'oklch(72% 0.22 55)';
    ctx.font = '10px "SF Mono", monospace';
    ctx.fillText(label, x + 8, y - 10);

    if (conf) {
      ctx.fillStyle = '#30d158';
      ctx.fillText(conf, x + fw - ctx.measureText(conf).width - 8, y - 10);
    }

    const lms = face.landmarks || [];
    lms.forEach(lm => {
      ctx.fillStyle = 'oklch(72% 0.25 60)';
      ctx.beginPath();
      ctx.arc(lm.x * w, lm.y * h, 3, 0, Math.PI * 2);
      ctx.fill();
    });
  });

  // Object bounding boxes
  const objects = latestDetections.objects || [];
  objects.forEach(obj => {
    const b = obj.bbox;
    if (!b) return;
    const x = b.x * w, y = b.y * h, ow = b.width * w, oh = b.height * h;

    ctx.strokeStyle = 'rgba(100,210,255,0.7)';
    ctx.lineWidth = 1.5;
    ctx.strokeRect(x, y, ow, oh);

    if (obj.label) {
      ctx.fillStyle = 'rgba(0,0,0,0.8)';
      ctx.fillRect(x, y - 22, ctx.measureText(obj.label).width + 16, 18);
      ctx.fillStyle = '#64d2ff';
      ctx.font = '9px "SF Mono", monospace';
      ctx.fillText(obj.label, x + 8, y - 8);
    }
  });

  // Pose skeleton
  const pose = latestDetections.pose_landmarks;
  if (pose?.body_landmarks) {
    drawPoseSkeleton(pose.body_landmarks, w, h, '#64d2ff');
  }
  if (pose?.left_hand_landmarks) {
    drawHandKeypoints(pose.left_hand_landmarks, w, h, '#30d158');
  }
  if (pose?.right_hand_landmarks) {
    drawHandKeypoints(pose.right_hand_landmarks, w, h, '#ff9f0a');
  }

  // Motion tracks
  const tracks = latestDetections.tracks || [];
  tracks.forEach(track => {
    if (track.points?.length < 2) return;
    ctx.strokeStyle = 'rgba(48,209,88,0.4)';
    ctx.lineWidth = 2;
    ctx.setLineDash([4, 3]);
    ctx.beginPath();
    ctx.moveTo(track.points[0].x * w, track.points[0].y * h);
    for (let i = 1; i < track.points.length; i++) {
      ctx.lineTo(track.points[i].x * w, track.points[i].y * h);
    }
    ctx.stroke();
    ctx.setLineDash([]);
  });
}

function drawPoseSkeleton(landmarks, w, h, color) {
  const connections = [
    [11,12],[11,13],[13,15],[12,14],[14,16],[11,23],[12,24],[23,24],
    [23,25],[25,27],[24,26],[26,28],[0,1],[1,2],[2,3],[3,7],[0,4],[4,5],[5,6],[6,8]
  ];
  ctx.strokeStyle = color;
  ctx.lineWidth = 1.5;
  connections.forEach(([i, j]) => {
    if (landmarks[i] && landmarks[j]) {
      const a = landmarks[i], b = landmarks[j];
      if (a[3] > 0.5 && b[3] > 0.5) {
        ctx.beginPath();
        ctx.moveTo(a[0] * w, a[1] * h);
        ctx.lineTo(b[0] * w, b[1] * h);
        ctx.stroke();
      }
    }
  });
  landmarks.forEach((lm, i) => {
    if (lm[3] > 0.5) {
      ctx.fillStyle = color;
      ctx.beginPath();
      ctx.arc(lm[0] * w, lm[1] * h, 3, 0, Math.PI * 2);
      ctx.fill();
    }
  });
}

function drawHandKeypoints(landmarks, w, h, color) {
  if (!landmarks) return;
  landmarks.forEach(lm => {
    ctx.fillStyle = color;
    ctx.beginPath();
    ctx.arc(lm[0] * w, lm[1] * h, 2, 0, Math.PI * 2);
    ctx.fill();
  });
}

function updateHud(snapFrame, snapDetections) {
  if (hudRes && snapFrame) hudRes.textContent = `${snapFrame.width}×${snapFrame.height}`;
  if (hudFps) hudFps.textContent = currentFps.toFixed(1);
  if (hudObj) hudObj.textContent = String((snapDetections?.objects || []).length);
  if (hudFace) hudFace.textContent = String((snapDetections?.faces || []).length);
}

// ─── Audio visuals ────────────────────────────────────────
function updateAudioVisuals(data) {
  if (!data) return;

  if (inputMeter && data.level_db != null) {
    const pct = Math.max(0, Math.min(100, (data.level_db + 60) / 60 * 100));
    inputMeter.style.width = pct + '%';
  }

  if (vadMeter && data.vad_prob != null) {
    vadMeter.style.width = (data.vad_prob * 100) + '%';
  }

  const bins = data.spectrum_bins || [];
  updateBars(waveformBars, bins, 48);
  updateOverlayBars(overlayBars, bins, 32);

  const matches = data.voiceprint_matches || [];
  if (voiceprintMatches) {
    if (matches.length > 0) {
      voiceprintMatches.innerHTML = matches.map(m => `
        <div class="voiceprint-row">
          <span class="voiceprint-label">${m.name || '未知'}</span>
          <span class="voiceprint-score ${m.score > 0.7 ? 'match' : 'no-match'}">${(m.score * 100).toFixed(1)}%</span>
        </div>`).join('');
    } else {
      voiceprintMatches.innerHTML = '<p style="padding:12px;color:var(--muted);font-size:11px;">等待声纹数据…</p>';
    }
  }

  // 延迟显示：等待后端提供真实管线延迟数据
  if (algoLatency && data.pipeline_latency_ms != null) {
    algoLatency.textContent = '延迟 ' + Math.round(data.pipeline_latency_ms) + 'ms';
  }
}

function updateBars(container, bins, targetCount) {
  if (!container) return;
  if (container.children.length === 0) {
    for (let i = 0; i < targetCount; i++) {
      const bar = document.createElement('div');
      bar.className = 'waveform-bar';
      container.appendChild(bar);
    }
  }
  const bars = container.children;
  const step = Math.max(1, Math.floor(bins.length / targetCount));
  for (let i = 0; i < Math.min(bars.length, targetCount); i++) {
    const val = bins[Math.min(i * step, bins.length - 1)] || 0;
    bars[i].style.height = Math.max(4, val * 50) + 'px';
  }
}

function updateOverlayBars(container, bins, targetCount) {
  if (!container) return;
  if (container.children.length === 0) {
    for (let i = 0; i < targetCount; i++) {
      const bar = document.createElement('div');
      bar.className = 'overlay-bar';
      container.appendChild(bar);
    }
  }
  const bars = container.children;
  const step = Math.max(1, Math.floor(bins.length / targetCount));
  for (let i = 0; i < Math.min(bars.length, targetCount); i++) {
    const val = bins[Math.min(i * step, bins.length - 1)] || 0;
    bars[i].style.height = Math.max(2, val * 20) + 'px';
  }
}

// ─── Audio panel collapse ─────────────────────────────────
let audioCollapsed = false;
function toggleAudio() {
  const panel = $('audioPanel');
  const overlay = $('waveformOverlay');
  const btn = $('audioCollapseBtn');
  audioCollapsed = !audioCollapsed;
  if (audioCollapsed) {
    panel?.classList.add('collapsed');
    overlay?.classList.add('visible');
    btn?.classList.add('collapsed');
  } else {
    panel?.classList.remove('collapsed');
    overlay?.classList.remove('visible');
    btn?.classList.remove('collapsed');
  }
}

$('audioCollapseBtn')?.addEventListener('click', toggleAudio);
$('overlayExpandHint')?.addEventListener('click', toggleAudio);

// ─── Audio tab switching ──────────────────────────────────
document.querySelectorAll('.audio-tab').forEach(tab => {
  tab.addEventListener('click', () => {
    document.querySelectorAll('.audio-tab').forEach(t => t.classList.remove('active'));
    document.querySelectorAll('.audio-panel').forEach(p => p.classList.remove('active'));
    tab.classList.add('active');
    const target = $('audio-' + tab.dataset.tab);
    if (target) target.classList.add('active');
  });
});

// ─── Close button ─────────────────────────────────────────
$('btnClose')?.addEventListener('click', () => {
  window.close();
});

// ─── Keyboard shortcuts ───────────────────────────────────
document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape') {
    window.close();
  }
  if (e.key === 'Tab') {
    e.preventDefault();
    const tabs = document.querySelectorAll('.audio-tab');
    const active = document.querySelector('.audio-tab.active');
    const idx = Array.from(tabs).indexOf(active);
    const next = tabs[(idx + 1) % tabs.length];
    if (next) next.click();
  }
  if (e.key === 'a' || e.key === 'A') {
    e.preventDefault();
    toggleAudio();
  }
});

// ─── Init ─────────────────────────────────────────────────
function init() {
  resizeCanvas();
  if (voiceprintSpectrum) {
    for (let i = 0; i < 56; i++) {
      const bar = document.createElement('div');
      bar.className = 'spec-bar';
      bar.style.height = (8 + Math.abs(Math.sin(i * 0.18)) * 30) + 'px';
      voiceprintSpectrum.appendChild(bar);
    }
  }
  console.log('[Frank Preview] Initialized');
}
init();
