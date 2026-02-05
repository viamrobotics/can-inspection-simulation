#!/usr/bin/env python3
"""
Capture Training Data for Can Quality Object Detection

Spawns cans in a controlled manner under the inspection camera,
captures labeled images with bounding box annotations, and uploads
them to Viam for ML training.

================================================================================
COMPLETE SETUP AND EXECUTION GUIDE
================================================================================

1. CONTAINER SETUP
------------------
Build and run the container with the Viam config mounted:

    docker stop gz-viam && docker rm gz-viam
    docker build -t gz-harmonic-viam .
    docker run --name gz-viam -d \
        -p 8080:8080 -p 8081:8081 -p 8443:8443 \
        -v ~/viam/config/stationary-vision-viam.json:/etc/viam.json \
        gz-harmonic-viam

The config file (stationary-vision-viam.json) contains the machine credentials
and is mounted to /etc/viam.json where viam-server expects it.


2. PREVENTING EXTRA CANS IN IMAGES (CRITICAL)
---------------------------------------------
The container starts can_spawner.py automatically via s6-overlay, which continuously
spawns cans on the conveyor belt. These will appear in training images!

IMMEDIATELY after the container starts (~10-15 sec for Gazebo to initialize),
kill the spawner:

    docker exec gz-viam pkill -f can_spawner.py

The capture script has its own cleanup routine, but it's much faster and
more reliable if no extra cans exist in the scene.


3. CAMERA GEOMETRY (CRITICAL FOR BOUNDING BOX ACCURACY)
-------------------------------------------------------
The inspection camera in cylinder_inspection.sdf has TWO relevant poses:

  Model pose:  <pose>0 0 0.88 0 1.5708 0</pose>
               Position (0, 0, 0.88), pitched 90 degrees (pi/2) around Y axis

  Sensor pose: <pose>0 0 -0.04 0 0 0</pose>  (within the model)
               Offset -0.04m in the model's LOCAL Z axis

After the 90 degree pitch rotation around Y:
  - Model's local +X -> World -Z (camera now looks DOWN)
  - Model's local +Y -> World +Y (unchanged)
  - Model's local +Z -> World +X

Therefore, the sensor's local Z offset of -0.04 becomes a WORLD X offset:
  - Sensor world position = (0, 0, 0.88) + (-0.04, 0, 0) = (-0.04, 0, 0.88)

This is why CAMERA_SENSOR_X = -0.04, not 0!


4. COORDINATE MAPPING (IMAGE <-> WORLD)
---------------------------------------
With camera pitched 90 degrees looking down (-Z direction):

  Image +X (right)  <->  World -Y (camera's right when looking down)
  Image +Y (down)   <->  World -X (camera's "down" when looking at ground)

Converting world position to pixel coordinates:
  pixel_x = IMAGE_WIDTH/2  - (world_y - camera_y) * PIXELS_PER_METER
  pixel_y = IMAGE_HEIGHT/2 - (world_x - camera_x) * PIXELS_PER_METER

The NEGATIVE signs are critical! Objects at larger world X appear HIGHER
in the image (smaller pixel_y), and objects at larger world Y appear more
LEFT in the image (smaller pixel_x).


5. CALCULATING PIXELS_PER_METER
-------------------------------
From camera intrinsics:
  - Horizontal FOV: 1.047 radians (60 degrees)
  - Image size: 640 x 480
  - Distance to can top: CAMERA_Z - CAN_TOP_Z = 0.88 - 0.60 = 0.28m

  VIEW_WIDTH = 2 * distance * tan(FOV/2) = 2 * 0.28 * tan(30 deg) = 0.323m
  PIXELS_PER_METER = IMAGE_WIDTH / VIEW_WIDTH = 640 / 0.323 = 1979.9


6. CAN PARAMETERS (ADJUST IF CAN SIZE CHANGES)
----------------------------------------------
Current values for standard beverage can:
  CAN_RADIUS = 0.033      # 33mm radius (66mm diameter)
  CAN_HEIGHT = 0.12       # 120mm tall
  CAN_Z = 0.54            # Z position where cans sit on belt

The can TOP is at: CAN_Z + CAN_HEIGHT/2 = 0.54 + 0.06 = 0.60m

If you change can dimensions:
  1. Update CAN_RADIUS, CAN_HEIGHT, CAN_Z as needed
  2. Recalculate CAN_TOP_Z = CAN_Z + CAN_HEIGHT/2
  3. Recalculate CAMERA_DISTANCE = CAMERA_POS_Z - CAN_TOP_Z
  4. PIXELS_PER_METER will auto-update from VIEW_WIDTH calculation

The bounding box size is: CAN_RADIUS * PIXELS_PER_METER * margin_factor
Current margin is 1.15 (15% padding around the can).


7. CREDENTIALS SETUP
--------------------
Create capture_config.json from the template (this file is gitignored):

    cp capture_config.template.json capture_config.json
    # Edit capture_config.json with your credentials

Required fields:
  viam_api_key      - API key from app.viam.com -> Organization Settings
  viam_api_key_id   - API key ID (shown when key is created)
  viam_org_id       - Organization ID from URL: app.viam.com/fleet?org=<ORG_ID>
  viam_location_id  - Location ID from URL: app.viam.com/fleet/location/<LOC_ID>
  viam_part_id      - Machine/Part ID from the viam config JSON ("id" field)

The PART_ID can be found in the mounted config file:
    docker exec gz-viam cat /etc/viam.json | grep '"id"'

Alternatively, set environment variables (they override the config file):
  VIAM_API_KEY, VIAM_API_KEY_ID, VIAM_ORG_ID, VIAM_LOCATION_ID, VIAM_PART_ID


8. RUNNING THE CAPTURE
----------------------
Copy config into container and run:

    docker cp capture_config.json gz-viam:/opt/capture_config.json
    docker exec gz-viam python3 /opt/capture_training_data.py --samples 50

Or with environment variables:

    docker exec \
        -e VIAM_API_KEY="your-api-key" \
        -e VIAM_API_KEY_ID="your-api-key-id" \
        -e VIAM_ORG_ID="your-org-id" \
        -e VIAM_LOCATION_ID="your-location-id" \
        -e VIAM_PART_ID="your-part-id" \
        gz-viam python3 /opt/capture_training_data.py --samples 50

Options:
  --samples N    Capture N images per class (default: 50)
  --no-upload    Capture images locally without uploading to Viam
  --output DIR   Save images to DIR (default: ./training_data)
  --config FILE  Path to config JSON (default: ./capture_config.json)


9. TROUBLESHOOTING
------------------
Multiple cans in images:
  -> Kill can_spawner.py before running capture
  -> Restart container fresh if too many cans accumulated

Bounding boxes offset from cans:
  -> Verify CAMERA_SENSOR_X accounts for sensor pose offset after rotation
  -> Check coordinate sign convention (both should be NEGATIVE in the formulas)
  -> Verify CAMERA_DISTANCE uses can TOP, not can center or belt surface

Bounding boxes wrong size:
  -> Check PIXELS_PER_METER calculation
  -> Verify CAN_RADIUS matches actual model
  -> Verify CAMERA_DISTANCE is correct (camera Z - can top Z)

Upload fails with "no robot part found":
  -> VIAM_PART_ID is wrong; get it from the config JSON "id" field

================================================================================
"""

import argparse
import asyncio
import io
import json
import os
import random
import subprocess
import time
from datetime import datetime
from pathlib import Path

# Viam SDK imports
try:
    from viam.app.viam_client import ViamClient
    from viam.rpc.dial import DialOptions, Credentials
    from viam.proto.app.data import BinaryID
    VIAM_SDK_AVAILABLE = True
except ImportError:
    VIAM_SDK_AVAILABLE = False
    print("Warning: viam-sdk not installed. Upload will be disabled.")

# PIL for image handling
try:
    from PIL import Image
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False
    print("Warning: Pillow not installed. Install with: pip install Pillow")

# Gazebo transport imports
try:
    from gz.transport13 import Node
    from gz.msgs10.image_pb2 import Image as GzImage
    from gz.msgs10.pose_pb2 import Pose
    from gz.msgs10.boolean_pb2 import Boolean
    GZ_AVAILABLE = True
except ImportError:
    GZ_AVAILABLE = False
    print("Warning: gz-transport not available. Run inside Gazebo container.")


# ============================================================================
# Camera and Scene Configuration
# ============================================================================

# Camera parameters (from inspection_camera in cylinder_inspection.sdf)
# Model pose: <pose>0 0 0.88 0 1.5708 0</pose> - at (0,0,0.88) pitched 90° around Y
# Sensor pose within model: <pose>0 0 -0.04 0 0 0</pose> - offset in local Z
# After 90° pitch, local Z maps to world -X, so sensor is at world X = -0.04
CAMERA_TOPIC = "/inspection_camera"
CAMERA_MODEL_X = 0.0    # Model X position (used for spawning cans)
CAMERA_MODEL_Y = 0.0    # Model Y position (used for spawning cans)
CAMERA_SENSOR_X = -0.04 # Actual sensor X position after rotation (for bounding box calc)
CAMERA_SENSOR_Y = 0.0   # Actual sensor Y position (unchanged by pitch rotation)
CAMERA_POS_Z = 0.88     # Camera Z position (from world file)
CAMERA_HFOV = 1.047     # Horizontal field of view in radians (60 degrees)
IMAGE_WIDTH = 640       # Image width in pixels
IMAGE_HEIGHT = 480      # Image height in pixels

# Can parameters
CAN_RADIUS = 0.033      # Can radius in meters
CAN_HEIGHT = 0.12       # Can height in meters
CAN_Z = 0.54            # Z position where cans sit on belt

# Calculated camera intrinsics
import math
# Distance from camera to TOP of can (what we see from above)
# Can is centered at CAN_Z, top is at CAN_Z + CAN_HEIGHT/2
CAN_TOP_Z = CAN_Z + CAN_HEIGHT / 2  # 0.54 + 0.06 = 0.60
CAMERA_DISTANCE = CAMERA_POS_Z - CAN_TOP_Z  # 0.88 - 0.60 = 0.28m
HFOV_HALF = CAMERA_HFOV / 2
VIEW_WIDTH = 2 * CAMERA_DISTANCE * math.tan(HFOV_HALF)  # Width visible at can level
VIEW_HEIGHT = VIEW_WIDTH * IMAGE_HEIGHT / IMAGE_WIDTH   # Height visible
PIXELS_PER_METER = IMAGE_WIDTH / VIEW_WIDTH             # Scale factor

# Output configuration
SAMPLES_PER_CLASS = 50
OUTPUT_DIR = Path(__file__).parent / "training_data"
CONFIG_FILE = Path(__file__).parent / "capture_config.json"


def log(msg: str):
    """Print with timestamp."""
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


def load_config(config_path: Path) -> dict:
    """
    Load Viam credentials from JSON config file.

    Environment variables override config file values.

    Returns:
        dict with api_key, api_key_id, org_id, location_id, part_id
    """
    config = {}

    # Try to load from config file
    if config_path.exists():
        try:
            with open(config_path) as f:
                file_config = json.load(f)
            config = {
                "api_key": file_config.get("viam_api_key"),
                "api_key_id": file_config.get("viam_api_key_id"),
                "org_id": file_config.get("viam_org_id"),
                "location_id": file_config.get("viam_location_id"),
                "part_id": file_config.get("viam_part_id"),
            }
            log(f"Loaded config from {config_path}")
        except Exception as e:
            log(f"Warning: Failed to load config from {config_path}: {e}")

    # Environment variables override config file
    env_overrides = {
        "api_key": os.environ.get("VIAM_API_KEY"),
        "api_key_id": os.environ.get("VIAM_API_KEY_ID"),
        "org_id": os.environ.get("VIAM_ORG_ID"),
        "location_id": os.environ.get("VIAM_LOCATION_ID"),
        "part_id": os.environ.get("VIAM_PART_ID"),
    }

    for key, value in env_overrides.items():
        if value:
            config[key] = value

    return config


# ============================================================================
# Bounding Box Calculation
# ============================================================================

def calculate_bounding_box(can_x: float, can_y: float) -> dict:
    """
    Calculate normalized bounding box for a can at given position.

    The camera is pitched 90° around Y, looking straight down (-Z direction).
    Camera coordinate frame after rotation:
    - Camera looks along local +X which becomes world -Z (down)
    - Camera's local +Y stays world +Y (left in camera view)
    - Camera's local +Z becomes world +X (up in camera view)

    Image coordinate mapping:
    - Image +X (right) corresponds to world -Y (camera's right)
    - Image +Y (down) corresponds to world -X (camera's down when looking at ground)

    Args:
        can_x: Can X position in world coordinates (meters)
        can_y: Can Y position in world coordinates (meters)

    Returns:
        dict with x_min_normalized, x_max_normalized, y_min_normalized, y_max_normalized
    """
    # Can position relative to camera SENSOR position (not model position)
    rel_x = can_x - CAMERA_SENSOR_X
    rel_y = can_y - CAMERA_SENSOR_Y

    # Convert to pixel coordinates
    # World +Y → image left (negative pixel_x offset from center)
    # World +X → image up (negative pixel_y offset from center)
    center_px_x = IMAGE_WIDTH / 2 - rel_y * PIXELS_PER_METER
    center_px_y = IMAGE_HEIGHT / 2 - rel_x * PIXELS_PER_METER

    # Can radius in pixels (add small margin for safety)
    radius_px = CAN_RADIUS * PIXELS_PER_METER * 1.15  # 15% margin for tight fit

    # Calculate bounding box in pixels
    x_min_px = center_px_x - radius_px
    x_max_px = center_px_x + radius_px
    y_min_px = center_px_y - radius_px
    y_max_px = center_px_y + radius_px

    # Clamp to image bounds
    x_min_px = max(0, x_min_px)
    x_max_px = min(IMAGE_WIDTH, x_max_px)
    y_min_px = max(0, y_min_px)
    y_max_px = min(IMAGE_HEIGHT, y_max_px)

    # Normalize to 0-1 range
    return {
        "x_min_normalized": x_min_px / IMAGE_WIDTH,
        "x_max_normalized": x_max_px / IMAGE_WIDTH,
        "y_min_normalized": y_min_px / IMAGE_HEIGHT,
        "y_max_normalized": y_max_px / IMAGE_HEIGHT,
    }


# ============================================================================
# Gazebo Interaction
# ============================================================================

def run_gz_command(cmd: list, timeout: int = 5) -> tuple[bool, str, str]:
    """Run a gz command and return (success, stdout, stderr)."""
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return result.returncode == 0, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return False, "", "Timeout"
    except Exception as e:
        return False, "", str(e)


def spawn_can(name: str, dented: bool, x_offset: float = 0.0, y_offset: float = 0.0, rotation: float = 0.0) -> bool:
    """Spawn a can at the camera position with optional offset."""
    model_type = "can_dented" if dented else "can_good"

    spawn_x = CAMERA_MODEL_X + x_offset
    spawn_y = CAMERA_MODEL_Y + y_offset

    req = (
        f'sdf_filename: "model://{model_type}", '
        f'name: "{name}", '
        f'pose: {{position: {{x: {spawn_x}, y: {spawn_y}, z: {CAN_Z}}}, '
        f'orientation: {{z: {rotation}}}}}'
    )

    cmd = [
        "gz", "service", "-s", "/world/cylinder_inspection/create",
        "--reqtype", "gz.msgs.EntityFactory",
        "--reptype", "gz.msgs.Boolean",
        "--timeout", "2000",
        "--req", req
    ]

    success, stdout, stderr = run_gz_command(cmd)
    return success and "true" in stdout.lower()


def delete_can(name: str) -> bool:
    """Delete a can from the simulation."""
    cmd = [
        "gz", "service", "-s", "/world/cylinder_inspection/remove",
        "--reqtype", "gz.msgs.Entity",
        "--reptype", "gz.msgs.Boolean",
        "--timeout", "1000",
        "--req", f'name: "{name}", type: 2'
    ]

    success, _, _ = run_gz_command(cmd)
    return success


def quick_delete(name: str) -> bool:
    """Quick delete with short timeout (for cleanup)."""
    cmd = [
        "gz", "service", "-s", "/world/cylinder_inspection/remove",
        "--reqtype", "gz.msgs.Entity",
        "--reptype", "gz.msgs.Boolean",
        "--timeout", "100",
        "--req", f'name: "{name}", type: 2'
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=0.5)
        return result.returncode == 0
    except:
        return False


def cleanup_scene():
    """Remove any leftover cans from previous captures."""
    log("Cleaning up scene...")
    for class_name in ["PASS", "FAIL"]:
        for i in range(60):
            quick_delete(f"capture_can_{class_name}_{i:03d}")
    for i in range(50):
        quick_delete(f"can_{i:04d}")
    time.sleep(0.5)
    log("Scene cleaned")


# ============================================================================
# Image Capture
# ============================================================================

class ImageCapture:
    """Captures images from Gazebo camera topic."""

    def __init__(self):
        self.node = Node()
        self.latest_image = None
        self.image_received = False

    def _on_image(self, msg: GzImage):
        """Callback for camera images."""
        self.latest_image = msg
        self.image_received = True

    def subscribe(self):
        """Subscribe to the camera topic."""
        success = self.node.subscribe(GzImage, CAMERA_TOPIC, self._on_image)
        if not success:
            raise RuntimeError(f"Failed to subscribe to {CAMERA_TOPIC}")
        log(f"Subscribed to {CAMERA_TOPIC}")

    def wait_for_image(self, timeout: float = 2.0) -> bytes | None:
        """Wait for a new image and return it as JPEG bytes."""
        self.image_received = False
        start = time.time()

        while not self.image_received and (time.time() - start) < timeout:
            time.sleep(0.05)

        if not self.image_received or self.latest_image is None:
            return None

        return self._convert_to_jpeg(self.latest_image)

    def _convert_to_jpeg(self, gz_image: GzImage) -> bytes | None:
        """Convert Gazebo image message to JPEG bytes."""
        if not PIL_AVAILABLE:
            return None

        try:
            width = gz_image.width
            height = gz_image.height
            data = gz_image.data

            if len(data) == width * height * 3:
                img = Image.frombytes('RGB', (width, height), data)
            elif len(data) == width * height * 4:
                img = Image.frombytes('RGBA', (width, height), data)
                img = img.convert('RGB')
            else:
                log(f"Unknown image format: {len(data)} bytes for {width}x{height}")
                return None

            buffer = io.BytesIO()
            img.save(buffer, format='JPEG', quality=90)
            return buffer.getvalue()

        except Exception as e:
            log(f"Image conversion error: {e}")
            return None


# ============================================================================
# Main Capture Function
# ============================================================================

def capture_images(output_dir: Path, samples_per_class: int) -> list[dict]:
    """
    Capture labeled images from the simulation.

    Returns:
        List of dicts with: filepath, label, bbox, x_offset, y_offset
    """
    if not GZ_AVAILABLE:
        raise RuntimeError("Gazebo transport not available. Run inside the container.")

    # Create output directory
    output_dir.mkdir(parents=True, exist_ok=True)

    # Clean up any leftover cans first
    cleanup_scene()

    # Initialize image capture
    capture = ImageCapture()
    capture.subscribe()

    log("Waiting for camera...")
    time.sleep(1.0)

    captured_data = []

    for class_name, is_dented in [("PASS", False), ("FAIL", True)]:
        log(f"\nCapturing {samples_per_class} {class_name} samples...")

        for i in range(samples_per_class):
            can_name = f"capture_can_{class_name}_{i:03d}"

            # Add position variation (within camera view)
            x_offset = random.uniform(-0.02, 0.02)
            y_offset = random.uniform(-0.02, 0.02)
            rotation = random.uniform(0, 6.28)

            # Spawn can
            if not spawn_can(can_name, dented=is_dented, x_offset=x_offset, y_offset=y_offset, rotation=rotation):
                log(f"  Failed to spawn {can_name}, skipping")
                continue

            # Wait for rendering
            time.sleep(0.2)

            # Capture image
            image_data = capture.wait_for_image(timeout=2.0)

            if image_data:
                # Save locally
                filename = f"{class_name}_{i:03d}.jpg"
                filepath = output_dir / filename
                with open(filepath, 'wb') as f:
                    f.write(image_data)

                # Calculate bounding box
                can_x = CAMERA_MODEL_X + x_offset
                can_y = CAMERA_MODEL_Y + y_offset
                bbox = calculate_bounding_box(can_x, can_y)

                captured_data.append({
                    "filepath": filepath,
                    "label": class_name,
                    "bbox": bbox,
                    "x_offset": x_offset,
                    "y_offset": y_offset,
                })

                if (i + 1) % 10 == 0:
                    log(f"  Captured {i + 1}/{samples_per_class}")
            else:
                log(f"  Failed to capture image for {can_name}")

            # Delete can and wait for scene to clear
            delete_can(can_name)
            time.sleep(0.5)

    log(f"\nCapture complete: {len([d for d in captured_data if d['label'] == 'PASS'])} PASS, "
        f"{len([d for d in captured_data if d['label'] == 'FAIL'])} FAIL")

    # Save metadata
    metadata_path = output_dir / "annotations.json"
    metadata = [
        {
            "filename": d["filepath"].name,
            "label": d["label"],
            "bbox": d["bbox"],
        }
        for d in captured_data
    ]
    with open(metadata_path, 'w') as f:
        json.dump(metadata, f, indent=2)
    log(f"Saved annotations to {metadata_path}")

    return captured_data


# ============================================================================
# Viam Upload with Bounding Boxes
# ============================================================================

async def upload_to_viam(captured_data: list[dict], config: dict):
    """Upload captured images to Viam with bounding box annotations."""

    if not VIAM_SDK_AVAILABLE:
        raise RuntimeError("viam-sdk not installed. Install with: pip install viam-sdk")

    # Get credentials from config (already merged with env vars)
    api_key = config.get("api_key")
    api_key_id = config.get("api_key_id")
    org_id = config.get("org_id")
    location_id = config.get("location_id")
    part_id = config.get("part_id")

    if not all([api_key, api_key_id]):
        raise RuntimeError(
            "Missing credentials. Set in capture_config.json or VIAM_API_KEY/VIAM_API_KEY_ID env vars."
        )

    if not all([org_id, location_id, part_id]):
        raise RuntimeError(
            "Missing org/location/part. Set in capture_config.json or VIAM_ORG_ID/VIAM_LOCATION_ID/VIAM_PART_ID env vars."
        )

    log("Connecting to Viam...")

    dial_options = DialOptions(
        credentials=Credentials(type="api-key", payload=api_key),
        auth_entity=api_key_id
    )

    client = await ViamClient.create_from_dial_options(dial_options)
    data_client = client.data_client

    log("Connected. Uploading images with bounding boxes...")

    uploaded = 0
    failed = 0

    for i, data in enumerate(captured_data):
        filepath = data["filepath"]
        label = data["label"]
        bbox = data["bbox"]

        try:
            # Read image data
            with open(filepath, 'rb') as f:
                image_data = f.read()

            # Upload image
            file_id_full = await data_client.file_upload(
                part_id=part_id,
                data=image_data,
                component_type="camera",
                component_name="training-capture",
                file_name=filepath.name,
                file_extension=".jpg",
                tags=[label, "can-detection-training"],
            )

            # file_upload returns "org_id/location_id/file_id" - extract just the file_id
            file_id = file_id_full.split("/")[-1] if "/" in file_id_full else file_id_full
            log(f"    Extracted file_id: {file_id}")

            # Wait for file to be indexed before adding bounding box
            await asyncio.sleep(2.0)

            # Add bounding box annotation
            binary_id = BinaryID(
                file_id=file_id,
                organization_id=org_id,
                location_id=location_id,
            )

            await data_client.add_bounding_box_to_image_by_id(
                binary_id=binary_id,
                label=label,
                x_min_normalized=bbox["x_min_normalized"],
                x_max_normalized=bbox["x_max_normalized"],
                y_min_normalized=bbox["y_min_normalized"],
                y_max_normalized=bbox["y_max_normalized"],
            )

            uploaded += 1

            if (i + 1) % 5 == 0:
                log(f"  Uploaded {i + 1}/{len(captured_data)}")

        except Exception as e:
            log(f"  Failed to upload {filepath.name}: {e}")
            failed += 1

    log(f"\nUpload complete: {uploaded} images uploaded, {failed} failed")
    log("Next steps:")
    log("  1. Go to app.viam.com → Data")
    log("  2. Filter by tag 'can-detection-training'")
    log("  3. Verify bounding boxes are correct")
    log("  4. Create a dataset and train an object detection model")

    client.close()


# ============================================================================
# Main Entry Point
# ============================================================================

async def main():
    parser = argparse.ArgumentParser(description="Capture training data for can detector")
    parser.add_argument("--no-upload", action="store_true", help="Capture only, don't upload")
    parser.add_argument("--samples", type=int, default=SAMPLES_PER_CLASS,
                        help=f"Samples per class (default: {SAMPLES_PER_CLASS})")
    parser.add_argument("--output", type=Path, default=OUTPUT_DIR,
                        help=f"Output directory (default: {OUTPUT_DIR})")
    parser.add_argument("--config", type=Path, default=CONFIG_FILE,
                        help=f"Path to config JSON file (default: {CONFIG_FILE})")
    args = parser.parse_args()

    log("=" * 50)
    log("Can Detection Training Data Capture")
    log("=" * 50)
    log(f"Camera intrinsics:")
    log(f"  Distance to cans: {CAMERA_DISTANCE:.3f}m")
    log(f"  View width: {VIEW_WIDTH:.3f}m ({IMAGE_WIDTH}px)")
    log(f"  Pixels per meter: {PIXELS_PER_METER:.1f}")
    log(f"  Can radius in pixels: {CAN_RADIUS * PIXELS_PER_METER:.1f}px")
    log("=" * 50)

    # Load credentials config
    config = load_config(args.config)

    # Capture images
    log(f"Capturing {args.samples} samples per class...")
    captured_data = capture_images(args.output, args.samples)

    if not args.no_upload and captured_data:
        await upload_to_viam(captured_data, config)
    elif captured_data:
        log("\nImages saved locally. To upload later, configure credentials and run again.")


if __name__ == "__main__":
    asyncio.run(main())
