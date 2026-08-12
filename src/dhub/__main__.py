"""Run d-hub with its environment-based configuration."""

import os

import uvicorn

from .config import PORT


def main():
    uvicorn.run(
        "dhub.app:app",
        host=os.getenv("DHUB_HOST", "0.0.0.0"),
        port=PORT,
        proxy_headers=True,
    )


if __name__ == "__main__":
    main()
