#!/bin/bash
# Diagnostic script to check faasd status and troubleshoot deployment issues

echo "=========================================="
echo "faasd Status Check"
echo "=========================================="
echo ""

# Check if faasd services are running
echo "1. Checking faasd services status..."
sudo systemctl status faasd faasd-provider --no-pager -l | head -20
echo ""

# Check if gateway is accessible
echo "2. Checking gateway accessibility..."
if curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8080/system/functions | grep -q "200\|401"; then
    echo "✓ Gateway is accessible at http://127.0.0.1:8080"
else
    echo "✗ Gateway is NOT accessible at http://127.0.0.1:8080"
    echo "  Connection refused means faasd gateway is not running"
fi
echo ""

# Check if docker-compose.yaml exists in faasd directory
echo "3. Checking faasd docker-compose.yaml..."
if [ -f "/var/lib/faasd/docker-compose.yaml" ]; then
    echo "✓ docker-compose.yaml exists at /var/lib/faasd/docker-compose.yaml"
    echo "  File size: $(stat -c%s /var/lib/faasd/docker-compose.yaml) bytes"
else
    echo "✗ docker-compose.yaml NOT found at /var/lib/faasd/docker-compose.yaml"
    echo "  You need to copy it from the project directory"
fi
echo ""

# Check if required directories exist
echo "4. Checking required directories..."
REQUIRED_DIRS=(
    "/var/lib/faasd/secrets"
    "/var/lib/faasd/nats"
    "/var/lib/faasd/prometheus"
)

for dir in "${REQUIRED_DIRS[@]}"; do
    if [ -d "$dir" ]; then
        echo "✓ $dir exists"
    else
        echo "✗ $dir does NOT exist"
    fi
done
echo ""

# Check if secrets exist
echo "5. Checking faasd secrets..."
if [ -f "/var/lib/faasd/secrets/basic-auth-password" ]; then
    echo "✓ basic-auth-password exists"
else
    echo "✗ basic-auth-password NOT found"
    echo "  This is required for faasd to work"
fi

if [ -f "/var/lib/faasd/secrets/basic-auth-user" ]; then
    echo "✓ basic-auth-user exists"
else
    echo "✗ basic-auth-user NOT found"
fi
echo ""

# Check containerd tasks (faasd uses containerd, not docker)
echo "6. Checking containerd tasks..."
if command -v ctr &> /dev/null; then
    echo "Containerd tasks in openfaas namespace:"
    sudo ctr -n openfaas tasks ls 2>/dev/null || echo "  No tasks found or containerd not accessible"
else
    echo "✗ ctr command not found (containerd CLI)"
fi
echo ""

# Check network connectivity
echo "7. Checking network ports..."
if netstat -tuln 2>/dev/null | grep -q ":8080"; then
    echo "✓ Port 8080 is listening"
    netstat -tuln 2>/dev/null | grep ":8080"
else
    echo "✗ Port 8080 is NOT listening"
    echo "  This means the gateway is not running"
fi
echo ""

# Summary and recommendations
echo "=========================================="
echo "Summary and Recommendations"
echo "=========================================="
echo ""

if ! curl -s http://127.0.0.1:8080/system/functions > /dev/null 2>&1; then
    echo "ISSUE: Gateway is not accessible"
    echo ""
    echo "To fix this, run the following commands:"
    echo ""
    echo "1. Copy docker-compose.yaml to faasd directory:"
    echo "   sudo cp /root/projects/SLO-RAG/docker-compose.yaml /var/lib/faasd/docker-compose.yaml"
    echo ""
    echo "2. Create required directories if they don't exist:"
    echo "   sudo mkdir -p /var/lib/faasd/{nats,prometheus,minio-data,redis-data,qdrant-data}"
    echo ""
    echo "3. Restart faasd to apply changes:"
    echo "   sudo systemctl restart faasd"
    echo ""
    echo "4. Wait a few seconds, then check status:"
    echo "   sudo systemctl status faasd"
    echo ""
    echo "5. Check gateway is accessible:"
    echo "   curl http://127.0.0.1:8080/system/functions"
    echo ""
    echo "6. If gateway is accessible, login and deploy:"
    echo "   sudo cat /var/lib/faasd/secrets/basic-auth-password | faas-cli login -s"
    echo "   export DOCKER_USER=<your-dockerhub-username>"
    echo "   faas-cli deploy -f stack.yaml"
else
    echo "✓ Gateway appears to be accessible"
    echo ""
    echo "If deployment still fails, check:"
    echo "1. Are you logged in? Run: sudo cat /var/lib/faasd/secrets/basic-auth-password | faas-cli login -s"
    echo "2. Is DOCKER_USER set? Run: export DOCKER_USER=<your-dockerhub-username>"
    echo "3. Have you published the images? Run: faas-cli publish -f stack.yaml"
fi
echo ""
