# Serverless Setup on Windows (WSL + Docker + faasd)

This project utilizes a hybrid development environment designed to balance ease of use with performance. We use **Windows Subsystem for Linux 2 (WSL2)** to host `faasd` (the lightweight OpenFaaS daemon), which manages the serverless runtime. Simultaneously, we leverage **Docker Desktop on Windows** to handle the heavy lifting of building and managing container images.

## Architecture Overview

* **WSL 2 (Ubuntu):** Acts as the "server." This is where the `faasd` process runs, managing your functions and routing traffic.
* **Docker Desktop:** Acts as the "builder." It builds your function code into container images that `faasd` can pull and run.
* **faasd:** A single-binary version of OpenFaaS. It uses `containerd` directly (skipping Kubernetes) for a highly efficient local serverless experience.

---

## Prerequisites

Please set up the components in the exact order listed below to ensure proper networking and permissions.

### 1. Install WSL 2 (Ubuntu)

We need a robust Linux environment to run the serverless control plane.

1. **Open PowerShell as Administrator.**
2. **Install WSL:** Run the following command to install the subsystem and the default Ubuntu distribution:
```powershell
wsl --install -d Ubuntu

```


3. **Restart:** Restart your computer if prompted by Windows.
4. **Initialize:** Open the "Ubuntu" app from your Start menu. Wait for the initialization to finish and create your UNIX username and password when prompted.

### 2. Configure Systemd (Critical Step)

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

### 3. Install & Connect Docker Desktop

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

## Installation

### 4. Install faasd

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
sudo systemctl status faasd provider

```


You should see both services listed as `active (running)`.

### 5. Install the CLI & Log In

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
Run the login command, pasting your password where indicated:
```bash
# Replace <your-password> with the string you just copied
echo -n <your-password> | faas-cli login --username admin --password-stdin

```



---

## Validation

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
Open a browser in Windows and navigate to: `http://localhost:8080/ui/`
* **User:** `admin`
* **Password:** (The password retrieved in step 5)

---

## Adding Non-Serverless Services

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

## Update Docker Hub Username

The `docker-compose.yaml` file in this repository contains a hardcoded Docker Hub username (`markovranjes`). Before deploying any custom images, **replace this with your own Docker Hub username**:

```yaml
# Find this line in docker-compose.yaml:
image: markovranjes/redpanda-connector:latest

# Replace "markovranjes" with your Docker Hub username:
image: <your-dockerhub-username>/redpanda-connector:latest

```

This ensures that when you build and push custom container images, they reference the correct Docker Hub account.

---

## Running the Environment for the First Time

Follow these steps to deploy the entire stack, including custom services and serverless functions.

### Step 1: Build & Push Custom Docker Images (Windows)

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

### Step 2: Publish Serverless Functions (Windows)

Still from Windows, publish the serverless function images using the OpenFaaS CLI from this repository:

```bash
./faas-cli.exe publish -f stack.yaml

```

> **Note:** Use `faas-cli.exe` from this repository directory, not a globally installed version. This command builds and pushes all functions defined in `stack.yaml` to your Docker Hub account.

### Step 3: Start Services in WSL

Switch to your Ubuntu (WSL) terminal and restart the faasd services to apply any configuration changes:

```bash
sudo systemctl restart faasd

```

### Step 4: Deploy Serverless Functions (WSL)

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

