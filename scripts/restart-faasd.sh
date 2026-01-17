#!/bin/bash
# Restart faasd with updated docker-compose.yaml
# Usage: sudo ./scripts/restart-faasd.sh

set -e

echo "Copying docker-compose.yaml to faasd..."
cp /home/milos/serverless/SLO-RAG/docker-compose.yaml /var/lib/faasd/docker-compose.yaml

echo "Restarting faasd..."
systemctl restart faasd

echo "Waiting for faasd to start..."
sleep 5

echo ""
systemctl status faasd --no-pager
