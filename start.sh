#!/usr/bin/env bash
# Start blackbook on Linux and macOS. The first start sets everything up inside this folder.
set -u
cd "$(dirname "$0")" || exit 1

fail() {
    echo
    echo "blackbook could not start: $1"
    echo "Press Enter to close this window."
    read -r _
    exit 1
}

if [ ! -x .venv/bin/blackbook ]; then
    echo "First start: setting up blackbook inside this folder. This takes a few minutes and needs internet."
fi

if [ -x .venv/bin/python ]; then
    .venv/bin/python bootstrap.py --if-needed || fail "the setup failed, see the messages above."
elif command -v python3 >/dev/null 2>&1 && python3 -c "import sys; sys.exit(sys.version_info < (3, 8))" 2>/dev/null; then
    python3 bootstrap.py --if-needed || fail "the setup failed, see the messages above."
else
    # No usable Python on this computer: fetch uv, which brings its own Python, into .tools
    echo "Python not found, downloading a private copy into this folder ..."
    UV_VERSION=0.5.11
    case "$(uname -s)-$(uname -m)" in
        Linux-x86_64) asset=uv-x86_64-unknown-linux-gnu.tar.gz ;;
        Linux-aarch64 | Linux-arm64) asset=uv-aarch64-unknown-linux-gnu.tar.gz ;;
        Darwin-x86_64) asset=uv-x86_64-apple-darwin.tar.gz ;;
        Darwin-arm64) asset=uv-aarch64-apple-darwin.tar.gz ;;
        *) fail "this system is not supported: $(uname -s) $(uname -m)" ;;
    esac
    url="https://github.com/astral-sh/uv/releases/download/$UV_VERSION/$asset"
    mkdir -p .tools/uv
    if command -v curl >/dev/null 2>&1; then
        curl -fsSL "$url" -o .tools/uv.tar.gz || fail "download of $url failed."
    elif command -v wget >/dev/null 2>&1; then
        wget -q "$url" -O .tools/uv.tar.gz || fail "download of $url failed."
    else
        fail "neither curl nor wget is installed. Install Python 3 instead (see README)."
    fi
    tar -xzf .tools/uv.tar.gz -C .tools/uv --strip-components=1 || fail "could not unpack uv."
    rm -f .tools/uv.tar.gz
    export UV_PYTHON_INSTALL_DIR="$PWD/.tools/python" UV_CACHE_DIR="$PWD/.tools/cache" UV_PYTHON_PREFERENCE=only-managed
    .tools/uv/uv run --no-project --python 3.12 bootstrap.py --if-needed || fail "the setup failed, see the messages above."
fi

# git is only needed for the backup; offer to install it, but start in any case
if [ "$(uname -s)" = "Darwin" ]; then
    if ! xcode-select -p >/dev/null 2>&1; then
        echo
        echo "git is missing, the backup needs it. A window from Apple opens: click Install."
        echo "blackbook starts now anyway. After the installation, close blackbook and start it again."
        xcode-select --install >/dev/null 2>&1
    fi
elif ! command -v git >/dev/null 2>&1; then
    if command -v apt-get >/dev/null 2>&1; then install="sudo apt-get install -y git"
    elif command -v dnf >/dev/null 2>&1; then install="sudo dnf install -y git"
    elif command -v pacman >/dev/null 2>&1; then install="sudo pacman -S --noconfirm git"
    elif command -v zypper >/dev/null 2>&1; then install="sudo zypper install -y git"
    else install=""
    fi
    echo
    echo "git is missing. blackbook works without it, but cannot make backups of your card."
    if [ -n "$install" ] && [ -t 0 ]; then
        echo "It can be installed now with: $install"
        printf "Install git now? Your password is asked, nothing is shown while you type it. [y/N] "
        read -r answer
        case "$answer" in
            y | Y | yes | j | J | ja) $install || echo "The installation of git failed, blackbook starts without backup." ;;
            *) echo "Skipped. blackbook starts without backup." ;;
        esac
    else
        echo "Install the package 'git' with your package manager, then start blackbook again."
    fi
    echo
fi

.venv/bin/blackbook "$@" || fail "see the messages above."
