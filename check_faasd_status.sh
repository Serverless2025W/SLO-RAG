#!/bin/bash
# Diagnostic script to check faasd status and troubleshoot deployment issues

echo "=========================================="
echo "faasd Status Check for SLO-RAG"
echo "=========================================="
echo ""

FAASD_DIR="/var/lib/faasd"

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

pass() { echo -e "${GREEN}✓${NC} $1"; }
fail() { echo -e "${RED}✗${NC} $1"; }
warn() { echo -e "${YELLOW}⚠${NC} $1"; }

# 1. Check faasd services
echo "1. Checking faasd systemd services..."
if systemctl is-active --quiet faasd; then
    pass "faasd service is running"
else
    fail "faasd service is NOT running"
fi
if systemctl is-active --quiet faasd-provider; then
    pass "faasd-provider service is running"
else
    fail "faasd-provider service is NOT running"
fi
echo ""

# 2. Check gateway accessibility
echo "2. Checking gateway accessibility..."
GATEWAY_STATUS=$(curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8080/healthz 2>/dev/null || echo "000")
if [ "$GATEWAY_STATUS" = "200" ]; then
    pass "Gateway is accessible at http://127.0.0.1:8080 (HTTP $GATEWAY_STATUS)"
elif [ "$GATEWAY_STATUS" = "401" ]; then
    pass "Gateway is accessible (requires auth)"
else
    fail "Gateway is NOT accessible (HTTP $GATEWAY_STATUS)"
fi
echo ""

# 3. Check docker-compose.yaml
echo "3. Checking faasd docker-compose.yaml..."
if [ -f "$FAASD_DIR/docker-compose.yaml" ]; then
    pass "docker-compose.yaml exists ($(stat -c%s $FAASD_DIR/docker-compose.yaml) bytes)"
else
    fail "docker-compose.yaml NOT found at $FAASD_DIR/"
fi
echo ""

# 4. Check required directories
echo "4. Checking required directories..."
REQUIRED_DIRS=(
    "$FAASD_DIR/secrets"
    "$FAASD_DIR/nats"
    "$FAASD_DIR/prometheus"
    "$FAASD_DIR/minio-data"
    "$FAASD_DIR/redis-data"
    "$FAASD_DIR/qdrant-data"
)
for dir in "${REQUIRED_DIRS[@]}"; do
    if [ -d "$dir" ]; then
        pass "$dir"
    else
        fail "$dir does NOT exist"
    fi
done
echo ""

# 5. Check secrets
echo "5. Checking faasd secrets..."
if [ -f "$FAASD_DIR/secrets/basic-auth-password" ]; then
    pass "basic-auth-password exists"
else
    fail "basic-auth-password NOT found"
fi
if [ -f "$FAASD_DIR/secrets/basic-auth-user" ]; then
    pass "basic-auth-user exists"
else
    fail "basic-auth-user NOT found"
fi
echo ""

# 6. Check containerd containers
echo "6. Checking containerd containers (faasd runtime)..."
if command -v ctr &> /dev/null; then
    echo "   Containers in openfaas namespace:"
    CONTAINERS=$(sudo ctr -n openfaas containers ls 2>/dev/null | tail -n +2)
    if [ -n "$CONTAINERS" ]; then
        echo "$CONTAINERS" | while read line; do
            NAME=$(echo "$line" | awk '{print $1}')
            echo "   • $NAME"
        done
    else
        warn "No containers found"
    fi
else
    warn "ctr command not found (containerd CLI)"
fi
echo ""

# 7. Check service ports
echo "7. Checking service ports..."
check_port() {
    local port=$1
    local service=$2
    if ss -tlnp 2>/dev/null | grep -q ":$port "; then
        pass "Port $port ($service) is listening"
    else
        fail "Port $port ($service) is NOT listening"
    fi
}

check_port 8080 "Gateway"
check_port 9000 "MinIO API"
check_port 9001 "MinIO Console"
check_port 19092 "Redpanda external"
check_port 6379 "Redis"
check_port 6333 "Qdrant"
check_port 8888 "Redpanda Console"
check_port 9090 "Prometheus"
echo ""

# 8. Check service health
echo "8. Checking service health..."

# Redis (try redis-cli if available, otherwise use nc/curl)
if command -v redis-cli &> /dev/null; then
    REDIS_PING=$(redis-cli -h 127.0.0.1 -p 6379 ping 2>/dev/null || echo "FAIL")
    if [ "$REDIS_PING" = "PONG" ]; then
        pass "Redis is responding"
    else
        fail "Redis is NOT responding"
    fi
else
    # Fallback: check if port accepts connections
    if timeout 2 bash -c 'echo PING | nc -q1 127.0.0.1 6379 2>/dev/null' | grep -q "PONG"; then
        pass "Redis is responding"
    elif ss -tlnp | grep -q ":6379 "; then
        warn "Redis port is open (redis-cli not installed for full check)"
    else
        fail "Redis is NOT responding"
    fi
fi

# Qdrant
QDRANT_STATUS=$(curl -s http://127.0.0.1:6333/collections 2>/dev/null | grep -c '"status":"ok"' || echo "0")
if [ "$QDRANT_STATUS" -ge 1 ]; then
    pass "Qdrant is responding"
else
    fail "Qdrant is NOT responding"
fi

# MinIO (port 9002 maps to internal 9000)
MINIO_STATUS=$(curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:9002/minio/health/live 2>/dev/null || echo "000")
if [ "$MINIO_STATUS" = "200" ]; then
    pass "MinIO is healthy"
else
    warn "MinIO health check returned HTTP $MINIO_STATUS"
fi

echo ""

# 9. Check deployed functions
echo "9. Checking deployed functions..."
FUNCTIONS=$(curl -s http://127.0.0.1:8080/system/functions 2>/dev/null)
if [ -n "$FUNCTIONS" ] && [ "$FUNCTIONS" != "[]" ]; then
    echo "$FUNCTIONS" | grep -o '"name":"[^"]*"' | sed 's/"name":"//g' | sed 's/"//g' | while read func; do
        pass "Function: $func"
    done
else
    warn "No functions deployed (or auth required)"
fi
echo ""

# Summary
echo "=========================================="
echo "Summary"
echo "=========================================="
echo ""

if [ "$GATEWAY_STATUS" = "200" ] || [ "$GATEWAY_STATUS" = "401" ]; then
    echo "faasd infrastructure appears to be running."
    echo ""
    echo "To deploy functions:"
    echo "  1. Login:  sudo cat /var/lib/faasd/secrets/basic-auth-password | faas-cli login -s"
    echo "  2. Deploy: faas-cli up -f stack.yaml"
else
    echo "faasd infrastructure has issues. Try:"
    echo ""
    echo "  1. Run setup script: sudo ./setup_faasd.sh"
    echo "  2. Check logs:       journalctl -u faasd -f"
    echo "  3. Restart faasd:    sudo systemctl restart faasd"
fi
echo ""

# Recent faasd logs
echo "=========================================="
echo "Recent faasd logs (last 10 lines)"
echo "=========================================="
journalctl -u faasd --no-pager -n 10 2>/dev/null || echo "Unable to read logs"
echo ""
