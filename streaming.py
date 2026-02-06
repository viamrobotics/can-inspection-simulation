#!/usr/bin/env python3
"""
Video streaming utilities using ffmpeg.
Encodes frames to H.264 MP4 for browser-compatible streaming.
"""

import io
import time
import threading
import subprocess
from PIL import Image


def generate_mp4_stream(frame_generator, width, height, framerate=30):
    """
    Generate a fragmented MP4 stream from a frame generator.

    Args:
        frame_generator: Iterator/generator that yields PIL Image objects or JPEG bytes
        width: Video width in pixels
        height: Video height in pixels
        framerate: Target framerate (default: 30)

    Yields:
        bytes: MP4 video chunks
    """
    frame_delay = 1.0 / framerate

    # Start ffmpeg process with browser-compatible settings
    ffmpeg_cmd = [
        'ffmpeg',
        '-f', 'rawvideo',
        '-pix_fmt', 'rgb24',
        '-s', f'{width}x{height}',
        '-r', str(framerate),
        '-i', '-',  # stdin
        '-c:v', 'libx264',
        '-preset', 'ultrafast',
        '-tune', 'zerolatency',
        '-profile:v', 'baseline',  # Browser-compatible profile
        '-level', '3.0',            # Widely supported level
        '-pix_fmt', 'yuv420p',      # Standard web video chroma format
        '-g', str(int(framerate)),  # Keyframe every 1 second
        '-f', 'mp4',
        '-movflags', 'frag_keyframe+empty_moov+default_base_moof',
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
            for frame in frame_generator:
                try:
                    current_time = time.time()
                    elapsed = current_time - last_time

                    # Maintain target framerate
                    if elapsed < frame_delay:
                        time.sleep(frame_delay - elapsed)

                    # Convert frame to RGB bytes if needed
                    if isinstance(frame, bytes):
                        # Assume it's JPEG bytes, decode first
                        img = Image.open(io.BytesIO(frame))
                    else:
                        # Assume it's already a PIL Image
                        img = frame

                    # Ensure correct size
                    if img.size != (width, height):
                        img = img.resize((width, height))

                    # Convert to RGB and get raw bytes
                    if img.mode != 'RGB':
                        img = img.convert('RGB')
                    rgb_data = img.tobytes()

                    process.stdin.write(rgb_data)
                    process.stdin.flush()

                    last_time = time.time()
                except (BrokenPipeError, IOError):
                    break
                except StopIteration:
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
