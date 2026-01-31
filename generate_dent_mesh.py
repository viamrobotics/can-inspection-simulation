#!/usr/bin/env python3
"""
Generate concave dent meshes for overlaying on can models.

Creates small bowl-shaped depressions that can be placed on the can surface
to create realistic-looking dents while keeping the primitive-based can
with all its colors (body, label, lids).

Requirements: pip install numpy numpy-stl
"""

import numpy as np
from stl import mesh
import math
import os


def create_concave_disc(radius, depth, segments=24):
    """
    Create a concave disc (shallow bowl) mesh.

    The disc curves inward, creating a depression effect.
    """
    vertices = []
    faces = []

    # Center vertex (deepest point)
    vertices.append([0, 0, -depth])

    # Create concentric rings
    rings = 6
    for ring in range(1, rings + 1):
        ring_radius = radius * ring / rings
        # Depth follows a smooth curve (parabolic)
        ring_depth = depth * (1 - (ring / rings) ** 2)

        for i in range(segments):
            angle = 2 * math.pi * i / segments
            x = ring_radius * math.cos(angle)
            y = ring_radius * math.sin(angle)
            z = -ring_depth
            vertices.append([x, y, z])

    # Create faces
    # Center to first ring
    for i in range(segments):
        next_i = (i + 1) % segments
        faces.append([0, 1 + i, 1 + next_i])

    # Between rings
    for ring in range(rings - 1):
        ring_start = 1 + ring * segments
        next_ring_start = 1 + (ring + 1) * segments

        for i in range(segments):
            next_i = (i + 1) % segments

            curr = ring_start + i
            curr_next = ring_start + next_i
            outer = next_ring_start + i
            outer_next = next_ring_start + next_i

            faces.append([curr, outer, curr_next])
            faces.append([curr_next, outer, outer_next])

    # Add a rim (flat edge) to blend with surface
    rim_ring_start = 1 + (rings - 1) * segments
    outer_rim_start = len(vertices)

    for i in range(segments):
        angle = 2 * math.pi * i / segments
        x = radius * 1.1 * math.cos(angle)  # Slightly larger
        y = radius * 1.1 * math.sin(angle)
        z = 0  # Flat at surface level
        vertices.append([x, y, z])

    # Connect last ring to rim
    for i in range(segments):
        next_i = (i + 1) % segments

        inner = rim_ring_start + i
        inner_next = rim_ring_start + next_i
        outer = outer_rim_start + i
        outer_next = outer_rim_start + next_i

        faces.append([inner, outer, inner_next])
        faces.append([inner_next, outer, outer_next])

    return np.array(vertices), np.array(faces)


def create_elongated_dent(length, width, depth, segments=20):
    """
    Create an elongated dent (like a crease or impact mark).
    """
    vertices = []
    faces = []

    # Create a grid of vertices
    length_segments = segments
    width_segments = max(8, segments // 2)

    for j in range(width_segments + 1):
        for i in range(length_segments + 1):
            # Position along length and width
            x = -length/2 + length * i / length_segments
            y = -width/2 + width * j / width_segments

            # Distance from center (normalized)
            dx = x / (length/2) if length > 0 else 0
            dy = y / (width/2) if width > 0 else 0
            dist = math.sqrt(dx*dx + dy*dy)

            # Depth follows smooth curve
            if dist < 1:
                z = -depth * (1 - dist**2) * math.cos(dist * math.pi / 2)
            else:
                z = 0

            vertices.append([x, y, z])

    # Create faces
    for j in range(width_segments):
        for i in range(length_segments):
            curr = j * (length_segments + 1) + i
            next_i = curr + 1
            next_j = curr + (length_segments + 1)
            next_ij = next_j + 1

            faces.append([curr, next_j, next_i])
            faces.append([next_i, next_j, next_ij])

    return np.array(vertices), np.array(faces)


def save_mesh(vertices, faces, output_path):
    """Save vertices and faces as STL mesh."""
    stl_mesh = mesh.Mesh(np.zeros(faces.shape[0], dtype=mesh.Mesh.dtype))
    for i, face in enumerate(faces):
        for j in range(3):
            stl_mesh.vectors[i][j] = vertices[face[j]]

    stl_mesh.save(output_path)
    print(f"Saved mesh to {output_path}")


def main():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    output_dir = os.path.join(script_dir, "models", "can_dented", "meshes")
    os.makedirs(output_dir, exist_ok=True)

    # Generate circular dent for top of can
    # Size: ~10mm radius, 3mm deep
    vertices, faces = create_concave_disc(radius=0.010, depth=0.003, segments=24)
    save_mesh(vertices, faces, os.path.join(output_dir, "dent_top.stl"))

    # Generate smaller circular dent
    vertices, faces = create_concave_disc(radius=0.007, depth=0.002, segments=20)
    save_mesh(vertices, faces, os.path.join(output_dir, "dent_top_small.stl"))

    # Generate elongated dent for side of can
    vertices, faces = create_elongated_dent(length=0.020, width=0.012, depth=0.004, segments=20)
    save_mesh(vertices, faces, os.path.join(output_dir, "dent_side.stl"))

    print("\nGenerated dent meshes:")
    print("  - dent_top.stl (10mm radius circular dent)")
    print("  - dent_top_small.stl (7mm radius circular dent)")
    print("  - dent_side.stl (20x12mm elongated dent)")
    print("\nUpdate the can_dented model.sdf to use these meshes.")


if __name__ == "__main__":
    main()
