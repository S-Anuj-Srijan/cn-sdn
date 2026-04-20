#!/bin/bash

# Configuration
SESSION="sdn_demo"
PROJECT_DIR="$HOME/cn-sdn"

# Clean up any existing Mininet/OpenFlow states
sudo mn -c

# Kill existing tmux session if it exists
tmux kill-session -t "$SESSION" 2>/dev/null

# Ensure we are in the project directory
cd "$PROJECT_DIR"

# Start a new tmux session and run Ryu in the first pane
tmux new-session -d -s "$SESSION" 'ryu-manager --observe-links path_tracer.py; exec bash'

# Split the window horizontally and run Mininet in the second pane
# We use sleep 3 to give Ryu time to initialize before Mininet starts
tmux split-window -h 'sleep 3 && sudo mn --custom topo.py --topo pathtopo --mac --switch ovsk --controller remote; exec bash'

# Attach to the session
tmux attach-session -t "$SESSION"
