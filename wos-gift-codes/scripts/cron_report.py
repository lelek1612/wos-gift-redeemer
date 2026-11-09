#!/usr/bin/env python3
"""Quiet wrapper around redeemer.py for Hermes cron `no_agent` mode.

No LLM is involved: the Hermes scheduler runs this script and posts its stdout.
Empty stdout = nothing is sent. It speaks up only when:
  - at least one code was redeemed, or
  - something needs attention (wrong state, unknown player, rejected signature,
    network down, missing config). The same alert is not repeated every run.

Config:  $WOS_CONFIG or ~/.config/wos-gift-redeemer/config.json
         ({"playerId": "...", "state": "..."})
Locates redeemer.py via $WOS_REDEEMER, next to this file, or inside the
Hermes skills tree (<hermes-home>/skills/**/wos-gift-codes/scripts/).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

CONFIG = Path(os.environ.get("WOS_CONFIG") or Path.home() / ".config" / "wos-gift-redeemer" / "config.json")
ALERT_FILE = CONFIG.parent / "last_alert.txt"
ATTENTION = {
    "wrong state for this player ID",
    "no such player",
    "signature rejected",
    "session rejected",
    "NETWORK ERROR",
}


def find_redeemer() -> Path | None:
    here = Path(__file__).resolve()
    candidates: list[Path] = []
    if os.environ.get("WOS_REDEEMER"):
        candidates.append(Path(os.environ["WOS_REDEEMER"]))
    candidates.append(here.with_name("redeemer.py"))
    roots = [here.parent.parent]  # <hermes-home>/scripts/this.py -> <hermes-home>
    if os.environ.get("HERMES_HOME"):
        roots.insert(0, Path(os.environ["HERMES_HOME"]))
    for root in roots:
        candidates.extend(sorted(root.glob("skills/**/wos-gift-codes/scripts/redeemer.py")))
    return next((c for c in candidates if c.is_file()), None)


def emit(alert: str) -> None:
    """Print an alert once; stay silent while the same alert persists."""
    previous = ALERT_FILE.read_text() if ALERT_FILE.exists() else ""
    if alert != previous:
        ALERT_FILE.parent.mkdir(parents=True, exist_ok=True)
        ALERT_FILE.write_text(alert)
        print(alert)


def clear_alert() -> None:
    if ALERT_FILE.exists():
        ALERT_FILE.unlink()


def main() -> int:
    if not CONFIG.exists():
        emit(f"⚠️ WoS gift codes: config not found ({CONFIG}). Create it with playerId and state.")
        return 0
    redeemer = find_redeemer()
    if redeemer is None:
        emit("⚠️ WoS gift codes: redeemer.py not found (reinstall the wos-gift-codes skill).")
        return 0

    try:
        run = subprocess.run(
            [sys.executable, str(redeemer), "--config", str(CONFIG), "--json"],
            capture_output=True,
            text=True,
            timeout=600,
        )
    except subprocess.TimeoutExpired:
        emit("⚠️ WoS gift codes: run exceeded 10 min.")
        return 0

    try:
        summary = json.loads(run.stdout)
    except json.JSONDecodeError:
        tail = "\n".join((run.stderr or run.stdout).strip().splitlines()[-3:])
        emit(f"⚠️ WoS gift codes: no summary (exit {run.returncode}).\n{tail}")
        return 0

    redeemed = summary.get("redeemed") or []
    failed = summary.get("failed") or {}
    attention = {c: r for c, r in failed.items() if r in ATTENTION}

    if redeemed:
        print("🎁 WoS: redeemed codes: " + ", ".join(redeemed))
    if attention:
        emit("⚠️ WoS gift codes need attention: " + "; ".join(f"{c}: {r}" for c, r in attention.items()))
    else:
        clear_alert()
    return 0


if __name__ == "__main__":
    sys.exit(main())
