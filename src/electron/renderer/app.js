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
  if (diff < 60) return '刚刚';
  if (diff < 3600) return `${Math.floor(diff / 60)} 分钟前`;
  if (diff < 86400) return `${Math.floor(diff / 3600)} 小时前`;
  if (diff < 604800) return `${Math.floor(diff / 86400)} 天前`;
  return d.toLocaleDateString('zh-CN');
}

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
    members: 'membersPanel',
    chat: 'chatOverlay',
  };
  const id = map[name] || name;
  const el = $(id);
  if (el) {
    if (name === 'settings') loadSettings();
    if (name === 'members') refreshMemberPanel();
    if (name === 'identity') loadPersonaPanel();
    if (name === 'tasks') refreshTaskDetailPanel();
    PanelManager.open(el);
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
  b.innerHTML = `<div class="convo-bubble-sender">用户</div>${msg}<div class="convo-bubble-time">${ts}</div>`;
  convoBubbles?.appendChild(b);
  if (convoBubbles) convoBubbles.scrollTop = convoBubbles.scrollHeight;
}

$('chatSendBtn')?.addEventListener('click', sendMessage);
chatInput?.addEventListener('keypress', (e) => { if (e.key === 'Enter') sendMessage(); });

// ═══════════════════════════════════════════════════════════
// SETTINGS PANEL
// ═══════════════════════════════════════════════════════════
let canAutoSave = false;

function loadSettings() {
  $('settingsLoading')?.classList.remove('hidden');
  $('settingsForm')?.classList.add('hidden');
  window.frankAPI?.sendMessage?.({ type: 'settings.get' });
}

function populateSettingsForm(config) {
  $('settingsLoading')?.classList.add('hidden');
  $('settingsForm')?.classList.remove('hidden');
  const flat = flattenConfig(config || {});
  document.querySelectorAll('#settingsForm [data-key]').forEach(el => {
    const val = flat[el.dataset.key];
    if (val === undefined) return;
    if (el.type === 'range') { el.value = val; const d = document.querySelector(`[data-for="${el.dataset.key}"]`); if (d) d.textContent = val; }
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
  if (el.type === 'range') { value = parseFloat(el.value); const d = document.querySelector(`[data-for="${el.dataset.key}"]`); if (d) d.textContent = value; }
  else if (el.type === 'checkbox') value = el.checked;
  else if (el.type === 'number') value = parseInt(el.value, 10);
  else value = el.value;
  window.frankAPI?.sendMessage?.({ type: 'settings.update', payload: unflattenConfig({ [el.dataset.key]: value }) });
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
async function loadDeviceLists() {
  try {
    if (window.frankAPI?.getAudioDevices) {
      const mics = await window.frankAPI.getAudioDevices();
      const sel = $('selectMic');
      if (sel) sel.innerHTML = '<option value="">默认设备</option>' + mics.map(m => `<option value="${m.deviceId}">${m.label}</option>`).join('');
    }
    if (window.frankAPI?.getVideoDevices) {
      const cams = await window.frankAPI.getVideoDevices();
      const sel = $('selectCam');
      if (sel) sel.innerHTML = '<option value="0">默认设备</option>' + cams.map(c => `<option value="${c.deviceId}">${c.label}</option>`).join('');
    }
  } catch (_) {}
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

// Event delegation for member lists
$('memberList')?.addEventListener('click', (e) => {
  const btn = e.target.closest('button');
  if (!btn) return;
  if (btn.dataset.action === 'delete') {
    if (confirm('确定要删除该成员吗？')) {
      window.frankAPI?.sendMessage?.({ type: 'member.delete', payload: { member_id: btn.dataset.id } });
      setTimeout(refreshMemberPanel, 500);
    }
  } else if (btn.dataset.action === 'edit') {
    window.frankAPI?.sendMessage?.({ type: 'member.register_info', payload: { member_id: btn.dataset.id } });
  }
});

$('pendingList')?.addEventListener('click', (e) => {
  const btn = e.target.closest('button');
  if (!btn) return;
  if (btn.dataset.action === 'identify') openIdentifyDialog(btn.dataset.id);
});

function openIdentifyDialog(unidentifiedId) {
  const name = prompt('请输入该成员显示名称（2-20 字符）：');
  if (!name || name.length < 2 || name.length > 20) { if (name) showToast('名称长度需在 2-20 个字符之间', 'error'); return; }
  const role = prompt('请选择角色（admin / member / guest）：', 'guest');
  if (!['admin','member','guest'].includes(role?.toLowerCase())) { showToast('角色必须为 admin、member 或 guest', 'error'); return; }
  window.frankAPI?.sendMessage?.({ type: 'member.identify', payload: { unidentified_id: unidentifiedId, display_name: name, role: role.toLowerCase() } });
  setTimeout(refreshMemberPanel, 500);
}

$('btnAddMember')?.addEventListener('click', () => openWizard());
$('btnAddMemberIdentity')?.addEventListener('click', () => openWizard());

// ═══════════════════════════════════════════════════════════
// PERSONA / IDENTITY PANEL
// ═══════════════════════════════════════════════════════════
// ─── Identity Panel: person list ──────────────────────────
let allPersons = [];
let currentFilter = 'all';
let _personListRenderPending = false;

function loadPersonaPanel() {
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

function renderPersonList(members, pending) {
  allPersons = [
    ...(members || []).map(m => ({ ...m, personType: 'member' })),
    ...(pending || []).map(p => ({
      ...p,
      personType: 'unidentified',
      display_name: p.serial_name || `访客_${String(p.id || '').substring(0, 4).toUpperCase()}`,
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
    if (empty) empty.classList.remove('hidden');
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
      ? `<img src="${String(p.face_thumbnail).replace(/"/g, '&quot;')}" onerror="this.parentElement.innerHTML='<span class=face-placeholder>${badge}</span>'" />`
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

    return `
    <div class="identity-item ${isIdentified ? '' : 'unidentified'}">
      <div class="identity-face-thumb">${faceThumb}</div>
      <div class="identity-voiceprint-mini">
        ${spectrumBars || '<span style="font-size:8px;color:var(--muted);margin:auto;">待采集</span>'}
      </div>
      <div class="identity-info">
        <div class="identity-info-name">${p.display_name || '未知'}</div>
        <div class="identity-info-role">${badge} ${roleName}</div>
        <div class="identity-info-meta">
          ${isIdentified
            ? `识别: ${formatTime(p.last_recognized_at || p.last_active_at)} · ${((p.recognition_confidence || 0) * 100).toFixed(0)}%`
            : `出现: ${formatTime(p.last_seen_at)} · ${p.appearance_count || 0}次`}
        </div>
      </div>
      <div class="identity-actions">
        ${isIdentified
          ? `<button class="identity-action-btn" data-action="edit-person" data-id="${(p.member_id || p.id || '').replace(/"/g, '&quot;')}">✏️</button>`
          : `<button class="identity-action-btn primary" data-action="identify-person" data-id="${(p.id || '').replace(/"/g, '&quot;')}">标识</button>`}
      </div>
    </div>`;
  }).join('');
}

function editPerson(memberId) {
  const name = prompt('修改显示名称（2-20 字符）：');
  if (!name || name.length < 2 || name.length > 20) { if (name) showToast('名称长度需在 2-20 个字符之间', 'error'); return; }
  const role = prompt('选择角色（admin / member / guest）：', 'member');
  if (!['admin', 'member', 'guest'].includes(role?.toLowerCase())) { showToast('角色无效', 'error'); return; }
  window.frankAPI?.sendMessage?.({ type: 'member.update', payload: { member_id: memberId, display_name: name, role: role.toLowerCase() } });
  setTimeout(loadPersonaPanel, 500);
}

function identifyPerson(unidentifiedId) {
  const name = prompt('请输入该成员显示名称（2-20 字符）：');
  if (!name || name.length < 2 || name.length > 20) { if (name) showToast('名称长度需在 2-20 个字符之间', 'error'); return; }
  const role = prompt('请选择角色（admin / member / guest）：', 'guest');
  if (!['admin', 'member', 'guest'].includes(role?.toLowerCase())) { showToast('角色必须为 admin、member 或 guest', 'error'); return; }
  window.frankAPI?.sendMessage?.({ type: 'member.identify', payload: { unidentified_id: unidentifiedId, display_name: name, role: role.toLowerCase() } });
  setTimeout(loadPersonaPanel, 500);
}

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

// ─── IPC ─────────────────────────────────────────────────
if (window.frankAPI) {
  window.frankAPI.onStateChanged(data => { const cfg = STATE_CONFIG[data.to]||STATE_CONFIG['Idle']; setOrbState(data.to); setChipState(chipCAM, cfg.chipCAM); setChipState(chipMIC, cfg.chipMIC); });
  window.frankAPI.onFaceDetected(() => setChipState(chipCAM, true));
  window.frankAPI.onFaceLost(() => setChipState(chipCAM, false));
  window.frankAPI.onVoiceStart(() => setChipState(chipMIC, true));
  window.frankAPI.onVoiceEnd(() => setChipState(chipMIC, false));
  window.frankAPI.onWakeWord(data => { frankOrb?.classList.add('thinking'); thinkingRings?.classList.add('visible'); });
  window.frankAPI.onIdentityConfirmed(data => { updateUserIdentity(data); if(data.display_name) showToast(`${getRoleBadge(data.role)} ${data.display_name} · 已识别`,'success'); });
  window.frankAPI.onIdentityChanging(() => { if(userRole) userRole.textContent='识别中...'; });
  window.frankAPI.onIdentityUnknown(() => updateUserIdentity(null));
  window.frankAPI.onGestureDetected(data => { showGestureToast(data.gesture_type, data.confidence); if(data.gesture_type==='raise_hand') togglePauseBanner(true); });
  window.frankAPI.onError(data => { if(errorMessage){errorMessage.textContent=`[${data.code}] ${data.message}${data.suggestion?' — '+data.suggestion:''}`;errorToast?.classList.remove('hidden');setTimeout(()=>errorToast?.classList.add('hidden'),5000);} });
  window.frankAPI.onMemberList(data => {
    cachedMembers = data?.members || [];
    schedulePersonListRender();
    renderMemberList(cachedMembers);
  });
  window.frankAPI.onMemberPending(data => {
    cachedPending = data?.pending || [];
    schedulePersonListRender();
    renderPendingList(cachedPending);
  });
  window.frankAPI.onMemberRegistered(() => { showToast('成员注册成功！','success'); refreshMemberPanel(); });
  window.frankAPI.onRoleList?.(data => {
    if (data?.roles) {
      if (PanelManager.isOpen($('roleInfoPanel'))) renderRoleInfoPanel(data.roles);
    }
  });
  window.frankAPI.onSettingsCurrent?.(data => populateSettingsForm(data));
  window.frankAPI.onSettingsUpdated?.(data => { populateSettingsForm(data); const s=$('settingsSaveStatus'); if(s){s.classList.remove('hidden');setTimeout(()=>s.classList.add('hidden'),2000);} });
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
    }
    if (data.microphone) {
      setChipState(chipMIC, data.microphone.active);
      if (chipMIC) chipMIC.title = `${data.microphone.pipeline || 'Mic'} · ${data.microphone.level_db?.toFixed(1) || '—'}dB${data.microphone.vad_active ? ' · VAD' : ''}`;
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
  window.frankAPI.onAssistantMessage?.(data => {
    if (convoMeta) convoMeta.textContent = '刚刚 · Frank';
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
}

// ─── Role info button ────────────────────────────────────
$('btnRoleInfo')?.addEventListener('click', (e) => {
  e.stopPropagation();
  openPanel('roleInfo');
  loadRoleInfoPanel();
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

// ─── Identity list action delegation ─────────────────────
$('identityList')?.addEventListener('click', (e) => {
  const btn = e.target.closest('.identity-action-btn');
  if (!btn) return;
  e.stopPropagation();
  if (btn.dataset.action === 'edit-person') editPerson(btn.dataset.id);
  else if (btn.dataset.action === 'identify-person') identifyPerson(btn.dataset.id);
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
