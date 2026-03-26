#!/bin/bash

timestamp() {
  date +"%Y%m%d%H%M%S"
}

# ------------------------------
# Variables
# ------------------------------
DOCKERFILE="docker/Dockerfile"
DOCKER_USERNAME="010497"   # <-- change this
DOCKER_REPO_NAME="lidar-studio"
TAG_LATEST="$DOCKER_USERNAME/$DOCKER_REPO_NAME:latest"

# ------------------------------
# Cleanup
# ------------------------------
docker image prune --force
docker container prune --force
docker network prune --force

# ------------------------------
# Login (required)
# ------------------------------
docker login

# ------------------------------
# Build, tag and push
# ------------------------------
docker build -f $DOCKERFILE . -t "$TAG_LATEST"

# Push to Docker Hub
docker push "$TAG_LATEST"