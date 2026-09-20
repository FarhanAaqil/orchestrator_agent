/**
 * toji-shell/tray-manager.js
 *
 * Creates the system-tray icon and context menu.
 *
 * Menu items:
 *   ▸ "Toji — ready"         (non-clickable status label)
 *   ▸ Open Chat              (shows overlay)
 *   ▸ Open in Browser        (opens http://127.0.0.1:8000 in default browser)
 *   ─────────────────────────────────────────────────────────
 *   ▸ Quit Toji
 *
 * Left-click on the tray icon toggles the overlay (Windows behaviour).
 */

'use strict';

const { Tray, Menu, shell, nativeImage, app } = require('electron');
const path = require('path');
const sidecar = require('./sidecar');

// SVG tray icon — rendered inline so we never depend on a file path.
// Electron's nativeImage.createFromDataURL supports SVG on all platforms.
const ICON_SVG = `<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 16 16">
  <defs>
    <radialGradient id="g" cx="38%" cy="35%" r="60%">
      <stop offset="0%"   stop-color="#FCD34D"/>
      <stop offset="55%"  stop-color="#D97706"/>
      <stop offset="100%" stop-color="#92400E"/>
    </radialGradient>
  </defs>
  <circle cx="8" cy="8" r="6" fill="url(#g)"/>
  <circle cx="8" cy="8" r="6" fill="none" stroke="#F59E0B" stroke-width="0.5" opacity="0.6"/>
</svg>`;
const ICON_DATA_URL = `data:image/svg+xml;base64,${Buffer.from(ICON_SVG).toString('base64')}`;

class TrayManager {
  constructor(windowManager) {
    this._wm   = windowManager;
    this._tray = null;
  }

  init() {
    // Build icon — try file first, fall back to inline base64
    let icon = this._buildIcon();

    this._tray = new Tray(icon);
    this._tray.setToolTip('Toji — Alt+T to summon');

    this._buildMenu();

    // Windows/Linux: left-click toggles overlay
    this._tray.on('click', () => {
      this._wm.toggle();
    });
  }

  _buildIcon() {
    // Windows requires .ico for Shell_NotifyIcon to prevent notify_icon.cc warnings
    const candidatePaths = [
      'C:\\Users\\aaqil\\toji-shell-deps\\toji-tray.ico',
      path.join(__dirname, 'assets', 'toji-tray.ico'),
      'C:\\Users\\aaqil\\toji-shell-deps\\toji-tray.png',
      path.join(__dirname, 'assets', 'toji-tray.png'),
    ];

    for (const p of candidatePaths) {
      try {
        if (require('fs').existsSync(p)) {
          const img = nativeImage.createFromPath(p);
          if (!img.isEmpty()) return img;
        }
      } catch {}
    }

    // Fallback: blank
    return nativeImage.createEmpty();
  }


  _buildMenu() {
    const status = sidecar.getStatus();

    const statusLabel =
      status === 'ready'    ? '● Toji — ready'
      : status === 'starting' ? '◌ Toji — starting…'
      : status === 'error'    ? '✕ Toji — backend error'
      :                          '○ Toji — idle';

    const menu = Menu.buildFromTemplate([
      {
        label:   statusLabel,
        enabled: false,
      },
      { type: 'separator' },
      {
        label: 'Open Chat Overlay (Alt+T)',
        click: () => this._wm.show(),
      },
      {
        label: 'Show / Hide Desktop Pet',
        click: () => this._wm.togglePet(),
      },
      {
        label: 'Open Executive Dashboard',
        click: () => this._wm.createDashboard(),
      },
      {
        label: 'Toggle Voice Mode',
        click: () => this._wm.toggleVoice(),
      },
      {
        label: 'Launch at Startup',
        type: 'checkbox',
        checked: app.getLoginItemSettings().openAtLogin,
        click: (item) => {
          app.setLoginItemSettings({
            openAtLogin: item.checked,
            openAsHidden: true,
            name: 'Toji',
          });
        },
      },
      {
        label: 'Open in Browser',
        click: () => shell.openExternal('http://127.0.0.1:8000/'),
      },
      { type: 'separator' },
      {
        label: 'Quit Toji',
        click: () => {
          app.quit();
        },
      },
    ]);

    this._tray.setContextMenu(menu);
  }

  /** Re-render the context menu (call after status changes) */
  refresh() {
    this._buildMenu();
  }
}

module.exports = TrayManager;
