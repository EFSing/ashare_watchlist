from __future__ import annotations

from datetime import date, time, timedelta

import pytest

from generation_contract import (
    ASIA_SHANGHAI,
    CALENDAR_ERROR,
    EXCHANGE_CALENDARS_VERSION,
    FUTURE_DATA_DETECTED,
    GenerationContractError,
    INPUT_DATE_MISMATCH,
    LIVE_OBSERVED,
    POINT_IN_TIME,
    PROVIDER_QFQ_SNAPSHOT,
    PROVIDER_RAW_SNAPSHOT,
    READY_FOR_STRATEGY_EVALUATION,
    SESSION_NOT_CLOSED,
    UNSUPPORTED_HISTORICAL_REPLAY,
    UNSUPPORTED_MODE,
    IndexManifest,
    KlineManifest,
    QuoteSnapshotManifest,
    RunContext,
    SectorManifest,
    UniverseManifest,
    freeze_generation_inputs,
    next_execution_date,
)
from trading_calendar import TradingCalendar, default_calendar


AS_OF = "2026-08-27"
RETRIEVED_AT = "2026-08-27T15:05:00+08:00"


def _bars(last_date: str = AS_OF) -> list[dict[str, object]]:
    previous_date = (date.fromisoformat(last_date) - timedelta(days=1)).isoformat()
    return [
        {"date": previous_date, "open": 9.8, "high": 10.2, "low": 9.7, "close": 10.0, "volume": 100},
        {"date": last_date, "open": 10.0, "high": 10.4, "low": 9.9, "close": 10.3, "volume": 120},
    ]


def _inputs(
    *,
    as_of_date: str = AS_OF,
    symbols: tuple[str, ...] = ("600000",),
    quote_date: str | None = None,
    stock_last_date: str | None = None,
    index_last_date: str | None = None,
    retrieved_at: str = RETRIEVED_AT,
    historical: bool = False,
    sector_semantics: str = LIVE_OBSERVED,
    universe_semantics: str = LIVE_OBSERVED,
    stock_adjustment_mode: str = PROVIDER_QFQ_SNAPSHOT,
    stock_provider: str = "Tencent",
    index_adjustment_mode: str = PROVIDER_QFQ_SNAPSHOT,
    index_provider: str = "Tencent",
):
    quote_date = as_of_date if quote_date is None else quote_date
    stock_last_date = as_of_date if stock_last_date is None else stock_last_date
    index_last_date = as_of_date if index_last_date is None else index_last_date
    universe = UniverseManifest(
        as_of_date=as_of_date,
        retrieved_at_bjt=retrieved_at,
        source="akshare.stock_info_a_code_name",
        symbols=symbols,
        temporal_semantics=universe_semantics,
    )
    quotes = QuoteSnapshotManifest(
        as_of_date=as_of_date,
        retrieved_at_bjt=retrieved_at,
        source="qt.gtimg.cn",
        quotes={
            symbol: {
                "code": symbol,
                "quote_date": quote_date,
                "price": 10.0 if symbol == "600000" else 11.0,
            }
            for symbol in symbols
        },
    )
    stock_klines = tuple(
        KlineManifest(
            symbol=symbol,
            as_of_date=as_of_date,
            retrieved_at_bjt=retrieved_at,
            bars=_bars(stock_last_date),
            provider=stock_provider,
            adjustment_mode=stock_adjustment_mode,
        )
        for symbol in reversed(symbols)
    )
    index = IndexManifest(
        symbol="sh000001",
        as_of_date=as_of_date,
        retrieved_at_bjt=retrieved_at,
        bars=_bars(index_last_date),
        provider=index_provider,
        adjustment_mode=index_adjustment_mode,
    )
    sector = SectorManifest(
        as_of_date=as_of_date,
        retrieved_at_bjt=retrieved_at,
        source="akshare.stock_sector_detail",
        definitions={"banking": {"name": "银行"}},
        members={"banking": list(reversed(symbols))},
        rank_input=[{"sector": "banking", "rank": 1}],
        temporal_semantics=sector_semantics,
    )
    context = RunContext(
        as_of_date=as_of_date,
        mode="close",
        timezone=ASIA_SHANGHAI,
        historical=historical,
        provider_version_metadata={"exchange_calendars": "4.13.2"},
    )
    return context, universe, quotes, stock_klines, index, sector


def _freeze(**kwargs):
    values = _inputs(**kwargs)
    return freeze_generation_inputs(
        *values,
        calendar=TradingCalendar(holidays=set(), session_close_time=time(15, 0)),
    )


def test_complete_t_day_inputs_are_ready_and_record_qfq_evidence():
    manifest = _freeze()

    assert manifest.status == READY_FOR_STRATEGY_EVALUATION
    assert manifest.run_context.as_of_date == AS_OF
    assert manifest.run_context.signal_date == AS_OF
    assert manifest.signal_date == AS_OF
    assert manifest.earliest_execution_date == "2026-08-28"
    kline = manifest.stock_klines[0]
    assert kline.provider == "Tencent"
    assert kline.adjustment_mode == PROVIDER_QFQ_SNAPSHOT
    assert kline.first_bar_date == "2026-08-26"
    assert kline.last_bar_date == AS_OF
    assert kline.bar_count == 2
    assert len(kline.normalized_data_sha256) == 64
    assert len(manifest.input_fingerprint) == 64
    assert "input_fingerprint" not in manifest._fingerprint_payload()


def test_quote_date_mismatch_fails_fast():
    with pytest.raises(GenerationContractError) as caught:
        _freeze(quote_date="2026-08-26")

    assert caught.value.status == INPUT_DATE_MISMATCH


def test_past_as_of_with_today_observation_is_rejected_without_historical_flag():
    with pytest.raises(GenerationContractError) as caught:
        _freeze(
            as_of_date="2026-08-20",
            retrieved_at="2026-08-27T15:30:00+08:00",
        )

    assert caught.value.status == INPUT_DATE_MISMATCH


def test_live_observed_timestamp_date_must_equal_t():
    with pytest.raises(GenerationContractError) as caught:
        _freeze(retrieved_at="2026-08-26T15:30:00+08:00")

    assert caught.value.status == INPUT_DATE_MISMATCH


def test_stock_kline_future_bar_fails_fast():
    with pytest.raises(GenerationContractError) as caught:
        _freeze(stock_last_date="2026-08-28")

    assert caught.value.status == FUTURE_DATA_DETECTED


def test_non_empty_stock_kline_may_end_before_t():
    manifest = _freeze(stock_last_date="2026-08-26")

    assert manifest.stock_klines[0].bar_count == 2
    assert manifest.stock_klines[0].last_bar_date == "2026-08-26"


def test_raw_stock_kline_is_rejected():
    with pytest.raises(GenerationContractError) as caught:
        _freeze(stock_adjustment_mode=PROVIDER_RAW_SNAPSHOT)

    assert caught.value.status == UNSUPPORTED_MODE


def test_hithink_raw_index_kline_is_accepted():
    manifest = _freeze(
        index_provider="HiThink Financial-API",
        index_adjustment_mode=PROVIDER_RAW_SNAPSHOT,
    )

    assert manifest.index.provider == "HiThink Financial-API"
    assert manifest.index.adjustment_mode == PROVIDER_RAW_SNAPSHOT


def test_tencent_qfq_index_fallback_is_accepted():
    manifest = _freeze(index_provider="Tencent", index_adjustment_mode=PROVIDER_QFQ_SNAPSHOT)

    assert manifest.index.provider == "Tencent"
    assert manifest.index.adjustment_mode == PROVIDER_QFQ_SNAPSHOT


@pytest.mark.parametrize(
    ("stock_adjustment_mode", "index_provider", "index_adjustment_mode"),
    [
        ("UNSUPPORTED_MODE", "Tencent", PROVIDER_QFQ_SNAPSHOT),
        (PROVIDER_QFQ_SNAPSHOT, "HiThink Financial-API", PROVIDER_QFQ_SNAPSHOT),
        (PROVIDER_QFQ_SNAPSHOT, "Tencent", PROVIDER_RAW_SNAPSHOT),
        (PROVIDER_QFQ_SNAPSHOT, "Other", PROVIDER_RAW_SNAPSHOT),
    ],
)
def test_unsupported_stock_or_index_adjustment_mapping_fails(
    stock_adjustment_mode, index_provider, index_adjustment_mode
):
    with pytest.raises(GenerationContractError) as caught:
        _freeze(
            stock_adjustment_mode=stock_adjustment_mode,
            index_provider=index_provider,
            index_adjustment_mode=index_adjustment_mode,
        )

    assert caught.value.status == UNSUPPORTED_MODE


def test_index_latest_bar_must_equal_t():
    with pytest.raises(GenerationContractError) as caught:
        _freeze(index_last_date="2026-08-26")

    assert caught.value.status == INPUT_DATE_MISMATCH


def test_historical_run_rejects_live_observed_universe():
    with pytest.raises(GenerationContractError) as caught:
        _freeze(historical=True)

    assert caught.value.status == UNSUPPORTED_HISTORICAL_REPLAY


def test_historical_run_rejects_live_observed_sector():
    with pytest.raises(GenerationContractError) as caught:
        _freeze(historical=True, universe_semantics=POINT_IN_TIME, sector_semantics=LIVE_OBSERVED)

    assert caught.value.status == UNSUPPORTED_HISTORICAL_REPLAY


def test_premarket_generation_is_not_supported():
    values = list(_inputs())
    values[0] = RunContext(as_of_date=AS_OF, mode="premarket")

    with pytest.raises(GenerationContractError) as caught:
        freeze_generation_inputs(
            *values,
            calendar=TradingCalendar(holidays=set(), session_close_time=time(15, 0)),
        )

    assert caught.value.status == UNSUPPORTED_MODE


def test_close_generation_before_xshg_session_close_is_rejected():
    with pytest.raises(GenerationContractError) as caught:
        _freeze(retrieved_at="2026-08-27T14:30:00+08:00")

    assert caught.value.status == SESSION_NOT_CLOSED


def test_close_generation_at_xshg_session_close_is_allowed():
    manifest = _freeze(retrieved_at="2026-08-27T15:00:00+08:00")

    assert manifest.status == READY_FOR_STRATEGY_EVALUATION


def test_close_generation_after_xshg_session_close_is_allowed():
    manifest = _freeze(retrieved_at="2026-08-27T15:01:00+08:00")

    assert manifest.status == READY_FOR_STRATEGY_EVALUATION


def test_next_execution_skips_weekend_and_holiday():
    calendar = TradingCalendar(holidays={date(2026, 8, 31)})

    assert next_execution_date("2026-08-28", calendar) == "2026-09-01"


def test_default_xshg_calendar_skips_national_day_holiday():
    assert next_execution_date("2024-09-30") == "2024-10-08"


def test_default_xshg_calendar_exposes_official_session_close_in_bjt():
    assert default_calendar().session_close("2024-09-30").isoformat() == "2024-09-30T15:00:00+08:00"


def test_as_of_weekend_is_a_calendar_error():
    values = list(_inputs())
    values[0] = RunContext(as_of_date="2026-08-29")
    values[1] = UniverseManifest(
        as_of_date="2026-08-29",
        retrieved_at_bjt=RETRIEVED_AT,
        source="akshare",
        symbols=("600000",),
    )

    with pytest.raises(GenerationContractError) as caught:
        freeze_generation_inputs(
            *values,
            calendar=TradingCalendar(holidays=set(), session_close_time=time(15, 0)),
        )

    assert caught.value.status == CALENDAR_ERROR


def test_symbol_order_does_not_change_input_fingerprint():
    first = _freeze(symbols=("600000", "000001"))
    second = _freeze(symbols=("000001", "600000"))

    assert first.universe.symbols == ("000001", "600000")
    assert first.input_fingerprint == second.input_fingerprint
    assert first.universe.content_sha256 == second.universe.content_sha256


def test_universe_scope_is_part_of_manifest_and_input_identity():
    first = _freeze()
    changed_values = list(_inputs())
    changed_values[1] = UniverseManifest(
        as_of_date=AS_OF,
        retrieved_at_bjt=RETRIEVED_AT,
        source="akshare.stock_info_a_code_name",
        symbols=("600000",),
        temporal_semantics=LIVE_OBSERVED,
        universe_scope="SH_SZ_BJ_A_SHARE",
        universe_scope_version="TRADABLE_UNIVERSE_SCOPE_V2",
    )
    second = freeze_generation_inputs(
        *changed_values,
        calendar=TradingCalendar(holidays=set(), session_close_time=time(15, 0)),
    )

    assert first.universe.universe_scope == "SH_SZ_A_SHARE_ONLY"
    assert first.universe.universe_scope_version == "TRADABLE_UNIVERSE_SCOPE_V1"
    assert second.input_fingerprint != first.input_fingerprint
    assert second.universe.content_sha256 != first.universe.content_sha256
    assert second._fingerprint_payload()["universe_scope"] == {
        "name": "SH_SZ_BJ_A_SHARE",
        "version": "TRADABLE_UNIVERSE_SCOPE_V2",
    }


def test_retrieved_at_does_not_change_content_or_input_fingerprint():
    first = _freeze(retrieved_at="2026-08-27T15:05:00+08:00")
    second = _freeze(retrieved_at="2026-08-27T18:35:00+08:00")

    assert first.input_fingerprint == second.input_fingerprint
    assert first.universe.content_sha256 == second.universe.content_sha256
    assert first.quote_snapshot.content_sha256 == second.quote_snapshot.content_sha256
    assert first.stock_klines[0].normalized_data_sha256 == second.stock_klines[0].normalized_data_sha256
    assert first.index.normalized_data_sha256 == second.index.normalized_data_sha256
    assert first.sector.content_sha256 == second.sector.content_sha256


def test_actual_input_value_change_changes_fingerprint():
    values = list(_inputs())
    first = freeze_generation_inputs(
        *values,
        calendar=TradingCalendar(holidays=set(), session_close_time=time(15, 0)),
    )
    changed_quote = QuoteSnapshotManifest(
        as_of_date=AS_OF,
        retrieved_at_bjt=RETRIEVED_AT,
        source="qt.gtimg.cn",
        quotes={"600000": {"code": "600000", "quote_date": AS_OF, "price": 10.01}},
    )
    values[2] = changed_quote
    second = freeze_generation_inputs(
        *values,
        calendar=TradingCalendar(holidays=set(), session_close_time=time(15, 0)),
    )

    assert first.quote_snapshot.content_sha256 != second.quote_snapshot.content_sha256
    assert first.input_fingerprint != second.input_fingerprint


def test_live_generation_requires_live_observed_sector_semantics():
    with pytest.raises(GenerationContractError) as caught:
        _freeze(sector_semantics=POINT_IN_TIME)

    assert caught.value.status == UNSUPPORTED_MODE


def test_runtime_metadata_records_pinned_exchange_calendars_version():
    assert RunContext(as_of_date=AS_OF).provider_version_metadata["exchange_calendars"] == (
        EXCHANGE_CALENDARS_VERSION
    )
