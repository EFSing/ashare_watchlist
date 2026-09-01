from __future__ import annotations

from development_preflight import _sector_audit


def test_sector_audit_distinguishes_exact_duplicates_from_ambiguous_memberships():
    definitions = [
        {"label": "a", "板块": "A"},
        {"label": "b", "板块": "B"},
    ]
    members = {
        "a": [
            {"代码": "002217", "名称": "ST合力泰"},
            {"代码": "002217", "名称": "ST合力泰"},
            {"代码": "600714", "名称": "金瑞矿业"},
        ],
        "b": [{"代码": "600714", "名称": "金瑞矿业"}],
    }

    report = _sector_audit(definitions, members, {"002217": "ST合力泰", "600714": "金瑞矿业"})

    assert report["raw_member_rows"] == 4
    assert report["repeated_sector_membership_signal_count"] == 1
    assert [item["symbol"] for item in report["exact_duplicate_symbols"]] == ["002217"]
    assert report["ambiguous_symbols"] == ["600714"]


def test_sector_audit_reports_symbol_authoritative_name_diagnostic_without_fuzzy_match():
    report = _sector_audit(
        [{"label": "a", "板块": "A"}],
        {"a": [{"代码": "000012", "名称": "南 玻Ａ"}]},
        {"000012": "南玻Ａ"},
    )

    assert report["common_symbols"] == 1
    assert report["exact_raw_name_matches"] == 0
    assert report["normalized_name_matches"] == 0
    assert report["normalization_only_mismatches_resolved"] == 0
