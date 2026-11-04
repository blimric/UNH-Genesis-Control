#!/usr/bin/env bash
# One-time setup for the Genesis cool-down simulation: macOS, Linux, or
# Windows through WSL (Ubuntu).  Safe to run again: it only adds what is
# missing, and needs no administrator rights except, on Linux, for the GTK
# library Phoebus's windows use (it prints the command if that is missing).
#
#   bash tools/sim_setup.sh
#
# Then start a simulation with:  bash tools/sim.sh
set -euo pipefail
cd "$(dirname "$0")/.."
REPO="$(pwd)"
VENV="${GENESIS_SIM_VENV:-$HOME/.venvs/genesis-sim}"
PYTHON_VERSION=3.13                      # environment.yml
PHOEBUS_VERSION=5.0.5
PHOEBUS_DIR="$HOME/phoebus"

case "$(uname -s)" in
    Darwin) OS=mac;   [ "$(uname -m)" = arm64 ] && ASSET=mac-aarch64 || ASSET=mac ;;
    *)      OS=linux; ASSET=linux ;;
esac
case "$(uname -m)" in arm64|aarch64) ARCH=aarch64 ;; *) ARCH=x64 ;; esac

for tool in curl git tar; do
    command -v "$tool" >/dev/null || { echo "Please install $tool first."; exit 1; }
done
if [ "$OS" = linux ] && ! { ldconfig -p 2>/dev/null || /sbin/ldconfig -p 2>/dev/null; } | grep -q "libgtk-3.so"; then
    echo "Phoebus's windows need GTK 3.  Please run, then run this setup again:"
    echo "  sudo apt update && sudo apt install -y libgtk-3-0"
    exit 1
fi

echo "== Python $PYTHON_VERSION environment: $VENV"
if ! command -v uv >/dev/null && [ ! -x "$HOME/.local/bin/uv" ]; then
    curl -LsSf https://astral.sh/uv/install.sh | sh >/dev/null
fi
UV="$(command -v uv || echo "$HOME/.local/bin/uv")"
[ -x "$VENV/bin/python" ] || "$UV" venv -q --python "$PYTHON_VERSION" "$VENV"
"$UV" pip install -q --python "$VENV/bin/python" -r requirements-dev.txt

echo "== Java 21 (Phoebus runs on it)"
if ! command -v java >/dev/null && [ ! -x "$PHOEBUS_DIR/jre/bin/java" ]; then
    mkdir -p "$PHOEBUS_DIR/jre"
    curl -fL "https://api.adoptium.net/v3/binary/latest/21/ga/$OS/$ARCH/jre/hotspot/normal/eclipse" \
        -o "$PHOEBUS_DIR/jre.tar.gz"
    tar -xzf "$PHOEBUS_DIR/jre.tar.gz" -C "$PHOEBUS_DIR/jre" --strip-components=1 && rm -f "$PHOEBUS_DIR/jre.tar.gz"
    # macOS runtimes keep their binaries under Contents/Home
    [ -x "$PHOEBUS_DIR/jre/Contents/Home/bin/java" ] && ln -sfn Contents/Home/bin "$PHOEBUS_DIR/jre/bin"
fi

echo "== Phoebus $PHOEBUS_VERSION (the operator screens): $PHOEBUS_DIR"
if ! ls "$PHOEBUS_DIR"/product-*/product-*.jar >/dev/null 2>&1; then
    mkdir -p "$PHOEBUS_DIR"
    url="https://github.com/ControlSystemStudio/phoebus/releases/download/v$PHOEBUS_VERSION/phoebus-$PHOEBUS_VERSION-$ASSET.tar.gz"
    echo "   downloading (~300 MB)"
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
