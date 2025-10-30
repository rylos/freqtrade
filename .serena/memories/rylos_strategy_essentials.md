# RyLoS Strategy - Essentials

## Core Info
- **File**: `user_data/strategies/RyLoSStrategy.py`
- **Type**: DCA long-only, 5m timeframe, 5x leverage
- **Logic**: Multi-oscillator oversold entry + overbought exit + auto-reduce

## Key Parameters (Hyperopt)
```python
# Entry (space='buy')
first_order_pct = DecimalParameter(0.005, 0.10, default=0.053)
dca_distance = DecimalParameter(0.002, 0.05, default=0.022)
dca_multiplier = DecimalParameter(1.5, 3.0, default=2.018)
min_oversold_count = IntParameter(2, 5, default=3)

# Exit (space='sell')
min_overbought_count = IntParameter(2, 5, default=4)
min_profit_for_overbought_exit = DecimalParameter(0.01, 0.10, default=0.013)
auto_reduce_threshold = DecimalParameter(1.0, 1.1, default=1.024)
```

## Entry Logic
5 oscillatori: RSI, BB%B, ATR, MACD, Williams%R
Entry quando ≥N oscillatori oversold + candela rossa

## Exit Logic
1. **Auto-reduce**: Over-exposure >102.4%
2. **Profit skimming**: Ultimo DCA profittevole
3. **Overbought exit**: ≥N oscillatori overbought + profit >1.3%

## DCA System
- Dynamic max orders based on balance limits
- Emergency DCA at -17% loss
- Progressive stake: `first_order_pct * (dca_multiplier ^ entry_count)`

## Commands
```bash
# Backtest
freqtrade backtesting --strategy RyLoSStrategy

# Hyperopt
freqtrade hyperopt --strategy RyLoSStrategy --hyperopt-loss CalmarRyLoSHyperOptLoss --epochs 100
```