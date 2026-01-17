#!/bin/bash
set -e

echo "Starting faasd VM..."
multipass start faasd-vm

echo "Waiting for VM to initialize..."
sleep 10

echo "Checking faasd status..."
multipass exec faasd-vm -- sudo systemctl status faasd --no-pager | head -5

# Get VM IP
VM_IP=$(multipass info faasd-vm | grep IPv4 | awk '{print $2}')
echo "VM IP: $VM_IP"

echo "Setting environment variables..."
export OPENFAAS_URL=http://$VM_IP:8080
export DOCKER_USER=stanisica

echo "Logging into OpenFaaS..."
PASSWORD=$(multipass exec faasd-vm -- sudo cat /var/lib/faasd/secrets/basic-auth-password)
echo -n $PASSWORD | faas-cli login --username admin --password-stdin

echo "Verifying deployment..."
faas-cli list

echo ""
echo "========================================"
echo "faasd is ready!"
echo "========================================"
echo ""
echo "Run these commands in your terminal:"
echo "  export OPENFAAS_URL=http://$VM_IP:8080"
echo "  export DOCKER_USER=stanisica"
echo ""
echo "Useful URLs:"
echo "  OpenFaaS UI:     http://$VM_IP:8080/ui/"
echo "  Qdrant:          http://$VM_IP:6333/dashboard"
echo "  Minio Console:   http://$VM_IP:9001"
echo "  Redpanda Console: http://$VM_IP:8888"
echo "  Prometheus:      http://$VM_IP:9090"
echo ""
