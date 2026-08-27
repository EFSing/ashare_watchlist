"""Single explicit resolver for all repository data artifacts.

The resolver deliberately has no filesystem probing fallback.  Set
``ASHARE_DATA_ROOT`` for a deployment-specific data directory; otherwise the
repository's ``data`` directory is used.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping


DATA_ROOT_ENV = "ASHARE_DATA_ROOT"


def resolve_data_root(
    env: Mapping[str, str] | None = None,
    project_root: Path | None = None,
) -> Path:
    """Resolve the one configured data root without probing alternatives."""

    environ = os.environ if env is None else env
    configured = environ.get(DATA_ROOT_ENV, "").strip()
    if configured:
        return Path(configured).expanduser().resolve()

    root = project_root or Path(__file__).resolve().parents[1]
    return (root / "data").resolve()


@dataclass(frozen=True)
class DataPaths:
    """Paths shared by every watchlist reader and writer."""

    root: Path | None = None

    def __post_init__(self) -> None:
        root = self.root if self.root is not None else resolve_data_root()
        object.__setattr__(self, "root", Path(root).expanduser().resolve())

    @classmethod
    def from_env(
        cls,
        env: Mapping[str, str] | None = None,
        project_root: Path | None = None,
    ) -> "DataPaths":
        return cls(resolve_data_root(env=env, project_root=project_root))

    def watchlist_file(self, date_value: str) -> Path:
        date_text = str(date_value).replace("-", "")
        return self.root / f"watchlist_{date_text}.json"

    def watchlist_review_file(self, date_value: str) -> Path:
        date_text = str(date_value).replace("-", "")
        return self.root / f"watchlist_{date_text}_review.json"

    def watchlist_files(self) -> list[Path]:
        return sorted(self.root.glob("watchlist_????????.json"))

    def positions_file(self) -> Path:
        return self.root / "positions.json"

    def perf_tracker_file(self) -> Path:
        return self.root / "perf_tracker.json"

    def index_pairs_file(self) -> Path:
        return self.root / "index_pairs.json"

    def index_pairs_result_file(self) -> Path:
        return self.root / "index_pairs_result.json"

    def reports_dir(self) -> Path:
        return self.root / "reports"
