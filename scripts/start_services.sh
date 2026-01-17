#!/bin/bash
# Start Local Lamps Services
# This script starts both the lamp control service and Matterbridge

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}Starting Local Lamps Services${NC}"
echo "================================"

# Check for configuration
CONFIG_FILE="$PROJECT_DIR/config/lamps.yaml"
if [ ! -f "$CONFIG_FILE" ]; then
    echo -e "${RED}Error: Configuration file not found${NC}"
    echo "Copy config/lamps.example.yaml to config/lamps.yaml and fill in your device keys."
    exit 1
fi

# Check uv
if ! command -v uv &> /dev/null; then
    echo -e "${RED}Error: uv is required (https://docs.astral.sh/uv/)${NC}"
    exit 1
fi

# Check Node.js
if ! command -v node &> /dev/null; then
    echo -e "${YELLOW}Warning: Node.js not found. Matterbridge will not start.${NC}"
    echo "Install Node.js 20 LTS for Google Home integration."
fi

# Start lamp service
echo -e "${GREEN}Starting Lamp Control Service...${NC}"
cd "$PROJECT_DIR/lamp-service"

# Install dependencies
uv sync

# Set config path
export LAMPS_CONFIG="$CONFIG_FILE"

# Start the service in the background
echo "Starting uvicorn on port 8000..."
uv run uvicorn src.main:app --host 0.0.0.0 --port 8000 &
LAMP_PID=$!

# Give it a moment to start
sleep 2

# Check if it started
if ! kill -0 $LAMP_PID 2>/dev/null; then
    echo -e "${RED}Error: Lamp service failed to start${NC}"
    exit 1
fi

echo -e "${GREEN}Lamp service started (PID: $LAMP_PID)${NC}"
echo "API available at: http://localhost:8000"
echo "API docs at: http://localhost:8000/docs"

# Check for Matterbridge
if command -v matterbridge &> /dev/null; then
    echo ""
    echo -e "${GREEN}Starting Matterbridge...${NC}"
    matterbridge &
    MB_PID=$!
    sleep 2

    if kill -0 $MB_PID 2>/dev/null; then
        echo -e "${GREEN}Matterbridge started (PID: $MB_PID)${NC}"
        echo "Web interface at: http://localhost:8283"
    else
        echo -e "${YELLOW}Matterbridge may have failed to start${NC}"
    fi
else
    echo ""
    echo -e "${YELLOW}Matterbridge not installed.${NC}"
    echo "Install with: npm install -g matterbridge matterbridge-webhooks"
fi

echo ""
echo "================================"
echo -e "${GREEN}Services started!${NC}"
echo ""
echo "To test the lamp service:"
echo "  curl http://localhost:8000/lamps"
echo ""
echo "Press Ctrl+C to stop all services"

# Wait for either process to exit
wait
