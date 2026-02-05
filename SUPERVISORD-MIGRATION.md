# Migration from s6-overlay to supervisord

## Overview

This document describes the migration of the can-inspection-simulation container from s6-overlay v3 to supervisord for process supervision.

## Rationale

The migration was performed to:

1. **Simplify maintenance** - supervisord is a more widely-used and well-documented process supervisor
2. **Improve accessibility** - More developers are familiar with supervisord compared to s6-overlay
3. **Standardization** - supervisord is the standard choice for Python-based applications and Docker containers
4. **Easier configuration** - supervisord uses a simple INI-style configuration format
5. **Better tooling** - supervisorctl provides intuitive commands for managing services

## Changes Made

### 1. Dockerfile Changes

**Removed:**
- s6-overlay v3 installation (ARG, ADD, and tar extraction commands)
- xz-utils package (only needed for s6-overlay archives)
- COPY of s6-rc.d/ directory
- ENTRYPOINT ["/init"] directive

**Added:**
- supervisor package installation
- Creation of /var/log/supervisor directory
- COPY of supervisord.conf to /etc/supervisor/conf.d/
- CMD ["/usr/bin/supervisord", "-c", "/etc/supervisor/conf.d/supervisord.conf"]

### 2. Service Configuration

All services previously defined in `s6-rc.d/` have been migrated to `/etc/supervisor/conf.d/supervisord.conf`:

| Service | Description | Priority | Auto-restart |
|---------|-------------|----------|--------------|
| xvfb | Virtual display server | 10 | Yes |
| gazebo | Gazebo simulation engine | 20 | Yes |
| unpause-sim | One-time command to unpause simulation | 30 | No |
| can-spawner | Spawns cans on conveyor | 40 | Yes |
| web-viewer | Flask web interface | 50 | Yes |
| viam-server | Viam RDK server (conditional) | 60 | Yes |

**Key Configuration Details:**

- **xvfb**: Runs on DISPLAY :1, provides virtual framebuffer for headless rendering
- **gazebo**: Depends on xvfb (enforced by priority order), includes all necessary environment variables
- **unpause-sim**: One-shot service that unpauses the simulation after startup (autorestart=false)
- **can-spawner**: Delayed start (10s) to ensure gazebo is ready
- **web-viewer**: Delayed start (10s) to ensure gazebo is ready
- **viam-server**: Conditional start based on /etc/viam.json existence, delayed start (10s)

### 3. Code Changes

**web_viewer.py:**
- Updated `restart_viam_server()` function to use `supervisorctl restart viam-server`
- Removed s6-svc command references (`/command/s6-svc -r /run/service/viam-server`)
- Maintained fallback mechanism using psutil for direct process termination

### 4. Documentation Updates

**CREDENTIALS-UPDATE.md:**
- Updated all references from s6-overlay to supervisord
- Changed command examples from `s6-svc` to `supervisorctl`
- Updated service status checking commands
- Changed log file paths and troubleshooting steps

### 5. Removed Files

- Deleted entire `s6-rc.d/` directory and all its contents:
  - Service run scripts (xvfb, gazebo, can-spawner, web-viewer, viam-server, unpause-sim)
  - Service dependencies files
  - Service type definitions
  - User bundle configuration

## Service Management

### supervisord vs s6-overlay Commands

| Task | s6-overlay (old) | supervisord (new) |
|------|------------------|-------------------|
| Restart service | `s6-svc -r /run/service/SERVICE` | `supervisorctl restart SERVICE` |
| Stop service | `s6-svc -d /run/service/SERVICE` | `supervisorctl stop SERVICE` |
| Start service | `s6-svc -u /run/service/SERVICE` | `supervisorctl start SERVICE` |
| List services | `s6-rc -a list` | `supervisorctl status` |
| Check service status | `s6-svstat /run/service/SERVICE` | `supervisorctl status SERVICE` |
| View logs | `cat /run/uncaught-logs` | `cat /var/log/supervisor/supervisord.log` |

### Common Operations

**Restart all services:**
```bash
docker exec <container-id> supervisorctl restart all
```

**Reload configuration:**
```bash
docker exec <container-id> supervisorctl reread
docker exec <container-id> supervisorctl update
```

**View service output:**
```bash
docker exec <container-id> supervisorctl tail -f SERVICE
```

**Interactive mode:**
```bash
docker exec -it <container-id> supervisorctl
```

## Environment Variables

All environment variables are preserved in the migration:

- **DISPLAY=:1** - Virtual display for Xvfb
- **PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION=python** - Required for gz-msgs compatibility
- **GZ_WORLD_NAME=cylinder_inspection** - Gazebo world name
- **GZ_STATION_NAME=Station 1** - Station identifier for UI
- **GZ_OVERVIEW_TOPIC=/overview_camera** - Overview camera topic
- **GZ_INSPECTION_TOPIC=/inspection_camera** - Inspection camera topic
- **GZ_SIM_RESOURCE_PATH=/opt/models** - Custom model path

## Startup Sequence

The priority system ensures proper service startup order:

1. **xvfb** (priority 10) - Starts first, provides virtual display
2. **gazebo** (priority 20) - Starts after xvfb is stable (startsecs=5)
3. **unpause-sim** (priority 30) - Runs once after gazebo starts
4. **can-spawner** (priority 40) - Starts spawning cans after delay
5. **web-viewer** (priority 50) - Web interface becomes available
6. **viam-server** (priority 60) - Viam server starts last (if configured)

The `startsecs` parameter ensures each service has time to initialize before the next one starts.

## Conditional Service Start

The viam-server service uses a bash conditional to only start if `/etc/viam.json` exists:

```bash
if [ -f /etc/viam.json ]; then sleep 10 && /usr/local/bin/viam-server -config /etc/viam.json; else sleep infinity; fi
```

This ensures the container runs successfully even without Viam credentials.

## Logging

All services are configured to log to stdout/stderr with:
- `stdout_logfile=/dev/stdout`
- `stdout_logfile_maxbytes=0` (no rotation)
- `stderr_logfile=/dev/stderr`
- `stderr_logfile_maxbytes=0` (no rotation)

This ensures logs are captured by Docker's logging system and accessible via `docker logs`.

## Testing

After migration, verify:

1. Container starts successfully: `docker run -d <image>`
2. All services are running: `docker exec <container-id> supervisorctl status`
3. Web viewer is accessible: `http://localhost:8081`
4. Camera streams are working
5. Viam server starts with config: Mount `/etc/viam.json` and verify service status
6. Configuration update works: Test via web UI at `/config`

## Backwards Compatibility

This is a breaking change for:
- Direct s6-svc command usage in scripts or documentation
- Custom s6 service definitions
- s6-overlay specific environment variables or features

Users should update any automation or scripts that interact with the container's process management.

## Future Considerations

Potential improvements:
- Add health checks to supervisord configuration
- Implement service restart limits to prevent infinite restart loops
- Consider adding email notifications for service failures
- Add support for custom supervisord.conf extensions via volume mounts

## References

- [supervisord documentation](http://supervisord.org/)
- [s6-overlay documentation](https://github.com/just-containers/s6-overlay)
- Original implementation: Task 17a (s6-overlay migration from entrypoint.sh)
- This migration: Supervisord migration from s6-overlay
