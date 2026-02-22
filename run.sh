#!/bin/bash
set -e
cd "$(dirname "$0")"

PYTHON="/opt/homebrew/bin/python3.11"
PORT=8900

# Create venv if needed
if [ ! -d ".venv" ]; then
    echo "Creating virtual environment..."
    $PYTHON -m venv .venv
fi

source .venv/bin/activate

# Install deps if needed
if ! python -c "import fastapi, faster_whisper" 2>/dev/null; then
    echo "Installing dependencies..."
    pip install -r requirements.txt
fi

echo "Starting Percept on port $PORT..."
exec python -m uvicorn src.receiver:app --host 0.0.0.0 --port $PORT --log-level info
