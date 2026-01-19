#!/usr/bin/env bash
set -euo pipefail

FAASD_COMPOSE_PATH="${1:-/var/lib/faasd/docker-compose.yaml}"

if [[ ! -f "$FAASD_COMPOSE_PATH" ]]; then
  echo "Faasd compose file not found: $FAASD_COMPOSE_PATH" >&2
  exit 1
fi

if ! command -v sudo >/dev/null 2>&1; then
  echo "sudo is required to edit $FAASD_COMPOSE_PATH and restart faasd." >&2
  exit 1
fi

echo "Disabling basic_auth in $FAASD_COMPOSE_PATH..."
sudo sed -i'' -e 's/basic_auth=true/basic_auth=false/g' "$FAASD_COMPOSE_PATH"

echo "Restarting faasd..."
sudo systemctl restart faasd

echo "Done."
