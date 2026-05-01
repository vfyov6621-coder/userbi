#!/bin/bash
cd "$(dirname "$0")"

# Check Python3
if ! command -v python3 &>/dev/null; then
    echo "[ERROR] python3 not found!"
    exit 1
fi

# Check .env
if [ ! -f .env ]; then
    echo "[!] .env not found. Creating from template..."
    if [ -f .env.example ]; then
        cp .env.example .env
        echo "[!] Edit .env and set API_ID, API_HASH, PHONE"
        ${EDITOR:-nano} .env
        echo "[!] Run start.sh again after editing."
        exit 0
    else
        echo "[ERROR] .env.example not found."
        exit 1
    fi
fi

# Create folders
mkdir -p scripts backups

# Install deps
echo "[1/2] Checking dependencies..."
python3 -m pip install -r requirements.txt -q 2>/dev/null

# Start
echo "[2/2] Starting userbot..."
echo ""
echo "========================================"
echo "  Web panel: http://localhost:8080"
echo "  Press Ctrl+C to stop"
echo "========================================"
echo ""

python3 main.py
