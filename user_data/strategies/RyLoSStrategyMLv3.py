from datetime import UTC

import pandas as pd
import talib.abstract as ta
from pandas import DataFrame

from freqtrade.strategy import (
    DecimalParameter,
    IntParameter,
    IStrategy,
    Trade,
    timeframe_to_minutes,
)


class RyLoSStrategyMLv3(IStrategy):
    timeframe = "5m"
    can_short = False
    process_only_new_candles = True
    position_adjustment_enable = True
    startup_candle_count: int = 50  # Massimo periodo indicatori (per FreqAI)
    # max_entry_position_adjustment rimosso - calcolato dinamicamente

    # Stoploss: -20% position = -80% capital (with 4x leverage)
    # Prevents catastrophic losses while allowing recovery
    stoploss = -0.20

    # Max trade duration: DISABLED (let ML handle exits)
    # max_trade_duration_candles = 576  # 2 giorni (DISABLED)

    # ROI disabilitato - usa solo custom_exit ML-driven
    minimal_roi = {
        "0": 0.5
    }

    # ============================================================================
    # ML-DRIVEN DYNAMIC DCA DISTANCE (4 optimizable)
    # ============================================================================

    # Enable/disable ML-driven dynamic DCA distance
    ml_dynamic_dca_distance_enabled = True  # Set to False to use static distance

    # DCA distance range based on ML confidence
    # Strong positive predictions → tight distance (aggressive DCA)
    # Weak/negative predictions → wide distance (conservative DCA)
    ml_dca_distance_tight = DecimalParameter(
        0.010, 0.025, default=0.0188, space="buy", optimize=True,
        load=True, decimals=4
    )
    ml_dca_distance_wide = DecimalParameter(
        0.020, 0.050, default=0.0369, space="buy", optimize=True,
        load=True, decimals=4
    )

    # ML prediction range for DCA distance mapping
    # Strong positive → tight distance
    # Weak/negative → wide distance
    ml_dca_pred_min = DecimalParameter(
        -0.03, -0.005, default=-0.0148, space="buy", optimize=True,
        load=True, decimals=4
    )
    ml_dca_pred_max = DecimalParameter(
        0.005, 0.05, default=0.0371, space="buy", optimize=True,
        load=True, decimals=4
    )

    # ============================================================================
    # CORE DCA PARAMETERS (3 optimizable)
    # ============================================================================

    first_order_pct = DecimalParameter(
        0.010, 0.035, default=0.0286, space="buy", optimize=True,
        load=True, decimals=4
    )
    dca_multiplier = DecimalParameter(
        1.5, 3.0, default=2.258, space="buy", optimize=True,
        load=True, decimals=3
    )

    # DCA dinamico basato su volatilità ATR
    dca_atr_multiplier = DecimalParameter(
        0.5, 3.0, default=2.728, space="buy", optimize=True,
        load=True, decimals=3
    )

    # ============================================================================
    # ML EXIT THRESHOLD (2 optimizable - sell space)
    # ============================================================================

    # ML exit: focus on 5m prediction for fast scalping
    ml_exit_threshold = DecimalParameter(
        -0.005, 0.01, default=0.003, space="sell", optimize=True,
        load=True, decimals=4
    )

    # Minimum profit required for ML exit (prevent premature exit)
    min_profit_for_ml_exit = DecimalParameter(
        0.010, 0.035, default=0.0251, space="sell", optimize=True,
        load=True, decimals=4
    )

    # Auto-Reduce per over-exposure (disabilitato)
    auto_reduce_enabled = False  # Disabilitato - causava Loss in backtest

    # Trailing stop (disabilitato)
    trailing_stop = False  # DISABILITATO - usa solo custom_exit ML-driven

    # ============================================================================
    # ML THRESHOLD PARAMETERS - WEIGHTED APPROACH (6 optimizable - entry + DCA)
    # ============================================================================

    # ML entry thresholds (USED for first entry)
    ml_entry_threshold = DecimalParameter(
        -0.015, 0.005, default=-0.0061, space="buy", optimize=True,
        load=True, decimals=4
    )
    ml_entry_5m_min = DecimalParameter(
        -0.010, 0.005, default=-0.005, space="buy", optimize=True,
        load=True, decimals=4
    )

    # ML DCA threshold (USED for DCA filtering) - CRITICAL PARAMETER
    # MUST be negative to allow DCA when predictions are slightly negative
    # Range: -0.03 (very permissive) to -0.005 (restrictive)
    ml_dca_threshold = DecimalParameter(
        -0.030, -0.005, default=-0.015, space="buy", optimize=True,
        load=True, decimals=4
    )

    # Weights for each time horizon (USED for both entry and DCA)
    ml_weight_5m = DecimalParameter(
        0.5, 4.0, default=2.90, space="buy", optimize=True,
        load=True, decimals=2
    )
    ml_weight_15m = DecimalParameter(
        0.5, 4.0, default=1.58, space="buy", optimize=True,
        load=True, decimals=2
    )
    ml_weight_30m = DecimalParameter(
        0.5, 4.0, default=1.93, space="buy", optimize=True,
        load=True, decimals=2
    )

    # ============================================================================
    # CRASH DETECTION PARAMETERS (1 optimizable)
    # ============================================================================

    # Crash detection: drop % in 15 minutes (3 candles @ 5m) to trigger immediate exit
    crash_detection_threshold = DecimalParameter(
        -0.10, -0.04, default=-0.071, space="sell", optimize=True,
        load=True, decimals=3
    )

    # ============================================================================
    # ML DRAWDOWN PREDICTION PARAMETERS (2 optimizable)
    # ============================================================================

    # ML drawdown prediction: exit if predicted drawdown exceeds threshold
    ml_drawdown_1h_threshold = DecimalParameter(
        -0.20, -0.08, default=-0.141, space="sell", optimize=True,
        load=True, decimals=3
    )
    ml_drawdown_2h_threshold = DecimalParameter(
        -0.25, -0.12, default=-0.195, space="sell", optimize=True,
        load=True, decimals=3
    )

    # ============================================================================
    # FIXED STOPLOSS (fallback)
    # ============================================================================

    # Fixed stoploss: -20% position = -80% capital (4x leverage)
    # Prevents catastrophic losses while allowing recovery
    fixed_stoploss = -0.20

    # ============================================================================
    # ML CONFIDENCE-BASED STAKE SIZING (Optional - 2 optimizable)
    # ============================================================================

    # Enable/disable confidence-based stake sizing
    ml_stake_confidence_enabled = False  # Set to True to enable

    # Prediction range for confidence mapping
    ml_confidence_min = DecimalParameter(
        -0.03, -0.005, default=-0.0098, space="buy", optimize=True,
        load=True, decimals=4
    )
    ml_confidence_max = DecimalParameter(
        0.01, 0.05, default=0.0246, space="buy", optimize=True,
        load=True, decimals=4
    )

    def leverage(
        self,
        pair: str,
        current_time,
        current_rate,
        proposed_leverage,
        max_leverage,
        entry_tag,
        side: str,
        **kwargs,
    ) -> float:
        return 4.0

    # ============================================================================
    # FREQAI METHODS
    # ============================================================================

    def feature_engineering_expand_all(self, dataframe: DataFrame, period: int,
                                       metadata: dict, **kwargs) -> DataFrame:
        """Features espanse per ogni periodo"""
        dataframe[f"%-rsi_{period}"] = ta.RSI(dataframe["close"], timeperiod=period)

        bb_upper, _, bb_lower = ta.BBANDS(dataframe["close"], timeperiod=period)
        dataframe[f"%-bb_width_{period}"] = (
            (dataframe["close"] - bb_lower) / (bb_upper - bb_lower)
        )

        dataframe[f"%-volume_ratio_{period}"] = (
            dataframe["volume"] / dataframe["volume"].rolling(period).mean()
        )
        return dataframe

    def feature_engineering_expand_basic(self, dataframe: DataFrame, metadata: dict,
                                         **kwargs) -> DataFrame:
        """Features base per FreqAI - Scalping optimized with early warning signals"""
        dataframe["%-rsi"] = ta.RSI(dataframe["close"], timeperiod=10)
        dataframe["%-atr_pct"] = (ta.ATR(dataframe, timeperiod=10) / dataframe["close"]) * 100

        stoch_k, _ = ta.STOCHRSI(dataframe["close"], timeperiod=10,
                                  fastk_period=5, fastd_period=3)
        dataframe["%-stochrsi"] = stoch_k

        dataframe["%-williams"] = ta.WILLR(dataframe, timeperiod=10)
        dataframe["%-pct_change"] = dataframe["close"].pct_change()
        dataframe["%-pct_change_vol"] = dataframe["volume"].pct_change()

        # NEW: Bollinger Band % (20-period, 2 std dev)
        bb_upper, _, bb_lower = ta.BBANDS(dataframe["close"], timeperiod=20, nbdevup=2.0, nbdevdn=2.0)
        dataframe["%-bb_percent"] = (dataframe["close"] - bb_lower) / (bb_upper - bb_lower)

        # NEW: MACD (12,26,9) - Momentum confirmation
        macd, signal, hist = ta.MACD(dataframe["close"], fastperiod=12, slowperiod=26, signalperiod=9)
        dataframe["%-macd"] = macd
        dataframe["%-macd_signal"] = signal
        dataframe["%-macd_hist"] = hist

        # NEW: EMA 9 and 21 - Trend identification
        dataframe["%-ema_9"] = ta.EMA(dataframe["close"], timeperiod=9)
        dataframe["%-ema_21"] = ta.EMA(dataframe["close"], timeperiod=21)

        # NEW: CCI (10-period) - Extreme price movements for scalping
        dataframe["%-cci"] = ta.CCI(dataframe, timeperiod=10)

        # NEW: VWAP - Volume Weighted Average Price
        typical_price = (dataframe["high"] + dataframe["low"] + dataframe["close"]) / 3
        # Use rolling window instead of cumsum to avoid issues with train/test splits
        vwap_period = 20
        dataframe["%-vwap"] = (
            (typical_price * dataframe["volume"]).rolling(window=vwap_period).sum() /
            dataframe["volume"].rolling(window=vwap_period).sum()
        )

        # NEW: OBV normalized - On-Balance Volume
        obv = ta.OBV(dataframe["close"], dataframe["volume"])
        # Convert to Series for rolling operations
        obv_series = pd.Series(obv, index=dataframe.index)
        dataframe["%-obv_norm"] = obv_series / obv_series.rolling(window=20).mean()

        # ========================================================================
        # EARLY WARNING FEATURES (for drawdown prediction)
        # ========================================================================
        # CRITICAL: Calculate ATR, RSI here (not in populate_indicators) because
        # feature_engineering_expand_basic() is called BEFORE populate_indicators()

        # Calculate ATR for early warning features (convert to Series)
        atr_temp = pd.Series(ta.ATR(dataframe, timeperiod=10), index=dataframe.index)

        # Calculate RSI for early warning features (convert to Series)
        rsi_temp = pd.Series(ta.RSI(dataframe["close"], timeperiod=10), index=dataframe.index)

        # 1. ATR Spike - Sudden volatility increase (pre-crash signal)
        dataframe["%-atr_spike"] = (
            atr_temp / atr_temp.rolling(window=20).mean()
        )

        # 2. Volume Spike - Unusual volume (panic selling/buying)
        dataframe["%-volume_spike"] = (
            dataframe["volume"] / dataframe["volume"].rolling(window=20).mean()
        )

        # 3. RSI Divergence - Momentum reversal signal
        dataframe["%-rsi_divergence"] = (
            rsi_temp - rsi_temp.shift(5)
        )

        # 4. Bollinger Band Squeeze - Pre-breakout indicator
        # bb_upper and bb_lower already calculated above for bb_percent
        bb_width = (bb_upper - bb_lower) / dataframe["close"]
        dataframe["%-bb_squeeze"] = (
            bb_width / bb_width.rolling(window=20).mean()
        )

        # 5. MACD Histogram Decline - Momentum loss
        dataframe["%-macd_decline"] = (
            dataframe["%-macd_hist"] - dataframe["%-macd_hist"].shift(3)
        )

        # 6. Distance to Recent Low - Support proximity
        dataframe["%-distance_to_low"] = (
            (dataframe["close"] - dataframe["low"].rolling(window=50).min()) /
            dataframe["close"]
        )

        # 7. Price Acceleration - Rate of change of momentum
        dataframe["%-price_acceleration"] = (
            dataframe["%-pct_change"] - dataframe["%-pct_change"].shift(3)
        )

        return dataframe

    def feature_engineering_standard(self, dataframe: DataFrame, metadata: dict,
                                     **kwargs) -> DataFrame:
        """Features standard (non espanse) - Removed temporal features to avoid time-based bias"""
        dataframe["%-adx"] = ta.ADX(dataframe, timeperiod=14)
        # REMOVED: %-hour and %-day_of_week (temporal bias)

        return dataframe

    def set_freqai_targets(self, dataframe: DataFrame, metadata: dict,
                          **kwargs) -> DataFrame:
        """
        Multi-horizon targets: 5min, 15min, 30min price change predictions
        + Drawdown prediction for early stop
        """
        # 5-minute target (1 candle @ 5m)
        dataframe["&-s_close_5m"] = (
            (dataframe["close"].shift(-1) - dataframe["close"]) /
            dataframe["close"]
        )

        # 15-minute target (3 candles @ 5m)
        dataframe["&-s_close_15m"] = (
            (dataframe["close"].shift(-3) - dataframe["close"]) /
            dataframe["close"]
        )

        # 30-minute target (6 candles @ 5m)
        dataframe["&-s_close_30m"] = (
            (dataframe["close"].shift(-6) - dataframe["close"]) /
            dataframe["close"]
        )

        # ========================================================================
        # DRAWDOWN PREDICTION TARGETS (for early stop)
        # ========================================================================

        # Predict worst drawdown in next 1 hour (12 candles @ 5m)
        # This helps ML learn to predict when a trade will go bad
        future_window_1h = 12
        future_min_1h = dataframe["close"].shift(-future_window_1h).rolling(
            window=future_window_1h, min_periods=1
        ).min()
        dataframe["&-s_max_drawdown_1h"] = (
            (future_min_1h - dataframe["close"]) / dataframe["close"]
        )

        # Predict worst drawdown in next 2 hours (24 candles @ 5m)
        future_window_2h = 24
        future_min_2h = dataframe["close"].shift(-future_window_2h).rolling(
            window=future_window_2h, min_periods=1
        ).min()
        dataframe["&-s_max_drawdown_2h"] = (
            (future_min_2h - dataframe["close"]) / dataframe["close"]
        )

        return dataframe

    def get_ml_predictions(self, pair: str) -> tuple[float, float, float]:
        """
        Retrieve all three horizon predictions for a pair.

        Args:
            pair: Trading pair (e.g., "BTC/USDT")

        Returns:
            tuple: (pred_5m, pred_15m, pred_30m)
                   Returns (0.0, 0.0, 0.0) if predictions unavailable
        """
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)

        if len(dataframe) < 1:
            return (0.0, 0.0, 0.0)

        current_candle = dataframe.iloc[-1]

        pred_5m = current_candle.get("&-s_close_5m", 0.0)
        pred_15m = current_candle.get("&-s_close_15m", 0.0)
        pred_30m = current_candle.get("&-s_close_30m", 0.0)

        return (pred_5m, pred_15m, pred_30m)

    def get_weighted_ml_prediction(self, pair: str) -> float:
        """
        Calculate weighted average of ML predictions across all time horizons.

        Formula: (pred_5m * w_5m + pred_15m * w_15m + pred_30m * w_30m) / (w_5m + w_15m + w_30m)

        Args:
            pair: Trading pair

        Returns:
            Weighted average prediction (normalized by sum of weights)
        """
        pred_5m, pred_15m, pred_30m = self.get_ml_predictions(pair)

        # Get weights
        w_5m = self.ml_weight_5m.value
        w_15m = self.ml_weight_15m.value
        w_30m = self.ml_weight_30m.value

        # Calculate weighted average
        total_weight = w_5m + w_15m + w_30m
        weighted_pred = (pred_5m * w_5m + pred_15m * w_15m + pred_30m * w_30m) / total_weight

        return weighted_pred

    def get_total_position_value(self) -> float:
        """Calcola il valore totale delle posizioni aperte su tutte le pairs"""
        total_value = 0
        open_trades = Trade.get_open_trades()

        for trade in open_trades:
            filled_entries = trade.select_filled_orders(trade.entry_side)
            total_stake = sum(order.cost for order in filled_entries if order.cost)
            position_value = total_stake * 4
            total_value += position_value

        return total_value

    def custom_stake_amount(
        self,
        pair: str,
        current_time,
        current_rate: float,
        proposed_stake: float,
        min_stake,
        max_stake: float,
        leverage: float,
        entry_tag,
        side: str,
        **kwargs,
    ) -> float:
        total_balance = self.wallets.get_total_stake_amount()
        max_open_trades = self.config.get("max_open_trades", 1)

        # Limite globale e per pair
        global_limit = total_balance * 4
        per_pair_limit = global_limit / max_open_trades

        # Esposizione attuale globale
        current_global_exposure = self.get_total_position_value()
        remaining_global = global_limit - current_global_exposure

        # Primo ordine: percentuale del balance totale
        base_stake = total_balance * self.first_order_pct.value

        # ML Confidence-based stake sizing (optional)
        if self.ml_stake_confidence_enabled:
            # Get ML predictions for all 3 horizons
            pred_5m, pred_15m, pred_30m = self.get_ml_predictions(pair)

            # Calculate average prediction
            avg_prediction = (pred_5m + pred_15m + pred_30m) / 3

            # Map prediction to confidence multiplier (0.5 to 1.5)
            # Linear mapping: ml_confidence_min -> 0.5, ml_confidence_max -> 1.5
            min_pred = self.ml_confidence_min.value
            max_pred = self.ml_confidence_max.value

            # Clamp prediction to range
            clamped_pred = max(min_pred, min(avg_prediction, max_pred))

            # Linear interpolation: [min_pred, max_pred] -> [0.5, 1.5]
            if max_pred > min_pred:
                confidence_multiplier = 0.5 + (clamped_pred - min_pred) / (max_pred - min_pred)
            else:
                confidence_multiplier = 1.0  # Fallback if range is invalid

            # Apply confidence multiplier
            base_stake = base_stake * confidence_multiplier

            # Log confidence multiplier
            from freqtrade.loggers import logger
            logger.info(
                f"{pair}: ML confidence stake sizing - "
                f"avg_pred={avg_prediction:.4f}, "
                f"multiplier={confidence_multiplier:.2f}, "
                f"stake={base_stake:.2f}"
            )

        # Limita al rimanente globale e al limite per pair
        max_allowed_stake = min(remaining_global / 4, per_pair_limit / 4)

        return min(base_stake, max_allowed_stake, max_stake)

    def calculate_max_orders(self, total_balance: float) -> int:
        """Calcola dinamicamente il numero massimo di ordini basato sui parametri ottimizzati"""
        max_open_trades = self.config.get("max_open_trades", 1)
        per_pair_limit = (total_balance * 4) / max_open_trades

        cumulative_stake = 0
        order_count = 0

        # Simula gli ordini fino al limite per pair
        for i in range(20):  # Limite di sicurezza
            if i == 0:
                stake = total_balance * self.first_order_pct.value
            else:
                stake_pct = self.first_order_pct.value * (self.dca_multiplier.value ** i)
                stake = total_balance * stake_pct

            position_value = stake * 4

            if cumulative_stake + position_value > per_pair_limit:
                break

            cumulative_stake += position_value
            order_count += 1

        return order_count - 1  # -1 perché primo ordine non conta come adjustment

    def get_dynamic_dca_distance(self, pair: str, current_rate: float) -> float:
        """
        Calcola distanza DCA dinamica basata su:
        1. ML confidence (predizioni positive → distanza stretta)
        2. ATR volatility (alta volatilità → distanza più ampia)

        Formula: base_distance × (1 + ATR% × multiplier)
        dove base_distance è calcolata da ML confidence
        """
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        if len(dataframe) < 1:
            # Fallback to wide distance if no data
            return self.ml_dca_distance_wide.value

        current_candle = dataframe.iloc[-1]
        atr = current_candle["atr"]
        atr_pct = atr / current_rate

        # Get ML predictions for all 3 horizons
        pred_5m, pred_15m, pred_30m = self.get_ml_predictions(pair)
        avg_prediction = (pred_5m + pred_15m + pred_30m) / 3

        # Calculate base distance from ML confidence
        if self.ml_dynamic_dca_distance_enabled:
            # Map prediction to distance: positive pred → tight, negative pred → wide
            min_pred = self.ml_dca_pred_min.value
            max_pred = self.ml_dca_pred_max.value

            # Clamp prediction to range
            clamped_pred = max(min_pred, min(avg_prediction, max_pred))

            # Linear interpolation: [min_pred, max_pred] → [wide, tight]
            # Note: INVERTED - positive predictions give TIGHT distance
            if max_pred > min_pred:
                distance_ratio = 1.0 - (clamped_pred - min_pred) / (max_pred - min_pred)
            else:
                distance_ratio = 0.5  # Fallback to middle

            base_distance = (
                self.ml_dca_distance_tight.value +
                distance_ratio * (self.ml_dca_distance_wide.value - self.ml_dca_distance_tight.value)
            )

            from freqtrade.loggers import logger
            logger.info(
                f"{pair}: Dynamic DCA distance - "
                f"avg_pred={avg_prediction:.4f}, "
                f"base_distance={base_distance:.4f} "
                f"(tight={self.ml_dca_distance_tight.value:.4f}, "
                f"wide={self.ml_dca_distance_wide.value:.4f})"
            )
        else:
            # Fallback to middle of range if disabled
            base_distance = (self.ml_dca_distance_tight.value + self.ml_dca_distance_wide.value) / 2

        # Apply ATR multiplier
        dynamic_distance = base_distance * (1 + atr_pct * self.dca_atr_multiplier.value)

        return dynamic_distance

    def adjust_trade_position(  # noqa: C901
        self,
        trade: Trade,
        current_time,
        current_rate: float,
        current_profit: float,
        min_stake,
        max_stake: float,
        current_entry_rate: float,
        current_exit_rate: float,
        current_entry_profit: float,
        current_exit_profit: float,
        **kwargs,
    ) -> float | tuple[float, str] | None:
        # Punto 1: Non agire se ci sono ordini aperti
        if trade.has_open_orders:
            return None

        # Punto 2: Cooldown di 1 candela (5 minuti) dall'ultimo DCA
        filled_entries = trade.select_filled_orders(trade.entry_side)
        if filled_entries:
            last_order = filled_entries[-1]

            # Ensure both datetimes are timezone-aware for comparison
            # Use order_filled_utc which is always timezone-aware
            last_order_time = last_order.order_filled_utc

            # Make current_time timezone-aware if it isn't
            if current_time.tzinfo is None:
                current_time = current_time.replace(tzinfo=UTC)

            time_since_last_order = current_time - last_order_time
            candle_duration_minutes = timeframe_to_minutes(self.timeframe)
            cooldown_candles = 1  # 1 candela = 5 minuti

            if time_since_last_order.total_seconds() < (candle_duration_minutes * 60 * cooldown_candles):
                return None

        total_balance = self.wallets.get_total_stake_amount()
        max_open_trades = self.config.get("max_open_trades", 1)

        # Calcola dinamicamente il numero massimo di ordini per questa pair
        max_orders = self.calculate_max_orders(total_balance)

        # Limiti globali e per pair (calcolo unificato)
        global_limit = total_balance * 4
        per_pair_limit = global_limit / max_open_trades
        current_global_exposure = self.get_total_position_value()

        # Usa solo ordini fillati per calcolare distanze
        filled_entries = trade.select_filled_orders(trade.entry_side)
        if not filled_entries:
            return None

        # Se abbiamo raggiunto il numero massimo di ordini per questa pair
        if trade.nr_of_successful_entries > max_orders:
            return None

        # Verifica se abbiamo raggiunto il limite globale
        if current_global_exposure >= global_limit * 0.95:  # 95% del limite per sicurezza
            return None

        # Wallet disponibile e posizione corrente
        available_balance = self.wallets.get_available_stake_amount()
        current_position_value = trade.stake_amount * 4

        # Calcola il prossimo stake
        entry_count = trade.nr_of_successful_entries
        next_stake_pct = self.first_order_pct.value * (self.dca_multiplier.value**entry_count)
        next_stake = total_balance * next_stake_pct

        # Verifica se available_balance è sufficiente
        if next_stake > available_balance:
            return None  # Non abbastanza fondi

        next_position_value = next_stake * 4

        # Verifica limite per pair
        if current_position_value + next_position_value > per_pair_limit:
            remaining_per_pair = per_pair_limit - current_position_value
            next_stake = remaining_per_pair / 4
            if next_stake < min_stake:
                return None

        # Verifica limite globale
        remaining_global = global_limit - current_global_exposure
        if next_position_value > remaining_global:
            next_stake = remaining_global / 4
            if next_stake < min_stake:
                return None

        # Controlla distanza minima dall'ultimo ordine fillato (solo in discesa)
        if not filled_entries:
            return None
        last_order_rate = filled_entries[-1].average
        price_distance = abs(current_rate - last_order_rate) / last_order_rate

        # Calcola distanza DCA dinamica
        dynamic_distance = self.get_dynamic_dca_distance(trade.pair, current_rate)

        # DCA solo se: distanza sufficiente E prezzo più basso dell'ultimo ordine
        if price_distance < dynamic_distance or current_rate >= last_order_rate:
            return None

        # Check if FreqAI model is ready using official flag
        dataframe, _ = self.dp.get_analyzed_dataframe(trade.pair, self.timeframe)
        if len(dataframe) < 1 or dataframe["do_predict"].iloc[-1] == 0:
            from freqtrade.loggers import logger
            logger.debug(f"{trade.pair}: DCA skipped - model not ready (do_predict=0)")
            return None

        # ML FILTER: Use weighted prediction for DCA decision
        weighted_pred = self.get_weighted_ml_prediction(trade.pair)

        # Get predictions and DI for logging
        pred_5m, pred_15m, pred_30m = self.get_ml_predictions(trade.pair)
        dataframe, _ = self.dp.get_analyzed_dataframe(trade.pair, self.timeframe)
        current_candle = dataframe.iloc[-1]
        di_value = current_candle.get("DI_values", 0.0)
        do_predict = current_candle.get("do_predict", 0)

        # Determine confidence level
        if do_predict != 1:
            confidence_emoji = "🚫"
            confidence_text = "OUTLIER"
        elif di_value < 0.9:
            confidence_emoji = "🟢"
            confidence_text = "HIGH"
        elif di_value < 1.5:
            confidence_emoji = "🟡"
            confidence_text = "MED"
        else:
            confidence_emoji = "🔴"
            confidence_text = "LOW"

        # Profit emoji
        profit_emoji = "💚" if current_profit >= 0 else "🔴"

        if weighted_pred < self.ml_dca_threshold.value:
            # Block DCA - weighted prediction below threshold
            from freqtrade.loggers import logger
            logger.info(
                f"{trade.pair}: 🚫 DCA BLOCKED | "
                f"📊 5m={pred_5m*100:+.2f}% 15m={pred_15m*100:+.2f}% 30m={pred_30m*100:+.2f}% → w={weighted_pred*100:+.2f}% | "
                f"{confidence_emoji} DI={di_value:.2f} ({confidence_text}, do_predict={int(do_predict)}) | "
                f"{profit_emoji} profit={current_profit*100:+.1f}% | "
                f"💡 w={weighted_pred*100:+.2f}%<{self.ml_dca_threshold.value*100:+.2f}%"
            )
            return None

        # DCA allowed - weighted prediction above threshold
        from freqtrade.loggers import logger
        logger.info(
            f"{trade.pair}: ➕ DCA ALLOWED | "  # noqa: RUF001
            f"📊 5m={pred_5m*100:+.2f}% 15m={pred_15m*100:+.2f}% 30m={pred_30m*100:+.2f}% → w={weighted_pred*100:+.2f}% | "
            f"{confidence_emoji} DI={di_value:.2f} ({confidence_text}, do_predict={int(do_predict)}) | "
            f"{profit_emoji} profit={current_profit*100:+.1f}% | "
            f"💡 w={weighted_pred*100:+.2f}%>{self.ml_dca_threshold.value*100:+.2f}%"
        )

        tag = f"dca_ml_w{weighted_pred:.4f}_{current_profit*100:.1f}%"
        return next_stake, tag

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:  # noqa: C901
        """
        CRITICAL: FreqAI must be called first.
        Calculate indicators for strategy use (ATR for DCA distance + multi-oscillator for entry).
        """
        dataframe = self.freqai.start(dataframe, metadata, self)

        # ATR for dynamic DCA distance calculation
        dataframe["atr"] = ta.ATR(dataframe, timeperiod=10)

        # ========================================================================
        # MULTI-OSCILLATOR INDICATORS (for first entry)
        # ========================================================================
        # RSI periodo 10 per maggiore reattività su 5min
        dataframe["rsi"] = ta.RSI(dataframe["close"], timeperiod=10)

        # Stochastic RSI periodo 10 (configurazione 10-5-3)
        stochrsi_k, stochrsi_d = ta.STOCHRSI(
            dataframe["close"], timeperiod=10, fastk_period=5, fastd_period=3
        )
        dataframe["stochrsi"] = stochrsi_k  # Usa %K (più reattivo)

        # Bollinger Bands %B (20 periodi standard)
        bb_upper, bb_middle, bb_lower = ta.BBANDS(
            dataframe["close"], timeperiod=20, nbdevup=2.0, nbdevdn=2.0
        )
        dataframe["bb_percent"] = (dataframe["close"] - bb_lower) / (bb_upper - bb_lower)

        # Williams %R periodo 10
        dataframe["williams_r"] = ta.WILLR(
            dataframe["high"], dataframe["low"], dataframe["close"], timeperiod=10
        )

        # Log ML prediction values after FreqAI generates them
        if len(dataframe) > 0 and "&-s_close_5m" in dataframe.columns:
            last_candle = dataframe.iloc[-1]
            pred_5m = last_candle.get("&-s_close_5m", 0.0)
            pred_15m = last_candle.get("&-s_close_15m", 0.0)
            pred_30m = last_candle.get("&-s_close_30m", 0.0)
            pred_dd_1h = last_candle.get("&-s_max_drawdown_1h", 0.0)
            pred_dd_2h = last_candle.get("&-s_max_drawdown_2h", 0.0)

            # Get DI (Dissimilarity Index) for confidence
            di_value = last_candle.get("DI_values", 0.0)
            do_predict = last_candle.get("do_predict", 0)

            # Calculate weighted prediction
            w_5m = self.ml_weight_5m.value
            w_15m = self.ml_weight_15m.value
            w_30m = self.ml_weight_30m.value
            total_weight = w_5m + w_15m + w_30m
            weighted = (pred_5m * w_5m + pred_15m * w_15m + pred_30m * w_30m) / total_weight

            # Determine status and reason
            status = ""
            reason = ""

            # Check if we're in a trade
            open_trades = Trade.get_open_trades()
            current_trade = None
            for t in open_trades:
                if t.pair == metadata['pair']:
                    current_trade = t
                    break

            if current_trade:
                # In trade - check exit conditions
                current_profit = current_trade.calc_profit_ratio(last_candle['close'])

                # Check ML exit
                if current_profit > self.min_profit_for_ml_exit.value and pred_5m < self.ml_exit_threshold.value:
                    status = "❌ SELL"
                    reason = f"5m={pred_5m*100:+.2f}%<{self.ml_exit_threshold.value*100:+.2f}%"
                # Check drawdown prediction
                elif pred_dd_1h < self.ml_drawdown_1h_threshold.value or pred_dd_2h < self.ml_drawdown_2h_threshold.value:
                    status = "⚠️ DD ALERT"
                    reason = f"DD 1h/2h < {self.ml_drawdown_1h_threshold.value*100:+.1f}%/{self.ml_drawdown_2h_threshold.value*100:+.1f}%"
                # Check DCA
                elif weighted < self.ml_dca_threshold.value:
                    status = "🚫 DCA BLOCKED"
                    reason = f"w={weighted*100:+.2f}%<{self.ml_dca_threshold.value*100:+.2f}%"
                else:
                    status = "⏸️ HOLD"
                    reason = None  # No reason for HOLD
            else:
                # Not in trade - check entry conditions
                if weighted > self.ml_entry_threshold.value and pred_5m > self.ml_entry_5m_min.value:
                    status = "✅ BUY"
                    reason = f"w={weighted*100:+.2f}%>{self.ml_entry_threshold.value*100:+.2f}%, 5m={pred_5m*100:+.2f}%>{self.ml_entry_5m_min.value*100:+.2f}%"
                elif weighted <= self.ml_entry_threshold.value:
                    status = "⏸️ NEUTRAL"
                    reason = None  # No reason for NEUTRAL
                else:
                    status = "⏸️ NEUTRAL"
                    reason = None  # No reason for NEUTRAL

            from freqtrade.loggers import logger

            # Determine confidence level based on DI threshold (0.9)
            if do_predict != 1:
                confidence_emoji = "🚫"
                confidence_text = "OUTLIER"
            elif di_value < 0.9:
                confidence_emoji = "🟢"
                confidence_text = "HIGH"
            elif di_value < 1.5:
                confidence_emoji = "🟡"
                confidence_text = "MED"
            else:
                confidence_emoji = "🔴"
                confidence_text = "LOW"

            # Profit emoji (only if in trade)
            profit_section = ""
            if current_trade:
                profit_emoji = "💚" if current_profit >= 0 else "🔴"
                profit_section = f" | {profit_emoji} profit={current_profit*100:+.1f}%"

            # Log in single line with clear separators
            log_message = (
                f"{metadata['pair']}: {status} | "
                f"📊 5m={pred_5m*100:+.2f}% 15m={pred_15m*100:+.2f}% 30m={pred_30m*100:+.2f}% → w={weighted*100:+.2f}% | "
                f"📉 DD 1h={pred_dd_1h*100:+.1f}% 2h={pred_dd_2h*100:+.1f}% | "
                f"{confidence_emoji} DI={di_value:.2f} ({confidence_text}, do_predict={int(do_predict)})"
                f"{profit_section}"
            )

            # Add reason only if present
            if reason:
                log_message += f" | 💡 {reason}"

            logger.info(log_message)

        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        ML-driven entry logic (ML-only, no multi-oscillator).

        Entry signal when:
        1. Weighted ML prediction > ml_entry_threshold
        2. 5m prediction > ml_entry_5m_min (prevents entry with negative short-term outlook)
        3. Model is ready (do_predict = 1)
        """
        # Check if FreqAI model is ready
        model_ready = (dataframe["do_predict"] == 1).fillna(False)

        # Get ML predictions
        pred_5m = dataframe.get("&-s_close_5m", 0.0)
        pred_15m = dataframe.get("&-s_close_15m", 0.0)
        pred_30m = dataframe.get("&-s_close_30m", 0.0)

        # Calculate weighted prediction
        w_5m = self.ml_weight_5m.value
        w_15m = self.ml_weight_15m.value
        w_30m = self.ml_weight_30m.value
        total_weight = w_5m + w_15m + w_30m

        weighted_pred = (pred_5m * w_5m + pred_15m * w_15m + pred_30m * w_30m) / total_weight

        # Entry conditions (all must be true)
        entry_condition = (
            model_ready &
            (weighted_pred > self.ml_entry_threshold.value) &
            (pred_5m > self.ml_entry_5m_min.value)
        )

        # Create descriptive tags
        dataframe["enter_tag"] = ""

        for i in range(len(dataframe)):
            if entry_condition.iloc[i]:
                w_val = weighted_pred.iloc[i]
                p5_val = pred_5m.iloc[i]
                p15_val = pred_15m.iloc[i]
                p30_val = pred_30m.iloc[i]

                dataframe.loc[dataframe.index[i], "enter_tag"] = (
                    f"buy_ml_w{w_val:.4f}_5m:{p5_val:.4f}_15m:{p15_val:.4f}_30m:{p30_val:.4f}"
                )

        dataframe.loc[entry_condition, "enter_long"] = 1
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        return dataframe

    def custom_stoploss(
        self,
        pair: str,
        trade: Trade,
        current_time,
        current_rate: float,
        current_profit: float,
        **kwargs,
    ) -> float:
        """
        Simplified ML-driven stoploss with 5 clean levels.

        LIVELLO 0: ML Drawdown Prediction (preventive exit)
        LIVELLO 1: Crash Detection (reactive exit)
        LIVELLO 2: Breakeven Move (protect profit)
        LIVELLO 3: Trailing Stop (maximize profit)
        LIVELLO 4: Fixed Stoploss (fallback)

        Returns:
            Stoploss value (negative float, e.g., -0.15 for -15%)
        """
        from freqtrade.loggers import logger

        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)

        # ========================================================================
        # LIVELLO 0: ML DRAWDOWN PREDICTION (preventive exit - massima priorità)
        # ========================================================================
        if len(dataframe) >= 1:
            current_candle = dataframe.iloc[-1]

            # Get ML drawdown predictions
            pred_dd_1h = current_candle.get("&-s_max_drawdown_1h", 0.0)
            pred_dd_2h = current_candle.get("&-s_max_drawdown_2h", 0.0)

            # Exit if ML predicts large drawdown
            if (pred_dd_1h < self.ml_drawdown_1h_threshold.value or
                pred_dd_2h < self.ml_drawdown_2h_threshold.value):
                logger.warning(
                    f"{pair}: ML DRAWDOWN PREDICTION - "
                    f"1h={pred_dd_1h*100:.1f}% (threshold={self.ml_drawdown_1h_threshold.value*100:.1f}%), "
                    f"2h={pred_dd_2h*100:.1f}% (threshold={self.ml_drawdown_2h_threshold.value*100:.1f}%) - "
                    f"Preventive exit at {current_profit*100:.2f}%"
                )
                return current_profit + 0.005  # Exit with small buffer

        # ========================================================================
        # LIVELLO 1: CRASH DETECTION (reactive exit)
        # ========================================================================
        if len(dataframe) >= 4:
            # Calcola drop % nelle ultime 3 candele (15 minuti)
            price_3_ago = dataframe.iloc[-4]["close"]
            price_2_ago = dataframe.iloc[-3]["close"]
            price_1_ago = dataframe.iloc[-2]["close"]
            current_price = dataframe.iloc[-1]["close"]

            # Crash detection: drop > threshold in 15min E confermato per 2 candele
            drop_3_candles = (current_price - price_3_ago) / price_3_ago
            drop_sustained = (current_price < price_2_ago and current_price < price_1_ago)

            if drop_3_candles < self.crash_detection_threshold.value and drop_sustained:
                # Crash confermato → exit immediato
                logger.warning(
                    f"{pair}: CRASH DETECTED! "
                    f"Drop={drop_3_candles*100:.2f}% in 15min "
                    f"(threshold={self.crash_detection_threshold.value*100:.2f}%) - "
                    f"Immediate exit at {current_profit*100:.2f}%"
                )
                return current_profit + 0.01  # Exit immediato con piccolo buffer

        # ========================================================================
        # LIVELLO 2: BREAKEVEN MOVE (protect profit)
        # ========================================================================
        if current_profit > 0.02:  # Dopo +2% profit
            # Muovi stoploss a breakeven (0%)
            logger.info(
                f"{pair}: Breakeven stoploss active - "
                f"profit={current_profit*100:.2f}% > 2%"
            )
            return 0.005  # Piccolo profit garantito

        # ========================================================================
        # LIVELLO 3: TRAILING STOP (maximize profit)
        # ========================================================================
        if current_profit > 0:
            # Trail 3% behind current profit
            trailing_stoploss = current_profit - 0.03
            # Don't go below fixed stoploss
            final_stoploss = max(trailing_stoploss, self.fixed_stoploss)
            logger.info(
                f"{pair}: Trailing stoploss active - "
                f"profit={current_profit*100:.2f}%, "
                f"trailing={trailing_stoploss:.4f}, "
                f"final={final_stoploss:.4f}"
            )
            return final_stoploss

        # ========================================================================
        # LIVELLO 4: FIXED STOPLOSS (fallback)
        # ========================================================================
        logger.debug(
            f"{pair}: Fixed stoploss - "
            f"stoploss={self.fixed_stoploss:.4f}"
        )
        return self.fixed_stoploss

    def custom_exit(
        self,
        pair: str,
        trade: Trade,
        current_time,
        current_rate: float,
        current_profit: float,
        **kwargs,
    ):
        """
        ML-driven exit with focus on 5m prediction for fast scalping.

        Exit when:
        - Trade duration > 2 days (force exit to avoid infinite trades)
        - Profit > min_profit_for_ml_exit AND 5m prediction < ml_exit_threshold
        """
        from freqtrade.loggers import logger

        # Check if FreqAI model is ready using official flag
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        if len(dataframe) < 1 or dataframe["do_predict"].iloc[-1] == 0:
            from freqtrade.loggers import logger
            logger.debug(f"{pair}: ML exit skipped - model not ready (do_predict=0)")
            return None

        # PRIORITY 1: ML exit if we have minimum profit
        if current_profit > self.min_profit_for_ml_exit.value:
            # Get ML predictions
            pred_5m, pred_15m, pred_30m = self.get_ml_predictions(pair)

            # Get current candle for DI
            current_candle = dataframe.iloc[-1]
            di_value = current_candle.get("DI_values", 0.0)
            do_predict = current_candle.get("do_predict", 0)

            # Calculate weighted prediction
            w_5m = self.ml_weight_5m.value
            w_15m = self.ml_weight_15m.value
            w_30m = self.ml_weight_30m.value
            total_weight = w_5m + w_15m + w_30m
            weighted = (pred_5m * w_5m + pred_15m * w_15m + pred_30m * w_30m) / total_weight

            # Determine confidence level
            if do_predict != 1:
                confidence_emoji = "🚫"
                confidence_text = "OUTLIER"
            elif di_value < 0.9:
                confidence_emoji = "🟢"
                confidence_text = "HIGH"
            elif di_value < 1.5:
                confidence_emoji = "🟡"
                confidence_text = "MED"
            else:
                confidence_emoji = "🔴"
                confidence_text = "LOW"

            # FOCUS ON 5M: Exit if 5m prediction below threshold
            # This gives fastest reaction for scalping
            if pred_5m < self.ml_exit_threshold.value:
                logger.info(
                    f"{pair}: ❌ SELL | "
                    f"📊 5m={pred_5m*100:+.2f}% 15m={pred_15m*100:+.2f}% 30m={pred_30m*100:+.2f}% → w={weighted*100:+.2f}% | "
                    f"{confidence_emoji} DI={di_value:.2f} ({confidence_text}, do_predict={int(do_predict)}) | "
                    f"💰 profit={current_profit*100:+.2f}% | "
                    f"💡 5m={pred_5m*100:+.2f}%<{self.ml_exit_threshold.value*100:+.2f}%"
                )
                return f"sell_ml_5m{pred_5m:.4f}_{current_profit*100:+.1f}%"

        return None
