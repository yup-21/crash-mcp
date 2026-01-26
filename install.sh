#!/bin/bash
set -e

echo "============================================"
echo "  Crash MCP Server Installation"
echo "============================================"

# Define venv directory
VENV_DIR="venv"

# Check for python3
echo ""
echo "[1/5] Checking for python3..."
if ! command -v python3 &> /dev/null; then
    echo "Error: python3 could not be found."
    exit 1
fi
echo "  ✓ Python3 found: $(python3 --version)"

# Create virtual environment
echo ""
echo "[2/5] Creating virtual environment in $VENV_DIR..."
if ! python3 -m venv "$VENV_DIR" 2>/dev/null; then
    echo "Error: Failed to create virtual environment."
    echo "It seems 'python3-venv' is missing. Please install it:"
    echo "  sudo apt update && sudo apt install python3-venv"
    echo "Then run this script again."
    exit 1
fi
echo "  ✓ Virtual environment created"

# Activate venv
source "$VENV_DIR/bin/activate"

# Upgrade pip
echo ""
echo "[3/5] Upgrading pip..."
pip install --upgrade pip -q
echo "  ✓ pip upgraded"

# Install project
echo ""
echo "[4/5] Installing project in editable mode..."
pip install -e . -q
echo "  ✓ Project installed"

# Print usage instructions
echo ""
echo "[5/5] Installation Complete!"
echo ""
echo "============================================"
echo "  Next Steps"
echo "============================================"
echo ""
echo "1. Activate the virtual environment:"
echo "   source $VENV_DIR/bin/activate"
echo ""
echo "2. (Optional) Compile crash utility with compression support:"
echo "   # View required dependencies first"
echo "   compile-crash --deps"
echo ""
echo "   # Install dependencies (Ubuntu/Debian)"
echo "   sudo apt-get install git make gcc g++ bison flex \\"
echo "     zlib1g-dev libgmp-dev libmpfr-dev libncurses-dev \\"
echo "     liblzma-dev texinfo liblzo2-dev libsnappy-dev libzstd-dev"
echo ""
echo "   # Compile for x86_64 vmcore analysis"
echo "   compile-crash"
echo ""
echo "   # Compile for ARM64 vmcore analysis (run on x86_64)"
echo "   compile-crash --arch ARM64"
echo ""
echo "   # Compile with PyKdump support (built from source)"
echo "   compile-crash --pykdump-from-source"
echo ""
echo "3. Start the MCP server:"
echo "   # Stdio mode (default)"
echo "   crash-mcp"
echo ""
echo "   # SSE mode"
echo "   crash-mcp --transport sse --port 8000"
echo ""
echo "============================================"
