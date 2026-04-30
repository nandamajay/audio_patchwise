import socket


def find_free_port(start_port: int, max_attempts: int = 20) -> int:
    """
    Find the next available port starting from start_port.
    Tries up to max_attempts consecutive ports.
    """
    for port in range(start_port, start_port + max_attempts):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("0.0.0.0", port))
                return port
            except OSError:
                continue
    raise RuntimeError(
        f"No free port found in range {start_port}–{start_port + max_attempts}"
    )


if __name__ == "__main__":
    import sys

    start = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    port = find_free_port(start)
    print(port)
