# Serverless Setup on Windows and Linux (WSL + Docker + faasd)

This project utilizes a hybrid development environment designed to balance ease of use with performance. We use **Windows Subsystem for Linux 2 (WSL2)** to host `faasd` (the lightweight OpenFaaS daemon), which manages the serverless runtime. Simultaneously, we leverage **Docker Desktop on Windows** to handle the heavy lifting of building and managing container images.

## Architecture Overview

* **WSL 2 (Ubuntu):** Acts as the "server." This is where the `faasd` process runs, managing your functions and routing traffic.
* **Docker Desktop:** Acts as the "builder." It builds your function code into container images that `faasd` can pull and run.
* **faasd:** A single-binary version of OpenFaaS. It uses `containerd` directly (skipping Kubernetes) for a highly efficient local serverless experience.

---
## [Linux] Quick setup script

```bash
# run setup script
./setup_faasd.sh

# check status of faasd
./check_faasd_status.sh
```

---

## [Windows] Prerequisites (WSL + Docker Desktop)

Please set up the components in the exact order listed below to ensure proper networking and permissions.

### [Windows] 1. Install WSL 2 (Ubuntu)

We need a robust Linux environment to run the serverless control plane.

1. **Open PowerShell as Administrator.**
2. **Install WSL:** Run the following command to install the subsystem and the default Ubuntu distribution:
```powershell
wsl --install -d Ubuntu

```


3. **Restart:** Restart your computer if prompted by Windows.
4. **Initialize:** Open the "Ubuntu" app from your Start menu. Wait for the initialization to finish and create your UNIX username and password when prompted.

### [Windows] 2. Configure Systemd (Critical Step)

`faasd` relies on `systemd` to manage its services. By default, older WSL setups used `init`. We must ensure `systemd` is active.

1. **Check current init system:**
Run this in your Ubuntu terminal:
```bash
ps --no-headers -o comm 1

```


* If it says `systemd`, skip to step 3.
* If it says `init`, proceed below.


2. **Enable Systemd:**
Edit the WSL configuration file:
```bash
sudo nano /etc/wsl.conf

```


Add the following lines:
```ini
[boot]
systemd=true

```


Save and exit (`Ctrl+O`, `Enter`, `Ctrl+X`).
3. **Restart WSL:**
Close your Linux terminal. Open **PowerShell (Admin)** and completely shut down WSL to apply changes:
```powershell
wsl --shutdown

```


Re-open your Ubuntu terminal.

### [Windows] 3. Install & Connect Docker Desktop

We use Docker Desktop on Windows to facilitate image building. The "WSL Integration" feature bridges the Docker engine on Windows into your Ubuntu shell.

1. **Install:** Download and install [Docker Desktop for Windows](https://www.docker.com/products/docker-desktop/).
2. **Configure Integration:**
* Open Docker Desktop.
* Click the **Settings** (Gear Icon) in the top right.
* Navigate to **Resources** > **WSL Integration**.
* Ensure "Enable integration with my default WSL distro" is checked.
* Toggle the switch **ON** specifically for your **Ubuntu** distribution.
* Click **Apply & Restart**.


3. **Verify:**
Open your Ubuntu terminal and run:
```bash
docker ps

```


* **Success:** You should see table headers (`CONTAINER ID`, `IMAGE`, etc.).
* **Failure:** If you see "Cannot connect to the Docker daemon," ensure Docker Desktop is running.



---

## [Windows] Installation (WSL)

### [Windows] 4. Install faasd (inside WSL)

Now we install the runtime that will actually execute your functions. This script installs `containerd`, CNI networking plugins, and the `faasd` binary.

1. **Install Dependencies:**
```bash
sudo apt update && sudo apt install -y curl git

```


2. **Clone & Install:**
```bash
git clone https://github.com/openfaas/faasd --depth=1
cd faasd
./hack/install.sh

```


> **Note:** This process may take 1-2 minutes.


3. **Verify Services:**
Check that the daemon is active:
```bash
sudo systemctl status faasd faasd-provider

```


You should see both services listed as `active (running)`.

### [Windows] 5. Install the CLI & Log In (inside WSL)

You need the OpenFaaS CLI (`faas-cli`) to deploy and invoke functions.

1. **Install CLI:**
```bash
curl -sL https://cli.openfaas.com | sudo sh

```


2. **Retrieve Admin Password:**
`faasd` generates a secure random password upon installation.
```bash
sudo cat /var/lib/faasd/secrets/basic-auth-password

```


*Copy the output string to your clipboard.*
3. **Log In:**
You can log in using either method:

**Method 1 (Simpler):** Pipe the password directly:
```bash
sudo cat /var/lib/faasd/secrets/basic-auth-password | faas-cli login -s
```

**Method 2:** Use the password you copied:
```bash
# Replace <your-password> with the string you just copied
echo -n <your-password> | faas-cli login --username admin --password-stdin
```

> **Note:** Method 1 automatically saves credentials to `~/.openfaas/config.yml`.



---

## [Both] Validation

To ensure everything is connected, let's deploy a test function.

1. **Deploy `figlet`:**
```bash
faas-cli store deploy figlet

```


2. **Invoke:**
```bash
echo "Hello World!" | faas-cli invoke figlet

```


3. **Access UI:**
You can access the OpenFaaS dashboard in several ways:

**Option 1: Using localhost (Windows/WSL):**
Open a browser and navigate to: `http://localhost:8080/ui/`

**Option 2: Using WSL IP address (Windows):**
If localhost doesn't work, get your WSL IP address:
```bash
hostname -I
# Example output: 172.26.19.196
```
Then navigate to: `http://[WSL-IP]:8080/ui/` (e.g., `http://172.26.19.196:8080/ui/`)

**Option 3: Using localhost (Linux):**
Open a browser and navigate to: `http://localhost:8080/ui/`

* **Username:** `admin`
* **Password:** Retrieve it with: `sudo cat /var/lib/faasd/secrets/basic-auth-password`

---

## [Both] Monitoring and Troubleshooting

Useful commands for monitoring and debugging your faasd installation:

### View Running Containers

Since faasd uses `containerd` (not Docker), use the `ctr` command to view containers:

```bash
sudo ctr -n openfaas tasks ls
```

### View System Logs

Check OpenFaaS system logs:

```bash
sudo journalctl -t openfaas -n 50 --no-pager
```

For real-time log monitoring:

```bash
sudo journalctl -u faasd -f
```

### Check Service Status

Verify that all services are running:

```bash
sudo systemctl status faasd faasd-provider
```

---

## [Both] Adding Non-Serverless Services

If you want to extend the setup with additional non-serverless services (such as Kafka brokers, databases, or custom microservices), you can do so by modifying the `docker-compose.yaml` file included in this repository.

1. **Extend the docker-compose.yaml:**
Edit the `docker-compose.yaml` file in this project directory to add your custom services and configurations.

2. **Replace the faasd docker-compose.yaml:**
Once you've made your changes, replace the existing `docker-compose.yaml` running with faasd:
```bash
sudo cp docker-compose.yaml /var/lib/faasd/docker-compose.yaml
sudo systemctl restart faasd

```


This will integrate your custom services with the existing faasd infrastructure.

---

## [Both] Update Docker Hub Username

The `docker-compose.yaml` file in this repository contains a hardcoded Docker Hub username (`markovranjes`). Before deploying any custom images, **replace this with your own Docker Hub username**:

```yaml
# Find this line in docker-compose.yaml:
image: markovranjes/redpanda-connector:latest

# Replace "markovranjes" with your Docker Hub username:
image: <your-dockerhub-username>/redpanda-connector:latest

```

This ensures that when you build and push custom container images, they reference the correct Docker Hub account.

---

## [Windows + Linux] Running the Environment for the First Time

Follow these steps to deploy the entire stack, including custom services and serverless functions.

---

### [Windows] For Windows (WSL) Users

#### Step 1: Build & Push Custom Docker Images (Windows)

From your local Windows machine (not WSL), build and push the custom services to your Docker Hub account:

```bash
# Navigate to the redpanda-connector directory
cd redpanda-connector

# Build the Docker image
docker build -t <your-dockerhub-username>/redpanda-connector:latest .

# Push to Docker Hub
docker push <your-dockerhub-username>/redpanda-connector:latest

```

> **Note:** Make sure you're logged in to Docker Hub locally. Run `docker login` if needed.

#### Step 2: Publish Serverless Functions (Windows)

Before publishing, set the `DOCKER_USER` environment variable to your Docker Hub username. In PowerShell:

```powershell
$env:DOCKER_USER="<your-dockerhub-username>"
```

Or in Command Prompt:

```cmd
set DOCKER_USER=<your-dockerhub-username>
```

Then publish the serverless function images using the OpenFaaS CLI from this repository:

```bash
./faas-cli.exe publish -f stack.yaml

```

> **Note:** Use `faas-cli.exe` from this repository directory, not a globally installed version. This command builds and pushes all functions defined in `stack.yaml` to your Docker Hub account. The `DOCKER_USER` variable must be set before running this command.

#### Step 3: Start Services in WSL

Switch to your Ubuntu (WSL) terminal and restart the faasd services to apply any configuration changes:

```bash
sudo systemctl restart faasd

```

#### Step 4: Deploy Serverless Functions (WSL)

Before deploying, set the `DOCKER_USER` environment variable to your Docker Hub username:

```bash
export DOCKER_USER=<your-dockerhub-username>

```

Then deploy your serverless functions to the running faasd environment:

```bash
faas-cli deploy -f stack.yaml

```

Monitor the deployment progress. Once complete, verify your functions are deployed:

```bash
faas-cli list

```

All services should now be operational and ready for use.

---

### [Linux] For Linux Users

#### Step 1: Build & Push Custom Docker Images

Build and push the custom services to your Docker Hub account:

```bash
# Navigate to the redpanda-connector directory
cd redpanda-connector

# Build the Docker image
docker build -t <your-dockerhub-username>/redpanda-connector:latest .

# Push to Docker Hub
docker push <your-dockerhub-username>/redpanda-connector:latest

```

> **Note:** Make sure you're logged in to Docker Hub. Run `docker login` if needed.

#### Step 2: Publish Serverless Functions

Before publishing, set the `DOCKER_USER` environment variable to your Docker Hub username:

```bash
export DOCKER_USER=<your-dockerhub-username>

```

Then publish the serverless function images using the OpenFaaS CLI:

```bash
faas-cli publish -f stack.yaml

```

> **Note:** This command builds and pushes all functions defined in `stack.yaml` to your Docker Hub account. Make sure `faas-cli` is installed and in your PATH. The `DOCKER_USER` variable must be set before running this command.

#### Step 3: Start Services

Restart the faasd services to apply any configuration changes:

```bash
sudo systemctl restart faasd

```

#### Step 4: Deploy Serverless Functions

Before deploying, set the `DOCKER_USER` environment variable to your Docker Hub username:

```bash
export DOCKER_USER=<your-dockerhub-username>

```

Then deploy your serverless functions to the running faasd environment:

```bash
faas-cli deploy -f stack.yaml

```

Monitor the deployment progress. Once complete, verify your functions are deployed:

```bash
faas-cli list

```

All services should now be operational and ready for use.


---
## [Both] Virtual environment

```bash
# create virtual environment
python3 -m venv .venv

# activate
source .venv/bin/activate

# install dependencies
pip install -r redpanda-connector/requirements.txt

# deactivate
deactivate
```

---

## [Both] Testing Manual


### Unit and Integration Tests

First activate virtual environment.

```bash
# run all tests
pytest -q

# run specific module
pytest -q redpanda-connector 

# run specific test file
pytest -q redpanda-connector -m integration
```


---

## [Both] Port Forwarding for VM Access

If you are running the services on a VM and want to access them from your local browser, you need to set up SSH port forwarding.

### Services and Ports

The following services expose ports that you may want to access:

- **MinIO Console:** Port 9001 (Web UI)
- **MinIO API:** Port 9000 (S3 API)
- **Redpanda Console:** Port 8888 (Web UI)
- **Redpanda Kafka:** Port 29092 (External Kafka endpoint)
- **OpenFaaS Gateway:** Port 8080 (Web UI and API)
- **Redis:** Port 6379 (Redis CLI access)
- **Qdrant:** Port 6333 (Web UI and API)
- **Prometheus:** Port 9090 (Web UI)

### SSH Port Forwarding (Local to VM)

From your local machine, establish SSH port forwarding to the VM:

```bash
# Forward all commonly used ports
ssh -L 9001:localhost:9001 \
    -L 9000:localhost:9000 \
    -L 8888:localhost:8888 \
    -L 29092:localhost:29092 \
    -L 8080:localhost:8080 \
    -L 6379:localhost:6379 \
    -L 6333:localhost:6333 \
    -L 9090:localhost:9090 \
    <user>@<vm-ip-or-hostname>
```

Or forward individual ports as needed:

```bash
# MinIO Console
ssh -L 9001:localhost:9001 <user>@<vm-ip-or-hostname>

# Redpanda Console
ssh -L 8888:localhost:8888 <user>@<vm-ip-or-hostname>

# OpenFaaS Gateway
ssh -L 8080:localhost:8080 <user>@<vm-ip-or-hostname>
```

### Accessing Services

Once port forwarding is established, you can access services from your local browser:

- **MinIO Console:** http://localhost:9001 (Username: `admin`, Password: `password123`)
- **MinIO API:** http://localhost:9000
- **Redpanda Console:** http://localhost:8888
- **OpenFaaS Gateway UI:** http://localhost:8080/ui/
- **Prometheus:** http://localhost:9090
- **Qdrant:** http://localhost:6333
