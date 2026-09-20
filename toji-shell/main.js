/**
 * toji-shell/main.js
 *
 * Electron main process — Toji Desktop Shell bootstrap.
 *
 * Responsibilities:
 *  1. Spawn the FastAPI sidecar process (uvicorn / bundled exe)
 *  2. Create the system-tray icon and context menu
 *  3. Create the chat overlay BrowserWindow (frameless, always-on-top)
 *  4. Create the Lottie avatar BrowserWindow (small, floating)
 *  5. Register the global hotkey (Alt+T) to toggle both windows
 *  6. Clean up sidecar on quit
 */

'use strict';

const { app, BrowserWindow, globalShortcut, ipcMain, screen, nativeImage } = require('electron');
const path = require('path');
const fs   = require('fs');

// Local modules
const sidecar      = require('./sidecar');
const TrayManager  = require('./tray-manager');
const WindowManager = require('./window-manager');

// ── Dev flag ─────────────────────────────────────────────────────────────────
const IS_DEV = Boolean(process.env.TOJI_DEV) || !app.isPackaged;

// Prevent multiple instances
if (!app.requestSingleInstanceLock()) {
  app.quit();
  process.exit(0);
}

// ── App lifecycle ─────────────────────────────────────────────────────────────
app.whenReady().then(async () => {
  // On Windows, the tray requires the app to have at least one window handle
  // before Shell_NotifyIcon succeeds. Create a hidden 1×1 anchor window first.
  const anchor = new BrowserWindow({
    width: 1, height: 1,
    show: false,
    skipTaskbar: true,
    frame: false,
    transparent: true,
    webPreferences: { nodeIntegration: false, contextIsolation: true },
  });
  anchor.loadURL('about:blank');

  // Enable openAtLogin by default in packaged distribution
  if (!IS_DEV) {
    const current = app.getLoginItemSettings();
    if (!current.openAtLogin) {
      app.setLoginItemSettings({ openAtLogin: true, openAsHidden: true, name: 'Toji' });
    }
  }

  // Start the FastAPI sidecar
  await sidecar.spawn({ dev: IS_DEV });

  // Build overlay + avatar windows
  const wm = new WindowManager({ dev: IS_DEV });
  wm.createOverlay();
  wm.createAvatar();

  // Create tray AFTER windows exist (Windows 11 requirement)
  const tray = new TrayManager(wm);
  tray.init();

  // ── Global hotkey ── Alt+T to toggle the overlay
  const HOTKEY = 'Alt+T';
  const registered = globalShortcut.register(HOTKEY, () => {
    wm.toggle();
  });
  if (!registered) {
    console.warn('[Toji] Could not register hotkey', HOTKEY);
  } else {
    console.log('[Toji] Hotkey registered:', HOTKEY);
  }

  // macOS: re-create window when dock icon clicked
  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      wm.createOverlay();
    }
  });
});

// ── Second instance → focus existing overlay ──────────────────────────────────
app.on('second-instance', () => {
  // If someone tried to open a second instance, show our overlay instead
  const wm = WindowManager.getInstance();
  if (wm) wm.show();
});

// ── Quit: kill sidecar, unregister hotkeys ────────────────────────────────────
app.on('before-quit', async () => {
  globalShortcut.unregisterAll();
  await sidecar.kill();
});

// Keep running in background (don't quit when all windows closed)
app.on('window-all-closed', (e) => {
  // Do nothing — Toji lives in the tray
  e.preventDefault?.();
});

// ── IPC handlers from renderer/preload ───────────────────────────────────────
ipcMain.on('toji:hide', () => {
  const wm = WindowManager.getInstance();
  if (wm) wm.hide();
});

ipcMain.on('toji:toggle-overlay', () => {
  const wm = WindowManager.getInstance();
  if (wm) wm.toggle();
});

ipcMain.on('toji:avatar-state', (_event, state) => {
  const wm = WindowManager.getInstance();
  if (wm) wm.setAvatarState(state); // 'idle' | 'thinking' | 'speaking'
});

ipcMain.on('toji:toggle-voice', () => {
  const wm = WindowManager.getInstance();
  if (wm) wm.toggleVoice();
});

ipcMain.handle('toji:get-api-base', () => {
  return sidecar.getApiBase();
});

ipcMain.handle('toji:get-status', () => {
  return { sidecar: sidecar.getStatus(), dev: IS_DEV };
});
