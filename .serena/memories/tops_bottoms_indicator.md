# Tops/Bottoms Indicator (CVI-based) - LOGICA ORIGINALE

## Descrizione
Indicatore basato su CVI (Cumulative Volume Index) di LazyBear che identifica tops e bottoms del mercato.

## Formula
```python
# hl2 = (high + low) / 2
# ValC = SMA(hl2, length)
# vol = SMA(ATR(length), length)
# cvi = (close - ValC) / (vol * sqrt(length))
```

## Segnali (LOGICA ORIGINALE PINESCRIPT)
- **BUY** (bull2): Quando CVI esce dalla zona bullish (era <= -0.51, ora > -0.51) - plotchar verde
- **SELL** (bear2): Quando CVI esce dalla zona bearish (era >= 0.43, ora < 0.43) - plotchar rosso

## Logica PineScript
```pinescript
bull1 = cvi <= bull    // cvi <= -0.51 (zona bullish)
bear1 = cvi >= bear    // cvi >= 0.43 (zona bearish)
bull2 = bull1[1] and not bull1  // era bullish, ora non più = BUY
bear2 = bear1[1] and not bear1  // era bearish, ora non più = SELL
```

## Parametri
- `length`: Periodo per SMA e ATR (default 3)
- `bull_threshold`: Soglia bullish (default -0.51)
- `bear_threshold`: Soglia bearish (default 0.43)

## Implementazione
File: `user_data/strategies/tops_bottoms_indicator.py`

## Integrazione in RyLoSStrategy
```python
# In populate_indicators
dataframe = tops_bottoms_indicator(dataframe)

# In populate_entry_trend
(dataframe['cvi_buy_signal'] == True)

# In populate_exit_trend  
(dataframe['cvi_sell_signal'] == True)
```
