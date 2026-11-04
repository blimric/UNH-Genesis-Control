#!/usr/bin/env bash
# One-time setup for the Genesis cool-down simulation: macOS, Linux, or
# Windows through WSL (Ubuntu).  Safe to run again: it only adds what is missing.
#
#   bash tools/sim_setup.sh
#
# Then start a simulation with:  bash tools/sim.sh
set -euo pipefail
cd "$(dirname "$0")/.."
REPO="$(pwd)"
VENV="${GENESIS_SIM_VENV:-$HOME/.venvs/genesis-sim}"
PHOEBUS_VERSION=5.0.5
PHOEBUS_DIR="$HOME/phoebus"

case "$(uname -s)" in
    Darwin)
        OS=mac
        [ "$(uname -m)" = arm64 ] && ASSET="mac-aarch64" || ASSET="mac"
        INSTALL="brew install python git && brew install --cask temurin@21" ;;
    *)
        OS=linux
        ASSET="linux"
        INSTALL="sudo apt update && sudo apt install -y python3 python3-venv git curl openjdk-21-jre libgtk-3-0" ;;
esac

missing=""
for tool in python3 java curl git; do
    command -v "$tool" >/dev/null || missing="$missing $tool"
done
if [ -n "$missing" ]; then
    echo "Missing:$missing.  Please install them first:"
    echo "  $INSTALL"
    exit 1
fi

echo "== Python environment: $VENV"
[ -x "$VENV/bin/python" ] || python3 -m venv "$VENV"
"$VENV/bin/pip" install -q --upgrade pip
"$VENV/bin/pip" install -q -r requirements-dev.txt

echo "== Phoebus $PHOEBUS_VERSION (the operator screens): $PHOEBUS_DIR"
if ! ls "$PHOEBUS_DIR"/product-*/product-*.jar >/dev/null 2>&1; then
    mkdir -p "$PHOEBUS_DIR"
    url="https://github.com/ControlSystemStudio/phoebus/releases/download/v$PHOEBUS_VERSION/phoebus-$PHOEBUS_VERSION-$ASSET.tar.gz"
    echo "   downloading $url (~300 MB)"
    if curl -fL "$url" -o "$PHOEBUS_DIR/phoebus.tar.gz"; then
        tar -xzf "$PHOEBUS_DIR/phoebus.tar.gz" -C "$PHOEBUS_DIR" && rm -f "$PHOEBUS_DIR/phoebus.tar.gz"
    else
        echo "Could not download Phoebus.  Get phoebus-$PHOEBUS_VERSION-$ASSET.tar.gz from"
        echo "  https://github.com/ControlSystemStudio/phoebus/releases"
        echo "and unpack it into $PHOEBUS_DIR (so that $PHOEBUS_DIR/product-*/product-*.jar exists)."
        exit 1
    fi
fi

echo "== Spin-1 polarization model (optional): $(dirname "$REPO")/Spin-1-Rates-Fit"
if [ ! -d "$(dirname "$REPO")/Spin-1-Rates-Fit" ]; then
    GIT_TERMINAL_PROMPT=0 git clone -q https://github.com/ellie-long/Spin-1-Rates-Fit "$(dirname "$REPO")/Spin-1-Rates-Fit" 2>/dev/null \
        || echo "   (not available: the simulation uses its simpler polarization model)"
fi

echo "== Checking this computer ($OS)"
"$VENV/bin/python" -m cooldown_sim guard || echo "   (a simulation or Genesis is running here now; stop it before starting another)"
echo
echo "Setup done.  Start the simulation with:  bash tools/sim.sh"
