"""Offline, protocol-locked DEVELOPMENT replay for C funnel and early starts."""

from __future__ import annotations

from bisect import bisect_left
from collections import Counter, defaultdict
from dataclasses import dataclass
import gzip
from hashlib import sha256
import json
import math
from pathlib import Path, PurePosixPath
import re
from statistics import fmean
import subprocess
from typing import NamedTuple

import numpy as np
from numpy.lib.stride_tricks import sliding_window_view

import c_pre_outcome_design as frozen_c
import core_signal_replay as replay
from track_perf import EXIT_REASON_AMBIGUOUS, _sellable_exit_decision


ROOT = Path(__file__).resolve().parents[1]
PROTOCOL = 'docs/research/c_bottom_higher_low_early_v1_protocol.md'
PROTOCOL_COMMIT = 'a0d464c5b2c6497c3ac116d79e06c07d6e52d666'
RUNTIME_COMMIT = 'cce76bf0a205a57b4fbde0ce279e89f4a3c26267'
REGISTRY = 'data/governance/frozen_artifacts.json'
VALIDATION = 'data/validation/'
RAW = VALIDATION + 'core_signal_validation/raw/'
DAILY = RAW + 'daily_k.parquet'
FACTORS = RAW + 'adjustment_factors.parquet'
INDEX = [RAW + f'index_000001_SH_{year}.json' for year in range(2023, 2027)]
MANIFEST = VALIDATION + 'core_signal_validation_continuous_parts/core_signal_validation_manifest.json'
B_EVENTS = VALIDATION + 'strategy_candidate_eligibility_v1/b_breakout_retest_eligibility_events.jsonl.gz'
OUTPUT = VALIDATION + 'c_bottom_higher_low_early_v1/summary.json'
REPORT = 'docs/research/c_bottom_higher_low_early_v1_report.md'
FUNNEL = 'data/research/c_rule_funnel_capture_v1/'
SIMULATION = 'data/research/c_simulation_v1/'
HASHES = dict(zip([DAILY, FACTORS, *INDEX, MANIFEST, B_EVENTS], (
    '61189a4850e2eb157453e28e5375e502e20d214508bbe70ea71066ca3e05e426',
    'a1b7d63c5826ccd3610dc9bdd949d82eeb0ba84ffad451bfb8bb30ca74962716',
    'c118fb39d31065914740da150455fba2375d3bcaa83566730d265df0753bb51c',
    '53fc9e9f0989e67f8a826614c5c8f260171cf081801bf752df6301e69f4ae4bf',
    '27acba0bd5bfc0f54d349d7dbc41a86bf6836dfee3976a970cbb210b287f76a1',
    '183f472a1699811edb2550f3ce99b2b05d06c23473b5e2acff0ad2431eaf1514',
    '008643a64e0070433f3d63dca8243f8dad294b049a7accb5d49af3597aae17b0',
    '8940a4a346ac6911ba669f84a9ceba7ef878b0ed0ce51edf673439b52aa056b9',
)))
C0, C1, C2, C3 = VARIANTS = (
    'C0_EXISTING_BALANCED_A', 'C1_BOTTOM_W_NECKLINE',
    'C2_BOTTOM_HL_EARLY_RECLAIM5', 'C3_BOTTOM_HL_EARLY_VOL',
)
C0_RR = 'C0_EXISTING_BALANCED_A_RR_CORRECTION'
RULES = tuple(frozen_c.RULE_CANDIDATES)
MARKET_GATES = ('G0', 'G2', 'G4')
MODES = ('S_ALL', 'TOP2')
COST = 0.002
EXPIRY, COOLDOWN = 10, 5
START, END = '2023-06-30', '2026-08-28'
WINDOWS = (('2024-02-06', '2024-02-29'), ('2024-09-18', '2024-09-30'))
PRICE = ('open', 'high', 'low', 'close')
SEED, BLOCK, DRAWS = 20261126, 20, 5000


def local_path(root: Path, relative: str) -> Path:
    allowed = {PROTOCOL, REGISTRY, OUTPUT, REPORT, *HASHES}
    if relative not in allowed:
        raise ValueError(f'INPUT_PATH_NOT_ALLOWED: {relative}')
    path = root / relative
    if path.resolve() != root.resolve() / PurePosixPath(relative):
        raise ValueError(f'INPUT_PATH_REDIRECTED: {relative}')
    return path


def git(root: Path, *args: str) -> bytes:
    return subprocess.check_output(['git', '--no-lazy-fetch', '-C', str(root), *args])


def lf(value: bytes) -> bytes:
    return value.replace(b'\r\n', b'\n')


def verify_protocol(root: Path) -> str:
    locked = lf(git(root, 'show', f'{PROTOCOL_COMMIT}:{PROTOCOL}'))
    if lf(local_path(root, PROTOCOL).read_bytes()) != locked:
        raise ValueError('PROTOCOL_LOCK_MISMATCH')
    return sha256(locked).hexdigest()


def verify_inputs(root: Path) -> dict:
    registry = {item['logical_path']: item['file_sha256']
                for item in json.loads(local_path(root, REGISTRY).read_bytes())['artifacts']
                if item['logical_path'] in HASHES}
    result = {}
    for relative, expected in HASHES.items():
        path = local_path(root, relative)
        actual = sha256(lf(path.read_bytes())).hexdigest() if relative == MANIFEST else replay.file_sha256(path)
        size = path.stat().st_size
        expected_size = {DAILY: 180203424, FACTORS: 295284}.get(relative, size)
        if registry.get(relative) != expected or actual != expected or size != expected_size:
            raise ValueError(f'FROZEN_INPUT_IDENTITY_MISMATCH: {relative}')
        result[relative] = {'sha256': actual, 'normalized_lf': relative == MANIFEST}
    return result


def runtime_blob(root: Path, path: str) -> bytes:
    if not re.fullmatch(r'data/research/(?:c_rule_funnel_capture_v1/(?:daily|near_miss)|c_simulation_v1)/[0-9]{8}\.json', path):
        raise ValueError(f'RUNTIME_PATH_NOT_ALLOWED: {path}')
    return git(root, 'show', f'{RUNTIME_COMMIT}:{path}')


def sum_counts(target: dict, source: dict) -> None:
    for key, value in source.items():
        if isinstance(value, dict):
            sum_counts(target.setdefault(key, {}), value)
        elif type(value) is int:
            target[key] = target.get(key, 0) + value
        else:
            raise ValueError(f'INVALID_COUNT: {key}')


def audit_runtime(root: Path) -> dict:
    paths = git(root, 'ls-tree', '-r', '--name-only', RUNTIME_COMMIT, '--',
                FUNNEL + 'daily', FUNNEL + 'near_miss', SIMULATION).decode().splitlines()
    totals = {rule: {} for rule in RULES}
    sampled = {rule: Counter() for rule in RULES}
    days, used, ledgers, plans = [], set(), [], defaultdict(list)
    bins = None
    for path in paths:
        if path.startswith(SIMULATION):
            raw = runtime_blob(root, path)
            ledger = json.loads(raw)
            if path != SIMULATION + ledger['date'].replace('-', '') + '.json':
                raise ValueError('SIMULATION_DATE_BINDING_MISMATCH')
            ledgers.append({'date': ledger['date'], 'sha256': sha256(raw).hexdigest(),
                            'signals': len(ledger['signals']), 'settled': len(ledger['settled'])})
            for row in ledger['signals']:
                plans[row['setup']].append(Plan(row['trigger'], row['stop'], row['target'], 'UNRESOLVED'))
            continue
        if not path.startswith(FUNNEL + 'daily/'):
            continue
        raw = runtime_blob(root, path)
        day = json.loads(raw)
        date_token = day['signal_date'].replace('-', '')
        binding = day['near_miss']
        near_path = FUNNEL + f'near_miss/{date_token}.json'
        if (path != FUNNEL + f'daily/{date_token}.json' or binding['path'] != near_path
                or near_path not in paths or day['outcome_accessed'] is not False
                or set(day['by_rule']) != set(RULES)):
            raise ValueError('FUNNEL_IDENTITY_MISMATCH')
        near_raw = runtime_blob(root, near_path)
        if len(near_raw) != binding['bytes'] or sha256(near_raw).hexdigest() != binding['sha256']:
            raise ValueError('NEAR_MISS_BYTE_BINDING_MISMATCH')
        near = json.loads(near_raw)
        if any(near[key] != day[key] for key in ('signal_date', 'package_sha256', 'c_observation_sha256')):
            raise ValueError('NEAR_MISS_SOURCE_BINDING_MISMATCH')
        used.add(near_path)
        if bins is not None and bins != day['histogram_bins']:
            raise ValueError('FUNNEL_HISTOGRAM_DRIFT')
        bins = day['histogram_bins']
        if day['complete_diagnostic_count'] != sum(row['complete_diagnostic_count'] for row in day['by_rule'].values()):
            raise ValueError('FUNNEL_COMPLETE_COUNT_MISMATCH')
        days.append({'date': day['signal_date'], 'sha256': sha256(raw).hexdigest(), 'near_miss': binding,
                     'complete': day['complete_diagnostic_count'], 'coverage': day['coverage_status']})
        for rule, source in day['by_rule'].items():
            sum_counts(totals[rule], {key: value for key, value in source.items()
                                      if key not in {'top_failure_reasons', 'funnel_count_semantics'}})
            sampled[rule].update({key: len(rows) for key, rows in near['by_rule'][rule].items()})
    complete = sum(day['complete'] for day in days)
    if used != {path for path in paths if path.startswith(FUNNEL + 'near_miss/')} or len(days) < 13 or complete < 79084:
        raise ValueError('FUNNEL_CHECKPOINT_INPUT_INCOMPLETE')
    for rule, value in totals.items():
        total = value['input_stock_count']
        value['near_miss_sample_counts'] = dict(sampled[rule])
        joint = value['slope_up_close_fraction_joint']
        joint['both_pass'] = total - sum(joint.values())
        value['condition_failure_rates_pct'] = {
            key: {'all': pct(count, total), 'known': pct(count, total - value['condition_missing_counts'][key])}
            for key, count in value['condition_failure_counts'].items()
        }
    return {'date_count': len(days), 'complete_count': complete, 'days': days, 'by_rule': totals,
            'status': 'COLLECTING_PRE_15D_CHECKPOINT_DIAGNOSTIC' if len(days) < 15 else 'DIAGNOSTIC_CHECKPOINT',
            'histogram_bins': bins, 'simulation_ledgers': ledgers,
            'simulation_rr': {rule: rr_audit(plans[rule]) for rule in RULES},
            'simulation_pressure_attribution': 'UNRESOLVED'}


def read_index(root: Path) -> tuple[list[str], np.ndarray, np.ndarray]:
    prices = {}
    for relative in INDEX:
        payload = json.loads(local_path(root, relative).read_bytes())
        if payload['code'] != 0:
            raise ValueError(f'INDEX_INPUT_ERROR: {relative}')
        for row in payload['data']['item']:
            ms, close = int(row['date_ms']), float(row['close_price'])
            if ms in prices or not math.isfinite(close) or close <= 0:
                raise ValueError(f'INVALID_INDEX_BAR: {relative}')
            prices[ms] = close
    ms = np.array(sorted(prices), dtype=np.int64)
    dates = [replay._date_from_ms(value) for value in ms]
    study = [d for d in dates if START <= d <= END]
    if len(study) != 769 or (study[0], study[-1]) != (START, END):
        raise ValueError('INDEX_SESSION_IDENTITY_MISMATCH')
    return dates, ms, np.array([prices[value] for value in ms])


def read_b(root: Path, study_dates: list[str]) -> dict:
    count, records = 0, set()
    with gzip.open(local_path(root, B_EVENTS), 'rt', encoding='utf-8') as file:
        for line in file:
            row = json.loads(line)
            count += 1
            symbol, day, setup = row['symbol'].lower(), row['signal_date'], row['setup_id']
            if symbol.startswith(('00', '60')):
                records.add((symbol, day, setup))
    dates = {day: index for index, day in enumerate(study_dates)}
    identities = {(symbol, dates[day]) for symbol, day, _ in records}
    if (count, len(records), len(identities), len({day for _, day in identities})) != (17714, 10779, 10779, 749):
        raise ValueError('FORMAL_B_IDENTITY_COUNT_MISMATCH')
    return {'identities': identities, 'all_count': count, 'main_count': len(identities),
            'date_count': 749, 'setup_counts': dict(Counter(setup for _, _, setup in records))}


def affine(dates: np.ndarray, events: list) -> tuple[np.ndarray, np.ndarray]:
    scale = np.ones(len(dates))
    offset = np.zeros(len(dates))
    slope, intercept, start = 1.0, 0.0, 0
    for day, dividend, bonus, allotment, price in events:
        if day <= dates[0]:
            continue
        if day > dates[-1]:
            break
        end = int(np.searchsorted(dates, day))
        scale[start:end], offset[start:end] = slope, intercept
        denominator = 1 + bonus + allotment
        if not math.isfinite(denominator) or denominator <= 0:
            raise ValueError('INVALID_CORPORATE_ACTION')
        slope /= denominator
        intercept = (intercept - dividend + price * allotment) / denominator
        start = end
    scale[start:], offset[start:] = slope, intercept
    return scale, offset


def verify_affine() -> dict:
    rng = np.random.default_rng(SEED)
    dates = np.arange(275, dtype=np.int64)
    worst = 0.0
    for _ in range(500):
        end = int(rng.integers(250, 275))
        actions = sorted([int(value) for value in rng.choice(np.arange(1, end), 8, replace=False)])
        actions.extend((end, end + 1))
        events = [(d, float(rng.uniform(.01, 1)), float(rng.uniform(.01, .3)),
                   float(rng.uniform(.01, .25)), float(rng.uniform(1, 15))) for d in actions]
        raw = rng.uniform(5, 160, size=(4, len(dates)))
        store = dict(zip(PRICE, raw), date_ms=dates, date_text={int(d): str(d) for d in dates}, volume=np.arange(len(dates)))
        scale, offset = affine(dates, events)
        reconstructed = scale[end] * ((raw[:, :end + 1] - offset[:end + 1]) / scale[:end + 1]) + offset[end]
        reference = replay._adjusted_bars(store, 0, end + 1, events, end)
        error = float(np.max(np.abs(reconstructed - [[row[field] for row in reference] for field in PRICE])))
        if error >= 1e-11 or any(row['volume'] != i for i, row in enumerate(reference)):
            raise ValueError('AFFINE_T_ANCHOR_PARITY_FAILED')
        worst = max(worst, error)
    return {'draws': 500, 'seed': SEED, 'max_abs_price_error': worst, 'raw_volume_verified': True}


@dataclass
class History:
    days: np.ndarray
    sessions: np.ndarray
    raw: np.ndarray
    volume: np.ndarray
    scale: np.ndarray
    offset: np.ndarray
    norm: np.ndarray

    def prices(self, anchor: int, selection):
        return self.scale[anchor] * self.norm[:, selection] + self.offset[anchor]

    def convert(self, values, source, anchor):
        if np.isscalar(source) and np.isscalar(anchor) and source == anchor:
            return values
        return self.scale[anchor] * ((values - self.offset[source]) / self.scale[source]) + self.offset[anchor]


class Pair(NamedTuple):
    left: int
    neck: int
    right: int


def find_pair(highs, lows, closes, t: int) -> Pair | None:
    # The earliest eligible L1 is T-55. Its radius needs two more prior bars.
    start = max(0, t - 57)
    pivots = [start + i for i in frozen_c._pivot_indices(lows[start:t], 2, low=True)]
    near_floor = min(lows[t-59:t+1]) * 1.05
    for right in reversed(pivots):
        if not 3 <= t - right <= 10 or min(lows[right+1:t+1]) < lows[right]:
            continue
        for left in reversed(pivots):
            if not 8 <= right - left <= 45 or lows[left] > near_floor:
                continue
            if not .005 <= (lows[right] - lows[left]) / lows[left] <= .12:
                continue
            neck = left + 1 + int(np.argmax(highs[left+1:right]))
            if (not .04 <= (highs[neck] - lows[left]) / lows[left] <= .25
                    or (highs[neck] - lows[right]) / highs[neck] < .03
                    or min(closes[left+1:t+1]) < lows[left]):
                continue
            return Pair(left, neck, right)
    return None


@dataclass(frozen=True)
class Plan:
    trigger: float
    stop: float
    target: float
    source: str

    @property
    def valid(self):
        return 0 < self.stop < self.trigger < self.target

    @property
    def risk(self):
        return (self.trigger - self.stop) / self.trigger

    @property
    def rr(self):
        return (self.target - self.trigger) / (self.trigger - self.stop)


def planned_target(trigger: float, stop: float, pressure: float) -> Plan:
    risk = trigger - stop
    if pressure - trigger >= 2 * risk:
        return Plan(trigger, stop, round(pressure, 2), 'PRESSURE')
    return Plan(trigger, stop, round(trigger + 2.5 * risk, 2), 'TREND_2_5R')


def corrected_target(plan: Plan) -> Plan:
    if 0 < plan.stop < plan.trigger and plan.rr < 2:
        return Plan(plan.trigger, plan.stop, round(plan.trigger + 2.5 * (plan.trigger - plan.stop), 2), 'RR_CORRECTED')
    return plan


def pct(numerator, denominator):
    return 100 * numerator / denominator if denominator else None


def rr_audit(plans: list[Plan]) -> dict:
    known = [plan for plan in plans if 0 < plan.stop < plan.trigger]
    return {'count': len(plans), 'positive_risk_count': len(known), 'invalid_order_count': sum(not p.valid for p in plans),
            'rr_below_2': sum(p.rr < 2 for p in known), 'rr_below_1': sum(p.rr < 1 for p in known),
            'rr_below_2_pct': pct(sum(p.rr < 2 for p in known), len(known)),
            'rr_below_1_pct': pct(sum(p.rr < 1 for p in known), len(known))}


@dataclass(frozen=True)
class Signal:
    code: str
    day: int
    bar: int
    position: float
    plan: Plan


def volume_bin(volume, right):
    before = float(np.median(volume[right-20:right]))
    if before <= 0:
        return 'UNAVAILABLE'
    ratio = (float(volume[right-1]) + float(volume[right])) / (2 * before)
    return ('<0.8', '[0.8,1.0)', '[1.0,1.2)', '>=1.2')[int(np.searchsorted([.8, 1, 1.2], ratio, side='right'))]


def new_plans(history: History, t: int) -> tuple[list[str], Plan | None, str | None]:
    adjusted = history.prices(t, slice(t-60, t+1))
    adjusted[:, -1] = history.raw[:, t]
    opening, highs, lows, closes = adjusted
    end = 60
    close, previous = float(history.raw[3, t]), closes[-2]
    width = highs[-1] - lows[-1]
    clv = (close - lows[-1]) / width if width else float(close > previous)
    ma20 = np.mean(closes[-20:])
    if (close <= ma20 or ma20 < .995 * np.mean(closes[-25:-5]) or close <= previous
            or close <= opening[-1] or clv < .60):
        return [], None, None
    pair = find_pair(highs, lows, closes, end)
    if pair is None or (close - lows[pair.right]) / lows[pair.right] > .15:
        return [], None, None
    variants = []
    if close > highs[pair.neck] >= previous:
        variants.append(C1)
    if close > max(closes[-6:-1]) and previous <= max(closes[-7:-2]):
        variants.append(C2)
        median = float(np.median(history.volume[t-20:t]))
        if median > 0 and history.volume[t] / median >= 1.8:
            variants.append(C3)
    if not variants:
        return [], None, None
    trigger, stop = round(close, 2), round(float(lows[pair.right]) * .98, 2)
    cents, risk_cents = round(trigger * 100), round((trigger - stop) * 100)
    if not 2 * cents <= 100 * risk_cents <= 10 * cents:
        return variants, None, None
    return variants, planned_target(trigger, stop, float(max(highs[:-1]))), volume_bin(history.volume, t-60+pair.right)


def possible_existing_structure(highs, lows, config) -> bool:
    """Necessary structure check within the oldest admissible peak plus its pivot radius."""
    end = len(lows) - 1
    radius = config.pivot_radius
    maximum_age = config.maximum_pullback_sessions + 2 * radius
    start = max(0, end - maximum_age - radius)
    lows, highs = lows[start:end], highs[start:end]
    peaks = frozen_c._pivot_indices(highs, radius, low=False)
    pivots = frozen_c._pivot_indices(lows, radius, low=True)
    for left in pivots:
        peak_position = bisect_left(peaks, left) - 1
        if peak_position < 0:
            continue
        peak = peaks[peak_position]
        depth = (highs[peak] - min(lows[peak+1:])) / highs[peak]
        if not config.shallow_depth_min <= depth <= config.shallow_depth_max:
            continue
        for right in pivots:
            if right - left < config.minimum_pivot_separation or lows[right] <= lows[left]:
                continue
            rebound = frozen_c._latest_rebound_high(highs, peaks, right, len(lows))
            if rebound is not None:
                size = (highs[rebound] - lows[right]) / lows[right]
                if config.rebound_size_min <= size <= config.rebound_size_max:
                    return True
    return False


def existing_match(history: History, t: int, rule: str, date_strings: dict) -> dict | None:
    start = max(0, t + 1 - 260)
    adjusted = history.prices(t, slice(start, t+1))
    adjusted[:, -1] = history.raw[:, t]
    config = frozen_c.RULE_CANDIDATES[rule]
    if (adjusted <= 0).any() or not possible_existing_structure(adjusted[1], adjusted[2], config):
        return None
    bars = [{'date': date_strings[int(history.days[i])], 'volume': float(history.volume[i]),
             **dict(zip(PRICE, (float(p) for p in row)))}
            for i, row in enumerate(adjusted.T, start)]
    if not frozen_c.trend_features(bars, config)['trend_qualified']:
        return None
    if not frozen_c._bar_geometry(bars[-1], bars[-2]['close'])['close_location'] >= config.confirmation_close_location:
        return None
    entry = frozen_c.build_entry_observation(bars, rule_id=rule)
    return entry['structure'] if entry['entry_candidate'] else None


def existing_plan(history: History, t: int, structure: dict) -> Plan:
    close = float(history.raw[3, t])
    window = history.prices(t, slice(t-4, t+1))[3]
    window[-1] = close
    trigger = round(max(structure['rebound_high'], fmean(window)), 2)
    stop = round(structure['support_floor'] * .98, 2)
    pressure = structure['stage_prior_high']
    if pressure > close * 1.03:
        return Plan(trigger, stop, pressure, 'PRESSURE')
    return Plan(trigger, stop, close + 2.5 * (close - stop), 'TREND_2_5R')


def market_gates(index_close, start: int, end: int) -> tuple[np.ndarray, np.ndarray]:
    average20 = sliding_window_view(index_close, 20).mean(axis=1)
    average5 = sliding_window_view(index_close, 5).mean(axis=1)
    idx = np.arange(start, end)
    g2 = (index_close[idx] > average20[idx-19]) & (average20[idx-19] > average20[idx-24])
    early = (index_close[idx] > average5[idx-4]) & (average5[idx-4] > average5[idx-7])
    return g2, early


def make_history(store, start, end, events, index_ms, study_start) -> History:
    dates = store['date_ms'][start:end]
    raw = np.array([store[name][start:end] for name in PRICE])
    volume = store['volume'][start:end]
    scale, offset = affine(dates, events)
    sessions = np.searchsorted(index_ms, dates) - study_start
    return History(dates, sessions, raw, volume, scale, offset, (raw - offset) / scale)


def verify_frozen_affine(store, histories, events) -> dict:
    pool = defaultdict(list)
    for code, history in histories.items():
        for event_day, dividend, bonus, allotment, _ in events.get(code, []):
            i = int(np.searchsorted(history.days, event_day))
            options = np.arange(max(i, 119), min(i + 100, len(history.days)))
            options = options[(options > 0) & (history.sessions[options] >= 0)]
            if i > 0 and len(options):
                for label, present in (('dividend', dividend != 0), ('bonus', bonus != 0), ('allotment', allotment != 0)):
                    if present:
                        pool[label].append((code, options))
    if not pool:
        raise ValueError('FROZEN_ACTION_SAMPLE_UNAVAILABLE')
    rng = np.random.default_rng(SEED)
    selected = set()
    labels = sorted(pool)
    for label in labels:
        group = pool[label]
        for _ in range(50):
            code, options = group[int(rng.integers(len(group)))]
            selected.add((code, int(rng.choice(options))))
    group = [entry for label in labels for entry in pool[label]]
    for _ in range(10000):
        if len(selected) == 500:
            break
        code, options = group[int(rng.integers(len(group)))]
        selected.add((code, int(rng.choice(options))))
    if len(selected) != 500:
        raise ValueError('FROZEN_ACTION_SAMPLE_INSUFFICIENT')
    worst = 0.0
    coverage = Counter()
    for code, t in sorted(selected):
        history = histories[code]
        start = max(0, t + 1 - 260)
        base = store['bounds'][code][0]
        actions = events[code]
        expected = replay._adjusted_bars(store, base+start, base+t+1, actions, history.days[t])
        actual = history.prices(t, slice(start, t+1))
        worst = max(worst, float(np.max(np.abs(actual - [[bar[name] for bar in expected] for name in PRICE]))))
        if not np.array_equal(history.volume[start:t+1], [bar['volume'] for bar in expected]):
            raise ValueError('FROZEN_AFFINE_RAW_VOLUME_MISMATCH')
        within = [event for event in actions if history.days[start] < event[0] <= history.days[t]]
        coverage.update(label for label, k in (('dividend', 1), ('bonus', 2), ('allotment', 3))
                        if any(event[k] != 0 for event in within))
    if worst >= 1e-11 or not all(coverage[label] for label in labels):
        raise ValueError('FROZEN_AFFINE_T_ANCHOR_PARITY_FAILED')
    return {'draws': 500, 'max_abs_price_error': worst, 'action_coverage': dict(coverage)}


def position_stats(values) -> dict:
    return {'match_count': len(values), 'bottom_count': sum(pos <= .40 for pos in values),
            'bottom_pct': pct(sum(pos <= .40 for pos in values), len(values)),
            'pos250_quantiles': dict(zip(('min', 'p10', 'p25', 'p50', 'p75', 'p90', 'max'),
                                         map(float, np.quantile(values, [0, .1, .25, .5, .75, .9, 1])))) if values else {}}


def c_prefilter(history: History, rows: np.ndarray, window: int, minimum_up: float) -> np.ndarray:
    # Necessary conditions only. Keep ties within arithmetic tolerance for the frozen evaluator.
    closes = sliding_window_view(history.norm[3], window)[rows - window + 1]
    fast = closes[:, -20:].mean(axis=1)
    slow = closes.mean(axis=1)
    closing = closes[:, -1]
    changes = np.diff(closes, axis=1)
    tolerance = 1e-11 / history.scale[rows]
    up_fraction = (changes >= -tolerance[:, None]).mean(axis=1)
    _, high, low, close = history.raw[:, rows]
    return ((closing > fast - tolerance) & (fast > slow - tolerance)
            & (closing > history.norm[0, rows] - tolerance) & (changes[:, -1] > -tolerance)
            & (close - low >= .60 * (high - low) - 1e-11)
            & (up_fraction >= minimum_up))


def scan_signals(histories, date_strings, study_length):
    signals = {variant: [] for variant in (*VARIANTS, C0_RR)}
    matches = {rule: [] for rule in RULES}
    legacy_plans = []
    raw_counts, risk_rejected = Counter(), Counter()
    volume_bins = {variant: Counter() for variant in (C1, C2, C3)}
    for code, history in histories.items():
        if len(history.days) < 250:
            continue
        rows = np.flatnonzero((history.sessions >= 0) & (history.sessions < study_length)
                              & (history.raw[3] > 2) & (np.arange(len(history.days)) >= 249))
        low = sliding_window_view(history.norm[2], 250).min(axis=1)[rows - 249]
        high = sliding_window_view(history.norm[1], 250).max(axis=1)[rows - 249]
        adj_low, adj_high = low * history.scale[rows] + history.offset[rows], high * history.scale[rows] + history.offset[rows]
        valid = (adj_low > 0) & (adj_high > adj_low)
        rows, adj_low, adj_high = rows[valid], adj_low[valid], adj_high[valid]
        close = history.raw[3, rows]
        previous20 = history.convert(history.raw[3, rows-20], rows-20, rows)
        position = (close - adj_low) / (adj_high - adj_low)
        for rule, config in frozen_c.RULE_CANDIDATES.items():
            eligible = c_prefilter(history, rows, config.trend_window, config.minimum_up_close_fraction)
            for t, pos in zip(rows[eligible], position[eligible]):
                t, pos = int(t), float(pos)
                structure = existing_match(history, t, rule, date_strings)
                if structure is None:
                    continue
                matches[rule].append(pos)
                if rule == 'BALANCED_A':
                    day = int(history.sessions[t])
                    plan = existing_plan(history, t, structure)
                    legacy_plans.append(plan)
                    fix = corrected_target(plan)
                    if plan.valid:
                        signals[C0].append(Signal(code, day, t, pos, plan))
                    if fix.valid:
                        signals[C0_RR].append(Signal(code, day, t, pos, fix))
        bottom = (position <= .40) & ((adj_high - adj_low) / adj_high >= .25) & (close / previous20 - 1 <= .20)
        for t, pos in zip(rows[bottom], position[bottom]):
            t = int(t)
            variants, plan, bin_label = new_plans(history, t)
            raw_counts.update(variants)
            if plan is None:
                risk_rejected.update(variants)
                continue
            signal = Signal(code, int(history.sessions[t]), t, float(pos), plan)
            for variant in variants:
                volume_bins[variant][bin_label] += 1
                signals[variant].append(signal)
    summary = {'pos250': {key: position_stats(values) for key, values in matches.items()},
               'legacy_rr': {source: rr_audit([p for p in legacy_plans if p.source == source])
                             for source in ('PRESSURE', 'TREND_2_5R')},
               'geometry_and_entry_pass': dict(raw_counts), 'risk_rejected': dict(risk_rejected),
               'valid_plans': {key: len(values) for key, values in signals.items()},
               'right_foot_volume_bins': {key: dict(value) for key, value in volume_bins.items()}}
    return signals, summary


class Trade(NamedTuple):
    status: str
    entry_day: int | None = None
    exit_day: int | None = None
    net: float | None = None


def limit_lock(opening, high, low, previous) -> int:
    if high != low:
        return 0
    if opening >= previous * 1.10 - .005000001:
        return 1
    return -1 if opening <= previous * .90 + .005000001 else 0


def settle(signal: Signal, history: History, last_day: int) -> Trade:
    stop, target = signal.plan.stop, signal.plan.target
    trigger = signal.plan.trigger
    anchor, fill, entry_day = signal.bar, None, None
    expiration = signal.day + EXPIRY
    for i in range(anchor + 1, len(history.days)):
        day = int(history.sessions[i])
        if day > last_day or (fill is None and day > expiration):
            break
        opening, high, low, _ = (float(x) for x in history.raw[:, i])
        previous = float(history.convert(history.raw[3, i-1], i-1, i))
        lock = limit_lock(opening, high, low, previous)
        if fill is None:
            adjusted_trigger = float(history.convert(trigger, anchor, i))
            if adjusted_trigger <= 0:
                raise ValueError('UNUSABLE_EXECUTION_TRIGGER')
            if lock != 1 and high >= adjusted_trigger:
                fill = max(opening, adjusted_trigger)
                entry_day, entry_index = day, i
            continue
        if lock == -1:
            continue
        adj_stop, adj_target = map(float, history.convert(np.array([stop, target]), anchor, i))
        if adj_stop <= 0:
            raise ValueError('UNUSABLE_EXECUTION_STOP')
        decision = _sellable_exit_decision({'stop': adj_stop, 'target': adj_target},
                                           {'open': opening, 'high': high, 'low': low})
        if decision is None:
            continue
        if decision['exit_reason'] == EXIT_REASON_AMBIGUOUS:
            return Trade('AMBIGUOUS_SAME_BAR', entry_day, day)
        adj_entry = float(history.convert(fill, entry_index, i))
        if adj_entry <= 0:
            raise ValueError('UNUSABLE_EXECUTION_ENTRY_REFERENCE')
        return Trade('CLOSED', entry_day, day, decision['exit_price'] / adj_entry - 1 - COST)
    if fill is not None:
        return Trade('OPEN', entry_day)
    if expiration <= last_day:
        return Trade('EXPIRED_UNTRIGGERED', exit_day=expiration)
    return Trade('PENDING_AT_CUTOFF')


def available(day: int, older: Signal, trade: Trade) -> bool:
    if day <= older.day + COOLDOWN or trade.exit_day is None or trade.exit_day > day:
        return False
    return trade.status == 'EXPIRED_UNTRIGGERED' or day > trade.exit_day + COOLDOWN


def accept(grouped: dict, results: dict, gate: str, mode: str, market: tuple) -> list[Signal]:
    g2, early = market
    accepted, previous = [], {}
    for day, signals in sorted(grouped.items()):
        if gate != 'G0' and not g2[day] and not (gate == 'G4' and early[day] and len(signals) >= 5):
            continue
        eligible = [s for s in signals if s.code not in previous or
                    available(day, previous[s.code], results[previous[s.code]])]
        if mode == 'TOP2':
            eligible = sorted(eligible, key=lambda s: (round(s.position, 10), round(s.plan.risk, 10), s.code))[:2]
        for s in eligible:
            previous[s.code] = s
        accepted.extend(eligible)
    return accepted


def fixed_window(signal: Signal, history: History, length: int) -> tuple[float, float, float] | None:
    window = slice(signal.bar + 1, signal.bar + length + 1)
    if not np.array_equal(history.sessions[window], np.arange(signal.day+1, signal.day+length+1)):
        return None
    entry_index = signal.bar + 1
    indices = np.arange(entry_index, entry_index + length)
    entries = history.convert(history.raw[0, entry_index], entry_index, indices)
    if (entries <= 0).any():
        return None
    return (float(history.raw[3, indices[-1]] / entries[-1] - 1),
            float(np.max(history.raw[1, window] / entries) - 1),
            float(np.min(history.raw[2, window] / entries) - 1))


def scan_waves(histories: dict, study_length: int) -> tuple[list, int]:
    complete, all_count = [], 0
    for code, history in histories.items():
        previous_day = -30
        rows = np.flatnonzero((history.sessions >= 0) & (history.sessions + 20 < study_length)
                              & (history.raw[3] > 2) & (np.arange(len(history.days)) >= 119))
        previous = history.convert(history.raw[3, rows-1], rows-1, rows)
        if len(history.volume) < 20:
            continue
        average = sliding_window_view(history.volume, 20).mean(axis=1)[rows-20]
        for t in rows[(previous > 0) & (history.raw[3, rows] >= 1.03 * previous)
                      & (average > 0) & (history.volume[rows] >= 1.8 * average)]:
            day = int(history.sessions[t])
            if day < previous_day + 30:
                continue
            window = history.prices(t, slice(max(0, t-249), t+1))
            low, high = float(window[2].min()), float(window[1].max())
            close = float(history.raw[3, t])
            if not 0 < low < high or (close - low) / (high - low) > .40:
                continue
            end = int(np.searchsorted(history.sessions, day+20, side='right'))
            forward = np.arange(t+1, end)
            reference = history.convert(close, t, forward)
            if len(forward) == 0 or (reference <= 0).any() or np.max(history.raw[1, forward] / reference) < 1.30:
                continue
            previous_day = day
            all_count += 1
            if day >= 5 and day + 40 < study_length:
                complete.append((code, day, int(t)))
    return complete, all_count


def coverage_sets(waves, identities, histories) -> tuple[set, set]:
    early, late = set(), set()
    dates = defaultdict(list)
    for code, day in sorted(identities):
        dates[code].append(day)
    for code, day, t in waves:
        days = dates[code]
        start, end = np.searchsorted(days, [day-5, day+41])
        history = histories[code]
        for candidate in days[start:end]:
            if candidate > day + 10:
                late.add((code, day))
                break
            j = int(np.searchsorted(history.sessions, candidate))
            if j == len(history.sessions) or history.sessions[j] != candidate:
                raise ValueError('SIGNAL_DAY_ABSENT_FROM_STOCK_HISTORY')
            anchor = max(t, j)
            close = history.convert(history.raw[3, j], j, anchor)
            base = history.convert(history.raw[3, t], t, anchor)
            if base > 0 and close <= base * 1.15:
                early.add((code, day))
                late.discard((code, day))
                break
            late.add((code, day))
    return early, late


def coverage_metrics(wave_count: int, early, blind, b_identities, identities) -> dict:
    overlap = len(identities & b_identities)
    recovered = len(early & blind)
    return {'unique_signals': len(identities), 'early_catch_count': len(early),
            'early_catch_pct': pct(len(early), wave_count), 'b_blindspot_early_recovery_count': recovered,
            'b_blindspot_early_recovery_pct': pct(recovered, len(blind)), 'formal_b_overlap_count': overlap,
            'formal_b_overlap_pct': pct(overlap, len(identities))}


class Bootstrap:
    def __init__(self, days: int):
        rng = np.random.default_rng(SEED)
        blocks = math.ceil(days / BLOCK)
        self.starts = rng.integers(0, days - BLOCK + 1, size=(DRAWS, blocks))
        self.lengths = np.minimum(BLOCK, days - np.arange(blocks) * BLOCK)
        self.days = days

    def summarize(self, observations: list) -> dict:
        days = defaultdict(list)
        for day, value in observations:
            days[day].append(value)
        if not days:
            return {'observed_days': 0, 'mean_pct': None, 'ci95_pct': [None, None], 'valid_draws': 0}
        daily = np.zeros(self.days)
        observed = np.zeros(self.days, dtype=np.int64)
        for day, values in days.items():
            daily[day] = fmean(values)
            observed[day] = 1
        ends = self.starts + self.lengths
        sums = np.r_[0, daily.cumsum()]
        counts = np.r_[0, observed.cumsum()]
        sampled_sums = (sums[ends] - sums[self.starts]).sum(axis=1)
        sampled_counts = (counts[ends] - counts[self.starts]).sum(axis=1)
        valid = sampled_counts > 0
        sampled = 100 * sampled_sums[valid] / sampled_counts[valid]
        return {'observed_days': len(days), 'mean_pct': float(100 * daily.sum() / len(days)),
                'ci95_pct': list(map(float, np.quantile(sampled, [.025, .975]))) if len(sampled) else [None, None],
                'valid_draws': len(sampled)}


def net_metrics(values) -> dict:
    profit = math.fsum(ret for ret in values if ret > 0)
    loss = -math.fsum(ret for ret in values if ret < 0)
    return {'closed': len(values), 'net_avg_return_pct': 100 * fmean(values) if values else None,
            'net_win_rate_pct': pct(sum(ret > 0 for ret in values), len(values)),
            'net_profit_factor': profit / loss if loss > 0 else None,
            'net_profit_factor_status': 'POSITIVE_INFINITY' if profit > 0 and loss == 0 else
            'AVAILABLE' if loss > 0 else 'UNAVAILABLE', 'net_sum_pp': 100 * math.fsum(values)}


def model_metrics(accepted, results, study_dates, bootstrap) -> dict:
    trades = Counter(results[s].status for s in accepted)
    triggered = trades['CLOSED'] + trades['AMBIGUOUS_SAME_BAR'] + trades['OPEN']
    closed = [(s.day, results[s].net) for s in accepted if results[s].status == 'CLOSED']
    by_year = {year: net_metrics([value for day, value in closed if study_dates[day].startswith(year)])
               for year in ('2023', '2024', '2025', '2026')}
    windows = {}
    for first, last in WINDOWS:
        values = [value for day, value in closed if first <= study_dates[day] <= last]
        windows[f'{first}..{last}'] = {'accepted': sum(first <= study_dates[s.day] <= last for s in accepted),
                                      'closed': len(values), 'net_sum_pp': 100 * math.fsum(values)}
    return {'accepted': len(accepted), 'status_counts': dict(trades), 'triggered': triggered,
            'ambiguous_triggered_pct': pct(trades['AMBIGUOUS_SAME_BAR'], triggered),
            **net_metrics([value for _, value in closed]), 'by_signal_year': by_year, 'windows': windows,
            'daily_net_bootstrap': bootstrap.summarize(closed)}


def fixed_metrics(accepted, windows, horizon, bootstrap) -> dict:
    rows = [(signal.day, windows[signal, horizon]) for signal in accepted if windows[signal, horizon] is not None]
    values = np.array([metrics for _, metrics in rows]).reshape(-1, 3)
    result = {'available': len(rows), 'unavailable': len(accepted) - len(rows)}
    for label, cost in (('gross', 0), ('net', COST)):
        result[label] = {
            'avg_return_pct': float(100 * values[:, 0].mean() - 100 * cost) if len(rows) else None,
            'median_return_pct': float(100 * np.median(values[:, 0]) - 100 * cost) if len(rows) else None,
            'win_rate_pct': pct(int((values[:, 0] > cost).sum()), len(rows)),
            'mfe_mean_pct': float(100 * values[:, 1].mean() - 100 * cost) if len(rows) else None,
            'mae_mean_pct': float(100 * values[:, 2].mean() - 100 * cost) if len(rows) else None,
        }
    result['daily_net_bootstrap'] = bootstrap.summarize([(day, metrics[0] - COST) for day, metrics in rows])
    return result


def one_sided_p(candidate: set, reference: set) -> float:
    improved, worsened = len(candidate - reference), len(reference - candidate)
    n = improved + worsened
    return sum(math.comb(n, k) for k in range(improved, n + 1)) / (1 << n)


def greater(value, baseline, floor=0) -> bool:
    return value is not None and baseline is not None and value >= floor and value > baseline


def profit_factor(metric):
    return math.inf if metric['net_profit_factor_status'] == 'POSITIVE_INFINITY' else metric['net_profit_factor']


def decide(matrix, recovered, blind_verified) -> dict:
    candidates = []
    for gate in MARKET_GATES:
        for variant in (C1, C2, C3):
            for mode in ('TOP2', 'S_ALL'):
                baseline = matrix[C0, gate, mode]
                row = matrix[variant, gate, mode]
                base_recovery = matrix[variant, gate, 'S_ALL']['coverage']['b_blindspot_early_recovery_pct']
                p_value = one_sided_p(recovered[variant, gate, mode], recovered[C0, gate, mode]) if mode == 'TOP2' else None
                overlap = row['coverage']['formal_b_overlap_pct']
                ambiguity = row['ambiguous_triggered_pct']
                comparable_years = [year for year, value in row['by_signal_year'].items()
                                    if value['net_avg_return_pct'] is not None and value['net_avg_return_pct'] > 0
                                    and greater(value['net_avg_return_pct'], baseline['by_signal_year'][year]['net_avg_return_pct'])]
                weak = math.fsum(row['by_signal_year'][year]['net_sum_pp'] for year in ('2023', '2026'))
                daily = row['daily_net_bootstrap']
                daily_positive = daily['mean_pct'] is not None and daily['mean_pct'] > 0
                lower, upper = daily['ci95_pct']
                checks = [row['closed'] >= 250 and ambiguity is not None and ambiguity <= 5 and overlap is not None and overlap < 15,
                          blind_verified and base_recovery is not None and base_recovery >= 15 and (p_value is None or p_value < .05),
                          greater(row['net_avg_return_pct'], baseline['net_avg_return_pct'], 1)
                          and greater(profit_factor(row), profit_factor(baseline), 1.35)
                          and greater(row['net_win_rate_pct'], baseline['net_win_rate_pct'], 40),
                          len(comparable_years) >= 3 and weak >= -150,
                          daily_positive and lower is not None and lower > 0]
                row['decision_checks'] = {'pass': checks, 'top2_recovery_p_one_sided': p_value,
                                          'positive_years_above_c0': comparable_years, 'weak_year_sum_pp': weak}
                candidates.append(((variant, gate, mode), row, daily_positive and lower is not None and lower <= 0 <= upper))
    adopted = [key for key, row, _ in candidates if all(row['decision_checks']['pass'])]
    if adopted:
        return {'decision': 'ADOPT', 'reason': 'RECOMMEND_C_V2_PROSPECTIVE_SHADOW_PROPOSAL', 'primary': adopted[0]}
    if any(all(row['decision_checks']['pass'][:4]) and cross for _, row, cross in candidates):
        return {'decision': 'NEEDS_MORE_EVIDENCE', 'reason': 'DAILY_BLOCK_CI_INCLUDES_ZERO', 'primary': None}
    means = [row['net_avg_return_pct'] for _, row, _ in candidates]
    recoveries = [row['coverage']['b_blindspot_early_recovery_pct'] for _, row, _ in candidates]
    if all(value is not None and value <= 0 for value in means):
        return {'decision': 'REJECT', 'reason': 'ALL_CANDIDATE_NET_MEANS_NON_POSITIVE', 'primary': None}
    if not blind_verified:
        return {'decision': 'NEEDS_MORE_EVIDENCE', 'reason': 'B_BLINDSPOT_DENOMINATOR_NOT_REPRODUCED', 'primary': None}
    if all(value is not None and value < 5 for value in recoveries):
        return {'decision': 'REJECT', 'reason': 'ALL_B_BLINDSPOT_RECOVERY_BELOW_5_PCT', 'primary': None}
    covering = [row for _, row, _ in candidates if row['decision_checks']['pass'][1]]
    if covering and all(not row['decision_checks']['pass'][2] for row in covering):
        return {'decision': 'REJECT', 'reason': 'COVERAGE_WITH_INSUFFICIENT_NET_EXPECTANCY', 'primary': None}
    return {'decision': 'DEFER', 'reason': 'NO_PREREGISTERED_COMBINATION_PASSED', 'primary': None}


def evaluate(root: Path) -> dict:
    protocol_hash = verify_protocol(root)
    frozen = verify_inputs(root)
    runtime = audit_runtime(root)
    index_dates, index_ms, index_close = read_index(root)
    start, end = index_dates.index(START), index_dates.index(END) + 1
    study_dates = index_dates[start:end]
    b = read_b(root, study_dates)
    b_identities = b.pop('identities')
    synthetic_affine = verify_affine()
    store, _ = replay._load_stock_store(local_path(root, DAILY))
    events, _ = replay._load_events(local_path(root, FACTORS))
    histories = {}
    for code, (left, right) in store['bounds'].items():
        if code.startswith(('00', '60')):
            right = left + int(np.searchsorted(store['date_ms'][left:right], index_ms[end-1], side='right'))
            if right > left:
                histories[code] = make_history(store, left, right, events.get(code, []), index_ms, start)
    if len(histories) != 3193:
        raise ValueError(f'MAIN_BOARD_UNIVERSE_COUNT_MISMATCH: {len(histories)}')
    frozen_affine = verify_frozen_affine(store, histories, events)
    print('Verified local freeze, runtime bindings and 500 frozen affine comparisons.', flush=True)
    signals, signal_summary = scan_signals(histories, store['date_text'], len(study_dates))
    print('Completed causal signal scans.', flush=True)
    waves, all_waves = scan_waves(histories, len(study_dates))
    b_early, b_late = coverage_sets(waves, b_identities, histories)
    wave_ids = {(code, day) for code, day, _ in waves}
    blind = wave_ids - b_early
    blind_verified = (len(waves), len(blind)) == (2137, 2080)
    wave_summary = {'status': 'VERIFIED' if blind_verified else 'NOT_REPRODUCIBLE_WITH_CURRENT_DATA',
                    'total_waves': all_waves, 'complete_windows': len(waves), 'expected_complete_windows': 2137,
                    'formal_b_early': len(b_early), 'formal_b_late': len(b_late), 'formal_b_missed': len(blind-b_late),
                    'formal_b_blindspot': len(blind), 'expected_formal_b_blindspot': 2080}
    market = market_gates(index_close, start, end)
    bootstrap = Bootstrap(len(study_dates))
    matrix, recovered, raw_coverage = {}, {}, {}
    all_signals = set().union(*signals.values())
    results = {s: settle(s, histories[s.code], len(study_dates) - 1) for s in all_signals}
    fixed = {(s, horizon): fixed_window(s, histories[s.code], horizon) for s in all_signals for horizon in (5, 10)}
    for variant, variant_signals in signals.items():
        grouped = defaultdict(list)
        for signal in variant_signals:
            grouped[signal.day].append(signal)
        identities = {(s.code, s.day) for s in variant_signals}
        if len(identities) != len(variant_signals):
            raise ValueError(f'DUPLICATE_SIGNAL_IDENTITY: {variant}')
        early, _ = coverage_sets(waves, identities, histories)
        raw_coverage[variant] = coverage_metrics(len(waves), early, blind, b_identities, identities)
        for gate in MARKET_GATES:
            for mode in MODES:
                accepted = accept(grouped, results, gate, mode, market)
                accepted_ids = {(s.code, s.day) for s in accepted}
                early, _ = coverage_sets(waves, accepted_ids, histories)
                key = variant, gate, mode
                recovered[key] = early & blind
                matrix[key] = {'variant': variant, 'gate': gate, 'mode': mode,
                               **model_metrics(accepted, results, study_dates, bootstrap),
                               'coverage': coverage_metrics(len(waves), early, blind, b_identities, accepted_ids),
                               'fixed_windows': {f'T+{h}': fixed_metrics(accepted, fixed, h, bootstrap) for h in (5, 10)}}
    decision = decide(matrix, recovered, blind_verified)
    return {'study': 'C_FUNNEL_AND_BOTTOM_HIGHER_LOW_EARLY_START_V1', 'classification': 'RESEARCH_QUESTION_STRICT_PATH',
            'protocol_commit': PROTOCOL_COMMIT, 'protocol_lf_sha256': protocol_hash, 'runtime_commit': RUNTIME_COMMIT,
            'sample': ['DEVELOPMENT', 'MAIN_BOARD_ST_UNVERIFIED_DEVELOPMENT_SAMPLE', 'NO_VINTAGE_PROOF'],
            'study_first': START, 'study_last': END, 'study_sessions': len(study_dates), 'main_board_symbols': len(histories),
            'inputs': frozen, 'affine': {'synthetic': synthetic_affine, 'frozen': frozen_affine}, 'runtime': runtime,
            'legacy_diagnosis': 'C_SCARCITY_AND_BOTTOM_BLINDSPOT_CAUSE', 'signal_diagnostics': signal_summary,
            'formal_b_reference': b, 'wave_audit': wave_summary, 'qualification_coverage': raw_coverage,
            'bootstrap': {'block_sessions': BLOCK, 'draws': DRAWS, 'seed': SEED},
            'matrix': list(matrix.values()), **decision}


def number(value, digits=2) -> str:
    return '—' if value is None else f'{value:.{digits}f}'


def interval(metric) -> str:
    return ' ~ '.join(map(number, metric['ci95_pct']))


def table(headers, rows) -> str:
    def line(cells):
        return '| ' + ' | '.join(str(cell).replace('|', r'\|') for cell in cells) + ' |'
    return '\n'.join([line(headers), line(['---'] * len(headers)), *(line(row) for row in rows)])


def variant_label(variant):
    return 'C0-RR' if variant == C0_RR else variant.split('_', 1)[0]


def report(summary: dict) -> str:
    runtime, scan, wave = (summary[key] for key in ('runtime', 'signal_diagnostics', 'wave_audit'))
    rules = runtime['by_rule']
    rows = summary['matrix']
    reasons = {
        'RECOMMEND_C_V2_PROSPECTIVE_SHADOW_PROPOSAL': '全部五道门槛通过。提交独立前瞻观察提案供审批。',
        'DAILY_BLOCK_CI_INCLUDES_ZERO': '有组合通过门槛 1–4 且日均净收益为正，但区间包含零。需要更长的独立时间序列。',
        'ALL_CANDIDATE_NET_MEANS_NON_POSITIVE': '18 个候选组合扣费后的结案均值全部非正。',
        'B_BLINDSPOT_DENOMINATOR_NOT_REPRODUCED': '锁定扫描未复现既有 B 盲区分母。门槛 2 需要既有波段身份、去重时钟与 B 捕获分类记录，才能逐轮对账。',
        'ALL_B_BLINDSPOT_RECOVERY_BELOW_5_PCT': '18 个候选组合对已核验 B 盲区的早捕恢复率均低于 5%。',
        'COVERAGE_WITH_INSUFFICIENT_NET_EXPECTANCY': '达到覆盖门槛的组合未达到净期望要求，早捕收益不足以抵消假底交易的损耗。',
        'NO_PREREGISTERED_COMBINATION_PASSED': '没有组合同时满足五道门槛。',
    }
    decision = summary['decision']
    lead = reasons[summary['reason']]
    if summary['primary']:
        lead += ' 主推荐为 `' + ' / '.join(summary['primary']) + '`。'
    else:
        lead += ' 现有 B 日报与 C 前瞻漏斗照常运行。'
    sections = ['# C 真实漏斗诊断与底部双底抬高早启动',
                f'**研究决定 `{decision}`。** {lead}',
                f'研究采用 STRICT PATH，归类为非阻塞 `research question`。样本为 {summary["main_board_symbols"]:,} 只沪深主板股票，'
                f'{START} 至 {END} 共 {summary["study_sessions"]} 个交易日。'
                '样本标记 `MAIN_BOARD_ST_UNVERIFIED_DEVELOPMENT_SAMPLE`、`NO_VINTAGE_PROOF`。'
                f'预注册提交为 `{PROTOCOL_COMMIT}`，前瞻证据固定于 runtime-state `{RUNTIME_COMMIT}`。',
                '## A. 真实 C 漏斗与原规则位置',
                f'`{summary["legacy_diagnosis"]}`。前瞻漏斗有 {runtime["date_count"]} 日、{runtime["complete_count"]:,} 条完整双规则观测。'
                f'13 份 near-miss 均通过路径、字节数和 SHA-256 绑定。采集状态 `{runtime["status"]}`。']
    flow = []
    for rule, rule_data in rules.items():
        for stage in (f'F{i}' for i in range(9)):
            passed = rule_data['funnel_counts'][stage]
            lost = rule_data['sequential_attrition_counts'][stage]
            missing = rule_data['sequential_unavailable_counts'][stage]
            flow.append((rule, stage, f'{passed:,}', f'{lost:,}', f'{missing:,}', number(pct(lost, passed+lost+missing))))
    sections.append(table(('规则', '阶段', '存活', '淘汰', '缺失', '本门淘汰 %'), flow))
    for rule, d in rules.items():
        f = d['funnel_counts']
        rates = d['condition_failure_rates_pct']
        config = frozen_c.RULE_CANDIDATES[rule]
        sections.append(f'**{rule}** 在 F2 由 {f["F1"]:,} 条降至 {f["F2"]:,} 条，'
                        f'上涨收盘占比和均线顺序的全样本独立失败率分别为 {number(rates["up_close_fraction_ok"]["all"])}% 和 '
                        f'{number(rates["ma_order_ok"]["all"])}%。含 {config.shallow_depth_max:.0%} 深度上限及峰龄的 F4 '
                        f'将 {f["F3"]:,} 条降至 {f["F4"]:,} 条，随后要求 L2 之后确认 R 且反弹幅度合规的 F5 留下 {f["F5"]:,} 条。')
    sections.append(table(('规则', '独立子条件', '失败', '缺失', '占全部 %', '占已知 %'),
                          ((rule, condition, f'{count:,}', f'{d["condition_missing_counts"][condition]:,}',
                            number(d['condition_failure_rates_pct'][condition]['all']), number(d['condition_failure_rates_pct'][condition]['known']))
                           for rule, d in rules.items() for condition, count in sorted(d['condition_failure_counts'].items()))))
    diagnostics = (
        ('slope_up_close_fraction_joint', '斜率和涨收比例联合'), ('exact_structure_status_counts', '原规则结构状态'),
        ('all_pair_contexts_failed_counts', '全部尝试配对均失败的股票日'), ('peak_age_depth_pair_counts', '峰龄与深度配对'),
        ('rebound_high_size_pair_counts', '反弹高点与幅度配对'), ('near_miss_counts', 'near-miss 全量分类'),
        ('near_miss_sample_counts', '已抽样 near-miss 分类'),
    )
    sections.append(table(('指标', '分类', *RULES),
                          ((label, key, *(f'{rules[rule][field].get(key, 0):,}' for rule in RULES))
                           for field, label in diagnostics for key in sorted(set().union(*(rules[rule][field] for rule in RULES))))))
    for field, label in (('stock_histograms', '股票日直方图'), ('tried_pair_histograms', '全部配对直方图'),
                         ('selected_structure_histograms', '选中配对直方图')):
        sections.append(f'### {label}')
        sections.append(table(('指标', '冻结分箱', *RULES),
                              ((name, bin_label, *(f'{rules[rule][field][name].get(bin_label, 0):,}' for rule in RULES))
                               for name in sorted(rules[RULES[0]][field])
                               for bin_label in [*(limit[0] for limit in runtime['histogram_bins'][name]), 'UNAVAILABLE'])))
    positions = scan['pos250']
    sections.extend(['### 冻结开发样本的一年位置',
                     table(('规则', '价格结构命中', '底部条数', '底部 %', 'P10', 'P25', '中位数', 'P75', 'P90'),
                           ((rule, d['match_count'], d['bottom_count'], number(d['bottom_pct']),
                             *(number(d['pos250_quantiles'].get(k), 3) for k in ('p10', 'p25', 'p50', 'p75', 'p90')))
                            for rule, d in positions.items()))])
    for rule, d in positions.items():
        sections.append(f'{rule} 的一年底部命中占比为 {number(d["bottom_pct"])}%，位置中位数为 '
                        f'{number(d["pos250_quantiles"].get("p50"), 3)}。')
    rr = [(f'前瞻模拟 {rule}', value) for rule, value in runtime['simulation_rr'].items()]
    rr.extend((f'冻结 C0 {source}', value) for source, value in scan['legacy_rr'].items())
    sections.extend(['### 原目标价 RR 倒挂',
                     table(('来源', '计划', '正风险', '无效顺序', '<2R', '<2R %', '<1R', '<1R %'),
                           ((source, d['count'], d['positive_risk_count'], d['invalid_order_count'], d['rr_below_2'], number(d['rr_below_2_pct']),
                             d['rr_below_1'], number(d['rr_below_1_pct'])) for source, d in rr)),
                     '前瞻账本只保留静态计划价位，压力目标来源为 `UNRESOLVED`。冻结重放可以直接识别 '
                     '`pressure > close × 1.03` 分支，3% 的收盘价距离与以触发止损价差计算的 RR 是两项不同约束。',
                     '## B. 四个锁定变体与计划',
                     table(('变体', '入场形态与转强通过', '风险幅度剔除', '有效计划'),
                           ((variant, scan['geometry_and_entry_pass'].get(variant, scan['pos250']['BALANCED_A']['match_count']),
                             scan['risk_rejected'].get(variant, '—'), scan['valid_plans'][variant]) for variant in VARIANTS)),
                     table(('变体', '右脚量比箱', '计划数'),
                           ((variant_label(variant), label, count) for variant, bins in scan['right_foot_volume_bins'].items()
                            for label, count in sorted(bins.items()))),
                     '## C. MODEL_S 交易与 B 互补性',
                     '净收益扣除双边合计 20 bps。日均和区间采用信号日等权、20 个交易日移动块、5,000 次抽样。'
                     '累计净损益为结案逐笔收益的百分点之和。C0-RR 行仅替换 C0 的目标价。'])
    sections.append(table(('变体', '门', '接纳模式', '接纳', '触发', '结案', '模糊 %', '净均 %', '净 PF', '净胜率 %',
                           '累计 pp', '日净均 %', '95% CI', '通过门槛'),
                          ((variant_label(r['variant']), r['gate'], r['mode'], r['accepted'], r['triggered'], r['closed'],
                            number(r['ambiguous_triggered_pct']), number(r['net_avg_return_pct']), number(profit_factor(r)),
                            number(r['net_win_rate_pct']), number(r['net_sum_pp']), number(r['daily_net_bootstrap']['mean_pct']),
                            interval(r['daily_net_bootstrap']), ''.join(str(i) for i, passed in enumerate(r['decision_checks']['pass'], 1) if passed) or '—'
                            if 'decision_checks' in r else '—') for r in rows)))
    sections.append(table(('变体', '门', '模式', '2023 净均 %', '2024 净均 %', '2025 净均 %', '2026 净均 %', '23+26 净 pp'),
                          ((variant_label(r['variant']), r['gate'], r['mode'],
                            *(number(year['net_avg_return_pct']) for year in r['by_signal_year'].values()),
                            number(sum(r['by_signal_year'][year]['net_sum_pp'] for year in ('2023', '2026')))) for r in rows)))
    sections.extend(['### 底部主升浪及 Formal B 盲区',
                     f'锁定波段扫描找到 {wave["total_waves"]:,} 轮，其中完整观察窗 {wave["complete_windows"]:,} 轮'
                     f'（既有基准 2,137，差额 {wave["complete_windows"]-2137:+,}）。正式 B 主板资格身份为 10,779 条、749 个信号日。'
                     f'按锁定分类，B 早捕 {wave["formal_b_early"]:,} 轮、晚捕 {wave["formal_b_late"]:,} 轮、漏捕 {wave["formal_b_missed"]:,} 轮，'
                     f'晚捕加漏捕 {wave["formal_b_blindspot"]:,} 轮（既有基准 2,080，差额 {wave["formal_b_blindspot"]-2080:+,}）。'
                     f'复核状态 `{wave["status"]}`。'])
    if wave['status'] != 'VERIFIED':
        sections.append('下表覆盖与恢复率使用本次锁定扫描的波段分母，门槛 2 保留未核验。')
    coverage = [(variant_label(variant), 'G0', '规则资格', d) for variant, d in summary['qualification_coverage'].items()]
    coverage.extend((variant_label(r['variant']), r['gate'], r['mode'], r['coverage']) for r in rows)
    sections.append(table(('变体', '门', '口径', '及时早捕', '及时早捕 %', '恢复 B 盲区', '恢复 %', '重叠', '重叠 %'),
                          ((variant, gate, mode, d['early_catch_count'], number(d['early_catch_pct']),
                            d['b_blindspot_early_recovery_count'], number(d['b_blindspot_early_recovery_pct']),
                            d['formal_b_overlap_count'], number(d['formal_b_overlap_pct'])) for variant, gate, mode, d in coverage)))
    sections.extend(['### 2024 年两段底部转强',
                     table(('变体', '门', '模式', '春季接纳', '春季结案', '春季净 pp', '9·24 接纳', '9·24 结案', '9·24 净 pp'),
                           ((variant_label(r['variant']), r['gate'], r['mode'],
                             *(value for d in r['windows'].values() for value in (d['accepted'], d['closed'], number(d['net_sum_pp'])))) for r in rows)),
                     '### 固定窗口',
                     '表中均值、中位数、胜率、MFE 和 MAE 均为百分比，各栏依次给出扣费前和扣费后。'
                     '日净均区间按完整行情的固定窗收益计算。'])
    fixed_keys = ('avg_return_pct', 'median_return_pct', 'win_rate_pct', 'mfe_mean_pct', 'mae_mean_pct')
    sections.append(table(('变体', '门', '模式', '窗口', '可用', '均值', '中位数', '胜率', 'MFE', 'MAE', '日净均', '95% CI'),
                          ((variant_label(r['variant']), r['gate'], r['mode'], horizon, d['available'],
                            *(f'{number(d["gross"][k])} / {number(d["net"][k])}' for k in fixed_keys),
                            number(d['daily_net_bootstrap']['mean_pct']), interval(d['daily_net_bootstrap']))
                           for r in rows for horizon, d in r['fixed_windows'].items())))
    sections.extend(['## D. 判定与复现', f'`{decision}` · `{summary["reason"]}`。{lead}',
                     f'仿射逐价校验的 500 个冻结样本最大绝对误差为 '
                     f'{summary["affine"]["frozen"]["max_abs_price_error"]:.3g}，另有 500 个含现金分红、送转和配股的合成样本。'
                     '完整逐日输入绑定、分箱、门槛、口径和汇总见同批次 `summary.json`。'])
    return '\n\n'.join(sections) + '\n'


def main() -> None:
    summary = evaluate(ROOT)
    data = (json.dumps(summary, ensure_ascii=False, allow_nan=False, sort_keys=True, indent=2) + '\n').encode('utf-8')
    markdown = report(summary).encode('utf-8')
    output = local_path(ROOT, OUTPUT)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(data)
    local_path(ROOT, REPORT).write_bytes(markdown)
    print(f'{summary["decision"]} {summary["reason"]}\nsummary SHA-256 {sha256(data).hexdigest()}', flush=True)


if __name__ == '__main__':
    main()
