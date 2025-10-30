# RyLoS Strategy - Miglioramenti Timing DCA

## Modifiche Implementate (2025-10-20)

### 1. Import Aggiunti
```python
from freqtrade.strategy import DecimalParameter, IntParameter, IStrategy, Trade, timeframe_to_minutes
from datetime import datetime, timedelta, timezone
```

### 2. Controlli Timing in adjust_trade_position()

#### Controllo Ordini Aperti (Punto 4)
```python
# Punto 4: Non agire se ci sono ordini aperti
if trade.has_open_orders:
    return None
```
**Effetto**: Previene chiamate multiple mentre un ordine è in attesa di riempimento.

#### Controllo Timing 1 Candela (Punto 2)
```python
# Punto 2: Aspetta almeno 1 candela dall'ultimo DCA
filled_entries = trade.select_filled_orders(trade.entry_side)
if len(filled_entries) > 0:
    last_order_time = filled_entries[-1].order_filled_date.replace(tzinfo=timezone.utc)
    min_wait_time = timedelta(minutes=timeframe_to_minutes(self.timeframe))
    if (current_time - min_wait_time) < last_order_time:
        return None
```
**Effetto**: Garantisce minimo 5 minuti (1 candela) tra DCA consecutivi.

### 3. Tag DCA Parlanti

#### Tipo di Ritorno Aggiornato
```python
) -> float | tuple[float, str] | None:
```

#### Tag Emergency DCA
```python
return emergency_stake, f"emergency_dca_{loss_pct:.1f}%"
```
**Esempio**: `emergency_dca_15.3%`

#### Tag DCA Normale
```python
return next_stake, f"dca_{entry_count + 1}_{current_profit*100:.1f}%"
```
**Esempio**: `dca_3_-8.2%`

## Comportamento Risultante

### Live Trading
- **Frequenza**: adjust_trade_position() chiamata ogni ~5 secondi
- **Blocchi**: Nessun DCA se ordini aperti
- **Timing**: Minimo 5 minuti tra DCA
- **Tag**: Tracciamento dettagliato di ogni DCA

### Backtest vs Live
- **Backtest**: 1 chiamata per candela (più conservativo)
- **Live**: Chiamate continue ogni 5s (più aggressivo)
- **Miglioramento**: Controllo timing riduce le differenze

### Simulazione Esempio
Timeline con prezzo in discesa da $100:
- 10:00 - Entry $100 (oversold_multi)
- 10:10 - DCA #2 $99 (dca_2_-1.0%) - 278$
- 10:20 - DCA #3 $97.5 (dca_3_-2.1%) - 774$
- 10:30 - DCA #4 $95 (dca_4_-4.8%) - 2,154$
- 10:40 - Emergency DCA $85 (emergency_dca_12.5%) - 5,994$

## Vantaggi
1. **Controllo spam DCA**: Evita ordini troppo frequenti
2. **Gestione ordini**: Previene conflitti con ordini aperti
3. **Tracciabilità**: Tag dettagliati per ogni DCA
4. **Coerenza**: Migliore allineamento backtest/live
5. **Debugging**: Più facile identificare problemi DCA

## File Modificati
- `/home/marco/dev/freqtrade/user_data/strategies/RyLoSStrategy.py`
- Aggiunti controlli timing e tag DCA
- Mantenuta logica DCA esistente intatta