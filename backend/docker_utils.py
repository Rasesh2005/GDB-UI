import asyncio
import os
import docker

def make_docker_client() -> docker.DockerClient:
    try:
        c = docker.from_env()
        c.ping()
        return c
    except Exception:
        import platform
        if platform.system() == "Darwin":
            return docker.DockerClient(
                base_url=f"unix://{os.path.expanduser('~')}/.docker/run/docker.sock"
            )
        raise

docker_client = make_docker_client()

def get_docker_socket_path() -> str:
    """Return the raw Docker socket path."""
    for path in ("/var/run/docker.sock",
                 os.path.expanduser("~/.docker/run/docker.sock")):
        if os.path.exists(path):
            return path
    return "/var/run/docker.sock"

async def open_exec_socket(exec_id: str, tty: bool) -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
    """
    Open exec socket with proper JSON body (Detach + Tty fields).
    This is the correct low-level approach to hijack a Docker exec stream.
    """
    sock_path = get_docker_socket_path()
    reader, writer = await asyncio.open_unix_connection(sock_path)

    body = f'{{"Detach":false,"Tty":{str(tty).lower()}}}'
    http_req = (
        f"POST /exec/{exec_id}/start HTTP/1.1\r\n"
        f"Host: localhost\r\n"
        f"Content-Type: application/json\r\n"
        f"Content-Length: {len(body)}\r\n"
        f"Connection: Upgrade\r\n"
        f"Upgrade: tcp\r\n"
        f"\r\n"
        f"{body}"
    )
    writer.write(http_req.encode())
    await writer.drain()

    # Read HTTP response headers
    while True:
        line = await reader.readline()
        if line in (b"\r\n", b"\n", b""):
            break

    return reader, writer
