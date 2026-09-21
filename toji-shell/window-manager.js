/**
 * toji-shell/window-manager.js
 *
 * Creates and manages the two Electron windows:
 *
 *  1. Overlay  — the full chat interface (frameless, always-on-top, 460×720)
 *               Loads http://127.0.0.1:8000/ from the sidecar.
 *               Injects a drag handle so the frameless window is movable.
 *
 *  2. Avatar   — small 120×120 Lottie animation window (always-on-top, draggable)
 *               Positioned to the top-left of the overlay.
 *               Receives 'avatar-state' IPC messages to change animation.
 *
 * WindowManager is a singleton — main.js holds the one instance.
 */

'use strict';

const { BrowserWindow, screen } = require('electron');
const path = require('path');

const API_BASE = 'http://127.0.0.1:8000';

// Overlay dimensions
const OW = 460;
const OH = 720;

// Avatar dimensions
const AW = 120;
const AH = 120;

let _instance = null; // singleton reference

class WindowManager {
  constructor({ dev = false } = {}) {
    this._dev            = dev;
    this._overlay        = null;
    this._avatar         = null;
    this._dashboard      = null;
    this._visible        = false;
    this._overlayVisible = false;
    _instance = this;
  }

  static getInstance() { return _instance; }

  // ── Overlay ─────────────────────────────────────────────────────────────────
  createOverlay() {
    const { workArea } = screen.getPrimaryDisplay();

    // Bottom-right of the primary display
    const x = workArea.x + workArea.width  - OW - 20;
    const y = workArea.y + workArea.height - OH - 20;

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
      backgroundColor: '#00000000',
      webPreferences: {
        preload:          path.join(__dirname, 'preload.js'),
        contextIsolation: true,
        nodeIntegration:  false,
        sandbox:          true,
        webSecurity:      true,
      },
    });

    // Step 1: Show branded loading screen immediately
    const loadingPath = path.join(__dirname, 'assets', 'loading.html');
    this._overlay.loadFile(loadingPath);

    // Step 2: Poll sidecar, then navigate to real chat UI
    this._waitForSidecarThenNavigate();

    // Inject drag handle + rounded corners each time a page finishes loading
    this._overlay.webContents.on('did-finish-load', () => {
      this._injectDragHandle();
      this._injectBorderRadius();
      this.show();
    });

    // Escape key hides the overlay
    this._overlay.webContents.on('before-input-event', (_event, input) => {
      if (input.key === 'Escape' && input.type === 'keyDown') {
        this.hide();
      }
    });

    // Open external links in default browser
    this._overlay.webContents.setWindowOpenHandler(({ url }) => {
      const { shell } = require('electron');
      shell.openExternal(url);
      return { action: 'deny' };
    });

    // Reposition avatar when overlay window moves
    this._overlay.on('move', () => {
      this._repositionAvatar();
    });

    this._overlay.on('closed', () => { this._overlay = null; });
  }

  // ── Full Dashboard Window ───────────────────────────────────────────────────
  createDashboard() {
    if (this._dashboard && !this._dashboard.isDestroyed()) {
      this._dashboard.show();
      this._dashboard.focus();
      return;
    }

    this._dashboard = new BrowserWindow({
      width:           1280,
      height:          850,
      minWidth:        900,
      minHeight:       600,
      title:           'Toji — Executive Control Plane',
      backgroundColor: '#B0B8C4',
      autoHideMenuBar: true,
      webPreferences: {
        preload:          path.join(__dirname, 'preload.js'),
        contextIsolation: true,
        nodeIntegration:  false,
        sandbox:          true,
        webSecurity:      true,
      },
    });

    this._dashboard.loadURL(API_BASE);

    this._dashboard.on('closed', () => {
      this._dashboard = null;
    });
  }

  toggleVoice() {
    if (this._overlay && !this._overlay.isDestroyed()) {
      this._overlay.webContents.send('toji:voice-toggle');
    }
    if (this._dashboard && !this._dashboard.isDestroyed()) {
      this._dashboard.webContents.send('toji:voice-toggle');
    }
  }

  /** Poll /health until ready, then navigate the overlay to the real chat UI */
  _waitForSidecarThenNavigate() {
    const http     = require('http');
    const MAX_MS   = 45_000;
    const INTERVAL = 700;
    const start    = Date.now();

    const attempt = () => {
      if (!this._overlay) return; // window was closed before sidecar ready
      if (Date.now() - start > MAX_MS) {
        console.error('[WindowManager] Sidecar did not become ready in time');
        return;
      }
      http.get(`${API_BASE}/health`, (res) => {
        if (res.statusCode === 200) {
          console.log('[WindowManager] Sidecar ready — navigating to chat UI');
          this._overlay?.loadURL(API_BASE);
        } else {
          setTimeout(attempt, INTERVAL);
        }
        res.resume();
      }).on('error', () => setTimeout(attempt, INTERVAL));
    };

    setTimeout(attempt, 500);
  }

  // ── Avatar (Desktop Pet) ─────────────────────────────────────────────────────
  createAvatar() {
    const { workArea } = screen.getPrimaryDisplay();

    // Default desktop pet position: bottom-right corner, 24px padding from taskbar/edge
    const ax = workArea.x + workArea.width - AW - 24;
    const ay = workArea.y + workArea.height - AH - 24;

    this._avatar = new BrowserWindow({
      width:           AW,
      height:          AH,
      x:               ax,
      y:               ay,
      frame:           false,
      transparent:     true,
      alwaysOnTop:     true,
      skipTaskbar:     true,
      resizable:       false,
      hasShadow:       false,
      show:            true, // Visible on screen as a desktop pet!
      backgroundColor: '#00000000',
      webPreferences: {
        preload:          path.join(__dirname, 'preload.js'),
        contextIsolation: true,
        nodeIntegration:  false,
        sandbox:          true,
      },
    });

    this._avatar.loadFile(path.join(__dirname, 'assets', 'avatar.html'));

    this._avatar.once('ready-to-show', () => {
      this._avatar?.show();
      this._avatar?.setAlwaysOnTop(true);
      this._avatar?.moveTop();
    });

    this._avatar.on('closed', () => { this._avatar = null; });
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
    if (this._overlay) {
      // Position overlay neatly to the left of the desktop pet
      if (this._avatar && !this._avatar.isDestroyed()) {
        const [ax, ay] = this._avatar.getPosition();
        const { workArea } = screen.getPrimaryDisplay();
        let ox = ax - OW - 16;
        let oy = Math.min(ay, workArea.y + workArea.height - OH - 16);
        if (ox < workArea.x) ox = ax + AW + 16;
        this._overlay.setPosition(ox, Math.max(workArea.y + 16, oy));
      }
      this._overlay.show();
      this._overlay.setAlwaysOnTop(true);
      this._overlay.moveTop();
      this._overlay.focus();
    }
    // Pet always stays visible on screen
    if (this._avatar && !this._avatar.isDestroyed()) {
      this._avatar.show();
      this._avatar.setAlwaysOnTop(true);
      this._avatar.moveTop();
    }
    this._visible = true;
    this._overlayVisible = true;
  }

  hide() {
    this._overlay?.hide();
    this._overlayVisible = false;
    // Pet stays on desktop!
    if (this._avatar && !this._avatar.isDestroyed()) {
      this._avatar.show();
    }
  }

  togglePet() {
    if (!this._avatar || this._avatar.isDestroyed()) {
      this.createAvatar();
      return;
    }
    if (this._avatar.isVisible()) {
      this._avatar.hide();
    } else {
      this._avatar.show();
      this._avatar.moveTop();
    }
  }

  // ── Mode Management (§2) ──────────────────────────────────────────────────
  setMode(mode) {
    this._mode = mode;
    if (mode === 'voice') {
      // Voice mode: keep overlay window hidden to save GPU/CPU cycles
      this.hide();
      this._avatar?.webContents.send('avatar:set-mode', 'voice');
    } else {
      this._avatar?.webContents.send('avatar:set-mode', 'interface');
    }
  }

  getMode() {
    return this._mode || 'interface';
  }

  // ── Avatar state (§3, §4) ──────────────────────────────────────────────────
  setAvatarState(state) {
    // 'idle' | 'thinking' | 'speaking' | 'needs-you' | 'found-something' | 'starting' | 'error'
    this._avatar?.webContents.send('avatar:set-state', state);
  }

  // ── Internals ─────────────────────────────────────────────────────────────────
  _repositionAvatar() {
    if (!this._overlay || !this._avatar) return;
    const [ox, oy] = this._overlay.getPosition();
    this._avatar.setPosition(ox - AW - 10, oy);
  }

  /** Injects a 28px drag handle bar at the top of the overlay */
  _injectDragHandle() {
    if (!this._overlay?.webContents) return;
    this._overlay.webContents.executeJavaScript(`
      (function() {
        if (document.getElementById('__toji_drag__')) return;
        const bar = document.createElement('div');
        bar.id = '__toji_drag__';
        bar.style.cssText = [
          'position:fixed',
          'top:0',
          'left:0',
          'right:0',
          'height:28px',
          '-webkit-app-region:drag',
          'z-index:2147483647',
          'cursor:grab',
          'background:linear-gradient(to bottom, rgba(15,23,42,0.85) 0%, transparent 100%)',
          'border-radius:12px 12px 0 0',
          'display:flex',
          'align-items:center',
          'justify-content:center',
          'gap:4px',
        ].join(';');

        // Dots pill indicator
        const dots = document.createElement('div');
        dots.style.cssText = 'display:flex;gap:4px;pointer-events:none;-webkit-app-region:no-drag;';
        for (let i = 0; i < 3; i++) {
          const d = document.createElement('div');
          d.style.cssText = 'width:6px;height:6px;border-radius:50%;background:rgba(255,255,255,0.25)';
          dots.appendChild(d);
        }
        bar.appendChild(dots);
        document.body.appendChild(bar);

        // Non-draggable for interactive elements
        document.querySelectorAll('input,textarea,button,a,[role="button"]').forEach(el => {
          el.style.webkitAppRegion = 'no-drag';
        });
      })();
    `).catch(() => {});
  }

  /** Clips the overlay to rounded corners via CSS injection */
  _injectBorderRadius() {
    if (!this._overlay?.webContents) return;
    this._overlay.webContents.insertCSS(`
      html, body {
        border-radius: 12px !important;
        overflow: hidden !important;
      }
    `).catch(() => {});
  }
}

module.exports = WindowManager;
