# RyLoS MLv3 - Short Implementation Summary

## Modifiche Implementate

### 1. Configurazione Base
- ✅ `can_short = True` - Abilitato supporto short
- ✅ `max_open_trades = 2` - Permette 1 long + 1 short simultanei

### 2. Parametri Ottimizzabili

**TOTALE: 42 parametri (21 long + 21 short)**

#### Buy Space (30 parametri: 15 long + 15 short)

**LONG Parameters:**
1. `ml_dca_distance_tight_long` = 0.0245 (range: 0.015-0.025)
2. `ml_dca_distance_wide_long` = 0.0422 (range: 0.035-0.055)
3. `ml_dca_pred_min_long` = -0.003 (range: -0.02 to 0.0)
4. `ml_dca_pred_max_long` = 0.0117 (range: 0.01-0.04)
5. `first_order_pct_long` = 0.017 (range: 0.005-0.03)
6. `dca_multiplier_long` = 2.656 (range: 1.5-3.0)
7. `dca_atr_multiplier_long` = 1.766 (range: 0.5-3.0)
8. `dca_cooldown_candles_long` = 2 (range: 1-5) **[NOW OPTIMIZABLE]**
9. `ml_entry_threshold_long` = 0.0012 (range: -0.01 to 0.01)
10. `ml_entry_5m_min_long` = -0.001 (range: -0.005 to 0.005)
11. `ml_dca_threshold_long` = -0.0099 (range: -0.02 to 0.02)
12. `ml_weight_5m_long` = 0.81 (range: 0.1-3.0)
13. `ml_weight_15m_long` = 2.17 (range: 0.1-3.0)
14. `ml_weight_30m_long` = 2.6 (range: 0.1-3.0)
15. `ml_confidence_min_long` = -0.0065 (range: -0.02 to 0.0) [OPTIONAL]
16. `ml_confidence_max_long` = 0.0417 (range: 0.01-0.05) [OPTIONAL]

**SHORT Parameters (simmetrici invertiti):**
1. `ml_dca_distance_tight_short` = 0.0245 (range: 0.015-0.025)
2. `ml_dca_distance_wide_short` = 0.0422 (range: 0.035-0.055)
3. `ml_dca_pred_min_short` = **-0.0117** (range: **-0.04 to -0.01**) ⚠️ INVERTITO
4. `ml_dca_pred_max_short` = **0.003** (range: **0.0 to 0.02**) ⚠️ INVERTITO
5. `first_order_pct_short` = 0.017 (range: 0.005-0.03)
6. `dca_multiplier_short` = 2.656 (range: 1.5-3.0)
7. `dca_atr_multiplier_short` = 1.766 (range: 0.5-3.0)
8. `dca_cooldown_candles_short` = 2 (range: 1-5) **[NOW OPTIMIZABLE]**
9. `ml_entry_threshold_short` = **-0.0012** (range: -0.01 to 0.01) ⚠️ INVERTITO
10. `ml_entry_5m_min_short` = **0.001** (range: -0.005 to 0.005) ⚠️ INVERTITO
11. `ml_dca_threshold_short` = **0.0099** (range: -0.02 to 0.02) ⚠️ INVERTITO
12. `ml_weight_5m_short` = 0.81 (range: 0.1-3.0)
13. `ml_weight_15m_short` = 2.17 (range: 0.1-3.0)
14. `ml_weight_30m_short` = 2.6 (range: 0.1-3.0)
15. `ml_confidence_min_short` = **0.0065** (range: **0.0 to 0.02**) ⚠️ INVERTITO
16. `ml_confidence_max_short` = **-0.0417** (range: **-0.05 to -0.01**) ⚠️ INVERTITO

#### Sell Space (10 parametri: 5 long + 5 short)

**LONG Parameters:**
1. `ml_exit_threshold_long` = -0.001 (range: -0.01 to 0.01)
2. `min_profit_for_ml_exit_long` = 0.01 (range: 0.005-0.03)
3. `crash_detection_threshold_long` = -0.06 (range: -0.10 to -0.03)
4. `ml_drawdown_1h_threshold_long` = -0.10 (range: -0.15 to -0.05)
5. `ml_drawdown_2h_threshold_long` = -0.15 (range: -0.20 to -0.08)

**SHORT Parameters (simmetrici invertiti):**
1. `ml_exit_threshold_short` = **0.001** (range: -0.01 to 0.01) ⚠️ INVERTITO
2. `min_profit_for_ml_exit_short` = 0.01 (range: 0.005-0.03)
3. `crash_detection_threshold_short` = **0.06** (range: **0.03 to 0.10**) ⚠️ INVERTITO (pump detection)
4. `ml_drawdown_1h_threshold_short` = **0.10** (range: **0.05 to 0.15**) ⚠️ INVERTITO
5. `ml_drawdown_2h_threshold_short` = **0.15** (range: **0.08 to 0.20**) ⚠️ INVERTITO

### 3. Logica Entry/Exit

#### Entry Logic

**LONG:**
```python
# Entry quando weighted_pred > threshold AND 5m > min
weighted_pred_long > ml_entry_threshold_long
pred_5m > ml_entry_5m_min_long
```

**SHORT:**
```python
# Entry quando weighted_pred < threshold AND 5m < min (INVERTITO)
weighted_pred_short < ml_entry_threshold_short
pred_5m < ml_entry_5m_min_short
```

#### DCA Logic

**LONG:**
- DCA quando prezzo SCENDE (`current_rate < last_order_rate`)
- Block DCA se `weighted_pred < ml_dca_threshold_long`

**SHORT:**
- DCA quando prezzo SALE (`current_rate > last_order_rate`) ⚠️ INVERTITO
- Block DCA se `weighted_pred > ml_dca_threshold_short` ⚠️ INVERTITO

#### Exit Logic

**LONG:**
- Exit quando `pred_5m < ml_exit_threshold_long` (prezzo atteso scendere)
- Crash detection: drop > threshold

**SHORT:**
- Exit quando `pred_5m > ml_exit_threshold_short` (prezzo atteso salire) ⚠️ INVERTITO
- Pump detection: rise > threshold ⚠️ INVERTITO

#### Stoploss Logic

**LONG:**
- Drawdown prediction: `pred_dd < threshold` (prezzo atteso scendere)
- Crash detection: drop > threshold

**SHORT:**
- Drawdown prediction: `pred_dd > threshold` (prezzo atteso salire) ⚠️ INVERTITO
- Pump detection: rise > threshold ⚠️ INVERTITO

### 4. Metodi Modificati

Tutti i metodi ora accettano/gestiscono il parametro `side`:

1. ✅ `get_weighted_ml_prediction(pair, side="long")`
2. ✅ `get_dynamic_dca_distance(pair, current_rate, side="long")`
3. ✅ `calculate_max_orders(total_balance, side="long")`
4. ✅ `custom_stake_amount(..., side, ...)` - usa parametri side-specific
5. ✅ `adjust_trade_position(...)` - logica DCA side-specific
6. ✅ `populate_entry_trend(...)` - genera segnali long E short
7. ✅ `populate_exit_trend(...)` - gestito da custom_exit
8. ✅ `custom_stoploss(...)` - logica side-specific
9. ✅ `custom_exit(...)` - logica side-specific
10. ✅ `populate_indicators(...)` - log side-specific

### 5. Config Necessarie

```json
{
  "max_open_trades": 2,
  "stake_amount": "unlimited",
  "tradable_balance_ratio": 1.0,
  "trading_mode": "futures",
  "margin_mode": "isolated",
  "exchange": {
    "name": "bybit"
  }
}
```

## Hyperopt Command

```bash
# Ottimizza SOLO parametri short (long già ottimizzati)
freqtrade hyperopt \
  -c user_data/config_ml.json \
  --strategy RyLoSStrategyMLv3 \
  --freqaimodel RyLoSPyTorchModel \
  --hyperopt-loss ProfitDrawdownDurationHyperOptLoss \
  --epochs 6000 \
  --spaces buy sell \
  --timerange 20241215-20260126 \
  -j 30
```

**NOTA**: Hyperopt ottimizzerà TUTTI i 42 parametri. Per ottimizzare solo short:
1. Prima ottimizza long (già fatto)
2. Fissa parametri long nel codice (`optimize=False`)
3. Ottimizza solo parametri short

## Testing

```bash
# Backtest con short abilitato
freqtrade backtesting \
  -c user_data/config_ml.json \
  --strategy RyLoSStrategyMLv3 \
  --freqaimodel RyLoSPyTorchModel \
  --timerange 20241215-20260126

# Dry-run
freqtrade trade \
  -c user_data/config_ml.json \
  --strategy RyLoSStrategyMLv3 \
  --freqaimodel RyLoSPyTorchModel \
  --dry-run
```

## Sync to Servers

```bash
# debian.ts (hyperopt)
scp user_data/strategies/RyLoSStrategyMLv3.py marco@debian.ts:/opt/freqtrade/user_data/strategies/

# AWS (live trading)
scp user_data/strategies/RyLoSStrategyMLv3.py admin@amazon.ziliani.net:/opt/freqtrade/user_data/strategies/
scp user_data/strategies/RyLoSStrategyMLv3.py admin@amazon.ziliani.net:/opt/freqtrade-hl/user_data/strategies/
```

## Rischi e Considerazioni

### Esposizione Leverage
- **Long 4x + Short 4x = 8x esposizione totale**
- Con `max_open_trades=2` e balance $1000:
  - Long: $1000 × 4 = $4000 esposizione
  - Short: $1000 × 4 = $4000 esposizione
  - **TOTALE: $8000 esposizione su $1000 capital**

### Risk Management
- Stoploss -10% su posizione = -40% su capital (con 4x leverage)
- Con long+short simultanei: possibile loss -80% su capital se entrambi vanno male
- **CONSIGLIO**: Inizia con `max_open_trades=1` per testare

### Hyperopt Complexity
- 42 parametri da ottimizzare (vs 21 originali)
- Tempo hyperopt raddoppiato (~12000 epochs consigliati)
- Rischio overfitting aumentato

### Strategia Consigliata
1. **Fase 1**: Testa con `max_open_trades=1` (o long o short)
2. **Fase 2**: Ottimizza parametri short separatamente
3. **Fase 3**: Testa con `max_open_trades=2` (long+short simultanei)
4. **Fase 4**: Live trading con capital ridotto

## Differenze Chiave Long vs Short

| Aspetto | LONG | SHORT |
|---------|------|-------|
| **Entry** | `weighted_pred > threshold` | `weighted_pred < threshold` |
| **DCA Trigger** | Prezzo scende | Prezzo sale |
| **DCA Block** | `pred < threshold` | `pred > threshold` |
| **Exit** | `pred_5m < threshold` | `pred_5m > threshold` |
| **Crash Detection** | Drop > threshold | Rise > threshold |
| **Drawdown Pred** | `pred_dd < threshold` | `pred_dd > threshold` |

## Status

✅ **IMPLEMENTAZIONE COMPLETATA**

- [x] Parametri long rinominati con suffisso `_long`
- [x] Parametri short creati con default simmetrici invertiti
- [x] `dca_cooldown_candles` ora ottimizzabile (`optimize=True`)
- [x] Tutti i metodi aggiornati per gestire `side`
- [x] Logica entry/exit/DCA/stoploss side-specific
- [x] Log aggiornati per mostrare long E short
- [x] Nessun errore di sintassi (solo warning minori)

**PRONTO PER TESTING E HYPEROPT!**
