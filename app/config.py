from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


class ConfigError(RuntimeError):
    pass


@dataclass(frozen=True)
class Settings:
    pka_root: Path
    idle_lock_seconds: int = 900

    @property
    def scott_inbox(self) -> Path:
        return self.pka_root / "scott" / "inbox"

    @property
    def content_drafts(self) -> Path:
        return self.scott_inbox / "content-drafts"

    @property
    def briefing_archive(self) -> Path:
        return self.scott_inbox / "briefing-archive"

    @property
    def kb(self) -> Path:
        return self.pka_root / "kb"

    @property
    def shallan_inbox(self) -> Path:
        return self.pka_root / "agents" / "shallan" / "inbox"


def _load_settings() -> Settings:
    raw = os.environ.get("PKA_ROOT")
    if not raw:
        raise ConfigError(
            "PKA_ROOT environment variable is required. "
            "Set it to the absolute path of the PKA repository "
            "(e.g. /path/to/pka in dev, /data/pka in the container)."
        )
    root = Path(raw).expanduser().resolve()
    if not root.is_dir():
        raise ConfigError(f"PKA_ROOT does not exist or is not a directory: {root}")

    idle_raw = os.environ.get("RENARIN_IDLE_LOCK_SECONDS", "900")
    try:
        idle = int(idle_raw)
    except ValueError:
        idle = 900
    if idle < 0:
        idle = 0
    return Settings(pka_root=root, idle_lock_seconds=idle)


settings = _load_settings()
