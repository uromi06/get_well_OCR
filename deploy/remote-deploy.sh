#!/bin/bash
# Get Well OCR: runs ON the EC2 instance (as root, sent by the GitHub workflow via SSM).
# Switches the API and the Streamlit app to a new image, checks both and rolls back if one does not come up.
#
# Input (environment):
#   IMAGE       full image URI, e.g. 363183905530.dkr.ecr.eu-north-1.amazonaws.com/get-well-ocr:abc1234
#   AWS_REGION  region of the ECR registry
#
# What runs afterwards:
#   API (port 8000)        "gwo" systemd service from ec2-user-data.sh if installed, else container "gwo-api"
#   Streamlit (port 8501)  container "gwo-app"
#
# Settings for both come from /etc/gwo/env if it exists (root only, chmod 600), e.g.
#   APP_USERNAME=...   APP_PASSWORD=...   (login of the Streamlit app, required by the app)
#   OCR_ENGINE=tesseract   AZURE_DI_ENDPOINT=...   AZURE_DI_KEY=...
set -euo pipefail

: "${IMAGE:?IMAGE not set}"
: "${AWS_REGION:?AWS_REGION not set}"
REGISTRY="${IMAGE%%/*}"
TAG="${IMAGE##*:}"
API=gwo-api
API_PORT=8000
APP=gwo-app
APP_PORT=8501
VOLUMES=(-v gwo-private:/app/data/private -v gwo-outputs:/app/outputs -v gwo-cache:/app/cache)
ENV_ARGS=()
[ -f /etc/gwo/env ] && ENV_ARGS=(--env-file /etc/gwo/env)

log() { echo "[deploy] $*"; }

# Up to 3 minutes: starting uvicorn / streamlit takes a moment
wait_for() {
  for _ in $(seq 1 36); do
    if curl -fsS "$1" >/dev/null 2>&1; then return 0; fi
    sleep 5
  done
  return 1
}
api_healthy() { wait_for "http://localhost:$API_PORT/health"; }
app_healthy() { wait_for "http://localhost:$APP_PORT/_stcore/health"; }

running_image() { docker inspect --format '{{.Config.Image}}' "$1" 2>/dev/null || true; }

start_api() {
  docker rm -f "$API" >/dev/null 2>&1 || true
  docker run -d --name "$API" --restart unless-stopped \
    -p "$API_PORT":8000 "${ENV_ARGS[@]}" "${VOLUMES[@]}" \
    "$1" >/dev/null
}

start_app() {
  docker rm -f "$APP" >/dev/null 2>&1 || true
  docker run -d --name "$APP" --restart unless-stopped \
    -p "$APP_PORT":8501 "${ENV_ARGS[@]}" "${VOLUMES[@]}" \
    "$1" streamlit run app.py --server.port 8501 --server.address 0.0.0.0 --server.headless true >/dev/null
}

log "logging in to $REGISTRY"
aws ecr get-login-password --region "$AWS_REGION" | docker login --username AWS --password-stdin "$REGISTRY"
log "pulling $IMAGE"
docker pull "$IMAGE"

# ---------- API ----------
if [ -f /etc/systemd/system/gwo.service ] && [ -f /etc/gwo/gwo.conf ]; then
  OLD_TAG=$(sed -n 's/^IMAGE_TAG=//p' /etc/gwo/gwo.conf)
  log "API (systemd service gwo): $OLD_TAG -> $TAG"
  sed -i "s/^IMAGE_TAG=.*/IMAGE_TAG=$TAG/" /etc/gwo/gwo.conf
  systemctl restart gwo
  if api_healthy; then
    log "API healthy on $TAG"
  else
    log "API NOT healthy on $TAG, rolling back to $OLD_TAG"
    journalctl -u gwo -n 50 --no-pager || true
    sed -i "s/^IMAGE_TAG=.*/IMAGE_TAG=$OLD_TAG/" /etc/gwo/gwo.conf
    systemctl restart gwo
    api_healthy && log "API rollback healthy" || log "API rollback also unhealthy"
    exit 1
  fi
else
  OLD_API=$(running_image "$API")
  log "API (container $API): ${OLD_API:-none} -> $IMAGE"
  start_api "$IMAGE"
  if api_healthy; then
    log "API healthy on $IMAGE"
  else
    log "API NOT healthy on $IMAGE"
    docker logs --tail 50 "$API" || true
    if [ -n "$OLD_API" ]; then
      log "API rolling back to $OLD_API"
      start_api "$OLD_API"
      api_healthy && log "API rollback healthy" || log "API rollback also unhealthy"
    fi
    exit 1
  fi
fi

# ---------- Streamlit app ----------
[ -f /etc/gwo/env ] && grep -q '^APP_PASSWORD=.' /etc/gwo/env \
  || log "WARNING: APP_USERNAME/APP_PASSWORD missing in /etc/gwo/env, the app will only show a login error"
OLD_APP=$(running_image "$APP")
log "app (container $APP): ${OLD_APP:-none} -> $IMAGE"
start_app "$IMAGE"
if app_healthy; then
  log "app healthy on $IMAGE"
else
  log "app NOT healthy on $IMAGE (the API already runs the new version)"
  docker logs --tail 50 "$APP" || true
  if [ -n "$OLD_APP" ]; then
    log "app rolling back to $OLD_APP"
    start_app "$OLD_APP"
    app_healthy && log "app rollback healthy" || log "app rollback also unhealthy"
  fi
  exit 1
fi

# Free disk space: unused images older than 3 days (older versions can be pulled again from ECR)
docker image prune -af --filter "until=72h" >/dev/null || true
log "done"
