# Implementation Plan: ML-Driven RyLoS Strategy Reengineering

## Overview

This implementation plan converts RyLoSStrategyMLv3 from a hybrid approach (traditional indicators + minimal ML) to a 100% ML-driven strategy with multi-horizon predictions, scalping-optimized features, and advanced risk management.

**Key Changes:**
- 3 prediction horizons (15m, 30m, 1h) instead of 1
- 22 ML features (added 10 scalping indicators, removed 2 temporal)
- 100% ML-driven entry/DCA/exit decisions
- Optional ML confidence-based stake sizing
- Optional partial exit for profitable DCA orders
- Maintained: Emergency DCA, risk limits, DCA progression

## Tasks

- [x] 1. Update FreqAI feature engineering with scalping indicators
  - [x] 1.1 Remove temporal features from feature_engineering_standard
    - Remove `%-hour` feature calculation
    - Remove `%-day_of_week` feature calculation
    - _Requirements: 6.1, 6.2_
  
  - [x] 1.2 Add bb_percent to feature_engineering_expand_basic
    - Calculate Bollinger Bands (20-period, 2 std dev)
    - Calculate `%-bb_percent = (close - bb_lower) / (bb_upper - bb_lower)`
    - _Requirements: 6.3, 6.4_
  
  - [x] 1.3 Add MACD features to feature_engineering_expand_basic
    - Calculate MACD with 12,26,9 configuration
    - Add `%-macd`, `%-macd_signal`, `%-macd_hist` features
    - _Requirements: 6.5, 6.6, 6.7_
  
  - [x] 1.4 Add EMA features to feature_engineering_expand_basic
    - Calculate `%-ema_9` (9-period EMA)
    - Calculate `%-ema_21` (21-period EMA)
    - _Requirements: 6.8, 6.9_
  
  - [x] 1.5 Add CCI feature to feature_engineering_expand_basic
    - Calculate `%-cci` with 10-period for scalping
    - _Requirements: 6.10_
  
  - [x] 1.6 Add Supertrend feature to feature_engineering_expand_basic
    - Implement simplified Supertrend using ATR(10) with multiplier 3
    - Calculate `%-supertrend` as directional indicator
    - _Requirements: 6.11_
  
  - [x] 1.7 Add VWAP feature to feature_engineering_expand_basic
    - Calculate typical price: (high + low + close) / 3
    - Calculate `%-vwap` as cumulative volume-weighted average
    - _Requirements: 6.12_
  
  - [x] 1.8 Add OBV normalized feature to feature_engineering_expand_basic
    - Calculate On-Balance Volume using TA-Lib
    - Normalize by 20-period rolling mean
    - Add `%-obv_norm` feature
    - _Requirements: 6.13_

- [x] 2. Implement multi-horizon ML targets
  - [x] 2.1 Update set_freqai_targets to create 3 target columns
    - Calculate `&-s_close_15m`: (close[+3] - close) / close
    - Calculate `&-s_close_30m`: (close[+6] - close) / close
    - Calculate `&-s_close_1h`: (close[+12] - close) / close
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.6_
  
  - [x] 2.2 Implement get_ml_predictions method
    - Replace get_ml_prediction (single) with get_ml_predictions (tuple)
    - Return tuple: (pred_15m, pred_30m, pred_1h)
    - Handle missing predictions gracefully (return 0.0, 0.0, 0.0)
    - Use iloc[-1] for most recent candle
    - _Requirements: 1.5, 8.1, 8.2, 8.3, 8.4, 8.5, 8.6_

- [x] 3. Implement ML-driven entry logic
  - [x] 3.1 Add 9 ML threshold parameters
    - Add `ml_entry_threshold_15m` (default 0.005, range -0.01 to 0.02, space="buy")
    - Add `ml_entry_threshold_30m` (default 0.005, range -0.01 to 0.02, space="buy")
    - Add `ml_entry_threshold_1h` (default 0.005, range -0.01 to 0.02, space="buy")
    - Add `ml_dca_threshold_15m` (default -0.01, range -0.05 to 0.01, space="buy")
    - Add `ml_dca_threshold_30m` (default -0.01, range -0.05 to 0.01, space="buy")
    - Add `ml_dca_threshold_1h` (default -0.01, range -0.05 to 0.01, space="buy")
    - Add `ml_exit_threshold_15m` (default -0.005, range -0.02 to 0.01, space="sell")
    - Add `ml_exit_threshold_30m` (default -0.005, range -0.02 to 0.01, space="sell")
    - Add `ml_exit_threshold_1h` (default -0.005, range -0.02 to 0.01, space="sell")
    - _Requirements: 2.3, 2.4, 2.5, 3.3, 3.4, 3.5, 5.3, 5.4, 5.5, 7.1, 7.2, 7.3, 7.4, 7.5_
  
  - [x] 3.2 Replace populate_entry_trend with ML-based entry logic
    - Remove traditional indicator-based entry logic
    - Implement all-3-positive check: all horizons > their entry thresholds
    - Create entry tag: "buy_ml_all_positive_15m:{pred_15m:.4f}_30m:{pred_30m:.4f}_1h:{pred_1h:.4f}"
    - Set enter_long = 1 when all 3 conditions met
    - _Requirements: 2.1, 2.2, 2.6, 2.7_

- [x] 4. Implement ML-driven DCA logic
  - [x] 4.1 Update adjust_trade_position with ML-based DCA filtering
    - Get ML predictions for all 3 horizons
    - Count how many predictions exceed DCA thresholds
    - Allow DCA if 2 or more horizons are positive
    - Block DCA if fewer than 2 horizons are positive
    - Log which horizons passed/failed
    - _Requirements: 3.1, 3.2, 3.6_
  
  - [x] 4.2 Preserve emergency DCA bypass
    - Ensure emergency DCA logic executes BEFORE ML filtering
    - Emergency DCA should never check ML predictions
    - Maintain existing emergency_dca_threshold and emergency_critical_multiplier
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6_
  
  - [x] 4.3 Maintain existing DCA risk management
    - Keep calculate_max_orders() method unchanged
    - Keep get_dynamic_dca_distance() method unchanged
    - Keep per-pair and global limit checks
    - Keep DCA cooldown logic
    - _Requirements: 3.7, 3.8, 10.1, 10.2, 10.3, 10.4, 10.5, 10.6, 10.7, 10.8_

- [x] 5. Implement ML-driven exit logic
  - [x] 5.1 Update custom_exit with ML-based exit logic
    - Get ML predictions for all 3 horizons
    - Count how many predictions are below exit thresholds
    - Trigger exit if 2 or more horizons are negative
    - Require current_profit > min_profit_for_overbought_exit
    - Create exit tag: "sell_ml_2of3_negative_{horizons}"
    - Log which horizons were negative
    - _Requirements: 5.1, 5.2, 5.6, 5.7, 5.8_
  
  - [x] 5.2 Remove traditional indicator-based exit logic
    - Remove _count_overbought_indicators method
    - Remove multi-oscillator overbought checks
    - Keep min_profit_for_overbought_exit parameter
    - _Requirements: 12.1, 12.3_

- [x] 6. Clean up traditional indicator parameters and code
  - [x] 6.1 Remove traditional entry parameters
    - Remove rsi_oversold_threshold
    - Remove bb_oversold_threshold
    - Remove stochrsi_oversold_threshold
    - Remove williams_oversold_threshold
    - Remove min_oversold_count
    - _Requirements: 7.7, 12.2_
  
  - [x] 6.2 Remove traditional exit parameters
    - Remove rsi_overbought_threshold
    - Remove bb_overbought_threshold
    - Remove atr_overbought_multiplier
    - Remove stochrsi_overbought_threshold
    - Remove williams_overbought_threshold
    - Remove min_overbought_count
    - _Requirements: 7.7, 12.3_
  
  - [x] 6.3 Clean up populate_entry_trend and populate_exit_trend
    - Keep populate_entry_trend but return dataframe without setting enter_long
    - Keep populate_exit_trend but return dataframe without setting exit_long
    - _Requirements: 12.5, 12.6_
  
  - [x] 6.4 Remove auto_reduce logic
    - Remove auto_reduce_enabled parameter
    - Remove auto_reduce code from custom_exit
    - _Requirements: 12.7_
  
  - [x] 6.5 Keep indicator calculations in populate_indicators
    - Maintain RSI, StochRSI, BB, ATR, Williams calculations
    - These are still useful for debugging and potential future use
    - _Requirements: 12.4_

- [x] 7. Checkpoint - Test core ML functionality
  - Ensure all tests pass, ask the user if questions arise.

- [x] 8. Implement optional ML confidence-based stake sizing
  - [x] 8.1 Add confidence-based stake sizing parameters
    - Add `ml_stake_confidence_enabled` (BoolParameter, default False, space="buy")
    - Add `ml_confidence_min` (DecimalParameter, -0.02 to 0.0, default -0.01, space="buy")
    - Add `ml_confidence_max` (DecimalParameter, 0.01 to 0.05, default 0.02, space="buy")
    - _Requirements: 14.1, 14.9_
  
  - [x] 8.2 Update custom_stake_amount with confidence multiplier
    - Check if ml_stake_confidence_enabled is True
    - Calculate average prediction: (pred_15m + pred_30m + pred_1h) / 3
    - Map prediction to confidence multiplier (0.5 to 1.5)
    - Apply multiplier to base_stake
    - Ensure result respects per-pair and global limits
    - Log confidence multiplier when applied
    - _Requirements: 14.2, 14.3, 14.4, 14.5, 14.6, 14.7, 14.8, 14.10_

- [x] 9. Implement optional partial exit for profitable DCA orders
  - [x] 9.1 Add partial exit parameters
    - Add `ml_partial_exit_enabled` (BoolParameter, default False, space="sell")
    - Add `ml_partial_exit_profit_threshold` (DecimalParameter, 0.01 to 0.05, default 0.02, space="sell")
    - _Requirements: 15.1, 15.9_
  
  - [x] 9.2 Implement partial exit logic in custom_exit
    - Check if ml_partial_exit_enabled is True
    - Iterate through filled_entries[1:] (skip first order)
    - Calculate profit for each order: (current_rate - order.average) / order.average
    - Check if order profit > ml_partial_exit_profit_threshold
    - Get ML predictions and count negative horizons
    - If 2+ horizons negative, return -order.cost with partial exit tag
    - Log which order is being closed and its profit
    - _Requirements: 15.2, 15.3, 15.4, 15.5, 15.6, 15.7, 15.8, 15.10_

- [x] 10. Update PyTorch model for multi-target support
  - [x] 10.1 Update RyLoSPyTorchModel.fit() to detect multiple targets
    - Check number of target columns in data_dictionary
    - Set output_dim = number of targets (3 for multi-horizon)
    - Ensure model trains on all targets simultaneously
    - _Requirements: 13.1, 13.2, 13.3_
  
  - [x] 10.2 Ensure multi-target inference works correctly
    - Verify model returns predictions for all targets
    - Verify FreqAI populates separate columns for each target
    - Test backward compatibility with single-target configs
    - _Requirements: 13.4, 13.5, 13.6_

- [x] 11. Update logging for ML decisions
  - [x] 11.1 Add comprehensive logging for entry decisions
    - Log all 3 prediction values when entry is triggered
    - Log all 3 threshold values
    - Include pair name in log message
    - Format predictions to 4 decimal places
    - _Requirements: 11.1, 11.5, 11.6, 11.7_
  
  - [x] 11.2 Add comprehensive logging for DCA decisions
    - Log when DCA is blocked by ML (which horizons failed)
    - Log when DCA is allowed by ML (which 2+ horizons passed)
    - Include all 3 prediction values
    - _Requirements: 11.2, 11.3, 11.5, 11.6, 11.7_
  
  - [x] 11.3 Add comprehensive logging for exit decisions
    - Log all 3 prediction values when exit is triggered
    - Log which horizons were negative
    - Include pair name and profit percentage
    - _Requirements: 11.4, 11.5, 11.6, 11.7_

- [x] 12. Verify backward compatibility and Freqtrade documentation
  - [x] 12.1 Review Freqtrade official documentation
    - Check latest documentation for position adjustment hooks
    - Verify custom_stake_amount signature and behavior
    - Verify adjust_trade_position signature and return types
    - Verify custom_exit signature and return types
    - Check for any new callbacks or hooks that should be implemented
    - Review FreqAI integration best practices
    - _Requirements: 9.2, 9.4_
  
  - [x] 12.2 Verify FreqAI integration
    - Confirm self.freqai.start() is called first in populate_indicators
    - Confirm all feature names start with `%-`
    - Confirm all target names start with `&-`
    - _Requirements: 9.3, 9.4_
  
  - [x] 12.3 Verify strategy configuration
    - Confirm class name is "RyLoSStrategyMLv3"
    - Confirm timeframe = "5m"
    - Confirm leverage = 4.0
    - Confirm can_short = False
    - Confirm position_adjustment_enable = True
    - _Requirements: 9.1, 9.5, 9.6, 9.7, 9.8_
  
  - [x] 12.4 Verify risk management preservation
    - Test custom_stake_amount with various scenarios
    - Test calculate_max_orders with different parameters
    - Test get_dynamic_dca_distance with ATR variations
    - Test get_total_position_value with multiple trades
    - Verify per-pair limit: (balance × 4) / max_open_trades
    - Verify global limit: balance × 4
    - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.5, 10.6_

- [x] 13. Final checkpoint - Comprehensive testing
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Optional features (confidence sizing, partial exit) are disabled by default
- All ML decision logic uses the 3-horizon prediction system
- Emergency DCA always bypasses ML filtering (safety mechanism)
- Risk management (balance × 4 limit) is strictly enforced

## Testing Strategy

### Unit Tests
- Test feature engineering methods return correct number of features (22)
- Test set_freqai_targets creates 3 target columns with correct calculations
- Test get_ml_predictions returns tuple of 3 floats
- Test entry logic requires all 3 horizons positive
- Test DCA logic requires 2/3 horizons positive
- Test exit logic requires 2/3 horizons negative
- Test emergency DCA bypasses ML checks
- Test confidence-based stake sizing calculations
- Test partial exit only closes profitable orders
- Test risk limits are enforced (balance × 4)

### Integration Tests
- Test full entry flow: features → ML → predictions → entry signal
- Test full DCA flow: distance check → ML filter → stake calculation → limits
- Test full exit flow: profit check → ML predictions → exit signal
- Test emergency DCA flow: loss threshold → bypass ML → stake reduction
- Test partial exit flow: order profit → ML check → partial close
- Test with FreqAI: training → inference → strategy decisions

### Property-Based Tests
Not applicable for this implementation (strategy logic is deterministic given inputs)

## Deployment Steps

1. **Local Development**: Implement and test on local machine
2. **Hyperopt on debian-lifting**: 
   ```bash
   scp user_data/strategies/RyLoSStrategyMLv3.py marco@192.168.0.34:/opt/freqtrade/user_data/strategies/
   scp user_data/freqaimodels/RyLoSPyTorchModel.py marco@192.168.0.34:/opt/freqtrade/user_data/freqaimodels/
   
   ssh marco@192.168.0.34
   cd /opt/freqtrade
   freqtrade hyperopt -c user_data/config_ml.json \
     --strategy RyLoSStrategyMLv3 \
     --freqaimodel RyLoSPyTorchModel \
     --hyperopt-loss CalmarRyLoSHyperOptLoss \
     --epochs 1000 --spaces buy sell \
     --timerange 20241215-20260122 \
     -j 30
   ```

3. **Backtest Validation**: Run backtest with optimized parameters
4. **Deploy to AWS**: Copy to live trading server
5. **Dry-run**: Test in paper trading mode for 24-48 hours
6. **Live Trading**: Switch to live mode if stable

## Configuration Recommendations

Update `user_data/config_ml.json` for 22 features:
```json
{
  "model_training_parameters": {
    "learning_rate": 3e-4,
    "trainer_kwargs": {
      "batch_size": 128,
      "n_epochs": 15
    },
    "model_kwargs": {
      "hidden_dim": 128,
      "dropout_percent": 0.2,
      "n_layer": 2
    }
  }
}
```

Rationale: More features (22 vs 14) benefit from larger hidden_dim and more epochs.
