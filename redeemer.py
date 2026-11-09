#!/usr/bin/env python3
"""Whiteout Survival gift-code auto-redeemer (zero dependencies, stdlib only).

Redeems the active gift codes for one player account. It only needs the public
Player ID and the State number - never an account login or password.

Protocol: Century Games' public gift-code web client signs a form post to
https://wos-giftcode-api.centurygame.com/api/gift_code with
sign = md5(<sorted key=value pairs joined by &> + shared client key).
That is the whole mechanism; everything else here is hygiene (dedupe, state
file, rate limits, readable exit codes).

Usage:
    ./redeemer.py --player-id 12345678 --state 4351
    ./redeemer.py --player-id 12345678 --state 4351 --dry-run
    ./redeemer.py --config config.json

Exit codes: 0 everything attempted (see summary), 2 bad usage, 3 network down.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

SECRET = "tB87#kPtkxqOS2"  # public client key used by the game's own web page
API_URL = "https://wos-giftcode-api.centurygame.com/api/gift_code"
ORIGIN = "https://wos-giftcode.centurygame.com"
CODES_API = "https://whiteoutsurvival.dev/api/gift-codes"
CODES_SCRAPE = "https://www.wosrewards.com"

DEFAULT_DELAY = 2.0      # seconds between two codes for the same player
MAX_ATTEMPTS = 3
RATE_LIMIT_SLEEP = 60
STATE_DIR = Path.home() / ".local" / "state" / "wos-gift-redeemer"

SUCCESS = {"SUCCESS", "SAME TYPE EXCHANGE"}
ALREADY = {"RECEIVED"}
# Codes are dead for everyone: no point retrying them ever again.
FATAL = {"TIME ERROR", "CDK NOT FOUND", "USED"}

MESSAGES = {
    "SUCCESS": "redeemed",
    "SAME TYPE EXCHANGE": "redeemed (same type)",
    "RECEIVED": "already claimed",
    "TIME ERROR": "expired",
    "CDK NOT FOUND": "code not found",
    "USED": "claim limit reached",
    "TIMEOUT RETRY": "server asked for retry",
    "TOO FREQUENT": "rate limited",
    "USER INFO ERROR": "wrong state for this player ID",
    "ROLE NOT EXIST": "no such player",
    "STOVE_LV ERROR": "furnace level too low",
    "RECHARGE_MONEY ERROR": "not enough spending for this code",
    "RECHARGE_MONEY_VIP ERROR": "VIP level too low",
    "SIGN ERROR": "signature rejected",
    "NOT LOGIN": "session rejected",
}
# Statuses worth another attempt in the same run.
TRANSIENT = {"TIMEOUT RETRY"}


def log(msg: str) -> None:
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"{ts}  {msg}", flush=True)


def sign(payload: dict) -> str:
    """md5 over sorted key=value pairs plus the client key, exactly as the web client does."""
    encoded = "&".join(f"{k}={payload[k]}" for k in sorted(payload))
    return hashlib.md5((encoded + SECRET).encode()).hexdigest()


def http_post(url: str, payload: dict, timeout: int = 25) -> dict | None:
    body = urllib.parse.urlencode({**payload, "sign": sign(payload)}).encode()
    req = urllib.request.Request(
        url,
        data=body,
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json, text/plain, */*",
            "Origin": ORIGIN,
            "Referer": ORIGIN + "/",
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                f"(KHTML, like Gecko) Chrome/{random.randint(124, 136)}.0.0.0 Safari/537.36"
            ),
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode() or "{}")
    except urllib.error.HTTPError as exc:
        detail = exc.read()[:200].decode(errors="replace")
        log(f"HTTP {exc.code} from API: {detail}")
    except Exception as exc:  # noqa: BLE001 - transport problems are reported, not raised
        log(f"transport error: {exc}")
    return None


def classify(response: dict) -> str:
    """Map the API's (msg, err_code) pair onto a stable status key."""
    msg = str(response.get("msg", "")).strip().rstrip(".").strip()
    err = response.get("err_code")
    for key, code in (
        ("TIME ERROR", 40007),
        ("CDK NOT FOUND", 40014),
        ("USED", 40005),
        ("TIMEOUT RETRY", 40004),
        ("TOO FREQUENT", 40019),
        ("USER INFO ERROR", 40020),
        ("STOVE_LV ERROR", 40006),
        ("RECHARGE_MONEY ERROR", 40017),
        ("RECHARGE_MONEY_VIP ERROR", 40018),
    ):
        if msg == key and err == code:
            return key
    if err == 40001 and "not exist" in msg.lower():
        return "ROLE NOT EXIST"
    if "sign error" in msg.lower():
        return "SIGN ERROR"
    if msg == "NOT LOGIN":
        return "NOT LOGIN"
    return msg or "UNKNOWN"


def redeem(player_id: str, state: str, code: str) -> str:
    """Redeem one code for one player. Returns a status key."""
    payload = {
        "fid": str(player_id),
        "kid": str(state),
        "cdk": code,
        "time": str(int(time.time())),
    }
    for attempt in range(1, MAX_ATTEMPTS + 1):
        response = http_post(API_URL, payload)
        if response is None:
            if attempt == MAX_ATTEMPTS:
                return "NETWORK ERROR"
            time.sleep(2 * attempt)
            continue
        status = classify(response)
        if status == "TOO FREQUENT" and attempt < MAX_ATTEMPTS:
            log(f"{code}: rate limited, waiting {RATE_LIMIT_SLEEP}s")
            time.sleep(RATE_LIMIT_SLEEP)
            continue
        if status in TRANSIENT and attempt < MAX_ATTEMPTS:
            time.sleep(2 * attempt)
            continue
        return status
    return "UNKNOWN"


def fetch_codes_from_api() -> list[str]:
    try:
        req = urllib.request.Request(CODES_API, headers={"User-Agent": "wos-gift-redeemer"})
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read().decode())
    except Exception as exc:  # noqa: BLE001
        log(f"code source whiteoutsurvival.dev failed: {exc}")
        return []
    return [c["code"].strip() for c in data.get("codes", []) if c.get("isActive") and c.get("code")]


def fetch_codes_from_scrape() -> list[str]:
    """Fallback: pull uppercase code-looking tokens from the wosrewards page."""
    import re

    try:
        req = urllib.request.Request(
            CODES_SCRAPE,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"},
        )
        with urllib.request.urlopen(req, timeout=20) as resp:
            html = resp.read().decode(errors="ignore")
    except Exception as exc:  # noqa: BLE001
        log(f"code source wosrewards.com failed: {exc}")
        return []
    tokens = re.findall(r">([A-Za-z0-9]{6,20})<", html)
    return [t for t in dict.fromkeys(tokens) if any(ch.isdigit() for ch in t) and t.isalnum()]


def collect_codes(local_file: Path | None) -> list[str]:
    codes: list[str] = []
    for getter in (fetch_codes_from_api, fetch_codes_from_scrape):
        codes.extend(getter())
    if local_file and local_file.exists():
        codes.extend(
            line.strip()
            for line in local_file.read_text().splitlines()
            if line.strip() and not line.startswith("#")
        )
    seen: dict[str, None] = {}
    for code in codes:
        seen.setdefault(code, None)
    return list(seen)


def load_state(path: Path) -> dict:
    if path.exists():
        try:
            return json.loads(path.read_text())
        except json.JSONDecodeError:
            log(f"state file {path} unreadable, starting fresh")
    return {"claimed": {}, "dead": []}


def save_state(path: Path, state: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2, sort_keys=True))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--player-id", help="in-game Player ID (digits under your name)")
    parser.add_argument("--state", help="State number your city is in (required by the API)")
    parser.add_argument("--config", type=Path, help="JSON file with playerId/state/stateFile")
    parser.add_argument("--codes-file", type=Path, help="extra codes, one per line")
    parser.add_argument("--retry-dead", action="store_true", help="retry codes previously marked dead")
    parser.add_argument("--dry-run", action="store_true", help="fetch and print, redeem nothing")
    parser.add_argument("--delay", type=float, default=DEFAULT_DELAY, help="seconds between codes")
    parser.add_argument("--json", action="store_true", help="machine-readable summary on stdout")
    args = parser.parse_args(argv)

    config: dict = {}
    if args.config:
        config = json.loads(args.config.read_text())
    player_id = str(args.player_id or config.get("playerId") or "").strip()
    state = str(args.state or config.get("state") or "").strip()
    if not player_id.isdigit() or not state.isdigit():
        parser.error("--player-id and --state are required (digits only)")

    state_path = Path(config.get("stateFile") or STATE_DIR / f"state-{player_id}.json")
    saved = load_state(state_path)
    claimed = set(saved.get("claimed", {}).get(player_id, []))
    dead = set(saved.get("dead", [])) if not args.retry_dead else set()

    codes = [c for c in collect_codes(args.codes_file) if c not in claimed and c not in dead]
    log(f"{len(codes)} candidate code(s) for player {player_id} (state {state})")

    if args.dry_run:
        for code in codes:
            print(code)
        return 0

    results: dict[str, str] = {}
    for index, code in enumerate(codes, 1):
        status = redeem(player_id, state, code)
        results[code] = status
        label = MESSAGES.get(status, status)
        log(f"[{index}/{len(codes)}] {code}: {label}")
        if status in SUCCESS or status in ALREADY:
            claimed.add(code)
        elif status in FATAL:
            dead.add(code)
        if index < len(codes):
            time.sleep(args.delay)

    saved.setdefault("claimed", {})[player_id] = sorted(claimed)
    saved["dead"] = sorted(dead)
    saved["lastRun"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    save_state(state_path, saved)

    summary = {
        "playerId": player_id,
        "state": state,
        "checked": len(codes),
        "redeemed": sorted(c for c, s in results.items() if s in SUCCESS),
        "alreadyClaimed": sorted(c for c, s in results.items() if s in ALREADY),
        "failed": {c: MESSAGES.get(s, s) for c, s in results.items() if s not in SUCCESS | ALREADY},
    }
    if args.json:
        print(json.dumps(summary, indent=2))
    else:
        log(
            f"done: {len(summary['redeemed'])} redeemed, "
            f"{len(summary['alreadyClaimed'])} already, {len(summary['failed'])} failed/expired"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
