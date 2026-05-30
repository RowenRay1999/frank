const fs = require('fs');
const path = require('path');

/**
 * 加载 Frank 配置文件 (YAML)
 * Phase 1: 使用简易 YAML 解析器（仅支持嵌套键值、列表、字符串、数字、布尔值）
 * 后续可替换为 js-yaml 库
 */
function loadConfig() {
  const configPath = path.join(__dirname, '..', '..', '..', 'config', 'frank.yaml');

  if (!fs.existsSync(configPath)) {
    console.warn('[Config] config/frank.yaml not found, using defaults');
    return getDefaultConfig();
  }

  try {
    const content = fs.readFileSync(configPath, 'utf-8');
    return parseSimpleYaml(content);
  } catch (err) {
    console.error('[Config] Failed to parse config:', err.message);
    return getDefaultConfig();
  }
}

/**
 * 简易 YAML 解析器
 * 支持：嵌套键值（缩进）、列表（- 前缀）、字符串、数字、布尔值、null
 */
function parseSimpleYaml(content) {
  const lines = content.split('\n');
  const root = {};
  const stack = [{ obj: root, indent: -1 }];

  for (const line of lines) {
    // 跳过空行和注释
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith('#')) continue;

    const indent = line.search(/\S/);

    // 弹出比当前缩进更深的层级
    while (stack.length > 1 && stack[stack.length - 1].indent >= indent) {
      stack.pop();
    }

    const current = stack[stack.length - 1].obj;

    // 列表项
    if (trimmed.startsWith('- ')) {
      const value = parseValue(trimmed.slice(2).trim());
      const parentKey = stack[stack.length - 1]._listKey;
      if (!Array.isArray(current[parentKey])) {
        current[parentKey] = [];
      }
      current[parentKey].push(value);
      continue;
    }

    // 键值对
    const colonIdx = trimmed.indexOf(':');
    if (colonIdx === -1) continue;

    const key = trimmed.slice(0, colonIdx).trim();
    const rest = trimmed.slice(colonIdx + 1).trim();

    if (rest === '' || rest === '{}') {
      // 嵌套对象开始
      const newObj = {};
      current[key] = newObj;
      stack.push({ obj: newObj, indent, _listKey: key });
    } else {
      current[key] = parseValue(rest);
    }
  }

  return root;
}

function parseValue(str) {
  // 去掉行内注释
  const commentIdx = str.indexOf(' #');
  if (commentIdx !== -1) str = str.slice(0, commentIdx).trim();

  // 行内数组: [1, 2, 4, 8, 16, 30]
  if (str.startsWith('[') && str.endsWith(']')) {
    const inner = str.slice(1, -1).trim();
    if (inner === '') return [];
    return inner.split(',').map((item) => parseValue(item.trim()));
  }

  // 行内对象: {key: val}
  if (str.startsWith('{') && str.endsWith('}')) {
    return {}; // 暂不深度解析，返回空对象
  }

  // 带引号的字符串
  if ((str.startsWith('"') && str.endsWith('"')) || (str.startsWith("'") && str.endsWith("'"))) {
    return str.slice(1, -1);
  }

  // null
  if (str === 'null' || str === '~') return null;

  // 布尔值
  if (str === 'true') return true;
  if (str === 'false') return false;

  // 数字
  if (/^-?\d+(\.\d+)?$/.test(str)) {
    return str.includes('.') ? parseFloat(str) : parseInt(str, 10);
  }

  return str;
}

function getDefaultConfig() {
  return {
    camera: { device_id: 0, width: 640, height: 480, fps_idle: 1, fps_aware: 5, fps_active: 10, detection_confidence: 0.7 },
    microphone: { device_id: null, sample_rate: 16000, chunk_size: 512, channels: 1 },
    wake_word: { text: 'Hey Frank', confidence_threshold: 0.7, face_cooldown_ms: 1000 },
    websocket: { host: 'localhost', port: 8765, port_max_retries: 15, heartbeat_interval: 5, heartbeat_missed_max: 3, reconnect_backoff: [1, 2, 4, 8, 16, 30] },
    state_machine: { timeout_aware_to_idle: 30, timeout_auth_delay: 2, timeout_chat_to_auth: 300, timeout_auth_to_idle: 60 },
    logging: { level: 'INFO', file: 'logs/frank.log', max_size_mb: 10, backup_count: 3 },
    app: { auto_start: true, minimize_to_tray: true, always_on_top: false, language: 'zh-CN' },
  };
}

module.exports = { loadConfig };
