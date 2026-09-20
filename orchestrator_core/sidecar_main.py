"""
orchestrator_core/sidecar_main.py

Standalone entry point for the PyInstaller-packaged sidecar binary.
Handles bundle paths (sys._MEIPASS), argument parsing, and uvicorn bootstrap.
"""

import argparse
import os
import sys
from pathlib import Path


def setup_bundle_environment() -> None:
    """Set up environment paths when running within a PyInstaller bundle."""
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        bundle_dir = Path(sys._MEIPASS)
        # Ensure the bundle directory is in python path
        if str(bundle_dir) not in sys.path:
            sys.path.insert(0, str(bundle_dir))
        os.environ["TOJI_BUNDLE_DIR"] = str(bundle_dir)


def main() -> None:
    setup_bundle_environment()

    parser = argparse.ArgumentParser(description="Toji Desktop Backend Sidecar")
    parser.add_argument(
        "--host",
        default=os.environ.get("HOST", "127.0.0.1"),
        help="Bind socket host (default: 127.0.0.1)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("PORT", "8000")),
        help="Bind socket port (default: 8000)",
    )
    parser.add_argument(
        "--log-level",
        default=os.environ.get("LOG_LEVEL", "warning"),
        help="Uvicorn log level (default: warning)",
    )
    args = parser.parse_args()

    import uvicorn
    from orchestrator_core.main import app

    uvicorn.run(
        app,
        host=args.host,
        port=args.port,
        log_level=args.log_level,
        access_log=False,
    )


if __name__ == "__main__":
    main()
