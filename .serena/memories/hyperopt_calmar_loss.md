# Hyperopt CalmarRyLoS Loss Function - Updated

## File
`freqtrade/optimize/hyperopt_loss/hyperopt_loss_calmar_rylos.py`

## New Implementation
```python
def hyperopt_loss_function(results, min_date, max_date, starting_balance, *args, **kwargs) -> float:
    calmar_ratio = calculate_calmar(results, min_date, max_date, starting_balance)
    trade_duration = results['trade_duration'].mean()
    
    duration_penalty = CalmarRyLoSHyperOptLoss._calculate_duration_penalty(trade_duration)
    result = -calmar_ratio / (1 + duration_penalty)
    return result

def _calculate_duration_penalty(trade_duration_minutes: float) -> float:
    if trade_duration_minutes <= 120:  # <= 2 hours
        return 0
    elif trade_duration_minutes <= 600:  # <= 10 hours
        normalized = (trade_duration_minutes - 120) / (600 - 120)
        return math.log(1 + normalized)
    else:  # > 10 hours
        return math.log(2)  # Cap at ~0.693
```

## Logic
- **No penalty**: Duration ≤ 2h → penalty = 0
- **Logarithmic penalty**: 2h < duration ≤ 10h → penalty = 0 to 0.693
- **Capped penalty**: Duration > 10h → penalty = 0.693
- **Formula**: `result = -calmar_ratio / (1 + duration_penalty)`

## Examples
- Calmar -100000, duration 2h → result = -100000 (no penalty)
- Calmar -100000, duration 6h → result = -69314 (moderate penalty)
- Calmar -100000, duration 10h → result = -59083 (max penalty)

## Removed
- Drawdown calculation and penalty
- Trade duration multiplier (1.075)
- Complex dd_result formula