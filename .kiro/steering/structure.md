# Struttura Progetto RyLoS

## File Principali

```
user_data/
├── strategies/
│   └── RyLoSStrategy.py              # Strategia principale
├── config.json                        # Configurazione bot
├── backtest_results/                  # Risultati backtesting
└── hyperopt_results/                  # Risultati ottimizzazione

freqtrade/optimize/hyperopt_loss/
└── hyperopt_loss_calmar_rylos.py     # Loss function personalizzata
```

## RyLoSStrategy.py

### Struttura Classe
```python
class RyLoSStrategy(IStrategy):
    # Configurazione base
    timeframe = '5m'
    can_short = False
    stoploss = -1
    minimal_roi = {"0": 0.5}
    
    # Parametri ottimizzabili (20 attivi)
    # - Buy space: 10 parametri
    # - Sell space: 7 parametri
    # - Trailing: 3 parametri (hardcoded)
    
    # Metodi principali
    def populate_indicators()      # Calcola RSI, BB, StochRSI, Williams, ATR
    def populate_entry_trend()     # Multi-oscillator oversold + DCA logic
    def populate_exit_trend()      # Multi-oscillator overbought
    def custom_stake_amount()      # Gestione stake DCA progressivo
```

### Logica Entry
1. **First Order**: ≥2 oscillatori oversold + candela rossa
2. **DCA Standard**: Distanza dinamica (base + ATR), cooldown 2 candles
3. **Emergency DCA**: Trigger a -12.4% loss, critical a -14.6%

### Logica Exit
- ≥4 oscillatori overbought + profit >1.7% + candela verde
- Trailing stop attivo dopo offset

## hyperopt_loss_calmar_rylos.py

### Formula
```python
result = -calmar_ratio / (1 + duration_penalty)

duration_penalty:
- ≤2h: 0
- 2h-10h: log(1 + normalized)  # 0 to 0.693
- >10h: log(2) = 0.693 (capped)
```

### Obiettivo
Massimizzare Calmar Ratio penalizzando trade lunghi (>2h).

## Configurazione

### config.json - Sezioni Chiave
```json
{
  "strategy": "RyLoSStrategy",
  "max_open_trades": 10,
  "stake_amount": "unlimited",
  "tradable_balance_ratio": 1.0,
  "trading_mode": "futures",
  "margin_mode": "isolated",
  
  "entry_pricing": {
    "price_side": "other",        # Esecuzione immediata
    "use_order_book": true,
    "order_book_top": 2
  },
  
  "exit_pricing": {
    "price_side": "other",
    "use_order_book": true,
    "order_book_top": 2
  }
}
```

## Indicatori Utilizzati

Tutti con periodo 10 (ottimizzabile):
- **RSI(10)**: Momentum
- **StochRSI(10,5,3)**: Momentum stocastico
- **Williams %R(10)**: Momentum inverso
- **ATR(10)**: Volatilità per DCA dinamico
- **BBANDS(20,2.0)**: Bollinger Bands per BB%

## Convenzioni Codice

### Naming
- Parametri: `snake_case` con suffisso descrittivo (`rsi_oversold_threshold`)
- Condizioni: `condition_name` (es. `oversold_condition`)
- Tags: `buy_/sell_` prefix (es. `buy_rsi_bb_stochrsi_wr`)

### Operazioni Vettoriali
```python
# ✅ CORRETTO
dataframe.loc[conditions, 'enter_long'] = 1

# ❌ SBAGLIATO
if dataframe['rsi'] > 30:
    dataframe['enter_long'] = 1
```

### Type Hints Obbligatori
```python
def custom_stake_amount(
    self,
    pair: str,
    current_time: datetime,
    current_rate: float,
    proposed_stake: float,
    min_stake: Optional[float],
    max_stake: float,
    leverage: float,
    entry_tag: Optional[str],
    side: str,
    **kwargs
) -> float:
```

## Workflow Sviluppo

1. **Modifica strategia**: `user_data/strategies/RyLoSStrategy.py`
2. **Test locale**: `freqtrade backtesting -c config.json`
3. **Ottimizzazione**: `freqtrade hyperopt -c config.json --hyperopt-loss CalmarRyLoSHyperOptLoss`
4. **Validazione**: Analisi risultati, verifica overfitting
5. **Deploy**: Dry-run → Live trading
