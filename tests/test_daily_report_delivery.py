from __future__ import annotations

import json
from datetime import datetime
from email import policy
from email.message import EmailMessage
from pathlib import Path

import pytest

import daily_report_delivery as delivery
from cloud_runtime_state import RuntimeStateError, validate_state_tree, _is_allowlisted_data_relative


DATE = "2026-09-14"
NOW = datetime.fromisoformat("2026-09-14T17:31:42+08:00")


def _env() -> dict[str, str]:
    return {
        "BARK_DEVICE_KEY": "bark-device-secret",
        "REPORT_EMAIL_TO": "recipient@example.com",
        "SMTP_HOST": "smtp.example.test",
        "SMTP_PORT": "587",
        "SMTP_USERNAME": "smtp-user",
        "SMTP_PASSWORD": "smtp-password-secret",
        "SMTP_FROM": "sender@example.com",
    }


def _success_result() -> dict:
    return {
        "status": "T_CLOSE_EVIDENCE_PACKAGE_AND_WATCHLIST_PERSISTED",
        "daily_close_bundle": {
            "status": "READY",
            "track_perf": {
                "status": "SUCCESS",
                "review_coverage": {"report_date": DATE, "status": "READY"},
            },
            "shadow_monitor": {"status": "COMPLETE"},
        },
    }


def _data_root(tmp_path: Path, *, candidate_count: int = 2) -> Path:
    root = tmp_path / "data"
    (root / "reports").mkdir(parents=True)
    candidates = [
        {"code": f"60051{i}", "name": f"测试股份{i}"}
        for i in range(candidate_count)
    ]
    (root / f"watchlist_{DATE.replace('-', '')}.json").write_text(
        json.dumps({"date": DATE, "candidates": candidates}, ensure_ascii=False),
        encoding="utf-8",
    )
    (root / "reports" / f"daily_close_{DATE.replace('-', '')}.html").write_text(
        "<html><body>dated report</body></html>\n", encoding="utf-8"
    )
    (root / "reports" / "latest.html").write_text(
        "<html><body>latest report</body></html>\n", encoding="utf-8"
    )
    return root


def _capture_transports(monkeypatch: pytest.MonkeyPatch, *, email_failures: int = 0, bark_failures: int = 0):
    email_messages: list[EmailMessage] = []
    bark_messages: list[tuple[str, str, str | None]] = []
    counts = {"email": 0, "bark": 0}

    def fake_email(message, _settings):
        counts["email"] += 1
        email_messages.append(message)
        if counts["email"] <= email_failures:
            raise RuntimeError("smtp transport failure")

    def fake_bark(*, settings, title, body, run_url):
        del settings
        counts["bark"] += 1
        bark_messages.append((title, body, run_url))
        if counts["bark"] <= bark_failures:
            raise RuntimeError("bark transport failure")

    monkeypatch.setattr(delivery, "send_email_message", fake_email)
    monkeypatch.setattr(delivery, "send_bark_notification", fake_bark)
    return counts, email_messages, bark_messages


def test_success_subject_uses_actual_bjt_send_time_and_dated_attachment(tmp_path):
    root = _data_root(tmp_path)
    context = delivery.load_report_context(root, DATE, result=_success_result())

    subject = delivery.success_subject(DATE, NOW, degraded=False)
    filename = delivery.success_attachment_filename(DATE)
    message = delivery.build_email_message(
        subject=subject,
        body=delivery.build_success_email_body(
            context,
            NOW,
            runtime_state_persisted="YES",
            run_url="https://github.com/EFSing/ashare_watchlist/actions/runs/123",
        ),
        recipient="recipient@example.com",
        sender="sender@example.com",
        attachment_path=context.report_path,
        attachment_filename=filename,
    )

    assert subject == "2026-09-14 17:31 - A股每日收盘复盘报告"
    assert "17:17" not in subject
    assert filename == "2026-09-14_A股每日收盘复盘报告.html"
    assert "完整复盘见附件：" in message.get_body(preferencelist=("plain",)).get_content()
    attachments = [part for part in message.walk() if part.get_content_disposition() == "attachment"]
    assert len(attachments) == 1
    assert attachments[0].get_filename() == filename
    assert attachments[0].get_payload(decode=True) == context.report_path.read_bytes()


def test_degraded_subject_and_body_identify_incomplete_channels(tmp_path):
    root = _data_root(tmp_path)
    result = {
        "daily_close_bundle": {
            "status": "REVIEW_OBSERVATION_INCOMPLETE_REPORT_READY",
            "track_perf": {
                "status": "SUCCESS",
                "review_coverage": {
                    "report_date": DATE,
                    "status": "REVIEW_OBSERVATION_INCOMPLETE",
                },
            },
            "shadow_monitor": {"status": "SHADOW_CAPTURE_INCOMPLETE"},
        }
    }
    context = delivery.load_report_context(root, DATE, result=result)

    assert delivery.success_subject(DATE, NOW, degraded=True) == (
        "2026-09-14 17:31 - A股每日收盘复盘报告 - 数据不完整"
    )
    body = delivery.build_success_email_body(
        context, NOW, runtime_state_persisted="YES", run_url=None
    )
    assert "运行状态：DEGRADED" in body
    assert "Review=REVIEW_OBSERVATION_INCOMPLETE" in body
    assert "Shadow=SHADOW_CAPTURE_INCOMPLETE" in body
    assert delivery.bark_title(DATE, NOW, degraded=False) == "17:31 - A股每日收盘复盘完成"
    assert delivery.bark_title(DATE, NOW, degraded=True) == "17:31 - A股每日复盘完成（数据不完整）"


def test_failure_email_has_no_attachment_even_when_stale_reports_exist(tmp_path, monkeypatch):
    root = _data_root(tmp_path)
    _counts, messages, _bark = _capture_transports(monkeypatch)

    result = delivery.send_failure_notification(
        DATE,
        failure_stage="production",
        error_summary="T_CLOSE_RUN_FAILED",
        run_url="https://github.com/EFSing/ashare_watchlist/actions/runs/456",
        env=_env(),
        now_bjt=NOW,
        sleep_fn=lambda _seconds: None,
    )

    assert result["status"] == "FAILURE_NOTIFICATION_SENT"
    assert messages
    for message in messages:
        assert not [part for part in message.walk() if part.get_content_disposition() == "attachment"]
        assert "未附加任何 HTML" in message.get_body(preferencelist=("plain",)).get_content()
    assert (root / "reports" / "latest.html").is_file()


def test_failure_subject_and_bark_title_are_bjt_and_secret_free(monkeypatch):
    counts, messages, bark = _capture_transports(monkeypatch)
    result = delivery.send_failure_notification(
        DATE,
        failure_stage="cloud-preflight",
        error_summary="SCHEDULED_TASK_CREDENTIAL_CONTEXT_NOT_READY",
        run_url="https://github.com/EFSing/ashare_watchlist/actions/runs/789",
        env=_env(),
        now_bjt=NOW,
        sleep_fn=lambda _seconds: None,
    )

    assert result["status"] == "FAILURE_NOTIFICATION_SENT"
    assert counts == {"email": 1, "bark": 1}
    assert messages[0]["Subject"] == "2026-09-14 17:31 - A股云端运行失败"
    assert bark[0][0] == "17:31 - A股云端运行失败"
    assert "bark-device-secret" not in json.dumps(result, ensure_ascii=False)
    assert "smtp-password-secret" not in json.dumps(result, ensure_ascii=False)


def test_failure_message_redacts_secret_if_transport_input_contains_one(monkeypatch):
    _counts, messages, bark = _capture_transports(monkeypatch)
    secret = "smtp-password-secret"
    env = _env()

    delivery.send_failure_notification(
        DATE,
        failure_stage="production",
        error_summary=secret,
        run_url=None,
        env=env,
        now_bjt=NOW,
        sleep_fn=lambda _seconds: None,
    )

    assert secret not in messages[0].get_body(preferencelist=("plain",)).get_content()
    assert secret not in bark[0][1]


def test_chinese_mime_subject_and_attachment_filename_are_rfc_encoded(tmp_path):
    root = _data_root(tmp_path)
    message = delivery.build_email_message(
        subject="2026-09-14 17:31 - A股每日收盘复盘报告",
        body="通知正文\n",
        recipient="recipient@example.com",
        sender="sender@example.com",
        attachment_path=root / "reports" / "latest.html",
        attachment_filename="2026-09-14_A股每日收盘复盘报告.html",
    )

    raw = message.as_bytes(policy=policy.SMTP)
    assert b"=?utf-8?" in raw.lower()
    assert "A股每日收盘复盘报告" in str(message["Subject"])
    attachment = next(part for part in message.walk() if part.get_content_disposition() == "attachment")
    assert attachment.get_filename() == "2026-09-14_A股每日收盘复盘报告.html"


def test_smtp_465_uses_implicit_ssl_without_starttls(monkeypatch):
    calls: list[tuple[str, object]] = []

    class FakeSMTP:
        def __init__(self, *args, **kwargs):
            calls.append(("init", (args, kwargs)))

        def login(self, username, password):
            calls.append(("login", (username, password)))

        def send_message(self, message):
            calls.append(("send", message))

        def quit(self):
            calls.append(("quit", None))

    monkeypatch.setattr(delivery.smtplib, "SMTP_SSL", FakeSMTP)
    settings = delivery._channel_settings("email", {**_env(), "SMTP_PORT": "465"})
    message = delivery.build_email_message(
        subject="测试",
        body="body",
        recipient=settings.report_email_to,
        sender=settings.smtp_from,
    )

    delivery.send_email_message(message, settings)

    assert calls[0][0] == "init"
    assert calls[0][1][0][1] == 465
    assert "context" in calls[0][1][1]
    assert [name for name, _value in calls].count("login") == 1
    assert not any(name == "starttls" for name, _value in calls)


def test_smtp_other_ports_use_starttls(monkeypatch):
    calls: list[str] = []

    class FakeSMTP:
        def __init__(self, *args, **kwargs):
            calls.append("init")

        def ehlo(self):
            calls.append("ehlo")

        def starttls(self, *, context):
            assert context is not None
            calls.append("starttls")

        def login(self, _username, _password):
            calls.append("login")

        def send_message(self, _message):
            calls.append("send")

        def quit(self):
            calls.append("quit")

    monkeypatch.setattr(delivery.smtplib, "SMTP", FakeSMTP)
    settings = delivery._channel_settings("email", _env())
    message = delivery.build_email_message(
        subject="测试", body="body", recipient=settings.report_email_to, sender=settings.smtp_from
    )

    delivery.send_email_message(message, settings)

    assert calls == ["init", "ehlo", "starttls", "ehlo", "login", "send", "quit"]


def test_bark_uses_current_json_push_endpoint_without_critical_level(monkeypatch):
    seen: dict[str, object] = {}

    class Response:
        def getcode(self):
            return 200

        def read(self):
            return b'{"code":200,"message":"success"}'

        def close(self):
            seen["closed"] = True

    def fake_urlopen(request, timeout):
        seen["url"] = request.full_url
        seen["timeout"] = timeout
        seen["payload"] = json.loads(request.data.decode("utf-8"))
        return Response()

    monkeypatch.setattr(delivery, "urlopen", fake_urlopen)
    settings = delivery._channel_settings("bark", _env())

    delivery.send_bark_notification(
        settings=settings,
        title="17:31 - A股每日收盘复盘完成",
        body="日期 2026-09-14\n候选数量 2\nReview READY\nShadow COMPLETE\nruntime-state persisted YES",
        run_url="https://github.com/EFSing/ashare_watchlist/actions/runs/123",
    )

    assert seen["url"] == "https://api.day.app/push"
    payload = seen["payload"]
    assert payload["device_key"] == "bark-device-secret"
    assert "bark-device-secret" not in seen["url"]
    assert payload["url"].endswith("/123")
    assert "level" not in payload
    assert seen["closed"] is True


def test_delivery_success_creates_sha_bound_receipt(tmp_path, monkeypatch):
    root = _data_root(tmp_path)
    counts, _messages, _bark = _capture_transports(monkeypatch)

    result = delivery.deliver_production(
        root,
        DATE,
        result=_success_result(),
        env=_env(),
        now_bjt=NOW,
        sleep_fn=lambda _seconds: None,
    )

    receipt = delivery.load_delivery_receipt(root, DATE)
    assert result["status"] == delivery.DELIVERY_SUCCESS
    assert counts == {"email": 1, "bark": 1}
    assert receipt is not None
    assert receipt["schema_version"] == delivery.RECEIPT_SCHEMA_VERSION
    assert receipt["report_sha256"] == delivery.file_sha256(root / "reports" / "daily_close_20260914.html")
    assert receipt["candidate_count"] == 2
    assert receipt["email_status"] == "SUCCESS"
    assert receipt["bark_status"] == "SUCCESS"
    assert receipt["email_sent_at_bjt"].startswith("2026-09-14T17:31:42+08:00")


def test_same_report_with_two_successful_channels_is_already_delivered(tmp_path, monkeypatch):
    root = _data_root(tmp_path)
    counts, _messages, _bark = _capture_transports(monkeypatch)
    delivery.deliver_production(root, DATE, result=_success_result(), env=_env(), now_bjt=NOW, sleep_fn=lambda _seconds: None)
    counts["email"] = 0
    counts["bark"] = 0

    result = delivery.deliver_production(
        root, DATE, result=_success_result(), env=_env(), now_bjt=NOW, sleep_fn=lambda _seconds: None
    )

    assert result["status"] == delivery.ALREADY_DELIVERED
    assert counts == {"email": 0, "bark": 0}
    assert result["attempted_channels"] == []


@pytest.mark.parametrize(
    ("first_email_failures", "first_bark_failures", "expected_retry"),
    [(0, 3, "bark"), (3, 0, "email")],
)
def test_next_run_retries_only_failed_channel(
    tmp_path,
    monkeypatch,
    first_email_failures,
    first_bark_failures,
    expected_retry,
):
    root = _data_root(tmp_path)
    first_counts, _messages, _bark = _capture_transports(
        monkeypatch,
        email_failures=first_email_failures,
        bark_failures=first_bark_failures,
    )
    first = delivery.deliver_production(
        root, DATE, result=_success_result(), env=_env(), now_bjt=NOW, sleep_fn=lambda _seconds: None
    )
    assert first["status"] == delivery.DELIVERY_DEGRADED
    assert first_counts[expected_retry] == 3

    second_counts, _messages, _bark = _capture_transports(monkeypatch)
    second = delivery.deliver_production(
        root, DATE, result=_success_result(), env=_env(), now_bjt=NOW, sleep_fn=lambda _seconds: None
    )

    assert second["status"] == delivery.DELIVERY_SUCCESS
    assert second["attempted_channels"] == [expected_retry]
    other = "bark" if expected_retry == "email" else "email"
    assert second_counts[expected_retry] == 1
    assert second_counts[other] == 0


def test_channel_retry_is_bounded_to_three_attempts(tmp_path, monkeypatch):
    root = _data_root(tmp_path)
    counts, _messages, _bark = _capture_transports(monkeypatch, email_failures=99)
    sleeps: list[float] = []

    result = delivery.deliver_production(
        root,
        DATE,
        result=_success_result(),
        env=_env(),
        now_bjt=NOW,
        sleep_fn=sleeps.append,
    )

    assert result["status"] == delivery.DELIVERY_DEGRADED
    assert counts["email"] == 3
    assert counts["bark"] == 1
    assert len(sleeps) == 2


def test_channel_retry_cannot_exceed_three_attempts_when_requested(tmp_path, monkeypatch):
    root = _data_root(tmp_path)
    counts, _messages, _bark = _capture_transports(monkeypatch, email_failures=99)

    result = delivery.deliver_production(
        root,
        DATE,
        result=_success_result(),
        env=_env(),
        now_bjt=NOW,
        max_attempts=99,
        sleep_fn=lambda _seconds: None,
    )

    assert result["status"] == delivery.DELIVERY_DEGRADED
    assert counts["email"] == 3
    assert counts["bark"] == 1


def test_receipt_report_sha_mismatch_fails_closed_without_sending(tmp_path, monkeypatch):
    root = _data_root(tmp_path)
    _capture_transports(monkeypatch)
    delivery.deliver_production(root, DATE, result=_success_result(), env=_env(), now_bjt=NOW, sleep_fn=lambda _seconds: None)
    (root / "reports" / "daily_close_20260914.html").write_text("changed\n", encoding="utf-8")
    counts, _messages, _bark = _capture_transports(monkeypatch)

    with pytest.raises(delivery.DeliveryReceiptIdentityConflict, match="DELIVERY_RECEIPT_REPORT_IDENTITY_CONFLICT"):
        delivery.deliver_production(root, DATE, result=_success_result(), env=_env(), now_bjt=NOW, sleep_fn=lambda _seconds: None)
    assert counts == {"email": 0, "bark": 0}


def test_production_missing_delivery_secrets_is_not_configured_but_receipt_is_safe(tmp_path, monkeypatch):
    root = _data_root(tmp_path)
    counts, _messages, _bark = _capture_transports(monkeypatch)
    env = {"SMTP_PORT": "587"}

    result = delivery.deliver_production(
        root, DATE, result=_success_result(), env=env, now_bjt=NOW, sleep_fn=lambda _seconds: None
    )

    receipt = delivery.load_delivery_receipt(root, DATE)
    assert result["status"] == delivery.DELIVERY_FAILED
    assert result["email_status"] == "NOT_CONFIGURED"
    assert result["bark_status"] == "NOT_CONFIGURED"
    assert counts == {"email": 0, "bark": 0}
    assert receipt["email_status"] == "NOT_CONFIGURED"
    assert receipt["bark_status"] == "NOT_CONFIGURED"
    assert "REPORT_EMAIL_TO" not in delivery.delivery_receipt_path(root, DATE).read_text(encoding="utf-8")


def test_success_delivery_never_falls_back_to_latest_when_dated_report_is_missing(tmp_path):
    root = _data_root(tmp_path)
    (root / "reports" / "daily_close_20260914.html").unlink()

    with pytest.raises(delivery.DeliveryError, match="REPORT_NOT_READY"):
        delivery.deliver_production(root, DATE, result=_success_result(), env=_env(), now_bjt=NOW)


def test_secrets_never_enter_delivery_result_or_receipt(tmp_path, monkeypatch):
    root = _data_root(tmp_path)

    def fail_email(_message, _settings):
        raise RuntimeError("password=smtp-password-secret")

    def fail_bark(**_kwargs):
        raise RuntimeError("key=bark-device-secret")

    monkeypatch.setattr(delivery, "send_email_message", fail_email)
    monkeypatch.setattr(delivery, "send_bark_notification", fail_bark)
    result = delivery.deliver_production(
        root, DATE, result=_success_result(), env=_env(), now_bjt=NOW, sleep_fn=lambda _seconds: None
    )
    serialized = json.dumps(result, ensure_ascii=False)
    receipt_text = delivery.delivery_receipt_path(root, DATE).read_text(encoding="utf-8")

    assert "smtp-password-secret" not in serialized
    assert "bark-device-secret" not in serialized
    assert "smtp-password-secret" not in receipt_text
    assert "bark-device-secret" not in receipt_text


def test_delivery_test_attaches_latest_without_receipt_or_state_mutation(tmp_path, monkeypatch):
    root = _data_root(tmp_path)
    before = {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file()
    }
    counts, messages, _bark = _capture_transports(monkeypatch)

    result = delivery.send_delivery_test(
        root,
        DATE,
        run_url="https://github.com/EFSing/ashare_watchlist/actions/runs/999",
        env=_env(),
        now_bjt=NOW,
        sleep_fn=lambda _seconds: None,
    )

    after = {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file()
    }
    assert result["status"] == delivery.REPORT_DELIVERY_CHANNELS_VERIFIED
    assert result["attachment_filename"] == "TEST_2026-09-14_A股每日收盘复盘报告.html"
    assert result["runtime_state_mutation"] == "NO"
    assert result["market_data_provider_calls"] == 0
    assert counts == {"email": 1, "bark": 1}
    assert before == after
    attachment = next(part for part in messages[0].walk() if part.get_content_disposition() == "attachment")
    assert attachment.get_filename() == "TEST_2026-09-14_A股每日收盘复盘报告.html"
    assert attachment.get_payload(decode=True) == (root / "reports" / "latest.html").read_bytes()


def test_delivery_test_requires_all_six_secret_names_without_values(tmp_path):
    root = _data_root(tmp_path)
    env = _env()
    env.pop("BARK_DEVICE_KEY")
    env.pop("SMTP_PASSWORD")

    with pytest.raises(delivery.SecretsRequired) as exc_info:
        delivery.send_delivery_test(root, DATE, env=env, now_bjt=NOW)

    assert exc_info.value.code == delivery.REPORT_DELIVERY_SECRETS_REQUIRED
    assert list(exc_info.value.missing) == ["BARK_DEVICE_KEY", "SMTP_PASSWORD"]
    assert "bark-device-secret" not in str(exc_info.value)
    assert "smtp-password-secret" not in str(exc_info.value)


def test_runtime_state_allowlist_accepts_only_dated_delivery_receipts(tmp_path):
    assert _is_allowlisted_data_relative(Path("delivery/daily_delivery_20260914.json"))
    assert not _is_allowlisted_data_relative(Path("delivery/daily_delivery_latest.json"))
    assert not _is_allowlisted_data_relative(Path("delivery/archive/daily_delivery_20260914.json"))
    assert not _is_allowlisted_data_relative(Path("delivery/secret.txt"))

    state_root = tmp_path / "runtime-state"
    state_root.mkdir()
    (state_root / "RUNTIME_STATE.md").write_text(
        "GITHUB_ACTIONS_DAILY_RUNTIME_V1\noperational state only\nnever merge into master\n"
        "cloud workflow is the normal single writer\nno secrets\nno raw market evidence\n",
        encoding="utf-8",
    )
    (state_root / "data" / "delivery").mkdir(parents=True)
    (state_root / "data" / "delivery" / "daily_delivery_latest.json").write_text("{}", encoding="utf-8")

    with pytest.raises(RuntimeStateError, match="non-allowlisted"):
        validate_state_tree(state_root)

    valid_state = tmp_path / "valid-runtime-state"
    valid_state.mkdir()
    (valid_state / "RUNTIME_STATE.md").write_text(
        (state_root / "RUNTIME_STATE.md").read_text(encoding="utf-8"), encoding="utf-8"
    )
    (valid_state / "data" / "delivery").mkdir(parents=True)
    (valid_state / "data" / "delivery" / "daily_delivery_20260914.json").write_text(
        "{}", encoding="utf-8"
    )
    assert "data/delivery/daily_delivery_20260914.json" in validate_state_tree(valid_state)["files"]


def test_workflow_keeps_schedule_and_xshg_gate_while_adding_delivery_test():
    workflow = (Path(__file__).resolve().parents[1] / ".github" / "workflows" / "daily_t_close.yml").read_text(encoding="utf-8")

    assert 'cron: "17 9 * * 1-5"' in workflow
    assert 'cron: "17 10 * * 1-5"' in workflow
    assert "- delivery-test" in workflow
    assert "ref: runtime-state" in workflow
    assert "Check same-day completion before provider calls" in workflow
    assert "ALREADY_COMPLETED" in workflow
    assert "git add ." not in workflow
    assert "git add -A" not in workflow
    assert "HITHINK_FINANCE_API_KEY" in workflow
    assert "DAILY_REPORT_DELIVERY_RECEIPT_V1" not in workflow
