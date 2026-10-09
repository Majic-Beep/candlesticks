# Candlestick-Muster an Key-Levels – Backtest, Paper-Trading & Dashboard

Umgezogen aus `Majic-Beep/Odds-Paper-bot` (Ordner `candle-patterns/`) am 9. Oktober 2026.

Mechanisierte Version der Strategie aus dem Video
*„The BEST Candlestick Pattern Guide You'll EVER FIND“* (YouTube `m4WOwgUMQuc`), gebaut wie
[The Sneaky Pivot](https://github.com/Majic-Beep/the-sneaky-pivot):

- ein **Backtest ohne Blick in die Zukunft** (Kerze-für-Kerze-Engine, Walk-Forward, versiegelter Hold-out),
- **Paper-Trading auf Alpaca** mit zwei eingefrorenen Varianten parallel und genau demselben Signal-Code wie im Backtest,
- ein **Dashboard** (`docs/index.html`) für Backtest, Live-Ergebnisse und den Vergleich der Varianten,
- eine **Pine-Script-Version** für TradingView (`pine/candle_patterns.pine`).

**Nur Paper-Trading.** Der Code verweigert jede Alpaca-URL, die nicht `paper-api.` ist.

## Stand (9. Oktober 2026)

- **Ergebnis des Backtests:** Die Video-Regeln verlieren nach Kosten, knapp statistisch belegt (t ≈ −2,1 bis −2,4).
  Long-Trades liegen leicht im Plus (+0,05 R), Short-Trades klar im Minus (−0,15 R). Ein belegter Vorteil
  existiert nicht.
- **Paper-Trading:** Beide Varianten handeln ab Montag, 12. Oktober 2026, parallel mit je 25.000 $.
- **Dashboard:** https://claude.ai/artifact/TECWJJdJ7SiBag1AATdW3c (privat; wird nach jedem Handelstag aktualisiert).
  Die Parameter sind eingefroren (`results/live_variants.json`).

## Woher die Regeln kommen

YouTube ist aus der Cloud-Umgebung gesperrt. Die Regeln stammen aus dem Transkript und Zusammenfassungen des Videos
(Exa-Suche, Dailymotion-Kopie mit Transkript). Das Video nennt:

1. **Key-Level finden** (Support/Resistance, Trendlinien, Fibonacci, Konfluenz),
2. **warten, bis der Kurs das Level erneut testet**,
3. **eines von sechs Mustern als Bestätigung:** Engulfing, Pin Bar, 3-Bar-Fortsetzung, 3-Bar-Umkehr,
   Breakout-Kerzen, schrumpfende Kerzen,
4. **Einstieg** beim Schluss des Musters, **Stop** hinter dem Muster, **Ziel** = 2 × Stop-Abstand,
5. Zeitrahmen **1 Stunde oder höher**.

Was das Video offenlässt (was „große“ Kerze heißt, wie ein Level genau definiert ist), ist als Parameter in
`candle_patterns/config.py` festgelegt, **vor** dem ersten Backtest. Trendlinien und Fibonacci sind nicht
mechanisiert; als Key-Level zählen bestätigte Swing-Hochs und -Tiefs.

## Die Regeln

1-Stunden-Chart, nur reguläre US-Handelszeit, Kerzen ab 09:30 (09:30, 10:30, … 14:30 und die halbe Stunde
15:30–16:00, wie TradingView).

**Key-Levels:** Swing-Hochs und -Tiefs der letzten 140 Kerzen (≈ 20 Handelstage). Ein Swing braucht 3 niedrigere
Hochs (bzw. höhere Tiefs) auf jeder Seite und ist erst danach bekannt. Alte Widerstände unter dem Kurs gelten als
Unterstützung und umgekehrt. Ein Muster steht **am Level**, wenn ein Level zwischen seinem Extrem
(± 0,1 × ATR) und seinem Schlusskurs liegt: Der Kurs hat das Level getestet und auf der Trade-Seite geschlossen.

**Die sechs Muster** (bullisch; bärisch spiegelbildlich). „Groß“ = Körper ≥ 1,2 × Durchschnittskörper der
20 Kerzen davor, „klein“ = ≤ 0,6 ×.

| Muster | Definition |
|---|---|
| Engulfing | rote Kerze, dann grüne, deren Körper den roten umschließt und größer ist |
| Pin Bar | grüne Kerze, unterer Docht ≥ 66 % der Kerzenspanne |
| 3-Bar-Umkehr | große rote, kleinere rote, große grüne mit Schluss über der Eröffnung der ersten |
| 3-Bar-Fortsetzung | große grüne, kleine Pause über dem ersten Tief, große grüne mit Schluss über beiden Hochs |
| Breakout-Kerze | ≥ 3 kleine Kerzen, dann eine große grüne mit Schluss über allen |
| Schrumpfende Kerzen | ≥ 3 rote Kerzen mit jeweils kleinerem Körper, dann eine große grüne |

**Trade:** Market-Order zur Eröffnung der nächsten Kerze. Stop 0,05 × ATR hinter dem Extrem des Musters,
Ziel 2 × Risiko (gemessen vom Schlusskurs der Signalkerze). Setups mit Stop näher als 0,25 ATR werden
ausgelassen. Spätestens nach 35 Kerzen (5 Handelstage) wird zur nächsten Eröffnung geschlossen. Positionen
laufen über Nacht. Long und Short auf derselben Kerze = kein Trade, eine Position pro Symbol, keine neuen
Einstiege an verkürzten Handelstagen.

**Größe:** 0,5 % des Kapitals Risiko pro Trade, höchstens 25 % des Kapitals pro Position, alle Positionen
zusammen höchstens 100 %.

**Universum:** XLF, XLE, XLV, SMH, GLD, TLT, JPM, AVGO, NFLX, COST, LLY, XOM – bewusst ohne Überschneidung mit
dem Sneaky-Pivot-Universum, damit sich die beiden Bots im gemeinsamen Paper-Konto nie in die Quere kommen.

## Die zwei Live-Varianten

Festgelegt am 9. Oktober 2026 in `results/live_variants.json`:

| | V1 – Video-Regeln | V2 – Trendfilter, Ziel 1,5 R |
|---|---|---|
| Muster | alle sechs | alle sechs |
| Level-Toleranz | 0,10 ATR | 0,25 ATR |
| Trendfilter | aus | Long nur über, Short nur unter dem 50-Kerzen-Durchschnitt |
| Ziel | 2 R | 1,5 R |
| Herkunft | vorab festgelegt, nicht optimiert | per Walk-Forward-Regel gewählt auf 05/2025 – 05/2026 |
| Budget | 25.000 $ | 25.000 $ |

Zusammen höchstens **50.000 $** des gemeinsamen Alpaca-Paper-Kontos (`CP_BUDGET`, vor dem ersten Live-Lauf
änderbar; danach steht es in `results/live_state.json`). Sneaky Pivot nutzt weitere 50.000 $ desselben Kontos.

## Warum der Backtest nicht geschönt ist

1. **Event-Engine:** Die Strategie bekommt jede Kerze erst nach ihrem Schluss und sieht nie eine spätere.
   Orders wirken frühestens ab der nächsten Kerze.
2. **Swings erst nach Bestätigung:** Ein Swing-Punkt zählt erst, wenn 3 spätere Kerzen ihn bestätigt haben.
   Swings im Muster selbst zählen nicht.
3. **Konservative Fills:** Einstieg zur nächsten Eröffnung plus 2 bp Slippage. Stop zum Stop oder einer
   schlechteren Eröffnungslücke plus Slippage. Liegen Stop und Ziel in derselben Kerze, gilt der Stop.
   Öffnet der Kurs schon jenseits von Stop oder Ziel, wird der Trade ausgelassen.
4. **Walk-Forward:** 8 Kombinationen (Trendfilter, Toleranz, Ziel), gewählt nur auf 12 Monaten Training,
   gehandelt in den folgenden 3 Monaten. Für die Wahl zählen nur Trades, die vor dem Testfenster geschlossen
   waren (Positionen laufen bis zu einer Woche).
5. **Versiegelter Hold-out:** Die letzten 6 Monate wurden für keine Entscheidung benutzt.
6. **Automatische Tests:** Werden alle Kerzen nach einem Stichtag ersetzt, bleiben alle früher geschlossenen
   Trades identisch (`tests/test_no_lookahead.py`). Jedes Muster hat einen eigenen Test.

## Ergebnisse

12 Symbole, 30-Minuten-Bars von Alpaca (SIP, split-bereinigt) zu 1-Stunden-Kerzen zusammengefasst,
01/2019 – 10/2026, 50.000 $ Startkapital. 1 R = geplantes Risiko (Signal-Schluss bis Stop).

| Test | Trades | Rendite | Max. DD | Ø pro Trade | t |
|---|---|---|---|---|---|
| Walk-Forward 02/2020 – 04/2026 | 5.968 | −0,8 % | −20,3 % | −0,047 R | −2,12 |
| Hold-out 05 – 10/2026 | 443 | −14,3 % | −15,3 % | −0,147 R | −1,91 |
| Standard (Video-Regeln) | 6.765 | −2,3 % | −24,4 % | −0,050 R | −2,36 |
| In-Sample (bestes Raster im Nachhinein) | 5.252 | +11,4 % | −19,1 % | −0,006 R | −0,24 |

Warum die Rendite besser aussieht als der Ø in R: Trades mit sehr engem Stop werden von der 25-%-Positionsgrenze
gedeckelt und riskieren deshalb weniger als 0,5 %. Gerade diese Trades verlieren in R am meisten
(Slippage und Lücken sind im Verhältnis zum kleinen Risiko groß). Der Erwartungswert in R ist die ehrlichere Zahl.

**Nach Muster** (Standard, Video-Regeln): Breakout-Kerze +0,04 R (623 Trades), 3-Bar-Fortsetzung +0,04 R (522),
3-Bar-Umkehr −0,02 R (194), schrumpfende Kerzen −0,02 R (106), Engulfing −0,07 R (4.009), Pin Bar −0,09 R (1.311).
Keines davon ist für sich signifikant; die beiden positiven sind die Fortsetzungsmuster.

**Die beiden Live-Varianten im Backtest** (je 25.000 $, ab 02/2020; `results/variants_backtest.json`):

| Variante | Trades | Rendite | Max. DD | Ø pro Trade | t |
|---|---|---|---|---|---|
| V1 – Video-Regeln | 6.730 | −13,6 % | −27,1 % | −0,047 R | −2,22 |
| V2 – Trendfilter, Ziel 1,5 R | 6.405 | +0,3 % | −18,6 % | −0,037 R | −1,82 |

V2 ist zum Teil im Nachhinein gewählt und deshalb zu optimistisch; ehrlich ist erst das Paper-Trading.

## Benutzung

Python ≥ 3.10, nur Standardbibliothek. Alle Befehle im Hauptordner des Repos.

```
cp .env.example .env                       # Alpaca-PAPER-Keys eintragen
python -m candle_patterns download --start 2019-01-01   # 30-Min-Bars von Alpaca -> data/
python -m candle_patterns backtest         # Walk-Forward + Hold-out -> results/backtest.json
python -m candle_patterns variants         # Backtest der Live-Varianten -> results/variants_backtest.json
python -m candle_patterns dashboard        # -> docs/index.html
python -m candle_patterns run --dry-run    # Live-Schritt ohne Orders
python -m unittest discover -s tests -t .
```

## Paper-Trading

`python -m candle_patterns run` läuft eine Minute nach jedem Kerzenschluss, Mo–Fr New-York-Zeit:
10:31, 11:31, 12:31, 13:31, 14:31, 15:31 und 16:01 (deutsche Zeit +6 h).

1. **Zeit-Ausstieg:** Positionen, die 35 Kerzen gehalten wurden, werden per Market-Order geschlossen.
2. **Einstiege:** Die gerade geschlossene Kerze wird geprüft. Ein Signal wird zur Market-Bracket-Order
   (Stop + Ziel, GTC). Um 16:01 stellt Alpaca die Order bis zur nächsten Eröffnung zurück – dort füllt auch
   der Backtest. Läuft der Schritt mehr als 15 Minuten nach Kerzenschluss, gibt es keine neuen Einstiege.

Um 16:01 zusätzlich `sync` (Fills und Simulation nach `results/live.json`) und `dashboard`.

- **Order-IDs** `cp-<variante>-<Signalkerze JJJJMMTTHHMM>-<symbol>`, Zeit-Ausstiege mit `-x`. Der Bot fasst nur eigene Orders an.
- **Andere Bots:** Symbole mit fremder Position oder Order werden ausgelassen.
- **Beide Varianten im selben Symbol:** gleiche Richtung erlaubt; die Gegenrichtung wird ausgelassen
  (Vorrang wechselt stündlich).
- **Feiertage / verkürzte Tage** über den Alpaca-Kalender.
- **Protokoll:** `results/live_signals.csv`, `results/live_state.json`, `results/live.json`.

Die Cloud-Routinen beschreibt `routine/ROUTINE.md`.

## TradingView

`pine/candle_patterns.pine` auf einen 1-Stunden-Chart (nur reguläre Handelszeit) legen. **Variant** wählt V1, V2
oder Custom. Unterschiede zur Python-Engine: verkürzte Tage werden gehandelt, und eine Eröffnung jenseits von
Stop/Ziel wird nicht ausgelassen. Maßgeblich sind Python-Backtest und Paper-Trading.

## Dateien

```
candle_patterns/config.py      Parameter, Universum, Raster, Live-Budget
candle_patterns/strategy.py    Key-Levels + sechs Muster (eine Klasse für Backtest und Live)
candle_patterns/engine.py      Event-Backtester mit konservativen Fills und Gesamtgrenze
candle_patterns/walkforward.py Walk-Forward, Hold-out, Referenzen, Raster-Varianten
candle_patterns/variants.py    Backtest der eingefrorenen Live-Varianten
candle_patterns/data.py        Alpaca-Kursdaten, CSV-Cache, 1-Stunden-Kerzen
candle_patterns/alpaca.py      Alpaca-Paper-Client (verweigert Live-Konten)
candle_patterns/live.py        Paper-Trading: run / sync, zwei Varianten
candle_patterns/dashboard.py   docs/index.html (Vorlage: dashboard_template.html)
results/live_variants.json     die eingefrorenen Live-Varianten
pine/candle_patterns.pine      TradingView-Strategie (V1 / V2 / Custom)
routine/ROUTINE.md             Cloud-Routinen
tests/                         kein Blick in die Zukunft, Muster, Fills, Live-Ablauf mit zwei Varianten
```
