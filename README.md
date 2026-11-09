# WoS Gift Redeemer

Automatyczne odbieranie gift code'ów w **Whiteout Survival** — bez logowania, bez hasła, bez bota do gry.

Potrzebujesz dwóch liczb: **Player ID** (cyfry pod nickiem w grze) i **numer stanu** (State). Nic więcej. Skrypt codziennie pobiera aktywne kody i wysyła je do oficjalnego endpointu, którego używa strona `wos-giftcode.centurygame.com`.

## Jak to działa

1. `GET https://whiteoutsurvival.dev/api/gift-codes` → lista aktywnych kodów (plus fallback ze scrape + własny plik z kodami).
2. Dla każdego nowego kodu: `POST https://wos-giftcode-api.centurygame.com/api/gift_code` z polami `fid` (Player ID), `kid` (State), `cdk` (kod), `time` i podpisem `md5(...)`.
3. Wynik trafia do pliku stanu: `redeemed` / `already claimed` / `expired` / `wrong state`. Kody raz odebrane i raz martwe nie są ponawiane.

Zero zależności — tylko biblioteka standardowa Pythona (3.10+).

## Użycie

```bash
./redeemer.py --player-id 12345678 --state 4351          # jedno uruchomienie
./redeemer.py --player-id 12345678 --state 4351 --dry-run # tylko pokaż kody
./redeemer.py --config config.json --json                 # pod cron, wynik maszynowy
```

Plik `config.json` (nie commituj go — jest w `.gitignore`):

```json
{
  "playerId": "12345678",
  "state": "4351"
}
```

### Cron, raz dziennie

```cron
15 8 * * * cd /sciezka/do/wos-gift-redeemer && ./redeemer.py --config config.json >> redeem.log 2>&1
```

### Cron w Hermesie

Skill `wos-gift-codes` w tym repo potrafi to uruchomić jako zadanie cykliczne z podsumowaniem na Telegram.

## Kody wyjścia i statusy

| Status | Znaczenie |
| --- | --- |
| `redeemed` | kod odebrany |
| `already claimed` | już był odebrany na tym koncie |
| `expired` | kod wygasł |
| `claim limit reached` | limit globalny kodu wyczerpany |
| `wrong state for this player ID` | zły numer stanu — popraw `state` |
| `rate limited` | API prosi o przerwę; skrypt czeka 60 s i próbuje raz jeszcze |
| `no such player` | Player ID nie istnieje |

## Zastrzeżenia

- To **szara strefa ToS** Century Games. Endpoint jest publiczny i używany przez oficjalną stronę, ale automatyczne odpytywanie go nie jest przez wydawcę wspierane. Praktyka jest powszechna w botach sojuszowych; gwarancji braku konsekwencji nikt nie daje.
- Skrypt nie przyjmuje hasła ani loginu Google/Apple/Facebook. Player ID + State nie pozwalają przejąć konta — pozwalają tylko odebrać kod na to konto.
- Kody odebrane raz na koncie nie wracają. Limit globalny kodu (`USED`) jest poza Twoją kontrolą.
- Nie używaj tego do masowego redeemowania na cudze konta.

## Podziękowania

Protokół podpisu i mapa kodów błędów odtworzone z publicznego klienta Century Games i z pracy tych projektów:

- [justncodes/wos-giftcode](https://github.com/justncodes/wos-giftcode) — pełny redeemer, mapa statusów
- [makorus/pyWoSRedemptionTool](https://github.com/makorus/pyWoSRedemptionTool) — wersja cronowa dla sojuszu
- [whiteoutsurvival.dev](https://whiteoutsurvival.dev/api-docs) — publiczne API z listą kodów (wymaga podania źródła)

Licencja: MIT. Kod napisany od zera; powyższe projekty były źródłem wiedzy o protokole, nie kodu.
