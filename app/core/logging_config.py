"""
Centralized logging configuration for PetroRAG.

Call setup_logging() once at application startup.
All modules using logging.getLogger(__name__) will automatically
inherit this configuration.
"""
import logging
import logging.handlers
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from contextvars import ContextVar

# ── Context variable for request correlation ──
request_id_var: ContextVar[str] = ContextVar("request_id", default="-")


def get_request_id() -> str:
    """Get the current request ID from context. Usable from any module."""
    return request_id_var.get("-")


# ══════════════════════════════════════════════════════════════════
# JSON Formatter (for log files / aggregation)
# ══════════════════════════════════════════════════════════════════
class JSONFormatter(logging.Formatter):
    """Outputs each log record as a single JSON line."""

    def format(self, record: logging.LogRecord) -> str:
        entry = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": get_request_id(),
        }
        # Add exception info if present
        if record.exc_info and record.exc_info[0] is not None:
            entry["exception"] = self.formatException(record.exc_info)
        # Add any extra fields attached by middleware or callers
        for key in ("method", "path", "status_code", "duration_ms",
                     "client_ip", "request_size", "response_size"):
            if hasattr(record, key):
                entry[key] = getattr(record, key)
        return json.dumps(entry, ensure_ascii=False)


# ══════════════════════════════════════════════════════════════════
# Console Formatter (colored, human-readable)
# ══════════════════════════════════════════════════════════════════
class ColoredFormatter(logging.Formatter):
    """
    Colored console output.
    Format: [HH:MM:SS] LEVEL    logger — message  [req:id]
    """

    COLORS = {
        "DEBUG":    "\033[36m",    # Cyan
        "INFO":     "\033[32m",    # Green
        "WARNING":  "\033[33m",    # Yellow
        "ERROR":    "\033[31m",    # Red
        "CRITICAL": "\033[1;31m",  # Bold Red
    }
    RESET = "\033[0m"
    DIM = "\033[2m"

    def format(self, record: logging.LogRecord) -> str:
        color = self.COLORS.get(record.levelname, self.RESET)
        time_str = datetime.fromtimestamp(record.created).strftime("%H:%M:%S")

        # Shorten logger name: app.controllers.chat_controller → chat_controller
        name = record.name
        parts = name.split(".")
        if len(parts) > 2:
            name = parts[-1]

        req_id = get_request_id()
        req_tag = f" {self.DIM}[req:{req_id[:8]}]{self.RESET}" if req_id != "-" else ""

        return (
            f"{self.DIM}[{time_str}]{self.RESET} "
            f"{color}{record.levelname:<8}{self.RESET} "
            f"{name} — {record.getMessage()}{req_tag}"
        )


# ══════════════════════════════════════════════════════════════════
# Setup
# ══════════════════════════════════════════════════════════════════
def setup_logging(
    log_level: str = "INFO",
    log_dir: Path = Path("./logs"),
    log_json: bool = True,
) -> None:
    """
    Configure the root logger with console + file handlers.

    Args:
        log_level: Minimum log level (DEBUG, INFO, WARNING, ERROR).
        log_dir: Directory for log files.
        log_json: Whether to write JSON to log files.
    """
    level = getattr(logging, log_level.upper(), logging.INFO)

    # Create log directory
    log_dir = Path(log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)

    # ── Root logger ──
    root = logging.getLogger()
    root.setLevel(level)

    # Clear any existing handlers (e.g. from basicConfig)
    root.handlers.clear()

    # ── Console handler ──
    console = logging.StreamHandler(sys.stdout)
    console.setLevel(level)
    console.setFormatter(ColoredFormatter())
    root.addHandler(console)

    # ── File handler (rotating) ──
    log_file = log_dir / "petrorag.log"
    file_handler = logging.handlers.RotatingFileHandler(
        filename=str(log_file),
        maxBytes=10 * 1024 * 1024,  # 10 MB
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setLevel(level)
    if log_json:
        file_handler.setFormatter(JSONFormatter())
    else:
        file_handler.setFormatter(logging.Formatter(
            "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
        ))
    root.addHandler(file_handler)

    # ── Error-only file (for quick triage) ──
    error_file = log_dir / "petrorag.error.log"
    error_handler = logging.handlers.RotatingFileHandler(
        filename=str(error_file),
        maxBytes=10 * 1024 * 1024,
        backupCount=3,
        encoding="utf-8",
    )
    error_handler.setLevel(logging.ERROR)
    if log_json:
        error_handler.setFormatter(JSONFormatter())
    else:
        error_handler.setFormatter(logging.Formatter(
            "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
        ))
    root.addHandler(error_handler)

    # ── Quiet noisy third-party loggers ──
    for noisy in (
        "uvicorn.access", "uvicorn.error",
        "httpcore", "httpx", "pymongo",
        "urllib3", "asyncio", "watchfiles",
        "qdrant_client", "sentence_transformers",
        "transformers", "torch",
    ):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    # Keep uvicorn.error at INFO so startup messages show
    logging.getLogger("uvicorn.error").setLevel(logging.INFO)

    logging.getLogger("petrorag").info(
        f"Logging configured: level={log_level}, dir={log_dir}, json={log_json}"
    )
