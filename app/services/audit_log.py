from __future__ import annotations

import datetime as dt
import json
import logging
import os
from pathlib import Path
from typing import Any

from app.config import settings


log = logging.getLogger(__name__)


def _log_path() -> Path:
    return settings.scott_inbox / "_renarin-audit-log.jsonl"


def record(
    op: str,
    path: str | os.PathLike[str],
    *,
    status: str = "ok",
    remote_addr: str | None = None,
    ua: str | None = None,
    reason: str | None = None,
    extra: dict[str, Any] | None = None,
) -> None:
    """Append one JSONL line describing a mediated write.

    Never raises — audit logging failures must not break user writes.
    """
    entry: dict[str, Any] = {
        "ts": dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z"),
        "op": op,
        "path": str(path),
        "status": status,
    }
    if remote_addr is not None:
        entry["remote_addr"] = remote_addr
    if ua is not None:
        entry["ua"] = ua
    if reason is not None:
        entry["reason"] = reason
    if extra:
        entry.update(extra)

    try:
        log_path = _log_path()
        log_path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(entry, ensure_ascii=False, separators=(",", ":")) + "\n"
        with log_path.open("a", encoding="utf-8") as fh:
            fh.write(line)
    except Exception as exc:
        log.warning("audit_log write failed: %s", exc)
