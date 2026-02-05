# Can Inspection Simulation

A Gazebo-based simulation of an industrial quality inspection station. Cans move along a conveyor belt past an overhead camera. Approximately 1 in 5 cans have visible defects (dents).

This simulation is designed for the [Viam Stationary Vision tutorial](https://docs.viam.com/tutorials/stationary-vision/), demonstrating computer vision-based defect detection.

## Quick Start

### Prerequisites

- Docker installed and running

### Build and Run

**Mac/Linux:**

```bash
# Build the Docker image
docker build -t can-inspection-sim .

# Run Station 1
docker run --name inspection-station1 -d \
  -p 8080:8080 -p 8081:8081 -p 8443:8443 \
  can-inspection-sim

# Open the web viewer
open http://localhost:8081
```

**Windows (PowerShell):**

```powershell
# Build the Docker image
docker build -t can-inspection-sim .

# Run Station 1
docker run --name inspection-station1 -d `
  -p 8080:8080 -p 8081:8081 -p 8443:8443 `
  can-inspection-sim

# Open the web viewer
Start-Process "http://localhost:8081"
```

### Running with Viam

To connect the simulation to Viam, mount your machine configuration:

```bash
docker run --name inspection-station1 -d \
  -p 8080:8080 -p 8081:8081 -p 8443:8443 \
  -v /path/to/your-viam-config.json:/etc/viam.json \
  can-inspection-sim
```

## Two Stations for Fleet Tutorial

Station 2 has a distinct visual style (yellow rails, orange reject bin, blue output chute) and different camera IDs for demonstrating fragments and fleet management.

**Run Station 2:**

```bash
docker run --name inspection-station2 -d \
  -p 8080:8080 -p 8081:8081 -p 8443:8443 \
  -e STATION=2 \
  can-inspection-sim
```

| Station | Camera ID | Visual Style |
|---------|-----------|--------------|
| Station 1 | `/inspection_camera` | Gray rails, red reject bin, green chute |
| Station 2 | `/station_2_camera` | Yellow rails, orange reject bin, blue chute |

## What's Included

- **Conveyor belt** with cans moving continuously
- **Overhead inspection camera** (640x480, 15fps)
- **Overview camera** - elevated side view of the work cell
- **Good cans** - silver aluminum, undamaged
- **Dented cans** (~1 in 5) - visible damage marks on top
- **Air jet rejector** - pneumatic nozzle (visual only)
- **Reject bin** and **output chute** (visual only)

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                      Docker Container                            │
│                                                                  │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────────┐  │
│  │   gz-sim     │    │ can_spawner  │    │   web_viewer     │  │
│  │              │    │    .py       │    │      .py         │  │
│  │  - Physics   │    │              │    │                  │  │
│  │  - Rendering │    │  - Spawns    │    │  - Subscribes    │  │
│  │  - Sensors   │    │    can pool  │    │    to cameras    │  │
│  │              │    │  - Moves     │    │  - Serves HTTP   │  │
│  │              │    │    cans      │    │    on :8081      │  │
│  │              │    │  - Recycles  │    │                  │  │
│  │              │    │    at end    │    │                  │  │
│  └──────┬───────┘    └──────┬───────┘    └────────┬─────────┘  │
│         │                   │                      │            │
│         └───────── gz-transport ──────────────────┘            │
│                    (topics & services)                          │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼ Port 8081
                    ┌──────────────────┐
                    │  User's Browser  │
                    │  (live camera)   │
                    └──────────────────┘
```

## Project Structure

```
can-inspection-simulation/
├── Dockerfile                    # Container build
├── s6-rc.d/                     # s6-overlay service definitions
├── can_spawner.py               # Conveyor belt controller
├── web_viewer.py                # Browser camera viewer
├── worlds/
│   ├── cylinder_inspection.sdf     # Station 1 world
│   └── cylinder_inspection_2.sdf   # Station 2 world
├── models/
│   ├── can_good/                # Undamaged can model
│   └── can_dented/              # Damaged can model
├── capture_training_data.py     # ML training data utility
└── CAN-INSPECTION-SIMULATION.md # Technical reference
```

## Resource Usage

The simulation uses software rendering (no GPU passthrough in Docker), which results in high CPU usage. This is expected behavior. Shadows and high frame rates have been disabled to reduce load.

## Stopping the Simulation

```bash
docker stop inspection-station1 && docker rm inspection-station1
```

## Technical Details

See [CAN-INSPECTION-SIMULATION.md](./CAN-INSPECTION-SIMULATION.md) for detailed technical documentation including camera specifications, conveyor parameters, and Gazebo service information.

## License

Apache 2.0
