#!/bin/bash
set -e

# =============================================================================
# Station 2 Entrypoint
# Runs the second inspection station with different camera topics and colors.
# =============================================================================

# Export protobuf compatibility setting
export PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION=python

# Station 2 configuration
export GZ_WORLD_NAME="cylinder_inspection_2"
export GZ_STATION_NAME="Station 2"
export GZ_OVERVIEW_TOPIC="/station_2_overview"
export GZ_INSPECTION_TOPIC="/station_2_camera"

# Start virtual display for headless rendering
echo "Starting Xvfb virtual display..."
Xvfb :1 -screen 0 1024x768x24 &
export DISPLAY=:1
sleep 2

echo "Starting Gazebo Sim (Station 2)..."
gz sim -s /opt/worlds/cylinder_inspection_2.sdf &
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
gz service -s /world/cylinder_inspection_2/control --reqtype gz.msgs.WorldControl --reptype gz.msgs.Boolean --timeout 2000 --req 'pause: false'
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
    /usr/local/bin/viam-server -config /etc/viam.json &
    VIAM_PID=$!
    echo "viam-server started with PID $VIAM_PID"
else
    echo ""
    echo "No /etc/viam.json found - viam-server not started"
    echo "To use viam-server, mount your config: -v /path/to/viam.json:/etc/viam.json"
fi

echo ""
echo "=========================================="
echo "Can Inspection Station 2 Running!"
echo "=========================================="
echo ""
echo "  Web Viewer:  http://localhost:8081"
echo ""
echo "  Camera topics:"
echo "    - /station_2_camera (inspection)"
echo "    - /station_2_overview"
echo ""
if [ -f /etc/viam.json ]; then
echo "  viam-server: running (use Viam app to configure)"
fi
echo ""
echo "=========================================="
echo ""

# Keep container running
wait $GZ_PID
