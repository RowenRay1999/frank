const { ipcMain } = require('electron');

/**
 * Electron 主进程 ↔ 渲染进程 IPC 桥
 * Phase 1: 基础状态同步 + 启动/停止控制
 */

function createIPC(mainWindow, { sendMessage, getState }) {
  // 渲染进程请求当前状态
  ipcMain.handle('frank:getState', () => {
    return getState ? getState() : { name: 'Idle', timeInState: 0 };
  });

  // 渲染进程请求发送消息到 Python
  ipcMain.handle('frank:sendMessage', (_event, msg) => {
    if (sendMessage) {
      sendMessage(msg);
      return { ok: true };
    }
    return { ok: false, error: 'WebSocket not connected' };
  });

  // 渲染进程询问连接状态
  ipcMain.handle('frank:getConnectionStatus', () => {
    return { connected: !!mainWindow };
  });

  return {
    // 后续可扩展更多 IPC 通道
  };
}

module.exports = { createIPC };
