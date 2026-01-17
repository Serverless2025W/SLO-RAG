#!/bin/bash
# View function logs
# Usage: ./scripts/logs.sh <function-name>
# Example: ./scripts/logs.sh query-embedding-retrieval

if [ -z "$1" ]; then
    echo "Usage: ./scripts/logs.sh <function-name>"
    echo ""
    echo "Available functions:"
    faas-cli list
    exit 1
fi

faas-cli logs "$1"
