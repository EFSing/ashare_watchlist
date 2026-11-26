"""Replay the frozen defensive ETF matrix and the matched B V2 accounts."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from dataclasses import dataclass, field
import gzip
from hashlib import sha256
import json
import math
from pathlib import Path
import re
import subprocess

import numpy as np
import pandas as pd
from numpy.lib.stride_tricks import sliding_window_view

import core_signal_replay as core
from b_breakout_retest_v1_1 import evaluate_numeric_projection
from b_structure_volume_observation import FIELDS, TRANSITION, observe
from fetch_defensive_etf_validation_inputs import CUTOFF, FIRST_SIGNAL, ROOT, START, SYMBOLS, sessions, validate
from preview_b_shortlist import _position_metrics


PROTOCOL_COMMIT = "1d1f0177e6e588bfb0c3fa4371e248cbfbb168c4"
PROTOCOL = "docs/research/defensive_etf_non_g2_v1_protocol.md"
REPORT = "docs/research/defensive_etf_non_g2_v1_report.md"
STUDY = "DEFENSIVE_ETF_NON_G2_V1"
DATA = "data/validation/defensive_etf_non_g2_v1"
ETF_RAW = f"{DATA}/raw"
CORE_RAW = "data/validation/core_signal_validation/raw"
REGISTRY = "data/governance/frozen_artifacts.json"
CONTINUOUS = "data/validation/core_signal_validation_continuous_parts/core_signal_validation_manifest.json"
STOCKS = f"{CORE_RAW}/daily_k.parquet"
ACTIONS = f"{CORE_RAW}/adjustment_factors.parquet"
B_EVENTS = "data/validation/strategy_candidate_eligibility_v1/b_breakout_retest_eligibility_events.jsonl.gz"
YEARS = ("2023", "2024", "2025", "2026")
WEAK_YEARS = ("2023", "2026")
INDEX = tuple(f"{CORE_RAW}/index_000001_SH_{year}.json" for year in YEARS)
REGISTRY_INPUTS = {STOCKS, ACTIONS, *INDEX, CONTINUOUS, B_EVENTS}
ETF_FILES = {f"{symbol.replace('.', '_')}_{kind}.json" for symbol in SYMBOLS
             for kind in ("ohlcv", "dividends", "nav")}
INPUTS = REGISTRY_INPUTS | {REGISTRY, f"{ETF_RAW}/input_manifest.json"} | {
    f"{ETF_RAW}/{name}" for name in ETF_FILES
}
LF_FILES = {PROTOCOL, REGISTRY, CONTINUOUS}
PAYMENT = {"2025-09-23": "2025-09-26", "2025-12-26": "2025-12-31",
           "2026-03-25": "2026-03-30", "2026-06-25": "2026-06-30"}
REGIMES = ("R0_IMMEDIATE_NON_G2", "R1_CONFIRM3_NON_G2")
ALLOCATIONS = ("A1_MACRO_SHIELD_CAPPED", "A2_TRIPLE_INV_VOL20", "A3_PURE_BOND_PARK")
B_SIDE = 0.001
SLOTS = 6
EPS = 1e-12


def allowed_path(root: Path, relative: str) -> Path:
    if relative not in INPUTS | {PROTOCOL}:
        raise ValueError(f"input path is outside the protocol allowlist: {relative}")
    path = root / relative
    if path.resolve(strict=True) != path or not path.is_file():
        raise ValueError(f"input path is redirected or is not a regular file: {relative}")
    return path


def verify_protocol(root: Path) -> bytes:
    try:
        subprocess.run(["git", "merge-base", "--is-ancestor", PROTOCOL_COMMIT, "HEAD"],
                       cwd=root, check=True, capture_output=True)
        frozen = subprocess.check_output(["git", "show", f"{PROTOCOL_COMMIT}:{PROTOCOL}"], cwd=root)
    except subprocess.CalledProcessError as error:
        raise ValueError("preregistration commit is unavailable or is not an ancestor of HEAD") from error
    if frozen != allowed_path(root, PROTOCOL).read_bytes().replace(b"\r\n", b"\n"):
        raise ValueError("preregistration protocol differs from the committed bytes")
    return frozen


def verify_inputs(root: Path, protocol: bytes) -> dict:
    rows = re.findall(rb"^\| `([^`]+)` \| ([0-9]+) \| `([0-9a-f]{64})` \|$", protocol, re.M)
    expected = {path.decode(): {"bytes": int(size), "sha256": digest.decode()}
                for path, size, digest in rows}
    if set(expected) != INPUTS or len(rows) != len(INPUTS):
        raise ValueError("protocol input identities do not match the allowlist")
    for name, identity in expected.items():
        path = allowed_path(root, name)
        if name in LF_FILES:
            raw = path.read_bytes().replace(b"\r\n", b"\n")
            actual = len(raw), sha256(raw).hexdigest()
        else:
            with path.open("rb") as stream:
                actual = path.stat().st_size, sha256_stream(stream)
        if actual != (identity["bytes"], identity["sha256"]):
            raise ValueError(f"frozen input identity mismatch: {name}")
    registry = json.loads(allowed_path(root, REGISTRY).read_bytes())
    artifacts = {row["logical_path"]: row["file_sha256"] for row in registry["artifacts"]
                 if row["logical_path"] in REGISTRY_INPUTS}
    if artifacts != {name: expected[name]["sha256"] for name in REGISTRY_INPUTS}:
        raise ValueError("preregistration and the frozen artifact registry differ")
    manifest = read_json(root, f"{ETF_RAW}/input_manifest.json")
    if manifest["files"] != {name: expected[f"{ETF_RAW}/{name}"] for name in ETF_FILES}:
        raise ValueError("preregistration and the ETF input manifest differ")
    return expected


def sha256_stream(stream) -> str:
    digest = sha256()
    for chunk in iter(lambda: stream.read(1024 * 1024), b""):
        digest.update(chunk)
    return digest.hexdigest()


def read_json(root: Path, name: str):
    return json.loads(allowed_path(root, name).read_bytes())


@dataclass(frozen=True)
class ETFData:
    opens: np.ndarray
    closes: np.ndarray
    dividends: np.ndarray
    payments: dict
    eligible: np.ndarray
    volatility: np.ndarray


def causal_prices(raw, cumulative, end, length):
    window = slice(end + 1 - length, end + 1)
    return raw[window] - (cumulative[end] - cumulative[window])


def load_etf(root, calendar, start):
    prices = {kind: [] for kind in ("open", "close")}
    dividends = np.zeros((len(calendar), len(SYMBOLS)))
    payments = {}
    diagnostics = {}
    for column, symbol in enumerate(SYMBOLS):
        rows = {}
        for kind, date_field in (("ohlcv", "date"), ("dividends", "ex_dividend_date"), ("nav", "nav_date")):
            payload = read_json(root, f"{ETF_RAW}/{symbol.replace('.', '_')}_{kind}.json")
            dates = [row[date_field] for row in payload["rows"]]
            if payload["symbol"] != symbol or dates != sorted(set(dates)) or any(
                not START <= value <= CUTOFF for value in dates
            ):
                raise ValueError(f"invalid frozen ETF dates or symbol: {symbol}/{kind}")
            rows[kind] = payload["rows"]
        diagnostics[symbol] = validate(rows["ohlcv"], rows["dividends"], rows["nav"], calendar)
        if not diagnostics[symbol]["passed"]:
            raise ValueError(f"ETF data gate failed: {symbol}")
        bars = {row["date"]: row for row in rows["ohlcv"]}
        for kind in prices:
            prices[kind].append([bars.get(day, {}).get(kind, math.nan) for day in calendar])
        if rows["dividends"] and (column != 0 or {r["ex_dividend_date"] for r in rows["dividends"]} != set(PAYMENT)):
            raise ValueError(f"missing preregistered exchange payment dates: {symbol}")
        for row in rows["dividends"]:
            ex = row["ex_dividend_date"]
            if row["dividend_per_share"] != row["per_ten_cash_before_tax"] / 10:
                raise ValueError(f"ETF dividend conversion mismatch: {symbol}/{ex}")
            i = calendar.index(ex)
            dividends[i, column] = row["dividend_per_share"]
            payments[(i - start, column)] = calendar.index(PAYMENT[ex]) - start
    closes = np.asarray(prices["close"]).T
    cumulative = dividends.cumsum(axis=0)
    eligible = []
    volatility = []
    for end in range(start, len(calendar)):
        history = causal_prices(closes, cumulative, end, 21)
        window = history[1:]
        eligible.append(np.all(window > 0, axis=0) & (window[-1] > window.mean(axis=0)))
        with np.errstate(divide="ignore", invalid="ignore"):
            stdev = np.std(history[1:] / history[:-1] - 1, axis=0, ddof=1)
        volatility.append(np.where(np.all(history > 0, axis=0), stdev, np.nan))
    return ETFData(np.asarray(prices["open"]).T[start:], closes[start:], dividends[start:],
                   payments, np.array(eligible), np.array(volatility)), diagnostics


def load_index(root, evaluation_dates):
    index = []
    for path in INDEX:
        payload = read_json(root, path)
        if payload["code"] != 0:
            raise ValueError(f"frozen index request was unsuccessful: {path}")
        for row in payload["data"]["item"]:
            stamp = int(row["date_ms"])
            day = core._date_from_ms(stamp)
            if day > CUTOFF:
                raise ValueError("out-of-bounds frozen index date")
            index.append({"date": day, "stamp": stamp, "close": float(row["close_price"])})
    index.sort(key=lambda row: row["stamp"])
    dates = [row["date"] for row in index]
    first = dates.index(FIRST_SIGNAL)
    close = np.array([row["close"] for row in index])
    if dates[first:] != evaluation_dates or len(set(dates)) != len(index) or first < 26 or not np.all(close > 0):
        raise ValueError("index dates or G2 warmup do not match the frozen XSHG window")
    ma20 = sliding_window_view(close, 20).mean(axis=1)
    g2_with_preroll = (close[first - 2:] > ma20[first - 21:]) & (ma20[first - 21:] > ma20[first - 26:-5])
    return index, np.array([row["stamp"] for row in index[first:]]), g2_with_preroll


def qualification_events(root, dates, g2):
    day_index = {day: i for i, day in enumerate(dates)}
    eligible = []
    seen = set()
    with gzip.open(allowed_path(root, B_EVENTS), "rt", encoding="utf-8") as stream:
        for line in stream:
            event = json.loads(line)
            signal, code, execution = (event[key] for key in ("signal_date", "symbol", "earliest_execution_date"))
            if signal not in day_index or (signal, code) in seen or event["as_of_date"] != signal:
                raise ValueError("invalid frozen B qualification identity")
            seen.add((signal, code))
            day = day_index[signal]
            if day + 1 < len(dates) and execution != dates[day + 1]:
                raise ValueError("frozen B earliest execution differs from XSHG T+1")
            if g2[day] and re.fullmatch(r"(?:00\d{4}\.sz|60\d{4}\.sh)", code):
                eligible.append((day, code, execution))
    return eligible, len(seen)


@dataclass(frozen=True)
class Stock:
    ohlc: np.ndarray
    scale: np.ndarray
    offset: np.ndarray
    by_day: dict

    def convert(self, price, origin, row):
        if self.scale[row] == self.scale[origin] and self.offset[row] == self.offset[origin]:
            return float(price)
        return float(self.scale[row] * (price - self.offset[origin]) / self.scale[origin] + self.offset[row])

    def locks(self, row):
        opening, high, low, _ = self.ohlc[row]
        if high != low:
            return False, False
        if row == 0:
            raise ValueError("no causal pre-close for a B price-limit bar")
        previous = self.convert(self.ohlc[row - 1, 3], row - 1, row)
        if previous <= 0:
            raise ValueError("non-positive causal B pre-close")
        return opening >= previous * 1.10 - 0.005, opening <= previous * 0.90 + 0.005


def stock_data(root, codes, stamps):
    columns = ("open", "high", "low", "close", "volume")
    aliases = [f"{name}_price" for name in columns[:4]] + ["volume"]
    code_filter = ("thscode", "in", sorted(code.upper() for code in codes))
    cutoff = int(stamps[-1])
    frame = pd.read_parquet(allowed_path(root, STOCKS), engine="pyarrow", filters=[("date_ms", "<=", cutoff), code_filter],
                            columns=["thscode", "date_ms", *aliases])
    frame = frame.sort_values(["thscode", "date_ms"], kind="stable").reset_index(drop=True)
    values = frame[aliases].to_numpy(dtype=float)
    if (frame.duplicated(["thscode", "date_ms"]).any() or not np.isfinite(values).all()
            or np.any(values[:, :4] <= 0) or np.any(values[:, 4] < 0)):
        raise ValueError("frozen stock bar data are malformed")
    date_ms = frame["date_ms"].to_numpy(dtype=np.int64)
    if not len(date_ms) or date_ms.max() > cutoff:
        raise ValueError("bounded frozen stock bar data are unavailable")
    store = {name: values[:, i] for i, name in enumerate(columns)}
    store.update(date_ms=date_ms, date_text={int(stamp): core._date_from_ms(stamp) for stamp in np.unique(date_ms)})
    factors = pd.read_parquet(allowed_path(root, ACTIONS), engine="pyarrow",
                              filters=[("ex_date_ms", "<=", cutoff), code_filter], columns=[
                                  "thscode", "ex_date_ms", "dividend_per_share", "per_share_bonus",
                                  "allotment_ratio", "allotment_price",
                              ])
    actions = defaultdict(list)
    for symbol, stamp, *cash_terms in factors.itertuples(index=False, name=None):
        if stamp > cutoff:
            raise ValueError("out-of-bounds frozen B action")
        actions[symbol.lower()].append((int(stamp), *(core._as_float(term, default=0.0) for term in cash_terms)))
    for rows in actions.values():
        rows.sort(key=lambda row: row[0])
    stocks, bounds = {}, {}
    for symbol, group in frame.groupby("thscode", sort=False):
        code = symbol.lower()
        begin = int(group.index[0])
        end = int(group.index[-1]) + 1
        bounds[code] = begin
        dates = date_ms[begin:end]
        scale = np.ones(len(dates))
        offset = np.zeros(len(dates))
        for stamp, dividend, bonus, allotment, price in actions[code]:
            i = int(np.searchsorted(dates, stamp))
            if not 0 < i < len(dates):
                continue
            denominator = 1 + bonus + allotment
            if denominator <= 0 or not math.isfinite(denominator):
                raise ValueError(f"invalid frozen B action for {code}")
            scale[i:] /= denominator
            offset[i:] = (offset[i:] - dividend + price * allotment) / denominator
        first = int(np.searchsorted(dates, stamps[0]))
        indices = np.searchsorted(stamps, dates[first:])
        if not np.array_equal(stamps[indices], dates[first:]):
            raise ValueError(f"off-calendar frozen stock bars for {code}")
        stocks[code] = Stock(values[begin:end, :4], scale, offset,
                             dict(zip(indices.tolist(), range(first, len(dates)))))
    if set(stocks) != codes:
        raise ValueError("one or more frozen B symbols have no bars")
    return stocks, store, bounds, actions


@dataclass(frozen=True)
class Order:
    origin: int
    trigger: float
    stop: float
    target: float


def b_signals(root, dates, g2, index, stamps):
    events, total = qualification_events(root, dates, g2)
    stocks, store, bounds, actions = stock_data(root, {code for _, code, _ in events}, stamps)
    index_start = len(index) - len(dates)
    ranked = [[] for _ in dates]
    counts = Counter(frozen_qualification_events=total, g2_main_board_formal_events=len(events))
    for day, code, execution in events:
        row = stocks[code].by_day[day]
        if row < 249:
            counts["insufficient_250_bars"] += 1
            continue
        date = dates[day]
        base = bounds[code]
        bars = core._adjusted_bars(store, base + max(0, row - 259), base + row + 1, actions[code], int(stamps[day]))
        metrics = _position_metrics(bars, date)
        if any(metrics[key] is None for key in ("pos250", "chg20", "chg60")):
            counts["position_unavailable"] += 1
            continue
        pos, chg20, chg60 = (round(metrics[key], 12) for key in ("pos250", "chg20", "chg60"))
        if pos > 0.55 or chg20 > 0.20 or chg60 > 0.30:
            continue
        counts["l1_pass"] += 1
        observation = observe({"signal_id": f"{date}:{code}", "code": code.split(".")[0]}, bars, date)
        volume = observation["volume"]
        v1, v2 = (volume[key] for key in FIELDS[:2])
        if observation["structure"]["state"] not in ("EARLY_PULLBACK", TRANSITION):
            counts["structure_outside_v2"] += 1
            continue
        if (any(volume.get("missing_reason", {}).get(key) for key in FIELDS[:2]) or v1 is None or v2 is None
                or not (0 <= v1 <= 1 and 0 <= v2 < math.inf)):
            counts["volume_unavailable"] += 1
            continue
        projection = evaluate_numeric_projection(
            symbol=code, signal_date=date, earliest_execution_date=execution,
            bars=tuple(np.array([bar[key] for bar in bars]) for key in ("close", "volume", "high", "low")),
            index_bars=index[:index_start + day + 1],
        )
        if projection["status"] != "QUALIFIED_LEGACY_BASELINE":
            raise ValueError(f"frozen B qualification did not reproduce for {date}/{code}")
        trigger, stop, target = (projection[key] for key in ("trigger", "stop", "target"))
        if (any(value is None for value in (stop, trigger, target))
                or not 0 < stop < trigger <= max(bars[-1]["close"], trigger) < target):
            counts["reference_levels_unusable"] += 1
            continue
        ranked[day].append((pos, round(v1, 12), code, Order(row, trigger, stop, target)))
    counts["v2_eligible_events"] = sum(map(len, ranked))
    if not counts["v2_eligible_events"]:
        raise ValueError("B benchmark qualification is unavailable")
    return stocks, [[(code, order) for _, _, code, order in sorted(rows)] for rows in ranked], dict(counts)


@dataclass
class BPosition:
    signal: int
    entry: int
    basis: int
    price: float
    order: Order
    last_gross: float = 1.0
    due: bool = False

    def gross(self, stock, row, price):
        basis = stock.convert(self.price, self.basis, row)
        if min(basis, price) <= 0:
            raise ValueError("non-positive B execution price or adjusted cost")
        return price / basis


@dataclass
class BDay:
    order_count: int = 0
    open_marks: dict = field(default_factory=dict)
    open_sales: dict = field(default_factory=dict)
    entries: list = field(default_factory=list)
    late_sales: dict = field(default_factory=dict)
    close_marks: dict = field(default_factory=dict)
    occupied_at_close: int = 0


def exit_for_day(stock, position, day, row):
    deadline = position.signal + 10
    if row is None or position.entry == day:
        position.due |= day >= deadline
        return None
    opening, high, low, closing = stock.ohlc[row]
    stop = stock.convert(position.order.stop, position.order.origin, row)
    target = stock.convert(position.order.target, position.order.origin, row)
    if stock.locks(row)[1]:
        position.due |= low <= stop or day >= deadline
        return None
    if position.due or opening <= stop or opening >= target:
        return "open", opening, "OPEN_EXIT"
    if low <= stop:
        return "late", stop, "AMBIGUOUS_SAME_BAR_STOP" if high >= target else "STOP"
    if high >= target:
        return "late", target, "TARGET"
    if day >= deadline:
        return "late", closing, "TIME_EXIT_CLOSE"
    return None


def b_tape(stocks, signals, g2, constrained):
    pending, positions, blocked_through = {}, {}, {}
    tape = []
    counts = Counter()
    for day, ranked in enumerate(signals):
        can_buy = day > 0 and (g2[day - 1] or not constrained)
        today = BDay(order_count=len(pending) if can_buy else 0)
        for code, position in positions.items():
            stock = stocks[code]
            row = stock.by_day.get(day)
            today.open_marks[code] = position.last_gross if row is None else position.gross(stock, row, stock.ohlc[row, 0])
        for code, (signal, order) in list(pending.items()):
            stock = stocks[code]
            row = stock.by_day.get(day)
            if can_buy and row is not None and not stock.locks(row)[0]:
                opening, high = stock.ohlc[row, :2]
                trigger = stock.convert(order.trigger, order.origin, row)
                if high >= trigger:
                    positions[code] = BPosition(signal, day, row, max(float(opening), trigger), order)
                    today.entries.append(code)
                    del pending[code]
                    continue
            if day >= signal + 10:
                del pending[code]
                counts["expired"] += 1
        for code, position in list(positions.items()):
            stock = stocks[code]
            row = stock.by_day.get(day)
            outcome = exit_for_day(stock, position, day, row)
            if outcome is None:
                if row is not None:
                    position.last_gross = position.gross(stock, row, stock.ohlc[row, 3])
                today.close_marks[code] = position.last_gross
                continue
            phase, price, status = outcome
            exits = today.open_sales if phase == "open" else today.late_sales
            exits[code] = position.gross(stock, row, price)
            del positions[code]
            blocked_through[code] = day + 5
            counts["closed"] += 1
            counts["ambiguous_stop"] += status == "AMBIGUOUS_SAME_BAR_STOP"
        if g2[day]:
            selected = 0
            for code, order in ranked:
                if selected == 3 or (constrained and len(positions) + len(pending) >= SLOTS):
                    break
                if code in positions or code in pending or blocked_through.get(code, -1) >= day:
                    continue
                pending[code] = day, order
                blocked_through[code] = day + 5
                selected += 1
            counts["accepted"] += selected
        today.occupied_at_close = len(positions) + len(pending)
        counts["entries"] += len(today.entries)
        counts["peak_occupied"] = max(counts["peak_occupied"], today.occupied_at_close)
        counts["peak_holdings"] = max(counts["peak_holdings"], len(today.open_marks) + len(today.entries) - len(today.open_sales))
        tape.append(today)
    counts["open_at_cutoff"] = len(positions)
    counts["pending_at_cutoff"] = len(pending)
    if not counts["closed"]:
        raise ValueError("B reference replay has no closed trades")
    return tape, dict(counts)


def defensive_modes(g2_with_preroll):
    non_g2 = ~np.asarray(g2_with_preroll, dtype=bool)
    return non_g2[2:], non_g2[:-2] & non_g2[1:-1] & non_g2[2:]


def target_weights(eligible, volatility, allocation):
    weights = np.zeros(len(SYMBOLS))
    if allocation == 0:
        weights[:2] = 0.5 * eligible[:2]
    elif allocation == 2:
        weights[0] = eligible[0]
    elif np.any(eligible):
        selected = volatility[eligible]
        if not np.all(np.isfinite(selected) & (selected > 0)):
            raise ValueError("eligible ETF has invalid 20-day volatility")
        inverse = 1 / selected
        weights[eligible] = inverse / inverse.sum()
        weights[1:] = np.minimum(weights[1:], 0.5)
    return weights


def last_of_week(dates):
    weeks = [pd.Timestamp(day).isocalendar()[:2] for day in dates]
    return [first != second for first, second in zip(weeks, weeks[1:])] + [True]


def rebalance(cash, shares, prices, target_values, side_cost):
    """Trade to opening targets using available cash and actual turnover fees."""
    changes = target_values - shares * prices
    sales = np.maximum(-changes, 0)
    buys = np.maximum(changes, 0)
    cash += float(sales.sum()) * (1 - side_cost)
    if buys.sum() * (1 + side_cost) > cash:
        buys *= cash / (buys.sum() * (1 + side_cost))
    cash -= float(buys.sum()) * (1 + side_cost)
    churn = float(sales.sum() + buys.sum())
    shares = np.maximum(shares + (buys - sales) / prices, 0)
    if cash < -EPS:
        raise ValueError("ETF rebalance exceeded available cash")
    return max(cash, 0.0), shares, churn, churn * side_cost


def setting_at_close(g2, activated, active, weekly, weights, qualified, shares, closes, equity, free_ratio):
    if g2:
        return 0.0, np.zeros(len(SYMBOLS))
    if not active or not (activated or weekly):
        return None
    current = shares * closes / equity
    removed = np.any((shares > EPS) & ~qualified)
    if np.abs(free_ratio * weights - current).sum() < 0.10 and not removed:
        return None
    return free_ratio, weights


def portfolio(etf, g2, tape, *, active=None, weeks=None, allocation=None, side_cost=0.0):
    cash = 1.0
    shares = np.zeros(len(SYMBOLS))
    b = {}
    receivables = {}
    directive = None
    equity = []
    costs = Counter()
    is_sleeve = tape is None
    if is_sleeve:
        tape = [BDay()] * len(g2)
    for i, today in enumerate(tape):
        cash += receivables.pop(i, 0.0)
        for column, dividend in enumerate(etf.dividends[i]):
            if dividend and shares[column] > 0:
                payment = etf.payments[i, column]
                amount = shares[column] * dividend
                if payment == i:
                    cash += amount
                else:
                    receivables[payment] = receivables.get(payment, 0.0) + amount
                costs["cash_dividend_accrued"] += amount
        prices = etf.opens[i]
        forced_exit = directive is not None and g2[i - 1]
        if forced_exit:
            cash, shares, turnover, fees = rebalance(cash, shares, prices, np.zeros(len(SYMBOLS)), side_cost)
            costs["exit_turnover"] += turnover
            costs["etf_turnover"] += turnover
            costs["etf_fees"] += fees
            costs["forced_exits"] += turnover > EPS
        if today.order_count and np.any(shares > EPS):
            raise ValueError("ETF and executable B orders share opening cash")
        if set(today.open_marks) != set(b):
            raise ValueError("B account opening holdings diverged from the shared tape")
        for code, gross in today.open_sales.items():
            cash += b.pop(code) * (gross - B_SIDE)
        marked_b = sum(b[code] * (today.open_marks[code] - B_SIDE) for code in b)
        liquid = cash + float(shares @ prices)
        open_equity = liquid + marked_b + sum(receivables.values())
        if directive is not None and not forced_exit:
            ratio, weights = directive
            budget = min(ratio * open_equity, liquid)
            cash, shares, turnover, fees = rebalance(cash, shares, prices, budget * weights, side_cost)
            costs["etf_turnover"] += turnover
            costs["etf_fees"] += fees
            costs["scheduled_trades"] += turnover > EPS
        if today.entries:
            if not 0 < len(today.entries) <= today.order_count:
                raise ValueError("B order count does not cover recorded entries")
            budget = min(open_equity / SLOTS, cash / today.order_count)
            if budget <= 0 or np.any(shares > EPS):
                raise ValueError("B entry was not fully funded by cash")
            for code in today.entries:
                b[code] = budget / (1 + B_SIDE)
                cash -= budget
            costs["b_buys"] += len(today.entries)
        for code, gross in today.late_sales.items():
            cash += b.pop(code) * (gross - B_SIDE)
        if set(today.close_marks) != set(b) or not len(b) <= today.occupied_at_close <= SLOTS:
            raise ValueError("B account broke the six-slot holding/ordering invariant")
        if cash < -EPS:
            raise ValueError("account spent funds that were not available")
        cash = max(cash, 0.0)
        closing = etf.closes[i]
        nav = (cash + float(shares @ closing) + sum(receivables.values())
               + sum(b[code] * (today.close_marks[code] - B_SIDE) for code in b))
        if not math.isfinite(nav) or nav <= 0:
            raise ValueError("invalid account net asset value")
        equity.append(nav)
        if active is not None:
            qualified = etf.eligible[i]
            weights = target_weights(qualified, etf.volatility[i], allocation)
            free = 1.0 if is_sleeve else (SLOTS - len(b)) / SLOTS
            directive = setting_at_close(g2[i], i == 0 or not active[i - 1], active[i], weeks[i],
                                         weights, qualified, shares, closing, nav, free)
    costs["max_b_etf_cash_overlap"] = 0
    costs["outstanding_dividend_at_cutoff"] = sum(receivables.values())
    costs["etf_value_at_cutoff"] = float(shares @ etf.closes[-1])
    return np.asarray(equity), dict(costs)


def bridge_b_pnl(tape):
    pnl = []
    realized = 0.0
    for today in tape:
        realized += sum(gross - 1 - 2 * B_SIDE for gross in today.open_sales.values())
        realized += sum(gross - 1 - 2 * B_SIDE for gross in today.late_sales.values())
        pnl.append(realized + sum(gross - 1 - 2 * B_SIDE for gross in today.close_marks.values()))
    return np.asarray(pnl)


def daily_returns(equity):
    return equity / np.r_[1.0, equity[:-1]] - 1


def risk_metrics(equity, year_masks):
    peaked = np.maximum.accumulate(np.r_[1, equity])[1:]
    max_drawdown = float(np.max(1 - equity / peaked))
    net = float(equity[-1] - 1)
    returns = daily_returns(equity)
    return {"total_return": net, "max_drawdown": max_drawdown,
            "return_drawdown": net / max_drawdown if max_drawdown else None,
            "annual_return": {year: float(np.prod(1 + returns[mask]) - 1) for year, mask in year_masks.items()}}


def block_indices(length, rng):
    starts = rng.integers(0, length - 20 + 1, (5000, (length + 19) // 20))
    return (starts[:, :, None] + np.arange(20)).reshape(5000, -1)[:, :length]


def interval(samples):
    return np.quantile(samples, [0.025, 0.975], method="linear").tolist()


def bootstrap_sleeve(returns):
    indices = block_indices(len(returns), np.random.default_rng(20261128))
    return {"actual_daily_mean": float(returns.mean()), "ci95": interval(returns[indices].mean(axis=1))}


def bootstrap_account(returns, baseline, year_masks):
    rng = np.random.default_rng(20261128)
    delta = np.zeros(5000)
    for year in WEAK_YEARS:
        mask = year_masks[year]
        indices = block_indices(int(mask.sum()), rng)
        delta += (1 + returns[mask][indices]).prod(axis=1) - (1 + baseline[mask][indices]).prod(axis=1)
    return interval(delta)


def assess(costs, baseline, sleeve_bootstrap, account_ci):
    main, stress = costs["5_bps"], costs["10_bps"]
    sleeve, account = main["standalone"], main["account"]
    weak_positive = all(cost["standalone"]["annual_return"][year] > 0
                        for cost in (main, stress) for year in WEAK_YEARS)
    g2 = weak_positive and sleeve["max_drawdown"] <= 0.06
    g3_economic = (sleeve["total_return"] > 0 and sum(value >= 0 for value in sleeve["annual_return"].values()) >= 3
                   and sleeve_bootstrap["actual_daily_mean"] > 0)
    ratio_a, ratio_b = account["return_drawdown"], baseline["return_drawdown"]
    g4_economic = (all(cost["weak_years_account_delta"] > 0 for cost in (main, stress))
                   and ratio_a is not None and ratio_b is not None and ratio_a > ratio_b
                   and account["max_drawdown"] <= 1.05 * baseline["max_drawdown"])
    intervals = (sleeve_bootstrap["ci95"], account_ci)
    all_gates = {"1_data_and_causality": True, "2_weak_years_and_drawdown": g2,
                 "3_full_period_robustness": g3_economic and intervals[0][0] > 0,
                 "4_shared_account_gain": g4_economic and intervals[1][0] > 0}
    only_ci = (g2 and g3_economic and g4_economic and not all(all_gates.values())
               and all(low > 0 or low <= 0 <= high for low, high in intervals))
    return {**all_gates, "3_economic_conditions": g3_economic, "4_economic_conditions": g4_economic,
            "only_inconclusive_bootstrap": only_ci}


def choose(matrix):
    ranked = sorted(matrix, key=lambda row: (-REGIMES.index(row["regime"]), (0, 2, 1).index(ALLOCATIONS.index(row["allocation"]))))
    passed = [row["id"] for row in ranked if all(row["gates"][key] for key in (
        "1_data_and_causality", "2_weak_years_and_drawdown", "3_full_period_robustness", "4_shared_account_gain",
    ))]
    if passed:
        return {"status": "ADOPT", "meaning": "RECOMMEND_DEFENSIVE_ETF_DAILY_REPORT_CARD_PROPOSAL", "selected": passed[0]}
    ambiguous = [row["id"] for row in ranked if row["gates"]["only_inconclusive_bootstrap"]]
    if ambiguous:
        return {"status": "NEEDS_MORE_EVIDENCE", "selected": None, "eligible_for_more_evidence": ambiguous}
    return {"status": "REJECT", "selected": None}


def run(root):
    protocol = verify_protocol(root)
    inputs = verify_inputs(root, protocol)
    calendar = sessions()
    start = calendar.index(FIRST_SIGNAL)
    dates = calendar[start:]
    etf, diagnostics = load_etf(root, calendar, start)
    manifest = read_json(root, f"{ETF_RAW}/input_manifest.json")
    if diagnostics != manifest["verification"] or (manifest["start"], manifest["cutoff"]) != (START, CUTOFF):
        raise ValueError("ETF data gate readback differs from the acquisition manifest")
    index, stamps, g2_with_preroll = load_index(root, dates)
    g2 = g2_with_preroll[2:]
    weeks = last_of_week(dates)
    masks = {year: np.array([day.startswith(year) for day in dates]) for year in YEARS}
    print("Frozen inputs verified; reconstructing B V2 qualifications.", flush=True)
    stocks, b_ranked, b_counts = b_signals(root, dates, g2, index, stamps)
    tape, tape_counts = b_tape(stocks, b_ranked, g2, constrained=True)
    bridge_tape, bridge_counts = b_tape(stocks, b_ranked, g2, constrained=False)
    bridge = bridge_b_pnl(bridge_tape)
    baseline_path, baseline_audit = portfolio(etf, g2, tape)
    baseline = risk_metrics(baseline_path, masks)
    matrix = []
    for r, active in enumerate(defensive_modes(g2_with_preroll)):
        for a, allocation in enumerate(ALLOCATIONS):
            outcomes = {}
            for fee, side_cost in (("5_bps", 0.00025), ("10_bps", 0.00050)):
                sleeve, sleeve_audit = portfolio(etf, g2, None, active=active, weeks=weeks, allocation=a, side_cost=side_cost)
                account, account_audit = portfolio(etf, g2, tape, active=active, weeks=weeks, allocation=a, side_cost=side_cost)
                if account_audit["b_buys"] != baseline_audit["b_buys"]:
                    raise ValueError("shared account failed to reproduce the baseline B fills")
                sleeve_metrics = risk_metrics(sleeve, masks)
                account_metrics = risk_metrics(account, masks)
                bridge_path = bridge + 6 * (sleeve - 1)
                bridge_changes = np.diff(np.r_[0, bridge_path])
                outcomes[fee] = {
                    "standalone": sleeve_metrics, "account": account_metrics,
                    "weak_years_account_delta": sum(account_metrics["annual_return"][year] - baseline["annual_return"][year]
                                                   for year in WEAK_YEARS),
                    "sleeve_daily_return": daily_returns(sleeve).tolist(), "account_daily_return": daily_returns(account).tolist(),
                    "sleeve_audit": sleeve_audit, "account_audit": account_audit,
                    "nominal_bridge_pnl": {"total": float(bridge_path[-1]),
                                           "annual": {year: float(bridge_changes[mask].sum()) for year, mask in masks.items()},
                                           "daily": bridge_changes.tolist()},
                }
            sleeve_bootstrap = bootstrap_sleeve(np.array(outcomes["5_bps"]["sleeve_daily_return"]))
            account_ci = bootstrap_account(np.array(outcomes["5_bps"]["account_daily_return"]), daily_returns(baseline_path), masks)
            matrix.append({"id": f"R{r}/A{a + 1}", "regime": REGIMES[r], "allocation": allocation,
                           "active_signal_days": int(active.sum()), "costs": outcomes,
                           "sleeve_bootstrap": sleeve_bootstrap, "weak_years_account_bootstrap_ci95": account_ci,
                           "gates": assess(outcomes, baseline, sleeve_bootstrap, account_ci)})
    return {
        "study": STUDY, "sample": ["DEVELOPMENT", "MAIN_BOARD_ST_UNVERIFIED_DEVELOPMENT_SAMPLE", "NO_VINTAGE_PROOF"],
        "units": {"return_and_drawdown": "fraction: 0.01 represents 1%", "nominal_bridge_pnl": "fixed notional units"},
        "protocol_commit": PROTOCOL_COMMIT, "protocol_lf_sha256": sha256(protocol).hexdigest(), "inputs": inputs,
        "window": {"first": FIRST_SIGNAL, "cutoff": CUTOFF, "sessions": dates,
                   "sessions_by_year": {year: int(mask.sum()) for year, mask in masks.items()}},
        "etf_data_gate": diagnostics, "g2_days": int(g2.sum()), "non_g2_days": int((~g2).sum()),
        "b_v2_qualification": b_counts,
        "baseline": {"label": "B_V2_6SLOT + CASH", "metrics": baseline, "ledger": tape_counts,
                     "audit": baseline_audit, "daily_return": daily_returns(baseline_path).tolist()},
        "bridge": {"label": "B_V2_UNCONSTRAINED + 6_UNITS_DEFENSIVE", "ledger": bridge_counts,
                   "b_only_total_pnl": float(bridge[-1])},
        "bootstrap": {"block_sessions": 20, "replicates": 5000, "seed": 20261128},
        "matrix": matrix, "decision": choose(matrix),
    }


def pc(value, digits=3):
    return f"{value * 100:.{digits}f}%"


def ratio(value):
    return "—" if value is None else f"{value:.3f}"


def render_report(summary, digest):
    matrix = summary["matrix"]
    decision = summary["decision"]
    lines = ["# G2 轮空期场内防守 ETF 研究报告", "",
             f"**Decision `{decision['status']}`**。研究归类仍为非阻塞 `research question`，走 `STRICT PATH`。"]
    if decision["status"] == "ADOPT":
        lines += [f"按固定优先级选定 `{decision['selected']}`，支持 `RECOMMEND_DEFENSIVE_ETF_DAILY_REPORT_CARD_PROPOSAL`。"]
    elif decision["status"] == "NEEDS_MORE_EVIDENCE":
        lines += ["所缺证据是独立、预先记录的同口径样本，用于把仍含零的经济增益置信区间收窄。现有 B V2 日报和现金基准可继续使用。"]
    else:
        lines += ["六组候选均未跨过全部预注册门槛。各组的具体失败项见下表。"]
    lines += ["", "## 数据与口径", "",
              f"预注册提交 `{summary['protocol_commit']}`。`summary.json` SHA-256 `{digest}`。",
              f"2023-06-30 至 2026-08-28 共 769 个 XSHG 交易日，G2 收盘 {summary['g2_days']} 日，非 G2 {summary['non_g2_days']} 日。",
              "2023 和 2026 为部分年份。样本为冻结开发样本 `MAIN_BOARD_ST_UNVERIFIED_DEVELOPMENT_SAMPLE / NO_VINTAGE_PROOF`。",
              "净值使用获批的总增长因子比值。三只 ETF 各有 263 根有效预热日线及 769 根评估日线，"
              "逐日以 XSHG 对齐，并覆盖窗口内供应商额外发布的净值。"]
    lines += ["", "| ETF | 评估交易日 | 预热日 | 分红事件 | 非除息日比值最大偏差（bp） | 除息校验失败 |",
              "| --- | ---: | ---: | ---: | ---: | ---: |"]
    for symbol, row in summary["etf_data_gate"].items():
        lines.append(f"| {symbol} | {row['evaluation_bars']} | {row['warmup_bars']} | {row['dividends']} | "
                     f"{row['max_nav_gross_return_ratio_gap_bps']:.4f} | {row['dividend_nav_mismatch']} |")
    lines += ["", "## 独立防守袖套", "",
              "| 候选 | 双边成本 | 2023 | 2024 | 2025 | 2026 | 全期 | 最大回撤 | 收益/回撤 |",
              "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |"]
    for row in matrix:
        for fee, result in row["costs"].items():
            m = result["standalone"]
            annual = " | ".join(pc(m["annual_return"][year]) for year in YEARS)
            lines.append(f"| {row['id']} | {fee.replace('_', ' ')} | {annual} | {pc(m['total_return'])} | "
                         f"{pc(m['max_drawdown'])} | {ratio(m['return_drawdown'])} |")
    baseline = summary["baseline"]
    b = baseline["ledger"]
    lines += ["", "## 六槽位共享账户", "",
              f"B V2 重建共 {b['accepted']} 笔入选，{b['entries']} 笔成交，{b['closed']} 笔结案，"
              f"{b['peak_occupied']} 槽峰值占用，{b['ambiguous_stop']} 笔盘中双触及按止损结算。"
              "六组组合与基准共用逐笔 B 成交时点和价格，成交金额随账户权益变化。"
              "所有回放通过资金余额、槽位及 ETF 清仓先于 B 开仓检查。",
              "弱年增量为两年各自相对六槽位现金基准的累计收益差相加，单位为百分点。", "",
              "| 候选 | ETF 双边成本 | 2023 | 2024 | 2025 | 2026 | 全期 | 最大回撤 | 收益/回撤 | 弱年增量（pp） |",
              "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |"]
    account_rows = [("B V2 + 现金", "—", baseline["metrics"], 0.0)]
    account_rows.extend((row["id"], fee.replace("_", " "), result["account"], result["weak_years_account_delta"])
                        for row in matrix for fee, result in row["costs"].items())
    for label, fee, metrics, delta in account_rows:
        annual = " | ".join(pc(metrics["annual_return"][year]) for year in YEARS)
        lines.append(f"| {label} | {fee} | {annual} | {pc(metrics['total_return'])} | "
                     f"{pc(metrics['max_drawdown'])} | {ratio(metrics['return_drawdown'])} | {delta * 100:+.3f} |")
    lines += ["", "## 预注册判定", "",
              "袖套置信区间为单日平均净收益，账户置信区间为两个弱年合计的复利增量。均用 5 bps、"
              "20 日移动块、5,000 次，账户在年内配对重采样。", "",
              "| 候选 | 激活信号日 | 袖套日均 | 袖套日均 95% CI | 弱年账户增量 95% CI（pp） | 门 1 | 门 2 | 门 3 | 门 4 |",
              "| --- | ---: | ---: | ---: | ---: | --- | --- | --- | --- |"]
    for row in matrix:
        boot = row["sleeve_bootstrap"]
        sleeve_ci = ", ".join(pc(value, 4) for value in boot["ci95"])
        account_ci = ", ".join(f"{value * 100:+.3f}" for value in row["weak_years_account_bootstrap_ci95"])
        gates = " | ".join("通过" if row["gates"][key] else "未过" for key in (
            "1_data_and_causality", "2_weak_years_and_drawdown", "3_full_period_robustness", "4_shared_account_gain",
        ))
        lines.append(f"| {row['id']} | {row['active_signal_days']} | {pc(boot['actual_daily_mean'], 4)} | "
                     f"[{sleeve_ci}] | [{account_ci}] | {gates} |")
    lines += ["", "## 固定名义单位桥接", "",
              f"前序口径无槽位上限 B 全期名义损益为 {summary['bridge']['b_only_total_pnl']:+.4f} 单位。"
              "下表为该 B 曲线加六倍防守袖套权益变化，仅用于对照历史口径。", "",
              "| 候选 | ETF 双边成本 | 2023 | 2024 | 2025 | 2026 | 全期 |",
              "| --- | ---: | ---: | ---: | ---: | ---: | ---: |"]
    for row in matrix:
        for fee, result in row["costs"].items():
            bridge = result["nominal_bridge_pnl"]
            annual = " | ".join(f"{bridge['annual'][year]:+.4f}" for year in YEARS)
            lines.append(f"| {row['id']} | {fee.replace('_', ' ')} | {annual} | {bridge['total']:+.4f} |")
    lines += ["", "研究使用整数交易日与零碎份额，ETF 以可用开盘价和固定成本模拟。"
              "实际成交报价、零碎份额限制及更高交易摩擦未纳入。国债现金红利在除息日计作应收，"
              "到场内发放日才计入可交易资金。截止日未平仓按收盘计值。",
              "策略定义、证据身份、资金约束与门槛见[预注册协议](defensive_etf_non_g2_v1_protocol.md)。", "",
              "在 `origin/codex/defensive-etf-non-g2-v1` 获取研究提交后可从本协议和冻结输入恢复。"
              "既有大型 B 日线按 `data/governance/frozen_artifacts.json` 中 `phase2e.raw.daily_k` 的恢复记录取得。"
              "回放入口为 `python scripts/defensive_etf_non_g2_v1.py`。", ""]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    summary = run(ROOT)
    encoded = json.dumps(summary, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    digest = sha256(encoded).hexdigest()
    for name, raw in ((f"{DATA}/summary.json", encoded), (REPORT, render_report(summary, digest).encode("utf-8"))):
        path = ROOT / name
        if path.resolve() != path:
            raise ValueError(f"study output path is redirected: {name}")
        path.write_bytes(raw)
    print(f"{STUDY}: {summary['decision']['status']}; summary SHA-256 {digest}", flush=True)


if __name__ == "__main__":
    main()
