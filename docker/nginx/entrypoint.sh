#!/bin/sh
# Render the nginx config template, substituting BACKEND_HOST and BACKEND_PORT.
# Defaults to 127.0.0.1:8005 (host-network deployment where both containers
# share the host network stack). Override via environment variables when using
# Docker bridge networking.
set -e

: "${BACKEND_HOST:=host.docker.internal}"
: "${BACKEND_PORT:=8004}"
export BACKEND_HOST BACKEND_PORT

envsubst '${BACKEND_HOST} ${BACKEND_PORT}' \
  < /etc/nginx/conf.d/default.conf.template \
  > /etc/nginx/conf.d/default.conf

exec nginx -g "daemon off;"
