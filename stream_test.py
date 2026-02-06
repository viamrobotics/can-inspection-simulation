#!/usr/bin/env python3
"""
Test server for video streaming.
Generates a simple clock animation and streams it via MP4.
"""

import time
import math
from datetime import datetime
from flask import Flask, Response
from PIL import Image, ImageDraw, ImageFont
from streaming import generate_mp4_stream

app = Flask(__name__)

# Video settings
WIDTH = 800
HEIGHT = 600
FRAMERATE = 30
BACKGROUND_COLOR = (30, 30, 40)
CLOCK_COLOR = (255, 255, 255)
HAND_COLOR = (255, 100, 100)


def generate_clock_frames():
    """Generate infinite clock animation frames."""
    frame_count = 0
    while True:
        # Create blank image
        img = Image.new('RGB', (WIDTH, HEIGHT), BACKGROUND_COLOR)
        draw = ImageDraw.Draw(img)

        # Get current time
        now = datetime.now()

        # Draw clock circle
        center_x, center_y = WIDTH // 2, HEIGHT // 2
        radius = min(WIDTH, HEIGHT) // 3
        draw.ellipse(
            [center_x - radius, center_y - radius,
             center_x + radius, center_y + radius],
            outline=CLOCK_COLOR,
            width=3
        )

        # Draw clock ticks
        for i in range(12):
            angle = math.radians(i * 30 - 90)
            x1 = center_x + int((radius - 20) * math.cos(angle))
            y1 = center_y + int((radius - 20) * math.sin(angle))
            x2 = center_x + int(radius * math.cos(angle))
            y2 = center_y + int(radius * math.sin(angle))
            draw.line([x1, y1, x2, y2], fill=CLOCK_COLOR, width=2)

        # Draw hour hand
        hour_angle = math.radians((now.hour % 12) * 30 + now.minute * 0.5 - 90)
        hour_length = radius * 0.5
        hour_x = center_x + int(hour_length * math.cos(hour_angle))
        hour_y = center_y + int(hour_length * math.sin(hour_angle))
        draw.line([center_x, center_y, hour_x, hour_y], fill=HAND_COLOR, width=6)

        # Draw minute hand
        minute_angle = math.radians(now.minute * 6 + now.second * 0.1 - 90)
        minute_length = radius * 0.7
        minute_x = center_x + int(minute_length * math.cos(minute_angle))
        minute_y = center_y + int(minute_length * math.sin(minute_angle))
        draw.line([center_x, center_y, minute_x, minute_y], fill=HAND_COLOR, width=4)

        # Draw second hand (smooth animation)
        second_angle = math.radians(now.second * 6 + now.microsecond / 166666.67 - 90)
        second_length = radius * 0.9
        second_x = center_x + int(second_length * math.cos(second_angle))
        second_y = center_y + int(second_length * math.sin(second_angle))
        draw.line([center_x, center_y, second_x, second_y], fill=(100, 150, 255), width=2)

        # Draw center dot
        dot_radius = 8
        draw.ellipse(
            [center_x - dot_radius, center_y - dot_radius,
             center_x + dot_radius, center_y + dot_radius],
            fill=HAND_COLOR
        )

        # Draw timestamp
        time_str = now.strftime("%H:%M:%S.%f")[:-3]
        # Use default font (no need to load specific font)
        bbox = draw.textbbox((0, 0), time_str)
        text_width = bbox[2] - bbox[0]
        draw.text(
            (center_x - text_width // 2, center_y + radius + 30),
            time_str,
            fill=CLOCK_COLOR
        )

        # Draw frame counter
        counter_text = f"Frame: {frame_count} | FPS: {FRAMERATE}"
        draw.text((10, 10), counter_text, fill=CLOCK_COLOR)

        frame_count += 1
        yield img


@app.route('/')
def index():
    """Simple HTML page with video player."""
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Video Streaming Test</title>
        <link href="https://vjs.zencdn.net/8.10.0/video-js.css" rel="stylesheet">
        <style>
            body {
                background: #222;
                color: #fff;
                font-family: monospace;
                display: flex;
                flex-direction: column;
                align-items: center;
                justify-content: center;
                min-height: 100vh;
                margin: 0;
                padding: 20px;
            }
            h1 {
                margin-bottom: 20px;
            }
            .video-container {
                width: 800px;
                max-width: 90vw;
            }
            .video-js {
                width: 100%;
                height: 600px;
            }
            .info {
                margin-top: 20px;
                padding: 15px;
                background: #333;
                border-radius: 4px;
                max-width: 800px;
            }
            code {
                background: #444;
                padding: 2px 6px;
                border-radius: 3px;
            }
            .status {
                margin-top: 10px;
                padding: 10px;
                background: #444;
                border-radius: 4px;
                font-size: 12px;
            }
            .status.error {
                background: #631;
            }
        </style>
    </head>
    <body>
        <h1>Video Streaming Test - Clock Animation</h1>

        <div class="video-container">
            <video id="video" class="video-js vjs-default-skin" autoplay muted playsinline></video>
        </div>

        <div class="status" id="status">Initializing...</div>

        <div class="info">
            <h3>Test Info:</h3>
            <ul>
                <li>Resolution: 800x600</li>
                <li>Target FPS: 30</li>
                <li>Codec: H.264 (Baseline profile)</li>
                <li>Format: Fragmented MP4 with video.js</li>
                <li>Buffer management: Automatic</li>
            </ul>
            <p>This test stream generates a simple clock animation locally. Use this to test:</p>
            <ul>
                <li>Video playback smoothness</li>
                <li>Long-running stream stability</li>
                <li>Browser compatibility</li>
                <li>Buffer management (no frame skipping!)</li>
            </ul>
            <p>To modify settings, edit <code>stream_test.py</code> and <code>streaming.py</code></p>
        </div>

        <script src="https://vjs.zencdn.net/8.10.0/video.min.js"></script>
        <script>
            const statusEl = document.getElementById('status');
            let retryCount = 0;
            const maxRetries = 3;

            function updateStatus(msg, isError = false) {
                statusEl.textContent = msg;
                statusEl.className = 'status' + (isError ? ' error' : '');
                console.log(msg);
            }

            // Initialize video.js player
            const player = videojs('video', {
                autoplay: true,
                muted: true,
                controls: true,
                fluid: false,
                liveui: true,
                html5: {
                    vhs: {
                        overrideNative: true
                    }
                }
            });

            // Set the source
            player.src({
                src: '/video',
                type: 'video/mp4'
            });

            // Event handlers
            player.on('loadstart', () => {
                updateStatus('Loading stream...');
            });

            player.on('playing', () => {
                updateStatus('✓ Stream playing - Buffer managed by video.js');
                retryCount = 0;
            });

            player.on('waiting', () => {
                updateStatus('Buffering...');
            });

            player.on('error', function() {
                const error = player.error();
                updateStatus(`Error: ${error.message} (Code: ${error.code})`, true);

                // Retry logic
                if (retryCount < maxRetries) {
                    retryCount++;
                    updateStatus(`Retrying... (${retryCount}/${maxRetries})`);
                    setTimeout(() => {
                        player.src({ src: '/video', type: 'video/mp4' });
                        player.load();
                        player.play();
                    }, 2000);
                } else {
                    updateStatus(`Stream failed after ${maxRetries} retries`, true);
                }
            });

            // Monitor buffer health
            setInterval(() => {
                const buffered = player.buffered();
                if (buffered.length > 0 && player.paused() === false) {
                    const bufferEnd = buffered.end(buffered.length - 1);
                    const currentTime = player.currentTime();
                    const bufferSize = bufferEnd - currentTime;
                    updateStatus(`✓ Playing | Buffer: ${bufferSize.toFixed(1)}s`);
                }
            }, 2000);

            // Cleanup
            window.addEventListener('beforeunload', () => {
                player.dispose();
            });
        </script>
    </body>
    </html>
    """


@app.route('/video')
def video():
    """MP4 video stream endpoint."""
    return Response(
        generate_mp4_stream(generate_clock_frames(), WIDTH, HEIGHT, FRAMERATE),
        mimetype='video/mp4'
    )


if __name__ == "__main__":
    print(f"Starting test video server on http://0.0.0.0:5000")
    print(f"Resolution: {WIDTH}x{HEIGHT} @ {FRAMERATE}fps")
    print("\nOpen http://localhost:5000 in your browser to test streaming")
    app.run(host='0.0.0.0', port=5000, threaded=True, debug=True)
