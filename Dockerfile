# Gazebo Harmonic POC for Viam Camera Bridge
FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive
# Required for protobuf compatibility with gz-msgs
ENV PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION=python

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

# Install xvfb for headless rendering (required for camera sensors)
RUN apt-get update && apt-get install -y \
    xvfb \
    mesa-utils \
    libgl1-mesa-glx \
    && rm -rf /var/lib/apt/lists/*

# Install Python and gz-transport bindings
RUN apt-get update && apt-get install -y \
    python3 \
    python3-pip \
    python3-venv \
    python3-gz-transport13 \
    python3-gz-msgs10 \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies for Viam module and web viewer
RUN pip3 install viam-sdk Pillow flask numpy

# Install viam-server AppImage (use --appimage-extract-and-run at runtime to avoid ARM64 SIGBUS bug)
RUN curl -fsSL https://storage.googleapis.com/packages.viam.com/apps/viam-server/viam-server-stable-$(uname -m).AppImage \
    -o /usr/local/bin/viam-server.AppImage \
    && chmod +x /usr/local/bin/viam-server.AppImage

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

# Copy web viewer, spawner, and training capture script
COPY web_viewer.py /opt/web_viewer.py
COPY can_spawner.py /opt/can_spawner.py
COPY capture_training_data.py /opt/capture_training_data.py

# Copy startup scripts
COPY entrypoint.sh /entrypoint.sh
COPY entrypoint_station2.sh /entrypoint_station2.sh
RUN chmod +x /entrypoint.sh /entrypoint_station2.sh

# Expose ports: web viewer (8081), viam-server web (8080), SSH (22), viam-server gRPC (8443)
EXPOSE 8081 8080 22 8443

WORKDIR /opt

ENTRYPOINT ["/entrypoint.sh"]
