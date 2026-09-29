from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

import structlog
from structlog.contextvars import merge_contextvars

from .pii import scrub_text

LOG_PATH = Path(os.getenv("LOG_PATH", "data/logs.jsonl"))


class JsonlFileProcessor:
    def __call__(self, logger: Any, method_name: str, event_dict: dict[str, Any]) -> dict[str, Any]:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        rendered = structlog.processors.JSONRenderer()(logger, method_name, event_dict)
        with LOG_PATH.open("a", encoding="utf-8") as f:
            f.write(rendered + "\n")
        return event_dict



_EXCLUDED_KEYS = {"ts", "level", "correlation_id"}


def _scrub_nested(val: Any) -> Any:
    if isinstance(val, str):
        return scrub_text(val)
    if isinstance(val, dict):
        return {k: _scrub_nested(v) for k, v in val.items()}
    if isinstance(val, list):
        return [_scrub_nested(item) for item in val]
    if isinstance(val, tuple):
        return tuple(_scrub_nested(item) for item in val)
    return val


def scrub_event(_: Any, __: str, event_dict: dict[str, Any]) -> dict[str, Any]:
    for key, value in list(event_dict.items()):
        if key in _EXCLUDED_KEYS:
            continue
        if key == "payload":
            event_dict[key] = _scrub_nested(value)
        elif isinstance(value, str):
            event_dict[key] = scrub_text(value)
        elif isinstance(value, (dict, list, tuple)):
            event_dict[key] = _scrub_nested(value)
    return event_dict


def configure_logging() -> None:
    logging.basicConfig(format="%(message)s", level=getattr(logging, os.getenv("LOG_LEVEL", "INFO")))
    structlog.configure(
        processors=[
            merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True, key="ts"),
            scrub_event,
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            JsonlFileProcessor(),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
        cache_logger_on_first_use=True,
    )



def get_logger() -> structlog.typing.FilteringBoundLogger:
    return structlog.get_logger()
