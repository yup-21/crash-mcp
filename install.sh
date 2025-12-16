#!/bin/bash
set -e

# Define venv directory
VENV_DIR="venv"

echo "Checking for python3..."
if ! command -v python3 &> /dev/null; then
    echo "Error: python3 could not be found."
    exit 1
fi

echo "Creating virtual environment in $VENV_DIR..."
# Try to create venv, catch error if python3-venv is missing
if ! python3 -m venv "$VENV_DIR" 2>/dev/null; then
    echo "Error: Failed to create virtual environment."
    echo "It seems 'python3-venv' is missing. Please install it:"
    echo "  sudo apt update && sudo apt install python3-venv"
    echo "Then run this script again."
    exit 1
fi

# Activate venv
source "$VENV_DIR/bin/activate"

echo "Upgrading pip..."
pip install --upgrade pip

echo "Installing project in editable mode..."
pip install -e .

echo "Done!"
echo "To use the server, activate the environment:"
echo "  source $VENV_DIR/bin/activate"
echo "  crash-mcp"
