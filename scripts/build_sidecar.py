"""
scripts/build_sidecar.py

Packages the FastAPI orchestrator_core into a standalone sidecar executable (toji-backend.exe)
using PyInstaller.

Usage:
    python scripts/build_sidecar.py [--dry-run] [--copy-to-shell]
"""

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description="Build Toji backend PyInstaller sidecar")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print command without executing build",
    )
    parser.add_argument(
        "--copy-to-shell",
        action="store_true",
        default=True,
        help="Copy built binary to toji-shell/resources/ (default: True)",
    )
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parent.parent
    entry_point = project_root / "orchestrator_core" / "sidecar_main.py"
    dist_dir = project_root / "dist"
    build_dir = project_root / "build"
    resources_dir = project_root / "toji-shell" / "resources"

    if not entry_point.exists():
        print(f"Error: Entry point {entry_point} not found.", file=sys.stderr)
        sys.exit(1)

    # Hidden imports required by uvicorn, fastapi, sqlite, and dynamic agents
    hidden_imports = [
        "uvicorn",
        "uvicorn.logging",
        "uvicorn.loops",
        "uvicorn.loops.auto",
        "uvicorn.protocols",
        "uvicorn.protocols.http",
        "uvicorn.protocols.http.auto",
        "uvicorn.protocols.websockets",
        "uvicorn.protocols.websockets.auto",
        "uvicorn.lifespans",
        "uvicorn.lifespans.on",
        "fastapi",
        "pydantic",
        "sqlite3",
        "aiosqlite",
        "orchestrator_core",
        "orchestrator_core.main",
        "orchestrator_core.config",
        "orchestrator_core.exceptions",
        "orchestrator_core.models",
        "orchestrator_core.agents.general_chat_agent",
        "orchestrator_core.agents.email_agent",
        "orchestrator_core.agents.github_agent",
        "orchestrator_core.agents.linkedin_agent",
        "orchestrator_core.agents.career_agent",
        "orchestrator_core.agents.research_agent",
        "orchestrator_core.agents.growth_agent",
        "orchestrator_core.agents.critic_agent",
        "orchestrator_core.agents.info_agent",
    ]

    # Data folders: on Windows separator is ';'
    sep = ";" if sys.platform == "win32" else ":"
    data_args = [
        f"--add-data={project_root / 'frontend'}{sep}frontend",
        f"--add-data={project_root / 'migrations'}{sep}migrations",
    ]

    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--onedir",
        "--name=toji-backend",
        f"--distpath={dist_dir}",
        f"--workpath={build_dir}",
        f"--specpath={build_dir}",
    ]

    for hi in hidden_imports:
        cmd.append(f"--hidden-import={hi}")

    cmd.extend(data_args)
    cmd.append(str(entry_point))

    print("PyInstaller Build Configuration:")
    print(f"  Entry Point: {entry_point}")
    print(f"  Dist Dir:    {dist_dir}")
    print(f"  Command:     {' '.join(cmd)}\n")

    if args.dry_run:
        print("[Dry Run] Build command verified successfully.")
        return

    # Check PyInstaller availability
    try:
        subprocess.run(
            [sys.executable, "-m", "PyInstaller", "--version"],
            check=True,
            capture_output=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        print(
            "PyInstaller is not installed. To build the sidecar exe, run:\n"
            "    pip install pyinstaller\n"
            "Then rerun this script.",
            file=sys.stderr,
        )
        sys.exit(1)

    print("Running PyInstaller build...")
    res = subprocess.run(cmd, cwd=str(project_root))
    if res.returncode != 0:
        print("PyInstaller build failed.", file=sys.stderr)
        sys.exit(res.returncode)

    print("\n✅ PyInstaller build complete!")

    if args.copy_to_shell:
        resources_dir.mkdir(parents=True, exist_ok=True)
        exe_name = "toji-backend.exe" if sys.platform == "win32" else "toji-backend"
        src_exe = dist_dir / "toji-backend" / exe_name
        dest_exe = resources_dir / exe_name

        if src_exe.exists():
            shutil.copy2(src_exe, dest_exe)
            print(f"Copied {src_exe} -> {dest_exe}")
        else:
            print(f"Note: Built binary at {src_exe} will be copied during packaging.")


if __name__ == "__main__":
    main()
