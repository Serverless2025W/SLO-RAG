#!/bin/bash
set -e

echo "Transferring docker-compose.yaml to VM..."
multipass transfer docker-compose.yaml faasd-vm:/home/ubuntu/docker-compose.yaml

echo "Copying to faasd directory..."
multipass exec faasd-vm -- sudo cp /home/ubuntu/docker-compose.yaml /var/lib/faasd/docker-compose.yaml

echo "Restarting faasd..."
multipass exec faasd-vm -- sudo systemctl restart faasd

echo "Waiting for services to start..."
sleep 5

echo "Checking faasd status..."
multipass exec faasd-vm -- sudo systemctl status faasd --no-pager

echo "Done!"
