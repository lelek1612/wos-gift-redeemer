---
name: wos-gift-codes
description: Auto-redeem Whiteout Survival gift codes on a quiet cron.
version: 0.1.0
author: lelek1612, Hermes Agent
license: MIT
platforms: [linux, macos]
metadata:
  hermes:
    tags: [Games, Automation, Cron, Whiteout-Survival]
    related_skills: []
---

# Whiteout Survival Gift Codes

Redeems active gift codes for one Whiteout Survival account through the
publisher's public gift-code endpoint. Needs only the in-game **Player ID** and
**State** number: no password, no login, no browser. Pure Python stdlib. The
recurring job runs with `no_agent`, so it costs zero LLM tokens and messages you
only when something was redeemed or needs attention.

## When to Use

- User wants new Whiteout Survival gift codes redeemed, once or automatically.
- User asks whether a specific code works or why a code was missed.
- User wants the hourly or daily redeem job set up, checked, or repaired.

Don't use for: redeeming on accounts the user does not own, or any account that
needs a login.

## Prerequisites

- Python 3.10+ on the host.
- Player ID (digits under the nickname) and State number (the user's server).
- Network access to `whiteoutsurvival.dev` (code list) and
  `wos-giftcode-api.centurygame.com` (redeem endpoint).

## Setup

1. Ask the user for Player ID and State. Do not echo them back in chat.
2. `terminal`: create the config and lock it down.
   `mkdir -p ~/.config/wos-gift-redeemer && printf '{"playerId":"<ID>","state":"<STATE>"}' > ~/.config/wos-gift-redeemer/config.json && chmod 600 ~/.config/wos-gift-redeemer/config.json`
3. `terminal`: dry run, redeems nothing.
   `python3 <skill-dir>/scripts/redeemer.py --config ~/.config/wos-gift-redeemer/config.json --dry-run`
   Done when it prints the candidate code count, with no `wrong state` error.
4. Tell the user about the risk (see Risks) before the first real run.

## Run Once

`terminal`: `python3 <skill-dir>/scripts/redeemer.py --config ~/.config/wos-gift-redeemer/config.json --json`

- Extra code from the user: put it in a file, one per line, and add
  `--codes-file <file>`.
- `--retry-dead` retries codes earlier marked expired or exhausted.
- State (claimed and dead codes) lives in `~/.local/state/wos-gift-redeemer/`.

## Recurring Job (no LLM)

1. `terminal`: copy the wrapper into the profile scripts dir.
   `mkdir -p "$HERMES_HOME/scripts" && cp <skill-dir>/scripts/cron_report.py "$HERMES_HOME/scripts/wos-gift-hourly.py"`
2. `cronjob`: `action="create"`, `name="WoS gift codes"`, `schedule="every 1h"`,
   `script="wos-gift-hourly.py"`, `no_agent=True`, `deliver="origin"`,
   `prompt="redeem WoS gift codes"` (ignored in `no_agent` mode, but required).
3. `cronjob` `action="list"`: confirm `no_agent: true` and a `next_run_at`.

The wrapper prints nothing unless a code was redeemed or something needs
attention, and it does not repeat the same alert every run.

## Pitfalls

- `wrong state for this player ID` (API: `USER INFO ERROR`) means a wrong State,
  not a wrong code. Fix `state` in the config; do not retry the code.
- `claim limit reached` (`USED`) and `expired` mean the code is dead for
  everyone. They are stored as dead and skipped.
- `rate limited` (`TOO FREQUENT`): the script waits 60 s on its own. Keep
  `--delay` at 1 s or more.
- Code lists lag the game: a code can appear in the list hours after players
  see it. Hourly polling shortens the wait; it cannot remove it.
- The fallback scraper (`wosrewards.com`) only keeps tokens containing a digit,
  so it misses letter-only codes. The main API is the reliable source.
- Never put the config in a git repo. `config.json` is in `.gitignore` here.

## Risks

Gray area of the publisher's Terms of Service: the endpoint is public and used
by the official site, but automated use is not supported. Say this before the
first run and never promise that a ban is impossible. Do not use it to redeem
on other people's accounts.

## Verification

- `python3 tests/test_redeemer.py` passes (offline, in the repo).
- A real run prints `redeemed`, `already claimed`, or a dead-code reason for
  every candidate code.
- `cronjob` `action="list"` shows `last_status: ok` after the first scheduled
  run.

## Credits

Code list: whiteoutsurvival.dev (credit required for public use). Protocol
knowledge: justncodes/wos-giftcode and makorus/pyWoSRedemptionTool. Code
written from scratch.
