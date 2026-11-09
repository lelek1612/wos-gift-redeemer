# WoS Gift Redeemer

Automatic gift-code redeeming for **Whiteout Survival**. No login, no password,
no game bot. Also packaged as a [Hermes Agent](https://hermes-agent.nousresearch.com/)
skill that runs hourly with zero LLM tokens.

You need two numbers: your **Player ID** (digits under your nickname in game)
and your **State** number. The script fetches active codes and sends them to the
endpoint used by the official gift-code site.

## How it works

1. `GET https://whiteoutsurvival.dev/api/gift-codes` returns the active codes
   (plus a scrape fallback and an optional local codes file).
2. For each new code: `POST https://wos-giftcode-api.centurygame.com/api/gift_code`
   with `fid` (Player ID), `kid` (State), `cdk` (code), `time` and an `md5`
   signature.
3. The result goes to a state file (`redeemed`, `already claimed`, `expired`,
   `wrong state`). Codes already claimed or dead are not retried.

Python 3.10+, standard library only.

## Layout

```
wos-gift-codes/            <- the Hermes skill (self-contained)
  SKILL.md
  scripts/redeemer.py      <- the CLI
  scripts/cron_report.py   <- quiet wrapper for Hermes cron (no_agent)
tests/test_redeemer.py     <- offline tests
```

## Usage (plain CLI)

```bash
python3 wos-gift-codes/scripts/redeemer.py --player-id 12345678 --state 1234
python3 wos-gift-codes/scripts/redeemer.py --player-id 12345678 --state 1234 --dry-run
python3 wos-gift-codes/scripts/redeemer.py --config config.json --json
```

`config.json` (never commit it, it is in `.gitignore`):

```json
{ "playerId": "12345678", "state": "1234" }
```

Plain cron, hourly:

```cron
0 * * * * python3 /path/to/wos-gift-codes/scripts/redeemer.py --config /path/to/config.json
```

Logs go to stderr; stdout carries only `--json` output or `--dry-run` codes.

## Hermes skill

Install the skill, then ask your agent to set up the gift-code job. The skill
creates a `no_agent` cron job that runs `cron_report.py` every hour. It prints
nothing unless a code was redeemed or something needs attention, and it does not
repeat the same alert.

```bash
hermes skills install <owner>/wos-gift-redeemer/wos-gift-codes
```

## Statuses

| Status | Meaning |
| --- | --- |
| `redeemed` | code redeemed |
| `already claimed` | already redeemed on this account |
| `expired` | code expired |
| `claim limit reached` | global limit of the code used up |
| `wrong state for this player ID` | wrong State, fix `state` |
| `rate limited` | API asked for a pause; script waits 60 s and retries once |
| `no such player` | Player ID does not exist |

## Known limits

- Code lists lag the game. A new code can show up hours after players see it.
- The fallback scraper (`wosrewards.com`) only keeps tokens with a digit, so it
  misses letter-only codes. The main API is the reliable source.

## Disclaimer

- This is a **gray area of the publisher's Terms of Service**. The endpoint is
  public and used by the official site, but automated polling is not supported
  by the publisher. Nobody can guarantee there are no consequences.
- The script takes no password or Google/Apple/Facebook login. Player ID and
  State cannot be used to take over an account; they only let you redeem a code
  on it.
- Do not use it to redeem on other people's accounts.

## Credits

The signing protocol and status map were rebuilt from the public Century Games
client and these projects:

- [justncodes/wos-giftcode](https://github.com/justncodes/wos-giftcode)
- [makorus/pyWoSRedemptionTool](https://github.com/makorus/pyWoSRedemptionTool)
- [whiteoutsurvival.dev](https://whiteoutsurvival.dev/api-docs): public API with the
  code list (credit required for public use)

License: MIT. Code written from scratch; the projects above were a source of
protocol knowledge, not code.
