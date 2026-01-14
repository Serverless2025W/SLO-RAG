#!/bin/bash
# Integration test runner for redpanda-connector
# This script runs integration tests and checks service logs

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

echo "=========================================="
echo "Redpanda Connector Integration Tests"
echo "=========================================="
echo ""

# Check if services are running
echo "Checking service availability..."
echo ""

# Check Redis
if docker ps | grep -q redis; then
    echo "✓ Redis container is running"
else
    echo "✗ Redis container is not running"
    echo "  Start with: docker-compose up -d redis"
fi

# Check Redpanda
if docker ps | grep -q redpanda; then
    echo "✓ Redpanda container is running"
else
    echo "✗ Redpanda container is not running"
    echo "  Start with: docker-compose up -d redpanda"
fi

# Check redpanda-connector
if docker ps | grep -q redpanda-connector; then
    echo "✓ redpanda-connector container is running"
else
    echo "✗ redpanda-connector container is not running"
    echo "  Start with: docker-compose up -d redpanda-connector"
fi

echo ""
echo "=========================================="
echo "Running Integration Tests"
echo "=========================================="
echo ""

cd "$SCRIPT_DIR"

# Run tests
pytest test_integration.py -v -m integration --tb=short

echo ""
echo "=========================================="
echo "Service Logs (last 20 lines)"
echo "=========================================="
echo ""

# Show redpanda-connector logs
if docker ps | grep -q redpanda-connector; then
    echo "--- redpanda-connector logs ---"
    docker logs redpanda-connector --tail 20 2>&1 | tail -20
    echo ""
fi

# Show Redis logs
if docker ps | grep -q redis; then
    echo "--- Redis logs ---"
    docker logs redis --tail 10 2>&1 | tail -10
    echo ""
fi

# Show Redpanda logs
if docker ps | grep -q redpanda; then
    echo "--- Redpanda logs ---"
    docker logs redpanda --tail 10 2>&1 | tail -10
    echo ""
fi

echo "=========================================="
echo "Test Summary"
echo "=========================================="
echo ""
echo "To view full logs:"
echo "  docker logs redpanda-connector -f"
echo "  docker logs redis -f"
echo "  docker logs redpanda -f"
echo ""
