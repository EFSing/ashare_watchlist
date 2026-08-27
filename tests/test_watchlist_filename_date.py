import json

import pytest

from test_watchlist_schema import payload
from watchlist_schema import WatchlistIntegrityError, load_watchlist


def test_watchlist_filename_date_must_match_payload_date(tmp_path):
    path = tmp_path / "watchlist_20260821.json"
    path.write_text(json.dumps(payload()), encoding="utf-8")

    with pytest.raises(WatchlistIntegrityError, match="date"):
        load_watchlist(path)

