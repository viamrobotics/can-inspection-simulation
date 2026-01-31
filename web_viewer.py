#!/usr/bin/env python3
"""
Web viewer for Gazebo cameras.
Serves MJPEG streams for camera topics.

Camera topics can be configured via environment variables:
  GZ_OVERVIEW_TOPIC  - defaults to /overview_camera
  GZ_INSPECTION_TOPIC - defaults to /inspection_camera
  GZ_STATION_NAME - optional station name for display (e.g., "Station 2")
"""

import io
import os
import time
import threading
from flask import Flask, Response

from gz.transport13 import Node
from gz.msgs10.image_pb2 import Image as GzImage
from PIL import Image

app = Flask(__name__)

# =============================================================================
# CAMERA CONFIGURATION
# Topics can be overridden via environment variables.
# =============================================================================
STATION_NAME = os.environ.get("GZ_STATION_NAME", "")
OVERVIEW_TOPIC = os.environ.get("GZ_OVERVIEW_TOPIC", "/overview_camera")
INSPECTION_TOPIC = os.environ.get("GZ_INSPECTION_TOPIC", "/inspection_camera")

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

        time.sleep(0.033)  # ~30fps


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


@app.route('/snapshot/<camera>')
def snapshot(camera):
    if camera not in CAMERAS:
        return "Camera not found", 404
    with camera_state[camera]["lock"]:
        frame = camera_state[camera]["frame"]
    if frame is None:
        return "No frame available", 503
    return Response(frame, mimetype='image/jpeg')


def main():
    node = Node()

    print("Subscribing to camera topics...")

    for key, cam in CAMERAS.items():
        camera_state[key] = {"frame": None, "lock": threading.Lock()}
        success = node.subscribe(GzImage, cam["topic"], make_callback(key))
        status = "OK" if success else "FAILED"
        print(f"  {cam['topic']}: {status}")

    print(f"\nStarting web server on http://0.0.0.0:8081")
    print("Open this URL in your browser to view the cameras.")
    app.run(host='0.0.0.0', port=8081, threaded=True)


if __name__ == "__main__":
    main()
