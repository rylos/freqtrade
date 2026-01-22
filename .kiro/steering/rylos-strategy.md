# RyLoS Strategy - Dettagli Implementazione

## Parametri Ottimizzati (v2025-11-10)

### Buy Space (10 parametri)
```python
first_order_pct = 0.029              # 2.9% del balance
dca_distance = 0.022                 # 2.2% distanza base
dca_multiplier = 1.991               # Moltiplicatore stake progressivo
dca_atr_multiplier = 2.306           # Peso ATR su distanza DCA
dca_cooldown_candles = 2             # FISSO - 10 minuti (2 × 5m)

rsi_oversold_threshold = 25.333
bb_oversold_threshold = 0.294
stochrsi_oversold_threshold = 0.782
williams_oversold_threshold = -74.991
min_oversold_count = 2               # Minimo oscillatori oversold

emergency_dca_threshold = -0.124     # -12.4% loss trigger
emergency_critical_multiplier = 1.175
```

### Sell Space (7 parametri)
```python
rsi_overbought_threshold = 63.146
bb_overbought_threshold = 0.871
atr_overbought_multiplier = 0.556
stochrsi_overbought_threshold = 94.809
williams_overbought_threshold = -24.965
min_overbought_count = 4             # Minimo oscillatori overbought
min_profit_for_overbought_exit = 0.017  # 1.7% profit minimo
```

### Trailing Stop (hardcoded)
```python
trailing_stop = True
trailing_stop_positive = 0.227       # 22.7% trailing dopo offset
trailing_stop_positive_offset = 0.315  # Attiva a +31.5% profit
trailing_only_offset_is_reached = False
```

## Entry Logic

### First Order
```python
conditions = [
    oversold_count >= min_oversold_count,
    dataframe['close'] < dataframe['open'],  # Candela rossa
]
dataframe.loc[reduce(lambda x, y: x & y, conditions), 'enter_long'] = 1
```

**Tag**: `buy_rsi_bb_stochrsi_wr` (indica quali oscillatori erano oversold)

### DCA Standard
- **Trigger**: Prezzo < last_order_price
- **Distanza**: `dca_distance × (1 + ATR% × dca_atr_multiplier)`
- **Cooldown**: 2 candele (10 minuti) dall'ultimo filled order
- **Stake**: `first_order_pct × (dca_multiplier ^ entry_count)`

### Emergency DCA
- **Trigger**: Loss ≤ -12.4% dall'ultimo filled order
- **Critical**: Loss ≤ -14.6% (threshold × multiplier)
- **Comportamento**: SALTA controlli BB, RIDUCE stake se supera limiti
- **Tag**: `dca_emergency` o `dca_critical`

## Exit Logic

### Multi-Oscillator Overbought
```python
conditions = [
    overbought_count >= min_overbought_count,
    current_profit > min_profit_for_overbought_exit,
    dataframe['close'] > dataframe['open'],  # Candela verde
]
dataframe.loc[reduce(lambda x, y: x & y, conditions), 'exit_long'] = 1
```

**Tag**: `sell_overbought_rsi_bb_atr_stochrsi_wr`

## Limiti e Risk Management

### Calcolo Limiti
```python
global_limit = balance × leverage  # balance × 4
per_pair_limit = global_limit / max_open_trades
max_orders = floor(log(per_pair_limit / first_order_stake) / log(dca_multiplier)) + 1
```

### Verifica Stake
- Controlla 95% del limite globale prima di ogni order
- Riduce stake se necessario (non blocca trade)
- Log warning se stake ridotto

## Indicatori (periodo 10)

```python
dataframe['rsi'] = ta.RSI(dataframe, timeperiod=10)
dataframe['atr'] = ta.ATR(dataframe, timeperiod=10)
dataframe['atr_pct'] = (dataframe['atr'] / dataframe['close']) * 100

stoch = ta.STOCHRSI(dataframe, timeperiod=10, fastk_period=5, fastd_period=3)
dataframe['stochrsi_k'] = stoch['fastk']

dataframe['williams_r'] = ta.WILLR(dataframe, timeperiod=10)

bollinger = qtpylib.bollinger_bands(dataframe['close'], window=20, stds=2)
dataframe['bb_lowerband'] = bollinger['lower']
dataframe['bb_upperband'] = bollinger['upper']
dataframe['bb_middleband'] = bollinger['mid']
dataframe['bb_percent'] = (dataframe['close'] - dataframe['bb_lowerband']) / \
                          (dataframe['bb_upperband'] - dataframe['bb_lowerband'])
```

## Note Implementazione

### Auto-Reduce DISABILITATO
```python
auto_reduce_enabled = False
```
Causava loss in backtest. Exit gestito solo da overbought + trailing.

### Stoploss DISABILITATO
```python
stoploss = -1
```
Gestione loss affidata a trailing stop e DCA recovery.

### Leverage Fisso
```python
leverage = 4
```
Non modificabile via hyperopt, hardcoded nella strategia.
