# Local vs Cloud Build Modes

This Docker image supports two build modes:

## Cloud Mode (GPU-accelerated)
- **Base Image**: `nvidia/opengl:1.2-glvnd-runtime-ubuntu22.04`
- **Rendering**: EGL headless rendering with GPU acceleration
- **Shadows**: Enabled for better visual quality
- **Platform**: `linux/amd64` only (NVIDIA GPU required)
- **Use Case**: Production deployments on GCP with GPU instances

### Image Tags
- `ghcr.io/viamrobotics/can-inspection-simulation:latest`
- `ghcr.io/viamrobotics/can-inspection-simulation:main-<sha>`

## Local Mode (CPU-only)
- **Base Image**: `ubuntu:22.04`
- **Rendering**: xvfb virtual framebuffer (CPU-based)
- **Shadows**: Disabled for better CPU performance
- **Platform**: `linux/amd64`, `linux/arm64` (multi-arch)
- **Use Case**: Local development on Linux and Mac laptops via Docker

### Image Tags
- `ghcr.io/viamrobotics/can-inspection-simulation:latest-local`
- `ghcr.io/viamrobotics/can-inspection-simulation:main-<sha>-local`

## Building Locally

### Local mode (CPU) - Default:
```bash
# Local mode is the default, no build arg needed
docker build -t can-inspection:local .

# Or explicitly:
docker build --build-arg BUILD_MODE=local -t can-inspection:local .
```

### Cloud mode (GPU):
```bash
docker build --build-arg BUILD_MODE=cloud -t can-inspection:cloud .
```

### Multi-arch local build:
```bash
docker buildx build --platform linux/amd64,linux/arm64 \
  --build-arg BUILD_MODE=local -t can-inspection:local .
```

## Running

### Cloud mode:
```bash
docker run --gpus all -p 8080:8080 -p 8081:8081 -p 8443:8443 \
  ghcr.io/viamrobotics/can-inspection-simulation:latest
```

### Local mode:
```bash
docker run -p 8080:8080 -p 8081:8081 -p 8443:8443 \
  ghcr.io/viamrobotics/can-inspection-simulation:latest-local
```

## How It Works

The `BUILD_MODE` arg controls:
1. **Base image selection**: Uses Docker multi-stage build to select `ubuntu:22.04` (local) or `nvidia/opengl:1.2-glvnd-runtime-ubuntu22.04` (cloud)
2. **Package installation**: Installs xvfb for local, EGL libraries for cloud
3. **Runtime configuration**: Sets `LOCAL_MODE` env var (`local` or `cloud`) for supervisord
4. **Gazebo command**: Local uses xvfb + standard rendering, cloud uses `--headless-rendering` with NVIDIA env vars
5. **Shadow configuration**: Startup script disables shadows in world files for local mode

## GitHub Actions

The workflow builds both versions:
- **Cloud job**: Builds amd64 cloud image on every workflow dispatch
- **Local job**: Builds multi-arch (amd64 + arm64) local image on every workflow dispatch

Both jobs run in parallel and use separate GitHub Actions caches.
