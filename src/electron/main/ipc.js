const { ipcMain, app, dialog } = require('electron');

/**
 * Electron 主进程 ↔ 渲染进程 IPC 桥
 * Phase 1: 基础状态同步 + 窗口控制 + 启动/停止控制
 */

function createIPC(mainWindow, { sendMessage, getState, createPreviewWindow, closePreviewWindow }) {
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

  // ── 窗口控制 IPC ──

  // 最小化窗口
  ipcMain.handle('frank:minimizeWindow', () => {
    if (mainWindow && !mainWindow.isDestroyed()) {
      mainWindow.minimize();
    }
  });

  // 隐藏窗口到系统托盘
  ipcMain.handle('frank:hideWindow', () => {
    if (mainWindow && !mainWindow.isDestroyed()) {
      mainWindow.hide();
    }
  });

  // 关闭窗口（触发 close 事件 → 根据配置最小化到托盘或退出）
  ipcMain.handle('frank:closeWindow', () => {
    if (mainWindow && !mainWindow.isDestroyed()) {
      mainWindow.close();
    }
  });

  // 退出应用程序
  ipcMain.handle('frank:quitApp', async () => {
    const { response } = await dialog.showMessageBox(mainWindow, {
      type: 'question',
      buttons: ['取消', '退出'],
      defaultId: 0,
      cancelId: 0,
      title: '退出 Frank',
      message: '确定要退出 Frank 吗？',
      detail: '退出后语音唤醒、身份识别等后台服务将停止运行。',
    });

    if (response === 1) {
      app.isQuitting = true;
      app.quit();
      return { confirmed: true };
    }
    return { confirmed: false };
  });

  // ── 预览窗口 IPC ──
  ipcMain.handle('frank:openPreview', () => {
    if (createPreviewWindow) createPreviewWindow();
  });

  ipcMain.handle('frank:closePreview', () => {
    if (closePreviewWindow) closePreviewWindow();
  });

  // ── 设备控制 IPC ──
  ipcMain.handle('frank:toggleCamera', () => {
    if (sendMessage) sendMessage({ type: 'camera.toggle' });
  });

  ipcMain.handle('frank:toggleMicrophone', () => {
    if (sendMessage) sendMessage({ type: 'microphone.toggle' });
  });

  return {
    // 后续可扩展更多 IPC 通道
  };
}

module.exports = { createIPC };
