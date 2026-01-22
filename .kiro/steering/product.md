# Progetto RyLoS Strategy

Strategia di trading crypto basata su Freqtrade con focus su DCA dinamico e multi-oscillator oversold/overbought detection.

## Componenti Principali

- **RyLoSStrategy**: Strategia long-only con leverage 4x, timeframe 5m
- **CalmarRyLoS Loss Function**: Funzione di ottimizzazione hyperopt personalizzata
- **Configurazione**: Setup orderbook pricing per esecuzione immediata

## Caratteristiche Strategia

- **Entry Logic**: Multi-oscillator oversold (RSI, BB%, StochRSI, Williams %R)
- **DCA Dinamico**: Distanza basata su ATR, stake progressivo, emergency DCA
- **Exit Logic**: Multi-oscillator overbought con profit minimo
- **Trailing Stop**: Hardcoded con offset positivo
- **Risk Management**: Limiti globali e per-pair, cooldown DCA

## Obiettivi Ottimizzazione

- Massimizzare Calmar Ratio (return/max_drawdown)
- Minimizzare durata trade (penalty logaritmico >2h)
- Bilanciare aggressività DCA con risk management

## Note Operative

- Solo long trades (can_short = False)
- Stoploss disabilitato (-1), gestito da trailing
- ROI target: 50%
- 20 parametri ottimizzabili attivi
