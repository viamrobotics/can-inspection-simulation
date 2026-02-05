# Task 15: Image Streaming Improvements

This document describes the improvements made to the image streaming functionality in `web_viewer.py`.

## Changes Made

### 1. Configurable Framerate (Part a)

**Location:** Lines 34-43 in `web_viewer.py`

The framerate is now configurable via the `FRAMERATE` environment variable:

```python
# Framerate configuration (defaults to 30 fps)
try:
    FRAMERATE = float(os.environ.get("FRAMERATE", "30"))
    if FRAMERATE <= 0:
        raise ValueError("FRAMERATE must be positive")
except (ValueError, TypeError) as e:
    print(f"Warning: Invalid FRAMERATE value, using default 30 fps. Error: {e}")
    FRAMERATE = 30

FRAME_DELAY = 1.0 / FRAMERATE
```

**Features:**
- Defaults to 30 fps if not set
- Validates that the framerate is a positive number
- Falls back to 30 fps with a warning if an invalid value is provided
- Automatically calculates frame delay (line 88: `time.sleep(FRAME_DELAY)`)

**Usage:**
```bash
# Set framerate to 15 fps
export FRAMERATE=15
python3 web_viewer.py

# Or in Docker
docker run -e FRAMERATE=15 ...
```

### 2. H.264 Video Stream Endpoint (Part b)

**Location:** Lines 91-167 in `web_viewer.py`

Added a new `/video/<camera>` endpoint that encodes frames to H.264 video using ffmpeg, providing better bandwidth efficiency than MJPEG.

**Implementation:**
```python
def generate_video_stream(camera_key):
    """
    Generator that encodes frames to H.264 video using ffmpeg.
    Provides better bandwidth efficiency than MJPEG.
    """
    # Uses ffmpeg with:
    # - libx264 codec for H.264 encoding
    # - ultrafast preset for low latency
    # - zerolatency tune for streaming
    # - mpegts format for HTTP streaming
```

**New Route (lines 290-301):**
```python
@app.route('/video/<camera>')
def video(camera):
    """
    H.264 video stream endpoint. Provides better bandwidth efficiency than MJPEG.
    Use with HTML5 video tag: <video src="/video/overview" autoplay muted></video>
    """
    if camera not in CAMERAS:
        return "Camera not found", 404
    return Response(
        generate_video_stream(camera),
        mimetype='video/mp2t'
    )
```

**Features:**
- Background thread continuously writes frames to ffmpeg stdin
- Respects the configured FRAMERATE
- Graceful error handling and cleanup
- Uses MPEG-TS container format which is suitable for HTTP streaming

**Usage:**
```html
<!-- In HTML -->
<video src="/video/overview" autoplay muted controls></video>

<!-- Or direct access -->
curl http://localhost:8081/video/overview > stream.ts
```

### 3. Dockerfile Updates

**Location:** Lines 43-48 in `Dockerfile`

Added ffmpeg installation:
```dockerfile
# Install ffmpeg for video streaming support
RUN apt-get update && apt-get install -y \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*
```

### 4. Improved Startup Messages

**Location:** Lines 318-337 in `web_viewer.py`

Added helpful output showing:
- Current framerate configuration
- Station name (if configured)
- Topic subscription status
- All available endpoints
- Valid camera names

**Example Output:**
```
Configuration:
  Framerate: 30 fps
  Station Name: (none)

Subscribing to camera topics...
  /overview_camera: OK
  /inspection_camera: OK

Starting web server on http://0.0.0.0:8081
Open this URL in your browser to view the cameras.

Available endpoints:
  /              - Web UI with MJPEG streams
  /stream/<cam>  - MJPEG stream (multipart/x-mixed-replace)
  /video/<cam>   - H.264 video stream (video/mp2t)
  /snapshot/<cam>- Single JPEG snapshot

Camera names: overview, inspection
```

## Available Endpoints Summary

| Endpoint | Method | Description | Format |
|----------|--------|-------------|--------|
| `/` | GET | Web UI with embedded MJPEG streams | HTML |
| `/stream/<camera>` | GET | MJPEG stream (existing) | multipart/x-mixed-replace |
| `/video/<camera>` | GET | H.264 video stream (NEW) | video/mp2t |
| `/snapshot/<camera>` | GET | Single JPEG snapshot | image/jpeg |

Valid camera names: `overview`, `inspection`

## Benefits

### Configurable Framerate
- Allows tuning for bandwidth/quality tradeoffs
- Can reduce to 15 fps for low-bandwidth scenarios
- Can increase to 60 fps for high-quality visualization
- Easy to configure per-deployment without code changes

### H.264 Video Stream
- **Better compression:** H.264 is much more efficient than MJPEG
- **Lower bandwidth:** Typically 3-5x less bandwidth than MJPEG for same quality
- **Better quality:** Inter-frame compression maintains visual quality
- **Standard format:** Works with HTML5 video players, VLC, ffplay, etc.
- **Still have MJPEG:** Original `/stream/<camera>` endpoint unchanged for compatibility

## Testing

To test the H.264 stream:

```bash
# Using ffplay (ffmpeg's player)
ffplay http://localhost:8081/video/overview

# Using VLC
vlc http://localhost:8081/video/overview

# In a browser with HTML5 video tag
<video src="http://localhost:8081/video/overview" autoplay muted controls></video>
```

To test configurable framerate:

```bash
# Test with different framerates
FRAMERATE=10 python3 web_viewer.py   # Slow: 10 fps
FRAMERATE=30 python3 web_viewer.py   # Default: 30 fps
FRAMERATE=60 python3 web_viewer.py   # Fast: 60 fps
```

## Deployment Notes

When deploying with Docker, pass the FRAMERATE environment variable:

```bash
docker run -e FRAMERATE=15 -e GZ_STATION_NAME="Station 1" \
  -p 8081:8081 ghcr.io/viamrobotics/can-inspection-simulation:latest
```

Or in cloud-init:

```yaml
environment:
  - FRAMERATE=15
  - GZ_STATION_NAME=Station 1
```
