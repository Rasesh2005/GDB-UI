# GDB-UI

This project is a web-based interface for interacting with GDB, running inside isolated Docker sandboxes.

## How it Works

1. **Backend**: A FastAPI server (`script.py`) manages the orchestration of Docker containers (sandboxes) where GDB runs. It communicates with the Docker daemon to spawn sibling containers.
2. **Frontend**: A React application built with Vite provides the user interface (editor, terminal, profile view).
3. **Docker-out-of-Docker (DooD)**: The server runs in a container and shares the host's Docker socket to manage sandbox containers.

## How to Start

### Prerequisites
- Docker and Docker Compose installed.
- Node.js installed (for building the frontend).

### Steps

1. **Build the Frontend**
   The Docker setup expects the frontend to be pre-built in the `frontend/dist` directory.
   ```bash
   cd frontend
   npm install
   npm run build
   cd ..
   ```

2. **Run the Application**
   Start the server.
   ```bash
   python script.py
   ```

3. **Access the App**
   Open your browser and navigate to `http://localhost:8000`.

## Directory Structure
- `frontend/`: React source code.
- `script.py`: Backend server logic.
- `Dockerfile.server`: Dockerfile for the backend server.
- `docker-compose.yml`: Orchestrates the services.
