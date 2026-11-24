"""Dispatch the A-share close workflow from a VPS systemd timer."""

import argparse
import base64
import json
import os
import subprocess
from datetime import datetime
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

REPOSITORY = "EFSing/ashare_watchlist"
WORKFLOW = f"/repos/{REPOSITORY}/actions/workflows/daily_t_close.yml"
API_VERSION = "2026-03-10"


def base64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def installation_jwt(key: Path, app_id: str, now: datetime) -> str:
    header = base64url(b'{"alg":"RS256","typ":"JWT"}')
    issued_at = int(now.timestamp())
    claims = {"iss": app_id, "iat": issued_at - 60, "exp": issued_at + 180}
    payload = base64url(json.dumps(claims).encode("ascii"))
    message = f"{header}.{payload}"
    try:
        signature = subprocess.run(
            ["/usr/bin/openssl", "dgst", "-sha256", "-sign", str(key)],
            input=message.encode("ascii"),
            capture_output=True,
            check=True,
            timeout=5,
        ).stdout
    except (OSError, subprocess.SubprocessError):
        raise ValueError("GITHUB_APP_SIGNING_FAILED") from None
    return f"{message}.{base64url(signature)}"


def request_json(path: str, token: str, body: dict | None = None) -> dict:
    request = Request(
        f"https://api.github.com{path}",
        data=json.dumps(body).encode("ascii") if body is not None else None,
        headers={
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/json",
            "User-Agent": "ashare-tclose-vps-dispatcher",
            "X-GitHub-Api-Version": API_VERSION,
        },
    )
    request.add_unredirected_header("Authorization", f"Bearer {token}")
    try:
        with urlopen(request, timeout=15) as response:
            result = json.load(response)
    except HTTPError as error:
        raise ValueError(f"GITHUB_API_HTTP_{error.code} {request.get_method()} {path}") from None
    except (OSError, ValueError):
        raise ValueError(f"GITHUB_API_UNCONFIRMED {request.get_method()} {path}") from None
    if not isinstance(result, dict):
        raise ValueError(f"GITHUB_API_INVALID_RESPONSE {request.get_method()} {path}")
    return result


def scheduled_date(now: datetime) -> str | None:
    local = now.astimezone(ZoneInfo("Asia/Shanghai"))
    if local.weekday() >= 5 or local.hour != 17 or not 25 <= local.minute < 35:
        return None
    return local.date().isoformat()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Verify access without dispatching.")
    options = parser.parse_args()
    now = datetime.now(ZoneInfo("Asia/Shanghai"))
    as_of_date = scheduled_date(now)
    if not options.check and as_of_date is None:
        print("ASHARE_VPS_DISPATCH_SKIPPED_OUTSIDE_WINDOW")
        return

    try:
        key = Path(os.environ["CREDENTIALS_DIRECTORY"]) / "github-app-key"
        app_id = os.environ["ASHARE_GITHUB_APP_ID"]
        installation_id = int(os.environ["ASHARE_GITHUB_INSTALLATION_ID"])
        token_details = request_json(
            f"/app/installations/{installation_id}/access_tokens",
            installation_jwt(key, app_id, now),
            {"repositories": ["ashare_watchlist"], "permissions": {"actions": "write"}},
        )
        token = token_details.get("token")
        if not isinstance(token, str) or not token or any(c.isspace() for c in token):
            raise ValueError("GITHUB_APP_TOKEN_INVALID")
        if options.check:
            workflow = request_json(WORKFLOW, token)
            if workflow.get("state") != "active":
                raise ValueError("ASHARE_WORKFLOW_NOT_ACTIVE")
            print("ASHARE_VPS_GITHUB_APP_AUTH_OK")
            return

        result = request_json(f"{WORKFLOW}/dispatches", token, {
            "ref": "master",
            "inputs": {
                "mode": "production",
                "trigger_source": "external-scheduler",
                "as_of_date": as_of_date,
            },
        })
        run_id = result.get("workflow_run_id")
        if type(run_id) is not int or run_id <= 0:
            raise ValueError("GITHUB_DISPATCH_UNCONFIRMED_INVALID_RUN_ID")
    except (KeyError, ValueError) as error:
        raise SystemExit(str(error)) from None

    print(f"ASHARE_VPS_DISPATCHED {as_of_date} https://github.com/{REPOSITORY}/actions/runs/{run_id}")


if __name__ == "__main__":
    main()
