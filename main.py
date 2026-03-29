"""
Main entry point for hosted !Clipit
Starts the FastAPI service and multi-broadcaster runtime manager
"""

import argparse
import io
import sys

import uvicorn

import logs
from config import Config

# Set stdout to handle Unicode properly
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description="!Clipit hosted service")
    parser.add_argument(
        "--host",
        default=None,
        help="Host interface to bind (defaults to config/app.host or HOST)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=None,
        help="Port to bind (defaults to config/app.port or PORT)",
    )
    parser.add_argument(
        "--reload",
        action="store_true",
        help="Enable uvicorn auto-reload for development",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Set the logging level.",
    )
    args = parser.parse_args()

    logs.init_logging(level=args.log_level, include_ascii_art=True)
    config = Config()
    _ = config.twitch_redirect_uri  # Validate hosted callback configuration early.

    host = args.host or config.server_host
    port = args.port or config.server_port

    uvicorn.run(
        "service:create_app",
        factory=True,
        host=host,
        port=port,
        reload=args.reload,
        log_level=args.log_level.lower(),
    )


if __name__ == "__main__":
    main()
