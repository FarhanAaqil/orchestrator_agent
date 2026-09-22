/**
 * toji-shell/window-manager.js
 *
 * Creates and manages the Electron windows:
 *
 *  1. Dashboard — Orchestrator Agent Executive Control Panel (1280×850)
 *                 The primary command center loading http://127.0.0.1:8000/
 *
 *  2. Overlay   — Compact companion chat interface (frameless, always-on-top, 460×720)
 *                 Loads local assets/chat.html for rapid (<15ms) prompts.
 *
 * WindowManager is a singleton — main.js holds the one instance.
 */

'use strict';

const { BrowserWindow, screen, shell } = require('electron');
const path = require('path');

const API_BASE = 'http://127.0.0.1:8000';

// Overlay dimensions
const OW = 460;
const OH = 720;

let _instance = null; // singleton reference

class WindowManager {
  constructor({ dev = false } = {}) {
    this._dev            = dev;
    this._overlay        = null;
    this._dashboard      = null;
    this._visible        = false;
    this._overlayVisible = false;
    _instance = this;
  }

  static getInstance() { return _instance; }

  // ── Executive Control Panel Window (Primary Command Center) ──────────────────
  createDashboard() {
    if (this._dashboard && !this._dashboard.isDestroyed()) {
      if (this._dashboard.isMinimized()) this._dashboard.restore();
      this._dashboard.show();
      this._dashboard.focus();
      return this._dashboard;
    }

    const { workArea } = screen.getPrimaryDisplay();
    const dw = Math.min(1360, workArea.width - 40);
    const dh = Math.min(880, workArea.height - 40);

    const iconPath = path.join(__dirname, 'assets', 'toji-tray.ico');

    this._dashboard = new BrowserWindow({
      width:           dw,
      height:          dh,
      minWidth:        960,
      minHeight:       640,
      title:           'Orchestrator Agent — Executive Control Panel',
      backgroundColor: '#B0B8C4',
      icon:            iconPath,
      autoHideMenuBar: true,
      show:            false,
      webPreferences: {
        preload:          path.join(__dirname, 'preload.js'),
        contextIsolation: true,
        nodeIntegration:  false,
        sandbox:          true,
        webSecurity:      true,
      },
    });

    this._dashboard.loadURL(API_BASE);

    this._dashboard.once('ready-to-show', () => {
      this._dashboard?.show();
      this._dashboard?.focus();
    });

    this._dashboard.webContents.setWindowOpenHandler(({ url }) => {
      shell.openExternal(url);
      return { action: 'deny' };
    });

    this._dashboard.on('closed', () => {
      this._dashboard = null;
    });

    return this._dashboard;
  }

  showControlPanel() {
    return this.createDashboard();
  }

  // ── Compact Chat Overlay ───────────────────────────────────────────────────
  createOverlay() {
    if (this._overlay && !this._overlay.isDestroyed()) {
      return this._overlay;
    }

    const { workArea } = screen.getPrimaryDisplay();

    // Position in bottom-right corner with 24px padding
    const x = workArea.x + workArea.width  - OW - 24;
    const y = workArea.y + workArea.height - OH - 24;

    const iconPath = path.join(__dirname, 'assets', 'toji-tray.ico');

    this._overlay = new BrowserWindow({
      width:           OW,
      height:          OH,
      x,
      y,
      frame:           false,
      transparent:     true,
      alwaysOnTop:     true,
      skipTaskbar:     true,
      resizable:       true,
      minimizable:     false,
      maximizable:     false,
      hasShadow:       true,
      show:            false,
      icon:            iconPath,
      backgroundColor: '#00000000',
      webPreferences: {
        preload:          path.join(__dirname, 'preload.js'),
        contextIsolation: true,
        nodeIntegration:  false,
        sandbox:          true,
        webSecurity:      true,
      },
    });

    // Load instant, zero-CDN local companion chat UI (<15ms)
    const chatPath = path.join(__dirname, 'assets', 'chat.html');
    this._overlay.loadFile(chatPath);

    // Escape key hides the overlay
    this._overlay.webContents.on('before-input-event', (_event, input) => {
      if (input.key === 'Escape' && input.type === 'keyDown') {
        this.hide();
      }
    });

    // Open external links in default browser
    this._overlay.webContents.setWindowOpenHandler(({ url }) => {
      shell.openExternal(url);
      return { action: 'deny' };
    });

    this._overlay.on('closed', () => {
      this._overlay = null;
      this._overlayVisible = false;
    });

    return this._overlay;
  }

  // ── Voice Mode Toggle ────────────────────────────────────────────────────────
  toggleVoice() {
    if (this._overlay && !this._overlay.isDestroyed()) {
      this._overlay.webContents.send('toji:voice-toggle');
    }
    if (this._dashboard && !this._dashboard.isDestroyed()) {
      this._dashboard.webContents.send('toji:voice-toggle');
    }
  }

  /** Notify windows that backend sidecar is ready */
  notifyBackendReady() {
    if (this._overlay && !this._overlay.isDestroyed()) {
      this._overlay.webContents.send('toji:backend-ready');
    }
    if (this._dashboard && !this._dashboard.isDestroyed()) {
      // If dashboard failed to load previously because backend was cold, reload it
      const currentURL = this._dashboard.webContents.getURL();
      if (!currentURL || currentURL.startsWith('chrome-error://') || currentURL === 'about:blank') {
        this._dashboard.loadURL(API_BASE);
      }
    }
  }

  // ── Toggle / Show / Hide ─────────────────────────────────────────────────────
  toggle() {
    if (this._overlayVisible) {
      this.hide();
    } else {
      this.show();
    }
  }

  show() {
    if (!this._overlay || this._overlay.isDestroyed()) {
      this.createOverlay();
    }
    if (this._overlay) {
      const { workArea } = screen.getPrimaryDisplay();
      const ox = workArea.x + workArea.width - OW - 24;
      const oy = workArea.y + workArea.height - OH - 24;
      this._overlay.setPosition(ox, oy);

      this._overlay.show();
      this._overlay.setAlwaysOnTop(true);
      this._overlay.moveTop();
      this._overlay.focus();
      this._overlay.webContents.send('toji:focus-input');
    }
    this._visible = true;
    this._overlayVisible = true;
  }

  hide() {
    this._overlay?.hide();
    this._overlayVisible = false;
  }

  // ── Mode Management ──────────────────────────────────────────────────────────
  setMode(mode) {
    this._mode = mode;
    if (mode === 'voice') {
      this.hide();
    }
  }

  getMode() {
    return this._mode || 'interface';
  }
}

module.exports = WindowManager;
