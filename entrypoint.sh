#!/bin/bash
set -e

# =============================================================================
# Station 1 Entrypoint (default)
# Runs the primary inspection station.
# =============================================================================

# Export protobuf compatibility setting
export PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION=python

# Station 1 configuration (defaults, but explicit for clarity)
export GZ_WORLD_NAME="cylinder_inspection"
export GZ_STATION_NAME="Station 1"
export GZ_OVERVIEW_TOPIC="/overview_camera"
export GZ_INSPECTION_TOPIC="/inspection_camera"

# Start virtual display for headless rendering
echo "Starting Xvfb virtual display..."
Xvfb :1 -screen 0 1024x768x24 &
export DISPLAY=:1
sleep 2

echo "Starting Gazebo Sim with rendering..."
gz sim -s /opt/worlds/cylinder_inspection.sdf &
GZ_PID=$!

# Wait for Gazebo to initialize
echo "Waiting for Gazebo to initialize..."
sleep 10

echo ""
echo "Checking Gazebo topics..."
gz topic -l

# Unpause simulation
echo ""
echo "Unpausing simulation..."
gz service -s /world/cylinder_inspection/control --reqtype gz.msgs.WorldControl --reptype gz.msgs.Boolean --timeout 2000 --req 'pause: false'
sleep 1

# Start can spawner to spawn cans on the conveyor
echo ""
echo "Starting can spawner..."
python3 /opt/can_spawner.py &
SPAWNER_PID=$!

# Start web viewer (always runs for camera visualization)
echo ""
echo "Starting web viewer..."
python3 /opt/web_viewer.py &
VIEWER_PID=$!

# Start viam-server if config exists
if [ -f /etc/viam.json ]; then
    echo ""
    echo "Starting viam-server..."
    /usr/local/bin/viam-server.AppImage --appimage-extract-and-run -config /etc/viam.json &
    VIAM_PID=$!
    echo "viam-server started with PID $VIAM_PID"
else
    echo ""
    echo "No /etc/viam.json found - viam-server not started"
    echo "To use viam-server, mount your config: -v /path/to/viam.json:/etc/viam.json"
fi

echo ""
echo "=========================================="
echo "Can Inspection Station 1 Running!"
echo "=========================================="
echo ""
echo "  Web Viewer:  http://localhost:8081"
echo ""
echo "  Camera topics:"
echo "    - /inspection_camera (inspection)"
echo "    - /overview_camera"
echo ""
if [ -f /etc/viam.json ]; then
echo "  viam-server: running (use Viam app to configure)"
fi
echo ""
echo "=========================================="
echo ""

# Keep container running
wait $GZ_PID
