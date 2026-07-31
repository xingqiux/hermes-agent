#!/usr/bin/env bash
set -Eeuo pipefail

IMAGE_REF=${1:?usage: deploy.sh IMAGE@DIGEST REVISION}
REVISION=${2:?usage: deploy.sh IMAGE@DIGEST REVISION}
DEPLOY_DIR=${DEPLOY_DIR:-/home/ziyu/services/hermes-deploy}
DATA_DIR=${HERMES_DATA_DIR:-/home/ziyu/services/hermes-agent-data}
COMPOSE_FILE=${COMPOSE_FILE:-$DEPLOY_DIR/docker-compose.yml}
NATIVE_DIR=${NATIVE_DIR:-/home/ziyu/services/hermes-agent-native}
CANARY_PORT=${CANARY_PORT:-19119}
DASHBOARD_PORT=${DASHBOARD_PORT:-9119}
REQUIRED_PLATFORMS=${REQUIRED_PLATFORMS:-telegram,weixin,napcat}
NATIVE_UNITS=(hermes-native-gateway-default.service hermes-native-dashboard.service)
CANDIDATE_IMAGE=xkqq/hermes-agent:candidate
ROLLBACK_IMAGE=xkqq/hermes-agent:rollback
CANARY_CONTAINER=hermes-dashboard-canary
had_native=false
had_compose=false
switched=false

mkdir -p "$DEPLOY_DIR"
exec 9>"$DEPLOY_DIR/deploy.lock"
flock -n 9 || { echo 'Another Hermes deployment is running' >&2; exit 1; }

log() { printf '[deploy] %s\n' "$*"; }
wait_http() {
  local url=$1 attempts=${2:-60}
  for ((i=1; i<=attempts; i++)); do
    curl -fsS --max-time 3 "$url" >/dev/null && return 0
    sleep 2
  done
  return 1
}
clear_drain() { rm -f "$DATA_DIR/.drain_request.json"; }

rollback() {
  local code=$?
  if (( code == 0 )); then return; fi
  trap - ERR
  log "Deployment failed; rolling back revision $REVISION"
  docker rm -f "$CANARY_CONTAINER" >/dev/null 2>&1 || true
  clear_drain
  if [[ "$switched" == true ]]; then
    HERMES_IMAGE="$CANDIDATE_IMAGE" docker compose -f "$COMPOSE_FILE" down --remove-orphans || true
  fi
  if [[ "$had_compose" == true ]] && docker image inspect "$ROLLBACK_IMAGE" >/dev/null 2>&1; then
    docker tag "$ROLLBACK_IMAGE" "$CANDIDATE_IMAGE"
    HERMES_IMAGE="$CANDIDATE_IMAGE" docker compose -f "$COMPOSE_FILE" up -d --force-recreate
  elif [[ "$had_native" == true ]]; then
    systemctl --user start "${NATIVE_UNITS[@]}" || true
  fi
  exit "$code"
}
trap rollback ERR

for command in docker curl flock python3 systemctl; do command -v "$command" >/dev/null; done
[[ -f "$COMPOSE_FILE" && -d "$DATA_DIR" ]]

for unit in "${NATIVE_UNITS[@]}"; do
  if systemctl --user is-active --quiet "$unit"; then had_native=true; fi
done
if docker inspect hermes >/dev/null 2>&1; then
  had_compose=true
  old_image=$(docker inspect --format '{{.Image}}' hermes)
  docker tag "$old_image" "$ROLLBACK_IMAGE"
fi
if [[ "$had_native" == true && "$had_compose" == true ]]; then
  echo 'Both native and Docker Hermes services are active; refusing an ambiguous deployment' >&2
  exit 1
fi

log "Pulling immutable image $IMAGE_REF"
docker pull "$IMAGE_REF"
docker tag "$IMAGE_REF" "$CANDIDATE_IMAGE"

canary_data=$(mktemp -d "$DEPLOY_DIR/canary.XXXXXX")
trap 'rm -rf "$canary_data"' EXIT
docker rm -f "$CANARY_CONTAINER" >/dev/null 2>&1 || true
docker run -d --name "$CANARY_CONTAINER" --network host \
  -v "$canary_data:/opt/data" \
  -e "HERMES_UID=$(id -u)" -e "HERMES_GID=$(id -g)" \
  -e HERMES_SKIP_PROFILE_RECONCILE=1 \
  "$CANDIDATE_IMAGE" dashboard --host 127.0.0.1 --port "$CANARY_PORT" --no-open --skip-build >/dev/null
wait_http "http://127.0.0.1:${CANARY_PORT}/api/status" 60
docker rm -f "$CANARY_CONTAINER" >/dev/null
log 'Isolated Dashboard canary passed'

if [[ "$had_compose" == true ]]; then
  docker exec hermes python -c \
    'from gateway.drain_control import write_drain_request; write_drain_request(principal="xkqq-deploy", suppress_notification=True)'
elif [[ "$had_native" == true ]]; then
  HERMES_HOME="$DATA_DIR" "$NATIVE_DIR/.venv/bin/python" -c \
    'from gateway.drain_control import write_drain_request; write_drain_request(principal="xkqq-deploy", suppress_notification=True)'
fi

if [[ "$had_compose" == true || "$had_native" == true ]]; then
  log 'Waiting for the live Gateway to drain'
  DATA_DIR="$DATA_DIR" python3 - <<'PY'
import json, os, time
from pathlib import Path

path = Path(os.environ["DATA_DIR"]) / "gateway_state.json"
for _ in range(240):
    try:
        state = json.loads(path.read_text())
    except (OSError, ValueError):
        state = {}
    if state.get("gateway_state") == "draining" and int(state.get("active_agents") or 0) == 0:
        break
    time.sleep(1)
else:
    raise SystemExit("Gateway did not drain within 240 seconds")
PY
fi

[[ "$had_native" == false ]] || systemctl --user stop "${NATIVE_UNITS[@]}"
[[ "$had_compose" == false ]] || HERMES_IMAGE="$CANDIDATE_IMAGE" docker compose -f "$COMPOSE_FILE" down --remove-orphans
clear_drain
switched=true
HERMES_IMAGE="$CANDIDATE_IMAGE" docker compose -f "$COMPOSE_FILE" up -d --force-recreate --remove-orphans
wait_http "http://127.0.0.1:${DASHBOARD_PORT}/api/status" 60

DATA_DIR="$DATA_DIR" REQUIRED_PLATFORMS="$REQUIRED_PLATFORMS" python3 - <<'PY'
import json, os, time
from pathlib import Path

path = Path(os.environ["DATA_DIR"]) / "gateway_state.json"
required = {item for item in os.environ["REQUIRED_PLATFORMS"].split(",") if item}
for _ in range(180):
    try:
        state = json.loads(path.read_text())
    except (OSError, ValueError):
        state = {}
    platforms = state.get("platforms") or {}
    connected = {name for name, value in platforms.items() if value.get("state") == "connected"}
    if state.get("gateway_state") == "running" and required <= connected:
        break
    time.sleep(1)
else:
    raise SystemExit(f"Gateway verification failed; required={sorted(required)} state={state}")
PY

trap - ERR
rm -f "$DATA_DIR/.drain_request.json"
docker image rm "$ROLLBACK_IMAGE" >/dev/null 2>&1 || true
current_image_id=$(docker image inspect --format '{{.Id}}' "$CANDIDATE_IMAGE")
while IFS= read -r image_id; do
  if [[ -n "$image_id" && "$image_id" != "$current_image_id" ]]; then
    docker image rm "$image_id" >/dev/null 2>&1 || true
  fi
done < <(docker image ls --no-trunc --filter "reference=${IMAGE_REF%@*}*" --format '{{.ID}}')
docker image prune -f >/dev/null
printf '%s\n' "$REVISION" > "$DEPLOY_DIR/current-revision"
log "Revision $REVISION is healthy"
