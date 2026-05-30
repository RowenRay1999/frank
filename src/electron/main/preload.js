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
});
