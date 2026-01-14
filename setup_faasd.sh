#!/bin/bash
# Setup script to configure faasd with docker-compose.yaml

set -e

PROJECT_DIR="/root/projects/SLO-RAG"
FAASD_DIR="/var/lib/faasd"

echo "=========================================="
echo "faasd Setup Script"
echo "=========================================="
echo ""

# Check if running as root or with sudo
if [ "$EUID" -ne 0 ]; then 
    echo "This script must be run with sudo"
    exit 1
fi

# Step 1: Check if faasd is installed
echo "1. Checking if faasd is installed..."
if ! systemctl list-units | grep -q faasd; then
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
mkdir -p "$FAASD_DIR"/{nats,prometheus,minio-data,redis-data,qdrant-data}
echo "✓ Directories created"
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
    # Create prometheus directory in faasd if it doesn't exist
    mkdir -p "$FAASD_DIR"
    cp "$PROJECT_DIR/prometheus.yml" "$FAASD_DIR/prometheus.yml"
    echo "✓ prometheus.yml copied"
else
    echo "⚠ prometheus.yml not found (this is okay if using default config)"
fi
echo ""

# Step 5: Check secrets
echo "5. Checking faasd secrets..."
if [ ! -f "$FAASD_DIR/secrets/basic-auth-password" ]; then
    echo "✗ basic-auth-password not found"
    echo "  This should have been created during faasd installation"
    echo "  If missing, faasd may not be properly installed"
else
    echo "✓ Secrets exist"
fi
echo ""

# Step 6: Restart faasd
echo "6. Restarting faasd..."
systemctl restart faasd
echo "✓ faasd restarted"
echo ""

# Step 7: Wait for services to start
echo "7. Waiting for services to start (5 seconds)..."
sleep 5
echo ""

# Step 8: Check status
echo "8. Checking faasd status..."
systemctl status faasd --no-pager -l | head -15
echo ""

echo "Next steps:"
echo "1. Login to faasd:"
echo "   sudo cat /var/lib/faasd/secrets/basic-auth-password | faas-cli login -s"
echo ""
echo "2. Set DOCKER_USER environment variable:"
echo "   export DOCKER_USER=<your-dockerhub-username>"
echo ""
echo "3. Publish function images (if not already done):"
echo "   faas-cli publish -f stack.yaml"
echo ""
echo "4. Deploy functions:"
echo "   faas-cli deploy -f stack.yaml"
echo ""