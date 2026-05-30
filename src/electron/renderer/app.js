/**
 * Frank (弗兰克) — 渲染进程脚本
 * Phase 1: 状态指示器 + 聊天面板占位 + IPC 事件监听
 */

// ─── 状态映射 ──────────────────────────────────────────
const STATE_CONFIG = {
  Idle:    { cssClass: 'status-idle',    dotClass: 'status-idle',    title: 'Frank - 待机中',       inputText: '语音监听中...', inputCss: '' },
  Aware:   { cssClass: 'status-aware',   dotClass: 'status-aware',   title: 'Frank - 检测中...',    inputText: '正在识别身份...', inputCss: 'active' },
  Auth:    { cssClass: 'status-auth',    dotClass: 'status-auth',    title: 'Frank - 就绪',         inputText: '说 "Hey Frank" 唤醒我', inputCss: 'listening' },
  Chat:    { cssClass: 'status-chat',    dotClass: 'status-chat',    title: 'Frank - 对话中',       inputText: '正在听...',       inputCss: 'active' },
  Degraded:{ cssClass: 'status-degraded',dotClass: 'status-degraded',title: 'Frank - 降级模式',     inputText: '设备不可用',      inputCss: '' },
};

let currentState = 'Idle';

// ─── DOM 引用 ──────────────────────────────────────────
const statusDot = document.getElementById('status-dot');
const titleText = document.getElementById('title-text');
const inputStatus = document.getElementById('input-status');
const greeting = document.getElementById('greeting');
const hintText = document.getElementById('hint-text');
const messageList = document.getElementById('message-list');
const settingsPanel = document.getElementById('settings-panel');
const errorToast = document.getElementById('error-toast');
const errorMessage = document.getElementById('error-message');

// ─── UI 更新函数 ───────────────────────────────────────

function updateUI(state, identityData) {
  currentState = state;
  const cfg = STATE_CONFIG[state] || STATE_CONFIG['Idle'];

  // 状态指示器
  statusDot.className = cfg.dotClass;
  titleText.textContent = cfg.title;
  inputStatus.textContent = cfg.inputText;
  inputStatus.className = cfg.inputCss;

  // 欢迎语（Phase 2: 个性化）
  if (state === 'Chat') {
    greeting.textContent = identityData?.display_name
      ? `${identityData.display_name}，我在听`
      : '正在听...';
    hintText.textContent = '说出你的指令';
  } else if (state === 'Auth' && identityData?.display_name) {
    const badge = getRoleBadge(identityData.role);
    greeting.textContent = `下午好，${badge} ${identityData.display_name}`;
    hintText.textContent = `角色: ${getRoleName(identityData.role)} — 说 "Hey Frank" 唤醒我`;
  } else if (state === 'Auth' || state === 'Aware') {
    greeting.textContent = '你好，需要我做些什么？';
    hintText.textContent = '说 "Hey Frank" 来唤醒我';
  } else if (state === 'Degraded') {
    greeting.textContent = '部分设备不可用';
    hintText.textContent = '请检查摄像头和麦克风连接';
  } else {
    greeting.textContent = '下午好，需要我做些什么？';
    hintText.textContent = '说一声 "Hey Frank" 来唤醒我';
  }
}

function addSystemMessage(text) {
  const msg = document.createElement('div');
  msg.className = 'message system';
  msg.textContent = text;
  messageList.appendChild(msg);
  messageList.scrollTop = messageList.scrollHeight;
}

function showError(code, message, suggestion) {
  errorMessage.textContent = `[${code}] ${message}${suggestion ? ' — ' + suggestion : ''}`;
  errorToast.classList.remove('hidden');

  // 5 秒后自动隐藏
  setTimeout(() => {
    errorToast.classList.add('hidden');
  }, 5000);
}

// ─── 事件监听（通过 contextBridge）─────────────────────

if (window.frankAPI) {
  // 状态变更
  window.frankAPI.onStateChanged((data) => {
    updateUI(data.to);
    addSystemMessage(`状态: ${data.from} → ${data.to}`);
  });

  // 人脸检测
  window.frankAPI.onFaceDetected((data) => {
    addSystemMessage('检测到人脸');
  });

  window.frankAPI.onFaceLost(() => {
    addSystemMessage('人脸消失');
  });

  // 语音活动
  window.frankAPI.onVoiceStart(() => {
    // VAD 事件，不打扰用户，仅调试用
  });

  window.frankAPI.onVoiceEnd(() => {
    // VAD 事件
  });

  // 唤醒词
  window.frankAPI.onWakeWord((data) => {
    const confidence = data.confidence ? ` (置信度: ${(data.confidence * 100).toFixed(0)}%)` : '';
    addSystemMessage(`🎯 检测到唤醒词"${data.text || 'Hey Frank'}"${confidence}`);
  });

  // Phase 2: Identity
  window.frankAPI.onIdentityConfirmed((data) => {
    if (data.display_name) {
      const roleEmoji = getRoleBadge(data.role);
      updateUI(data.status === 'confirmed' ? 'Auth' : currentState, data);
      addSystemMessage(`👤 识别身份: ${roleEmoji} ${data.display_name} (${getRoleName(data.role)})`);
    }
  });

  window.frankAPI.onIdentityChanging(() => {
    addSystemMessage('身份变更中...');
  });

  window.frankAPI.onIdentityUnknown(() => {
    updateUI('Auth');
  });

  // Phase 5: Gesture events
  window.frankAPI.onGestureDetected((data) => {
    showGestureToast(data.gesture_type, data.confidence, data.gesture_id);
    if (data.gesture_type === 'raise_hand') {
      togglePauseBanner(true);
    }
  });

  // 错误
  window.frankAPI.onError((data) => {
    showError(data.code, data.message, data.suggestion);
  });
}

// ─── Role helpers ─────────────────────────────────────
const ROLE_BADGES = { owner: '👑', adult: '🔵', child: '🟢', guest: '⚪' };
const ROLE_NAMES = { owner: '主人', adult: '成人', child: '儿童', guest: '访客' };

function getRoleBadge(role) { return ROLE_BADGES[role] || '⚪'; }
function getRoleName(role) { return ROLE_NAMES[role] || '未知'; }

// ─── Phase 5: Gesture UI ─────────────────────────────

const GESTURE_ICONS = {
  raise_hand: '✋',
  wave: '👋',
  point: '👉',
  come_closer: '🚶',
  custom: '🤌',
};
const GESTURE_NAMES = {
  raise_hand: '举手',
  wave: '挥手',
  point: '指向',
  come_closer: '走近',
  custom: '自定义手势',
};

const gestureToast = document.getElementById('gesture-toast');
const gestureIcon = document.getElementById('gesture-icon');
const gestureText = document.getElementById('gesture-text');
const pauseBanner = document.getElementById('pause-banner');
let gestureTimer = null;

function showGestureToast(type, confidence, gestureId) {
  if (gestureTimer) clearTimeout(gestureTimer);

  const icon = GESTURE_ICONS[type] || '🤌';
  const name = GESTURE_NAMES[type] || '自定义手势';
  const confStr = confidence ? ` (${(confidence * 100).toFixed(0)}%)` : '';

  gestureIcon.textContent = icon;
  gestureText.textContent = `${name}${confStr}`;
  gestureToast.classList.remove('hidden', 'fade-out');

  // 3 秒后淡出
  gestureTimer = setTimeout(() => {
    gestureToast.classList.add('fade-out');
    setTimeout(() => gestureToast.classList.add('hidden'), 500);
  }, 3000);
}

function togglePauseBanner(show) {
  if (show) {
    pauseBanner.classList.remove('hidden');
  } else {
    pauseBanner.classList.add('hidden');
  }
}

// ─── 标题栏按钮 ────────────────────────────────────────

document.getElementById('btn-minimize').addEventListener('click', () => {
  window.frankAPI?.sendMessage?.({ type: 'window.minimize' });
});

document.getElementById('btn-close').addEventListener('click', () => {
  window.frankAPI?.sendMessage?.({ type: 'window.close' });
});

document.getElementById('btn-expand').addEventListener('click', () => {
  window.frankAPI?.sendMessage?.({ type: 'window.toggle_expand' });
});

document.getElementById('btn-always-on-top').addEventListener('click', function () {
  this.classList.toggle('active');
  window.frankAPI?.sendMessage?.({ type: 'window.toggle_always_on_top' });
});

// ─── 设置面板 ──────────────────────────────────────────

document.getElementById('btn-settings').addEventListener('click', () => {
  settingsPanel.classList.toggle('hidden');
});

document.querySelector('.panel-close')?.addEventListener('click', () => {
  settingsPanel.classList.add('hidden');
});

// ─── 错误提示关闭 ──────────────────────────────────────

document.getElementById('error-close').addEventListener('click', () => {
  errorToast.classList.add('hidden');
});

// ─── 初始化 ────────────────────────────────────────────

async function init() {
  console.log('[Frank UI] Initializing...');

  try {
    // 获取当前状态
    if (window.frankAPI) {
      const stateInfo = await window.frankAPI.getState();
      if (stateInfo) {
        updateUI(stateInfo.name || 'Idle');
      }
    }
  } catch (e) {
    console.warn('[Frank UI] Failed to get initial state:', e);
  }

  addSystemMessage('Frank 已启动，等待中...');
}

init();
