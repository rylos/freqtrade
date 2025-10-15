# RyLoSStrategy - Informazioni Specifiche

## Descrizione
RyLoSStrategy è una strategia DCA (Dollar Cost Averaging) avanzata con:
- Multi-oscillator oversold/overbought detection
- Position adjustment dinamico
- Emergency DCA per situazioni critiche
- Auto-reduce per over-exposure
- Profit skimming intelligente

## Caratteristiche Principali
- **Timeframe**: 5m
- **Tipo**: Solo long (can_short = False)
- **Position Adjustment**: Abilitato
- **Stoploss**: Disabilitato (-1), gestito da custom_exit

## Parametri Ottimizzabili

### Entry Parameters
- `first_order_pct`: Percentuale primo ordine (0.005-0.10)
- `dca_distance`: Distanza tra ordini DCA (0.002-0.05)
- `dca_multiplier`: Moltiplicatore size DCA (1.5-3.0)

### Multi-Oscillator Oversold
- `rsi_oversold_threshold`: Soglia RSI oversold (25-40)
- `bb_oversold_threshold`: Soglia Bollinger Bands (0.1-0.3)
- `atr_oversold_multiplier`: Moltiplicatore ATR (0.5-2.0)
- `macd_oversold_threshold`: Soglia MACD (-0.01 a -0.001)
- `williams_oversold_threshold`: Soglia Williams %R (-90 a -70)
- `min_oversold_count`: Minimo oscillatori oversold (2-5)

### Emergency DCA
- `emergency_dca_threshold`: Soglia perdita per emergency (-0.18 a -0.10)
- `emergency_critical_multiplier`: Moltiplicatore emergency (1.05-2.0)

### Exit Parameters
- `rsi_overbought_threshold`: Soglia RSI overbought (60-85)
- `bb_overbought_threshold`: Soglia BB overbought (0.7-0.9)
- `min_profit_for_overbought_exit`: Profitto minimo per exit (0.01-0.10)
- `last_dca_profit_threshold`: Soglia profit skimming (0.01-0.10)

## Comandi Specifici
```bash
# Backtesting
freqtrade backtesting --strategy RyLoSStrategy --timerange 20230101-20231231

# Hyperopt
freqtrade hyperopt --strategy RyLoSStrategy --hyperopt-loss SharpeHyperOptLoss --epochs 100

# Plot risultati
freqtrade plot-dataframe --strategy RyLoSStrategy --timerange 20230101-20230201
```

## File Location
`user_data/strategies/RyLoSStrategy.py` (365 righe)