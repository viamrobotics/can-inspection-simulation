#!/usr/bin/env python3
"""
Web viewer for Gazebo cameras.
Serves MJPEG streams for camera topics.

Camera topics can be configured via environment variables:
  GZ_OVERVIEW_TOPIC  - defaults to /overview_camera
  GZ_INSPECTION_TOPIC - defaults to /inspection_camera
  GZ_STATION_NAME - optional station name for display (e.g., "Station 2")
  FRAMERATE - stream framerate in fps (defaults to 30)
"""

import io
import os
import time
import threading
import subprocess
import json
import signal
from flask import Flask, Response, request, render_template, redirect, url_for, flash, jsonify
import psutil

from gz.transport13 import Node
from gz.msgs10.image_pb2 import Image as GzImage
from PIL import Image

app = Flask(__name__)
app.secret_key = os.environ.get('FLASK_SECRET_KEY', 'dev-secret-key-change-in-production')

# Path to viam.json config file
VIAM_CONFIG_PATH = '/etc/viam.json'

# =============================================================================
# CAMERA CONFIGURATION
# Topics can be overridden via environment variables.
# =============================================================================
STATION_NAME = os.environ.get("GZ_STATION_NAME", "")
OVERVIEW_TOPIC = os.environ.get("GZ_OVERVIEW_TOPIC", "/overview_camera")
INSPECTION_TOPIC = os.environ.get("GZ_INSPECTION_TOPIC", "/inspection_camera")

# Framerate configuration (defaults to 30 fps)
try:
    FRAMERATE = float(os.environ.get("FRAMERATE", "30"))
    if FRAMERATE <= 0:
        raise ValueError("FRAMERATE must be positive")
except (ValueError, TypeError) as e:
    print(f"Warning: Invalid FRAMERATE value, using default 30 fps. Error: {e}")
    FRAMERATE = 30

FRAME_DELAY = 1.0 / FRAMERATE

CAMERAS = {
    "overview": {
        "topic": OVERVIEW_TOPIC,
        "label": "Overview Camera",
        "description": "Elevated view of the entire work cell"
    },
    "inspection": {
        "topic": INSPECTION_TOPIC,
        "label": "Inspection Camera",
        "description": "Overhead view for defect detection (640x480)"
    },
}

# Runtime state for each camera (populated at startup)
camera_state = {}


def make_callback(camera_key):
    """Create a callback for a camera topic."""
    def callback(msg: GzImage):
        try:
            img = Image.frombytes("RGB", (msg.width, msg.height), msg.data)
            buffer = io.BytesIO()
            img.save(buffer, format="JPEG", quality=80)
            jpeg_bytes = buffer.getvalue()

            with camera_state[camera_key]["lock"]:
                camera_state[camera_key]["frame"] = jpeg_bytes
        except Exception as e:
            print(f"Error processing {camera_key} frame: {e}")
    return callback


def generate_stream(camera_key):
    """Generator that yields MJPEG frames."""
    while True:
        with camera_state[camera_key]["lock"]:
            frame = camera_state[camera_key]["frame"]

        if frame is not None:
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')

        time.sleep(FRAME_DELAY)


def generate_video_stream(camera_key):
    """
    Generator that encodes frames to H.264 video using ffmpeg.
    Provides better bandwidth efficiency than MJPEG.
    """
    # Get first frame to determine dimensions
    while camera_state[camera_key]["frame"] is None:
        time.sleep(0.1)

    with camera_state[camera_key]["lock"]:
        first_frame = camera_state[camera_key]["frame"]

    img = Image.open(io.BytesIO(first_frame))
    width, height = img.size

    # Start ffmpeg process to encode to H.264
    # Using -f rawvideo for input, outputting to mpegts for streaming
    ffmpeg_cmd = [
        'ffmpeg',
        '-f', 'rawvideo',
        '-pix_fmt', 'rgb24',
        '-s', f'{width}x{height}',
        '-r', str(FRAMERATE),
        '-i', '-',  # stdin
        '-c:v', 'libx264',
        '-preset', 'ultrafast',
        '-tune', 'zerolatency',
        '-f', 'mpegts',
        '-'  # stdout
    ]

    try:
        process = subprocess.Popen(
            ffmpeg_cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            bufsize=10**8
        )

        def write_frames():
            """Background thread to write frames to ffmpeg."""
            last_time = time.time()
            while True:
                try:
                    current_time = time.time()
                    elapsed = current_time - last_time

                    # Maintain target framerate
                    if elapsed < FRAME_DELAY:
                        time.sleep(FRAME_DELAY - elapsed)

                    with camera_state[camera_key]["lock"]:
                        frame = camera_state[camera_key]["frame"]

                    if frame is not None:
                        img = Image.open(io.BytesIO(frame))
                        rgb_data = img.tobytes()
                        process.stdin.write(rgb_data)
                        process.stdin.flush()

                    last_time = time.time()
                except (BrokenPipeError, IOError):
                    break
                except Exception as e:
                    print(f"Error writing frame to ffmpeg: {e}")
                    break

        writer_thread = threading.Thread(target=write_frames, daemon=True)
        writer_thread.start()

        # Read and yield encoded video chunks
        while True:
            chunk = process.stdout.read(4096)
            if not chunk:
                break
            yield chunk

    except Exception as e:
        print(f"Error in video stream: {e}")
    finally:
        try:
            process.stdin.close()
            process.stdout.close()
            process.terminate()
            process.wait(timeout=2)
        except:
            pass




@app.route('/')
def index():
    """Display the main camera viewer page."""
    title = f"Can Inspection - {STATION_NAME}" if STATION_NAME else "Can Inspection Station"
    heading = f"Can Inspection {STATION_NAME}" if STATION_NAME else "Can Inspection Station"

    return render_template('index.html',
                         title=title,
                         heading=heading,
                         cameras=CAMERAS)


@app.route('/stream/<camera>')
def stream(camera):
    if camera not in CAMERAS:
        return "Camera not found", 404
    return Response(
        generate_stream(camera),
        mimetype='multipart/x-mixed-replace; boundary=frame'
    )


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


@app.route('/snapshot/<camera>')
def snapshot(camera):
    if camera not in CAMERAS:
        return "Camera not found", 404
    with camera_state[camera]["lock"]:
        frame = camera_state[camera]["frame"]
    if frame is None:
        return "No frame available", 503
    return Response(frame, mimetype='image/jpeg')


@app.route('/config')
def config_page():
    """Display the Viam configuration page."""
    # Read current config if it exists
    current_config = ""
    config_exists = os.path.exists(VIAM_CONFIG_PATH)

    if config_exists:
        try:
            with open(VIAM_CONFIG_PATH, 'r') as f:
                current_config = f.read()
        except Exception as e:
            flash(f'Error reading config: {e}', 'error')

    return render_template('config.html',
                         current_config=current_config,
                         config_exists=config_exists)


@app.route('/api/viam-running')
def api_viam_running():
    """API endpoint to check if viam-server is running (for live status updates)."""
    running = is_viam_server_running()
    status_class = 'running' if running else 'stopped'
    status_text = 'Running' if running else 'Stopped'

    # Return HTML fragment with HTMX attributes preserved for continued polling
    return f'''<div class="status {status_class}"
         hx-get="/api/viam-running"
         hx-trigger="every 1s"
         hx-swap="outerHTML">
        <strong>Viam Server Status:</strong> {status_text}
    </div>'''


@app.route('/config/update', methods=['POST'])
def update_config():
    """Update the Viam configuration and restart the server."""
    try:
        new_config = request.form.get('config', '')

        if not new_config.strip():
            flash('Configuration cannot be empty', 'error')
            return redirect(url_for('config_page'))

        # Validate JSON
        try:
            json.loads(new_config)
        except json.JSONDecodeError as e:
            flash(f'Invalid JSON: {e}', 'error')
            return redirect(url_for('config_page'))

        # Write the new config
        with open(VIAM_CONFIG_PATH, 'w') as f:
            f.write(new_config)

        # Restart viam-server via s6
        restart_viam_server()

        flash('Configuration updated successfully. Viam server is restarting...', 'success')
        return redirect(url_for('config_page'))

    except Exception as e:
        flash(f'Error updating config: {e}', 'error')
        return redirect(url_for('config_page'))


def is_viam_server_running():
    """Check if viam-server process is running."""
    try:
        for proc in psutil.process_iter(['name', 'cmdline']):
            cmdline = proc.info.get('cmdline') or []
            cmdline_str = ' '.join(cmdline)
            if 'viam-server' in cmdline_str and '-config' in cmdline_str:
                return True
        return False
    except Exception as e:
        print(f"Error checking viam-server status: {e}")
        return False


def restart_viam_server():
    """
    Restart viam-server using supervisorctl.
    This uses supervisorctl to restart the viam-server service.
    """
    try:
        # Use supervisorctl to restart the viam-server service
        subprocess.run(['supervisorctl', 'restart', 'viam-server'],
                      check=True, timeout=5)
        print("Sent restart signal to viam-server via supervisorctl")
    except subprocess.TimeoutExpired:
        print("Warning: supervisorctl command timed out")
    except subprocess.CalledProcessError as e:
        print(f"Error restarting viam-server via supervisorctl: {e}")
        # Fallback: try to kill the process directly
        try:
            for proc in psutil.process_iter(['name', 'cmdline', 'pid']):
                cmdline = proc.info.get('cmdline') or []
                cmdline_str = ' '.join(cmdline)
                if 'viam-server' in cmdline_str and '-config' in cmdline_str:
                    pid = proc.info['pid']
                    print(f"Killing viam-server process {pid}")
                    os.kill(pid, signal.SIGTERM)
                    # Give it 2 seconds to terminate gracefully
                    time.sleep(2)
                    try:
                        # Check if still alive, force kill if needed
                        os.kill(pid, 0)
                        print(f"Process still alive, sending SIGKILL")
                        os.kill(pid, signal.SIGKILL)
                    except OSError:
                        pass  # Process already terminated
        except Exception as e2:
            print(f"Error in fallback kill: {e2}")
    except Exception as e:
        print(f"Unexpected error restarting viam-server: {e}")


def main():
    node = Node()

    print(f"Configuration:")
    print(f"  Framerate: {FRAMERATE} fps")
    print(f"  Station Name: {STATION_NAME or '(none)'}")
    print()
    print("Subscribing to camera topics...")

    for key, cam in CAMERAS.items():
        camera_state[key] = {"frame": None, "lock": threading.Lock()}
        success = node.subscribe(GzImage, cam["topic"], make_callback(key))
        status = "OK" if success else "FAILED"
        print(f"  {cam['topic']}: {status}")

    print(f"\nStarting web server on http://0.0.0.0:8081")
    print("Open this URL in your browser to view the cameras.")
    print("\nAvailable endpoints:")
    print("  /              - Web UI with MJPEG streams")
    print("  /stream/<cam>  - MJPEG stream (multipart/x-mixed-replace)")
    print("  /video/<cam>   - H.264 video stream (video/mp2t)")
    print("  /snapshot/<cam>- Single JPEG snapshot")
    print("\nCamera names: " + ", ".join(CAMERAS.keys()))
    app.run(host='0.0.0.0', port=8081, threaded=True)


if __name__ == "__main__":
    main()
