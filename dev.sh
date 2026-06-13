#!/bin/bash

# Configuration
PROJECT_ROOT=$(pwd)
API_DIR="$PROJECT_ROOT/apps/api"
WEB_DIR="$PROJECT_ROOT/apps/web"
VENV_PATH="$PROJECT_ROOT/venv"

# Function to open a new terminal tab and run a command
# Adjust 'gnome-terminal' to your preferred emulator if necessary
open_terminal() {
    local title=$1
    local command=$2
    gnome-terminal --tab --title="$title" -- bash -c "$command; exec bash"
}

echo "Starting Design Suite development environment..."

# 1. Start Backend
echo "Launching Backend API in new tab..."
BACKEND_CMD="cd $API_DIR && source $VENV_PATH/bin/activate && uvicorn main:app --reload --port 5000"
open_terminal "Backend API" "$BACKEND_CMD"

# 2. Start Frontend
echo "Launching Frontend Dev Server in new tab..."
FRONTEND_CMD="cd $WEB_DIR && pnpm dev"
open_terminal "Frontend Web" "$FRONTEND_CMD"

echo "Servers launched. API: http://localhost:5000, Web: http://localhost:3000"

