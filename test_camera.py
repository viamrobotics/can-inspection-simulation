#!/usr/bin/env python3
"""
Test script to verify the Gazebo camera bridge works.

This script connects to a local viam-server and retrieves an image
from the simulated Gazebo camera.

Usage:
    python3 test_camera.py
"""

import asyncio
import sys
from datetime import datetime


async def main():
    try:
        from viam.robot.client import RobotClient
        from viam.components.camera import Camera
    except ImportError:
        print("ERROR: viam-sdk not installed. Run: pip install viam-sdk")
        sys.exit(1)

    # Configuration
    ADDRESS = "localhost:8443"
    CAMERA_NAME = "sim-camera"

    print(f"Connecting to robot at {ADDRESS}...")

    try:
        robot = await RobotClient.at_address(
            ADDRESS,
            RobotClient.Options(
                disable_sessions=True,
                allow_insecure_connection=True,
            ),
        )
    except Exception as e:
        print(f"ERROR: Failed to connect to robot: {e}")
        print("\nMake sure viam-server is running with the gazebo-camera module configured.")
        sys.exit(1)

    print(f"Connected! Getting camera '{CAMERA_NAME}'...")

    try:
        camera = Camera.from_robot(robot, CAMERA_NAME)
    except Exception as e:
        print(f"ERROR: Failed to get camera: {e}")
        print("\nAvailable components:")
        for name in robot.resource_names:
            print(f"  - {name}")
        await robot.close()
        sys.exit(1)

    print("Getting image...")

    try:
        image = await camera.get_image()
    except Exception as e:
        print(f"ERROR: Failed to get image: {e}")
        await robot.close()
        sys.exit(1)

    # Save the image
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"gazebo_camera_{timestamp}.jpg"

    with open(filename, "wb") as f:
        f.write(image.data)

    print(f"SUCCESS! Image saved to: {filename}")
    print(f"  Size: {len(image.data)} bytes")
    print(f"  MIME type: {image.mime_type}")

    # Get properties
    try:
        props = await camera.get_properties()
        print(f"  Supports PCD: {props.supports_pcd}")
    except Exception as e:
        print(f"  (Could not get properties: {e})")

    await robot.close()
    print("\nPOC test complete!")


if __name__ == "__main__":
    asyncio.run(main())
