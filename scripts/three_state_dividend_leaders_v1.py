"""Replay the locked three-state breadth and dividend development study."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from types import ModuleType

import numpy as np
from numpy.lib.stride_tricks import sliding_window_view
import pandas as pd
import pyarrow.parquet as pq

import core_signal_replay as core


ROOT = Path(__file__).resolve().parents[1]
STUDY = "THREE_STATE_REGIME_AND_DIVIDEND_LEADERS_V1"
NAME = "three_state_dividend_leaders_v1"
PROTOCOL_COMMIT = "d268e74690251d5f3eeebf93fa1db6cbcd00622d"
PROTOCOL = f"docs/research/{NAME}_protocol.md"
REPORT = f"docs/research/{NAME}_report.md"
DATA = f"data/validation/{NAME}"
SUMMARY = f"{DATA}/summary.json"
ARCHIVE = "8a7a528dd2df89bdeab9cf18304da5835143364d"
ETF_LOCK = "1d1f0177e6e588bfb0c3fa4371e248cbfbb168c4"
PRIOR_DATA = "data/validation/defensive_etf_non_g2_v1"
FETCH_SOURCE = "scripts/fetch_defensive_etf_validation_inputs.py"
REPLAY_SOURCE = "scripts/defensive_etf_non_g2_v1.py"
REGISTRY = "data/governance/frozen_artifacts.json"
START, CUTOFF = "2023-06-30", "2026-08-28"
YEARS = ("2023", "2024", "2025", "2026")
SLICES_2026 = {"2026_01_03": ("2026-01-01", "2026-03-31"),
               "2026_04_06": ("2026-04-01", "2026-06-30"),
               "2026_07_08": ("2026-07-01", CUTOFF)}
WEAK_YEARS = ("2023", "2026")
WIDTHS = {"W45": 0.45, "W50": 0.50}
COSTS = {"5_bps": 0.00025, "10_bps": 0.00050}
SEED, BLOCK, REPLICATES = 20261129, 20, 5000
STOCK_SIDE, EPS = 0.001, 1e-12
STRONG, HUG, DEFENSE, BUFFER = (
    "STATE_STRONG", "STATE_DIVIDEND_HUG", "STATE_FULL_DEFENSE", "OBSERVATION_BUFFER",
)
DEFER = "DEFER_OBSERVATION_ONLY_SUBOPTIMAL_VS_BOND_GOLD"
MAIN_BOARD = re.compile(r"(?:00\d{4}\.sz|60\d{4}\.sh)", re.I)


def git(root, *args):
    return subprocess.check_output(["git", *args], cwd=root, stderr=subprocess.PIPE,
                                   env={**os.environ, "GIT_NO_LAZY_FETCH": "1"})


def regular_path(root, relative):
    path = root / relative
    if path.resolve(strict=True) != path or not path.is_file():
        raise ValueError(f"redirected or non-regular input: {relative}")
    return path


def verify_inputs(root):
    git(root, "merge-base", "--is-ancestor", PROTOCOL_COMMIT, "HEAD")
    locked = git(root, "show", f"{PROTOCOL_COMMIT}:{PROTOCOL}")
    if locked != regular_path(root, PROTOCOL).read_bytes().replace(b"\r\n", b"\n"):
        raise ValueError("preregistration protocol differs from committed bytes")
    pattern = r"^\| `([^\r\n`]+)` \| (\d+) \| `([0-9a-f]{64})` \| ([^\n]+?) \|$"
    known_sources = {"Git 输入锁": ETF_LOCK, "Git 验证归档": ARCHIVE}
    rows = re.findall(pattern, locked.decode("utf-8"), flags=re.M)
    if len(rows) != 19 or len({row[0] for row in rows}) != len(rows):
        raise ValueError("frozen protocol input table is incomplete or ambiguous")
    identity, blobs = {}, {}
    for name, size, digest, source in rows:
        if source in known_sources:
            blob = blobs[name] = git(root, "show", f"{known_sources[source]}:{name}")
            length, checksum = len(blob), sha256(blob).hexdigest()
        else:
            path = regular_path(root, name)
            if source == "LF":
                blob = blobs[name] = path.read_bytes().replace(b"\r\n", b"\n")
                length, checksum = len(blob), sha256(blob).hexdigest()
            elif source == "工作区":
                length = path.stat().st_size
                with path.open("rb") as stream:
                    checksum = sha256_stream(stream)
            else:
                raise ValueError(f"unknown frozen input source: {source}")
            if name.startswith(f"{DATA}/raw/"):
                archived = git(root, "show", f"{ETF_LOCK}:{PRIOR_DATA}/raw/{path.name}")
                if path.read_bytes() != archived:
                    raise ValueError(f"ETF input differs from archived original: {name}")
        if (length, checksum) != (int(size), digest):
            raise ValueError(f"frozen input identity failed: {name}")
        identity[name] = {"bytes": length, "sha256": checksum, "source": known_sources.get(source, source)}
    registry = {row["logical_path"]: row["file_sha256"]
                for row in json.loads(blobs[REGISTRY])["artifacts"]}
    for name, entry in identity.items():
        if name.startswith("data/validation/") and not name.startswith((DATA, PRIOR_DATA)):
            if registry.get(name) != entry["sha256"]:
                raise ValueError(f"frozen registry disagrees: {name}")
    return identity, blobs, sha256(locked).hexdigest()


def sha256_stream(stream):
    digest = sha256()
    for block in iter(lambda: stream.read(1024 * 1024), b""):
        digest.update(block)
    return digest.hexdigest()


def archived_module(name, source, raw):
    module = ModuleType(name)
    module.__file__ = str(ROOT / source)
    sys.modules[name] = module
    exec(compile(raw, module.__file__, "exec"), module.__dict__)
    return module


def load_archive(blobs):
    archived_module("fetch_defensive_etf_validation_inputs", FETCH_SOURCE, blobs[FETCH_SOURCE])
    prior = archived_module("_frozen_defensive_etf_replay", REPLAY_SOURCE, blobs[REPLAY_SOURCE])
    prior.SYMBOLS = prior.SYMBOLS[:2]  # The omitted asset has zero weight throughout A1.
    prior.ETF_RAW = f"{DATA}/raw"
    prior.INPUTS = prior.REGISTRY_INPUTS | {
        f"{prior.ETF_RAW}/{symbol.replace('.', '_')}_{kind}.json"
        for symbol in prior.SYMBOLS for kind in ("ohlcv", "dividends", "nav")
    }
    return prior


def dividend_yield(action_stamps, action_years, cash, factors, stamps, raw_close):
    result = np.zeros(len(stamps))
    years = pd.to_datetime(stamps, unit="ms", utc=True).tz_convert("Asia/Shanghai").year.to_numpy()
    for year in np.unique(years):
        group = np.flatnonzero(years == year)
        annual = []
        for calendar_year in (year - 2, year - 1):
            dps = np.zeros(len(group))
            for event in np.flatnonzero((action_years == calendar_year) & (cash > 0)):
                applies = ((action_stamps > action_stamps[event])[None, :]
                           & (action_stamps[None, :] <= stamps[group, None]))
                dps += cash[event] / np.where(applies, factors[None, :], 1.0).prod(axis=1)
            annual.append(dps)
        qualified = (annual[0] > 0) & (annual[1] > 0)
        result[group] = np.where(qualified, (annual[0] + annual[1]) / (2 * raw_close[group]), 0.0)
    return result


def affine(stamps, actions):
    scale, offset = np.ones(len(stamps)), np.zeros(len(stamps))
    if any(not np.isfinite(row).all() or 1 + row[2] + row[3] <= 0 for row in actions):
        raise ValueError("invalid corporate-action terms")
    for stamp, dividend, bonus, allotment, price in actions:
        first = np.searchsorted(stamps, stamp)
        if 0 < first < len(stamps):
            factor = 1 + bonus + allotment
            scale[first:] /= factor
            offset[first:] = (offset[first:] - dividend + price * allotment) / factor
    return scale, offset


def load_market(root, prior, stamps):
    cutoff = int(stamps[-1])
    if cutoff != core._ms_from_date(CUTOFF):
        raise ValueError("unexpected session cutoff")
    raw_path = regular_path(root, prior.STOCKS)
    codes = pq.read_table(raw_path, columns=["thscode"],
                          filters=[("date_ms", "<=", cutoff)])["thscode"].unique().to_pylist()
    board = sorted(code for code in codes if code and MAIN_BOARD.fullmatch(code))
    columns = ["open_price", "high_price", "low_price", "close_price", "volume", "turnover"]
    raw = pd.read_parquet(raw_path, engine="pyarrow", columns=["thscode", "date_ms", *columns],
                          filters=[("date_ms", "<=", cutoff), ("thscode", "in", board)])
    action_columns = ["ex_date_ms", "dividend_per_share", "per_share_bonus", "allotment_ratio", "allotment_price"]
    actions = pd.read_parquet(regular_path(root, prior.ACTIONS), engine="pyarrow",
                              columns=["thscode", *action_columns],
                              filters=[("ex_date_ms", ">=", core._ms_from_date("2016-01-01")),
                                       ("ex_date_ms", "<=", cutoff), ("thscode", "in", board)])
    actions = {code: sorted(frame[action_columns].itertuples(index=False, name=None), key=lambda row: row[0])
               for code, frame in actions.groupby("thscode", sort=False)}
    breadth, above, pool, trend = np.zeros((4, len(stamps)), dtype=int)
    ranked = [[] for _ in stamps]
    stocks, pool_days = {}, Counter()
    witnesses, max_error = 0, 0.0
    for idx, (symbol, frame) in enumerate(raw.groupby("thscode", sort=True)):
        code = symbol.lower()
        frame = frame.sort_values("date_ms", kind="stable")
        observed = frame["date_ms"].to_numpy()
        values = frame[columns].to_numpy()
        if (np.any(np.diff(observed) <= 0) or observed[-1] > cutoff
                or not np.isfinite(values).all() or np.any(values[:, :4] <= 0)
                or np.any(values[:, 4:] < 0)):
            raise ValueError(f"invalid bounded stock data: {code}")
        events = actions.get(symbol, [])
        scale, offset = affine(observed, events)
        ohlc, volume, turnover = values[:, :4], values[:, 4], values[:, 5]
        actual = np.flatnonzero((observed >= stamps[0]) & (volume > 0))
        days = np.searchsorted(stamps, observed[actual])
        if not np.array_equal(stamps[days], observed[actual]):
            raise ValueError(f"stock bars do not match XSHG sessions: {code}")
        eligible = actual >= 249
        if not eligible.any():
            continue
        rows, market_days = actual[eligible], days[eligible]
        normalized = (ohlc - offset[:, None]) / scale[:, None]
        close61 = scale[rows, None] * sliding_window_view(normalized[:, 3], 61)[rows - 60] + offset[rows, None]
        close61[:, -1] = ohlc[rows, 3]
        ma20 = close61[:, -20:].mean(axis=1)
        positive20 = (close61[:, -20:] > 0).all(axis=1)
        rising = close61[:, -1] > ma20
        breadth[market_days] += positive20
        above[market_days] += positive20 & rising

        if idx % 5 == 0:
            for stamp, *_ in events:
                row = np.searchsorted(observed, stamp)
                if rows[0] <= row <= rows[-1] and observed[row - 249] < stamp:
                    store = dict(zip(("open", "high", "low", "close", "volume", "turnover"), values.T))
                    store.update(date_ms=observed, date_text={int(x): core._date_from_ms(x)
                                                             for x in observed[row - 249:row + 1]})
                    expected = core._adjusted_bars(store, row - 249, row + 1, events, int(observed[row]))
                    expected = np.array([[bar[k] for k in ("open", "high", "low", "close")] for bar in expected])
                    actual_prices = scale[row] * normalized[row - 249:row + 1] + offset[row]
                    max_error = max(max_error, float(np.abs(expected - actual_prices).max()))
                    witnesses += 1
                    break

        if not events:
            continue
        minimum = sliding_window_view(normalized.min(axis=1), 61)[rows - 60].min(axis=1)
        liquid = np.median(sliding_window_view(turnover, 20)[rows - 19], axis=1) >= 250_000_000
        valid = positive20 & (close61[:, -1] > 3) & liquid & (scale[rows] * minimum + offset[rows] > 0)
        if not valid.any():
            continue
        rows, market_days = rows[valid], market_days[valid]
        close61, ma20, rising = close61[valid], ma20[valid], rising[valid]
        action_stamps, cash, bonus, allotment, _ = np.asarray(events).T
        action_years = pd.to_datetime(action_stamps.astype(np.int64), unit="ms", utc=True)
        action_years = action_years.tz_convert("Asia/Shanghai").year.to_numpy()
        yields = dividend_yield(action_stamps, action_years, cash, 1 + bonus + allotment,
                                observed[rows], ohlc[rows, 3])
        std60 = np.std(close61[:, 1:] / close61[:, :-1] - 1, axis=1, ddof=1)
        in_pool = (yields >= 0.035) & (std60 * np.sqrt(250) <= 0.32)
        in_trend = rising & (ma20 > close61[:, -60:].mean(axis=1)) & (ma20 > close61[:, -25:-5].mean(axis=1))
        pool[market_days] += in_pool
        trend[market_days] += in_pool & in_trend
        pool_days[code] += int(np.count_nonzero(in_pool & (market_days >= 2)))
        ret20 = close61[:, -1] / close61[:, -21] - 1
        bias20 = close61[:, -1] / ma20 - 1
        ret60 = close61[:, -1] / close61[:, 0] - 1
        candidates = np.flatnonzero(in_pool & in_trend & (ret20 <= 0.15))
        if len(candidates):
            if np.any(std60[candidates] <= 0):
                raise ValueError(f"undefined risk-adjusted dividend score: {code}")
            stocks[code] = prior.Stock(ohlc.copy(), scale, offset,
                                       dict(zip((days - 2).tolist(), actual.tolist())))
        for pos in candidates:
            row = rows[pos]
            pullback = 0 <= bias20[pos] <= 0.03 and ohlc[row, 3] >= ohlc[row, 0]
            ranked[market_days[pos]].append((-round(float(ret60[pos] / std60[pos]), 10),
                                             -float(yields[pos]), code, bool(pullback)))
    if not witnesses or max_error >= 1e-11 or np.any(breadth == 0) or not pool.any():
        raise ValueError("affine parity or main-board coverage failed")
    daily = {"breadth_n": breadth, "above_ma20": above, "pool_n": pool, "trend_n": trend}
    return stocks, [sorted(rows) for rows in ranked[2:]], daily, pool_days, {
        "main_board_symbols": len(board), "affine_witnesses": witnesses, "max_abs_ohlc_error": max_error,
    }


def states(g2_preroll, daily, width):
    strong = g2_preroll & (daily["above_ma20"] / daily["breadth_n"] >= width)
    active = ~(strong[:-2] | strong[1:-1] | strong[2:])
    pool, trend = daily["pool_n"][2:], daily["trend_n"][2:]
    hugging = (pool >= 15) & (trend >= 2) & (trend >= 0.40 * pool)
    labels = np.select([strong[2:], active & hugging, active], [STRONG, HUG, DEFENSE], default=BUFFER)
    return strong[2:], active, labels


def prepare(root):
    identity, blobs, protocol_hash = verify_inputs(root)
    prior = load_archive(blobs)
    calendar = sys.modules["fetch_defensive_etf_validation_inputs"].sessions()
    start = calendar.index(START)
    dates = calendar[start:]
    etf, diagnostics = prior.load_etf(root, calendar, start)
    etf_manifest = json.loads(blobs[f"{PRIOR_DATA}/raw/input_manifest.json"])
    if diagnostics != {code: etf_manifest["verification"][code] for code in prior.SYMBOLS}:
        raise ValueError("ETF gate differs from archived validation")
    index, stamps, g2_preroll = prior.load_index(root, dates)
    g2 = g2_preroll[2:]
    weeks = prior.last_of_week(dates)
    masks = {year: np.array([day.startswith(year) for day in dates]) for year in YEARS}
    print("Frozen inputs verified; reconstructing the Stage 0 B V2 qualification.", flush=True)
    b_stocks, b_ranked, b_counts = prior.b_signals(root, dates, g2, index, stamps)
    b_tape, b_audit = prior.b_tape(b_stocks, b_ranked, g2, constrained=True)
    expected = json.loads(blobs[f"{PRIOR_DATA}/summary.json"])
    champion = next(row for row in expected["matrix"] if row["id"] == expected["decision"]["selected"])
    if (champion["regime"], champion["allocation"]) != (prior.REGIMES[1], prior.ALLOCATIONS[0]):
        raise ValueError("archived champion is not R1/A1")
    if b_counts != expected["b_v2_qualification"] or b_audit != expected["baseline"]["ledger"]:
        raise ValueError("Stage 0 qualification or B ledger failed exact archived parity")
    baseline = {}
    active = prior.defensive_modes(g2_preroll)[1]
    for fee, side in COSTS.items():
        nav, audit = prior.portfolio(etf, g2, b_tape, active=active, weeks=weeks, allocation=0, side_cost=side)
        archived_cost = champion["costs"][fee]
        returns = prior.daily_returns(nav)
        if (not np.array_equal(returns, archived_cost["account_daily_return"])
                or prior.risk_metrics(nav, masks) != archived_cost["account"]
                or audit != archived_cost["account_audit"]):
            raise ValueError(f"R1/A1 Stage 0 archived account mismatch at {fee}")
        baseline[fee] = nav
    print("Stage 0 exact parity verified at 5 and 10 bps.", flush=True)
    warm_stamps = np.array([row["stamp"] for row in index[-len(dates) - 2:]])
    return (prior, dates, g2_preroll, active, weeks, masks, b_stocks, b_ranked, b_tape, b_counts,
            b_audit, etf, diagnostics, baseline, warm_stamps, identity, protocol_hash)


@dataclass
class DividendPosition:
    entry: int
    basis: int
    price: float
    due: bool = False
    last_gross: float = 1.0

    def gross(self, stock, row, price):
        basis = stock.convert(self.price, self.basis, row)
        if min(price, basis) <= 0:
            raise ValueError("non-positive dividend execution price or causal cost")
        return price / basis


def dividend_exit(stock, trade, day, row, mode):
    if day == trade.entry:
        return None
    timed = mode == "X2" and day >= trade.entry + 25
    if row is None:
        trade.due |= timed
        return None
    opening, high, low, close = stock.ohlc[row]
    stop = stock.convert(trade.price * (0.94 if mode == "X1" else 0.95), trade.basis, row)
    if stock.locks(row)[1]:
        trade.due |= timed or low <= stop
        return None
    target = (stock.convert(trade.price * 1.10, trade.basis, row) if mode == "X2" else np.inf)
    if trade.due or opening <= stop or opening >= target:
        return "open", opening, "OPEN_EXIT"
    if low <= stop:
        return "late", stop, "AMBIGUOUS_SAME_BAR_STOP" if high >= target else "STOP"
    if high >= target:
        return "late", target, "TARGET"
    if timed:
        return "late", close, "TIME_EXIT_CLOSE"
    return None


def below_ma30(stock, row):
    history = stock.ohlc[row - 29:row + 1, 3]
    adjusted = (stock.scale[row] * (history - stock.offset[row - 29:row + 1])
                / stock.scale[row - 29:row + 1] + stock.offset[row])
    return len(history) == 30 and np.all(adjusted > 0) and history[-1] < adjusted.mean()


@dataclass
class DividendDay:
    open_marks: dict = field(default_factory=dict)
    open_sales: dict = field(default_factory=dict)
    entries: list = field(default_factory=list)
    late_sales: dict = field(default_factory=dict)
    close_marks: dict = field(default_factory=dict)
    accepted: list = field(default_factory=list)
    closes: list = field(default_factory=list)


def assess_open_and_exits(stocks, positions, today, day, close_exit, cooldown):
    # Late exits remain occupied during entry funding. Missing bars retain the last valid mark.
    for code, pos in list(positions.items()):
        stock = stocks[code]
        row = stock.by_day.get(day)
        today.open_marks[code] = pos.last_gross if row is None else pos.gross(stock, row, stock.ohlc[row, 0])
        outcome = close_exit(stock, pos, day, row)
        if outcome:
            phase, price, status = outcome
            gross = pos.gross(stock, row, price)
            (today.open_sales if phase == "open" else today.late_sales)[code] = gross
            if isinstance(today, DividendDay):
                today.closes.append((code, status, float(gross - 1 - 2 * STOCK_SIDE)))
            cooldown[code] = day + 5


def mark_close(stocks, positions, today, day):
    for code in (*today.open_sales, *today.late_sales):
        del positions[code]
    for code, pos in positions.items():
        stock = stocks[code]
        row = stock.by_day.get(day)
        if row is not None:
            pos.last_gross = pos.gross(stock, row, stock.ohlc[row, 3])
        today.close_marks[code] = pos.last_gross


def shared_tape(prior, b_stocks, b_ranked, div_stocks, div_ranked, labels, weeks, mode, *, slots):
    b_pos, div_pos, b_pending, b_cd, div_cd = {}, {}, {}, {}, {}
    div_pending = []
    result_b, result_div = [], []
    for day, label in enumerate(labels):
        previous = labels[day - 1] if day else BUFFER
        b, div = prior.BDay(), DividendDay()
        assess_open_and_exits(b_stocks, b_pos, b, day, prior.exit_for_day, b_cd)
        assess_open_and_exits(div_stocks, div_pos, div, day,
                              lambda stock, pos, i, row: dividend_exit(stock, pos, i, row, mode), div_cd)
        open_b = set(b_pos) - set(b.open_sales)
        open_div = set(div_pos) - set(div.open_sales)
        if len(open_b) + len(open_div) > slots or open_b & open_div:
            raise ValueError("opening stock slots overlap")
        if previous == STRONG:
            capacity = slots - len(open_b) - len(open_div)
            executable = [code for code in b_pending if code not in open_div][:capacity]
            b.order_count = len(executable)
            for code in executable:
                signal, order = b_pending[code]
                stock = b_stocks[code]
                row = stock.by_day.get(day)
                if row is None or stock.locks(row)[0]:
                    continue
                opening, high = stock.ohlc[row, :2]
                trigger = stock.convert(order.trigger, order.origin, row)
                if high >= trigger:
                    b_pos[code] = prior.BPosition(signal, day, row, max(float(opening), trigger), order)
                    b_pos[code].due = day >= signal + 10
                    b.entries.append(code)
                    del b_pending[code]
        b_pending = {code: order for code, order in b_pending.items() if day < order[0] + 10}
        for code in div_pending:
            stock = div_stocks[code]
            row = stock.by_day.get(day)
            if row is None or code in open_b:
                continue
            locked_up, locked_down = stock.locks(row)
            if not locked_up:
                div_pos[code] = DividendPosition(day, row, float(stock.ohlc[row, 0]), due=bool(locked_down))
                div.entries.append(code)
        if len(open_b) + len(open_div) + len(b.entries) + len(div.entries) > slots or len(open_div) + len(div.entries) > 2:
            raise ValueError("stock entries exceed shared capacity")
        mark_close(b_stocks, b_pos, b, day)
        mark_close(div_stocks, div_pos, div, day)
        if label == STRONG:
            selected = 0
            for code, order in b_ranked[day]:
                # Strong-close B orders may prepare for funded dividend displacements.
                # Actual fills are capped against the positions that survive the opening.
                if selected == 3 or len(b_pos) + len(b_pending) >= slots:
                    break
                if code in b_pos or code in b_pending or b_cd.get(code, -1) >= day:
                    continue
                b_pending[code] = day, order
                b_cd[code] = day + 5
                selected += 1
        b.occupied_at_close = len(b_pos) + len(b_pending)
        div_pending = []
        for code, pos in div_pos.items():
            stock = div_stocks[code]
            row = stock.by_day.get(day)
            weekly_exit = mode == "X1" and weeks[day] and row is not None and below_ma30(stock, row)
            pos.due |= label == STRONG or (mode == "X1" and label == DEFENSE) or weekly_exit
        if label == HUG and (mode == "X2" or previous != HUG or weeks[day]):
            capacity = min(2, slots - len(b_pos)) - len(div_pos)
            for _, _, code, pullback in div_ranked[day]:
                if len(div_pending) == capacity:
                    break
                if code in b_pos or code in div_pos or div_cd.get(code, -1) >= day or (mode == "X2" and not pullback):
                    continue
                div_pending.append(code)
        div.accepted = div_pending
        result_b.append(b)
        result_div.append(div)
    return result_b, result_div


def sale(book, marks):
    return sum(book.pop(code) * (gross - STOCK_SIDE) for code, gross in marks.items())


def value(book, marks):
    return sum(book[code] * (gross - STOCK_SIDE) for code, gross in marks.items() if code in book)


def portfolio(prior, etf, strong, active, weeks, b_tape, div_tape, *, side, slots=6, resize=False):
    cash, b, div, receivables = 1.0, {}, {}, {}
    shares = np.zeros(len(prior.SYMBOLS))
    directive, last_ratio = None, None
    weights_at_confirmation = np.zeros_like(shares)
    previous_values = np.zeros(3)
    nav, contributions, audit = [], [], Counter()
    for i, (b_day, div_day) in enumerate(zip(b_tape, div_tape)):
        flows = np.zeros(3)
        if etf is not None:
            etf_start = cash
            cash += receivables.pop(i, 0.0)
            for column, dividend in enumerate(etf.dividends[i]):
                if dividend and shares[column] > 0:
                    payment = etf.payments[i, column]
                    amount = shares[column] * dividend
                    if payment == i:
                        cash += amount
                    else:
                        receivables[payment] = receivables.get(payment, 0.0) + amount
                    audit["dividend_accrued"] += amount
            prices = etf.opens[i]
            if i and strong[i - 1]:
                cash, shares, turnover, fees = prior.rebalance(cash, shares, prices, np.zeros_like(shares), side)
                audit["etf_turnover"] += turnover
                audit["etf_fees"] += fees
                last_ratio = None
                directive = None
            flows[2] += cash - etf_start
        else:
            prices = np.zeros_like(shares)

        if set(b) != set(b_day.open_marks) or set(div) != set(div_day.open_marks):
            raise ValueError("opening stock positions disagree with the execution tape")
        flows[0] = sale(b, b_day.open_sales)
        flows[1] = sale(div, div_day.open_sales)
        cash += flows[0]
        if div_day.open_sales:
            cash += flows[1]
        liquid = cash + float(shares @ prices)
        opening_equity = (liquid + value(b, b_day.open_marks) + value(div, div_day.open_marks)
                          + sum(receivables.values()))
        if b_day.order_count and (np.any(shares > EPS) or div_day.entries):
            raise ValueError("B, dividend entry and ETF share an opening budget")

        targets = None
        if etf is not None and i and active[i - 1]:
            used_slots = len(b) + len(div) + len(div_day.entries)
            free_ratio = (slots - used_slots) / slots
            slot_change = (last_ratio is not None and free_ratio != last_ratio) or bool(div_day.entries)
            if directive is not None or (resize and slot_change):
                ratio, weights = directive if directive is not None else (free_ratio, weights_at_confirmation)
                if resize:
                    ratio = free_ratio
                stock_reserve = opening_equity * len(div_day.entries) / slots
                targets = min(ratio * opening_equity, max(0.0, liquid - stock_reserve)) * weights
                last_ratio = ratio
                if div_day.entries:
                    before = cash
                    cash, shares, turnover, fees = prior.rebalance(
                        cash, shares, prices, np.minimum(targets, shares * prices), side,
                    )
                    flows[2] += cash - before
                    audit["etf_turnover"] += turnover
                    audit["etf_fees"] += fees
                else:
                    before = cash
                    cash, shares, turnover, fees = prior.rebalance(cash, shares, prices, targets, side)
                    flows[2] += cash - before
                    audit["etf_turnover"] += turnover
                    audit["etf_fees"] += fees
                    targets = None
            if resize and last_ratio is None:
                last_ratio = free_ratio

        for leg, book, today, count in ((0, b, b_day, b_day.order_count), (1, div, div_day, len(div_day.entries))):
            if not today.entries:
                continue
            if len(today.entries) > count:
                raise ValueError("fill exceeds executable stock orders")
            budget = min(opening_equity / slots, cash / count)
            if not np.isfinite(budget) or budget <= 0:
                raise ValueError("stock order lacks unencumbered opening funds")
            for code in today.entries:
                if code in b or code in div:
                    raise ValueError("duplicate funded security")
                book[code] = budget / (1 + STOCK_SIDE)
                cash -= budget
                flows[leg] -= budget
            audit["b_buys" if leg == 0 else "dividend_buys"] += len(today.entries)
        audit["peak_open_stock_slots"] = max(audit["peak_open_stock_slots"], len(b) + len(div))
        if cash < -EPS or len(b) + len(div) > slots or len(div) > 2:
            raise ValueError("opening cash or funded slot use is invalid")

        if targets is not None:
            before = cash
            cash, shares, turnover, fees = prior.rebalance(max(cash, 0.0), shares, prices, targets, side)
            flows[2] += cash - before
            audit["etf_turnover"] += turnover
            audit["etf_fees"] += fees
        for leg, book, today in ((0, b, b_day), (1, div, div_day)):
            proceeds = sale(book, today.late_sales)
            cash += proceeds
            flows[leg] += proceeds
            if set(book) != set(today.close_marks):
                raise ValueError("closing stock positions disagree with the execution tape")
        if cash < -EPS or not len(b) <= b_day.occupied_at_close <= slots:
            raise ValueError("cash overspent or B slot reservation invalid")
        cash = max(cash, 0.0)
        audit["minimum_cash"] = min(audit.get("minimum_cash", 1.0), cash)
        closing = etf.closes[i] if etf is not None else prices
        etf_mark = float(shares @ closing)
        b_mark = value(b, b_day.close_marks)
        div_mark = value(div, div_day.close_marks)
        receivable = sum(receivables.values())
        equity = cash + etf_mark + receivable + b_mark + div_mark
        if not np.isfinite(equity) or equity <= 0:
            raise ValueError("account equity is not finite and positive")
        nav.append(equity)
        marked = np.array([b_mark, div_mark, etf_mark + receivable])
        daily_pnl = flows + marked - previous_values
        if abs(float(daily_pnl.sum()) - (equity - (nav[-2] if i else 1.0))) > EPS:
            raise ValueError("cash and leg attribution do not reconcile to account NAV")
        contributions.append(daily_pnl)
        previous_values = marked
        directive = None
        if etf is not None:
            activated = i == 0 or not active[i - 1]
            qualified = etf.eligible[i]
            weights = prior.target_weights(qualified, etf.volatility[i], 0)
            if active[i] and (activated or weeks[i]):
                weights_at_confirmation = weights
            if not active[i]:
                last_ratio = None
            directive = prior.setting_at_close(strong[i], activated, active[i], weeks[i], weights, qualified,
                                                shares, closing, equity, (slots - len(b) - len(div)) / slots)
    audit["outstanding_etf_receivable"] = sum(receivables.values())
    audit["ending_stock_slots"] = len(b) + len(div)
    audit["ending_dividend_slots"] = len(div)
    audit["max_cash_overlap"] = 0
    return np.asarray(nav), np.asarray(contributions), dict(audit)


def daily_returns(nav):
    return nav / np.r_[1.0, nav[:-1]] - 1


def risk(returns, nav=None):
    equity = np.r_[1.0, np.cumprod(1 + returns) if nav is None else nav]
    drawdown = float(np.max(1 - equity / np.maximum.accumulate(equity)))
    net = float(equity[-1] - 1)
    return {"return": net, "drawdown": drawdown, "return_drawdown": net / drawdown if drawdown > 0 else None}


def block_indices(length, rng):
    starts = rng.integers(0, length - BLOCK + 1, (REPLICATES, (length + BLOCK - 1) // BLOCK))
    return (starts[:, :, None] + np.arange(BLOCK)).reshape(REPLICATES, -1)[:, :length]


def interval(values):
    return np.quantile(values, [0.025, 0.975], method="linear").tolist()


def bootstrap_daily(delta):
    indices = block_indices(len(delta), np.random.default_rng(SEED))
    return interval(delta[indices].mean(axis=1))


def bootstrap_weak(returns, baseline, masks):
    rng = np.random.default_rng(SEED)
    deltas = np.zeros(REPLICATES)
    for year in WEAK_YEARS:
        mask = masks[year]
        indices = block_indices(int(mask.sum()), rng)
        deltas += (1 + returns[mask][indices]).prod(axis=1) - (1 + baseline[mask][indices]).prod(axis=1)
    return interval(deltas)


def build_masks(dates):
    dates = np.asarray(dates)
    masks = {year: np.char.startswith(dates, year) for year in YEARS}
    masks.update({name: (dates >= start) & (dates <= end) for name, (start, end) in SLICES_2026.items()})
    return masks


def account_record(nav, pnl, audit, labels, masks):
    returns = daily_returns(nav)
    records = {}
    for name, mask in masks.items():
        records[name] = {
            **risk(returns[mask]), "states": dict(sorted(Counter(labels[mask]).items())),
            "net_pnl_initial_capital": dict(zip(("B", "dividend", "bond_gold"), pnl[mask].sum(axis=0).tolist())),
        }
    return {
        "full": risk(returns, nav), "periods": records, "daily_return": returns.tolist(), "audit": audit,
        "weak_years_return_sum": sum(records[year]["return"] for year in WEAK_YEARS),
    }


def top_selected(tapes, pool_days):
    selections = Counter(code for tape in tapes for day in tape for code in day.accepted)
    fills = Counter(code for tape in tapes for day in tape for code in day.entries)
    return [{"code": code, "selected": selections[code], "filled": fills[code], "pool_days": pool_days[code]}
            for code in sorted(selections, key=lambda code: (-selections[code], code))[:15]]


def sleeve_record(nav, tape, masks, pool_days):
    returns = daily_returns(nav)
    periods = {}
    for key, mask in {"all": np.ones(len(tape), dtype=bool), **masks}.items():
        days = [day for day, included in zip(tape, mask) if included]
        trades = [item for day in days for item in day.closes]
        net = [item[2] for item in trades]
        periods[key] = {
            **risk(returns[mask]), "filled": sum(len(day.entries) for day in days), "closed": len(trades),
            "ambiguous_as_stop": sum(status == "AMBIGUOUS_SAME_BAR_STOP" for _, status, _ in trades),
            "net_win_rate": float(np.mean(np.asarray(net) > 0)) if trades else None,
            "net_mean": float(np.mean(net)) if trades else None,
        }
    return {"periods": periods, "top15": top_selected([tape], pool_days)}


def compare(stage, baseline, matched, sleeve, masks):
    is_stage_one = matched is None
    independent = None
    if not is_stage_one:
        periods = sleeve["periods"]
        independent = {
            "2023_positive": periods["2023"]["return"] > 0,
            "2026_positive": periods["2026"]["return"] > 0,
            "full_positive": periods["all"]["return"] > 0,
            "drawdown_within_8pct": periods["all"]["drawdown"] <= 0.08,
        }
    at_cost = {}
    for fee in COSTS:
        row, s0 = stage[fee], baseline[fee]
        a, b = row["full"], s0["full"]
        annual_delta = row["periods"]["2026"]["return"] - s0["periods"]["2026"]["return"]
        weak_delta = row["weak_years_return_sum"] - s0["weak_years_return_sum"]
        ratio = a["return_drawdown"] is not None and b["return_drawdown"] is not None
        gates = {"full_return_above_stage0": a["return"] > b["return"],
                 "drawdown_within_stage0_multiple": a["drawdown"] <= (1.02 if is_stage_one else 1.05) * b["drawdown"]}
        returns = np.asarray(row["daily_return"])
        if is_stage_one:
            delta = returns - s0["daily_return"]
            gates.update({"return_drawdown_above_stage0": ratio and a["return_drawdown"] > b["return_drawdown"],
                          "2026_return_above_stage0": annual_delta > 0, "daily_excess_mean_positive": delta.mean() > 0})
            observed, ci = float(delta.mean()), bootstrap_daily(delta)
            matched_full = None
        else:
            peer = matched[fee]
            matched_full = a["return"] - peer["full"]["return"]
            observed = row["weak_years_return_sum"] - peer["weak_years_return_sum"]
            gates.update({"return_drawdown_at_least_stage0": ratio and a["return_drawdown"] >= b["return_drawdown"],
                          "weak_years_above_stage0": weak_delta > 0, "full_return_above_stage1": matched_full > 0,
                          "weak_years_above_stage1": observed > 0})
            ci = bootstrap_weak(returns, np.asarray(peer["daily_return"]), masks)
        at_cost[fee] = {
            "economic_gates": {key: bool(passed) for key, passed in gates.items()},
            "full_return_delta_vs_stage0": a["return"] - b["return"], "2026_delta_vs_stage0": annual_delta,
            "weak_years_delta_vs_stage0": weak_delta, "full_return_delta_vs_stage1": matched_full,
            "bootstrap_observed": observed, "bootstrap_ci95": ci,
        }
    independent_pass = independent is None or all(independent.values())
    economic_pass = independent_pass and all(all(cost["economic_gates"].values()) for cost in at_cost.values())
    intervals = [cost["bootstrap_ci95"] for cost in at_cost.values()]
    if economic_pass and all(low > 0 for low, _ in intervals):
        decision = "ADOPT"
    elif economic_pass and all(low > 0 or low <= 0 <= high for low, high in intervals):
        decision = "NEEDS_MORE_EVIDENCE"
    elif not is_stage_one and independent_pass and any(
        cost["full_return_delta_vs_stage1"] < 0 or cost["bootstrap_observed"] < 0 for cost in at_cost.values()
    ):
        decision = DEFER
    else:
        decision = "REJECT"
    return {"status": decision, "standalone_gates": independent, "costs": at_cost}


def choose(ranked, decisions):
    for status in ("ADOPT", "NEEDS_MORE_EVIDENCE", DEFER):
        matches = [name for name in ranked if decisions[name]["status"] == status]
        if matches:
            return {"status": status, "selected": matches[0] if status == "ADOPT" else None, "matching_rows": matches}
    return {"status": "REJECT", "selected": None, "matching_rows": []}


def run(root):
    (prior, dates, g2_preroll, active0, weeks, _, b_stocks, b_ranked, b_tape, b_counts,
     b_audit, etf, etf_diagnostics, baseline, warm_stamps, inputs, protocol_hash) = prepare(root)
    g2 = g2_preroll[2:]
    masks = build_masks(dates)
    div_stocks, div_ranked, daily, pool_days, stock_audit = load_market(root, prior, warm_stamps)
    print("Causal breadth and dividend pool verified; replaying the fixed seven-account matrix.", flush=True)
    regimes = {width: states(g2_preroll, daily, threshold) for width, threshold in WIDTHS.items()}
    stage0_labels = np.select([g2, active0], [STRONG, DEFENSE], default=BUFFER)
    accounts, sleeves, evaluations, diagnostic_tapes = {}, {}, {}, []

    def replay(name, strong, active, labels, tape, dividend_tape=None, archived_path=None):
        accounts[name] = {}
        for fee, side in COSTS.items():
            nav, attribution, audit = portfolio(
                prior, etf, strong, active, weeks, tape,
                dividend_tape if dividend_tape is not None else [DividendDay()] * len(dates),
                side=side, resize=dividend_tape is not None,
            )
            if dividend_tape is None:
                reference = (archived_path[fee] if archived_path is not None else prior.portfolio(
                    etf, strong, tape, active=active, weeks=weeks, allocation=0, side_cost=side,
                )[0])
                if not np.allclose(nav, reference, rtol=0, atol=EPS):
                    raise ValueError(f"{name}/{fee} component ledger failed reference parity")
                nav = reference
            accounts[name][fee] = account_record(nav, attribution, audit, labels, masks)

    replay("S0_R1_A1", g2, active0, stage0_labels, b_tape, archived_path=baseline)
    for width, (strong, active, labels) in regimes.items():
        s1 = f"S1_{width}"
        width_b_tape, _ = prior.b_tape(b_stocks, b_ranked, strong, constrained=True)
        replay(s1, strong, active, labels, width_b_tape)
        evaluations[s1] = compare(accounts[s1], accounts["S0_R1_A1"], None, None, masks)
        for mode in ("X1", "X2"):
            key = f"{width}_{mode}"
            s2 = f"S2_{key}"
            shared_b, shared_div = shared_tape(
                prior, b_stocks, b_ranked, div_stocks, div_ranked, labels, weeks, mode, slots=6,
            )
            replay(s2, strong, active, labels, shared_b, shared_div)
            sleeve_b, sleeve_div = shared_tape(
                prior, {}, [[] for _ in dates], div_stocks, div_ranked, labels, weeks, mode, slots=2,
            )
            standalone, _, _ = portfolio(
                prior, None, strong, active, weeks, sleeve_b, sleeve_div, side=0, slots=2,
            )
            sleeves[key] = sleeve_record(standalone, sleeve_div, masks, pool_days)
            diagnostic_tapes.append(sleeve_div)
            evaluations[s2] = compare(accounts[s2], accounts["S0_R1_A1"], accounts[s1], sleeves[key], masks)
    return {
        "study": STUDY, "classification": "non-blocking research question / STRICT PATH",
        "protocol_commit": PROTOCOL_COMMIT, "protocol_sha256_lf": protocol_hash,
        "inputs": inputs, "etf_validation": etf_diagnostics, "market_validation": stock_audit,
        "stage0_exact_parity": {"archive": ARCHIVE, "matched_sessions_per_cost": len(dates), "costs": list(COSTS),
                                "b_qualification": b_counts, "b_ledger": b_audit},
        "window": {"first": START, "cutoff": CUTOFF, "sessions": len(dates), "dates": dates},
        "daily_market": {
            **{name: values[2:].tolist() for name, values in daily.items()},
            "b20": (daily["above_ma20"][2:] / daily["breadth_n"][2:]).tolist(),
            "dividend_trend": [float(trend / pool) if pool else None
                               for trend, pool in zip(daily["trend_n"][2:], daily["pool_n"][2:])],
            "g2": g2.tolist(), **{width: values[2].tolist() for width, values in regimes.items()},
        },
        "accounts": accounts, "sleeves": sleeves, "top15": top_selected(diagnostic_tapes, pool_days),
        "bootstrap": {"block_sessions": BLOCK, "replicates": REPLICATES, "seed": SEED},
        "evaluations": evaluations,
        "DECISION_STAGE1_BREADTH_GATE": choose(["S1_W50", "S1_W45"], evaluations),
        "DECISION_STAGE2_DIVIDEND_SLEEVE": choose(
            [f"S2_{width}_{mode}" for mode in ("X1", "X2") for width in ("W50", "W45")], evaluations,
        ),
    }


def percent(value):
    return "—" if value is None else f"{100 * value:.3f}%"


def ratio(value):
    return "—" if value is None else f"{value:.3f}"


def table(headers, rows):
    return ["| " + " | ".join(headers) + " |", "| " + " | ".join("---" for _ in headers) + " |",
            *["| " + " | ".join(map(str, row)) + " |" for row in rows], ""]


def render_report(result, digest):
    decisions = ("DECISION_STAGE1_BREADTH_GATE", "DECISION_STAGE2_DIVIDEND_SLEEVE")
    lines = [
        "# 三态市场温度计与高股息大盘龙头卫星验证", "",
        "评估期为 2023-06-30 至 2026-08-28，共 769 个 XSHG 交易日。2023 和 2026 为部分年份。",
        "本轮归类保持为非阻塞 research question，走 STRICT PATH。", "",
        *[f"- `{key}` **{result[key]['status']}**"
          + (f"，选中 `{result[key]['selected']}`" if result[key]["selected"] else "")
          for key in decisions], "",
        f"Stage 0 两档费用各 769 个日收益点、B 资格及账本与原 R1/A1 归档精确相同。"
        f"主板冻结样本共 {result['market_validation']['main_board_symbols']} 个代码。"
        f"仿射复权对照 {result['market_validation']['affine_witnesses']} 组，"
        f"最大 OHLC 误差 {result['market_validation']['max_abs_ohlc_error']:.3g} 元。", "",
        "## 六槽单账户全期与分年净收益", "",
    ]
    accounts = result["accounts"]
    for fee in COSTS:
        lines.extend([f"### ETF 双边 {fee.split('_')[0]} bps", ""])
        lines.extend(table(["组别", "全期", "最大回撤", "收益/回撤", *YEARS, "2023+2026 合计"], [
            [name, percent(cost["full"]["return"]), percent(cost["full"]["drawdown"]),
             ratio(cost["full"]["return_drawdown"]), *[percent(cost["periods"][year]["return"]) for year in YEARS],
             percent(cost["weak_years_return_sum"])]
            for name, costs in accounts.items() for cost in [costs[fee]]
        ]))
    lines.extend(["## 预注册判定", "",
                  "Stage 1 的 CI 为全期超额日均，Stage 2 的 CI 为相对同宽度 Stage 1 的两个弱年复利收益差之和。",
                  "区间单位为百分点。", ""])
    failures = {
        "full_return_above_stage0": "全期收益 vs S0", "drawdown_within_stage0_multiple": "回撤上限",
        "return_drawdown_above_stage0": "收益回撤比 vs S0", "2026_return_above_stage0": "2026 收益 vs S0",
        "daily_excess_mean_positive": "超额日均", "return_drawdown_at_least_stage0": "收益回撤比 vs S0",
        "weak_years_above_stage0": "弱年收益 vs S0", "full_return_above_stage1": "全期收益 vs S1",
        "weak_years_above_stage1": "弱年收益 vs S1",
    }
    lines.extend(table(["组别", "ETF 双边成本", "独立盈利门", "未过组合经济门", "实际超额", "95% CI", "组判定"], [
        [name, fee.replace("_", " "), ("—" if outcome["standalone_gates"] is None else
          "通过" if all(outcome["standalone_gates"].values()) else "未过"),
         "、".join(failures[gate] for gate, passed in row["economic_gates"].items() if not passed) or "均通过",
         percent(row["bootstrap_observed"]), " 至 ".join(map(percent, row["bootstrap_ci95"])), outcome["status"]]
        for name, outcome in result["evaluations"].items() for fee, row in outcome["costs"].items()
    ]))
    lines.extend(["## 2026 年三段市场状态与损益拆解", "",
                  "状态天数按当日收盘计算。三条腿均含费用，按初始本金列示，合计等于该段账户权益变动。",
                  "Stage 0 沿用 G2 与 R1 确认，状态列中的全面防守对应原防守激活日。", ""])
    segment_labels = dict(zip(SLICES_2026, ("1–3 月", "4–6 月", "7–8 月")))
    for fee in COSTS:
        lines.extend([f"### ETF 双边 {fee.split('_')[0]} bps", ""])
        lines.extend(table(["区间", "组别", "强态", "抱团", "全面防守", "观察缓冲", "B 损益", "红利损益", "债金损益"], [
            [segment_label, name, *[row["states"].get(label, 0) for label in (STRONG, HUG, DEFENSE, BUFFER)],
             *[percent(row["net_pnl_initial_capital"][leg]) for leg in ("B", "dividend", "bond_gold")]]
            for key, segment_label in segment_labels.items() for name, costs in accounts.items()
            for row in [costs[fee]["periods"][key]]
        ]))
    lines.extend(["## 独立两槽红利诊断", "",
                  "X1 为中线持有，X2 为 MA20 回踩波段。成交按买入日，净胜率与单笔净均值按结案日。",
                  "模糊单按止损计入，双边股票费用为 20 bps。", ""])
    lines.extend(table(["组别", "区间", "成交", "结案", "双触及", "净胜率", "单笔净均值", "累计净收益", "最大回撤"], [
        [name, segment_labels.get(key, "全期" if key == "all" else key), row["filled"], row["closed"], row["ambiguous_as_stop"],
         percent(row["net_win_rate"]), percent(row["net_mean"]), percent(row["return"]), percent(row["drawdown"])]
        for name, sleeve in result["sleeves"].items() for key, row in sleeve["periods"].items()
    ]))
    lines.extend(["## 高股息动态池高频入选 TOP15", "",
                  "合并四个独立两槽面板。同一代码在不同面板的入选分别计数，池内天数来自同一动态池。",
                  "高频代码包括建设银行（601939.sh）、中国神华（601088.sh）、陕西煤业（601225.sh）"
                  "和华电国际（600027.sh）。",
                  "冻结输入提供股票代码和行情，本表未使用额外的行业或历史市值映射。", ""])
    lines.extend(table(["代码", "入选次数", "实际买入次数", "池内天数"], [
        [row["code"], row["selected"], row["filled"], row["pool_days"]] for row in result["top15"]
    ]))
    for name, sleeve in result["sleeves"].items():
        lines.extend([f"- `{name}` 入选频次顺序为 "
                      + "、".join(f"`{row['code']}`（{row['selected']}）" for row in sleeve["top15"]) + "。"])
    if any(result[key]["status"] == "NEEDS_MORE_EVIDENCE" for key in decisions):
        lines.extend(["", "需要独立的前瞻冻结日样本缩窄相应的超额区间，供未来独立观察提案使用。现行日报路径可继续。"])
    lines.extend(["", "## 证据与范围", "",
                  "这是冻结发展样本。历史 ST 与当日供应商快照未独立验证，成交额仅为流动性代理。",
                  "市场状态使用窗口开始前两个交易日预热，所有评估收益在截止日收盘结束。",
                  f"预注册提交 `{result['protocol_commit']}`。汇总 SHA-256 `{digest}`。", ""])
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    try:
        result = run(ROOT)
    except (ValueError, OSError, subprocess.CalledProcessError) as exc:
        raise SystemExit(f"PARTIAL_UNVERIFIED: {exc}") from exc
    raw = (json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False, sort_keys=True) + "\n").encode("utf-8")
    digest = sha256(raw).hexdigest()
    (ROOT / SUMMARY).write_bytes(raw)
    (ROOT / REPORT).write_text(render_report(result, digest), encoding="utf-8", newline="\n")
    print(f"summary SHA-256 {digest}")


if __name__ == "__main__":
    main()
