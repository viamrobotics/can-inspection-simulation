#!/usr/bin/env python3
"""
Can Spawner for Conveyor Belt Simulation (Object Pool Version)

Spawns a fixed pool of cans at startup and recycles them continuously.
When a can reaches the end of the belt, it teleports back to the start.

This design eliminates spawn/delete overhead and prevents orphaned cans
from accumulating in Gazebo when delete operations fail.

Uses gz-transport Python bindings for efficient pose updates.
"""

import os
import time
import random
import subprocess
import threading

from gz.transport13 import Node
from gz.msgs10.pose_pb2 import Pose
from gz.msgs10.boolean_pb2 import Boolean

# =============================================================================
# Configuration
# =============================================================================

# Belt geometry
BELT_START_X = -0.92  # X position where cans enter (start of belt)
BELT_END_X = 1.00     # X position where cans recycle (end of belt)
BELT_Y = 0.0          # Y position (center of belt)
CAN_Z = 0.54          # Z position (height on belt)

# Pool settings
# Belt is 1.92m long. With spacing of 0.40m, max cans = floor(1.92/0.40) + 1 = 5
POOL_SIZE = 5                # Number of cans in the pool
DENT_COUNT = 1               # Number of dented cans in the pool (rest are good)
CAN_SPACING = 0.40           # Meters between can centers
Y_VARIATION = 0.03           # Random Y offset range for visual variety

# Movement settings
BELT_SPEED = 0.10            # Meters per second
UPDATE_INTERVAL = 0.05       # Seconds between position updates (20 Hz)

# Gazebo world name (used in service paths)
# Can be overridden via GZ_WORLD_NAME environment variable
WORLD_NAME = os.environ.get("GZ_WORLD_NAME", "cylinder_inspection")

# =============================================================================
# Can Pool
# =============================================================================

class Can:
    """Represents a single can in the pool."""

    def __init__(self, name: str, dented: bool, x_pos: float):
        self.name = name
        self.dented = dented
        self.x_pos = x_pos
        self.y_offset = random.uniform(-Y_VARIATION, Y_VARIATION)
        self.waiting_to_recycle = False


class CanPool:
    """Manages a fixed pool of cans on the conveyor belt."""

    def __init__(self):
        self.cans: list[Can] = []
        self.node = Node()
        self.lock = threading.Lock()

    def initialize(self):
        """Spawn all cans in the pool, evenly spaced along the belt."""
        log("Initializing can pool...")

        # Calculate belt length
        belt_length = BELT_END_X - BELT_START_X

        # Create cans with even spacing
        for i in range(POOL_SIZE):
            is_dented = i < DENT_COUNT
            model_type = "can_dented" if is_dented else "can_good"
            name = f"pool_can_{i:02d}"

            # Space cans evenly, starting from belt start
            x_pos = BELT_START_X + (i * CAN_SPACING)

            # Spawn in Gazebo
            if self._spawn_can(name, model_type, x_pos):
                can = Can(name, is_dented, x_pos)
                self.cans.append(can)
                log(f"  Spawned {name} ({'DENTED' if is_dented else 'good'}) at x={x_pos:.2f}")
            else:
                log(f"  FAILED to spawn {name}")

        log(f"Pool initialized: {len(self.cans)} cans ({DENT_COUNT} dented, {POOL_SIZE - DENT_COUNT} good)")

    def _spawn_can(self, name: str, model_type: str, x_pos: float) -> bool:
        """Spawn a can in Gazebo."""
        y_offset = random.uniform(-Y_VARIATION, Y_VARIATION)

        req = (
            f'sdf_filename: "model://{model_type}", '
            f'name: "{name}", '
            f'pose: {{position: {{x: {x_pos}, y: {BELT_Y + y_offset}, z: {CAN_Z + 0.06}}}}}'
        )

        cmd = [
            "gz", "service", "-s", f"/world/{WORLD_NAME}/create",
            "--reqtype", "gz.msgs.EntityFactory",
            "--reptype", "gz.msgs.Boolean",
            "--timeout", "5000",
            "--req", req
        ]

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            return result.returncode == 0 and "true" in result.stdout.lower()
        except Exception as e:
            log(f"Spawn error: {e}")
            return False

    def update_positions(self, delta_time: float):
        """Move all cans forward and update their positions in Gazebo."""
        distance = BELT_SPEED * delta_time

        with self.lock:
            # Pass 1: Advance all active cans, mark those needing recycle
            for can in self.cans:
                if not can.waiting_to_recycle:
                    can.x_pos += distance
                    if can.x_pos > BELT_END_X:
                        can.waiting_to_recycle = True

            # Pass 2: Recycle at most ONE waiting can if space available
            if self._space_available_at_start():
                for can in self.cans:
                    if can.waiting_to_recycle:
                        can.x_pos = BELT_START_X
                        can.y_offset = random.uniform(-Y_VARIATION, Y_VARIATION)
                        can.waiting_to_recycle = False
                        log(f"{can.name} recycled")
                        break  # Only one per cycle

            # Pass 3: Update positions in Gazebo (skip waiting cans)
            for can in self.cans:
                if not can.waiting_to_recycle:
                    self._set_can_position(can)

    def _space_available_at_start(self):
        """Check if there's room to recycle a can at the belt start."""
        active_cans = [c for c in self.cans if not c.waiting_to_recycle]
        if not active_cans:
            return True  # No active cans, safe to recycle
        min_x = min(c.x_pos for c in active_cans)
        return min_x > BELT_START_X + CAN_SPACING

    def _set_can_position(self, can: Can):
        """Update a can's position in Gazebo using gz-transport."""
        pose = Pose()
        pose.name = can.name
        pose.position.x = can.x_pos
        pose.position.y = BELT_Y + can.y_offset
        pose.position.z = CAN_Z

        try:
            self.node.request(
                f"/world/{WORLD_NAME}/set_pose",
                pose,
                Pose,
                Boolean,
                100  # timeout in ms
            )
        except Exception:
            pass  # Position updates are best-effort


# =============================================================================
# Main
# =============================================================================

def log(msg: str):
    """Print with flush for immediate output."""
    print(msg, flush=True)


def main():
    """Main entry point."""
    log("=" * 50)
    log("Can Spawner (Object Pool Version)")
    log("=" * 50)
    log(f"  World: {WORLD_NAME}")
    log(f"  Pool size: {POOL_SIZE} cans ({DENT_COUNT} dented)")
    log(f"  Belt speed: {BELT_SPEED} m/s")
    log(f"  Can spacing: {CAN_SPACING} m")
    log(f"  Update rate: {1/UPDATE_INTERVAL:.0f} Hz")
    log("=" * 50)

    # Wait for Gazebo to be ready
    log("Waiting for Gazebo...")
    time.sleep(5)

    # Initialize the can pool
    pool = CanPool()
    pool.initialize()

    log("Starting conveyor movement...")

    # Main loop: continuously update can positions
    last_time = time.time()

    try:
        while True:
            current_time = time.time()
            delta_time = current_time - last_time
            last_time = current_time

            pool.update_positions(delta_time)

            time.sleep(UPDATE_INTERVAL)

    except KeyboardInterrupt:
        log("\nShutting down...")


if __name__ == "__main__":
    main()
