#!/bin/sh
# Fix Docker socket permissions so the app process can reach the host Docker daemon.
# On macOS Docker Desktop the socket is owned by root:root (mode 660).
# We simply make it world-readable/writable which is safe inside this container.
if [ -S /var/run/docker.sock ]; then
    chmod 666 /var/run/docker.sock
fi

exec uvicorn script:app --host 0.0.0.0 --port 8000
