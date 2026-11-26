"""Offline DEVELOPMENT replay for the locked weak-market hypothesis."""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from hashlib import sha256
from itertools import product
from pathlib import Path
import gzip
import json
import math
import re
import subprocess

import exchange_calendars as xcals
import numpy as np
from numpy.lib.stride_tricks import sliding_window_view

import core_signal_replay as reference
from b_breakout_retest_v1_1 import evaluate_numeric_projection
from b_structure_volume_observation import FIELDS, TRANSITION, observe
from preview_b_shortlist import _position_metrics


ROOT = Path(__file__).resolve().parents[1]
PROTOCOL_COMMIT = "b30dd4979f47151ba4efa8ddf6ebca2add4ac10e"
PROTOCOL = "docs/research/weak_regime_panic_reversion_v1_protocol.md"
REPORT = "docs/research/weak_regime_panic_reversion_v1_report.md"
SUMMARY = "data/validation/weak_regime_panic_reversion_v1/summary.json"
REGISTRY = "data/governance/frozen_artifacts.json"
RAW = "data/validation/core_signal_validation/raw/"
MANIFEST = "data/validation/core_signal_validation_continuous_parts/core_signal_validation_manifest.json"
B_EVENTS = "data/validation/strategy_candidate_eligibility_v1/b_breakout_retest_eligibility_events.jsonl.gz"
YEARS = ("2023", "2024", "2025", "2026")
INPUTS = {
    RAW + "daily_k.parquet": (180203424, "61189a4850e2eb157453e28e5375e502e20d214508bbe70ea71066ca3e05e426"),
    RAW + "adjustment_factors.parquet": (295284, "a1b7d63c5826ccd3610dc9bdd949d82eeb0ba84ffad451bfb8bb30ca74962716"),
    RAW + "index_000001_SH_2023.json": (40966, "c118fb39d31065914740da150455fba2375d3bcaa83566730d265df0753bb51c"),
    RAW + "index_000001_SH_2024.json": (40983, "53fc9e9f0989e67f8a826614c5c8f260171cf081801bf752df6301e69f4ae4bf"),
    RAW + "index_000001_SH_2025.json": (41175, "27acba0bd5bfc0f54d349d7dbc41a86bf6836dfee3976a970cbb210b287f76a1"),
    RAW + "index_000001_SH_2026.json": (27109, "183f472a1699811edb2550f3ce99b2b05d06c23473b5e2acff0ad2431eaf1514"),
    MANIFEST: (523376, "008643a64e0070433f3d63dca8243f8dad294b049a7accb5d49af3597aae17b0"),
    B_EVENTS: (2506292, "8940a4a346ac6911ba669f84a9ceba7ef878b0ed0ce51edf673439b52aa056b9"),
}
START, END = "2023-06-30", "2026-08-28"
LABELS = ("DEVELOPMENT", "MAIN_BOARD_ST_UNVERIFIED_DEVELOPMENT_SAMPLE", "NO_VINTAGE_PROOF")
REGIMES = ("P0_ALL_NON_G2", "P1_MARKET_PANIC_PULSE")
PATTERNS = ("M1_PURE_EXTREME_STRETCH", "M2_PANIC_HAMMER_REJECTION", "M3_LOW_POS_EXHAUSTION")
EXITS = ("X1_TARGET_45_STOP_50_HOLD4", "X2_MA5_CLOSE_RECLAIM_NEXT_OPEN_HOLD5")
MAX_CONCURRENT_POSITIONS = 6
COOLDOWN = 3
COST_PP = 0.20
AMBIGUOUS = "AMBIGUOUS_SAME_BAR"
POSITIVE_INFINITY = "INF"


def allowed_path(root: Path, relative: str) -> Path:
    if relative not in {*INPUTS, REGISTRY, PROTOCOL, REPORT, SUMMARY}:
        raise RuntimeError(f"path outside research allowlist: {relative}")
    path = root / relative
    if path.resolve() != root / relative:
        raise RuntimeError(f"research path redirects outside its declared location: {relative}")
    return path


def lf(raw: bytes) -> bytes:
    return raw.replace(b"\r\n", b"\n")


def verify_protocol(root: Path) -> str:
    subprocess.run(["git", "merge-base", "--is-ancestor", PROTOCOL_COMMIT, "HEAD"],
                   cwd=root, check=True, capture_output=True)
    frozen = subprocess.check_output(["git", "show", f"{PROTOCOL_COMMIT}:{PROTOCOL}"], cwd=root)
    if lf(frozen) != lf(allowed_path(root, PROTOCOL).read_bytes()):
        raise RuntimeError("PROTOCOL_DRIFT: working protocol differs from preregistration")
    return sha256(lf(frozen)).hexdigest()


def verify_inputs(root: Path) -> dict:
    rows = json.loads(allowed_path(root, REGISTRY).read_bytes())["artifacts"]
    verified = {}
    for relative, (size, expected) in INPUTS.items():
        matching = [row for row in rows if row["logical_path"] == relative]
        path = allowed_path(root, relative)
        if relative == MANIFEST:
            data = lf(path.read_bytes())
            actual_size, actual_sha = len(data), sha256(data).hexdigest()
        else:
            actual_size = path.stat().st_size
            actual_sha = reference.file_sha256(path)
        if (len(matching) != 1 or matching[0]["file_sha256"] != expected
                or actual_size != size or actual_sha != expected):
            raise RuntimeError(f"FROZEN_INPUT_MISMATCH: {relative}")
        verified[relative] = {"bytes": size, "sha256": expected, "lf_normalized": relative == MANIFEST}
    return verified


def load_index(root: Path) -> tuple[list[dict], list[str], np.ndarray, np.ndarray, np.ndarray]:
    rows = []
    for year in YEARS:
        payload = json.loads(allowed_path(root, RAW + f"index_000001_SH_{year}.json").read_bytes())
        if payload["code"] != 0:
            raise RuntimeError(f"frozen index response failed: {year}")
        for row in payload["data"]["item"]:
            ms = int(row["date_ms"])
            rows.append({"ms": ms, "date": reference._date_from_ms(ms),
                         **{k: float(row[f"{k}_price"]) for k in ("open", "high", "low", "close")},
                         "volume": float(row["volume"])})
    rows.sort(key=lambda r: r["ms"])
    index_dates = [r["date"] for r in rows]
    dates = [d for d in index_dates if START <= d <= END]
    expected = xcals.get_calendar("XSHG").sessions_in_range(START, END).strftime("%Y-%m-%d").tolist()
    if len(set(index_dates)) != len(index_dates) or dates != expected or len(dates) != 769:
        raise RuntimeError("frozen benchmark dates do not match 769 XSHG sessions")
    start = index_dates.index(START)
    close = np.array([r["close"] for r in rows[:start + len(dates)]])
    if start < 24 or not np.all(np.isfinite(close) & (close > 0)):
        raise RuntimeError("frozen index lacks valid G2 history")
    ma20 = sliding_window_view(close, 20).mean(axis=1)
    g2 = (close[start:] > ma20[start - 19:]) & (ma20[start - 19:] > ma20[start - 24:-5])
    index_pulse = close[start:] / close[start - 1:-1] - 1 <= -0.012
    return rows, dates, np.array([r["ms"] for r in rows[start:start + len(dates)]]), g2, index_pulse


@dataclass
class Stock:
    dates: np.ndarray
    ohlc: np.ndarray
    volume: np.ndarray
    turnover: np.ndarray
    scale: np.ndarray
    offset: np.ndarray
    by_session: dict[int, int]

    def prices(self, anchor: int, start: int) -> np.ndarray:
        return self.scale[anchor] * ((self.ohlc[start:anchor + 1] - self.offset[start:anchor + 1, None])
                                     / self.scale[start:anchor + 1, None]) + self.offset[anchor]

    def convert(self, value: float, origin: int, anchor: int) -> float:
        if origin == anchor or (self.scale[origin] == self.scale[anchor]
                                and self.offset[origin] == self.offset[anchor]):
            return float(value)
        return float(self.scale[anchor] * ((value - self.offset[origin]) / self.scale[origin]) + self.offset[anchor])

    def locks(self, row: int) -> tuple[bool, bool]:
        op, hi, lo, _ = self.ohlc[row]
        if hi != lo:
            return False, False
        if row == 0:
            raise RuntimeError("cannot evaluate a price-limit bar without a pre-close")
        previous = self.convert(self.ohlc[row - 1, 3], row - 1, row)
        if previous <= 0:
            raise RuntimeError("unusable ex-rights pre-close for price-limit check")
        return bool(op >= previous * 1.10 - 0.005), bool(op <= previous * 0.90 + 0.005)

    def reclaim(self, row: int) -> bool:
        if row < 4:
            return False
        close = self.prices(row, row - 4)[:, 3]
        return bool(np.all(close > 0) and close[-1] >= close.mean())


def affine(dates: np.ndarray, events: list[tuple]) -> tuple[np.ndarray, np.ndarray]:
    scale, offset = np.ones(len(dates)), np.zeros(len(dates))
    current_scale, current_offset = 1.0, 0.0
    for ex_date, dividend, bonus, allotment, allotment_price in events:
        i = int(np.searchsorted(dates, ex_date))
        if i == len(dates):
            break
        # Earlier events apply to no observed old row and cancel from every conversion.
        if i == 0:
            continue
        denominator = 1 + bonus + allotment
        if not math.isfinite(denominator) or denominator <= 0:
            raise RuntimeError("invalid corporate-action denominator")
        current_scale /= denominator
        current_offset = (current_offset - dividend + allotment_price * allotment) / denominator
        scale[i:] = current_scale
        offset[i:] = current_offset
    if not np.all(np.isfinite(scale) & (scale > 0) & np.isfinite(offset)):
        raise RuntimeError("invalid affine coordinates")
    return scale, offset


def build_stocks(store: dict, events: dict, sessions: np.ndarray) -> dict[str, Stock]:
    stocks = {}
    for code, (start, end) in store["bounds"].items():
        if not re.fullmatch(r"(?:00\d{4}\.sz|60\d{4}\.sh)", code):
            continue
        sl = slice(start, end)
        dates = store["date_ms"][sl]
        scale, offset = affine(dates, events.get(code, []))
        first = int(np.searchsorted(dates, sessions[0]))
        last = int(np.searchsorted(dates, sessions[-1], side="right"))
        indices = np.searchsorted(sessions, dates[first:last])
        if not np.array_equal(sessions[indices], dates[first:last]):
            raise RuntimeError(f"off-calendar stock bar for {code}")
        stocks[code] = Stock(dates, np.column_stack([store[k][sl] for k in ("open", "high", "low", "close")]),
                             store["volume"][sl], store["turnover"][sl], scale, offset,
                             dict(zip(indices.tolist(), range(first, last))))
    return stocks


def verify_affine(store: dict, events: dict, stocks: dict[str, Stock], sessions: np.ndarray) -> dict:
    candidates = []
    for code, stock in sorted(stocks.items()):
        for event in events.get(code, []):
            date = event[0]
            row = int(np.searchsorted(stock.dates, date))
            if 249 <= row < len(stock.dates) and sessions[0] <= stock.dates[row] <= sessions[-1]:
                candidates.append((code, date, row))
    if len(candidates) < 500:
        raise RuntimeError("fewer than 500 eligible frozen adjustment witnesses")
    witnesses = [candidates[i * (len(candidates) - 1) // 499] for i in range(500)]
    maximum = 0.0
    for code, _date, row in witnesses:
        stock = stocks[code]
        beginning = store["bounds"][code][0]
        bars = reference._adjusted_bars(store, beginning + row - 249, beginning + row + 1,
                                        events[code], int(stock.dates[row]))
        expected = np.array([[b[k] for k in ("open", "high", "low", "close")] for b in bars])
        maximum = max(maximum, float(np.max(np.abs(stock.prices(row, row - 249) - expected))))
    if maximum >= 1e-11:
        raise RuntimeError(f"affine parity failed: {maximum:.17g}")
    return {"witnesses": len(witnesses), "eligible_corporate_actions": len(candidates),
            "max_abs_ohlc_error": maximum, "witness_sha256": sha256(json.dumps(witnesses).encode()).hexdigest()}


def weak_signals(stocks: dict[str, Stock], g2: np.ndarray, index_pulse: np.ndarray) -> tuple[list, np.ndarray, dict]:
    by_pattern = [[[] for _ in g2] for _ in PATTERNS]
    eligible, falls, oversold = np.zeros((3, len(g2)), dtype=int)
    for code, stock in stocks.items():
        pairs = [(d, row) for d, row in stock.by_session.items() if row >= 249]
        if not pairs:
            continue
        days, rows = np.array(pairs).T
        norm_close = (stock.ohlc[:, 3] - stock.offset) / stock.scale
        close20 = (stock.scale[rows, None] * sliding_window_view(norm_close, 20)[rows - 19]
                   + stock.offset[rows, None])
        valid = (close20 > 0).all(axis=1)
        days, rows, close20 = days[valid], rows[valid], close20[valid]
        close20[:, -1] = stock.ohlc[rows, 3]
        ret1 = close20[:, -1] / close20[:, -2] - 1
        ret5 = close20[:, -1] / close20[:, -6] - 1
        bias = close20[:, -1] / close20.mean(axis=1) - 1
        eligible[days] += 1
        falls[days] += ret1 <= -0.04
        oversold[days] += bias <= -0.08
        common = ((~g2[days]) & (ret1 > -0.092) & (bias <= -0.08)
                  & (ret5 <= -0.06) & (stock.ohlc[rows, 3] > 3))
        for j in np.flatnonzero(common):
            d, row = int(days[j]), int(rows[j])
            if np.median(stock.turnover[row - 19:row + 1]) < 50_000_000:
                continue
            prices = stock.prices(row, row - 249)
            if not np.all(prices > 0):
                continue
            _, hi, lo, close = stock.ohlc[row]
            floor, ceiling = prices[:, 2].min(), prices[:, 1].max()
            pos = (close - floor) / (ceiling - floor) if ceiling > floor else 0.5
            clv = (close - lo) / (hi - lo) if hi > lo else -math.inf
            volume, base_volume = stock.volume[row], np.median(stock.volume[row - 20:row])
            key = (round(float(bias[j]), 10), round(float(pos), 10), code)
            if bias[j] <= -0.10 and ret5[j] <= -0.08:
                by_pattern[0][d].append(key)
            if ((hi - lo) / close20[j, -2] >= 0.04 and clv >= 0.55
                    and base_volume > 0 and volume >= 1.2 * base_volume):
                by_pattern[1][d].append(key)
            if (pos <= 0.50 and close / prices[-61, 3] - 1 <= 0.15
                    and ret1[j] > close20[j, -2] / close20[j, -3] - 1
                    and clv >= 0.45 and volume <= 1.2 * base_volume):
                by_pattern[2][d].append(key)
    pulse = (~g2) & (((eligible > 0) & ((falls * 100 >= eligible * 12)
                     | (oversold * 100 >= eligible * 20))) | index_pulse)
    ranked = [[[entry[2] for entry in sorted(entries)] for entries in days] for days in by_pattern]
    return ranked, pulse, {"g2_days": int(g2.sum()), "p0_days": int((~g2).sum()),
                            "p1_days": int(pulse.sum()), "breadth_days_with_members": int((eligible > 0).sum()),
                            "p1_index_pulse_days": int(((~g2) & index_pulse).sum())}


def b_signals(root: Path, stocks: dict, store: dict, events: dict, dates: list[str],
              g2: np.ndarray, index: list[dict]) -> tuple[list, dict]:
    positions = {d: i for i, d in enumerate(dates)}
    index_dates = {r["date"]: i for i, r in enumerate(index)}
    ranked = [[] for _ in dates]
    seen = set()
    counts = Counter()
    with gzip.open(allowed_path(root, B_EVENTS), "rt", encoding="utf-8") as stream:
        for line in stream:
            event = json.loads(line)
            date, code, execution = (event[k] for k in ("signal_date", "symbol", "earliest_execution_date"))
            if (date, code) in seen or date not in positions or event["as_of_date"] != date:
                raise RuntimeError("invalid frozen B qualification identity")
            seen.add((date, code))
            day = positions[date]
            if day + 1 < len(dates) and execution != dates[day + 1]:
                raise RuntimeError("frozen B earliest execution differs from XSHG T+1")
            if code not in stocks or not g2[day]:
                continue
            counts["g2_main_board_formal_events"] += 1
            stock = stocks[code]
            row = stock.by_session[day]
            if row < 249:
                continue
            begin = max(0, row - 259)
            base = store["bounds"][code][0]
            bars = reference._adjusted_bars(store, base + begin, base + row + 1,
                                            events.get(code, []), int(stock.dates[row]))
            metrics = _position_metrics(bars, date)
            if any(metrics[k] is None for k in ("pos250", "chg20", "chg60")):
                counts["position_unavailable"] += 1
                continue
            pos, chg20, chg60 = (round(metrics[k], 12) for k in ("pos250", "chg20", "chg60"))
            if pos > 0.55 or chg20 > 0.20 or chg60 > 0.30:
                continue
            counts["l1_pass"] += 1
            # The frozen provider key includes an exchange suffix. Report observations use six digits.
            observation = observe({"signal_id": f"{date}:{code}", "code": code.split(".")[0]}, bars, date)
            volume = observation["volume"]
            v1, v2 = (volume[k] for k in FIELDS[:2])
            if observation["structure"]["state"] not in ("EARLY_PULLBACK", TRANSITION):
                counts["structure_outside_v2"] += 1
                continue
            if (any(volume.get("missing_reason", {}).get(k) for k in FIELDS[:2])
                    or v1 is None or v2 is None or not (0 <= v1 <= 1 and 0 <= v2 < math.inf)):
                counts["volume_unavailable"] += 1
                continue
            i = index_dates[date]
            projection = evaluate_numeric_projection(
                symbol=code, signal_date=date, earliest_execution_date=execution,
                bars=tuple(np.array([bar[k] for bar in bars]) for k in ("close", "volume", "high", "low")),
                index_bars=index[:i + 1],
            )
            if projection["status"] != "QUALIFIED_LEGACY_BASELINE":
                raise RuntimeError(f"frozen B qualification did not reproduce for {date}/{code}")
            trigger, stop, target = (projection[k] for k in ("trigger", "stop", "target"))
            if any(v is None for v in (stop, trigger, target)) or not 0 < stop < trigger <= max(bars[-1]["close"], trigger) < target:
                counts["reference_levels_unusable"] += 1
                continue
            ranked[day].append((pos, round(v1, 12), code, BOrder(row, trigger, stop, target)))
    counts["frozen_qualification_events"] = len(seen)
    counts["v2_eligible_events"] = sum(map(len, ranked))
    if not counts["v2_eligible_events"]:
        raise RuntimeError(f"B benchmark unavailable: no qualifying V2 events ({dict(counts)})")
    return [[(code, order) for _, _, code, order in sorted(rows)] for rows in ranked], dict(counts)


@dataclass(frozen=True)
class BOrder:
    origin: int
    trigger: float
    stop: float
    target: float


@dataclass
class Position:
    signal: int
    entry: int
    basis: int
    price: float
    stop: float
    target: float | None
    level_basis: int
    deadline: int
    due: str | None = None
    mark: float = 0.0

    def net(self, stock: Stock, row: int, price: float) -> float:
        entry_basis = stock.convert(self.price, self.basis, row)
        if min(entry_basis, price) <= 0:
            raise RuntimeError("non-positive price in trade measurement")
        return (price / entry_basis - 1) * 100 - COST_PP


@dataclass(frozen=True)
class Result:
    signal: int
    status: str
    exit: int | None = None
    net: float | None = None


def sell(stock: Stock, trade: Position, day: int, row: int, policy: str) -> tuple[str, float] | None:
    op, hi, lo, close = stock.ohlc[row]
    if day == trade.entry:
        if policy == "X2" and stock.reclaim(row):
            trade.due = "MA5_NEXT_OPEN"
        if policy == "B" and day >= trade.deadline:
            trade.due = "TIME_EXIT_DEFERRED"
        return None
    if policy == "X2" and day >= trade.deadline and trade.due is None:
        trade.due = "TIME_EXIT_OPEN"
    stop = stock.convert(trade.stop, trade.level_basis, row)
    target = None if trade.target is None else stock.convert(trade.target, trade.level_basis, row)
    _, lower_locked = stock.locks(row)
    if lower_locked:
        if trade.due is None and (lo <= stop or day >= trade.deadline):
            trade.due = "LOCKED_EXIT_NEXT_OPEN"
        elif trade.due is None and policy == "X2" and stock.reclaim(row):
            trade.due = "MA5_NEXT_OPEN"
        return None
    if trade.due is not None:
        return trade.due, float(op)
    if op <= stop:
        return "STOP_GAP", float(op)
    if target is not None and op >= target:
        return "TARGET_GAP", float(op)
    if lo <= stop:
        return (AMBIGUOUS if target is not None and hi >= target else "STOP"), stop
    if target is not None and hi >= target:
        return "TARGET", target
    if day >= trade.deadline:
        return "TIME_EXIT_CLOSE", float(close)
    if policy == "X2" and stock.reclaim(row):
        trade.due = "MA5_NEXT_OPEN"
    return None


def replay(stocks: dict[str, Stock], candidates: list, allowed: np.ndarray, policy: str,
           mode: str) -> tuple[list[Result], np.ndarray, int]:
    b = policy == "B"
    daily_cap = 3 if b else 2 if mode == "TOP2" else math.inf
    cap = MAX_CONCURRENT_POSITIONS if mode == "TOP2" else math.inf
    cooldown = 5 if b else COOLDOWN
    pending: dict[str, tuple[int, BOrder | None]] = {}
    positions: dict[str, Position] = {}
    blocked_through: dict[str, int] = {}
    results = []
    pnl = np.zeros(len(candidates))
    peak_positions = 0
    for day, todays_candidates in enumerate(candidates):
        for code, (signal, order) in list(pending.items()):
            stock = stocks[code]
            row = stock.by_session.get(day)
            fill = None
            if row is not None and not stock.locks(row)[0]:
                op, hi = stock.ohlc[row, :2]
                if order is None:
                    fill = float(op)
                else:
                    trigger = stock.convert(order.trigger, order.origin, row)
                    if hi >= trigger:
                        fill = max(float(op), trigger)
            if fill is None:
                if not b or day >= signal + 10:
                    del pending[code]
                    results.append(Result(signal, "EXPIRED_UNTRIGGERED" if b else "UNBUYABLE_SKIP"))
                continue
            del pending[code]
            if order is None:
                stop, target = (fill * 0.95, fill * 1.045) if policy == "X1" else (fill * 0.94, None)
                positions[code] = Position(signal, day, row, fill, stop, target, row,
                                           day + (4 if policy == "X1" else 5))
            else:
                positions[code] = Position(signal, day, row, fill, order.stop, order.target,
                                           order.origin, signal + 10)
        peak_positions = max(peak_positions, len(positions))
        for code, trade in list(positions.items()):
            stock = stocks[code]
            row = stock.by_session.get(day)
            if row is None:
                if day >= trade.deadline and trade.due is None:
                    trade.due = "TIME_EXIT_DEFERRED"
                continue
            outcome = sell(stock, trade, day, row, policy)
            if outcome is not None:
                status, price = outcome
                net = trade.net(stock, row, price)
                pnl[day] += net - trade.mark
                results.append(Result(trade.signal, status, day, net))
                del positions[code]
                blocked_through[code] = day + cooldown
            else:
                mark = trade.net(stock, row, float(stock.ohlc[row, 3]))
                pnl[day] += mark - trade.mark
                trade.mark = mark
        if not allowed[day]:
            continue
        selected = 0
        for item in todays_candidates:
            if selected >= daily_cap or len(pending) + len(positions) >= cap:
                break
            code, order = item if b else (item, None)
            if code in pending or code in positions or blocked_through.get(code, -1) >= day:
                continue
            selected += 1
            pending[code] = day, order
            if b:
                blocked_through[code] = day + cooldown
    for signal, _order in pending.values():
        results.append(Result(signal, "ENTRY_AFTER_CUTOFF" if signal == len(candidates) - 1
                              else "PENDING_AT_CUTOFF"))
    results.extend(Result(trade.signal, "OPEN_AT_CUTOFF") for trade in positions.values())
    return results, pnl, peak_positions


def profit_factor(values: list[float]) -> float | str | None:
    profit = math.fsum(value for value in values if value > 0)
    loss = -math.fsum(value for value in values if value < 0)
    return profit / loss if loss else POSITIVE_INFINITY if profit else None


def trade_metrics(results: list[Result]) -> dict:
    closed = [r.net for r in results if r.net is not None and r.status != AMBIGUOUS]
    pessimistic = [r.net for r in results if r.net is not None]
    statuses = Counter(r.status for r in results)
    ambiguity, open_count = statuses[AMBIGUOUS], statuses["OPEN_AT_CUTOFF"]
    triggered = len(pessimistic) + open_count
    return {"accepted_orders": len(results), "triggered": triggered, "closed": len(closed),
            "ambiguous": ambiguity, "ambiguous_rate_pct": ambiguity * 100 / triggered if triggered else None,
            "open_at_cutoff": open_count, "net_avg_return_pct": math.fsum(closed) / len(closed) if closed else None,
            "pessimistic_net_avg_pct": math.fsum(pessimistic) / len(pessimistic) if pessimistic else None,
            "net_win_rate_pct": sum(v > 0 for v in closed) * 100 / len(closed) if closed else None,
            "net_profit_factor": profit_factor(closed), "net_realized_total_pp": math.fsum(closed),
            "pessimistic_realized_total_pp": math.fsum(pessimistic), "status_counts": dict(statuses)}


def pnl_metrics(pnl: np.ndarray, by_year: dict[str, np.ndarray]) -> dict:
    equity = np.cumsum(pnl)
    with_initial = np.concatenate(([0.0], equity))
    maxdd = float(np.max(np.maximum.accumulate(with_initial) - with_initial))
    total = float(equity[-1])
    return {"yearly_net_pnl_pp": {year: float(pnl[idx].sum()) for year, idx in by_year.items()},
            "total_net_pnl_pp": total, "max_drawdown_pp": maxdd,
            "return_over_max_drawdown": total / maxdd if maxdd else POSITIVE_INFINITY if total > 0 else None,
            "daily_equity_pp": equity.round(10).tolist()}


def block_sums(values: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    size, block = len(values), 20
    starts = rng.integers(0, size - block + 1, size=(5000, math.ceil(size / block)))
    prefix = np.concatenate(([0.0], np.cumsum(values)))
    widths = np.minimum(block, size - np.arange(starts.shape[1]) * block)
    return np.sum(prefix[starts + widths] - prefix[starts], axis=1)


def interval(values: np.ndarray) -> list[float]:
    return np.quantile(values, [0.025, 0.975], method="linear").tolist()


def day_bootstrap(results: list[Result], n_days: int) -> dict:
    daily = defaultdict(list)
    for r in results:
        if r.net is not None and r.status != AMBIGUOUS:
            daily[r.signal].append(r.net)
    returns = np.zeros(n_days)
    for day, values in daily.items():
        returns[day] = math.fsum(values) / len(values)
    return {"mean_pct": float(returns.mean()), "ci95_pct": interval(block_sums(returns, bootstrap_rng()) / n_days),
            "session_count": n_days, "sessions_with_closed_trades": len(daily)}


def bootstrap_rng() -> np.random.Generator:
    return np.random.default_rng(20261127)


def numeric(metric: float | str | None) -> float:
    return -math.inf if metric is None else math.inf if metric == POSITIVE_INFINITY else float(metric)


def evaluate_gates(results: list[Result], total: dict, annual: dict, weak_years: dict, pnl: np.ndarray,
                   baseline: dict, combination: dict, by_year: dict) -> dict:
    rng = bootstrap_rng()
    earlier, later = pnl[by_year["2023"]], pnl[by_year["2026"]]
    difference = float(earlier.sum() + later.sum())
    contrast = interval(block_sums(earlier, rng) + block_sums(later, rng))
    boot = day_bootstrap(results, len(pnl))
    gate1 = total["closed"] >= 120 and weak_years["closed"] >= 60 and numeric(total["ambiguous_rate_pct"]) <= 5
    gate2 = (all(numeric(annual[y][k]) > 0 for y in ("2023", "2026")
                 for k in ("net_avg_return_pct", "pessimistic_net_avg_pct"))
             and numeric(weak_years["net_profit_factor"]) >= 1.20)
    gate3 = (numeric(total["net_avg_return_pct"]) >= 0.50 and numeric(total["net_win_rate_pct"]) >= 52
             and numeric(total["net_profit_factor"]) >= 1.25)
    gate4 = (difference > 0 and contrast[0] > 0 and baseline["return_over_max_drawdown"] is not None
             and numeric(combination["return_over_max_drawdown"]) > numeric(baseline["return_over_max_drawdown"]))
    gate5 = boot["mean_pct"] > 0 and boot["ci95_pct"][0] > 0
    gates = [bool(g) for g in (gate1, gate2, gate3, gate4, gate5)]
    return {"passes": gates, "bootstrap": boot,
            "weak_year_combination_gain_pp": difference, "weak_year_gain_ci95_pp": contrast,
            "p1_or_p0_combo_pass": gates[3],
            "dual_year_positive": all(numeric(annual[y]["net_avg_return_pct"]) > 0 for y in ("2023", "2026"))}


def decision(rows: list[dict]) -> dict:
    top2 = [r for r in rows if r["mode"] == "TOP2"]
    priority = lambda r: (r["regime"] != REGIMES[1], r["exit"] != EXITS[1], r["pattern"])
    adopted = sorted((r for r in top2 if all(r["gates"]["passes"])), key=priority)
    borderline = [r["id"] for r in top2 if all(r["gates"]["passes"][:4])
                  and r["gates"]["bootstrap"]["mean_pct"] > 0
                  and r["gates"]["bootstrap"]["ci95_pct"][0] <= 0 <= r["gates"]["bootstrap"]["ci95_pct"][1]]
    positive = [r["id"] for r in top2 if r["gates"]["dual_year_positive"]]
    if adopted:
        return {"decision": "ADOPT", "recommendation": adopted[0]["id"], "dual_year_positive": positive,
                "reason": "RECOMMEND_WEAK_REGIME_PROSPECTIVE_SHADOW"}
    if borderline:
        return {"decision": "NEEDS_MORE_EVIDENCE", "recommendation": None, "dual_year_positive": positive,
                "reason": "DAY_LEVEL_CI_INCLUDES_ZERO", "borderline_candidates": borderline}
    return {"decision": "REJECT", "recommendation": None, "dual_year_positive": positive,
            "reason": "NO_CANDIDATE_PASSED_ALL_GATES" if positive else "NO_DUAL_YEAR_POSITIVE_TOP2"}


def run(root: Path) -> dict:
    protocol_hash = verify_protocol(root)
    inputs = verify_inputs(root)
    index, dates, sessions, g2, index_pulse = load_index(root)
    store, _ = reference._load_stock_store(allowed_path(root, RAW + "daily_k.parquet"))
    events, _ = reference._load_events(allowed_path(root, RAW + "adjustment_factors.parquet"))
    stocks = build_stocks(store, events, sessions)
    parity = verify_affine(store, events, stocks, sessions)
    print(f"769 XSHG sessions; {parity['witnesses']} adjustment witnesses verified", flush=True)
    ranked_b, b_counts = b_signals(root, stocks, store, events, dates, g2, index)
    ranked, pulse, coverage = weak_signals(stocks, g2, index_pulse)
    year_ids = np.array([d[:4] for d in dates])
    by_year = {yr: np.flatnonzero(year_ids == yr) for yr in YEARS}
    b_results, b_pnl, b_peak = replay(stocks, ranked_b, g2, "B", "B_V2")
    b_metrics = pnl_metrics(b_pnl, by_year)
    if not trade_metrics(b_results)["closed"]:
        raise RuntimeError("B benchmark unavailable: no resolved B trades")
    print(f"B benchmark reconstructed; {coverage['p0_days']} NOT G2 days, {coverage['p1_days']} panic days", flush=True)
    rows = []
    for p, m, x, mode in product(range(2), range(3), range(2), ("TOP2", "S_ALL")):
        identifier = f"P{p}/M{m + 1}/X{x + 1}/{mode}"
        allowed = pulse if p else ~g2
        results, pnl, peak = replay(stocks, ranked[m], allowed, f"X{x + 1}", mode)
        total = trade_metrics(results)
        annual = {yr: trade_metrics([r for r in results if year_ids[r.signal] == yr]) for yr in YEARS}
        weak_years = trade_metrics([r for r in results if year_ids[r.signal] in ("2023", "2026")])
        row = {"id": identifier, "regime": REGIMES[p], "pattern": PATTERNS[m], "exit": EXITS[x], "mode": mode,
               "total": total, "annual": annual, "2023_plus_2026": weak_years, "peak_concurrent_positions": peak}
        if mode == "TOP2":
            combination = pnl_metrics(b_pnl + pnl, by_year)
            row.update(weak_equity=pnl_metrics(pnl, by_year), combined_equity=combination,
                       gates=evaluate_gates(results, total, annual, weak_years, pnl, b_metrics, combination, by_year))
        rows.append(row)
    return {"study": "WEAK_REGIME_PANIC_MEAN_REVERSION_V1", "identity": "NEW_INDEPENDENT_RESEARCH_HYPOTHESIS",
            "sample_labels": list(LABELS), "protocol_commit": PROTOCOL_COMMIT, "protocol_lf_sha256": protocol_hash,
            "frozen_inputs": inputs, "affine_parity": parity, "calendar": dates,
            "coverage": {**coverage, "main_board_symbols": len(stocks),
                         "xshg_sessions_by_year": {yr: len(idx) for yr, idx in by_year.items()}},
            "round_trip_cost_bps": 20, "bootstrap": {"block_sessions": 20, "replicates": 5000, "seed": 20261127},
            "b_v2": {"label": "INDEPENDENT_FROZEN_QUALIFICATION_PANEL", "qualification": b_counts,
                     "trades": trade_metrics(b_results), "peak_concurrent_positions": b_peak, "equity": b_metrics},
            "matrix": rows, **decision(rows)}


def fmt(value: float | str | None, decimals: int = 3) -> str:
    if value is None:
        return "—"
    if value == POSITIVE_INFINITY:
        return "∞"
    return f"{value:.{decimals}f}"


def md_table(headers: list[str], rows: list[list]) -> list[str]:
    return ["| " + " | ".join(map(str, row)) + " |" for row in [headers, ["---"] * len(headers), *rows]]


def render_report(summary: dict, summary_sha: str) -> str:
    rows = summary["matrix"]
    top2 = [r for r in rows if r["mode"] == "TOP2"]
    b = summary["b_v2"]
    coverage = summary["coverage"]
    verdict = summary["decision"]
    message = {
        "NO_DUAL_YEAR_POSITIVE_TOP2": "12 组 TOP2 中，没有一组在 2023 与 2026 均取得正的扣费单笔均值。冻结样本未支持这套主板日线超跌反抽规则能稳定覆盖成本与连续急跌风险。",
        "NO_CANDIDATE_PASSED_ALL_GATES": "部分 TOP2 在 2023 与 2026 都录得正的主统计净均值，全部候选均有至少一项预注册门槛未通过。",
        "DAY_LEVEL_CI_INCLUDES_ZERO": "有候选通过前四道门槛且日均为正，95% 区间含零。未来独立提案需用能提高日级净均值估计精度的前瞻样本补齐证据。",
        "RECOMMEND_WEAK_REGIME_PROSPECTIVE_SHADOW": f"按预注册优先级推荐 `{summary['recommendation']}` 提交独立前瞻观察提案。",
    }[summary["reason"]]
    lines = ["# 弱市恐慌超跌均值回归 V1 研究报告", "", f"**决定 `{verdict}`。** {message}", "",
             "任务归类保持为非阻塞 `research question`，走 STRICT PATH。研究身份为 `NEW_INDEPENDENT_RESEARCH_HYPOTHESIS`。",
             f"覆盖 {START} 至 {END} 共 {len(summary['calendar'])} 个 XSHG 交易日，2023 和 2026 为部分年份。",
             "样本固定为 `DEVELOPMENT`、`MAIN_BOARD_ST_UNVERIFIED_DEVELOPMENT_SAMPLE` 与 `NO_VINTAGE_PROOF`。",
             "主板涨跌停代理用因果除权前收与 10% 阈值。ST 历史身份和日线限价内排队无法从冻结文件核实。", "",
             f"协议提交 `{summary['protocol_commit']}`，LF SHA-256 `{summary['protocol_lf_sha256']}`。",
             f"汇总 JSON SHA-256 `{summary_sha}`。",
             f"复权对照 {summary['affine_parity']['witnesses']} 个冻结除权样本，OHLC 最大绝对误差 "
             f"`{summary['affine_parity']['max_abs_ohlc_error']:.17g}`。",
             f"`G2` 共 {coverage['g2_days']} 日，`P0` 放行 {coverage['p0_days']} 日，`P1` 放行 {coverage['p1_days']} 日。", "",
             "## 24 组交易汇总", "",
             "主统计剔除双触及模糊单，悲观列将其按止损计入。净收益已扣每笔 20 bps，均值和胜率用百分数。", ""]
    lines += md_table(["组合", "已触发", "主统计结案", "模糊", "模糊率%", "不可买", "截止未平仓", "净均值%",
                       "悲观均值%", "胜率%", "获利因子", "并发峰值"], [
        [r["id"], t["triggered"], t["closed"], t["ambiguous"], fmt(t["ambiguous_rate_pct"]),
         t["status_counts"].get("UNBUYABLE_SKIP", 0), t["open_at_cutoff"], fmt(t["net_avg_return_pct"]),
         fmt(t["pessimistic_net_avg_pct"]), fmt(t["net_win_rate_pct"]), fmt(t["net_profit_factor"]),
         r["peak_concurrent_positions"]] for r in rows for t in [r["total"]]])
    lines += ["", "## 分年交易表现", "", "按信号年归组。各年单元格依次为主统计结案笔数、净均值%、悲观净均值%。", ""]
    lines += md_table(["组合", *YEARS, "2023+2026 结案", "2023+2026 获利因子"], [
        [r["id"], *[f"{a['closed']} / {fmt(a['net_avg_return_pct'])} / {fmt(a['pessimistic_net_avg_pct'])}"
                    for a in r["annual"].values()], r["2023_plus_2026"]["closed"],
         fmt(r["2023_plus_2026"]["net_profit_factor"])] for r in rows])
    lines += ["", "## TOP2 五项门槛", "",
              "日级检验对信号日已结案交易等权，无有效结案日计零。采用 20 交易日移动块，5,000 次，种子 `20261127`。", ""]
    lines += md_table(["组合", "样本", "双年", "全期", "组合", "Bootstrap", "日均%", "日均 95% CI（%）",
                       "弱年组合增益 pp", "增益 95% CI（pp）"], [
        [r["id"], *["过" if ok else "未过" for ok in g["passes"]], fmt(g["bootstrap"]["mean_pct"]),
         " / ".join(map(fmt, g["bootstrap"]["ci95_pct"])), fmt(g["weak_year_combination_gain_pp"]),
         " / ".join(map(fmt, g["weak_year_gain_ci95_pp"]))] for r in top2 for g in [r["gates"]]])
    lines += ["", "## B（G2+L1）+ 弱市候选（TOP2）顺逆风组合曲线对照", "",
              f"B 从冻结正式资格重建主板 G2+L1 独立面板。V2 过滤后有 {b['qualification']['v2_eligible_events']} 个候选事件，"
              f"E0 主统计结案 {b['trades']['closed']} 笔。B 与弱市腿使用相同日历、名义交易单位和成本。",
              "权益以每日实现与未平仓盯市损益累计，模糊单按止损。组合叠加两腿的日度 pp，允许既有持仓跨市场门重叠。"
              "完整日度曲线随汇总 JSON 交付。", ""]

    def equity_row(label: str, equity: dict) -> list:
        return [label, *map(fmt, equity["yearly_net_pnl_pp"].values()), fmt(equity["total_net_pnl_pp"]),
                fmt(equity["max_drawdown_pp"]), fmt(equity["return_over_max_drawdown"])]

    comparison = [equity_row("B V2", b["equity"])]
    for row in top2:
        comparison.append(equity_row(row["id"], row["weak_equity"]))
        comparison.append(equity_row("B + " + row["id"], row["combined_equity"]))
    lines += md_table(["曲线", *[f"{year} pp" for year in YEARS], "累计 pp", "最大回撤 pp", "收益/回撤"], comparison)
    lines += ["", "## 输入与适用范围", "",
              "完整文件哈希、LF 归一规则、年内会话数及结果状态分解见汇总 JSON。", "",
              "组合衡量固定名义单位下的收益和回撤，实际账户的现金占用和交易摩擦需由前瞻观察独立验证。"
              "研究决定只用于评估前瞻观察提案，既有生产日报与 B 运行路径可继续。", ""]
    return "\n".join(lines)


def main() -> None:
    summary = run(ROOT)
    raw = (json.dumps(summary, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8")
    checksum = sha256(raw).hexdigest()
    report = render_report(summary, checksum)
    path = allowed_path(ROOT, SUMMARY)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    allowed_path(ROOT, REPORT).write_bytes(report.encode("utf-8"))
    print(f"{summary['decision']} summary_sha256={checksum}", flush=True)


if __name__ == "__main__":
    main()
