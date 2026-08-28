import json
from pathlib import Path


AUDIT_PATH = Path(__file__).parents[1] / "data" / "validation" / "phase2e_source_audit.json"


def _audit() -> dict[str, object]:
    return json.loads(AUDIT_PATH.read_text(encoding="utf-8"))


def _probe() -> dict[str, object]:
    probe_path = AUDIT_PATH.with_name("phase2e_hithink_probe.json")
    return json.loads(probe_path.read_text(encoding="utf-8"))


def test_phase2e_audit_shrinks_to_historical_sector_membership_only():
    audit = _audit()

    assert audit["schema_version"] == "PHASE2E_SOURCE_AUDIT_V1"
    assert audit["status"] == "REQUIRES_HISTORICAL_SECTOR_MEMBERSHIP_SOURCE"
    assert audit["status"] != "BLOCKED_NO_PIT_DATASET"
    assert [item["id"] for item in audit["blockers"]] == [
        "HISTORICAL_SECTOR_MEMBERSHIP_UNAVAILABLE"
    ]
    assert audit["blockers"][0]["scope"] == ["sector.membership"]

    dataset = audit["dataset"]
    assert dataset["frozen"] is False
    assert dataset["dataset_version"] is None
    assert dataset["content_sha256"] is None
    assert dataset["manifest_sha256"] is None


def test_phase2e_audit_uses_financial_api_without_classic_ifind_gate():
    audit = _audit()

    inventory = audit["runtime_inventory"]
    assert inventory["configured_clients"] == ["HiThink REST API"]
    assert inventory["configured_credentials"] is True
    assert inventory["configured_credentials_detail"]["classic_ifind_path_required"] is False
    assert inventory["current_data_fetched"] is True
    assert inventory["strategy_validation_run"] is False
    assert inventory["final_oos_read"] is False
    assert inventory["parameter_tuning_run"] is False

    review = audit["official_financial_api_ecosystem_review"]
    assert review["reviewed"] is True
    assert review["historical_membership_or_effective_date_object_found"] is False


def test_phase2e_audit_records_core_and_full_validation_decision_point():
    layers = _audit()["historical_validation_layers"]

    core = layers["CORE_SIGNAL_VALIDATION"]
    assert core["status"] == "FROZEN_ENGINEERING_REPLAY_COMPLETE_NO_RETURN_METRICS"
    assert core["sector_score_status"] == "UNVERIFIED"
    assert core["sector_report_status"] == "UNVERIFIED"
    assert core["requires_historical_sina_membership"] is False
    assert core["claims_full_legacy_output_parity"] is False

    full = layers["FULL_LEGACY_OUTPUT_VALIDATION"]
    assert full["status"] == "BLOCKED_HISTORICAL_SINA_MEMBERSHIP"
    assert full["requires_historical_sina_membership"] is True
    assert full["sector_taxonomy"] == "新浪行业"
    assert full["claims_full_legacy_output_parity"] is True
    development = layers["DEVELOPMENT_HISTORICAL_RETURNS_VALIDATION"]
    assert development["status"] == "DEVELOPMENT_HISTORICAL_RETURNS_VALIDATION_COMPLETE"
    assert development["retrospective_status"] == "RECONSTRUCTED_RETROSPECTIVE"
    assert development["qualified_signal_count"] == 8463
    assert development["entry"] == "T+1 XSHG session open"
    assert development["score_85_status"] == "UNVERIFIED"
    assert development["full_legacy_output_validation"] == "BLOCKED_HISTORICAL_SINA_MEMBERSHIP"
    assert layers["decision_point"] == (
        "DEVELOPMENT_HISTORICAL_RETURNS_VALIDATION_COMPLETE_WHILE_FULL_PARITY_REMAINS_BLOCKED"
    )


def test_hithink_probe_records_deterministic_t_anchor_and_dump_fields():
    probe = _probe()

    assert probe["authentication"]["authenticated_http_200_code_0"] is True
    assert probe["authentication"]["key_value_logged"] is False
    assert probe["date_parameter_probes"]["sector_membership"]["items_semantic_equal"] is True
    assert probe["historical_probes"]["stock"]["all_dates_http_200_code_0"] is True
    assert probe["historical_probes"]["sector_index"]["all_dates_http_200_code_0"] is True
    assert probe["historical_probes"]["adjustment_events"]["latest_ex_dates_are_not_after_to"] is True

    dump = probe["market_dump_capability"]
    assert dump["adjustment_factors_probe_downloaded"] is True
    assert dump["presigned_urls_logged"] is False
    assert dump["adjustment_factors_probe_rows"] == 57010
    assert "allotment_ratio" in dump["adjustment_factors_probe_columns"]
    assert "allotment_price" in dump["adjustment_factors_probe_columns"]

    adjustment = probe["adjustment_t_anchor_probe"]
    assert adjustment["provider_forward_is_not_used_as_t_anchor"] is True
    assert adjustment["cash_only_rest_sample"]["max_provider_forward_absolute_error"] == 0.0
    assert adjustment["dump_allotment_sample"]["max_provider_forward_absolute_error"] == 0.0
    assert adjustment["dump_allotment_sample"]["all_anchor_identity_checks_passed"] is True
    assert adjustment["result"] == "DETERMINISTIC_T_ANCHOR_CONSTRUCTION_VERIFIED_ON_REAL_API_AND_DUMP_SAMPLES"


def test_phase2e_probe_and_audit_preserve_acquisition_boundary():
    audit = _audit()
    probe = _probe()

    assert probe["raw_payloads_archived"] is False
    assert probe["strategy_validation_run"] is False
    assert probe["final_oos_read"] is False
    assert probe["parameter_tuning_run"] is False
    assert all(source["content_sha256"] is None for source in audit["sources"])
    assert all(source["status"] != "READY_FOR_VALIDATION_DATASET_FREEZE" for source in audit["sources"])


def test_phase2e_audit_records_frozen_core_artifact_without_return_metrics():
    artifact = _audit()["core_signal_validation_artifact"]

    assert artifact["status"] == "FROZEN_ENGINEERING_REPLAY_COMPLETE_NO_RETURN_METRICS"
    assert artifact["manifest_sha256"] == "29c73d764de37b35e2ad3ce6fa61da6e18dddad53cf0037e76939c98e76ecdf0"
    assert artifact["results_sha256"] == "3c43a66b6e49cc654a9f141fabf841f9531c45e318826fe112a13915e0a963ea"
    assert artifact["projection_stream_sha256"] == "a599791eeed2d2338d5baacfbb4609c946dd37094b3eee0fa81c0c24dd594093"
    assert artifact["score_85_status"] == "UNVERIFIED"
    assert artifact["return_metrics_computed"] is False
