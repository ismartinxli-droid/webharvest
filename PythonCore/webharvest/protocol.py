"""JSON line protocol: write events to stdout, one per line."""
import json
import sys
from typing import Any


def emit(event: str, **data: Any) -> None:
    """Write a JSON line to stdout. Use one keyword per scalar/dict field."""
    payload = {"event": event, **data}
    sys.stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")
    sys.stdout.flush()
