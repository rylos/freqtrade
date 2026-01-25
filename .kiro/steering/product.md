# Progetto RyLoS Strategy

Strategia di trading crypto basata su Freqtrade con focus su DCA dinamico e multi-oscillator oversold/overbought detection.

## Componenti Principali

- **RyLoSStrategy**: Strategia long-only con leverage 4x, timeframe 5m
- **CalmarRyLoS Loss Function**: Funzione di ottimizzazione hyperopt personalizzata
- **Configurazione**: Setup orderbook pricing per esecuzione immediata

## Caratteristiche Strategia

- **Entry Logic**: ML-driven con 3 orizzonti temporali (15m, 30m, 1h) - tutti devono essere positivi
- **DCA Dinamico**: Distanza basata su ATR, stake progressivo, filtro ML (2/3 orizzonti positivi)
- **Exit Logic**: ML-driven semplice (2/3 orizzonti negativi) con profit minimo
- **Risk Management**: Limiti globali e per-pair, cooldown DCA, confidence-based stake sizing (opzionale)

## Obiettivi Ottimizzazione

- Massimizzare Calmar Ratio (return/max_drawdown) con CalmarHyperOptLoss
- Ottimizzare 13 parametri: 4 DCA base + 9 ML thresholds
- Bilanciare aggressività DCA con risk management e filtri ML

## Note Operative

- Solo long trades (can_short = False)
- Stoploss disabilitato (-1), gestito da custom_exit ML-driven
- ROI disabilitato (0.5), usa solo custom_exit
- 13 parametri ottimizzabili attivi (buy + sell spaces)
