# Candlestick-Muster an Key-Levels – Backtest, Paper-Trading & Dashboard

Umgezogen aus `Majic-Beep/Odds-Paper-bot` (Ordner `candle-patterns/`) am 9. Oktober 2026.

Mechanisierte Version der Strategie aus dem Video
*„The BEST Candlestick Pattern Guide You'll EVER FIND“* (YouTube `m4WOwgUMQuc`), gebaut wie
[The Sneaky Pivot](https://github.com/Majic-Beep/the-sneaky-pivot):

- ein **Backtest ohne Blick in die Zukunft** (Kerze-für-Kerze-Engine, Walk-Forward, versiegelter Hold-out),
- **Paper-Trading auf Alpaca** mit drei eingefrorenen Varianten parallel und genau demselben Signal-Code wie im Backtest,
- ein **Dashboard** (`docs/index.html`) für Backtest, Live-Ergebnisse und den Vergleich der Varianten,
- eine **Pine-Script-Version** für TradingView (`pine/candle_patterns.pine`).

**Nur Paper-Trading.** Der Code verweigert jede Alpaca-URL, die nicht `paper-api.` ist.

## Stand (11. Oktober 2026)

- **Ergebnis des Backtests:** Die Video-Regeln verlieren nach Kosten, knapp statistisch belegt (t ≈ −2,1 bis −2,4).
  Long-Trades liegen leicht im Plus (+0,05 R), Short-Trades klar im Minus (−0,15 R). Ein belegter Vorteil
  existiert nicht.
- **Paper-Trading:** Drei Varianten handeln ab Montag, 12. Oktober 2026, parallel mit je 16.667 $ (50.000 $ gedrittelt).
- **Optimierung (11.10.2026):** Variante 3 – nur Long, Trendfilter, Mindest-Stop 0,5 ATR – ist im Backtest klar
  positiv (+0,104 R, t = +3,49), aber im Nachhinein gewählt. Der Großteil ihres Gewinns kommt vom steigenden Markt
  (siehe „Optimierung“).
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

## Die drei Live-Varianten

V1 und V2 festgelegt am 9. Oktober 2026, V3 am 11. Oktober 2026, alle in `results/live_variants.json`:

| | V1 – Video-Regeln | V2 – Trendfilter, Ziel 1,5 R | V3 – nur Long, Trend, Mindest-Stop |
|---|---|---|---|
| Muster | alle sechs | alle sechs | alle sechs, nur bullisch |
| Seiten | Long + Short | Long + Short | nur Long |
| Level-Toleranz | 0,10 ATR | 0,25 ATR | 0,10 ATR |
| Trendfilter | aus | Long nur über, Short nur unter dem 50-Kerzen-Durchschnitt | Long nur über dem 50-Kerzen-Durchschnitt |
| Mindest-Stop | 0,25 ATR | 0,25 ATR | 0,5 ATR |
| Ziel | 2 R | 1,5 R | 2 R |
| Herkunft | vorab festgelegt, nicht optimiert | per Walk-Forward-Regel gewählt auf 05/2025 – 05/2026 | nach Ansicht aller Daten bis 09.10.2026 gewählt (in-sample) |
| Budget | 16.667 $ | 16.667 $ | 16.667 $ |

Zusammen höchstens **50.000 $**, gedrittelt, des gemeinsamen Alpaca-Paper-Kontos (`CP_BUDGET`, vor dem ersten Live-Lauf
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

**Die drei Live-Varianten im Backtest** (je 16.667 $, ab 02/2020; `results/variants_backtest.json`):

| Variante | Trades | Rendite | Max. DD | Ø pro Trade | t |
|---|---|---|---|---|---|
| V1 – Video-Regeln | 6.742 | −12,1 % | −27,6 % | −0,049 R | −2,31 |
| V2 – Trendfilter, Ziel 1,5 R | 6.391 | −3,0 % | −18,1 % | −0,042 R | −2,05 |
| V3 – nur Long, Trend, Mindest-Stop | 3.360 | +159,5 % | −12,4 % | +0,104 R | +3,49 |

V2 und V3 sind im Nachhinein gewählt und deshalb zu optimistisch; ehrlich ist erst das Paper-Trading.

## Optimierung (11. Oktober 2026)

Ausgangspunkt war die Diagnose der Video-Regeln: Long-Trades +0,056 R, Short-Trades −0,158 R; Engulfing und
Pin Bar verlieren, Breakout und 3-Bar-Fortsetzung sind leicht positiv; Stop-Ausstiege kosten im Schnitt −1,27 R
(enge Stops, Slippage, Lücken). Getestet wurden acht Varianten (02/2020 – 10/2026, gleiche Engine und Kosten):

| Variante | Trades | Ø pro Trade | t | nur 05–10/2026 |
|---|---|---|---|---|
| A Video-Regeln | 6.765 | −0,050 R | −2,36 | −0,20 R |
| B nur Long | 5.426 | +0,021 R | +0,85 | −0,14 R |
| C nur Fortsetzungsmuster | 2.321 | +0,019 R | +0,61 | −0,16 R |
| D nur Long + Fortsetzung | 1.363 | +0,105 R | +2,65 | −0,19 R |
| E Mindest-Stop 0,5 ATR | 6.552 | −0,038 R | −1,76 | −0,14 R |
| F nur Long + Mindest-Stop 0,5 ATR | 5.154 | +0,044 R | +1,79 | −0,10 R |
| G nur Long + Trendfilter | 3.559 | +0,075 R | +2,49 | −0,09 R |
| **H nur Long + Trend + Mindest-Stop (= V3)** | 3.395 | **+0,105 R** | **+3,54** | −0,10 R |

**Gegenprobe:** Long-Einstiege an zufälligen Zeitpunkten mit denselben Regeln wie H (Trendfilter, Mindest-Stop,
Ziel 2 R, ohne Muster und Level) brachten in drei Läufen +0,007, +0,057 und +0,072 R pro Trade. Muster und Levels
tragen also nur etwa +0,06 R bei; der Rest ist der steigende Aktienmarkt 2020 – 2026.

**Einordnung:** Die Varianten wurden mit Wissen über alle Daten gewählt; bei acht Tests braucht ein echter
Vorteil etwa t ≥ 2,7. Auch V3 ist in den letzten Monaten negativ (−0,10 R, 209 Trades, nicht signifikant), und
als reine Long-Strategie hängt sie am Markt. Darum läuft sie als dritte Variante im Paper-Trading, statt V1/V2
zu ersetzen.

## Krypto-Backtest (11. Oktober 2026)

Dieselbe Strategie und Engine auf Alpaca-Krypto-Kerzen: BTC, ETH, SOL, DOGE, LTC, LINK, AVAX, 01/2021 – 10/2026,
rund um die Uhr, Bruchteile erlaubt. Kosten 0,30 % pro Seite (Alpaca-Gebühr 0,25 % plus Spread). SOL hatte bei
Alpaca 2023/24 eine Datenlücke und zählt erst danach. Ergebnisse in `results/crypto/`.

| Test (ab 02/2022) | Kerzen | Kosten | Trades | Ø pro Trade | t |
|---|---|---|---|---|---|
| Video-Regeln (V1) | 1 h | 0,30 % | 12.404 | −0,563 R | −41,0 |
| Video-Regeln (V1) | 1 h | keine | 15.100 | −0,051 R | −4,7 |
| V3-Regeln (nur Long, Trend, Mindest-Stop) | 1 h | 0,30 % | 6.087 | −0,544 R | −27,2 |
| V3-Regeln | 1 h | keine | 6.111 | −0,010 R | −0,6 |
| Video-Regeln | 4 h | keine | 4.186 | −0,047 R | −2,3 |
| V3-Regeln | 4 h | 0,30 % | 1.585 | −0,260 R | −7,3 |
| Video-Regeln | 1 Tag | keine | 728 | +0,018 R | +0,5 |
| V3-Regeln | 1 Tag | 0,30 % | 225 | −0,045 R | −0,6 |

**Ergebnis:** Auf Krypto haben die Muster keinen Vorteil, auch nicht ohne Kosten und auf keinem Zeitrahmen. Mit
realistischen Kosten verliert jede Variante massiv, weil der Stop auf dem 1-Stunden-Chart im Schnitt nur etwa 2 %
entfernt ist und 0,6 % Kosten pro Runde damit rund ein Drittel des Risikos auffressen. Kein Paper-Trading für
Krypto (Alpaca erlaubt dort ohnehin keine Shorts).

```
python -m candle_patterns crypto-download
python -m candle_patterns crypto-backtest
```

## Forex-Backtest über Währungs-ETFs (11. Oktober 2026)

Echte Devisenkurse sind in der Cloud-Umgebung nicht in ausreichender Länge verfügbar (Alpaca hat keine Devisen,
FMP verlangt einen höheren Tarif, TradingView liefert nur 5.000 Kerzen pro Abruf). Getestet wurde darum wie im
NNFX-Projekt mit Währungs-ETFs von Alpaca: FXE (Euro), FXB (Pfund), FXY (Yen), FXA (AUD), FXC (CAD), FXF (Franken),
UUP (Dollar-Index), 1-Stunden-Kerzen der US-Handelszeit, 01/2019 – 10/2026, ausgewertet ab 02/2020. Die ETFs sind
dünn gehandelt; Kosten 0,05 % pro Seite. Ergebnisse in `results/forex/`.

| Test (ab 02/2020) | Kosten | Trades | Ø pro Trade | t |
|---|---|---|---|---|
| Walk-Forward | 0,05 % | 2.198 | −0,459 R | −8,85 |
| Hold-out 05 – 10/2026 | 0,05 % | 235 | −0,754 R | −4,46 |
| V1 Video-Regeln | 0,05 % | 2.746 | −0,548 R | −11,33 |
| V2 | 0,05 % | 2.132 | −0,504 R | −9,55 |
| V3 nur Long, Trend, Mindest-Stop | 0,05 % | 952 | −0,457 R | −5,81 |
| V1 Video-Regeln | keine | 2.751 | −0,046 R | −1,02 |
| V3 | keine | 952 | −0,028 R | −0,37 |

**Ergebnis:** Kein Vorteil, auch nicht ohne Kosten. Währungen bewegen sich pro Stunde sehr wenig: Der Stop liegt im
Schnitt nur 0,3 % vom Einstieg entfernt, schon 0,02 % Kosten pro Seite machen daraus −0,25 R pro Trade. Kein
Paper-Trading für Forex. Ein Test mit echten Spot-Devisenkursen (deutlich geringere Spreads) wäre nur mit einer
anderen Datenquelle möglich.

```
python -m candle_patterns forex-download
python -m candle_patterns forex-backtest
```

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
- **Mehrere Varianten im selben Symbol:** gleiche Richtung erlaubt; die Gegenrichtung wird ausgelassen
  (Vorrang wechselt stündlich).
- **Feiertage / verkürzte Tage** über den Alpaca-Kalender.
- **Protokoll:** `results/live_signals.csv`, `results/live_state.json`, `results/live.json`.

Die Cloud-Routinen beschreibt `routine/ROUTINE.md`.

## TradingView

`pine/candle_patterns.pine` auf einen 1-Stunden-Chart (nur reguläre Handelszeit) legen. **Variant** wählt V1, V2, V3
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
candle_patterns/crypto.py      Krypto-Backtest (Alpaca-Krypto-Kerzen, Kosten, Bruchteile)
candle_patterns/forex.py       Forex-Backtest über Währungs-ETFs
candle_patterns/alpaca.py      Alpaca-Paper-Client (verweigert Live-Konten)
candle_patterns/live.py        Paper-Trading: run / sync, drei Varianten
candle_patterns/dashboard.py   docs/index.html (Vorlage: dashboard_template.html)
results/live_variants.json     die eingefrorenen Live-Varianten
pine/candle_patterns.pine      TradingView-Strategie (V1 / V2 / V3 / Custom)
routine/ROUTINE.md             Cloud-Routinen
tests/                         kein Blick in die Zukunft, Muster, Fills, Live-Ablauf mit mehreren Varianten
```
