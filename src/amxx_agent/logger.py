"""Logging configuration for the GenAI sidecar."""

import logging
import sys

from amxx_agent.config import settings

_FORMAT = "%(asctime)s %(levelname)-8s %(name)s %(message)s"
_DATE_FORMAT = "%Y-%m-%dT%H:%M:%S"


def setup() -> None:
    """Configure the root logger from settings.

    Call once at process startup (serve_cli). Safe to call again - replaces
    any previously added handlers rather than stacking duplicates.
    """
    level = getattr(logging, settings.log_level, logging.INFO)

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(_FORMAT, datefmt=_DATE_FORMAT))

    root = logging.getLogger()
    root.setLevel(level)
    root.handlers.clear()
    root.addHandler(handler)
