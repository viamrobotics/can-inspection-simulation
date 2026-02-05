# Task 13 Implementation Summary

## Objective
Modify the `./can-inspection-simulation` submodule to allow users to replace Viam credentials dynamically without recreating the container.

## Implementation Details

### Part A: Process Supervisor Design

**Solution:** Replaced simple bash entrypoint with **s6-overlay v3**

**Why s6-overlay?**
- Industry-standard process supervisor for containers
- Automatically restarts crashed services
- Allows controlled restart of individual services via `s6-svc`
- Handles service dependencies elegantly
- Minimal overhead and resource usage

**Services Created:**
1. **xvfb** - Virtual display for headless rendering
2. **gazebo** - Main simulation (depends on xvfb)
3. **can-spawner** - Spawns cans on conveyor (depends on gazebo)
4. **web-viewer** - Flask web interface (depends on gazebo)
5. **viam-server** - Viam RDK server (depends on gazebo, optional)
6. **unpause-sim** - Oneshot service to unpause simulation after startup

**Service Definitions Location:** `/etc/s6-overlay/s6-rc.d/` inside the container

**Key Files:**
- `s6-rc.d/*/type` - Service type (longrun or oneshot)
- `s6-rc.d/*/run` - Service execution script
- `s6-rc.d/*/dependencies` - Service dependencies
- `s6-rc.d/user/` - Bundle to start all services

### Part B: Configuration Web Interface

**Added Route:** `http://localhost:8081/config`

**Features:**
- Display current `viam.json` configuration
- In-browser JSON editor with syntax highlighting
- Client-side JSON validation before submission
- Shows viam-server running status (Running/Stopped)
- Success/error flash messages
- Navigation back to camera viewer

**Frontend:**
- Dark theme matching existing UI
- Responsive design
- "Validate JSON" button for syntax checking
- Clear instructions and help text

**Backend (Flask):**
- `@app.route('/config')` - Display configuration page
- `@app.route('/config/update', methods=['POST'])` - Handle config updates
- `is_viam_server_running()` - Check process status using psutil
- `restart_viam_server()` - Restart service via s6 or kill signal

**Requirements:**
- `/etc/viam.json` must be mounted with `rw` (read-write) permissions
- Python package `psutil` added to Dockerfile

### Part C: Restart Mechanism

**Primary Method:** s6-overlay service control
```bash
/command/s6-svc -r /run/service/viam-server
```
- Clean restart via process supervisor
- Automatic monitoring and respawn if needed
- Graceful shutdown before restart

**Fallback Method:** Direct process signaling
1. Find viam-server process using psutil
2. Send `SIGTERM` for graceful shutdown
3. Wait 2 seconds for termination
4. Send `SIGKILL` if process still alive

**Signal Flow:**
```
Config Update → Validate JSON → Write to /etc/viam.json →
  Try s6-svc restart →
    If fails: SIGTERM → Wait 2s → SIGKILL (if needed)
```

## Changes Made

### Modified Files:
1. **Dockerfile**
   - Added s6-overlay v3 installation
   - Added psutil Python package
   - Changed ENTRYPOINT from `/entrypoint.sh` to `/init` (s6)
   - Copy s6-rc.d service definitions

2. **web_viewer.py**
   - Added Flask secret key for sessions
   - Added `/config` route with HTML template
   - Added `/config/update` POST endpoint
   - Added `is_viam_server_running()` function
   - Added `restart_viam_server()` function
   - Updated main page with "Configuration" button
   - Imported json, signal, psutil, flask helpers

3. **entrypoint.sh** & **entrypoint_station2.sh**
   - Kept for reference/compatibility
   - No longer used as entrypoint (s6 /init is now used)

### New Files:
1. **s6-rc.d/** - Complete service definition tree
   - 5 longrun services + 1 oneshot service
   - Proper dependencies configured
   - User bundle to start all services

2. **CREDENTIALS-UPDATE.md** - Full documentation
   - Architecture explanation
   - Usage instructions
   - Manual restart commands
   - Troubleshooting guide
   - Security considerations

3. **TASK13-SUMMARY.md** - This file

## Testing Recommendations

### 1. Build and Run Container
```bash
cd can-inspection-simulation
docker build -t can-inspection:task13 .

# Run with writable viam.json mount
docker run -d \
  -v $(pwd)/viam-test.json:/etc/viam.json:rw \
  -p 8081:8081 -p 8080:8080 -p 8443:8443 \
  --name can-test \
  can-inspection:task13
```

### 2. Verify Services Running
```bash
# Check all services
docker exec can-test s6-rc -a list

# Check viam-server status
docker exec can-test s6-svstat /run/service/viam-server
```

### 3. Test Configuration Update
1. Open `http://localhost:8081/config`
2. Modify the JSON configuration
3. Click "Validate JSON" - should show success
4. Click "Update and Restart"
5. Should see success message and redirect
6. Verify new config applied: `docker exec can-test cat /etc/viam.json`

### 4. Test Manual Restart
```bash
# Restart via s6
docker exec can-test s6-svc -r /run/service/viam-server

# Check logs
docker logs can-test | tail -20
```

### 5. Test Crash Recovery
```bash
# Kill viam-server process
docker exec can-test pkill viam-server

# Wait 2 seconds, then check - should be restarted
sleep 2
docker exec can-test s6-svstat /run/service/viam-server
```

## Security Considerations

**Current State:**
- No authentication on `/config` endpoint
- Flask secret key uses default in development
- Configuration page is publicly accessible

**Recommendations for Production:**
1. Add HTTP Basic Auth or session-based authentication
2. Set `FLASK_SECRET_KEY` environment variable with strong random key
3. Restrict port 8081 to localhost or trusted networks only
4. Consider adding API key validation for credential updates
5. Add audit logging for configuration changes
6. Implement rate limiting on update endpoint

## Deployment Notes

### Terraform Integration
The existing terraform configuration needs to ensure:
```yaml
# In cloud-init script
docker run -d \
  -v /etc/viam.json:/etc/viam.json:rw \  # Note: :rw for read-write
  --network host \
  ghcr.io/viamrobotics/can-inspection-simulation:latest
```

### Volume Mount Requirements
- **Must be read-write** (`:rw` suffix)
- Host file should exist before container starts
- Permissions should allow container user to write

### GitHub Actions
The existing workflow will automatically build and push the updated image to `ghcr.io/viamrobotics/can-inspection-simulation:main-<commit-sha>`

## Benefits

1. **No Container Restarts** - Update credentials without losing simulation state
2. **User-Friendly** - Web UI is more accessible than SSH/docker exec
3. **Robust** - s6-overlay ensures services always running
4. **Automatic Recovery** - Crashed services auto-restart
5. **Clean Separation** - Each service isolated and independently controllable
6. **Production Ready** - s6-overlay used by many production containers

## Known Limitations

1. **No Authentication** - Config page is public (address with firewall rules)
2. **No Backup** - Old configs not saved (consider implementing history)
3. **No Validation** - Only JSON syntax checked, not credential validity
4. **Terraform Updates** - Existing deployments need mount changed to `:rw`

## Future Enhancements

- Add authentication to configuration interface
- Implement configuration history/backup
- Add service log viewer in web UI
- Support file upload for viam.json
- Add API endpoint for programmatic updates
- Show more detailed service status (uptime, restarts, etc.)
- Add webhook notification on credential change

## Documentation

Full documentation available in:
- **CREDENTIALS-UPDATE.md** - Complete user guide
- **s6-rc.d/README.md** - Service architecture details (if created)
- **Inline comments** - In web_viewer.py and service scripts

## Conclusion

Task 13 is complete. The container now supports dynamic credential updates through a web interface, backed by a robust process supervisor (s6-overlay) that can cleanly restart the Viam server without affecting other services.
