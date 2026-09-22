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

const path = require('path');
const fs   = require('fs');

// Ensure external dependencies directory is always in module search path
try {
  const Module = require('module');
  const depsDir = 'C:\\Users\\aaqil\\toji-shell-deps\\node_modules';
  if (Module.globalPaths && !Module.globalPaths.includes(depsDir)) {
    Module.globalPaths.push(depsDir);
  }
} catch {}

const { app, BrowserWindow, globalShortcut, ipcMain, screen, nativeImage } = require('electron');

// Local modules
const sidecar      = require('./sidecar');
const TrayManager  = require('./tray-manager');
const WindowManager = require('./window-manager');

process.on('uncaughtException', (err) => {
  console.error('[Toji UncaughtException]', err);
});
process.on('unhandledRejection', (reason) => {
  console.error('[Toji UnhandledRejection]', reason);
});

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

  // Build windows
  const wm = new WindowManager({ dev: IS_DEV });
  wm.createOverlay();

  // Load UI configuration mode
  const configManager = require('./config-manager');
  wm.setMode(configManager.getMode());

  // Create tray AFTER windows exist (Windows 11 requirement)
  const tray = new TrayManager(wm);
  tray.init();

  // Open the Orchestrator Agent Executive Control Panel immediately on launch
  wm.createDashboard();

  // React to config mode changes without app restart
  configManager.onConfigChange((cfg) => {
    wm.setMode(cfg.mode);
    tray.refresh();
  });

  // ── Global hotkeys ──────────────────────────────────────────────────────────
  // Alt+T to toggle compact overlay
  const HOTKEY = 'Alt+T';
  const registered = globalShortcut.register(HOTKEY, () => {
    wm.toggle();
  });
  if (!registered) {
    console.warn('[Toji] Could not register hotkey', HOTKEY);
  } else {
    console.log('[Toji] Hotkey registered:', HOTKEY);
  }

  // Ctrl+Shift+V to toggle Interface vs Voice-only modes
  const MODE_HOTKEY = 'CommandOrControl+Shift+V';
  const modeRegistered = globalShortcut.register(MODE_HOTKEY, () => {
    const newMode = configManager.toggleMode();
    console.log('[Toji] Mode toggled via hotkey to:', newMode);
  });
  if (!modeRegistered) {
    console.warn('[Toji] Could not register mode hotkey', MODE_HOTKEY);
  } else {
    console.log('[Toji] Mode hotkey registered:', MODE_HOTKEY);
  }

  // Start the FastAPI sidecar asynchronously in background (non-blocking)
  sidecar.spawn({
    dev: IS_DEV,
  }).then(() => {
    tray.refresh();
    wm.notifyBackendReady();
  }).catch((err) => {
    console.error('[Toji main] Sidecar spawn background error:', err);
    tray.refresh();
  });

  // macOS: re-create window when dock icon clicked
  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      wm.createDashboard();
    }
  });
});

// ── Second instance → focus existing overlay ──────────────────────────────────
app.on('second-instance', () => {
  // If someone tried to open a second instance, show and focus Executive Control Panel
  const wm = WindowManager.getInstance();
  if (wm) wm.createDashboard();
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

ipcMain.on('toji:open-dashboard', () => {
  const wm = WindowManager.getInstance();
  if (wm) wm.createDashboard();
});

ipcMain.on('toji:toggle-voice', () => {
  const wm = WindowManager.getInstance();
  if (wm) wm.toggleVoice();
});

ipcMain.handle('toji:get-mode', () => {
  const configManager = require('./config-manager');
  return configManager.getMode();
});

ipcMain.on('toji:set-mode', (_event, mode) => {
  const configManager = require('./config-manager');
  configManager.setMode(mode);
});

ipcMain.handle('toji:get-api-base', () => {
  return sidecar.getApiBase();
});

ipcMain.handle('toji:get-status', () => {
  return { sidecar: sidecar.getStatus(), dev: IS_DEV };
});
