# Context7 TA-Lib Usage

## Library ID
- **Context7 ID**: `/ta-lib/ta-lib-python`
- **Description**: Python wrapper for TA-Lib technical analysis library

## Key Indicators per RyLoSStrategy

### Momentum Indicators
```python
# RSI - Relative Strength Index
rsi = talib.RSI(close, timeperiod=14)

# MACD - Moving Average Convergence/Divergence
macd, macdsignal, macdhist = talib.MACD(close, fastperiod=12, slowperiod=26, signalperiod=9)

# Williams %R
willr = talib.WILLR(high, low, close, timeperiod=14)
```

### Volatility Indicators
```python
# ATR - Average True Range
atr = talib.ATR(high, low, close, timeperiod=14)
```

### Overlap Studies
```python
# Bollinger Bands
upper, middle, lower = talib.BBANDS(close, timeperiod=20, nbdevup=2, nbdevdn=2, matype=0)

# BB Position calculation (0-1 range)
bb_position = (close - lower) / (upper - lower)
```

## Usage Notes
- Usa Context7 per documentazione TA-Lib aggiornata
- Tutti gli indicatori supportano parametri personalizzabili
- Funzioni restituiscono numpy arrays compatibili con pandas DataFrame