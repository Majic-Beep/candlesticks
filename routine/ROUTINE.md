# Cloud-Routinen (Claude Code) für das Paper-Trading

**Aktiv ab Montag, 12.10.2026.** Beide Routinen feuern in die feste Sitzung `session_01Qvh29LUBhYaEGDoRH7koSY`,
in der dieses Repo (Branch `main`, Pfad `/home/user/candlesticks`) ausgecheckt ist – wie bei Sneaky Pivot, weil
frische Sitzungen das Repo nicht zuverlässig nachladen konnten.

| Routine | ID | Cron | Schritt |
|---|---|---|---|
| Candle Patterns – Stundenlauf | `trig_014jAQTrQZDeJBba2smSXRMq` | `CRON_TZ=America/New_York 31 10-15 * * 1-5` | `run` |
| Candle Patterns – Handelsschluss | `trig_011QbP91RfgMd3T8bVg9uk7i` | `CRON_TZ=America/New_York 1 16 * * 1-5` | `run` + `sync` + `dashboard` + Artifact |

Dashboard (privat): https://claude.ai/artifact/TECWJJdJ7SiBag1AATdW3c

## Prompt Stundenlauf

```
Candle-Patterns-Routine, SCHRITT = run (eine Minute nach Kerzenschluss).
1. Falls /home/user/candlesticks fehlt: git clone https://github.com/Majic-Beep/candlesticks /home/user/candlesticks
   cd /home/user/candlesticks && git pull origin main
2. python3 -m candle_patterns run
3. Falls sich results/ geändert hat: committen und auf main pushen.
4. Erfinde keine Orders und handle nichts manuell: nur der Befehl oben sendet Orders, und nur an
   paper-api.alpaca.markets. Melde das Ergebnis in einer Zeile.
```

## Prompt Handelsschluss

```
Candle-Patterns-Routine, SCHRITT = Handelsschluss (16:01 ET).
1. git pull (wie oben)
2. python3 -m candle_patterns run && python3 -m candle_patterns sync
   && python3 -m candle_patterns dashboard
3. results/ und docs/ committen und pushen.
4. Dashboard-Artifact aktualisieren (file_path /home/user/candlesticks/docs/index.html, url siehe oben).
5. Keine manuellen Orders. Live-PnL je Variante und Fehler melden.
```

Benötigt: Alpaca-Paper-Keys als Umgebungsvariablen (`ALPACA_API_KEY` / `ALPACA_SECRET_KEY` oder
`ALPACA_API_KEY_ID` / `ALPACA_API_SECRET_KEY`) und `data.alpaca.markets` + `paper-api.alpaca.markets` in den
erlaubten Domains der Umgebung (beides ist in der aktuellen Umgebung vorhanden).

Feiertage und verkürzte Handelstage erkennt `run` selbst über den Alpaca-Kalender. Ein Lauf, der mehr als
15 Minuten nach Kerzenschluss startet, sendet keine neuen Einstiege (Zeit-Ausstiege schon).
