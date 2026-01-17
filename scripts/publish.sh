#!/bin/bash
# Build and push function images to Docker Hub
# Usage: ./scripts/publish.sh [function-name]
# Examples:
#   ./scripts/publish.sh                    # Publish all functions
#   ./scripts/publish.sh query-embedding-retrieval  # Publish single function

set -e

if [ -z "$DOCKER_USER" ]; then
    echo "Error: DOCKER_USER not set"
    echo "Run: export DOCKER_USER=<your-dockerhub-username>"
    exit 1
fi

if [ -n "$1" ]; then
    echo "Building and pushing $1..."
    faas-cli publish -f stack.yaml --filter "$1"
else
    echo "Building and pushing all functions..."
    faas-cli publish -f stack.yaml
fi

echo ""
echo "Done! Now run: ./scripts/deploy.sh $1"
