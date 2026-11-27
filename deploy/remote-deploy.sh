#!/bin/bash
# Get Well OCR: runs ON the EC2 instance (as root, sent by the GitHub workflow via SSM).
# Switches the API to a new image, checks /health and rolls back if the new version does not come up.
#
# Input (environment):
#   IMAGE       full image URI, e.g. 363183905530.dkr.ecr.eu-north-1.amazonaws.com/get-well-ocr:abc1234
#   AWS_REGION  region of the ECR registry
#
# Works with both setups:
#   - "gwo" systemd service from ec2-user-data.sh  -> sets IMAGE_TAG in /etc/gwo/gwo.conf, restarts the service
#   - plain container "gwo-api" (docker run)       -> replaces the container
set -euo pipefail

: "${IMAGE:?IMAGE not set}"
: "${AWS_REGION:?AWS_REGION not set}"
REGISTRY="${IMAGE%%/*}"
TAG="${IMAGE##*:}"
CONTAINER=gwo-api
PORT=8000

log() { echo "[deploy] $*"; }

healthy() {
  # Up to 3 minutes: pulling the image and starting uvicorn takes a moment
  for _ in $(seq 1 36); do
    if curl -fsS "http://localhost:$PORT/health" >/dev/null 2>&1; then return 0; fi
    sleep 5
  done
  return 1
}

log "logging in to $REGISTRY"
aws ecr get-login-password --region "$AWS_REGION" | docker login --username AWS --password-stdin "$REGISTRY"
log "pulling $IMAGE"
docker pull "$IMAGE"

if [ -f /etc/systemd/system/gwo.service ] && [ -f /etc/gwo/gwo.conf ]; then
  # ---------- systemd setup ----------
  OLD_TAG=$(sed -n 's/^IMAGE_TAG=//p' /etc/gwo/gwo.conf)
  log "systemd service gwo: $OLD_TAG -> $TAG"
  sed -i "s/^IMAGE_TAG=.*/IMAGE_TAG=$TAG/" /etc/gwo/gwo.conf
  systemctl restart gwo
  if healthy; then
    log "healthy on $TAG"
  else
    log "NOT healthy on $TAG, rolling back to $OLD_TAG"
    journalctl -u gwo -n 50 --no-pager || true
    sed -i "s/^IMAGE_TAG=.*/IMAGE_TAG=$OLD_TAG/" /etc/gwo/gwo.conf
    systemctl restart gwo
    healthy && log "rollback healthy" || log "rollback also unhealthy"
    exit 1
  fi
else
  # ---------- plain container setup ----------
  OLD_IMAGE=$(docker inspect --format '{{.Config.Image}}' "$CONTAINER" 2>/dev/null || true)
  log "container $CONTAINER: ${OLD_IMAGE:-none} -> $IMAGE"

  ENV_ARGS=()
  [ -f /etc/gwo/env ] && ENV_ARGS=(--env-file /etc/gwo/env)

  run() {
    docker rm -f "$CONTAINER" >/dev/null 2>&1 || true
    docker run -d --name "$CONTAINER" --restart unless-stopped \
      -p "$PORT":8000 "${ENV_ARGS[@]}" \
      -v gwo-private:/app/data/private -v gwo-outputs:/app/outputs -v gwo-cache:/app/cache \
      "$1" >/dev/null
  }

  run "$IMAGE"
  if healthy; then
    log "healthy on $IMAGE"
  else
    log "NOT healthy on $IMAGE"
    docker logs --tail 50 "$CONTAINER" || true
    if [ -n "$OLD_IMAGE" ]; then
      log "rolling back to $OLD_IMAGE"
      run "$OLD_IMAGE"
      healthy && log "rollback healthy" || log "rollback also unhealthy"
    fi
    exit 1
  fi
fi

# Free disk space: unused images older than 3 days (older versions can be pulled again from ECR)
docker image prune -af --filter "until=72h" >/dev/null || true
log "done"
