/**
 * toji-shell/config-manager.js
 *
 * Manages ~/.toji/config.json as specified in Toji Deep Spec (§2).
 * UI configuration state (mode: 'interface' | 'voice').
 * Watches for external changes and notifies listeners immediately without restarts.
 */

'use strict';

const fs   = require('fs');
const path = require('path');
const os   = require('os');

const CONFIG_DIR  = path.join(os.homedir(), '.toji');
const CONFIG_FILE = path.join(CONFIG_DIR, 'config.json');

const DEFAULT_CONFIG = {
  mode: 'interface', // 'interface' | 'voice'
};

let _currentConfig = { ...DEFAULT_CONFIG };
const _listeners = new Set();

function ensureConfigDir() {
  try {
    if (!fs.existsSync(CONFIG_DIR)) {
      fs.mkdirSync(CONFIG_DIR, { recursive: true });
    }
  } catch (err) {
    console.error('[Config] Failed to create config dir:', err.message);
  }
}

function loadConfig() {
  ensureConfigDir();
  try {
    if (fs.existsSync(CONFIG_FILE)) {
      const raw = fs.readFileSync(CONFIG_FILE, 'utf8');
      const parsed = JSON.parse(raw);
      _currentConfig = { ...DEFAULT_CONFIG, ...parsed };
    } else {
      saveConfig(DEFAULT_CONFIG);
    }
  } catch (err) {
    console.warn('[Config] Error loading config, using defaults:', err.message);
    _currentConfig = { ...DEFAULT_CONFIG };
  }
  return _currentConfig;
}

function saveConfig(cfg) {
  ensureConfigDir();
  try {
    _currentConfig = { ..._currentConfig, ...cfg };
    fs.writeFileSync(CONFIG_FILE, JSON.stringify(_currentConfig, null, 2), 'utf8');
    notifyListeners();
  } catch (err) {
    console.error('[Config] Failed to save config:', err.message);
  }
}

function notifyListeners() {
  for (const listener of _listeners) {
    try {
      listener(_currentConfig);
    } catch (e) {
      console.error('[Config] Listener error:', e);
    }
  }
}

function watchConfig() {
  ensureConfigDir();
  try {
    fs.watch(CONFIG_DIR, (eventType, filename) => {
      if (filename === 'config.json' || !filename) {
        // Debounce read
        setTimeout(() => {
          try {
            if (fs.existsSync(CONFIG_FILE)) {
              const raw = fs.readFileSync(CONFIG_FILE, 'utf8');
              const parsed = JSON.parse(raw);
              if (parsed.mode && parsed.mode !== _currentConfig.mode) {
                _currentConfig.mode = parsed.mode;
                console.log('[Config] Mode changed via file watch:', _currentConfig.mode);
                notifyListeners();
              }
            }
          } catch {}
        }, 100);
      }
    });
  } catch (err) {
    console.warn('[Config] Watcher failed:', err.message);
  }
}

function getMode() {
  return _currentConfig.mode || 'interface';
}

function setMode(mode) {
  if (mode !== 'interface' && mode !== 'voice') return;
  saveConfig({ mode });
}

function toggleMode() {
  const newMode = getMode() === 'interface' ? 'voice' : 'interface';
  setMode(newMode);
  return newMode;
}

function onConfigChange(callback) {
  _listeners.add(callback);
  return () => _listeners.delete(callback);
}

// Initial load
loadConfig();
watchConfig();

module.exports = {
  loadConfig,
  saveConfig,
  getMode,
  setMode,
  toggleMode,
  onConfigChange,
};
