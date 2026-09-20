# toji-shell

Electron desktop shell for Toji — the always-available orchestrator agent.

## What this does

- Lives in the **system tray** (taskbar notification area)
- **`Alt+T`** → summon / dismiss the chat overlay from anywhere
- Shows the full Toji chat UI (served by the FastAPI sidecar)
- Small **Lottie avatar** floats alongside the overlay
- Sidecar is auto-spawned on launch, killed on quit

## Running (dev)

> Make sure the project Python environment has `uvicorn` installed.

```powershell
# From this directory:
npm install
npm start
```

## Hotkey

| Shortcut | Action                  |
|----------|-------------------------|
| `Alt+T`  | Toggle overlay + avatar |
| `Escape` | Hide overlay            |

## Architecture

```
main.js          Electron entry point
sidecar.js       Spawns / manages uvicorn
window-manager.js  Overlay + avatar BrowserWindows
tray-manager.js  System tray icon + context menu
preload.js       Secure IPC context bridge
assets/
  avatar.html    Lottie avatar window
  loading.html   Shown while sidecar boots
  toji-idle.json Lottie animation data
  toji-tray.png  Tray icon
```
