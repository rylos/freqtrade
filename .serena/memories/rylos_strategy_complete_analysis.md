# RyLoSStrategy - Analisi Completa del Funzionamento

## Struttura Base
- **File**: `user_data/strategies/RyLoSStrategy.py` (365 righe)
- **Timeframe**: 5m
- **Tipo**: Solo long (can_short = False)
- **Position Adjustment**: Abilitato (dinamico)
- **Stoploss**: -1 (disabilitato, gestito da custom_exit)
- **ROI**: 10.0 (praticamente disabilitato)
- **Leverage**: 5.0x fisso

## Parametri Ottimizzabili (Hyperopt)

### Entry Parameters (space='buy')
```python
first_order_pct = DecimalParameter(0.005, 0.10, default=0.053)  # % primo ordine
dca_distance = DecimalParameter(0.002, 0.05, default=0.022)     # Distanza DCA
dca_multiplier = DecimalParameter(1.5, 3.0, default=2.018)      # Moltiplicatore DCA
```

### Multi-Oscillator Oversold (space='buy')
```python
rsi_oversold_threshold = DecimalParameter(25, 40, default=26.221)
bb_oversold_threshold = DecimalParameter(0.1, 0.3, default=0.105)
atr_oversold_multiplier = DecimalParameter(0.5, 2.0, default=0.758)
macd_oversold_threshold = DecimalParameter(-0.01, -0.001, default=-0.006)
williams_oversold_threshold = DecimalParameter(-90, -70, default=-79.415)
min_oversold_count = IntParameter(2, 5, default=3)  # Min indicatori oversold
```

### Emergency DCA (space='buy')
```python
emergency_dca_threshold = DecimalParameter(-0.18, -0.10, default=-0.17)
emergency_critical_multiplier = DecimalParameter(1.05, 2.0, default=1.59)
```

### Exit Parameters (space='sell')
```python
rsi_overbought_threshold = DecimalParameter(60, 85, default=71.587)
bb_overbought_threshold = DecimalParameter(0.7, 0.9, default=0.858)
atr_overbought_multiplier = DecimalParameter(0.5, 2.0, default=0.631)
macd_overbought_threshold = DecimalParameter(0.001, 0.01, default=0.007)
williams_overbought_threshold = DecimalParameter(-30, -10, default=-11.154)
min_overbought_count = IntParameter(2, 5, default=4)
min_profit_for_overbought_exit = DecimalParameter(0.01, 0.10, default=0.013)
last_dca_profit_threshold = DecimalParameter(0.01, 0.10, default=0.04)
```

### Auto-Reduce (space='sell')
```python
auto_reduce_threshold = DecimalParameter(1.0, 1.1, default=1.024)        # 102.4%
auto_reduce_critical_threshold = DecimalParameter(1.06, 1.15, default=1.146)  # 114.6%
```

## Indicatori Tecnici (populate_indicators)

### Indicatori Calcolati
1. **RSI**: RSI(close, 14) - Relative Strength Index
2. **Bollinger Bands %B**: (close - bb_lower) / (bb_upper - bb_lower)
3. **ATR**: ATR(high, low, close, 14) - Average True Range
4. **MACD**: MACD(close, 12, 26, 9) - Moving Average Convergence Divergence
5. **Williams %R**: WILLR(high, low, close, 14) - Williams Percent Range

## Logica di Entry (populate_entry_trend)

### Multi-Oscillator Oversold Detection
Conta quanti dei 5 indicatori sono in condizione oversold:

1. **RSI Oversold**: rsi < rsi_oversold_threshold
2. **BB Oversold**: bb_percent < bb_oversold_threshold  
3. **ATR Oversold**: close < (low_min_14 + atr * atr_oversold_multiplier)
4. **MACD Oversold**: macd < macd_oversold_threshold
5. **Williams Oversold**: williams_r < williams_oversold_threshold

### Condizione Entry
```python
entry_condition = (oversold_count >= min_oversold_count) & (close < open)
```
- Almeno N indicatori in oversold (default: 3)
- Candela rossa (close < open)
- Entry tag dinamico: `buy_(rsi+bb+atr+macd+wr)`

## Sistema DCA e Position Management

### Leverage e Exposure Control
```python
def leverage(self) -> float:
    return 5.0

def get_total_position_value(self) -> float:
    # Calcola esposizione totale: stake_amount * 5 per ogni trade
    
global_limit = total_balance * 5  # Limite globale
per_pair_limit = global_limit / max_open_trades  # Limite per pair
```

### Custom Stake Amount
- **Primo ordine**: `total_balance * first_order_pct`
- **Limiti**: Rispetta global_limit e per_pair_limit
- **Controllo**: Verifica esposizione rimanente

### Calculate Max Orders (Dinamico)
Simula ordini DCA fino al limite per pair:
```python
for i in range(20):  # Max 20 ordini
    if i == 0:
        stake = total_balance * first_order_pct
    else:
        stake_pct = first_order_pct * (dca_multiplier ** (i-1))
        stake = total_balance * stake_pct
    
    position_value = stake * 5
    if cumulative_stake + position_value > per_pair_limit:
        break
```

### Adjust Trade Position (DCA Logic)

#### Controlli Preliminari
1. **Max Orders**: Rispetta limite dinamico calcolato
2. **Global Limit**: 95% del limite globale per sicurezza
3. **Available Balance**: Verifica fondi disponibili

#### Emergency DCA
Attivato quando:
- `current_loss >= emergency_dca_threshold` (default: -17%)
- `current_loss >= emergency_threshold * emergency_multiplier` (soglia critica)
- `current_rate < last_order_price` (solo in discesa)
- `trade.nr_of_successful_entries < max_orders`

#### Regular DCA
- **Distanza minima**: `dca_distance` dall'ultimo ordine
- **Solo in discesa**: `current_rate < last_order_price`
- **Stake progressivo**: `first_order_pct * (dca_multiplier ** entry_count)`

## Logica di Exit (custom_exit)

### 1. Auto-Reduce (Over-Exposure Protection)
```python
exposure_ratio = current_global_exposure / global_limit

if exposure_ratio > auto_reduce_threshold:  # >102.4%
    if exposure_ratio < auto_reduce_critical_threshold:  # <114.6%
        # Prova profit skimming se ultimo DCA profittevole
    else:
        # Auto-reduce proporzionale
        reduce_amount = (over_exposure * position_ratio) / 5
```

### 2. Last DCA Profit Skimming
Quando trade ha raggiunto max_orders:
- Verifica se ultimo DCA è profittevole
- Vende solo il PROFITTO dell'ultimo DCA
- `current_rate > last_order_price * (1 + last_dca_profit_threshold)`

### 3. Multi-Oscillator Overbought Exit
Quando `current_profit > min_profit_for_overbought_exit`:
- Conta indicatori overbought (stessa logica entry ma inversa)
- Richiede candela verde (`close > open`)
- Exit tag: `sell_overbought_(rsi+bb+atr+macd+wr)`

## Exit Tags e Significato
- `sell_auto_reduce_X`: Riduzione automatica per over-exposure
- `sell_last_dca_skim_X`: Profit skimming ultimo DCA
- `sell_last_dca_profit_X`: Profitto ultimo DCA
- `sell_overbought_(indicators)`: Exit multi-oscillator

## Caratteristiche Avanzate

### Protezioni Integrate
1. **Global Exposure Limit**: Previene over-leveraging
2. **Per-Pair Limit**: Distribuzione bilanciata
3. **Dynamic Max Orders**: Adatta DCA ai parametri ottimizzati
4. **Emergency DCA**: Protezione in situazioni critiche
5. **Auto-Reduce**: Gestione automatica over-exposure

### Tag Informativi
- Entry tags mostrano quali indicatori hanno triggerato
- Exit tags indicano motivo specifico dell'uscita
- Facilita analisi e debugging della strategia
