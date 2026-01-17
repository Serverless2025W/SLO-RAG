#!/bin/bash
sudo ctr -n openfaas tasks ls

#!/bin/bash

# 1. Get the primary IP address of the WSL instance
HOST_IP=$(hostname -I | awk '{print $1}')

# 2. Fetch OpenFaaS Password (requires sudo read access)
OPENFAAS_PASS=$(sudo cat /var/lib/faasd/secrets/basic-auth-password 2>/dev/null)


echo "=========================================="
echo "      BaaS Services Dashboard Links       "
echo "=========================================="
echo "WSL IP Address: $HOST_IP"
echo ""

# --- OpenFaaS ---
echo "OpenFaaS UI:       http://$HOST_IP:8080/ui/"
echo "  User:            admin"
echo "  Password:        $OPENFAAS_PASS"
echo ""

# --- MinIO ---
# Credentials found in docker-compose.yaml
echo "MinIO Console:     http://$HOST_IP:9001"
echo "  User:            admin"
echo "  Password:        password123" 
echo ""

# --- Redpanda ---
echo "Redpanda Console:  http://$HOST_IP:8888"
echo "  Credentials:     (None by default in dev mode)"
echo ""

# --- Redis Commander ---
echo "Redis Commander:   http://$HOST_IP:8082"
echo "  Credentials:     (None by default)"
echo ""

# --- Prometheus ---
echo "Prometheus:        http://$HOST_IP:9090"
echo "  Credentials:     (None by default)"
echo ""

# --- Qdrant ---
echo "Qdrant Dashboard:  http://$HOST_IP:6333/dashboard"
echo "  Credentials:     (None by default)"
echo ""

echo "=========================================="