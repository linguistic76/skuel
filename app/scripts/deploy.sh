#!/usr/bin/env bash
# SKUEL droplet deploy — rsync the working tree over SSH, rebuild, health-gate.
# =============================================================================
# One-shot push deploy for the app+Caddy droplet stack
# (docker-compose.production.yml). No CI/CD dependency: what you have locally
# is what ships.
#
# Steps:
#   1. rsync working tree -> $REMOTE_DIR (excludes via app/.deployignore;
#      excluded paths are also protected from deletion, so the droplet-side
#      .env.production and logs/ survive)
#   2. [--content] rsync the content vault -> /opt/skuel/content-vault/
#   3. remote: stash current skuel-app:latest as skuel-app:predeploy, then
#      compose build && up -d
#   4. health gate: poll http://127.0.0.1:5001/health/ready over SSH for up to
#      ~2 min (readiness covers an AuraDB Free instance waking from pause).
#      PASS promotes predeploy -> skuel-app:rollback (the rollback tag only
#      ever advances past a green gate, so re-running a failed deploy can
#      never clobber the last known-good image). Failure exits non-zero and
#      prints rollback instructions — NO auto-rollback; rolling back is a
#      deliberate human call.
#   5. [--content] after the gate: content-vault sync inside the container
#
# Config (env vars):
#   SKUEL_DROPLET_SSH   ssh destination (default: skuel-droplet — an ssh_config
#                       Host alias carrying user/IP/key)
#   INGESTION_PATH      local content-vault source for --content
#                       (default: $HOME/0bsidian/0vault)
#
# Flags:
#   --content   also sync the content vault + run in-container vault sync
#   --dry-run   print every command instead of executing (rsync runs with -n)
#
# First-deploy prerequisites (droplet side): Docker + compose plugin,
# /opt/skuel/secrets.env (0600), $REMOTE_DIR/.env.production — see
# .env.production.example.

set -euo pipefail

# Colors (matched to ./dev)
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

DROPLET_SSH="${SKUEL_DROPLET_SSH:-skuel-droplet}"
REMOTE_DIR="/opt/skuel/app"
CONTENT_SRC="${INGESTION_PATH:-$HOME/0bsidian/0vault}"
COMPOSE="docker compose -f docker-compose.production.yml"
HEALTH_URL="http://127.0.0.1:5001/health/ready"
HEALTH_ATTEMPTS=24 # x 5s = ~2 min (covers AuraDB Free wake-from-pause)
SKUEL_UID=10001    # container user — pinned in Dockerfile.production

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

SYNC_CONTENT=0
DRY_RUN=0
for arg in "$@"; do
  case "$arg" in
    --content) SYNC_CONTENT=1 ;;
    --dry-run) DRY_RUN=1 ;;
    *)
      echo -e "${RED}Unknown flag: $arg${NC} (supported: --content --dry-run)" >&2
      exit 2
      ;;
  esac
done

# run <cmd...> — execute, or just echo under --dry-run.
run() {
  if [ "$DRY_RUN" -eq 1 ]; then
    echo -e "${YELLOW}[dry-run]${NC} $*"
  else
    "$@"
  fi
}

# remote <script> — run a snippet on the droplet (or echo it under --dry-run).
remote() {
  if [ "$DRY_RUN" -eq 1 ]; then
    echo -e "${YELLOW}[dry-run] ssh $DROPLET_SSH:${NC} $1"
  else
    ssh "$DROPLET_SSH" "$1"
  fi
}

print_rollback_instructions() {
  echo -e "${RED}Deploy FAILED health gate.${NC}" >&2
  echo -e "${RED}skuel-app:rollback holds the last image that PASSED a gate (absent on a first deploy).${NC}" >&2
  echo -e "${YELLOW}To roll back (deliberate human call — no auto-rollback):${NC}" >&2
  echo "  ssh $DROPLET_SSH" >&2
  echo "  cd $REMOTE_DIR" >&2
  echo "  docker tag skuel-app:rollback skuel-app:latest && $COMPOSE up -d" >&2
  echo "Inspect first: $COMPOSE logs --tail 200 skuel-app" >&2
}

cd "$APP_DIR"

echo -e "${GREEN}==> Deploying SKUEL to $DROPLET_SSH:$REMOTE_DIR${NC}"

# --- 1. Sync working tree ----------------------------------------------------
# --delete keeps the droplet an exact mirror; .deployignore paths are excluded
# from BOTH transfer and deletion (no --delete-excluded — that would destroy
# the droplet-side .env.production).
RSYNC_FLAGS=(-az --info=stats1 --delete --exclude-from="$APP_DIR/.deployignore")

echo -e "${YELLOW}Syncing working tree...${NC}"
remote "mkdir -p $REMOTE_DIR /opt/skuel/content-vault /opt/skuel/personal-vault"
run rsync "${RSYNC_FLAGS[@]}" "$APP_DIR/" "$DROPLET_SSH:$REMOTE_DIR/"

# Writable bind mounts must belong to the container user: a bind mount hides
# the image's chowned directory, so ownership is a host-side concern. The
# content vault stays root-owned (mounted :ro; rsync'd files are world-
# readable), but personal-vault writebacks and log files are written as
# $SKUEL_UID and would EACCES on a root-owned directory.
remote "mkdir -p $REMOTE_DIR/logs \
  && chown -R $SKUEL_UID:$SKUEL_UID /opt/skuel/personal-vault $REMOTE_DIR/logs"

# --- 2. Sync content vault (--content) ---------------------------------------
if [ "$SYNC_CONTENT" -eq 1 ]; then
  if [ ! -d "$CONTENT_SRC" ]; then
    echo -e "${RED}Content vault not found: $CONTENT_SRC${NC} (set INGESTION_PATH)" >&2
    exit 2
  fi
  echo -e "${YELLOW}Syncing content vault from $CONTENT_SRC...${NC}"
  # Resources/ excluded: binary attachments, not ingestible curriculum.
  run rsync "${RSYNC_FLAGS[@]}" --exclude 'Resources/' \
    "$CONTENT_SRC/" "$DROPLET_SSH:/opt/skuel/content-vault/"
fi

# --- 3. Stash previous image + build + up ------------------------------------
echo -e "${YELLOW}Building and starting containers...${NC}"
# Stash the currently-running image as :predeploy BEFORE build replaces
# :latest. It is promoted to :rollback only after the health gate passes —
# never here — so re-running a failed deploy cannot overwrite the last
# known-good rollback image with a broken one.
remote "cd $REMOTE_DIR \
  && { docker image inspect skuel-app:latest >/dev/null 2>&1 \
       && docker tag skuel-app:latest skuel-app:predeploy \
       || echo 'No existing skuel-app:latest — nothing to stash (first deploy?)'; } \
  && $COMPOSE build \
  && $COMPOSE up -d"

# --- 4. Health gate -----------------------------------------------------------
# /health/ready returns 503 until Neo4j is reachable, so passing it means the
# app booted AND AuraDB answered (including wake-from-pause).
echo -e "${YELLOW}Health gate: polling $HEALTH_URL (up to $((HEALTH_ATTEMPTS * 5))s)...${NC}"
if [ "$DRY_RUN" -eq 1 ]; then
  echo -e "${YELLOW}[dry-run] ssh $DROPLET_SSH:${NC} curl -fsS $HEALTH_URL (poll ${HEALTH_ATTEMPTS}x5s)"
else
  healthy=0
  for attempt in $(seq 1 "$HEALTH_ATTEMPTS"); do
    if ssh "$DROPLET_SSH" "curl -fsS -o /dev/null $HEALTH_URL"; then
      healthy=1
      break
    fi
    echo "  not ready yet (attempt $attempt/$HEALTH_ATTEMPTS)..."
    sleep 5
  done
  if [ "$healthy" -ne 1 ]; then
    print_rollback_instructions
    exit 1
  fi
  echo -e "${GREEN}✓ /health/ready is 200 — app is serving${NC}"
fi

# Gate passed: the image that was serving before this deploy is proven
# replaceable — promote it to :rollback and drop the stash tag.
remote "docker image inspect skuel-app:predeploy >/dev/null 2>&1 \
  && docker tag skuel-app:predeploy skuel-app:rollback \
  && docker rmi skuel-app:predeploy >/dev/null \
  || true"

# --- 5. In-container content-vault sync (--content, after the gate) ----------
if [ "$SYNC_CONTENT" -eq 1 ]; then
  echo -e "${YELLOW}Ingesting content vault (one-shot in-container sync)...${NC}"
  remote "cd $REMOTE_DIR && $COMPOSE exec -T skuel-app python scripts/vault_bridge_sync.py --vault content"
fi

echo -e "${GREEN}✓ Deploy complete${NC}"
