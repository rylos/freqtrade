# Documentazione Strategia Freqtrade

## Struttura Base Strategia

### Componenti Principali
- **Classe**: Eredita da `IStrategy`
- **INTERFACE_VERSION**: 3 (versione corrente)
- **timeframe**: Es. '15m', '1h', '4h'
- **stoploss**: Percentuale perdita massima (es. -0.10 = -10%)
- **minimal_roi**: ROI minimo per uscita automatica

### Metodi Obbligatori
```python
def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
    # Calcola indicatori tecnici
    return dataframe

def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
    # Definisce segnali di entrata (enter_long/enter_short)
    return dataframe

def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
    # Definisce segnali di uscita (exit_long/exit_short)
    return dataframe
```

## Dataframe e Operazioni Vettoriali

### Struttura Dataframe
- Colonne base: date, open, high, low, close, volume
- Indicatori aggiunti come nuove colonne
- Ogni riga = una candela completa

### Operazioni Vettoriali (OBBLIGATORIE)
```python
# ❌ SBAGLIATO - non funziona
if dataframe['rsi'] > 30:
    dataframe['enter_long'] = 1

# ✅ CORRETTO - operazione vettoriale
dataframe.loc[(dataframe['rsi'] > 30), 'enter_long'] = 1
```

### Evitare Lookahead Bias
- Non usare `df.iloc[-1]` (dati futuri)
- Usare `df.shift()` per dati precedenti
- Backtesting passa tutto il range temporale insieme

## Callbacks Disponibili

### Callback Principali
- `bot_start()`: Eseguito una volta all'avvio
- `bot_loop_start()`: Ogni iterazione del bot
- `custom_stake_amount()`: Gestione dimensione posizione
- `custom_exit()`: Logica uscita personalizzata per trade
- `custom_stoploss()`: Stoploss dinamico/trailing
- `custom_roi()`: ROI personalizzato
- `confirm_trade_entry()/exit()`: Conferma trade
- `adjust_trade_position()`: Modifica posizioni aperte

### Confronto Logiche di Uscita
- **populate_exit_trend()**: Segnali basati su indicatori (vettoriale)
- **custom_exit()**: Logica per singolo trade (usa dati trade)
- **custom_stoploss()**: Solo per stoploss dinamico
- **custom_roi()**: Solo per ROI dinamico

## Gestione Stoploss

### Tipi di Stoploss

#### 1. Static Stoploss
```python
stoploss = -0.10  # -10% perdita massima
```

#### 2. Trailing Stoploss
```python
stoploss = -0.10
trailing_stop = True
# Segue il prezzo verso l'alto, mantiene distanza fissa
```

#### 3. Trailing Stoploss con Offset Positivo
```python
stoploss = -0.10
trailing_stop = True
trailing_stop_positive = 0.02  # -2% quando in profitto
trailing_stop_positive_offset = 0.01  # Attiva a +1% profitto
trailing_only_offset_is_reached = True  # Solo dopo offset
```

#### 4. Custom Stoploss (Callback)
```python
def custom_stoploss(self, pair: str, trade: Trade, current_time: datetime,
                   current_rate: float, current_profit: float, **kwargs) -> float:
    # Logica personalizzata per stoploss dinamico
    if current_profit > 0.20:  # Se profitto > 20%
        return 0.05  # Stoploss a +5%
    elif current_profit > 0.10:  # Se profitto > 10%
        return -0.02  # Stoploss a -2%
    return self.stoploss  # Stoploss default
```

### Stoploss On-Exchange

#### Configurazione
```python
order_types = {
    "stoploss": "market",  # o "limit"
    "stoploss_on_exchange": True,
    "stoploss_on_exchange_interval": 60,  # Aggiorna ogni 60s
    "stoploss_on_exchange_limit_ratio": 0.99  # Per ordini limit
}
```

#### Exchange Supportati
- **Binance**: spot (limit), futures (market/limit)
- **Gate.io**: spot/futures (limit)
- **OKX**: spot/futures (limit)
- **Kraken**: spot (market/limit)
- **Bybit**: solo futures (market/limit)

### Parametri Futures
```python
stoploss_price_type = "mark"  # "last", "mark", "index"
```

### Helper Functions
```python
from freqtrade.strategy import stoploss_from_open, stoploss_from_absolute

# Stoploss basato su prezzo di apertura
stoploss_from_open(0.02, current_profit, is_short=False)

# Stoploss da prezzo assoluto
stoploss_from_absolute(stop_price, current_rate, is_short=False)
```

## Imports Standard
```python
import numpy as np
import pandas as pd
from datetime import datetime, timedelta, timezone
from pandas import DataFrame
from typing import Dict, Optional, Union, Tuple
from freqtrade.strategy import (
    IStrategy, Trade, Order, PairLocks, informative,
    BooleanParameter, CategoricalParameter, DecimalParameter, IntParameter, RealParameter,
    timeframe_to_minutes, timeframe_to_next_date, timeframe_to_prev_date,
    merge_informative_pair, stoploss_from_absolute, stoploss_from_open,
)
import talib.abstract as ta
from technical import qtpylib
```

## Best Practices
1. Usare operazioni vettoriali sempre
2. Evitare loop nei metodi populate_*
3. Testare con lookahead-analysis e recursive-analysis
4. Dry run prima del live trading
5. Calcoli pesanti solo nei callback necessari
6. Mantenere colonne OHLCV intatte
7. Non impostare stoploss troppo stretti con stoploss_on_exchange
8. Usare custom_stoploss per logiche dinamiche complesse
