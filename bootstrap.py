#!/usr/bin/env python3
"""Set up the complete toolchain inside the repository.

Downloads uv into .tools/uv, installs a managed Python into .tools/python
and creates .venv with all dependencies. Runs on Linux, Windows and macOS
with any Python >= 3.8 and the standard library only.

Usage: python bootstrap.py [--dev] [--clean] [--if-needed]
"""

import argparse
import hashlib
import io
import os
import platform
import shutil
import subprocess
import sys
import tarfile
import urllib.request
import zipfile
from pathlib import Path

UV_VERSION = "0.5.11"
PYTHON_VERSION = "3.12"

REPO_DIR = Path(__file__).resolve().parent
TOOLS_DIR = REPO_DIR / ".tools"
UV_DIR = TOOLS_DIR / "uv"
VENV_DIR = REPO_DIR / ".venv"

IS_WINDOWS = sys.platform == "win32"
EXE = ".exe" if IS_WINDOWS else ""
UV_BIN = UV_DIR / ("uv" + EXE)
VENV_PYTHON = VENV_DIR / ("Scripts/python.exe" if IS_WINDOWS else "bin/python")

STAMP = VENV_DIR / ".bootstrap-stamp"

RELEASE_URL = "https://github.com/astral-sh/uv/releases/download/{version}/{asset}"


def uv_asset() -> str:
    """Return the uv release asset name for the current platform."""
    machine = platform.machine().lower()
    arch = {
        "x86_64": "x86_64",
        "amd64": "x86_64",
        "aarch64": "aarch64",
        "arm64": "aarch64",
    }.get(machine)
    if arch is None:
        sys.exit("Unsupported architecture: " + machine)

    if sys.platform.startswith("linux"):
        return f"uv-{arch}-unknown-linux-gnu.tar.gz"
    if sys.platform == "darwin":
        return f"uv-{arch}-apple-darwin.tar.gz"
    if IS_WINDOWS:
        return f"uv-{arch}-pc-windows-msvc.zip"
    sys.exit("Unsupported platform: " + sys.platform)


def download(url: str) -> bytes:
    with urllib.request.urlopen(url, timeout=60) as response:
        return response.read()


def installed_uv_version():
    if not UV_BIN.exists():
        return None
    result = subprocess.run([str(UV_BIN), "--version"], capture_output=True, text=True, check=False)
    parts = result.stdout.split()
    return parts[1] if len(parts) > 1 else None


def install_uv() -> None:
    """Download the pinned uv release, verify its checksum and extract the binaries."""
    asset = uv_asset()
    url = RELEASE_URL.format(version=UV_VERSION, asset=asset)
    print("Downloading " + url)
    archive = download(url)

    expected = download(url + ".sha256").decode().split()[0].lower()
    actual = hashlib.sha256(archive).hexdigest()
    if actual != expected:
        sys.exit(f"Checksum mismatch for {asset}: expected {expected}, got {actual}")

    # Only the uv and uvx binaries are extracted, by basename, to avoid path traversal
    wanted = {"uv" + EXE, "uvx" + EXE}
    files = {}
    if asset.endswith(".zip"):
        with zipfile.ZipFile(io.BytesIO(archive)) as zf:
            for name in zf.namelist():
                base = name.rsplit("/", 1)[-1]
                if base in wanted:
                    files[base] = zf.read(name)
    else:
        with tarfile.open(fileobj=io.BytesIO(archive), mode="r:gz") as tf:
            for member in tf.getmembers():
                base = member.name.rsplit("/", 1)[-1]
                if member.isfile() and base in wanted:
                    files[base] = tf.extractfile(member).read()

    if "uv" + EXE not in files:
        sys.exit("uv binary not found in " + asset)

    UV_DIR.mkdir(parents=True, exist_ok=True)
    for base, data in files.items():
        target = UV_DIR / base
        target.write_bytes(data)
        target.chmod(0o755)


def stamp_value(dev: bool) -> str:
    """Fingerprint of everything the environment depends on."""
    digest = hashlib.sha256(f"{UV_VERSION}|{PYTHON_VERSION}|{dev}".encode())
    for name in ("requirements.txt", "requirements-dev.txt", "pyproject.toml"):
        path = REPO_DIR / name
        if path.is_file():
            digest.update(path.read_bytes())
    return digest.hexdigest()


def up_to_date(dev: bool) -> bool:
    try:
        return VENV_PYTHON.exists() and STAMP.read_text().strip() == stamp_value(dev)
    except OSError:
        return False


def run(*args) -> None:
    print("> " + " ".join(str(a) for a in args))
    # Relative entries in the requirements files are resolved against the repository
    subprocess.run([str(a) for a in args], check=True, cwd=REPO_DIR)


def main() -> None:
    parser = argparse.ArgumentParser(description="Set up the repository-local toolchain.")
    parser.add_argument("--dev", action="store_true", help="install development dependencies")
    parser.add_argument("--clean", action="store_true", help="remove .tools and .venv first")
    parser.add_argument("--if-needed", action="store_true", help="do nothing when the environment is up to date")
    args = parser.parse_args()

    if args.if_needed and not args.clean and up_to_date(args.dev):
        return

    if args.clean:
        print(f"Removing {TOOLS_DIR} and {VENV_DIR}")
        shutil.rmtree(TOOLS_DIR, ignore_errors=True)
        shutil.rmtree(VENV_DIR, ignore_errors=True)

    TOOLS_DIR.mkdir(exist_ok=True)

    # uv reads these from the environment of every subprocess
    os.environ["UV_PYTHON_INSTALL_DIR"] = str(TOOLS_DIR / "python")
    os.environ["UV_CACHE_DIR"] = str(TOOLS_DIR / "cache")
    os.environ["UV_PYTHON_PREFERENCE"] = "only-managed"

    if installed_uv_version() != UV_VERSION:
        install_uv()

    run(UV_BIN, "python", "install", PYTHON_VERSION)
    if not VENV_PYTHON.exists():
        run(UV_BIN, "venv", VENV_DIR, "--python", PYTHON_VERSION)

    requirements = REPO_DIR / ("requirements-dev.txt" if args.dev else "requirements.txt")
    run(UV_BIN, "pip", "install", "--python", VENV_PYTHON, "-r", requirements)
    STAMP.write_text(stamp_value(args.dev))

    activate = r".venv\Scripts\activate" if IS_WINDOWS else "source .venv/bin/activate"
    print()
    print("Done. Activate with: " + activate)


if __name__ == "__main__":
    main()
