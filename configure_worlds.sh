#!/bin/bash
# Configure world files based on LOCAL_MODE

if [ "$LOCAL_MODE" = "local" ]; then
    echo "Local mode detected: Disabling shadows for CPU rendering..."

    # Disable shadows in all world files
    for world_file in /opt/worlds/*.sdf; do
        if [ -f "$world_file" ]; then
            sed -i 's/<shadows>true<\/shadows>/<shadows>false<\/shadows>/g' "$world_file"
            sed -i 's/<cast_shadows>true<\/cast_shadows>/<cast_shadows>false<\/cast_shadows>/g' "$world_file"
            echo "  Configured: $world_file"
        fi
    done
else
    echo "Cloud mode (GPU): Shadows enabled"
fi
