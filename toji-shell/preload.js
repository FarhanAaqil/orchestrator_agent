/**
 * toji-shell/preload.js
 *
 * Secure context-bridge between the Electron main process and renderer pages.
 *
 * Exposes a minimal `window.toji` API to renderer pages:
 *
 *   window.toji.hide()               → hide the overlay
 *   window.toji.getStatus()          → Promise<{sidecar, dev}>
 *   window.toji.getApiBase()         → Promise<string>
 *   window.toji.setAvatarState(s)    → tell avatar to change state
 *   window.toji.onAvatarState(cb)    → (avatar.html only) receive state changes
 *
 * Nothing from Node.js / Electron is exposed beyond this whitelist.
 */

'use strict';

const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('toji', {
  /** Hide the overlay window */
  hide: () => ipcRenderer.send('toji:hide'),

  /** Get runtime status from main */
  getStatus: () => ipcRenderer.invoke('toji:get-status'),

  /** Get the sidecar API base URL */
  getApiBase: () => ipcRenderer.invoke('toji:get-api-base'),

  /** Push an avatar state change ('idle' | 'thinking' | 'speaking' | 'error') */
  setAvatarState: (state) => ipcRenderer.send('toji:avatar-state', state),

  /** Avatar window: subscribe to state changes pushed from main */
  onAvatarState: (callback) => {
    ipcRenderer.on('avatar:set-state', (_event, state) => callback(state));
  },

  /** Subscribe to voice toggle events triggered from tray or main */
  onVoiceToggle: (callback) => {
    ipcRenderer.on('toji:voice-toggle', () => callback());
  },

  /** Request voice toggle from renderer */
  toggleVoice: () => ipcRenderer.send('toji:toggle-voice'),

  /** Toggle the chat overlay window */
  toggleOverlay: () => ipcRenderer.send('toji:toggle-overlay'),

  /** Get current UI mode ('interface' | 'voice') */
  getMode: () => ipcRenderer.invoke('toji:get-mode'),

  /** Set current UI mode ('interface' | 'voice') */
  setMode: (mode) => ipcRenderer.send('toji:set-mode', mode),

  /** Subscribe to mode changes */
  onModeChange: (callback) => {
    ipcRenderer.on('toji:mode-changed', (_event, mode) => callback(mode));
  },

  /** Open the full Executive Dashboard in a separate window */
  openDashboard: () => ipcRenderer.send('toji:open-dashboard'),

  /** Overlay window: focus prompt input when window shown */
  onFocusInput: (callback) => {
    ipcRenderer.on('toji:focus-input', () => callback());
  },

  /** Overlay window: notification when backend sidecar is ready */
  onBackendReady: (callback) => {
    ipcRenderer.on('toji:backend-ready', () => callback());
  },
});
