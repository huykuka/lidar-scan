# Use the official Ubuntu image as the base
FROM ubuntu:22.04

# Set ROS_VERSION environment variable
ENV ROS_VERSION=0

# Avoid prompts from apt
ENV DEBIAN_FRONTEND=noninteractive

# Update and install required packages
RUN apt-get update && apt-get install -y \
    git \
    build-essential \
    cmake \
    gdb \
    ninja-build \
    && rm -rf /var/lib/apt/lists/*

# Clone and build sick_scan_xd
RUN git clone -b master https://github.com/SICKAG/sick_scan_xd.git /workspace/sick_scan_xd \
    && mkdir -p /workspace/build \
    && cd /workspace/build \
    && export ROS_VERSION=0 \
    && cmake -DROS_VERSION=0 -DLDMRS=0 -G "Unix Makefiles" ../sick_scan_xd \
    && make -j4 \
    && make -j4 install \
    && rm -rf /workspace/build/*

# Set the working directory inside the container
WORKDIR /workspace

# Default command to keep the container running
CMD ["bash"]
