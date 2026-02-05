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
from flask import Flask, Response, request, render_template_string, redirect, url_for, flash
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


def generate_html():
    """Generate the HTML page from the CAMERAS config."""
    camera_cards = []
    for key, cam in CAMERAS.items():
        card = f'''
        <div class="camera-card">
            <div class="camera-header">
                <span>{cam["label"]}</span>
                <span class="topic">{cam["topic"]}</span>
            </div>
            <div class="camera-feed">
                <img src="/stream/{key}" alt="{cam["label"]}">
            </div>
            <div class="camera-description">{cam["description"]}</div>
        </div>'''
        camera_cards.append(card)

    title = f"Can Inspection - {STATION_NAME}" if STATION_NAME else "Can Inspection Station"
    heading = f"Can Inspection {STATION_NAME}" if STATION_NAME else "Can Inspection Station"

    return f'''<!DOCTYPE html>
<html>
<head>
    <title>{title}</title>
    <style>
        body {{
            background: #1a1a1a;
            color: #fff;
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            margin: 0;
            padding: 20px;
        }}
        .nav {{
            text-align: right;
            margin-bottom: 10px;
        }}
        .nav a {{
            color: #4a9eff;
            text-decoration: none;
            padding: 8px 16px;
            border: 1px solid #4a9eff;
            border-radius: 4px;
            font-size: 14px;
            transition: all 0.2s;
        }}
        .nav a:hover {{
            background: #4a9eff;
            color: #1a1a1a;
        }}
        h1 {{
            text-align: center;
            margin-bottom: 5px;
            font-weight: 400;
        }}
        .subtitle {{
            text-align: center;
            color: #888;
            margin-bottom: 30px;
        }}
        .camera-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(400px, 1fr));
            gap: 20px;
            max-width: 1400px;
            margin: 0 auto;
        }}
        .camera-card {{
            background: #252525;
            border-radius: 8px;
            overflow: hidden;
            box-shadow: 0 4px 20px rgba(0,0,0,0.3);
        }}
        .camera-header {{
            padding: 12px 16px;
            background: #333;
            font-size: 14px;
            font-weight: 500;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }}
        .camera-header .topic {{
            color: #888;
            font-family: monospace;
            font-size: 11px;
        }}
        .camera-feed {{
            background: #000;
        }}
        .camera-feed img {{
            display: block;
            width: 100%;
            height: auto;
        }}
        .camera-description {{
            padding: 10px 16px;
            font-size: 12px;
            color: #888;
        }}
    </style>
</head>
<body>
    <div class="nav">
        <a href="/config">⚙ Configuration</a>
    </div>
    <h1>{heading}</h1>
    <p class="subtitle">Simulated conveyor belt inspection system</p>
    <div class="camera-grid">
        {"".join(camera_cards)}
    </div>
</body>
</html>'''


@app.route('/')
def index():
    return generate_html()


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

    # Check if viam-server is running
    viam_running = is_viam_server_running()

    return render_template_string(CONFIG_PAGE_TEMPLATE,
                                 current_config=current_config,
                                 config_exists=config_exists,
                                 viam_running=viam_running)


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
    Restart viam-server by sending a signal to s6-overlay.
    This uses s6-svc to restart the viam-server service.
    """
    try:
        # Use s6-svc to restart the viam-server service
        # -r restarts the service, -d brings it down, -u brings it up
        subprocess.run(['/command/s6-svc', '-r', '/run/service/viam-server'],
                      check=True, timeout=5)
        print("Sent restart signal to viam-server via s6")
    except subprocess.TimeoutExpired:
        print("Warning: s6-svc command timed out")
    except subprocess.CalledProcessError as e:
        print(f"Error restarting viam-server via s6: {e}")
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


# HTML template for the config page
CONFIG_PAGE_TEMPLATE = '''<!DOCTYPE html>
<html>
<head>
    <title>Viam Configuration</title>
    <style>
        body {
            background: #1a1a1a;
            color: #fff;
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            margin: 0;
            padding: 20px;
            max-width: 1200px;
            margin: 0 auto;
        }
        h1 {
            margin-bottom: 5px;
            font-weight: 400;
        }
        .subtitle {
            color: #888;
            margin-bottom: 30px;
        }
        .nav {
            margin-bottom: 20px;
        }
        .nav a {
            color: #4a9eff;
            text-decoration: none;
            margin-right: 20px;
        }
        .nav a:hover {
            text-decoration: underline;
        }
        .status {
            padding: 10px 15px;
            border-radius: 4px;
            margin-bottom: 20px;
        }
        .status.running {
            background: #1a4d2e;
            border-left: 4px solid #28a745;
        }
        .status.stopped {
            background: #4d1a1a;
            border-left: 4px solid #dc3545;
        }
        .form-container {
            background: #252525;
            border-radius: 8px;
            padding: 30px;
            box-shadow: 0 4px 20px rgba(0,0,0,0.3);
        }
        label {
            display: block;
            margin-bottom: 10px;
            font-weight: 500;
        }
        textarea {
            width: 100%;
            min-height: 400px;
            background: #1a1a1a;
            color: #fff;
            border: 1px solid #444;
            border-radius: 4px;
            padding: 15px;
            font-family: 'Monaco', 'Menlo', 'Ubuntu Mono', monospace;
            font-size: 13px;
            line-height: 1.5;
            resize: vertical;
            box-sizing: border-box;
        }
        textarea:focus {
            outline: none;
            border-color: #4a9eff;
        }
        .button-group {
            margin-top: 20px;
            display: flex;
            gap: 10px;
        }
        button {
            background: #4a9eff;
            color: #fff;
            border: none;
            padding: 12px 24px;
            border-radius: 4px;
            font-size: 14px;
            font-weight: 500;
            cursor: pointer;
            transition: background 0.2s;
        }
        button:hover {
            background: #357abd;
        }
        button.secondary {
            background: #444;
        }
        button.secondary:hover {
            background: #555;
        }
        .flash {
            padding: 12px 20px;
            border-radius: 4px;
            margin-bottom: 20px;
        }
        .flash.success {
            background: #1a4d2e;
            border-left: 4px solid #28a745;
        }
        .flash.error {
            background: #4d1a1a;
            border-left: 4px solid #dc3545;
        }
        .help {
            margin-top: 20px;
            padding: 15px;
            background: #2a2a2a;
            border-radius: 4px;
            font-size: 13px;
            color: #888;
        }
        .help h3 {
            margin-top: 0;
            color: #fff;
            font-size: 14px;
        }
        .help code {
            background: #1a1a1a;
            padding: 2px 6px;
            border-radius: 3px;
            font-family: monospace;
        }
    </style>
</head>
<body>
    <div class="nav">
        <a href="/">← Back to Camera Viewer</a>
        <a href="/config">Configuration</a>
    </div>

    <h1>Viam Configuration</h1>
    <p class="subtitle">Update viam.json credentials</p>

    {% with messages = get_flashed_messages(with_categories=true) %}
        {% if messages %}
            {% for category, message in messages %}
                <div class="flash {{ category }}">{{ message }}</div>
            {% endfor %}
        {% endif %}
    {% endwith %}

    <div class="status {{ 'running' if viam_running else 'stopped' }}">
        <strong>Viam Server Status:</strong> {{ 'Running' if viam_running else 'Stopped' }}
    </div>

    <div class="form-container">
        <form method="POST" action="/config/update">
            <label for="config">Viam Configuration (viam.json)</label>
            <textarea name="config" id="config" required>{{ current_config }}</textarea>

            <div class="button-group">
                <button type="submit">Update and Restart</button>
                <button type="button" class="secondary" onclick="validateJSON()">Validate JSON</button>
            </div>
        </form>
    </div>

    <div class="help">
        <h3>Instructions</h3>
        <ul>
            <li>Paste your <code>viam.json</code> configuration from the Viam app</li>
            <li>Click "Validate JSON" to check for syntax errors</li>
            <li>Click "Update and Restart" to save changes and restart the Viam server</li>
            <li>The server will automatically restart with the new credentials</li>
        </ul>
    </div>

    <script>
        function validateJSON() {
            const textarea = document.getElementById('config');
            try {
                JSON.parse(textarea.value);
                alert('JSON is valid!');
            } catch (e) {
                alert('Invalid JSON: ' + e.message);
            }
        }
    </script>
</body>
</html>'''


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
