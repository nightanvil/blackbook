#!/usr/bin/env bash
# Sets up the complete toolchain inside the repository (Linux, macOS).
# Usage: ./bootstrap.sh [--dev] [--clean]
set -euo pipefail

UV_VERSION="0.5.11"
PYTHON_VERSION="3.12"

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TOOLS_DIR="${REPO_DIR}/.tools"
VENV_DIR="${REPO_DIR}/.venv"

export UV_INSTALL_DIR="${TOOLS_DIR}/uv"
export UV_NO_MODIFY_PATH=1
export UV_PYTHON_INSTALL_DIR="${TOOLS_DIR}/python"
export UV_CACHE_DIR="${TOOLS_DIR}/cache"
export UV_PYTHON_PREFERENCE="only-managed"

UV_BIN="${UV_INSTALL_DIR}/uv"

dev=0
clean=0
for arg in "$@"; do
    case "${arg}" in
        --dev)   dev=1 ;;
        --clean) clean=1 ;;
        *) echo "Unknown argument: ${arg}" >&2; exit 1 ;;
    esac
done

if [[ ${clean} -eq 1 ]]; then
    echo "Removing ${TOOLS_DIR} and ${VENV_DIR}"
    rm -rf "${TOOLS_DIR}" "${VENV_DIR}"
fi

mkdir -p "${TOOLS_DIR}"

# uv
if [[ ! -x "${UV_BIN}" ]] || [[ "$("${UV_BIN}" --version | awk '{print $2}')" != "${UV_VERSION}" ]]; then
    echo "Installing uv ${UV_VERSION} into ${UV_INSTALL_DIR}"
    if command -v curl >/dev/null 2>&1; then
        curl -LsSf "https://astral.sh/uv/${UV_VERSION}/install.sh" | sh
    elif command -v wget >/dev/null 2>&1; then
        wget -qO- "https://astral.sh/uv/${UV_VERSION}/install.sh" | sh
    else
        echo "curl or wget is required" >&2
        exit 1
    fi
fi

# Python and virtual environment
"${UV_BIN}" python install "${PYTHON_VERSION}"
if [[ ! -x "${VENV_DIR}/bin/python" ]]; then
    "${UV_BIN}" venv "${VENV_DIR}" --python "${PYTHON_VERSION}"
fi

# Dependencies
requirements="${REPO_DIR}/requirements.txt"
if [[ ${dev} -eq 1 ]]; then
    requirements="${REPO_DIR}/requirements-dev.txt"
fi
"${UV_BIN}" pip install --python "${VENV_DIR}/bin/python" -r "${requirements}"

echo
echo "Done. Python: $("${VENV_DIR}/bin/python" --version)"
echo "Activate with: source .venv/bin/activate"
