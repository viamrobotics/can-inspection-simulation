# s6-overlay Service Architecture

This directory contains service definitions for s6-overlay v3, which manages all processes in the container.

## Service Dependency Tree

```
user (bundle)
├── xvfb (longrun)
│   └── Virtual X display server
│
├── gazebo (longrun)
│   ├── Depends on: xvfb
│   └── Gazebo Harmonic simulation
│
├── unpause-sim (oneshot)
│   ├── Depends on: gazebo
│   └── Unpauses simulation after startup
│
├── can-spawner (longrun)
│   ├── Depends on: gazebo
│   └── Spawns cans on conveyor belt
│
├── web-viewer (longrun)
│   ├── Depends on: gazebo
│   └── Flask web interface on port 8081
│
└── viam-server (longrun)
    ├── Depends on: gazebo
    └── Viam RDK server (optional, requires /etc/viam.json)
```

## Service Types

### longrun
Services that run continuously and are automatically restarted if they crash.
- Location: `<service>/run` (executable script)

### oneshot
Services that run once during startup.
- Location: `<service>/up` (executable script)

### bundle
Collections of other services.
- Location: `<service>/contents.d/` (directory with symlink-like files)

## Service Control

### View all services
```bash
s6-rc -a list
```

### Check service status
```bash
s6-svstat /run/service/<service-name>
```

### Restart a service
```bash
s6-svc -r /run/service/<service-name>
```

### Stop a service
```bash
s6-svc -d /run/service/<service-name>
```

### Start a service
```bash
s6-svc -u /run/service/<service-name>
```

### View service logs
Services write to stdout/stderr, which s6-overlay captures. View with:
```bash
docker logs <container-id>
```

## Service Details

### xvfb
- **Purpose:** Provides virtual display for Gazebo's OpenGL rendering
- **Command:** `Xvfb :1 -screen 0 1024x768x24`
- **Environment:** Sets `DISPLAY=:1` for dependent services

### gazebo
- **Purpose:** Runs Gazebo Harmonic simulation
- **Command:** `gz sim -s /opt/worlds/cylinder_inspection.sdf`
- **Startup delay:** 2 seconds after xvfb starts
- **World file:** `/opt/worlds/cylinder_inspection.sdf`

### unpause-sim
- **Purpose:** Unpauses the simulation after Gazebo initializes
- **Command:** `gz service -s /world/cylinder_inspection/control ...`
- **Startup delay:** 10 seconds after gazebo starts
- **Type:** Oneshot (runs once)

### can-spawner
- **Purpose:** Continuously spawns cans on the conveyor belt
- **Command:** `python3 /opt/can_spawner.py`
- **Startup delay:** 10 seconds after gazebo starts

### web-viewer
- **Purpose:** Flask web UI for camera streams and configuration
- **Command:** `python3 /opt/web_viewer.py`
- **Port:** 8081
- **Startup delay:** 10 seconds after gazebo starts
- **Routes:**
  - `/` - Camera viewer
  - `/config` - Viam configuration editor
  - `/stream/<camera>` - MJPEG streams
  - `/video/<camera>` - H.264 video streams

### viam-server
- **Purpose:** Viam RDK server for robot control
- **Command:** `/usr/local/bin/viam-server -config /etc/viam.json`
- **Condition:** Only runs if `/etc/viam.json` exists
- **Startup delay:** 10 seconds after gazebo starts
- **Ports:** 8080 (web), 8443 (gRPC)

## Modifying Services

### To change a service:
1. Edit the appropriate file in `s6-rc.d/<service-name>/`
2. Rebuild the Docker image
3. Restart the container

### To add a new service:
1. Create directory: `s6-rc.d/<service-name>/`
2. Create `type` file: `longrun` or `oneshot`
3. Create `run` or `up` file (executable)
4. Add dependencies in `dependencies` file (optional)
5. Add to bundle: `touch s6-rc.d/user/contents.d/<service-name>`
6. Rebuild the Docker image

## Troubleshooting

### Service won't start
Check s6 logs:
```bash
cat /run/uncaught-logs
```

### Service keeps restarting
Check service output in container logs:
```bash
docker logs <container-id> | grep <service-name>
```

### Manual service restart not working
Ensure you're using the correct path:
```bash
# Correct
s6-svc -r /run/service/viam-server

# Incorrect (won't work)
s6-svc -r /etc/s6-overlay/s6-rc.d/viam-server
```

### Want to disable a service
Remove it from the user bundle:
```bash
rm s6-rc.d/user/contents.d/<service-name>
```
Then rebuild the image.

## Environment Variables

Services inherit environment variables from:
1. Dockerfile `ENV` statements
2. `docker run -e KEY=VALUE`
3. Inline exports in service `run` scripts

Currently used:
- `DISPLAY` - Set to `:1` by xvfb dependency
- `PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION` - Set to `python`
- `GZ_WORLD_NAME` - Gazebo world name
- `GZ_STATION_NAME` - Display name for station
- `GZ_OVERVIEW_TOPIC` - Overview camera topic
- `GZ_INSPECTION_TOPIC` - Inspection camera topic
- `FRAMERATE` - Video stream framerate (default: 30)
- `FLASK_SECRET_KEY` - Flask session secret (default: dev key)

## References

- s6-overlay documentation: https://github.com/just-containers/s6-overlay
- s6 service command reference: https://skarnet.org/software/s6/
