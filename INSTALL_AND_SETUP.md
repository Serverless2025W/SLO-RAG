# 🚀 Serverless Local Setup: faasd on WSL2

This guide documents the setup of a lightweight serverless environment using `faasd` inside WSL2, with a workflow that builds functions on Windows (using Docker Desktop) and deploys them to WSL.

## 1. Install WSL and Distro (In Windows)

Open PowerShell as Administrator and set up a fresh WSL2 instance.

```powershell
# Update WSL kernel
wsl --update

# Install a fresh Ubuntu instance named 'ServerlessSLORAG'
wsl --install --name ServerlessSLORAG

# Enter the distro
wsl -d ServerlessSLORAG

```

---

## 2. Install faasd (In WSL)

Once inside your Ubuntu terminal, install the dependencies and the `faasd` runtime.

```bash
# 1. Install required dependencies
sudo apt update && sudo apt install -y curl git bridge-utils

# 2. Clone and install faasd
git clone https://github.com/openfaas/faasd --depth=1
cd faasd
./hack/install.sh

# 3. Install the faas-cli
curl -sL https://cli.openfaas.com | sudo sh

# 4. Log in using the generated password
# (This saves credentials to ~/.openfaas/config.yml)
sudo cat /var/lib/faasd/secrets/basic-auth-password | faas-cli login -s

# --- Optional Verification ---
# Deploy sample function
faas-cli store deploy figlet
# Invoke it
echo "Hello World!" | faas-cli invoke figlet

# --- Monitoring Commands ---
# View containers (faasd uses containerd, not docker)
sudo ctr -n openfaas tasks ls

# View system logs
sudo journalctl -t openfaas -n 50 --no-pager

```

---

## 3. Build Serverless Functions (In Windows)

Since `faasd` in WSL does not include a build engine, use **Docker Desktop on Windows** to build and publish images.

### Prerequisites

* **Docker Desktop** installed and running.
* **faas-cli** installed on Windows.

```powershell
# Install faas-cli via wget (if not installed) and add to path
wget https://github.com/openfaas/faas-cli/releases/download/0.18.0/faas-cli.exe -o faas-cli.exe

# Pull the python template
faas-cli template store pull python3-http

```

### Create the Function

```powershell
mkdir serverless-func
cd serverless-func

# Create a new function named 'test'
faas-cli new --lang python3-http test

```

### Configure `stack.yaml`

Edit the generated `stack.yaml` file. You must point the image to a registry (Docker Hub) so the WSL instance can pull it.

```yaml
functions:
  test:
    lang: python3-http
    handler: ./test
    # CHANGE THIS: Replace with your Docker Hub username
    image: your-docker-username/test:latest

```

### Build & Push

```powershell
# Login to Docker Hub
docker login

# Build the image and push to Docker Hub
# (publish = build + push)
faas-cli publish -f stack.yaml

```

---

## 4. Deploy Function (In WSL)

Navigate to your project directory inside WSL (or ensure `stack.yaml` is present).

```bash
# Deploy the function
# faasd will pull the image from Docker Hub automatically
faas-cli deploy -f stack.yaml

```

---

## 5. Inspect in Browser

You can access the OpenFaaS dashboard from your Windows browser using the WSL IP address.

### Get the IP

```bash
# Run inside WSL
hostname -I
# Example output: 172.26.19.196

```

### Access UI

* **URL:** `http://[WSL-IP]:8080` (e.g., `http://172.26.19.196:8080`)
* **Username:** `admin`
* **Password:** Run the command below in WSL to retrieve it:
```bash
sudo cat /var/lib/faasd/secrets/basic-auth-password

```