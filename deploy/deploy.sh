#!/bin/bash

timestamp() {
  date +"%Y%m%d%H%M%S" # current time
}

# ------------------------------
# Variables
# ------------------------------
APP_ENV=amd
DOCKERFILE="docker/Dockerfile"
DOCKER_REGISTRY="artifactory.sick.com"
DOCKER_REPO_NAME="ssc07-eh-docker-local/lidar-studio-$APP_ENV"
TAG_LATEST="$DOCKER_REPO_NAME:latest"

docker image prune --force
docker container prune --force
docker network prune --force

# ------------------------------
# Build, tag and push the image
# ------------------------------
docker build -f $DOCKERFILE . -t "$TAG_LATEST"

# Tag the image
docker tag "$TAG_LATEST" "$DOCKER_REGISTRY/$TAG_LATEST"
#
## Push the image to the registry
#docker push "$DOCKER_REGISTRY/$TAG_LATEST"
