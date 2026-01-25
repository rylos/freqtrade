# Requirements Document

## Introduction

This document specifies the requirements for reengineering the RyLoS trading strategy (RyLoSStrategyMLv3.py) to be 100% ML-driven with multi-horizon predictions. The current strategy uses traditional technical indicators for entry/exit decisions with minimal ML filtering. The reengineered strategy will make all trading decisions based on machine learning predictions across three time horizons (15 minutes, 30 minutes, and 1 hour), while maintaining the proven DCA (Dollar Cost Averaging) risk management framework.

## Glossary

- **Strategy**: The RyLoSStrategyMLv3 class that implements trading logic
- **FreqAI**: Freqtrade's machine learning framework for training and inference
- **ML_Model**: The PyTorch neural network model (RyLoSPyTorchModel)
- **Target**: The prediction output from ML (price change percentage)
- **Feature**: Input data for ML model (technical indicators, price data)
- **Horizon**: Time period for prediction (15min, 30min, 1h)
- **Entry**: Opening a new trade position
- **DCA**: Dollar Cost Averaging - adding to existing position at lower prices
- **Exit**: Closing a trade position
- **Emergency_DCA**: Safety mechanism for positions with large unrealized losses
- **Threshold**: ML prediction value that triggers trading decisions
- **Position**: Open trade with one or more entry orders
- **Leverage**: Multiplier for position size (fixed at 4x)
- **Stake**: Amount of capital allocated to an order

## Requirements

### Requirement 1: Multi-Horizon ML Predictions

**User Story:** As a trader, I want the strategy to predict price movements across multiple time horizons, so that I can make more informed trading decisions based on short, medium, and long-term trends.

#### Acceptance Criteria

1. WHEN the Strategy calculates ML targets, THE Strategy SHALL create three separate target columns for 15-minute, 30-minute, and 1-hour horizons
2. THE Strategy SHALL calculate the 15-minute target as the percentage price change from current close to close price 3 candles ahead
3. THE Strategy SHALL calculate the 30-minute target as the percentage price change from current close to close price 6 candles ahead
4. THE Strategy SHALL calculate the 1-hour target as the percentage price change from current close to close price 12 candles ahead
5. WHEN the ML_Model performs inference, THE Strategy SHALL retrieve all three prediction values for the current candle
6. THE Strategy SHALL name the target columns "&-s_close_15m", "&-s_close_30m", and "&-s_close_1h"

### Requirement 2: ML-Driven Entry Logic

**User Story:** As a trader, I want entry decisions to be based entirely on ML predictions, so that the strategy can identify optimal entry points without relying on fixed technical indicator thresholds.

#### Acceptance Criteria

1. WHEN evaluating a potential first entry, THE Strategy SHALL check all three ML prediction horizons
2. IF all three predictions (15m, 30m, 1h) are above their respective entry thresholds, THEN THE Strategy SHALL signal an entry
3. THE Strategy SHALL provide three optimizable entry threshold parameters: ml_entry_threshold_15m, ml_entry_threshold_30m, ml_entry_threshold_1h
4. THE Strategy SHALL set default entry thresholds to 0.005 (0.5% expected gain)
5. THE Strategy SHALL allow entry thresholds to be optimized in the range -0.01 to 0.02
6. WHEN an ML-based entry is triggered, THE Strategy SHALL tag the entry with "buy_ml_all_positive" plus the prediction values
7. THE Strategy SHALL remove all traditional technical indicator logic from the entry decision

### Requirement 3: ML-Driven DCA Logic

**User Story:** As a trader, I want DCA (Dollar Cost Averaging) decisions to be filtered by ML predictions, so that I only add to positions when the ML model indicates favorable conditions.

#### Acceptance Criteria

1. WHEN evaluating a standard DCA opportunity, THE Strategy SHALL check all three ML prediction horizons
2. IF at least 2 out of 3 predictions are above their respective DCA thresholds, THEN THE Strategy SHALL allow the DCA
3. THE Strategy SHALL provide three optimizable DCA threshold parameters: ml_dca_threshold_15m, ml_dca_threshold_30m, ml_dca_threshold_1h
4. THE Strategy SHALL set default DCA thresholds to -0.01 (-1% expected change)
5. THE Strategy SHALL allow DCA thresholds to be optimized in the range -0.05 to 0.01
6. WHEN an ML-filtered DCA is executed, THE Strategy SHALL tag it with "dca_ml_2of3" plus which horizons were positive
7. THE Strategy SHALL maintain existing DCA distance, cooldown, and stake progression logic
8. THE Strategy SHALL maintain existing per-pair and global position limits

### Requirement 4: ML-Driven Exit Logic

**User Story:** As a trader, I want exit decisions to be based on ML predictions, so that the strategy can identify optimal exit points and avoid premature exits.

#### Acceptance Criteria

1. WHEN evaluating a potential exit, THE Strategy SHALL check all three ML prediction horizons
2. IF at least 2 out of 3 predictions are below their respective exit thresholds, THEN THE Strategy SHALL signal an exit
3. THE Strategy SHALL provide three optimizable exit threshold parameters: ml_exit_threshold_15m, ml_exit_threshold_30m, ml_exit_threshold_1h
4. THE Strategy SHALL set default exit thresholds to -0.005 (-0.5% expected decline)
5. THE Strategy SHALL allow exit thresholds to be optimized in the range -0.02 to 0.01
6. WHEN an ML-based exit is triggered, THE Strategy SHALL tag it with "sell_ml_2of3_negative" plus which horizons were negative
7. THE Strategy SHALL remove all traditional technical indicator logic from the exit decision
8. THE Strategy SHALL maintain the minimum profit requirement before allowing exits

### Requirement 5: Feature Engineering Optimization for Scalping

**User Story:** As a developer, I want the ML model to use scalping-optimized technical indicators as features, so that predictions are based on proven short-term trading signals without temporal bias.

#### Acceptance Criteria

1. THE Strategy SHALL remove the "%-hour" feature from feature_engineering_standard
2. THE Strategy SHALL remove the "%-day_of_week" feature from feature_engineering_standard
3. THE Strategy SHALL add "%-bb_percent" feature to feature_engineering_expand_basic
4. THE Strategy SHALL calculate bb_percent as (close - bb_lower) / (bb_upper - bb_lower) using 20-period Bollinger Bands
5. THE Strategy SHALL add "%-macd" feature (MACD line from 12,26,9 configuration)
6. THE Strategy SHALL add "%-macd_signal" feature (signal line from MACD)
7. THE Strategy SHALL add "%-macd_hist" feature (MACD histogram)
8. THE Strategy SHALL add "%-ema_9" feature (9-period EMA for short-term trend)
9. THE Strategy SHALL add "%-ema_21" feature (21-period EMA for medium-term trend)
10. THE Strategy SHALL add "%-cci" feature (Commodity Channel Index with 10-period for scalping)
11. THE Strategy SHALL add "%-supertrend" feature (Supertrend indicator with ATR(10,3) configuration)
12. THE Strategy SHALL add "%-vwap" feature (Volume Weighted Average Price)
13. THE Strategy SHALL add "%-obv" feature (On-Balance Volume normalized by rolling mean)
14. THE Strategy SHALL maintain all existing features: rsi, atr_pct, stochrsi, williams, pct_change, pct_change_vol, adx
15. THE Strategy SHALL maintain all existing expanded features: rsi_10, bb_width_10, volume_ratio_10
16. WHEN FreqAI trains the model, THE ML_Model SHALL use the updated feature set with 22 total features

### Requirement 6: Hyperopt Parameter Space

**User Story:** As a trader, I want to optimize ML thresholds through hyperopt, so that I can find the best threshold values for my trading conditions.

#### Acceptance Criteria

1. THE Strategy SHALL define 9 DecimalParameter instances for ML thresholds
2. THE Strategy SHALL mark all 9 ML threshold parameters as optimizable (optimize=True)
3. THE Strategy SHALL assign entry thresholds to the "buy" space
4. THE Strategy SHALL assign DCA thresholds to the "buy" space
5. THE Strategy SHALL assign exit thresholds to the "sell" space
6. THE Strategy SHALL maintain all existing DCA parameters (first_order_pct, dca_distance, dca_multiplier, dca_atr_multiplier)
7. THE Strategy SHALL remove traditional indicator threshold parameters (rsi_oversold_threshold, bb_oversold_threshold, etc.)

### Requirement 7: ML Prediction Retrieval

**User Story:** As a developer, I want clean methods to retrieve ML predictions, so that the strategy code is maintainable and testable.

#### Acceptance Criteria

1. THE Strategy SHALL implement a method get_ml_predictions(pair: str) that returns all three horizon predictions
2. THE Strategy SHALL return predictions as a tuple (pred_15m, pred_30m, pred_1h)
3. WHEN ML predictions are not available, THE Strategy SHALL return (0.0, 0.0, 0.0)
4. THE Strategy SHALL retrieve predictions from the analyzed dataframe columns "&-s_close_15m", "&-s_close_30m", "&-s_close_1h"
5. THE Strategy SHALL use the most recent candle (iloc[-1]) for prediction values
6. THE Strategy SHALL handle missing columns gracefully without raising exceptions

### Requirement 8: Backward Compatibility

**User Story:** As a developer, I want the reengineered strategy to work with existing FreqAI infrastructure, so that I don't need to modify config files or the PyTorch model.

#### Acceptance Criteria

1. THE Strategy SHALL maintain the class name "RyLoSStrategyMLv3"
2. THE Strategy SHALL maintain compatibility with the existing RyLoSPyTorchModel
3. THE Strategy SHALL call self.freqai.start() in populate_indicators before calculating indicators
4. THE Strategy SHALL implement all required FreqAI methods: feature_engineering_expand_all, feature_engineering_expand_basic, feature_engineering_standard, set_freqai_targets
5. THE Strategy SHALL maintain the timeframe = "5m" setting
6. THE Strategy SHALL maintain the leverage = 4.0 setting
7. THE Strategy SHALL maintain the can_short = False setting
8. THE Strategy SHALL maintain position_adjustment_enable = True

### Requirement 9: Risk Management Preservation

**User Story:** As a trader, I want the proven risk management mechanisms to remain intact, so that the strategy maintains capital preservation while using ML predictions.

#### Acceptance Criteria

1. THE Strategy SHALL maintain the custom_stake_amount method for first order sizing
2. THE Strategy SHALL maintain the calculate_max_orders method for dynamic position limits
3. THE Strategy SHALL maintain the get_dynamic_dca_distance method for volatility-adjusted DCA spacing
4. THE Strategy SHALL maintain the get_total_position_value method for global exposure tracking
5. THE Strategy SHALL maintain per-pair position limits based on max_open_trades
6. THE Strategy SHALL maintain global position limits based on total balance × leverage
7. THE Strategy SHALL maintain DCA cooldown logic based on dca_cooldown_candles
8. THE Strategy SHALL maintain the has_open_orders check in adjust_trade_position

### Requirement 10: Logging and Observability

**User Story:** As a trader, I want detailed logging of ML-based decisions, so that I can understand why the strategy entered, added to, or exited positions.

#### Acceptance Criteria

1. WHEN an entry is triggered by ML, THE Strategy SHALL log all three prediction values and thresholds
2. WHEN a DCA is blocked by ML, THE Strategy SHALL log which horizons failed the threshold check
3. WHEN a DCA is allowed by ML, THE Strategy SHALL log which 2+ horizons passed the threshold check
4. WHEN an exit is triggered by ML, THE Strategy SHALL log all three prediction values and which horizons were negative
5. THE Strategy SHALL use the freqtrade.loggers.logger for all ML-related log messages
6. THE Strategy SHALL include the pair name in all log messages
7. THE Strategy SHALL format prediction values to 4 decimal places in log messages

### Requirement 11: Traditional Indicator Removal

**User Story:** As a developer, I want to remove unused traditional indicator logic, so that the codebase is clean and maintainable.

#### Acceptance Criteria

1. THE Strategy SHALL remove the _count_overbought_indicators method
2. THE Strategy SHALL remove traditional indicator parameters: rsi_oversold_threshold, bb_oversold_threshold, stochrsi_oversold_threshold, williams_oversold_threshold, min_oversold_count
3. THE Strategy SHALL remove traditional exit parameters: rsi_overbought_threshold, bb_overbought_threshold, atr_overbought_multiplier, stochrsi_overbought_threshold, williams_overbought_threshold, min_overbought_count
4. THE Strategy SHALL keep indicator calculations in populate_indicators for potential future use and debugging
5. THE Strategy SHALL remove the populate_entry_trend method implementation (return empty dataframe)
6. THE Strategy SHALL remove the populate_exit_trend method implementation (return empty dataframe)
7. THE Strategy SHALL remove the auto_reduce_enabled logic and related code

### Requirement 14: ML-Based Stake Sizing (Optional Enhancement)

**User Story:** As a trader, I want the first order stake to be influenced by ML prediction confidence, so that I allocate more capital to high-confidence entries while maintaining risk limits.

#### Acceptance Criteria

1. THE Strategy MAY implement an optional ml_stake_confidence_enabled parameter (default False for backward compatibility)
2. WHEN ml_stake_confidence_enabled is True, THE Strategy SHALL calculate stake as: base_stake × confidence_multiplier
3. THE Strategy SHALL calculate confidence_multiplier based on the average of all three horizon predictions
4. THE Strategy SHALL define confidence_multiplier range: 0.5 to 1.5 (50% to 150% of base stake)
5. THE Strategy SHALL map prediction values to confidence: higher positive predictions = higher multiplier
6. THE Strategy SHALL ensure total position value (first order + all DCA) never exceeds (balance × leverage) / max_open_trades
7. THE Strategy SHALL ensure global exposure never exceeds balance × leverage
8. WHEN ml_stake_confidence_enabled is False, THE Strategy SHALL use fixed first_order_pct as before
9. THE Strategy SHALL provide ml_confidence_min and ml_confidence_max parameters for mapping predictions to multipliers
10. THE Strategy SHALL log the confidence multiplier when it affects stake sizing


### Requirement 13: Partial Exit for Profitable DCA Orders (Optional Enhancement)

**User Story:** As a trader, I want to close individual DCA orders that are in profit, so that I can reduce risk and lock in gains while keeping losing positions open for potential recovery.

#### Acceptance Criteria

1. THE Strategy MAY implement an optional ml_partial_exit_enabled parameter (default False for backward compatibility)
2. WHEN ml_partial_exit_enabled is True, THE Strategy SHALL evaluate each filled entry order individually for partial exit
3. THE Strategy SHALL calculate profit for each individual entry order as: (current_price - entry_price) / entry_price
4. WHEN an individual entry order has profit above ml_partial_exit_profit_threshold, THE Strategy SHALL consider closing that specific order's stake
5. THE Strategy SHALL use ML predictions to confirm partial exit: at least 2 out of 3 horizons must be negative
6. WHEN partial exit is triggered, THE Strategy SHALL return negative stake amount equal to that specific order's stake
7. THE Strategy SHALL tag partial exits with "partial_exit_order_N_profit_X%" where N is the order number and X is the profit percentage
8. THE Strategy SHALL NOT apply partial exit to the first order (only DCA orders)
9. THE Strategy SHALL provide ml_partial_exit_profit_threshold parameter (default 0.02 or 2% profit per order)
10. THE Strategy SHALL log which specific order is being partially closed and its profit

**Example Scenario:**
- First order: 100$ stake at 10$ price
- DCA 1: 200$ stake at 9$ price  
- DCA 2: 400$ stake at 8$ price
- Current price: 9.5$
- DCA 1 profit: (9.5 - 9) / 9 = 5.5% → Can partially exit DCA 1 (200$ stake)
- DCA 2 profit: (9.5 - 8) / 8 = 18.75% → Can partially exit DCA 2 (400$ stake)
- First order loss: (9.5 - 10) / 10 = -5% → Keep open
- Result: Close 200$ + 400$ = 600$ stake, keep 100$ stake open
