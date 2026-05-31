const { contextBridge, ipcRenderer } = require('electron');

/**
 * Electron preload 脚本
 * 通过 contextBridge 向渲染进程暴露安全的 API
 */

contextBridge.exposeInMainWorld('frankAPI', {
  // ── 状态查询 ──
  getState: () => ipcRenderer.invoke('frank:getState'),

  // ── 消息发送 ──
  sendMessage: (msg) => ipcRenderer.invoke('frank:sendMessage', msg),

  // ── 连接状态 ──
  getConnectionStatus: () => ipcRenderer.invoke('frank:getConnectionStatus'),

  // ── 窗口控制 ──
  minimizeWindow: () => ipcRenderer.invoke('frank:minimizeWindow'),
  closeWindow: () => ipcRenderer.invoke('frank:closeWindow'),
  hideWindow: () => ipcRenderer.invoke('frank:hideWindow'),
  quitApp: () => ipcRenderer.invoke('frank:quitApp'),

  // ── 事件监听 ──
  onStateChanged: (callback) => {
    const handler = (_event, data) => callback(data);
    ipcRenderer.on('state:changed', handler);
    return () => ipcRenderer.removeListener('state:changed', handler);
  },

  onFaceDetected: (callback) => {
    const handler = (_event, data) => callback(data);
    ipcRenderer.on('camera:face_detected', handler);
    return () => ipcRenderer.removeListener('camera:face_detected', handler);
  },

  onFaceLost: (callback) => {
    const handler = (_event, data) => callback(data);
    ipcRenderer.on('camera:face_lost', handler);
    return () => ipcRenderer.removeListener('camera:face_lost', handler);
  },

  onVoiceStart: (callback) => {
    const handler = (_event, data) => callback(data);
    ipcRenderer.on('mic:voice_start', handler);
    return () => ipcRenderer.removeListener('mic:voice_start', handler);
  },

  onVoiceEnd: (callback) => {
    const handler = (_event, data) => callback(data);
    ipcRenderer.on('mic:voice_end', handler);
    return () => ipcRenderer.removeListener('mic:voice_end', handler);
  },

  onWakeWord: (callback) => {
    const handler = (_event, data) => callback(data);
    ipcRenderer.on('mic:wake_word', handler);
    return () => ipcRenderer.removeListener('mic:wake_word', handler);
  },

  onError: (callback) => {
    const handler = (_event, data) => callback(data);
    ipcRenderer.on('error', handler);
    return () => ipcRenderer.removeListener('error', handler);
  },

  // ── Phase 2: Identity events ──
  onIdentityConfirmed: (callback) => {
    const handler = (_event, data) => callback(data);
    ipcRenderer.on('identity:confirmed', handler);
    return () => ipcRenderer.removeListener('identity:confirmed', handler);
  },

  onIdentityChanging: (callback) => {
    const handler = (_event, data) => callback(data);
    ipcRenderer.on('identity:changing', handler);
    return () => ipcRenderer.removeListener('identity:changing', handler);
  },

  onIdentityUnknown: (callback) => {
    const handler = (_event, data) => callback(data);
    ipcRenderer.on('identity:unknown', handler);
    return () => ipcRenderer.removeListener('identity:unknown', handler);
  },

  // ── Phase 2: Member events ──
  onMemberList: (callback) => {
    const handler = (_event, data) => callback(data);
    ipcRenderer.on('member.list', handler);
    return () => ipcRenderer.removeListener('member.list', handler);
  },

  onMemberPending: (callback) => {
    const handler = (_event, data) => callback(data);
    ipcRenderer.on('member.pending', handler);
    return () => ipcRenderer.removeListener('member.pending', handler);
  },

  onMemberRegistered: (callback) => {
    const handler = (_event, data) => callback(data);
    ipcRenderer.on('member.identified', handler);
    return () => ipcRenderer.removeListener('member.identified', handler);
  },

  // ── Phase 3: Chat events ──
  onChatSubState: (callback) => {
    const handler = (_event, data) => callback(data);
    ipcRenderer.on('chat.sub_state', handler);
    return () => ipcRenderer.removeListener('chat.sub_state', handler);
  },
  onUserMessage: (callback) => {
    const handler = (_event, data) => callback(data);
    ipcRenderer.on('chat.user_message', handler);
    return () => ipcRenderer.removeListener('chat.user_message', handler);
  },
  onAssistantMessage: (callback) => {
    const handler = (_event, data) => callback(data);
    ipcRenderer.on('chat.assistant_message', handler);
    return () => ipcRenderer.removeListener('chat.assistant_message', handler);
  },

  // ── Phase 3: STT/LLM/TTS events ──
  onSTTTranscription: (callback) => {
    const handler = (_event, data) => callback(data);
    ipcRenderer.on('stt.transcription', handler);
    return () => ipcRenderer.removeListener('stt.transcription', handler);
  },
  onLLMToken: (callback) => {
    const handler = (_event, data) => callback(data);
    ipcRenderer.on('llm.token', handler);
    return () => ipcRenderer.removeListener('llm.token', handler);
  },
  onTTSStart: (callback) => {
    const handler = (_event, data) => callback(data);
    ipcRenderer.on('tts.start', handler);
    return () => ipcRenderer.removeListener('tts.start', handler);
  },

  // ── Phase 5: Gesture events ──
  onGestureDetected: (callback) => {
    const handler = (_event, data) => callback(data);
    ipcRenderer.on('gesture.detected', handler);
    return () => ipcRenderer.removeListener('gesture.detected', handler);
  },

  // ── 媒体设备枚举 ──
  getAudioDevices: async () => {
    try {
      const devices = await navigator.mediaDevices.enumerateDevices();
      return devices
        .filter(d => d.kind === 'audioinput')
        .map(d => ({ deviceId: d.deviceId, label: d.label || `麦克风 (${d.deviceId.slice(0, 8)})` }));
    } catch (e) {
      return [];
    }
  },

  getVideoDevices: async () => {
    try {
      const devices = await navigator.mediaDevices.enumerateDevices();
      return devices
        .filter(d => d.kind === 'videoinput')
        .map(d => ({ deviceId: d.deviceId, label: d.label || `摄像头 (${d.deviceId.slice(0, 8)})` }));
    } catch (e) {
      return [];
    }
  },

  // ── 角色 / 设置事件监听 ──
  onRoleList: (callback) => {
    const handler = (_event, data) => callback(data);
    ipcRenderer.on('role.list', handler);
    return () => ipcRenderer.removeListener('role.list', handler);
  },

  onRoleInfo: (callback) => {
    const handler = (_event, data) => callback(data);
    ipcRenderer.on('role.info', handler);
    return () => ipcRenderer.removeListener('role.info', handler);
  },

  onSettingsCurrent: (callback) => {
    const handler = (_event, data) => callback(data);
    ipcRenderer.on('settings.current', handler);
    return () => ipcRenderer.removeListener('settings.current', handler);
  },

  onSettingsUpdated: (callback) => {
    const handler = (_event, data) => callback(data);
    ipcRenderer.on('settings.updated', handler);
    return () => ipcRenderer.removeListener('settings.updated', handler);
  },

  // ── 预览窗口 ──
  openPreview: () => ipcRenderer.invoke('frank:openPreview'),
  closePreview: () => ipcRenderer.invoke('frank:closePreview'),

  // ── 设备控制 ──
  toggleCamera: () => ipcRenderer.invoke('frank:toggleCamera'),
  toggleMicrophone: () => ipcRenderer.invoke('frank:toggleMicrophone'),

  // ── 设备状态 ──
  onDeviceStatus: (callback) => {
    const handler = (_event, data) => callback(data);
    ipcRenderer.on('device:status', handler);
    return () => ipcRenderer.removeListener('device:status', handler);
  },

  // ── 任务事件 ──
  onTaskUpdated: (callback) => {
    const handler = (_event, data) => callback(data);
    ipcRenderer.on('task.updated', handler);
    return () => ipcRenderer.removeListener('task.updated', handler);
  },
  onTaskCompleted: (callback) => {
    const handler = (_event, data) => callback(data);
    ipcRenderer.on('task.completed', handler);
    return () => ipcRenderer.removeListener('task.completed', handler);
  },
  onTaskFailed: (callback) => {
    const handler = (_event, data) => callback(data);
    ipcRenderer.on('task.failed', handler);
    return () => ipcRenderer.removeListener('task.failed', handler);
  },

  // ── 通知事件 ──
  onNotification: (callback) => {
    const handler = (_event, data) => callback(data);
    ipcRenderer.on('notification', handler);
    return () => ipcRenderer.removeListener('notification', handler);
  },

  // ── 预览窗口数据 (仅预览窗口使用) ──
  onPreviewFrame: (callback) => {
    const handler = (_event, data) => callback(data);
    ipcRenderer.on('preview.frame', handler);
    return () => ipcRenderer.removeListener('preview.frame', handler);
  },
  onPreviewDetections: (callback) => {
    const handler = (_event, data) => callback(data);
    ipcRenderer.on('preview.detections', handler);
    return () => ipcRenderer.removeListener('preview.detections', handler);
  },
  onPreviewAudioSpectrum: (callback) => {
    const handler = (_event, data) => callback(data);
    ipcRenderer.on('preview.audio_spectrum', handler);
    return () => ipcRenderer.removeListener('preview.audio_spectrum', handler);
  },
});
