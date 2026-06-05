/**
 * Frank (弗兰克) — 渲染进程脚本 v3
 * 全窗口布局 + 面板系统 + 功能面板挂载
 */

// ─── State config ──────────────────────────────────────────
const STATE_CONFIG = {
  Idle:     { orbState: 'breathing', label: '聆听中 · 等待唤醒',   chipCAM: false, chipMIC: false },
  Aware:    { orbState: 'breathing', label: '检测中 · 识别身份',    chipCAM: true,  chipMIC: false },
  Auth:     { orbState: 'breathing', label: '就绪 · 等待唤醒',     chipCAM: true,  chipMIC: false },
  Chat:     { orbState: 'thinking',  label: '对话中 · 正在响应',    chipCAM: true,  chipMIC: true  },
  Degraded: { orbState: 'breathing', label: '降级模式 · 设备不可用', chipCAM: false, chipMIC: false },
};

// ─── Task history (replaces seed data) ─────────────────────
const taskHistory = [];
const MAX_TASK_HISTORY = 50;
let cachedMembers = [];
let cachedPending = [];
let _pipelineReady = false;  // InsightFace 是否就绪（来自 device.status）

function upsertTask(task) {
  if (task.task_id == null) return;  // 防护: 缺少 task_id 的任务丢弃
  const idx = taskHistory.findIndex(t => t.task_id === task.task_id);
  if (idx >= 0) {
    Object.assign(taskHistory[idx], task);
  } else {
    taskHistory.unshift(task);
    if (taskHistory.length > MAX_TASK_HISTORY) taskHistory.pop();
  }
  renderInlineTasks(taskHistory);
}

// ─── DOM refs ─────────────────────────────────────────────
const $ = (id) => document.getElementById(id);
const userAvatar = $('userAvatar');
const userName = $('userName');
const userRole = $('userRole');
const liveTime = $('liveTime');
const notifPreview = $('notifPreview');
const notifText = $('notifText');
const notifCount = $('notifCount');
const chipCAM = $('chipCAM');
const chipMIC = $('chipMIC');
const chipSCR = $('chipSCR');
const frankOrb = $('frankOrb');
const thinkingRings = $('thinkingRings');
const agentLabelText = $('agentLabelText');
const taskCount = $('taskCount');
const taskListScroll = $('taskListScroll');
const convoTopic = $('convoTopic');
const convoMeta = $('convoMeta');
const convoBubbles = $('convoBubbles');
const chatOverlay = $('chatOverlay');
const chatMessages = $('chatMessages');
const chatInput = $('chatInput');
const gestureToast = $('gestureToast');
const gestureIcon = $('gestureIcon');
const gestureText = $('gestureText');
const pauseBanner = $('pauseBanner');
const errorToast = $('errorToast');
const errorMessage = $('errorMessage');

// Helpers
const ROLE_BADGES = { owner: '👑', admin: '🔵', member: '🟢', guest: '⚪', unregistered: '⬜' };
const ROLE_NAMES = { owner: '主人', admin: '管理员', member: '成员', guest: '访客', unregistered: '未登记' };
function getRoleBadge(r) { return ROLE_BADGES[r] || '⚪'; }
function getRoleName(r) { return ROLE_NAMES[r] || '未知'; }
function formatTime(ts) {
  if (ts == null || ts === '') return '—';
  const d = typeof ts === 'number' ? new Date(ts * 1000) : new Date(ts);
  if (isNaN(d.getTime())) return '—';
  const diff = (Date.now() - d.getTime()) / 1000;
  if (diff < 0) return '—';
  if (diff < 60) return '刚刚';
  if (diff < 3600) return `${Math.floor(diff / 60)} 分钟前`;
  if (diff < 86400) return `${Math.floor(diff / 3600)} 小时前`;
  if (diff < 604800) return `${Math.floor(diff / 86400)} 天前`;
  return d.toLocaleDateString('zh-CN');
}
function escAttr(s) { return String(s||'').replace(/\\/g, '\\\\').replace(/'/g, "\\'"); }
function escHtml(s) { return String(s||'').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#39;'); }

// ─── Orb ───────────────────────────────────────────────────
function setOrbState(state) {
  const cfg = STATE_CONFIG[state] || STATE_CONFIG['Idle'];
  if (cfg.orbState === 'thinking') { frankOrb?.classList.add('thinking'); thinkingRings?.classList.add('visible'); }
  else { frankOrb?.classList.remove('thinking'); thinkingRings?.classList.remove('visible'); }
  if (agentLabelText) agentLabelText.textContent = cfg.label;
}
function setChipState(chip, active) { chip?.classList.toggle('active', !!active); }
function updateUserIdentity(id) {
  if (id?.display_name) {
    if (userAvatar) userAvatar.textContent = (id.display_name || '?')[0];
    if (userName) userName.textContent = id.display_name;
    if (userRole) userRole.textContent = getRoleName(id.role);
  } else {
    if (userAvatar) userAvatar.textContent = '?';
    if (userName) userName.textContent = '访客';
    if (userRole) userRole.textContent = '未识别';
  }
}

// ─── Clock ─────────────────────────────────────────────────
function updateTime() {
  if (!liveTime) return;
  const n = new Date();
  liveTime.textContent = n.getHours().toString().padStart(2,'0')+':'+ n.getMinutes().toString().padStart(2,'0');
}

// ─── Toast ─────────────────────────────────────────────────
function showToast(msg, type) {
  const t = document.createElement('div');
  t.className = 'toast toast-'+type; t.textContent = msg; document.body.appendChild(t);
  setTimeout(() => { t.style.opacity='0'; t.style.transition='opacity 0.3s'; setTimeout(() => t.remove(), 300); }, 2000);
}

function showConfirmDialog(title, message, onConfirm) {
  const overlay = document.createElement('div');
  overlay.className = 'confirm-overlay';
  overlay.innerHTML = `
    <div class="confirm-dialog">
      <div class="confirm-dialog-title">${escHtml(title)}</div>
      <div class="confirm-dialog-msg">${escHtml(message)}</div>
      <div class="confirm-dialog-actions">
        <button class="btn-sm" id="_confirmCancel">取消</button>
        <button class="btn-sm btn-danger-outline" id="_confirmOk" style="border-color:var(--danger,#e74c3c);color:var(--danger,#e74c3c);">确认清除</button>
      </div>
    </div>`;
  document.body.appendChild(overlay);
  const close = () => overlay.remove();
  overlay.querySelector('#_confirmCancel').addEventListener('click', close);
  overlay.querySelector('#_confirmOk').addEventListener('click', () => {
    close();
    if (onConfirm) onConfirm();
  });
  overlay.addEventListener('click', (e) => { if (e.target === overlay) close(); });
}

// ═══════════════════════════════════════════════════════════
// PANEL SYSTEM (PanelManager)
// ═══════════════════════════════════════════════════════════
const PanelManager = {
  _current: null,
  open(el) {
    if (!el) return;
    if (this._current && this._current !== el) this.close(this._current);
    el.classList.add('open');
    this._current = el;
    this._syncNav(el);
  },
  close(el) {
    if (!el) return;
    el.classList.remove('open');
    if (this._current === el) { this._current = null; this._syncNav(null); }
  },
  closeAll() {
    document.querySelectorAll('.panel-slide.open').forEach(p => p.classList.remove('open'));
    this._current = null;
    this._syncNav(null);
  },
  isOpen(el) { return el?.classList.contains('open'); },
  _syncNav(el) {
    // Reset all nav items, then activate matching one
    document.querySelectorAll('.route-item').forEach(n => n.classList.remove('active'));
    if (!el) { document.querySelector('[data-panel="taskDetailPanel"]')?.classList.add('active'); return; }
    const panelId = el.id;
    const nav = document.querySelector(`.route-item[data-panel="${panelId}"]`);
    if (nav) nav.classList.add('active');
  }
};

// Panel close button delegation
document.addEventListener('click', (e) => {
  const closeBtn = e.target.closest('.panel-slide-close');
  if (closeBtn) {
    const panelId = closeBtn.dataset.panel;
    const panel = panelId ? $(panelId) : closeBtn.closest('.panel-slide');
    if (panel) PanelManager.close(panel);
  }
});

// ─── openPanel(name) ───────────────────────────────────────
function openPanel(name) {
  const map = {
    identity: 'identityPanel',
    tasks: 'taskDetailPanel',
    roleInfo: 'roleInfoPanel',
    notifications: 'notifPanel',
    settings: 'settingsPanel',
    chat: 'chatOverlay',
  };
  const id = map[name] || name;
  const el = $(id);
  if (el) {
    PanelManager.open(el);  // 先打开面板，再加载数据（loadPersonaPanel 等依赖 isOpen 检查）
    if (name === 'settings') { loadSettings(); loadDeviceLists(); }
    if (name === 'members') refreshMemberPanel();
    if (name === 'identity') loadPersonaPanel();
    if (name === 'tasks') refreshTaskDetailPanel();
  }
}

// Nav item clicks
document.querySelectorAll('.route-item[data-panel]').forEach(nav => {
  nav.addEventListener('click', (e) => {
    e.preventDefault();
    const panelId = nav.dataset.panel;
    const panel = $(panelId);
    if (panel) {
      if (PanelManager.isOpen(panel)) { PanelManager.close(panel); }
      else { openPanel(panelId.replace('Panel','').replace('identity','identity').replace('taskDetail','tasks').replace('notif','notifications').replace('settings','settings')); }
    }
  });
});

// Notification preview click → open notification panel
notifPreview?.addEventListener('click', (e) => { e.preventDefault(); openPanel('notifications'); });

// Task view all
$('taskViewAll')?.addEventListener('click', (e) => { e.preventDefault(); openPanel('tasks'); });

// Convo expand button
$('convoExpandBtn')?.addEventListener('click', () => openPanel('chat'));

// Orb click → open preview window
frankOrb?.addEventListener('click', () => {
  window.frankAPI?.openPreview?.();
});

// Agent label click → open chat
$('agentLabelText')?.addEventListener('click', (e) => {
  e.stopPropagation();
  openPanel('chat');
});

// ─── Keyboard shortcuts ───────────────────────────────────
document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape') {
    if (PanelManager._current) { PanelManager.close(PanelManager._current); return; }
  }
  if (e.key === ' ' && e.target === document.body) {
    e.preventDefault();
    if (PanelManager.isOpen(chatOverlay)) { PanelManager.close(chatOverlay); }
    else { PanelManager.open(chatOverlay); }
  }
});

// ═══════════════════════════════════════════════════════════
// CHAT OVERLAY
// ═══════════════════════════════════════════════════════════
function openChat() { PanelManager.open(chatOverlay); }
function closeChat() { PanelManager.close(chatOverlay); }

function sendMessage() {
  const msg = chatInput?.value.trim();
  if (!msg) return;
  // Append user bubble to chat overlay
  const div = document.createElement('div');
  div.className = 'chat-bubble user'; div.textContent = msg;
  chatMessages?.appendChild(div);
  if (chatInput) chatInput.value = '';
  if (chatMessages) chatMessages.scrollTop = chatMessages.scrollHeight;
  // Update inline preview
  const now = new Date();
  const ts = now.getHours().toString().padStart(2,'0')+':'+ now.getMinutes().toString().padStart(2,'0');
  if (convoTopic) convoTopic.textContent = msg.length > 20 ? msg.substring(0,20)+'…' : msg;
  if (convoMeta) convoMeta.textContent = '刚刚 · 共 '+chatMessages.querySelectorAll('.chat-bubble').length+' 条消息';
  const b = document.createElement('div');
  b.className = 'convo-bubble user';
  b.innerHTML = `<div class="convo-bubble-sender">用户</div>${escHtml(msg)}<div class="convo-bubble-time">${ts}</div>`;
  convoBubbles?.appendChild(b);
  if (convoBubbles) convoBubbles.scrollTop = convoBubbles.scrollHeight;
  // Send to server
  window.frankAPI?.sendMessage?.({ type: 'chat.text', payload: { text: msg } });
}

$('chatSendBtn')?.addEventListener('click', sendMessage);
chatInput?.addEventListener('keypress', (e) => { if (e.key === 'Enter') sendMessage(); });

// ═══════════════════════════════════════════════════════════
// SETTINGS PANEL
// ═══════════════════════════════════════════════════════════
let canAutoSave = false;

let _settingsLoadTimer = null;

function loadSettings() {
  $('settingsLoading')?.classList.remove('hidden');
  $('settingsError')?.classList.add('hidden');
  $('settingsForm')?.classList.add('hidden');
  window.frankAPI?.sendMessage?.({ type: 'settings.get' });
  // 8s timeout fallback
  if (_settingsLoadTimer) clearTimeout(_settingsLoadTimer);
  _settingsLoadTimer = setTimeout(() => {
    $('settingsLoading')?.classList.add('hidden');
    const errEl = $('settingsError');
    if (errEl) { errEl.classList.remove('hidden'); $('settingsErrorText').textContent = '配置加载超时，请确认服务已启动'; }
    _settingsLoadTimer = null;
  }, 8000);
}

function populateSettingsForm(config) {
  if (_settingsLoadTimer) { clearTimeout(_settingsLoadTimer); _settingsLoadTimer = null; }
  $('settingsLoading')?.classList.add('hidden');
  $('settingsError')?.classList.add('hidden');
  $('settingsForm')?.classList.remove('hidden');
  const flat = flattenConfig(config || {});
  document.querySelectorAll('#settingsForm [data-key]').forEach(el => {
    let val = flat[el.dataset.key];
    if (val === undefined) return;
    if (el.type === 'range') {
      // tts.volume: YAML stores 0.0-1.0, UI slider uses 0-100
      if (el.dataset.key === 'tts.volume') val = Math.round(val * 100);
      el.value = val;
      const d = document.querySelector(`[data-for="${el.dataset.key}"]`); if (d) d.textContent = val;
    }
    else if (el.type === 'checkbox') el.checked = !!val;
    else if (el.tagName === 'SELECT') el.value = String(val);
    else el.value = val;
  });
  canAutoSave = true;
}

function flattenConfig(obj, prefix) {
  prefix = prefix || '';
  const r = {};
  for (const [k, v] of Object.entries(obj || {})) {
    const key = prefix ? prefix+'.'+k : k;
    if (v && typeof v === 'object' && !Array.isArray(v)) Object.assign(r, flattenConfig(v, key));
    else r[key] = v;
  }
  return r;
}

function unflattenConfig(flat) {
  const r = {};
  for (const [key, value] of Object.entries(flat)) {
    const parts = key.split('.');
    let cur = r;
    for (let i = 0; i < parts.length - 1; i++) { if (!cur[parts[i]]) cur[parts[i]] = {}; cur = cur[parts[i]]; }
    cur[parts[parts.length - 1]] = value;
  }
  return r;
}

$('settingsForm')?.addEventListener('change', (e) => {
  if (!canAutoSave) return;
  const el = e.target;
  if (!el.dataset.key) return;
  let value;
  if (el.type === 'range') {
    value = parseFloat(el.value);
    // tts.volume: UI slider 0-100 → YAML 0.0-1.0
    if (el.dataset.key === 'tts.volume') value = Math.round(value) / 100;
    const d = document.querySelector(`[data-for="${el.dataset.key}"]`); if (d) d.textContent = el.value;
  }
  else if (el.type === 'checkbox') value = el.checked;
  else if (el.type === 'number') value = parseInt(el.value, 10);
  else value = el.value;
  window.frankAPI?.sendMessage?.({ type: 'settings.update', payload: unflattenConfig({ [el.dataset.key]: value }) });
  // 设备热切换 toast 提示
  if (el.dataset.key === 'camera.device_id') showToast('📷 摄像头已切换，即时生效', 'success');
  if (el.dataset.key === 'microphone.device_id') showToast('🎤 麦克风已切换，即时生效', 'success');
});

$('settingsForm')?.addEventListener('input', (e) => {
  if (e.target.type === 'range') { const d = document.querySelector(`[data-for="${e.target.dataset.key}"]`); if (d) d.textContent = e.target.value; }
});

// Group collapse
$('settingsContent')?.addEventListener('click', (e) => {
  const title = e.target.closest('.settings-section-title');
  if (!title) return;
  const section = title.dataset.section;
  const group = document.getElementById('section-' + section);
  const icon = title.querySelector('.collapse-icon');
  if (group) { group.classList.toggle('hidden'); if (icon) icon.textContent = group.classList.contains('hidden') ? '▸' : '▾'; }
});

// Device lists
function loadDeviceLists() {
  // 请求后端枚举系统设备（返回整数索引，兼容 PyAudio/OpenCV）
  window.frankAPI?.sendMessage?.({ type: 'audio.devices' });
  window.frankAPI?.sendMessage?.({ type: 'camera.devices' });
}

// 填充麦克风设备下拉
function _populateMicDevices(devices) {
  const sel = $('selectMic');
  if (!sel) return;
  const currentVal = sel.value;
  sel.innerHTML = '<option value="">默认设备</option>' +
    devices.map(d => `<option value="${d.index}">${d.name}</option>`).join('');
  // 恢复选中值
  if (currentVal) sel.value = currentVal;
}

// 填充摄像头设备下拉
function _populateCamDevices(devices) {
  const sel = $('selectCam');
  if (!sel) return;
  const currentVal = sel.value;
  sel.innerHTML = '<option value="0">默认设备</option>' +
    devices.map(d => `<option value="${d.index}">${d.name}</option>`).join('');
  if (currentVal) sel.value = currentVal;
}

// ═══════════════════════════════════════════════════════════
// VIEW ROUTING (main ↔ memberManagement)
// ═══════════════════════════════════════════════════════════
let currentView = 'main';

function navigateTo(view) {
  currentView = view;
  const mainStage = document.querySelector('.main-stage');
  const mmgView = $('memberManagementView');
  if (mainStage) mainStage.classList.toggle('hidden', view !== 'main');
  if (mmgView) mmgView.classList.toggle('hidden', view !== 'memberManagement');
  if (view === 'memberManagement') {
    loadMemberManagementPage();
  }
}

function loadMemberManagementPage() {
  window.frankAPI?.sendMessage?.({ type: 'member.list' });
  window.frankAPI?.sendMessage?.({ type: 'member.stats' });
}

function renderMemberManagementList(members) {
  if (currentView !== 'memberManagement') return;
  const list = $('memberMgmtList');
  const empty = $('memberMgmtEmpty');
  if (!list) return;
  list.innerHTML = '';
  if (!members || !members.length) {
    if (empty) empty.classList.remove('hidden');
    return;
  }
  if (empty) empty.classList.add('hidden');

  members.forEach(m => {
    const badge = getRoleBadge(m.role);
    const roleName = getRoleName(m.role);

    const faceThumb = m.face_thumbnail
      ? `<img src="file:///${String(m.face_thumbnail).replace(/\\/g, '/').replace(/"/g, '&quot;')}" onerror="this.parentElement.innerHTML='<span class=face-placeholder>${badge}</span>'" />`
      : `<span class="face-placeholder">${badge}</span>`;

    let spectrumBars = '';
    if (m.voiceprint_spectrum) {
      try {
        const bins = typeof m.voiceprint_spectrum === 'string'
          ? JSON.parse(m.voiceprint_spectrum) : m.voiceprint_spectrum;
        spectrumBars = (bins || []).slice(0, 9).map(v => {
          const h = Number(v) * 48;
          if (isNaN(h) || !isFinite(h)) return '';
          return `<div class="voiceprint-mini-bar" style="height:${Math.max(2, h)}px"></div>`;
        }).filter(Boolean).join('');
      } catch (_) {}
    }

    const memberId = m.member_id || m.id || '';
    const div = document.createElement('div');
    div.className = 'member-mgmt-item';
    div.dataset.memberId = memberId;
    div.innerHTML = `
      <div class="member-mgmt-face">${faceThumb}</div>
      <div class="member-mgmt-spectrum">
        ${spectrumBars || '<span style="font-size:7px;color:var(--muted);margin:auto;">—</span>'}
      </div>
      <div class="member-mgmt-info">
        <span class="member-mgmt-name">${escHtml(m.display_name) || '未知'}</span>
        <span class="member-mgmt-role">${badge} ${roleName}</span>
      </div>
      <div class="member-mgmt-meta">${formatTime(m.last_active_at)}</div>`;
    div.addEventListener('click', () => openMemberDetail(memberId));
    list.appendChild(div);
  });
}

function renderMemberManagementStats(stats) {
  const countEl = $('statMembersCount');
  const visitsEl = $('statTotalVisits');
  if (countEl) countEl.textContent = stats.members_count ?? 0;
  if (visitsEl) visitsEl.textContent = stats.total_visits ?? 0;
}

// ═══════════════════════════════════════════════════════════
// MEMBER DETAIL MODAL
// ═══════════════════════════════════════════════════════════
let _currentDetailMemberId = null;

function openMemberDetail(memberId) {
  _currentDetailMemberId = memberId;
  window.frankAPI?.sendMessage?.({ type: 'member.info', payload: { member_id: memberId } });
  window.frankAPI?.sendMessage?.({ type: 'member.history', payload: { member_id: memberId } });
  $('memberDetailOverlay')?.classList.remove('hidden');
}

function closeMemberDetail() {
  $('memberDetailOverlay')?.classList.add('hidden');
  _currentDetailMemberId = null;
}

function renderMemberDetailModal(member) {
  const badge = getRoleBadge(member.role);
  const faceThumb = member.face_thumbnail
    ? `<img src="file:///${String(member.face_thumbnail).replace(/\\/g, '/').replace(/"/g, '&quot;')}" onerror="this.parentElement.innerHTML='<span class=face-placeholder>${badge}</span>'" />`
    : `<span class="face-placeholder">${badge}</span>`;

  const faceEl = $('detailFace');
  if (faceEl) faceEl.innerHTML = faceThumb;
  const nameEl = $('detailName');
  if (nameEl) nameEl.textContent = member.display_name || '未知';
  const roleEl = $('detailRole');
  if (roleEl) roleEl.textContent = `${badge} ${getRoleName(member.role)}`;
  const confEl = $('detailConfidence');
  if (confEl) confEl.textContent = member.last_recognized_at ? `最后识别: ${formatTime(member.last_recognized_at)}` : '';

  const recogEl = $('detailRecogConfidence');
  if (recogEl) recogEl.textContent = member.recognition_confidence ? `${(member.recognition_confidence * 100).toFixed(0)}%` : '—';
  const createdEl = $('detailCreatedAt');
  if (createdEl) createdEl.textContent = member.created_at ? formatTime(member.created_at) : '—';
  const activeEl = $('detailLastActive');
  if (activeEl) activeEl.textContent = member.last_active_at ? formatTime(member.last_active_at) : '—';
  const countEl = $('detailAppearanceCount');
  if (countEl) countEl.textContent = member.appearance_count ?? '—';
}

// ═══════════════════════════════════════════════════════════
// HISTORY MODAL
// ═══════════════════════════════════════════════════════════
let _currentHistoryItems = [];
let _currentHistoryFilter = 'all';

function openHistoryModal() {
  $('historyOverlay')?.classList.remove('hidden');
  const titleEl = $('historyTitle');
  if (titleEl && _currentDetailMemberId) {
    titleEl.textContent = `历史指令记录 — ${_currentDetailMemberId.substring(0, 8)}`;
  }
  if (_currentDetailMemberId) {
    window.frankAPI?.sendMessage?.({ type: 'member.history', payload: { member_id: _currentDetailMemberId } });
  }
}

function closeHistoryModal() {
  $('historyOverlay')?.classList.add('hidden');
}

function renderHistoryTimeline(items) {
  _currentHistoryItems = items || [];
  _currentHistoryFilter = 'all';
  applyHistoryFilter();
}

function applyHistoryFilter() {
  const filtered = _currentHistoryFilter === 'all'
    ? _currentHistoryItems
    : _currentHistoryItems.filter(item => item.type === _currentHistoryFilter);

  const timeline = $('historyTimeline');
  const empty = $('historyEmpty');
  if (!timeline) return;

  if (!filtered.length) {
    if (empty) empty.classList.remove('hidden');
    timeline.querySelectorAll('.history-item').forEach(el => el.remove());
    return;
  }
  if (empty) empty.classList.add('hidden');

  timeline.innerHTML = filtered.map(item => {
    const icon = item.type === 'conversation' ? '💬' : '📋';
    const typeLabel = item.type === 'conversation' ? '对话' : '任务';
    return `
      <div class="history-item">
        <div class="history-item-type">${icon}</div>
        <div class="history-item-body">
          <span class="history-item-summary">${escHtml(item.summary) || '(无摘要)'}</span>
          <div style="display:flex;justify-content:space-between;align-items:center;">
            <span class="history-item-time">${formatTime(item.timestamp)}</span>
            <span style="font-size:10px;color:var(--muted);">${typeLabel}</span>
          </div>
        </div>
      </div>`;
  }).join('');
}

// ═══════════════════════════════════════════════════════════
// MEMBERS PANEL
// ═══════════════════════════════════════════════════════════
function refreshMemberPanel() {
  window.frankAPI?.sendMessage?.({ type: 'member.list' });
  window.frankAPI?.sendMessage?.({ type: 'member.pending' });
}

function renderMemberList(members) {
  const list = $('memberList'), empty = $('memberEmpty'), stats = $('statsMembers');
  if (!list) return;
  list.innerHTML = '';
  if (stats) stats.textContent = '已识别: ' + (members?.length || 0);
  if (!members?.length) { empty?.classList.remove('hidden'); return; }
  empty?.classList.add('hidden');
  members.forEach(m => {
    const li = document.createElement('li');
    li.className = 'member-item';
    li.innerHTML = `<div class="member-info"><span class="member-name"><span class="member-avatar">${(m.display_name||'?')[0]}</span>${m.display_name||'未知'}</span><span class="member-meta"><span class="role-badge role-${m.role||'guest'}">${getRoleBadge(m.role)} ${getRoleName(m.role)}</span><span>${formatTime(m.last_active_at||m.created_at)}</span></span></div><div class="member-actions"><button class="btn-sm" data-action="edit" data-id="${m.member_id||m.id}">编辑</button><button class="btn-sm" data-action="delete" data-id="${m.member_id||m.id}">删除</button></div>`;
    list.appendChild(li);
  });
}

function renderPendingList(pending) {
  const list = $('pendingList'), empty = $('pendingEmpty'), stats = $('statsPending');
  if (!list) return;
  list.innerHTML = '';
  if (stats) stats.textContent = '待识别: ' + (pending?.length || 0);
  if (!pending?.length) { empty?.classList.remove('hidden'); return; }
  empty?.classList.add('hidden');
  pending.forEach(p => {
    const li = document.createElement('li');
    li.className = 'member-item pending-item';
    li.innerHTML = `<div class="member-info"><span class="member-name">${p.serial_name||p.id||'未知访客'}</span><span class="member-meta"><span>出现 ${p.appearance_count||0} 次</span><span>${formatTime(p.last_active_at||p.last_seen_at)}</span></span></div><div class="member-actions"><button class="btn-sm primary" data-action="identify" data-id="${p.unidentified_id||p.id||p.member_id}">识别</button></div>`;
    list.appendChild(li);
  });
}

$('btnAddMemberIdentity')?.addEventListener('click', () => navigateTo('memberManagement'));

// ═══════════════════════════════════════════════════════════
// PERSONA / IDENTITY PANEL
// ═══════════════════════════════════════════════════════════
// ─── Identity Panel: person list ──────────────────────────
let allPersons = [];
let currentFilter = 'all';
let _personListRenderPending = false;

function loadPersonaPanel() {
  if (!PanelManager.isOpen($('identityPanel'))) return;
  window.frankAPI?.sendMessage?.({ type: 'member.list' });
  window.frankAPI?.sendMessage?.({ type: 'member.pending' });
}

// Batch renderPersonList calls from separate IPC handlers into a single
// animation-frame render to avoid double-paint and flash of incomplete data.
function schedulePersonListRender() {
  if (_personListRenderPending) return;
  _personListRenderPending = true;
  requestAnimationFrame(() => {
    _personListRenderPending = false;
    if (PanelManager.isOpen($('identityPanel'))) renderPersonList(cachedMembers, cachedPending);
  });
}

function _updateIdentityEmptyState() {
  const el = document.getElementById('identityEmpty');
  if (!el) return;
  const hasCamera = chipCAM?.classList.contains('active');
  if (!hasCamera) {
    el.textContent = '摄像头未启动\n请在主界面开启摄像头以启用人脸识别';
  } else if (!_pipelineReady) {
    el.textContent = '人脸识别引擎加载中…\nInsightFace 模型正在初始化，请稍候';
  } else {
    el.textContent = '暂无识别记录\n将摄像头对准人脸，系统将自动发现并记录';
  }
}

function renderPersonList(members, pending) {
  allPersons = [
    ...(members || []).map(m => ({ ...m, personType: 'member' })),
    ...(pending || []).map(p => ({
      ...p,
      personType: 'unidentified',
      display_name: p.display_name || `访客_${String(p.id || '').substring(0, 4).toUpperCase()}`,
      role: 'unregistered',
    })),
  ];

  const identified = (members || []).length;
  const unidentified = (pending || []).length;
  const statIdentified = document.getElementById('identityStatIdentified');
  const statPending = document.getElementById('identityStatPending');
  const statTotal = document.getElementById('identityStatTotal');
  if (statIdentified) statIdentified.textContent = identified;
  if (statPending) statPending.textContent = unidentified;
  if (statTotal) statTotal.textContent = identified + unidentified;

  applyFilter();
}

function applyFilter() {
  const filtered = currentFilter === 'all'
    ? allPersons
    : currentFilter === 'unidentified'
      ? allPersons.filter(p => p.personType === 'unidentified')
      : allPersons.filter(p => p.role === currentFilter);

  const list = document.getElementById('identityList');
  const empty = document.getElementById('identityEmpty');
  if (!list) return;

  if (!filtered.length) {
    if (empty) { empty.classList.remove('hidden'); _updateIdentityEmptyState(); }
    list.innerHTML = '';
    return;
  }
  if (empty) empty.classList.add('hidden');

  list.innerHTML = filtered.map(p => {
    const isIdentified = p.personType === 'member';
    const role = p.role || 'unregistered';
    const badge = getRoleBadge(role);
    const roleName = getRoleName(role);

    const faceThumb = p.face_thumbnail
      ? `<img src="file:///${String(p.face_thumbnail).replace(/\\/g, '/').replace(/"/g, '&quot;')}" onerror="this.parentElement.innerHTML='<span class=face-placeholder>${badge}</span>'" />`
      : `<span class="face-placeholder">${badge}</span>`;

    let spectrumBars = '';
    if (p.voiceprint_spectrum) {
      try {
        const bins = typeof p.voiceprint_spectrum === 'string'
          ? JSON.parse(p.voiceprint_spectrum) : p.voiceprint_spectrum;
        spectrumBars = (bins || []).slice(0, 9).map(v => {
          const h = Number(v) * 50;
          if (isNaN(h) || !isFinite(h)) return '';
          return `<div class="voiceprint-mini-bar" style="height:${Math.max(2, h)}px"></div>`;
        }).filter(Boolean).join('');
      } catch (_) {}
    }

    const pid = escAttr(isIdentified ? (p.member_id || p.id || '') : (p.id || ''));
    const resampleAction = isIdentified
      ? `window.requestVoiceResample('${pid}')`
      : `showToast('请先标识该人物后再采集声纹','info')`;
    return `
    <div class="identity-item ${isIdentified ? '' : 'unidentified'}">
      <div class="identity-face-thumb">${faceThumb}</div>
      <div class="identity-voiceprint-mini" title="${isIdentified ? '点击重新采集声纹' : '请先标识该人物'}" onclick="${resampleAction}" style="cursor:pointer;">
        ${spectrumBars || '<span style="font-size:8px;color:var(--muted);margin:auto;">' + (isIdentified ? '点击采样' : '待采集') + '</span>'}
      </div>
      <div class="identity-info">
        <div class="identity-info-name">${escHtml(p.display_name) || '未知'}</div>
        <div class="identity-info-role">${badge} ${roleName}</div>
        <div class="identity-info-meta">
          ${isIdentified
            ? `识别: ${formatTime(p.last_recognized_at || p.last_active_at)} · ${((p.recognition_confidence || 0) * 100).toFixed(0)}%`
            : `出现: ${formatTime(p.last_seen_at)} · ${p.appearance_count || 0}次`}
        </div>
      </div>
      <div class="identity-actions">
        ${isIdentified
          ? `<button class="identity-action-btn" onclick="openIdentifyDialog({mode:'edit',id:'${escAttr(p.member_id||p.id||'')}',name:'${escAttr(p.display_name||'')}',role:'${escAttr(p.role||'member')}'})">✏️</button>`
          : `<button class="identity-action-btn primary" onclick="openIdentifyDialog({mode:'identify',id:'${escAttr(p.id||'')}'})">标识</button>`}
      </div>
    </div>`;
  }).join('');
}

// ─── Identity dialog ──────────────────────────────────────
let _identifyDialogState = { mode: 'identify', id: '' };

function openIdentifyDialog(opts) {
  // Support both old API: openIdentifyDialog(idString) and new API: openIdentifyDialog({mode, id, name, role})
  if (!opts) return;
  if (typeof opts === 'string') {
    opts = { mode: 'identify', id: opts };
  }
  _identifyDialogState = opts;
  const overlay = $('identifyOverlay');
  const title = $('identifyTitle');
  const nameInput = $('identifyName');
  const confirmBtn = $('identifyConfirm');

  if (!overlay) return;

  nameInput.value = opts.name || '';
  if (opts.role) {
    const radio = document.querySelector(`input[name="identifyRole"][value="${opts.role}"]`);
    if (radio) { radio.checked = true; }
    else {
      // Role not in radio group (e.g., 'owner') — fall back to member
      const fallback = document.querySelector('input[name="identifyRole"][value="member"]');
      if (fallback) fallback.checked = true;
    }
  } else {
    const def = document.querySelector('input[name="identifyRole"][value="member"]');
    if (def) def.checked = true;
  }
  $('identifyNameError')?.classList.add('hidden');

  if (opts.mode === 'edit') {
    title.textContent = '编辑成员';
    confirmBtn.textContent = '保存修改';
  } else {
    title.textContent = '标识访客';
    confirmBtn.textContent = '确认标识';
  }

  overlay.classList.remove('hidden');
  setTimeout(() => nameInput.focus(), 100);
}

function closeIdentifyDialog() {
  $('identifyOverlay')?.classList.add('hidden');
}

function submitIdentify() {
  const name = $('identifyName')?.value.trim();
  const roleRadio = document.querySelector('input[name="identifyRole"]:checked');
  const role = roleRadio?.value || 'member';
  const errorEl = $('identifyNameError');

  if (!name || name.length < 2 || name.length > 20) {
    if (errorEl) { errorEl.textContent = '名称长度需在 2-20 个字符之间'; errorEl.classList.remove('hidden'); }
    return;
  }
  if (errorEl) errorEl.classList.add('hidden');

  const { mode, id } = _identifyDialogState;
  if (mode === 'edit') {
    window.frankAPI?.sendMessage?.({ type: 'member.update', payload: { member_id: id, display_name: name, role: role } });
  } else {
    window.frankAPI?.sendMessage?.({ type: 'member.identify', payload: { unidentified_id: id, display_name: name, role: role } });
  }

  closeIdentifyDialog();
  // 注意：loadPersonaPanel/refreshMemberPanel 由 member.identified / member.updated
  // 的 IPC 回调负责触发（onMemberRegistered / onMemberUpdated），无需在此 setTimeout
}

// Dialog button wiring
$('identifyClose')?.addEventListener('click', closeIdentifyDialog);
$('identifyCancel')?.addEventListener('click', closeIdentifyDialog);
$('identifyConfirm')?.addEventListener('click', submitIdentify);
$('identifyName')?.addEventListener('keypress', (e) => { if (e.key === 'Enter') submitIdentify(); });

// ─── Voice capture dialog buttons ──────────────────────
$('voiceCaptureCancel')?.addEventListener('click', closeVoiceCaptureDialog);
$('voiceCaptureRetry')?.addEventListener('click', () => {
  document.getElementById('voiceCaptureWaveform')?.classList.remove('hidden');
  document.getElementById('voiceCaptureSpectrum')?.classList.add('hidden');
  document.getElementById('voiceCaptureRetry')?.classList.add('hidden');
  document.getElementById('voiceCaptureDone')?.classList.add('hidden');
  document.getElementById('voiceCaptureStatus').textContent = '请在摄像头前正常说话…';
  const cd = document.getElementById('voiceCaptureCountdown');
  if (cd) { cd.textContent = '5s'; cd.classList.add('recording'); }
  _voiceCaptureCountdown = 5;
  _startWaveformAnimation();
  _voiceCaptureTimer = setInterval(() => {
    _voiceCaptureCountdown--;
    const cel = document.getElementById('voiceCaptureCountdown');
    if (cel) cel.textContent = _voiceCaptureCountdown > 0 ? _voiceCaptureCountdown + 's' : '等待中…';
    if (_voiceCaptureCountdown <= 0) {
      document.getElementById('voiceCaptureStatus').textContent = '等待声纹采集完成…';
    }
  }, 1000);
  window.frankAPI?.sendMessage?.({ type: 'member.capture_voice', payload: { member_id: _voiceCaptureMemberId } });
});
$('voiceCaptureDone')?.addEventListener('click', () => {
  closeVoiceCaptureDialog();
  loadPersonaPanel();
  showToast('声纹采样已保存 ✅', 'success');
});
$('voiceCaptureOverlay')?.addEventListener('click', (e) => {
  if (e.target === e.currentTarget) closeVoiceCaptureDialog();
});

// ─── Role Info Panel ──────────────────────────────────────
function loadRoleInfoPanel() {
  window.frankAPI?.sendMessage?.({ type: 'role.list' });
}

function renderRoleInfoPanel(roles) {
  const container = $('roleInfoContent');
  if (!container || !roles?.length) return;

  const perms = [
    {key:'member_management',label:'成员管理'},{key:'system_config',label:'系统配置'},
    {key:'full_data_access',label:'全数据访问'},{key:'regular_skills',label:'常规技能'},
    {key:'smart_home_control',label:'智能家居'},{key:'calendar_notes',label:'日历笔记'},
    {key:'file_operations',label:'文件操作'},{key:'third_party_skills',label:'第三方技能'},
    {key:'session_preempt',label:'会话打断'},{key:'basic_qa',label:'基础问答'},
  ];
  const descs = {
    owner: '系统所有者，每个部署环境仅 1 人。拥有最高指令权限，不可删除。',
    admin: '管理员，由主人授权。拥有全部指令权限，可管理成员和配置系统。',
    member: '家庭成员。可使用所有常规技能，每日限制 2 小时。',
    guest: '临时访客。仅可使用基础问答、天气等受限功能。每日 30 分钟。',
    unregistered: '未登记。系统自动发现但尚未标识的人物。无任何权限。',
  };

  container.innerHTML = `
    <div class="role-info-section-title">角色层级</div>
    ${roles.map(r => `
      <div class="role-info-card role-${r.name}">
        <div class="role-info-card-header">
          <span style="font-size:18px;">${r.badge || '⬜'}</span>
          <span style="font-size:14px;font-weight:500;">${r.display_name}</span>
          <span class="role-info-level">等级 ${r.level}</span>
        </div>
        <div class="role-info-desc">${descs[r.name] || r.description || ''}</div>
      </div>`).join('')}

    <div class="role-info-section-title">权限矩阵</div>
    <div class="permission-matrix">
      <table class="perm-table">
        <thead><tr><th>权限</th>${roles.map(r => `<th>${r.badge} ${r.display_name}</th>`).join('')}</tr></thead>
        <tbody>
          ${perms.map(p => `<tr><td>${p.label}</td>${roles.map(r =>
            `<td class="${r.permissions?.[p.key] ? 'perm-yes' : 'perm-no'}">${r.permissions?.[p.key] ? '✓' : '✗'}</td>`
          ).join('')}</tr>`).join('')}
        </tbody>
      </table>
    </div>
  `;
}

// ═══════════════════════════════════════════════════════════
// WIZARD
// ═══════════════════════════════════════════════════════════
let wizardStep = 1;

function openWizard() {
  wizardStep = 1; $('wizardOverlay')?.classList.remove('hidden'); goToStep(1);
  window.frankAPI?.sendMessage?.({ type: 'member.register_start' });
}
function closeWizard() { $('wizardOverlay')?.classList.add('hidden'); window.frankAPI?.sendMessage?.({ type: 'member.register_cancel' }); wizardStep = 1; }

function goToStep(n) {
  wizardStep = n;
  for (let i=1;i<=4;i++) $(`wizardStep${i}`)?.classList.toggle('hidden', i!==n);
  $('wizardPrev')?.classList.toggle('hidden', n===1);
  $('wizardNext')?.classList.toggle('hidden', n===4);
  if ($('wizardTitle')) $('wizardTitle').textContent = `添加成员 — 步骤 ${n}/4`;
  if (n===4) {
    $('summaryName').textContent = $('regName')?.value || '—';
    $('summaryRole').textContent = document.querySelector('input[name="regRole"]:checked')?.value || '—';
  }
}

$('wizardClose')?.addEventListener('click', closeWizard);
$('wizardCancel')?.addEventListener('click', closeWizard);
$('wizardPrev')?.addEventListener('click', () => { if (wizardStep > 1) goToStep(wizardStep - 1); });
$('wizardNext')?.addEventListener('click', () => {
  if (wizardStep === 1) {
    const name = $('regName')?.value.trim();
    const role = document.querySelector('input[name="regRole"]:checked')?.value;
    const err = $('regNameError');
    if (!name || name.length < 2 || name.length > 20) { if(err){err.textContent='名称长度需在 2-20 个字符之间';err.classList.remove('hidden');} return; }
    if (!role) { if(err){err.textContent='请选择角色';err.classList.remove('hidden');} return; }
    if (err) err.classList.add('hidden');
    window.frankAPI?.sendMessage?.({ type: 'member.register_info', payload: { display_name: name, role: role } });
    goToStep(2);
  } else if (wizardStep < 4) { goToStep(wizardStep + 1); }
  else { closeWizard(); showToast('注册完成！', 'success'); refreshMemberPanel(); }
});

// ═══════════════════════════════════════════════════════════
// TASK DETAIL PANEL
// ═══════════════════════════════════════════════════════════
let allTasks = [];

function refreshTaskDetailPanel() {
  window.frankAPI?.sendMessage?.({ type: 'task.list' });
  // Fallback: use inline tasks if IPC not available
  if (!window.frankAPI) renderTaskDetailList(allTasks);
}

function renderTaskDetailList(tasks) {
  allTasks = tasks || [];
  const list = $('taskDetailList'), empty = $('taskEmpty');
  if (!list) return;
  const filter = $('taskFilterStatus')?.value || 'all';
  const filtered = filter === 'all' ? allTasks : allTasks.filter(t => t.status === filter);

  // Stats
  const running = allTasks.filter(t=>t.status==='running').length;
  const done = allTasks.filter(t=>t.status==='done').length;
  const failed = allTasks.filter(t=>t.status==='failed').length;
  if ($('statTotal')) $('statTotal').textContent = allTasks.length;
  if ($('statRunning')) $('statRunning').textContent = running;
  if ($('statDone')) $('statDone').textContent = done;
  if ($('statFailed')) $('statFailed').textContent = failed;

  if (!filtered.length) { empty?.classList.remove('hidden'); list.innerHTML = ''; return; }
  empty?.classList.add('hidden');
  list.innerHTML = filtered.map(t => `
    <div class="task-detail-item">
      <div class="task-detail-progress"><div class="task-detail-progress-fill" style="width:${t.progress||(t.status==='done'?100:t.status==='running'?30:0)}%"></div></div>
      <div class="task-detail-info"><div class="task-detail-title">${t.text||t.title||''}</div><div class="task-detail-meta">${t.source||'sys'} · ${t.elapsed||'—'}</div></div>
      <span class="task-detail-status ${t.status||'pending'}">${t.status==='running'?'进行中':t.status==='done'?'已完成':t.status==='failed'?'失败':'等待'}</span>
      <div class="task-detail-actions">${t.status==='failed'?'<button class="btn-sm">重试</button>':''}${t.status==='done'?'<button class="btn-sm primary">查看</button>':''}</div>
    </div>`).join('');
}

$('taskFilterStatus')?.addEventListener('change', () => renderTaskDetailList(allTasks));

// ═══════════════════════════════════════════════════════════
// NOTIFICATION PANEL
// ═══════════════════════════════════════════════════════════
function renderNotifList(notifs) {
  const list = $('notifList'); if (!list) return;
  if (!notifs?.length) { list.innerHTML = '<p class="empty-state" style="padding:40px 0;">暂无通知</p>'; return; }
  list.innerHTML = notifs.map(n => `
    <div class="notif-list-item"><div class="notif-list-dot"></div><div class="notif-list-content"><div class="notif-list-title">${n.title||''}</div><div class="notif-list-body">${n.body||''}</div><div class="notif-list-time">${formatTime(n.time)}</div></div></div>`).join('');
}

// ═══════════════════════════════════════════════════════════
// TASK LIST 3-STATE TOGGLE
// ═══════════════════════════════════════════════════════════
const TASK_STATES = ['collapsed','','full'];
let taskStateIdx = 1;
function cycleTaskState() {
  const zone = document.querySelector('.zone-monitor'); if (!zone) return;
  zone.classList.remove('collapsed','full');
  taskStateIdx = (taskStateIdx+1) % TASK_STATES.length;
  const next = TASK_STATES[taskStateIdx]; if (next) zone.classList.add(next);
}

// ─── Gesture UI ──────────────────────────────────────────
const GESTURE_ICONS = { raise_hand:'✋',wave:'👋',point:'👉',come_closer:'🚶',custom:'🤌' };
const GESTURE_NAMES = { raise_hand:'举手',wave:'挥手',point:'指向',come_closer:'走近',custom:'自定义手势' };
let gestureTimer;
function showGestureToast(type, confidence) {
  if (gestureTimer) clearTimeout(gestureTimer);
  if (gestureIcon) gestureIcon.textContent = GESTURE_ICONS[type]||'🤌';
  if (gestureText) gestureText.textContent = (GESTURE_NAMES[type]||'手势') + (confidence?` (${(confidence*100).toFixed(0)}%)`:'');
  gestureToast?.classList.remove('hidden','fade-out');
  gestureTimer = setTimeout(()=>{ gestureToast?.classList.add('fade-out'); setTimeout(()=>gestureToast?.classList.add('hidden'),500); }, 3000);
}
function togglePauseBanner(s) { pauseBanner?.classList.toggle('hidden',!s); }

// ─── Window controls ─────────────────────────────────────
$('btn-minimize')?.addEventListener('click', () => window.frankAPI?.minimizeWindow?.());
$('btn-close')?.addEventListener('click', () => window.frankAPI?.closeWindow?.());
$('errorClose')?.addEventListener('click', ()=>errorToast?.classList.add('hidden'));

// ─── Voice resample request ─────────────────────────────
function requestVoiceResample(memberId) {
  if (!memberId) return;
  openVoiceCaptureDialog(memberId);
}
// Expose to window for inline onclick reliability
window.requestVoiceResample = requestVoiceResample;

// ─── Voice capture dialog ────────────────────────────
let _voiceCaptureTimer = null;
let _voiceCaptureAnimFrame = null;
let _voiceCaptureMemberId = null;
let _voiceCaptureCountdown = 0;

function openVoiceCaptureDialog(memberId) {
  _voiceCaptureMemberId = memberId;
  _voiceCaptureCountdown = 10;
  const overlay = document.getElementById('voiceCaptureOverlay');
  if (!overlay) return;
  overlay.classList.remove('hidden');
  document.getElementById('voiceCaptureRetry')?.classList.add('hidden');
  document.getElementById('voiceCaptureDone')?.classList.add('hidden');
  document.getElementById('voiceCaptureSpectrum')?.classList.add('hidden');
  document.getElementById('voiceCaptureWaveform')?.classList.remove('hidden');
  const countdownEl = document.getElementById('voiceCaptureCountdown');
  if (countdownEl) { countdownEl.textContent = _voiceCaptureCountdown + 's'; countdownEl.classList.add('recording'); }
  const statusEl = document.getElementById('voiceCaptureStatus');
  const guideEl = document.getElementById('voiceCaptureGuide');
  const scriptEl = document.getElementById('voiceCaptureScript');
  if (guideEl) guideEl.textContent = '请朗读以下文字：';
  if (scriptEl) scriptEl.textContent = '你好弗兰克';
  if (statusEl) statusEl.textContent = '请在 10 秒内朗读以上文字';
  // Start animated waveform
  _startWaveformAnimation();
  // Countdown
  _voiceCaptureTimer = setInterval(() => {
    _voiceCaptureCountdown--;
    if (countdownEl) countdownEl.textContent = _voiceCaptureCountdown > 0 ? _voiceCaptureCountdown + 's' : '…';
    if (_voiceCaptureCountdown <= 0) {
      if (statusEl) statusEl.textContent = '等待语音输入…';
    }
  }, 1000);
  // Send capture request
  window.frankAPI?.sendMessage?.({ type: 'member.capture_voice', payload: { member_id: memberId } });
}

// Track mic level in voice capture dialog
let _voiceCaptureMicAnimFrame = null;
function _updateVoiceCaptureMicLevel(db) {
  if (!document.getElementById('voiceCaptureOverlay') || document.getElementById('voiceCaptureOverlay').classList.contains('hidden')) return;
  const bar = document.getElementById('voiceCaptureMicBar');
  if (!bar) return;
  // Map -60..0 dB to 0..100%
  const pct = Math.max(0, Math.min(100, (db + 60) / 60 * 100));
  bar.style.width = pct + '%';
  bar.style.background = db > -30 ? 'var(--success)' : db > -50 ? 'var(--accent)' : 'var(--border)';
}

function closeVoiceCaptureDialog() {
  const overlay = document.getElementById('voiceCaptureOverlay');
  if (overlay) overlay.classList.add('hidden');
  _stopWaveformAnimation();
  if (_voiceCaptureTimer) { clearInterval(_voiceCaptureTimer); _voiceCaptureTimer = null; }
  _voiceCaptureMemberId = null;
  // Reset mic bar
  const bar = document.getElementById('voiceCaptureMicBar');
  if (bar) bar.style.width = '0%';
}

function _handleVoiceCaptureTimeout() {
  _stopWaveformAnimation();
  if (_voiceCaptureTimer) { clearInterval(_voiceCaptureTimer); _voiceCaptureTimer = null; }
  const countdownEl = document.getElementById('voiceCaptureCountdown');
  if (countdownEl) { countdownEl.textContent = '超时 ⏰'; countdownEl.classList.remove('recording'); }
  document.getElementById('voiceCaptureWaveform')?.classList.add('hidden');
  const statusEl = document.getElementById('voiceCaptureStatus');
  if (statusEl) statusEl.textContent = '未检测到语音，请重试';
  document.getElementById('voiceCaptureRetry')?.classList.remove('hidden');
  document.getElementById('voiceCaptureMicBar').style.width = '0%';
}

function _startWaveformAnimation() {
  const container = document.getElementById('voiceCaptureWaveform');
  if (!container) return;
  // Create 16 bars
  container.innerHTML = '';
  for (let i = 0; i < 16; i++) {
    const bar = document.createElement('div');
    bar.className = 'voice-capture-waveform-bar recording';
    container.appendChild(bar);
  }
  _voiceCaptureAnimFrame = requestAnimationFrame(_animateWaveform);
}

function _stopWaveformAnimation() {
  if (_voiceCaptureAnimFrame) { cancelAnimationFrame(_voiceCaptureAnimFrame); _voiceCaptureAnimFrame = null; }
  // Remove recording class from countdown
  const countdownEl = document.getElementById('voiceCaptureCountdown');
  if (countdownEl) countdownEl.classList.remove('recording');
}

function _animateWaveform() {
  const bars = document.querySelectorAll('.voice-capture-waveform-bar');
  bars.forEach(bar => {
    const h = 4 + Math.random() * 56;
    bar.style.height = h + 'px';
  });
  _voiceCaptureAnimFrame = requestAnimationFrame(_animateWaveform);
}

function _showVoiceCaptureResult(spectrum) {
  _stopWaveformAnimation();
  if (_voiceCaptureTimer) { clearInterval(_voiceCaptureTimer); _voiceCaptureTimer = null; }
  const countdownEl = document.getElementById('voiceCaptureCountdown');
  if (countdownEl) { countdownEl.textContent = '完成 ✅'; countdownEl.classList.remove('recording'); }
  const statusEl = document.getElementById('voiceCaptureStatus');
  if (statusEl) statusEl.textContent = '声纹采样完成';
  // Hide waveform, show spectrum
  document.getElementById('voiceCaptureWaveform')?.classList.add('hidden');
  const spectrumContainer = document.getElementById('voiceCaptureSpectrum');
  if (spectrumContainer && spectrum) {
    spectrumContainer.innerHTML = '';
    spectrumContainer.classList.remove('hidden');
    const bins = spectrum.slice(0, 24);
    const maxV = Math.max(...bins, 0.01);
    bins.forEach(v => {
      const bar = document.createElement('div');
      bar.className = 'voice-capture-spectrum-bar';
      bar.style.height = Math.max(2, (v / maxV) * 44) + 'px';
      spectrumContainer.appendChild(bar);
    });
  }
  document.getElementById('voiceCaptureRetry')?.classList.remove('hidden');
  document.getElementById('voiceCaptureDone')?.classList.remove('hidden');
}

// ─── IPC ─────────────────────────────────────────────────
if (window.frankAPI) {
  window.frankAPI.onStateChanged(data => { const cfg = STATE_CONFIG[data.to]||STATE_CONFIG['Idle']; setOrbState(data.to); setChipState(chipCAM, cfg.chipCAM); setChipState(chipMIC, cfg.chipMIC); });
  window.frankAPI.onFaceDetected(() => setChipState(chipCAM, true));
  window.frankAPI.onFaceLost(() => setChipState(chipCAM, false));
  window.frankAPI.onVoiceStart(() => setChipState(chipMIC, true));
  window.frankAPI.onVoiceEnd(() => setChipState(chipMIC, false));
  window.frankAPI.onWakeWord(data => { frankOrb?.classList.add('thinking'); thinkingRings?.classList.add('visible'); });
  window.frankAPI.onIdentityConfirmed(data => { updateUserIdentity(data); loadPersonaPanel(); if(data.display_name) showToast(`${getRoleBadge(data.role)} ${data.display_name} · 已识别`,'success'); });
  window.frankAPI.onIdentityChanging(() => { if(userRole) userRole.textContent='识别中...'; });
  window.frankAPI.onIdentityUnknown(data => { updateUserIdentity(null); if (data?.auto_discovered) loadPersonaPanel(); });
  window.frankAPI.onGestureDetected(data => { showGestureToast(data.gesture_type, data.confidence); if(data.gesture_type==='raise_hand') togglePauseBanner(true); });
  window.frankAPI.onError(data => { if(errorMessage){errorMessage.textContent=`[${data.code}] ${data.message}${data.suggestion?' — '+data.suggestion:''}`;errorToast?.classList.remove('hidden');setTimeout(()=>errorToast?.classList.add('hidden'),5000);} });
  window.frankAPI.onMemberList(data => {
    cachedMembers = data?.members || [];
    schedulePersonListRender();
    renderMemberList(cachedMembers);
    renderMemberManagementList(cachedMembers);
  });
  window.frankAPI.onMemberPending(data => {
    cachedPending = data?.pending || [];
    schedulePersonListRender();
    renderPendingList(cachedPending);
  });
  window.frankAPI.onMemberRegistered(() => { showToast('成员注册成功！','success'); loadMemberManagementPage(); loadPersonaPanel(); });
  window.frankAPI.onVoiceResampled?.(data => {
    showToast(`声纹重采样完成 ✅\n${data?.member_id ? '已更新声纹特征' : ''}`, 'success');
    loadPersonaPanel();
  });
  window.frankAPI.onVoiceCaptured?.(data => {
    if (data?.spectrum && _voiceCaptureMemberId) {
      _showVoiceCaptureResult(data.spectrum);
    }
  });
  window.frankAPI.onVoiceCaptureTimeout?.(() => {
    if (_voiceCaptureMemberId) _handleVoiceCaptureTimeout();
  });
  window.frankAPI.onRoleList?.(data => {
    if (data?.roles) {
      if (PanelManager.isOpen($('roleInfoPanel'))) renderRoleInfoPanel(data.roles);
    }
  });
  window.frankAPI.onSettingsCurrent?.(data => { if (PanelManager.isOpen($('settingsPanel'))) populateSettingsForm(data); });
  window.frankAPI.onSettingsUpdated?.(data => { if (PanelManager.isOpen($('settingsPanel'))) { populateSettingsForm(data); const s=$('settingsSaveStatus'); if(s){s.classList.remove('hidden');setTimeout(()=>s.classList.add('hidden'),2000);} } });
  // 设备列表事件：后端返回系统级设备索引（兼容 PyAudio/OpenCV）
  window.frankAPI.onAudioDevices?.(data => { if (data?.devices) _populateMicDevices(data.devices); });
  window.frankAPI.onCameraDevices?.(data => { if (data?.devices) _populateCamDevices(data.devices); });
  // Settings retry button
  $('btnSettingsRetry')?.addEventListener('click', () => { loadSettings(); });
  // Reset defaults button: confirm then send settings.reset
  $('btnResetDefaults')?.addEventListener('click', () => {
    if (confirm('确定恢复所有配置项为默认值吗？当前配置将被覆盖。')) {
      window.frankAPI?.sendMessage?.({ type: 'settings.reset' });
    }
  });
  // Clean up timeout when settings panel closes
  document.addEventListener('click', (e) => {
    if (e.target.closest('.panel-slide-close[data-panel="settingsPanel"]')) {
      if (_settingsLoadTimer) { clearTimeout(_settingsLoadTimer); _settingsLoadTimer = null; }
    }
  });
  window.frankAPI.onTaskList?.(data => { if(data?.tasks) { allTasks = data.tasks; if(PanelManager.isOpen($('taskDetailPanel'))) renderTaskDetailList(allTasks); } });

  // ── 任务事件 ──
  window.frankAPI.onTaskUpdated?.(data => {
    const STATUS_MAP = { executing: 'running', queued: 'pending', completed: 'done', cancelled: 'failed' };
    upsertTask({
      task_id: data.task_id,
      status: STATUS_MAP[data.status] || data.status,
      text: data.display_name || data.command || '',
      source: data.user_id ? 'user' : 'sys',
      elapsed: data.started_at ? formatTime(data.started_at) : '—',
      progress: data.progress || 0,
    });
    if (PanelManager.isOpen($('taskDetailPanel'))) refreshTaskDetailPanel();
  });
  window.frankAPI.onTaskCompleted?.(data => {
    upsertTask({
      task_id: data.task_id,
      status: 'done',
      text: data.display_name || data.command || '',
      source: data.user_id ? 'user' : 'sys',
      elapsed: data.completed_at ? formatTime(data.completed_at) : '—',
      progress: 100,
    });
    if (PanelManager.isOpen($('taskDetailPanel'))) refreshTaskDetailPanel();
  });
  window.frankAPI.onTaskFailed?.(data => {
    upsertTask({
      task_id: data.task_id,
      status: 'failed',
      text: data.display_name || data.command || '',
      source: data.user_id ? 'user' : 'sys',
      elapsed: data.completed_at ? formatTime(data.completed_at) : '—',
      progress: data.progress || 0,
      error: data.error_info?.message || '未知错误',
    });
    if (PanelManager.isOpen($('taskDetailPanel'))) refreshTaskDetailPanel();
  });

  // ── 设备状态 ──
  window.frankAPI.onDeviceStatus?.(data => {
    if (data.camera) {
      setChipState(chipCAM, data.camera.active);
      if (chipCAM) chipCAM.title = `${data.camera.pipeline || 'Camera'} · ${data.camera.fps}fps · ${data.camera.faces_detected || 0} face`;
      _pipelineReady = data.camera.pipeline === 'InsightFace';
      _updateIdentityEmptyState();
    }
    if (data.microphone) {
      setChipState(chipMIC, data.microphone.active);
      if (chipMIC) chipMIC.title = `${data.microphone.pipeline || 'Mic'} · ${data.microphone.level_db?.toFixed(1) || '—'}dB${data.microphone.vad_active ? ' · VAD' : ''}`;
      _updateVoiceCaptureMicLevel(data.microphone.level_db ?? -60);
    }
    if (data.screen) {
      setChipState(chipSCR, data.screen.active);
    }
  });

  // ── 对话事件 ──
  window.frankAPI.onChatSubState?.(data => {
    if (agentLabelText) {
      const labels = { listening: '聆听中…', transcribing: '转写中…', thinking: '思考中…', speaking: '回复中…' };
      agentLabelText.textContent = labels[data.to] || data.to || '等待中';
    }
  });
  window.frankAPI.onUserMessage?.(data => {
    if (convoTopic) convoTopic.textContent = (data.text || '').length > 20 ? (data.text || '').substring(0, 20) + '…' : (data.text || '');
    if (convoMeta) convoMeta.textContent = '刚刚 · 用户';
  });
  let _assistantStreamBubble = null;
  let _assistantStreamText = '';
  window.frankAPI.onLLMToken?.(data => {
    // Streaming token: create or update assistant bubble in chat overlay
    if (!PanelManager.isOpen(chatOverlay)) return;
    _assistantStreamText += data.token || '';
    if (!_assistantStreamBubble) {
      _assistantStreamBubble = document.createElement('div');
      _assistantStreamBubble.className = 'chat-bubble frank';
      chatMessages?.appendChild(_assistantStreamBubble);
    }
    _assistantStreamBubble.textContent = _assistantStreamText;
    if (chatMessages) chatMessages.scrollTop = chatMessages.scrollHeight;
  });
  window.frankAPI.onAssistantMessage?.(data => {
    if (convoMeta) convoMeta.textContent = '刚刚 · Frank';
    // Finalize streaming bubble in chat overlay
    const finalText = data.text || _assistantStreamText || '';
    if (finalText && PanelManager.isOpen(chatOverlay)) {
      if (!_assistantStreamBubble) {
        _assistantStreamBubble = document.createElement('div');
        _assistantStreamBubble.className = 'chat-bubble frank';
        chatMessages?.appendChild(_assistantStreamBubble);
      }
      _assistantStreamBubble.textContent = finalText;
      if (chatMessages) chatMessages.scrollTop = chatMessages.scrollHeight;
    }
    // Also update conversation preview
    if (convoTopic && finalText) convoTopic.textContent = finalText.length > 20 ? finalText.substring(0, 20) + '…' : finalText;
    const ts = new Date().getHours().toString().padStart(2,'0')+':'+new Date().getMinutes().toString().padStart(2,'0');
    const b = document.createElement('div');
    b.className = 'convo-bubble assistant';
    b.innerHTML = `<div class="convo-bubble-sender">Frank</div>${escHtml(finalText)}<div class="convo-bubble-time">${ts}</div>`;
    convoBubbles?.appendChild(b);
    if (convoBubbles) convoBubbles.scrollTop = convoBubbles.scrollHeight;
    // Reset stream state
    _assistantStreamBubble = null;
    _assistantStreamText = '';
  });
  window.frankAPI.onSTTTranscription?.(data => {
    if (convoMeta) convoMeta.textContent = '转写: ' + ((data.text || '').substring(0, 30));
  });
  window.frankAPI.onNotification?.(data => {
    if (data?.notifications) {
      renderNotifList(data.notifications);
      if (data.notifications.length > 0) {
        const latest = data.notifications[0];
        if (notifText) notifText.textContent = latest.body || latest.title || '';
        if (notifCount) notifCount.textContent = String(data.notifications.length);
        notifPreview?.classList.remove('hidden');
      }
    }
  });

  // ── 成员管理 IPC ──
  window.frankAPI.onMemberStats?.(data => {
    renderMemberManagementStats(data);
  });
  window.frankAPI.onMemberInfo?.(data => {
    if (data?.member) renderMemberDetailModal(data.member);
  });
  window.frankAPI.onMemberHistory?.(data => {
    if (data?.items) renderHistoryTimeline(data.items);
  });
  window.frankAPI.onMemberUpdated?.(data => {
    showToast('成员信息已更新', 'success');
    closeMemberDetail();
    window.frankAPI?.sendMessage?.({ type: 'member.list' });
    window.frankAPI?.sendMessage?.({ type: 'member.pending' });
    window.frankAPI?.sendMessage?.({ type: 'member.stats' });
  });
  window.frankAPI.onMemberDeleted?.(() => {
    showToast('成员已删除', 'success');
    closeMemberDetail();
    window.frankAPI?.sendMessage?.({ type: 'member.list' });
    window.frankAPI?.sendMessage?.({ type: 'member.pending' });
    window.frankAPI?.sendMessage?.({ type: 'member.stats' });
  });
  window.frankAPI.onMemberCleared?.(data => {
    showToast(`已清除 ${data?.members_deleted || 0} 名成员、${data?.unidentified_deleted || 0} 名访客`, 'info');
    closeMemberDetail();
    window.frankAPI?.sendMessage?.({ type: 'member.list' });
    window.frankAPI?.sendMessage?.({ type: 'member.pending' });
    window.frankAPI?.sendMessage?.({ type: 'member.stats' });
    window.frankAPI?.sendMessage?.({ type: 'role.list' });
  });
}

// ─── Role info button ────────────────────────────────────
$('btnRoleInfo')?.addEventListener('click', (e) => {
  e.stopPropagation();
  openPanel('roleInfo');
  loadRoleInfoPanel();
});

// ─── Clear records button ──────────────────────────────
$('btnClearRecords')?.addEventListener('click', (e) => {
  e.stopPropagation();
  showConfirmDialog(
    '⚠️ 确认清除所有记录？',
    '此操作将移除所有已标识成员、未标识访客及指令历史记录。该操作不可恢复，确定要继续吗？',
    () => {
      window.frankAPI?.sendMessage?.({ type: 'member.clear' });
      showToast('已清除所有人物记录', 'info');
    }
  );
});

// ─── Identity filter clicks ──────────────────────────────
$('identityFilters')?.addEventListener('click', (e) => {
  const btn = e.target.closest('.identity-filter');
  if (!btn) return;
  document.querySelectorAll('.identity-filter').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  currentFilter = btn.dataset.role;
  applyFilter();
});

// ─── Identity list delegation (fallback) ─────────────────
$('identityList')?.addEventListener('click', (e) => {
  // Inline onclick handlers are used for identity action buttons;
  // this listener is reserved for future event-delegation migration.
});

// ─── Chip click handlers ─────────────────────────────────
chipCAM?.addEventListener('click', () => window.frankAPI?.toggleCamera?.());
chipMIC?.addEventListener('click', () => window.frankAPI?.toggleMicrophone?.());

// ─── Init ────────────────────────────────────────────────
async function init() {
  console.log('[Frank UI v3] Initializing...');
  updateTime(); setInterval(updateTime, 10000);
  try { if (window.frankAPI) { const s = await window.frankAPI.getState(); if (s) setOrbState(s.name||'Idle'); } } catch (_) {}
}
init();

// ─── Inline helpers ──────────────────────────────────────
function renderInlineTasks(tasks) {
  if (!taskListScroll) return;
  if (taskCount) taskCount.textContent = String(tasks.length);
  taskListScroll.innerHTML = tasks.map(t => `
    <div class="task-row${t.status === 'done' ? ' done-row' : ''}" onclick="openPanel('chat')">
      <div class="task-status-icon ${t.status||'pending'}">
        ${t.status==='running'?'<div class="task-spinner"></div>':''}
        ${t.status==='pending'?'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="10" height="10"><circle cx="12" cy="12" r="10"></circle><path d="M12 6v6l4 2"></path></svg>':''}
        ${t.status==='done'?'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" width="10" height="10"><path d="M20 6L9 17l-5-5"></path></svg>':''}
        ${t.status==='failed'?'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="10" height="10"><path d="M18 6L6 18M6 6l12 12"></path></svg>':''}
      </div>
      <span class="task-row-text">${t.text||''}</span>
      <span class="task-row-source">${t.source||'sys'}</span>
      <span class="task-row-elapsed">${t.elapsed||'—'}</span>
    </div>`).join('');
}

function updateInlineConversation(topic, meta, bubbles) {
  if (topic && convoTopic) convoTopic.textContent = topic;
  if (meta && convoMeta) convoMeta.textContent = meta;
  if (bubbles && convoBubbles) {
    convoBubbles.innerHTML = bubbles.map(b => `<div class="convo-bubble ${b.role==='user'?'user':'frank'}"><div class="convo-bubble-sender">${b.sender||'Frank'}</div>${b.text||''}<div class="convo-bubble-time">${b.time||''}</div></div>`).join('');
  }
}

// ─── Member detail modal buttons ─────────────────────────
$('btnDetailClose')?.addEventListener('click', closeMemberDetail);
$('memberDetailOverlay')?.addEventListener('click', (e) => {
  if (e.target === e.currentTarget) closeMemberDetail();
});
$('btnDetailHistory')?.addEventListener('click', openHistoryModal);
$('btnDetailEdit')?.addEventListener('click', () => {
  if (!_currentDetailMemberId) return;
  const member = cachedMembers?.find(m => (m.member_id || m.id) === _currentDetailMemberId);
  if (member) {
    openIdentifyDialog({
      mode: 'edit',
      id: _currentDetailMemberId,
      name: member.display_name || '',
      role: member.role || 'member'
    });
  }
});
$('btnDetailDelete')?.addEventListener('click', () => {
  if (!_currentDetailMemberId) return;
  if (confirm('确定要移除该成员吗？此操作不可恢复。')) {
    window.frankAPI?.sendMessage?.({ type: 'member.delete', payload: { member_id: _currentDetailMemberId } });
  }
});

// ─── History modal buttons ───────────────────────────────
$('btnHistoryClose')?.addEventListener('click', closeHistoryModal);
$('historyOverlay')?.addEventListener('click', (e) => {
  if (e.target === e.currentTarget) closeHistoryModal();
});
$('historyFilterBar')?.addEventListener('click', (e) => {
  const btn = e.target.closest('.history-filter');
  if (!btn) return;
  document.querySelectorAll('.history-filter').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  _currentHistoryFilter = btn.dataset.type;
  applyHistoryFilter();
});

// ─── Member management view buttons ──────────────────────
$('btnMemberMgmtBack')?.addEventListener('click', () => navigateTo('main'));
$('btnMemberMgmtAdd')?.addEventListener('click', openWizard);
