#!/bin/bash
# Setup script to configure faasd with docker-compose.yaml

set -e

PROJECT_DIR="/root/projects/SLO-RAG"
FAASD_DIR="/var/lib/faasd"

echo "=========================================="
echo "faasd Setup Script for SLO-RAG"
echo "=========================================="
echo ""

# Check if running as root or with sudo
if [ "$EUID" -ne 0 ]; then 
    echo "This script must be run with sudo"
    exit 1
fi

# Step 1: Check if faasd is installed
echo "1. Checking if faasd is installed..."
if ! systemctl list-units --all | grep -q faasd; then
    echo "✗ faasd is not installed"
    echo "  Please install faasd first:"
    echo "    git clone https://github.com/openfaas/faasd --depth=1"
    echo "    cd faasd"
    echo "    ./hack/install.sh"
    exit 1
fi
echo "✓ faasd is installed"
echo ""

# Step 2: Create required directories
echo "2. Creating required directories..."
REQUIRED_DIRS=(
    "$FAASD_DIR/nats"
    "$FAASD_DIR/prometheus"
    "$FAASD_DIR/minio-data"
    "$FAASD_DIR/redis-data"
    "$FAASD_DIR/qdrant-data"
    "$FAASD_DIR/secrets"
)

for dir in "${REQUIRED_DIRS[@]}"; do
    if [ ! -d "$dir" ]; then
        mkdir -p "$dir"
        echo "  Created: $dir"
    else
        echo "  Exists: $dir"
    fi
done
echo "✓ Directories ready"
echo ""

# Step 3: Copy docker-compose.yaml
echo "3. Copying docker-compose.yaml..."
if [ -f "$PROJECT_DIR/docker-compose.yaml" ]; then
    cp "$PROJECT_DIR/docker-compose.yaml" "$FAASD_DIR/docker-compose.yaml"
    echo "✓ docker-compose.yaml copied to $FAASD_DIR/"
else
    echo "✗ docker-compose.yaml not found in $PROJECT_DIR"
    exit 1
fi
echo ""

# Step 4: Copy prometheus.yml if it exists
echo "4. Checking prometheus.yml..."
if [ -f "$PROJECT_DIR/prometheus.yml" ]; then
    cp "$PROJECT_DIR/prometheus.yml" "$FAASD_DIR/prometheus.yml"
    echo "✓ prometheus.yml copied"
else
    echo "⚠ prometheus.yml not found in project"
    # Create a minimal prometheus.yml if it doesn't exist
    if [ ! -f "$FAASD_DIR/prometheus.yml" ]; then
        cat > "$FAASD_DIR/prometheus.yml" << 'EOF'
global:
  scrape_interval: 15s
  evaluation_interval: 15s

scrape_configs:
  - job_name: 'prometheus'
    static_configs:
      - targets: ['localhost:9090']
  - job_name: 'gateway'
    static_configs:
      - targets: ['gateway:8080']
EOF
        echo "  Created minimal prometheus.yml"
    fi
fi
echo ""

# Step 5: Check secrets
echo "5. Checking faasd secrets..."
if [ ! -f "$FAASD_DIR/secrets/basic-auth-password" ]; then
    echo "✗ basic-auth-password not found"
    echo "  Generating new password..."
    head -c 16 /dev/urandom | sha256sum | head -c 32 > "$FAASD_DIR/secrets/basic-auth-password"
    echo "✓ Generated new basic-auth-password"
fi
if [ ! -f "$FAASD_DIR/secrets/basic-auth-user" ]; then
    echo "admin" > "$FAASD_DIR/secrets/basic-auth-user"
    echo "✓ Created basic-auth-user (admin)"
fi
echo "✓ Secrets exist"
echo ""

# Step 6: Set correct permissions
echo "6. Setting permissions..."
chmod 644 "$FAASD_DIR/secrets/basic-auth-password"
chmod 644 "$FAASD_DIR/secrets/basic-auth-user"
chmod 755 "$FAASD_DIR/secrets"
# Set ownership for data directories that containers need to write to
chmod -R 777 "$FAASD_DIR/nats"
chmod -R 777 "$FAASD_DIR/prometheus"
chmod -R 777 "$FAASD_DIR/minio-data"
chmod -R 777 "$FAASD_DIR/redis-data"
chmod -R 777 "$FAASD_DIR/qdrant-data"
# Clear NATS data to prevent permission issues on fresh start
rm -rf "$FAASD_DIR/nats/*" 2>/dev/null
echo "✓ Permissions set"
echo ""

# Step 7: Restart faasd
echo "7. Restarting faasd..."
systemctl restart faasd
echo "✓ faasd restart initiated"
echo ""

# Step 8: Wait for services to start
echo "8. Waiting for services to start..."
sleep 10
echo ""

# Step 9: Check status
echo "9. Checking faasd status..."
if systemctl is-active --quiet faasd; then
    echo "✓ faasd is running"
else
    echo "✗ faasd failed to start"
    echo "  Check logs: journalctl -u faasd -f"
    exit 1
fi
echo ""

# Step 10: Wait for gateway
echo "10. Waiting for gateway to be ready..."
for i in {1..30}; do
    if curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8080/healthz 2>/dev/null | grep -q "200"; then
        echo "✓ Gateway is ready"
        break
    fi
    if [ $i -eq 30 ]; then
        echo "⚠ Gateway not responding after 30 seconds"
        echo "  Check logs: journalctl -u faasd -f"
    fi
    sleep 1
    echo -n "."
done
echo ""

# Summary
echo "=========================================="
echo "Setup Complete!"
echo "=========================================="
echo ""
echo "Services running on faasd:"
echo "  • Gateway:          http://127.0.0.1:8080"
echo "  • MinIO API:        http://127.0.0.1:9002"
echo "  • MinIO Console:    http://127.0.0.1:9003"
echo "  • Redpanda:         localhost:19092 (external)"
echo "  • Redpanda Console: http://127.0.0.1:8888"
echo "  • Redis:            localhost:6379"
echo "  • Qdrant:           http://127.0.0.1:6333"
echo "  • Prometheus:       http://127.0.0.1:9090"
echo ""
echo "Next steps:"
echo ""
echo "1. Login to faasd:"
echo "   sudo cat /var/lib/faasd/secrets/basic-auth-password | faas-cli login -s"
echo ""
echo "2. Set DOCKER_USER environment variable:"
echo "   export DOCKER_USER=<your-dockerhub-username>"
echo ""
echo "3. Build and deploy functions:"
echo "   cd $PROJECT_DIR"
echo "   faas-cli up -f stack.yaml"
echo ""
