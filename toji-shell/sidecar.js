/**
 * toji-shell/sidecar.js
 *
 * Deep Spec (§1) Always-on backend manager:
 *   1. GET localhost:8000/health with 1.5s fast timeout.
 *   2. If healthy → ready immediately (sub-100ms launch).
 *   3. If unhealthy → execute `docker compose up -d` as fallback
 *      (with dev uvicorn / local exe fallback).
 *   4. Poll health check every 500ms up to 10s.
 */

'use strict';

const { spawn: spawnProc, exec } = require('child_process');
const path = require('path');
const fs   = require('fs');
const http = require('http');

const HOST     = '127.0.0.1';
const PORT     = 8000;
const API_BASE = `http://${HOST}:${PORT}`;

let _proc   = null;
let _status = 'idle'; // idle | starting | ready | error | dead

// ── Quick port check (400ms fast timeout) ────────────────────────────────────
function isPortListening(timeoutMs = 400) {
  return new Promise((resolve) => {
    const req = http.get(`${API_BASE}/health`, (res) => {
      resolve(res.statusCode === 200);
      res.resume();
    });
    req.setTimeout(timeoutMs, () => {
      req.destroy();
      resolve(false);
    });
    req.on('error', () => resolve(false));
  });
}

// ── Health poll (250ms interval up to 8s) ─────────────────────────────────────
function pollHealth({ intervalMs = 250, timeoutMs = 8_000 } = {}) {
  return new Promise((resolve, reject) => {
    const deadline = Date.now() + timeoutMs;
    const check = () => {
      http.get(`${API_BASE}/health`, (res) => {
        if (res.statusCode === 200) {
          resolve();
        } else if (Date.now() > deadline) {
          reject(new Error(`Backend did not become healthy within ${timeoutMs}ms`));
        } else {
          setTimeout(check, intervalMs);
        }
        res.resume();
      }).on('error', () => {
        if (Date.now() > deadline) {
          reject(new Error(`Backend did not become healthy within ${timeoutMs}ms`));
        } else {
          setTimeout(check, intervalMs);
        }
      });
    };
    setTimeout(check, 100);
  });
}

// ── Execute Docker Compose fallback (Fast 1.5s probe) ─────────────────────────
function tryDockerComposeUp(projectRoot) {
  return new Promise((resolve) => {
    // Fast 1.5s check. If Docker daemon is stopped, fail fast to local python
    const cmd = 'docker compose up -d';
    console.log('[Toji sidecar] Fast probe for Docker backend:', cmd);
    exec(cmd, { cwd: projectRoot, timeout: 1500 }, (err, stdout) => {
      if (!err) {
        console.log('[Toji sidecar] Docker backend running:', stdout.trim());
        resolve(true);
      } else {
        console.log('[Toji sidecar] Docker not active or cold, proceeding directly to local runner');
        resolve(false);
      }
    });
  });
}

// ── Spawn / Startup Chain ────────────────────────────────────────────────────
async function spawn({ dev = true, onStarting = null } = {}) {
  _status = 'starting';

  // Step 1: 1.5s fast health check
  const warm = await isPortListening(1500);
  if (warm) {
    console.log('[Toji sidecar] Backend already warm & listening on', PORT);
    _status = 'ready';
    return;
  }

  // Notify avatar to show "starting up..." state
  if (typeof onStarting === 'function') {
    onStarting();
  }

  const projectRoot = path.resolve(__dirname, '..');

  // Step 2: Try Docker Compose up -d fallback
  console.log('[Toji sidecar] Backend cold — attempting Docker startup fallback...');
  const dockerStarted = await tryDockerComposeUp(projectRoot);

  if (!dockerStarted) {
    // Step 3: Local process fallback (dev uvicorn or packaged exe)
    console.log('[Toji sidecar] Starting local backend process fallback...');
    let cmd, args, opts;

    if (dev) {
      cmd  = 'uvicorn';
      args = [
        'orchestrator_core.main:app',
        '--host', HOST,
        '--port', String(PORT),
        '--log-level', 'warning',
      ];
      opts = {
        cwd: projectRoot,
        env: { ...process.env },
        shell: true,
        windowsHide: true,
      };
    } else {
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
  }

  // Step 4: Poll health every 500ms up to 10s
  try {
    await pollHealth({ intervalMs: 500, timeoutMs: 10_000 });
    _status = 'ready';
    console.log('[Toji sidecar] Ready at', API_BASE);
  } catch (err) {
    _status = 'error';
    console.error('[Toji sidecar] Startup timeout:', err.message);
  }
}

// ── Kill ──────────────────────────────────────────────────────────────────────
function kill() {
  return new Promise((resolve) => {
    if (!_proc || _status === 'dead') { resolve(); return; }

    _proc.on('exit', () => resolve());
    _proc.kill('SIGTERM');

    setTimeout(() => {
      try { _proc?.kill('SIGKILL'); } catch {}
      resolve();
    }, 3000);
  });
}

function getStatus()  { return _status; }
function getApiBase() { return API_BASE; }

module.exports = { spawn, kill, getStatus, getApiBase };
