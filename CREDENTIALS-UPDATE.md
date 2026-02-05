# Credentials Update Feature

## Overview

The can-inspection-simulation container now supports dynamic credential updates through a web interface. Users can update the `viam.json` configuration file and restart the Viam server without recreating the container.

## Architecture Changes

### 1. Process Supervision with s6-overlay

Replaced the simple bash `entrypoint.sh` with **s6-overlay v3**, a process supervisor that:
- Manages multiple long-running services
- Automatically restarts crashed services
- Allows controlled restart of individual services
- Handles service dependencies

### 2. Services Managed by s6-overlay

The following services are now supervised:

- **xvfb**: Virtual display for headless rendering
- **gazebo**: Gazebo simulation (depends on xvfb)
- **can-spawner**: Spawns cans on the conveyor (depends on gazebo)
- **web-viewer**: Flask web interface (depends on gazebo)
- **viam-server**: Viam RDK server (optional, depends on gazebo)

Service files are located in `/etc/s6-overlay/s6-rc.d/` inside the container.

### 3. Web Configuration Interface

The Flask web viewer (`web_viewer.py`) now includes a configuration page at `/config` that allows:

- Viewing the current `viam.json` configuration
- Editing the configuration in a text area
- Validating JSON syntax before saving
- Saving and automatically restarting the Viam server

## Usage

### Accessing the Configuration Page

1. Start the container with a writable mount for `/etc/viam.json`:
   ```bash
   docker run -d \
     -v /path/to/viam.json:/etc/viam.json:rw \
     -p 8081:8081 -p 8080:8080 -p 8443:8443 \
     ghcr.io/viamrobotics/can-inspection-simulation:latest
   ```

2. Open the web viewer: `http://localhost:8081`

3. Click the "⚙ Configuration" button in the top-right corner

4. Edit the `viam.json` configuration

5. Click "Update and Restart" to save and restart the Viam server

### Manual Restart via s6

If you need to manually restart the Viam server from inside the container:

```bash
# Restart the viam-server service
docker exec <container-id> s6-svc -r /run/service/viam-server

# Stop the service
docker exec <container-id> s6-svc -d /run/service/viam-server

# Start the service
docker exec <container-id> s6-svc -u /run/service/viam-server
```

### Check Service Status

```bash
# List all services
docker exec <container-id> s6-rc -a list

# Check if a specific service is up
docker exec <container-id> s6-svstat /run/service/viam-server
```

## Technical Details

### Restart Mechanism

When the configuration is updated:

1. Flask validates the JSON and writes it to `/etc/viam.json`
2. Flask calls `restart_viam_server()` which:
   - First tries to use `s6-svc -r` to restart the service cleanly
   - Falls back to sending `SIGTERM` to the viam-server process
   - If needed, sends `SIGKILL` after a timeout
3. s6-overlay automatically restarts the viam-server service with the new config

### Requirements

- The `/etc/viam.json` file must be mounted with read-write (`rw`) permissions
- The container needs the `psutil` Python package (already included)
- s6-overlay v3 is installed in the container

### Security Considerations

- The Flask app uses a secret key for session management (configurable via `FLASK_SECRET_KEY` env var)
- No authentication is implemented - the configuration page is publicly accessible
- In production, consider adding authentication or restricting access via firewall rules
- Only bind the web port (8081) to localhost if running on a public server

## Migration from Old Entrypoint

The old `entrypoint.sh` has been removed from the codebase (as of task 17a). The container now exclusively uses `/init` (from s6-overlay) as the entrypoint.

## Troubleshooting

### Service won't restart

Check s6 logs:
```bash
docker exec <container-id> cat /run/uncaught-logs
```

### Configuration page shows error

Check Flask logs:
```bash
docker logs <container-id> | grep -i error
```

### Viam server not starting

1. Verify `/etc/viam.json` exists and is valid JSON
2. Check service status: `docker exec <container-id> s6-svstat /run/service/viam-server`
3. Check viam-server logs in the container logs: `docker logs <container-id>`

### Mount is read-only

Ensure the volume mount includes `:rw`:
```bash
-v /path/to/viam.json:/etc/viam.json:rw
```

## Future Enhancements

Potential improvements:
- Add authentication to the configuration page
- Add API key validation when updating credentials
- Show service logs in the web UI
- Support for uploading configuration files
- Backup/restore configuration history
