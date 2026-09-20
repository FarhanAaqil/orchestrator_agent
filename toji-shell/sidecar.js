/**
 * toji-shell/sidecar.js
 *
 * Manages the FastAPI backend (uvicorn) as a child process.
 *
 * Dev mode   → spawns `uvicorn orchestrator_core.main:app ...`
 * Packaged   → spawns `./resources/toji-backend.exe` (PyInstaller bundle)
 *
 * Exposes:
 *   spawn(opts)    → start the sidecar, resolve when /health is 200
 *   kill()         → send SIGTERM, wait for exit
 *   getStatus()    → 'starting' | 'ready' | 'error' | 'dead'
 *   getApiBase()   → 'http://127.0.0.1:8000'
 */

'use strict';

const { spawn: spawnProc } = require('child_process');
const path = require('path');
const fs   = require('fs');
const http = require('http');
const { app } = require('electron');

const HOST    = '127.0.0.1';
const PORT    = 8000;
const API_BASE = `http://${HOST}:${PORT}`;

let _proc   = null;
let _status = 'idle'; // idle | starting | ready | error | dead

// ── Quick port check ──────────────────────────────────────────────────────────
function isPortListening() {
  return new Promise((resolve) => {
    const req = http.get(`${API_BASE}/health`, (res) => {
      resolve(res.statusCode === 200);
      res.resume();
    });
    req.setTimeout(600, () => { req.destroy(); resolve(false); });
    req.on('error', () => resolve(false));
  });
}

// ── Health poll ───────────────────────────────────────────────────────────────
function pollHealth({ intervalMs = 700, timeoutMs = 45_000 } = {}) {
  return new Promise((resolve, reject) => {
    const deadline = Date.now() + timeoutMs;
    const check = () => {
      http.get(`${API_BASE}/health`, (res) => {
        if (res.statusCode === 200) {
          resolve();
        } else if (Date.now() > deadline) {
          reject(new Error(`Sidecar health check timed out after ${timeoutMs}ms`));
        } else {
          setTimeout(check, intervalMs);
        }
        res.resume();
      }).on('error', () => {
        if (Date.now() > deadline) {
          reject(new Error(`Sidecar health check timed out after ${timeoutMs}ms`));
        } else {
          setTimeout(check, intervalMs);
        }
      });
    };
    setTimeout(check, 300);
  });
}

// ── Spawn ─────────────────────────────────────────────────────────────────────
async function spawn({ dev = true } = {}) {
  _status = 'starting';

  // If the backend is already running (manual dev start), skip spawning
  const alreadyUp = await isPortListening();
  if (alreadyUp) {
    console.log('[Toji sidecar] Backend already on port', PORT, '— skipping spawn');
    _status = 'ready';
    return;
  }

  // Resolve the working directory (project root, one level up from toji-shell/)
  const projectRoot = path.resolve(__dirname, '..');

  let cmd, args, opts;

  if (dev) {
    // Dev: use the system Python/uvicorn in the project root
    cmd  = process.platform === 'win32' ? 'uvicorn' : 'uvicorn';
    args = [
      'orchestrator_core.main:app',
      '--host', HOST,
      '--port', String(PORT),
      '--log-level', 'warning',
    ];
    opts = {
      cwd: projectRoot,
      env: { ...process.env },
      shell: true,           // needed on Windows to find uvicorn on PATH
      windowsHide: true,     // don't flash a console window on Windows
    };
  } else {
    // Packaged: use the bundled sidecar executable
    const exeName = process.platform === 'win32' ? 'toji-backend.exe' : 'toji-backend';
    const exePath = path.join(process.resourcesPath, exeName);
    if (!fs.existsSync(exePath)) {
      _status = 'error';
      throw new Error(`Packaged sidecar not found at ${exePath}`);
    }
    cmd  = exePath;
    args = [];
    opts = { windowsHide: true };
  }

  console.log('[Toji sidecar] Spawning:', cmd, args.join(' '));
  _proc = spawnProc(cmd, args, opts);

  _proc.stdout?.on('data', (d) => console.log('[sidecar]', d.toString().trimEnd()));
  _proc.stderr?.on('data', (d) => console.error('[sidecar]', d.toString().trimEnd()));

  _proc.on('exit', (code, signal) => {
    console.warn(`[Toji sidecar] Exited — code=${code} signal=${signal}`);
    _status = 'dead';
  });

  _proc.on('error', (err) => {
    console.error('[Toji sidecar] Spawn error:', err.message);
    _status = 'error';
  });

  // Wait for the backend to be responsive
  try {
    await pollHealth({ timeoutMs: 30_000 });
    _status = 'ready';
    console.log('[Toji sidecar] Ready at', API_BASE);
  } catch (err) {
    _status = 'error';
    console.error('[Toji sidecar] Health check failed:', err.message);
    // Don't throw — app can still launch with a degraded banner
  }
}

// ── Kill ──────────────────────────────────────────────────────────────────────
function kill() {
  return new Promise((resolve) => {
    if (!_proc || _status === 'dead') { resolve(); return; }

    _proc.on('exit', () => resolve());
    _proc.kill('SIGTERM');

    // Force-kill after 3s if still alive
    setTimeout(() => {
      try { _proc?.kill('SIGKILL'); } catch {}
      resolve();
    }, 3000);
  });
}

// ── Getters ───────────────────────────────────────────────────────────────────
function getStatus()  { return _status; }
function getApiBase() { return API_BASE; }

module.exports = { spawn, kill, getStatus, getApiBase };
