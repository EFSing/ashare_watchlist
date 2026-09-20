#!/usr/bin/env python3.11
"""Create a retrospective, targeted volume-observation addendum.

This module is deliberately narrower than both daily production and the
prospective shadow monitor.  It accepts only the already-persisted
2026-09-18 Formal B watchlist, keeps its candidate order, and reads either a
validated ten-symbol K-line cache or the ten symbols' historical K-lines from
HiThink.  It never constructs a universe, reads snapshots, evaluates Formal B,
or writes shadow/runtime state.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import html
import json
import math
from pathlib import Path
import subprocess
from typing import Any, Callable, Mapping, Sequence

from b_shadow_monitor import (
    _VOLUME_OBSERVATION_FIELDS,
    VOLUME_OBSERVATION_PROTOCOL_COMMIT_SHA,
    VOLUME_OBSERVATION_VERSION,
    _stock_snapshot,
)
from generation_contract import PROVIDER_QFQ_SNAPSHOT
from live_acquisition import (
    DEFAULT_STOCK_BAR_COUNT,
    HITHINK_API_VERSION,
    HITHINK_BASE_URL,
    HITHINK_STOCK_KLINE_API,
    HiThinkClient,
    _canonical_date,
    _hithink_thscode,
    _historical_window,
    _resolve_market_bars,
    _validate_historical_bars,
)


_BJT = timezone(timedelta(hours=8))
TARGET_DATE = "2026-09-18"
RETROSPECTIVE_VOLUME_ENRICHMENT = "RETROSPECTIVE_VOLUME_ENRICHMENT"
REPORT_SCHEMA_VERSION = "RETROSPECTIVE_VOLUME_ADDENDUM_V1"
INPUT_CACHE_SCHEMA_VERSION = "RETROSPECTIVE_VOLUME_INPUT_V1"
EXPECTED_STRATEGY = "B_BREAKOUT_RETEST_LEGACY_V1_1"
EXPECTED_WATCHLIST_MODE = "close"
EXPECTED_PROVIDER = "HiThink Financial-API"
EXPECTED_ADJUSTMENT = "forward"
EXPECTED_SOURCE_MODE = "TARGETED_POSTHOC_HISTORICAL_KLINE_FETCH"
LOCKED_CODES = (
    "000701",
    "000807",
    "001217",
    "001222",
    "600689",
    "600929",
    "601599",
    "603096",
    "603628",
    "605003",
)
_FORMAL_REPORT_NAMES = {"daily_close_20260918.html", "latest.html"}
VOLUME_OBSERVATION_FIELDS = _VOLUME_OBSERVATION_FIELDS
_MISSING_METRIC = {field: None for field in VOLUME_OBSERVATION_FIELDS}


class VolumeAddendumError(ValueError):
    """Fail-closed watchlist, input, or output identity error."""


FetchHistorical = Callable[[str], tuple[Sequence[Mapping[str, Any]], Mapping[str, Any]]]


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _now_bjt() -> datetime:
    return datetime.now(_BJT)


def _timestamp(value: datetime | str | None) -> str:
    parsed = _now_bjt() if value is None else value
    if isinstance(parsed, str):
        parsed = datetime.fromisoformat(parsed.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise VolumeAddendumError("timestamp must be timezone-aware")
    return parsed.astimezone(_BJT).isoformat()


def _read_source_bytes(source: str | Path) -> tuple[bytes, str]:
    """Read a local file or a read-only ``git:<ref>:<path>`` source."""

    text = str(source)
    if text.startswith("git:"):
        spec = text[4:]
        try:
            completed = subprocess.run(
                ["git", "show", spec],
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
        except (OSError, subprocess.CalledProcessError) as exc:
            detail = getattr(exc, "stderr", b"")
            if isinstance(detail, bytes):
                detail = detail.decode("utf-8", errors="replace").strip()
            raise VolumeAddendumError(f"cannot read git source {spec}: {detail or type(exc).__name__}") from exc
        return completed.stdout, text
    path = Path(source)
    try:
        return path.read_bytes(), str(path)
    except OSError as exc:
        raise VolumeAddendumError(f"cannot read watchlist source {path}: {exc}") from exc


def _as_code(value: Any, field: str) -> str:
    if isinstance(value, bool) or value is None:
        raise VolumeAddendumError(f"{field} is missing")
    text = str(value).strip()
    if not text.isdigit():
        raise VolumeAddendumError(f"{field} is not a six-digit code")
    text = text.zfill(6)
    if len(text) != 6:
        raise VolumeAddendumError(f"{field} is not a six-digit code")
    return text


def _finite_number(value: Any, field: str, *, positive: bool = False, non_negative: bool = False) -> float:
    if isinstance(value, bool):
        raise VolumeAddendumError(f"{field} is not numeric")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise VolumeAddendumError(f"{field} is not numeric") from exc
    if not math.isfinite(number):
        raise VolumeAddendumError(f"{field} is not finite")
    if positive and number <= 0:
        raise VolumeAddendumError(f"{field} must be positive")
    if non_negative and number < 0:
        raise VolumeAddendumError(f"{field} must be non-negative")
    return number


def _load_locked_watchlist(source: str | Path) -> tuple[dict[str, Any], list[dict[str, Any]], str, str]:
    payload, source_label = _read_source_bytes(source)
    source_sha256 = _sha256_bytes(payload)
    try:
        watchlist = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise VolumeAddendumError(f"watchlist is not valid UTF-8 JSON: {type(exc).__name__}") from exc
    if not isinstance(watchlist, Mapping):
        raise VolumeAddendumError("watchlist root is not an object")
    if watchlist.get("date") != TARGET_DATE:
        raise VolumeAddendumError(f"watchlist date must be {TARGET_DATE}")
    if watchlist.get("mode") != EXPECTED_WATCHLIST_MODE:
        raise VolumeAddendumError(f"watchlist mode must be {EXPECTED_WATCHLIST_MODE}")
    if watchlist.get("strategy_version") != EXPECTED_STRATEGY:
        raise VolumeAddendumError(f"watchlist strategy must be {EXPECTED_STRATEGY}")
    raw_candidates = watchlist.get("candidates")
    if not isinstance(raw_candidates, list) or len(raw_candidates) != len(LOCKED_CODES):
        raise VolumeAddendumError(f"watchlist must contain exactly {len(LOCKED_CODES)} candidates")

    candidates: list[dict[str, Any]] = []
    for rank, raw in enumerate(raw_candidates, start=1):
        if not isinstance(raw, Mapping):
            raise VolumeAddendumError(f"candidate {rank} is not an object")
        code = _as_code(raw.get("code"), f"candidate[{rank}].code")
        if code != LOCKED_CODES[rank - 1]:
            raise VolumeAddendumError(
                f"candidate order/code identity conflict at rank {rank}: {code} != {LOCKED_CODES[rank - 1]}"
            )
        name = raw.get("name")
        if not isinstance(name, str) or not name.strip():
            raise VolumeAddendumError(f"candidate[{rank}].name is missing")
        _finite_number(raw.get("score"), f"candidate[{rank}].score")
        score = raw.get("score")
        price = _finite_number(raw.get("price"), f"candidate[{rank}].price", positive=True)
        expected_signal_id = f"{EXPECTED_STRATEGY}:{TARGET_DATE}:{code}:B_BREAKOUT_RETEST"
        if raw.get("signal_id") != expected_signal_id:
            raise VolumeAddendumError(f"candidate[{rank}] signal identity conflict")
        candidates.append({
            "rank": rank,
            "code": code,
            "name": name,
            "score": score,
            "price": price,
            "signal_id": expected_signal_id,
            "candidate": dict(raw),
        })
    return dict(watchlist), candidates, source_label, source_sha256


def _source_metadata(code: str, *, retrieved_at_bjt: str | None = None, **extra: Any) -> dict[str, Any]:
    metadata = {
        "provider": EXPECTED_PROVIDER,
        "api": HITHINK_STOCK_KLINE_API,
        "base_url": HITHINK_BASE_URL,
        "provider_version": HITHINK_API_VERSION,
        "provider_symbol": _hithink_thscode(code),
        "adjustment": EXPECTED_ADJUSTMENT,
        "adjustment_mode": PROVIDER_QFQ_SNAPSHOT,
        "retrieved_at_bjt": retrieved_at_bjt,
    }
    metadata.update(extra)
    return metadata


def _validate_source_metadata(code: str, metadata: Mapping[str, Any]) -> None:
    expected_symbol = _hithink_thscode(code)
    if metadata.get("provider") != EXPECTED_PROVIDER:
        raise VolumeAddendumError("UNTRUSTED_PROVIDER")
    if metadata.get("api") not in {None, HITHINK_STOCK_KLINE_API}:
        raise VolumeAddendumError("UNEXPECTED_HISTORICAL_API")
    if metadata.get("provider_symbol") not in {None, expected_symbol}:
        raise VolumeAddendumError("HISTORICAL_SYMBOL_IDENTITY_CONFLICT")
    if metadata.get("adjustment") not in {None, EXPECTED_ADJUSTMENT}:
        raise VolumeAddendumError("HISTORICAL_ADJUSTMENT_CONFLICT")
    if metadata.get("adjustment_mode") not in {None, PROVIDER_QFQ_SNAPSHOT}:
        raise VolumeAddendumError("HISTORICAL_ADJUSTMENT_MODE_CONFLICT")


def _validate_and_normalize_bars(
    code: str,
    bars: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Apply the production historical OHLCV/date checks, then normalize values."""

    thscode = _hithink_thscode(code)
    try:
        validated = _validate_historical_bars(
            bars,
            thscode,
            minimum_acceptable_history=1,
            as_of_date=TARGET_DATE,
            require_last_bar_date=True,
            provider=EXPECTED_PROVIDER,
        )
    except Exception as exc:
        status = getattr(exc, "status", type(exc).__name__)
        diagnostics = getattr(exc, "diagnostics", {})
        latest = diagnostics.get("latest_historical_date") if isinstance(diagnostics, Mapping) else None
        suffix = f":{latest}" if latest else ""
        raise VolumeAddendumError(f"{status}{suffix}") from exc

    normalized: list[dict[str, Any]] = []
    for index, bar in enumerate(validated):
        if not isinstance(bar, Mapping):
            raise VolumeAddendumError(f"BAR_NOT_OBJECT:{index}")
        try:
            opening = _finite_number(bar.get("open"), f"{code}[{index}].open", positive=True)
            high = _finite_number(bar.get("high"), f"{code}[{index}].high", positive=True)
            low = _finite_number(bar.get("low"), f"{code}[{index}].low", positive=True)
            closing = _finite_number(bar.get("close"), f"{code}[{index}].close", positive=True)
            volume = _finite_number(bar.get("volume"), f"{code}[{index}].volume", non_negative=True)
        except VolumeAddendumError as exc:
            raise VolumeAddendumError(f"INVALID_OHLCV:{exc}") from exc
        if high < max(opening, closing) or low > min(opening, closing) or high < low:
            raise VolumeAddendumError(f"OHLC_CONFLICT:{bar.get('date')}")
        normalized.append({
            "date": str(bar["date"]),
            "open": opening,
            "high": high,
            "low": low,
            "close": closing,
            "volume": volume,
        })
    if not normalized or normalized[-1]["date"] != TARGET_DATE:
        latest = normalized[-1]["date"] if normalized else "NONE"
        raise VolumeAddendumError(f"TARGET_DAY_HISTORICAL_STALE:{latest}")
    return normalized


def _missing_observation(reason: str) -> dict[str, Any]:
    return {
        "observation_version": VOLUME_OBSERVATION_VERSION,
        "protocol_commit_sha": VOLUME_OBSERVATION_PROTOCOL_COMMIT_SHA,
        "window_days": None,
        **_MISSING_METRIC,
        "missing_reason": {field: reason for field in VOLUME_OBSERVATION_FIELDS},
    }


def _exception_reason(exc: Exception) -> str:
    if isinstance(exc, VolumeAddendumError):
        return str(exc)
    status = getattr(exc, "status", None)
    diagnostics = getattr(exc, "diagnostics", {})
    if status:
        latest = diagnostics.get("latest_historical_date") if isinstance(diagnostics, Mapping) else None
        return f"{status}:{latest}" if latest else str(status)
    return f"{type(exc).__name__}"


def _load_input_cache(
    cache_path: Path | None,
    codes: Sequence[str],
) -> tuple[dict[str, tuple[Sequence[Mapping[str, Any]], Mapping[str, Any]]], str, str | None]:
    if cache_path is None:
        return {}, "NOT_PROVIDED", None
    if not cache_path.exists():
        return {}, "NOT_FOUND", None
    try:
        payload = json.loads(cache_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        return {}, f"REJECTED:{type(exc).__name__}", "INPUT_CACHE_INVALID"
    if not isinstance(payload, Mapping):
        return {}, "REJECTED:ROOT_NOT_OBJECT", "INPUT_CACHE_INVALID"
    required = {
        "schema_version": INPUT_CACHE_SCHEMA_VERSION,
        "target_date": TARGET_DATE,
        "provider": EXPECTED_PROVIDER,
        "api": HITHINK_STOCK_KLINE_API,
        "adjustment": EXPECTED_ADJUSTMENT,
        "adjustment_mode": PROVIDER_QFQ_SNAPSHOT,
    }
    if any(payload.get(key) != value for key, value in required.items()):
        return {}, "REJECTED:PROVENANCE_CONFLICT", "INPUT_CACHE_PROVENANCE_CONFLICT"
    raw_items = payload.get("stock_klines")
    if not isinstance(raw_items, list):
        return {}, "REJECTED:STOCK_KLINES_MISSING", "INPUT_CACHE_INVALID"
    by_code: dict[str, tuple[Sequence[Mapping[str, Any]], Mapping[str, Any]]] = {}
    for raw in raw_items:
        if not isinstance(raw, Mapping):
            return {}, "REJECTED:STOCK_KLINE_NOT_OBJECT", "INPUT_CACHE_INVALID"
        try:
            code = _as_code(raw.get("symbol"), "input_cache.symbol")
        except VolumeAddendumError:
            return {}, "REJECTED:SYMBOL_INVALID", "INPUT_CACHE_INVALID"
        if code not in codes or code in by_code or not isinstance(raw.get("bars"), list):
            return {}, "REJECTED:SYMBOL_SET_CONFLICT", "INPUT_CACHE_SYMBOL_IDENTITY_CONFLICT"
        metadata = _source_metadata(
            code,
            retrieved_at_bjt=str(payload.get("retrieved_at_bjt") or ""),
            provider=payload["provider"],
            api=payload["api"],
            adjustment=payload["adjustment"],
            adjustment_mode=payload["adjustment_mode"],
        )
        by_code[code] = (raw["bars"], metadata)
    if set(by_code) != set(codes):
        return {}, "REJECTED:SYMBOL_SET_INCOMPLETE", "INPUT_CACHE_SYMBOL_SET_INCOMPLETE"
    return by_code, "USED", None


def _provider_fetcher(
    client: HiThinkClient,
    *,
    timeout: float,
    call_log: list[str],
) -> FetchHistorical:
    start_ms, end_ms = _historical_window(TARGET_DATE, DEFAULT_STOCK_BAR_COUNT)

    def fetch(code: str) -> tuple[Sequence[Mapping[str, Any]], Mapping[str, Any]]:
        # This function intentionally has no universe(), snapshots(), or
        # evaluator call.  The only provider read is one stock historical-K
        # request (with the existing bounded same-source stale retry).
        call_log.append(code)
        bars, resolution = _resolve_market_bars(
            client,
            code,
            requested_count=DEFAULT_STOCK_BAR_COUNT,
            minimum_acceptable_history=1,
            as_of_date=TARGET_DATE,
            timeout=timeout,
            request_get=None,
            retries=0,
            index=False,
            allow_tencent_fallback=False,
        )
        metadata = _source_metadata(
            code,
            provider=resolution.get("provider", EXPECTED_PROVIDER),
            api=HITHINK_STOCK_KLINE_API,
            adjustment=EXPECTED_ADJUSTMENT,
            adjustment_mode=resolution.get("adjustment_mode", PROVIDER_QFQ_SNAPSHOT),
            source=resolution.get("source"),
            retry_count=resolution.get("retry_count", 0),
        )
        return bars, metadata

    return fetch


def _format_metric(field: str, value: Any) -> str:
    if value is None:
        return "—"
    number = float(value)
    if field == "down_volume_share":
        return f"{number * 100:.1f}%"
    return f"{number:.2f}×"


def _esc(value: Any) -> str:
    return html.escape("" if value is None else str(value), quote=True)


def _metric_cell(observation: Mapping[str, Any], field: str) -> str:
    value = observation.get(field)
    reason = observation.get("missing_reason", {})
    reason = reason.get(field) if isinstance(reason, Mapping) else None
    extra = f'<small class="missing">{_esc(reason)}</small>' if value is None and reason else ""
    return f'<td><strong>{_esc(_format_metric(field, value))}</strong>{extra}</td>'


def _render_html(summary: Mapping[str, Any]) -> str:
    rows = []
    for item in summary["candidates"]:
        observation = item["observation"]
        reasons = observation.get("missing_reason", {})
        status = "VALID" if item["complete"] else "PARTIAL" if item["valid"] else "MISSING"
        if item.get("validation_reason"):
            status = f"{status}: {item['validation_reason']}"
        rows.append(
            "<tr>"
            f"<td>{_esc(item['rank'])}</td>"
            f"<td><code>{_esc(item['code'])}</code></td>"
            f"<td>{_esc(item['name'])}</td>"
            f"<td>{_esc(item['score'])}</td>"
            f"{_metric_cell(observation, 'down_volume_share')}"
            f"{_metric_cell(observation, 'up_down_volume_ratio')}"
            f"{_metric_cell(observation, 'pullback_volume_decay_ratio')}"
            f"<td><strong>{_esc(status)}</strong>"
            + (f"<small class=\"missing\">{_esc(json.dumps(reasons, ensure_ascii=False, sort_keys=True))}</small>" if not item["valid"] else "")
            + "</td></tr>"
        )

    artifact_rows = []
    for label, value in summary["original_artifacts"].items():
        artifact_rows.append(f"<tr><th>{_esc(label)}</th><td><code>{_esc(value)}</code></td></tr>")

    return f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="report-kind" content="{RETROSPECTIVE_VOLUME_ENRICHMENT}">
<title>A股量能补充报告 · {TARGET_DATE}</title>
<style>
:root {{ color-scheme: light; --bg:#f3f5f7; --surface:#fff; --text:#17232d; --muted:#63717c; --border:#d9e1e6; --accent:#28658a; --warn:#8a5a00; }}
* {{ box-sizing:border-box; }} body {{ margin:0; background:var(--bg); color:var(--text); font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif; line-height:1.5; }}
main {{ width:min(1440px,100%); margin:0 auto; padding:24px; }} h1 {{ margin:0 0 4px; font-size:clamp(24px,4vw,34px); }} h2 {{ margin:28px 0 10px; font-size:20px; }} p {{ margin:8px 0; }}
.eyebrow {{ color:var(--accent); font-size:12px; font-weight:700; letter-spacing:.08em; }} .notice {{ padding:14px 16px; margin:16px 0; border:1px solid #e5c785; background:#fff8e6; color:#5c4300; border-radius:8px; }}
.grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(220px,1fr)); gap:12px; }} .card {{ padding:14px; border:1px solid var(--border); background:var(--surface); border-radius:8px; }} .label {{ color:var(--muted); font-size:12px; }} .value {{ display:block; margin-top:3px; font-weight:700; overflow-wrap:anywhere; }}
.table-wrap {{ overflow:auto; border:1px solid var(--border); border-radius:8px; background:var(--surface); }} table {{ width:100%; min-width:1080px; border-collapse:collapse; }} th,td {{ padding:10px 9px; border-bottom:1px solid var(--border); text-align:left; vertical-align:top; }} th {{ background:#f7f9fa; color:#344752; font-size:12px; }} tbody tr:last-child td {{ border-bottom:0; }} code {{ overflow-wrap:anywhere; }} small {{ display:block; color:var(--muted); font-weight:400; }} .missing {{ color:var(--warn); margin-top:3px; font-size:11px; }}
ul {{ margin:8px 0 8px 20px; padding:0; }} .muted {{ color:var(--muted); }}
@media (max-width:600px) {{ main {{ padding:16px 12px 28px; }} table {{ min-width:980px; }} h2 {{ margin-top:22px; }} }}
</style>
</head>
<body><main>
<div class="eyebrow">{RETROSPECTIVE_VOLUME_ENRICHMENT}</div>
<h1>2026-09-18 正式 B 名单 · 量能补充</h1>
<p class="muted">独立 addendum；不覆盖、不改写原正式日报。</p>
<div class="notice"><strong>重要边界：</strong>本报告是事后量能补充，不是 9 月 18 日当时已冻结的完整生产输入；不属于 prospective shadow，不参与 Formal B 筛选、Score、排名或任何生产决策。</div>

<section class="grid">
<div class="card"><span class="label">原正式名单日期</span><span class="value">{_esc(summary['target_date'])}</span></div>
<div class="card"><span class="label">原名单候选</span><span class="value">{_esc(summary['candidate_count'])} 只；顺序锁定</span></div>
<div class="card"><span class="label">逐票输入有效 / 无有效指标</span><span class="value">{_esc(summary['valid_count'])} / {_esc(summary['missing_count'])}</span></div>
<div class="card"><span class="label">三项全有效 / 指标部分缺失</span><span class="value">{_esc(summary['complete_count'])} / {_esc(summary['partial_count'])}</span></div>
<div class="card"><span class="label">计算协议</span><span class="value">{_esc(VOLUME_OBSERVATION_VERSION)}</span></div>
</section>

<h2>原正式产物身份</h2>
<div class="table-wrap"><table><tbody>{''.join(artifact_rows)}</tbody></table></div>

<h2>10 只锁定候选的量能观察</h2>
<p class="muted">窗口严格复用：突破日 <code>i</code> 与信号日 <code>T</code> 已由原逻辑确定，计算区间为 <code>R=i+1:T-1</code>，信号日不计入。</p>
<div class="table-wrap"><table><thead><tr><th>原排名</th><th>代码</th><th>名称</th><th>Score</th><th>下跌日成交量占比</th><th>上涨/下跌日均量比</th><th>回踩后半/前半均量比</th><th>验证状态 / 缺失原因</th></tr></thead><tbody>{''.join(rows)}</tbody></table></div>

<h2>数据来源与验证</h2>
<div class="grid">
<div class="card"><span class="label">输入来源</span><span class="value">{_esc(summary['input_source_status'])}</span><small>{_esc(summary['source_mode'])}</small></div>
<div class="card"><span class="label">Provider / API</span><span class="value">{_esc(EXPECTED_PROVIDER)}</span><small>{_esc(HITHINK_STOCK_KLINE_API)} · adjust=forward · {PROVIDER_QFQ_SNAPSHOT}</small></div>
<div class="card"><span class="label">实际获取时间（BJT）</span><span class="value">{_esc(summary['retrieval_started_at_bjt'])}</span><small>结束：{_esc(summary['retrieval_finished_at_bjt'])}</small></div>
<div class="card"><span class="label">历史日期上界</span><span class="value">≤ {TARGET_DATE}</span><small>未来交易日输入 fail-closed</small></div>
</div>
<ul>
<li>本次仅允许锁定的 10 个代码进入历史 K 线读取；未调用全市场 universe、全市场 snapshot 或 Formal B evaluator。</li>
<li>prospective shadow capture：未执行；不会写入任何 shadow/runtime-state，也不会产生 <code>PROSPECTIVE_CAPTURED</code> 记录。</li>
<li>量能值与缺失值仅描述性展示；缺失不会被填 0，也不会改变原名单身份、顺序或排名。</li>
<li>协议版本：<code>{_esc(VOLUME_OBSERVATION_VERSION)}</code>；protocol commit：<code>{_esc(VOLUME_OBSERVATION_PROTOCOL_COMMIT_SHA)}</code>。</li>
</ul>
<p class="muted">生成时间（BJT）：{_esc(summary['generated_at_bjt'])} · 报告 schema：{_esc(REPORT_SCHEMA_VERSION)}</p>
</main></body></html>
"""


def _write_report(path: Path, html_text: str, *, watchlist_sha256: str) -> None:
    if path.name in _FORMAL_REPORT_NAMES:
        raise VolumeAddendumError(f"refusing to overwrite canonical report {path.name}")
    if path.exists():
        try:
            existing = path.read_text(encoding="utf-8")
        except OSError as exc:
            raise VolumeAddendumError(f"cannot inspect existing output: {path}") from exc
        if RETROSPECTIVE_VOLUME_ENRICHMENT not in existing or watchlist_sha256 not in existing:
            raise VolumeAddendumError("OUTPUT_IDENTITY_CONFLICT")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(html_text, encoding="utf-8", newline="\n")
    except OSError as exc:
        raise VolumeAddendumError(f"cannot write addendum report {path}: {exc}") from exc


def generate_volume_addendum(
    watchlist_source: str | Path,
    output_path: str | Path,
    *,
    cache_path: str | Path | None = None,
    original_artifacts: Mapping[str, str] | None = None,
    fetch_historical: FetchHistorical | None = None,
    provider_client: HiThinkClient | None = None,
    timeout: float = 15.0,
    retrieved_at_bjt: datetime | str | None = None,
    generated_at_bjt: datetime | str | None = None,
) -> dict[str, Any]:
    """Generate one independent addendum and return its machine summary."""

    _watchlist, candidates, source_label, watchlist_sha256 = _load_locked_watchlist(watchlist_source)
    codes = [item["code"] for item in candidates]
    retrieval_started = _timestamp(retrieved_at_bjt)
    cache_entries, cache_status, cache_reason = _load_input_cache(
        None if cache_path is None else Path(cache_path),
        codes,
    )

    call_log: list[str] = []
    fetch_error: str | None = None
    fetcher = fetch_historical
    if fetcher is None and len(cache_entries) < len(codes):
        try:
            client = provider_client or HiThinkClient()
            fetcher = _provider_fetcher(client, timeout=timeout, call_log=call_log)
        except Exception as exc:
            fetch_error = _exception_reason(exc)

    results: list[dict[str, Any]] = []
    for candidate in candidates:
        code = candidate["code"]
        metadata: Mapping[str, Any] | None = None
        raw_bars: Sequence[Mapping[str, Any]] | None = None
        validation_reason: str | None = None
        source_kind = "CACHE"
        if code in cache_entries:
            raw_bars, metadata = cache_entries[code]
        elif fetcher is not None:
            source_kind = "TARGETED_PROVIDER_FETCH"
            if fetch_historical is not None:
                call_log.append(code)
            try:
                raw_bars, metadata = fetcher(code)
                if not isinstance(metadata, Mapping):
                    metadata = _source_metadata(code)
            except Exception as exc:
                validation_reason = _exception_reason(exc)
        elif fetch_error:
            validation_reason = fetch_error
        elif cache_reason:
            validation_reason = cache_reason
        else:
            validation_reason = "HISTORICAL_INPUT_UNAVAILABLE"

        observation = _missing_observation(validation_reason or "HISTORICAL_INPUT_UNAVAILABLE")
        bar_count: int | None = None
        first_bar_date: str | None = None
        last_bar_date: str | None = None
        if raw_bars is not None and metadata is not None and validation_reason is None:
            try:
                _validate_source_metadata(code, metadata)
                normalized_bars = _validate_and_normalize_bars(code, raw_bars)
                target_close = normalized_bars[-1]["close"]
                if not math.isclose(target_close, candidate["price"], rel_tol=0.0, abs_tol=1e-7):
                    raise VolumeAddendumError(
                        f"TARGET_DAY_CLOSE_INCOMPATIBLE:{target_close}!={candidate['price']}"
                    )
                _reactivation, _structural, observation = _stock_snapshot(
                    candidate["candidate"],
                    [{"symbol": code, "bars": normalized_bars}],
                    TARGET_DATE,
                )
                if observation.get("observation_version") != VOLUME_OBSERVATION_VERSION:
                    raise VolumeAddendumError("VOLUME_PROTOCOL_VERSION_CONFLICT")
                bar_count = len(normalized_bars)
                first_bar_date = normalized_bars[0]["date"]
                last_bar_date = normalized_bars[-1]["date"]
            except Exception as exc:
                validation_reason = _exception_reason(exc)
                observation = _missing_observation(validation_reason)
        valid = validation_reason is None and any(
            observation.get(field) is not None for field in VOLUME_OBSERVATION_FIELDS
        )
        complete = valid and all(observation.get(field) is not None for field in VOLUME_OBSERVATION_FIELDS)
        results.append({
            "rank": candidate["rank"],
            "code": code,
            "name": candidate["name"],
            "score": candidate["score"],
            "price": candidate["price"],
            "signal_id": candidate["signal_id"],
            "observation": observation,
            "valid": valid,
            "complete": complete,
            "validation_reason": validation_reason,
            "source_kind": source_kind,
            "bar_count": bar_count,
            "first_bar_date": first_bar_date,
            "last_bar_date": last_bar_date,
        })

    retrieval_finished = _timestamp(retrieved_at_bjt) if retrieved_at_bjt is not None else _timestamp(None)
    valid_count = sum(1 for item in results if item["valid"])
    complete_count = sum(1 for item in results if item["complete"])
    partial_count = sum(1 for item in results if item["valid"] and not item["complete"])
    artifact_values = {
        "watchlist_sha256": watchlist_sha256,
        "checkpoint_sha256": "NOT_PROVIDED",
        "formal_report_sha256": "NOT_PROVIDED",
        "delivery_receipt_sha256": "NOT_PROVIDED",
    }
    if original_artifacts:
        for key in artifact_values:
            if original_artifacts.get(key):
                artifact_values[key] = str(original_artifacts[key])
    summary: dict[str, Any] = {
        "schema_version": REPORT_SCHEMA_VERSION,
        "report_kind": RETROSPECTIVE_VOLUME_ENRICHMENT,
        "target_date": TARGET_DATE,
        "source_watchlist": source_label,
        "watchlist_sha256": watchlist_sha256,
        "original_artifacts": artifact_values,
        "candidate_count": len(results),
        "valid_count": valid_count,
        "missing_count": len(results) - valid_count,
        "complete_count": complete_count,
        "partial_count": partial_count,
        "candidates": results,
        "input_cache_status": cache_status,
        "input_source_status": (
            "VALIDATED_LOCAL_CACHE"
            if cache_status == "USED"
            else "NO_TRUSTED_CACHE; TARGETED_HISTORICAL_FETCH"
        ),
        "cache_rejection_reason": cache_reason,
        "source_mode": EXPECTED_SOURCE_MODE,
        "provider": EXPECTED_PROVIDER,
        "provider_api": HITHINK_STOCK_KLINE_API,
        "provider_call_symbols": list(call_log),
        "historical_kline_call_count": len(call_log),
        "universe_call_count": 0,
        "snapshot_call_count": 0,
        "formal_b_evaluator_call_count": 0,
        "prospective_shadow_capture": "NOT_CREATED",
        "retrieval_started_at_bjt": retrieval_started,
        "retrieval_finished_at_bjt": retrieval_finished,
        "generated_at_bjt": _timestamp(generated_at_bjt),
    }
    html_text = _render_html(summary)
    _write_report(Path(output_path), html_text, watchlist_sha256=watchlist_sha256)
    summary["output_path"] = str(Path(output_path))
    summary["output_sha256"] = _sha256_bytes(html_text.encode("utf-8"))
    return summary


def _parse_original_artifacts(args: argparse.Namespace) -> dict[str, str]:
    return {
        "checkpoint_sha256": args.checkpoint_sha256,
        "formal_report_sha256": args.formal_report_sha256,
        "delivery_receipt_sha256": args.delivery_receipt_sha256,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--watchlist", required=True, help="local path or git:<ref>:<path> to the locked watchlist")
    parser.add_argument("--output", required=True, help="independent HTML addendum path")
    parser.add_argument("--cache", help="optional validated RETROSPECTIVE_VOLUME_INPUT_V1 cache")
    parser.add_argument("--checkpoint-sha256", default="", help="original checkpoint SHA-256")
    parser.add_argument("--formal-report-sha256", default="", help="original formal daily report SHA-256")
    parser.add_argument("--delivery-receipt-sha256", default="", help="original delivery receipt SHA-256")
    parser.add_argument("--timeout", type=float, default=15.0)
    parser.add_argument("--retrieved-at-bjt", default=None, help="fixed timestamp for reproducible tests")
    parser.add_argument("--generated-at-bjt", default=None, help="fixed timestamp for reproducible tests")
    args = parser.parse_args(argv)
    try:
        summary = generate_volume_addendum(
            args.watchlist,
            args.output,
            cache_path=args.cache,
            original_artifacts=_parse_original_artifacts(args),
            timeout=args.timeout,
            retrieved_at_bjt=args.retrieved_at_bjt,
            generated_at_bjt=args.generated_at_bjt,
        )
    except VolumeAddendumError as exc:
        parser.error(str(exc))
        return 2
    print(json.dumps({
        "report_kind": summary["report_kind"],
        "output_path": summary["output_path"],
        "output_sha256": summary["output_sha256"],
        "valid_count": summary["valid_count"],
        "missing_count": summary["missing_count"],
        "complete_count": summary["complete_count"],
        "partial_count": summary["partial_count"],
        "historical_kline_call_count": summary["historical_kline_call_count"],
        "provider_call_symbols": summary["provider_call_symbols"],
        "prospective_shadow_capture": summary["prospective_shadow_capture"],
    }, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
