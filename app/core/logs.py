import logging
import sys


def init_logging(
    *,
    level: str | int = "INFO",
    max_bytes: int = 5 * 1024 * 1024,  # 5 MB
    backup_count: int = 10,
) -> None:
    """
    Configure the root logger once.

    Parameters
    ----------
    level : str | int
        One of ``"DEBUG"``, ``"INFO"``, ``"WARNING"``,
        ``"ERROR"`` or ``"CRITICAL"``, or the corresponding
        integer value from :mod:`logging`.
    log_file : str | None
        Path to the file where logs are written. If *None*, only console output is used.
    max_bytes, backup_count :
        Arguments for :class:`RotatingFileHandler` – keeps log size bounded.
    """

    # Accept a string and map it to an int level
    if isinstance(level, str):
        # Allow the user to pass e.g. "debug" or "DEBUG"
        try:
            level = getattr(logging, level.upper())
        except AttributeError as exc:
            raise ValueError(
                f'Invalid log level "{level}". '
                "Choose from DEBUG, INFO, WARNING, ERROR, CRITICAL."
            ) from exc

    root = logging.getLogger()
    root.setLevel(level)

    # Remove any existing handlers (idempotent)
    while root.handlers:
        root.removeHandler(root.handlers[0])

    formatter = logging.Formatter(
        fmt="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Console handler (stdout)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    root.addHandler(console_handler)

    # Silence noisy third‑party libraries unless the user explicitly wants them
    logging.getLogger("twitchio").setLevel(logging.WARNING)
    logging.getLogger("twitchio.web.aio_adapter").setLevel(logging.WARNING)


def get_logger(name: str | None = None) -> logging.Logger:
    """Return a logger for the given name.  If no name is supplied,
    it returns the root logger."""
    return logging.getLogger(name or __name__)
