# Build arg to control local vs cloud mode (values: "local" or "cloud")
# Default to local for easier local development
ARG BUILD_MODE=local

# Use Ubuntu base for local (CPU-only), NVIDIA base for cloud (GPU)
FROM ubuntu:22.04 AS local
FROM nvidia/opengl:1.2-glvnd-runtime-ubuntu22.04 AS cloud

FROM ${BUILD_MODE} AS base

ENV DEBIAN_FRONTEND=noninteractive
# Required for protobuf compatibility with gz-msgs
ENV PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION=python
# Set LOCAL_MODE env var for runtime (values: "local" or "cloud")
ARG BUILD_MODE
ENV LOCAL_MODE=${BUILD_MODE}

RUN apt-get update && apt-get install -y \
    supervisor \
    && mkdir -p /var/log/supervisor \
    && rm -rf /var/lib/apt/lists/*

# Install Gazebo Harmonic
RUN apt-get update && apt-get install -y \
    curl \
    gnupg \
    lsb-release \
    && curl https://packages.osrfoundation.org/gazebo.gpg --output /usr/share/keyrings/pkgs-osrf-archive-keyring.gpg \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/pkgs-osrf-archive-keyring.gpg] http://packages.osrfoundation.org/gazebo/ubuntu-stable $(lsb_release -cs) main" | tee /etc/apt/sources.list.d/gazebo-stable.list > /dev/null \
    && apt-get update \
    && apt-get install -y gz-harmonic \
    && rm -rf /var/lib/apt/lists/*

# Install rendering dependencies (GPU for cloud, CPU+xvfb for local)
RUN if [ "$BUILD_MODE" = "local" ]; then \
        apt-get update && apt-get install -y \
            xvfb \
            mesa-utils \
            libgl1-mesa-glx \
            && rm -rf /var/lib/apt/lists/*; \
    else \
        apt-get update && apt-get install -y \
            libegl1-mesa \
            libegl1 \
            libgl1-mesa-glx \
            libgl1 \
            libglvnd0 \
            libglx0 \
            libvulkan1 \
            mesa-vulkan-drivers \
            && rm -rf /var/lib/apt/lists/*; \
    fi

# Install Python and gz-transport bindings
RUN apt-get update && apt-get install -y \
    python3 \
    python3-pip \
    python3-venv \
    python3-gz-transport13 \
    python3-gz-msgs10 \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies for Viam module and web viewer
RUN pip3 install viam-sdk Pillow flask numpy psutil requests urllib3

# Install ffmpeg for video streaming support
RUN apt-get update && apt-get install -y \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Install viam-server native binary (stable v0.112.0)
# Use uname -m to get architecture (x86_64 or aarch64)
RUN curl -fsSL https://storage.googleapis.com/packages.viam.com/apps/viam-server/viam-server-v0.112.0-$(uname -m) \
    -o /usr/local/bin/viam-server \
    && chmod +x /usr/local/bin/viam-server

# Install SSH server and sudo
RUN apt-get update && apt-get install -y \
    openssh-server \
    sudo \
    && rm -rf /var/lib/apt/lists/* \
    && mkdir /var/run/sshd

# Create non-root user with sudo access
RUN useradd -m -s /bin/bash viam \
    && echo 'viam:viam' | chpasswd \
    && usermod -aG sudo viam \
    && echo 'viam ALL=(ALL) NOPASSWD:ALL' >> /etc/sudoers

# Configure SSH
RUN sed -i 's/#PasswordAuthentication yes/PasswordAuthentication yes/' /etc/ssh/sshd_config \
    && mkdir -p /home/viam/.ssh \
    && chmod 700 /home/viam/.ssh \
    && chown viam:viam /home/viam/.ssh

# Copy world files and models
COPY worlds/ /opt/worlds/
COPY models/ /opt/models/

# Set Gazebo resource path for custom models
ENV GZ_SIM_RESOURCE_PATH=/opt/models

# Copy configuration script for local/cloud mode
COPY configure_worlds.sh /opt/configure_worlds.sh
RUN chmod +x /opt/configure_worlds.sh

# Copy web viewer, spawner, and training capture script
COPY web_viewer.py /opt/web_viewer.py
COPY templates/ /opt/templates/
COPY static/ /opt/static/
COPY can_spawner.py /opt/can_spawner.py
COPY capture_training_data.py /opt/capture_training_data.py

# Copy supervisord configuration
COPY supervisord.conf /etc/supervisor/conf.d/supervisord.conf

# Expose ports: web viewer (8081), viam-server web (8080), SSH (22), viam-server gRPC (8443)
EXPOSE 8081 8080 22 8443

WORKDIR /opt

# Use supervisord as the entrypoint
CMD ["/usr/bin/supervisord", "-c", "/etc/supervisor/conf.d/supervisord.conf"]
