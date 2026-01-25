from datetime import UTC, timedelta

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
    stoploss = -1  # Disabilitato, gestito da custom_exit adattivo

    # ROI disabilitato - usa solo custom_exit
    minimal_roi = {
        "0": 0.5
    }

    # Parametri ottimizzabili
    first_order_pct = DecimalParameter(0.005, 0.03, default=0.029, space="buy", optimize=True)
    dca_distance = DecimalParameter(0.005, 0.05, default=0.022, space="buy", optimize=True)
    dca_multiplier = DecimalParameter(1.5, 3.0, default=1.991, space="buy", optimize=True)

    # DCA dinamico basato su volatilità ATR
    dca_atr_multiplier = DecimalParameter(0.5, 3.0, default=2.306, space="buy", optimize=True)

    # DCA cooldown dinamico (numero di candele da aspettare)
    dca_cooldown_candles = IntParameter(1, 5, default=2, space="buy", optimize=False)

    # Exit parameters
    min_profit_for_overbought_exit = DecimalParameter(
        0.01, 0.10, default=0.017, space="sell", optimize=True
    )

    # Auto-Reduce per over-exposure (disabilitato)
    auto_reduce_enabled = False  # Disabilitato - causava Loss in backtest

    # Trailing stop (disabilitato)
    trailing_stop = False  # DISABILITATO per test ML

    # ============================================================================
    # ML THRESHOLD PARAMETERS (9 total - Multi-Horizon)
    # ============================================================================
    
    # Entry Thresholds (all 3 must be positive)
    ml_entry_threshold_15m = DecimalParameter(
        -0.01, 0.02, default=0.005, space="buy", optimize=True
    )
    ml_entry_threshold_30m = DecimalParameter(
        -0.01, 0.02, default=0.005, space="buy", optimize=True
    )
    ml_entry_threshold_1h = DecimalParameter(
        -0.01, 0.02, default=0.005, space="buy", optimize=True
    )
    
    # DCA Thresholds (2 out of 3 must be positive)
    ml_dca_threshold_15m = DecimalParameter(
        -0.05, 0.01, default=-0.01, space="buy", optimize=True
    )
    ml_dca_threshold_30m = DecimalParameter(
        -0.05, 0.01, default=-0.01, space="buy", optimize=True
    )
    ml_dca_threshold_1h = DecimalParameter(
        -0.05, 0.01, default=-0.01, space="buy", optimize=True
    )
    
    # Exit Thresholds (2 out of 3 must be negative)
    ml_exit_threshold_15m = DecimalParameter(
        -0.02, 0.01, default=-0.005, space="sell", optimize=True
    )
    ml_exit_threshold_30m = DecimalParameter(
        -0.02, 0.01, default=-0.005, space="sell", optimize=True
    )
    ml_exit_threshold_1h = DecimalParameter(
        -0.02, 0.01, default=-0.005, space="sell", optimize=True
    )
    
    # ============================================================================
    # ML CONFIDENCE-BASED STAKE SIZING (Optional - disabled by default)
    # ============================================================================
    
    # Enable/disable confidence-based stake sizing
    ml_stake_confidence_enabled = False  # Set to True to enable
    
    # Prediction range for confidence mapping
    ml_confidence_min = DecimalParameter(
        -0.02, 0.0, default=-0.01, space="buy", optimize=True
    )
    ml_confidence_max = DecimalParameter(
        0.01, 0.05, default=0.02, space="buy", optimize=True
    )
    
    # ============================================================================
    # ML PARTIAL EXIT FOR PROFITABLE DCA ORDERS (Optional - disabled by default)
    # ============================================================================
    
    # Enable/disable partial exit for profitable DCA orders
    ml_partial_exit_enabled = False  # Set to True to enable
    
    # Minimum profit threshold for partial exit (per individual order)
    ml_partial_exit_profit_threshold = DecimalParameter(
        0.01, 0.05, default=0.02, space="sell", optimize=True
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
        """Features base per FreqAI - Scalping optimized"""
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

        # NEW: Supertrend (ATR 10, multiplier 3) - Clear trend direction
        # Simplified implementation: price relative to ATR bands
        atr = ta.ATR(dataframe, timeperiod=10)
        hl_avg = (dataframe["high"] + dataframe["low"]) / 2
        upper_band = hl_avg + (3 * atr)
        lower_band = hl_avg - (3 * atr)
        # Supertrend: 1 if uptrend (close > lower_band), -1 if downtrend (close < upper_band), 0 otherwise
        dataframe["%-supertrend"] = ((dataframe["close"] > lower_band).astype(int) - 
                                      (dataframe["close"] < upper_band).astype(int))

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

        return dataframe

    def feature_engineering_standard(self, dataframe: DataFrame, metadata: dict,
                                     **kwargs) -> DataFrame:
        """Features standard (non espanse) - Removed temporal features to avoid time-based bias"""
        dataframe["%-adx"] = ta.ADX(dataframe, timeperiod=14)
        # REMOVED: %-hour and %-day_of_week (temporal bias)

        return dataframe

    def set_freqai_targets(self, dataframe: DataFrame, metadata: dict,
                          **kwargs) -> DataFrame:
        """Multi-horizon targets: 15min, 30min, 1h price change predictions"""
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
        
        # 1-hour target (12 candles @ 5m)
        dataframe["&-s_close_1h"] = (
            (dataframe["close"].shift(-12) - dataframe["close"]) /
            dataframe["close"]
        )

        return dataframe

    def get_ml_predictions(self, pair: str) -> tuple[float, float, float]:
        """
        Retrieve all three horizon predictions for a pair.
        
        Args:
            pair: Trading pair (e.g., "BTC/USDT")
        
        Returns:
            tuple: (pred_15m, pred_30m, pred_1h)
                   Returns (0.0, 0.0, 0.0) if predictions unavailable
        """
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        
        if len(dataframe) < 1:
            return (0.0, 0.0, 0.0)
        
        current_candle = dataframe.iloc[-1]
        
        pred_15m = current_candle.get("&-s_close_15m", 0.0)
        pred_30m = current_candle.get("&-s_close_30m", 0.0)
        pred_1h = current_candle.get("&-s_close_1h", 0.0)
        
        return (pred_15m, pred_30m, pred_1h)

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
            pred_15m, pred_30m, pred_1h = self.get_ml_predictions(pair)
            
            # Calculate average prediction
            avg_prediction = (pred_15m + pred_30m + pred_1h) / 3
            
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
        """Calcola distanza DCA dinamica: dca_distance × (1 + ATR% × multiplier)"""  # noqa: RUF002
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        if len(dataframe) < 1:
            return self.dca_distance.value

        current_candle = dataframe.iloc[-1]
        atr = current_candle["atr"]

        # ATR normalizzato in percentuale
        atr_pct = atr / current_rate

        # Distanza dinamica: base × (1 + volatilità × multiplier)  # noqa: RUF003
        distance = self.dca_distance.value * (1 + atr_pct * self.dca_atr_multiplier.value)

        return distance

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
        # Punto 4: Non agire se ci sono ordini aperti
        if trade.has_open_orders:
            return None

        # Cooldown dinamico: aspetta N candele dall'ultimo DCA
        filled_entries = trade.select_filled_orders(trade.entry_side)
        if len(filled_entries) > 0:
            last_order_time = filled_entries[-1].order_filled_date.replace(tzinfo=UTC)
            cooldown_minutes = timeframe_to_minutes(self.timeframe) * self.dca_cooldown_candles.value  # noqa: E501
            min_wait_time = timedelta(minutes=cooldown_minutes)
            if (current_time - min_wait_time) < last_order_time:
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
        if not filled_entries:
            return None

        last_order_price = filled_entries[-1].average

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

        # ML FILTER: blocca DCA standard se meno di 2/3 orizzonti positivi
        # (SOLO per DCA standard, NON emergency)
        pred_15m, pred_30m, pred_1h = self.get_ml_predictions(trade.pair)
        
        positive_count = sum([
            pred_15m > self.ml_dca_threshold_15m.value,
            pred_30m > self.ml_dca_threshold_30m.value,
            pred_1h > self.ml_dca_threshold_1h.value
        ])
        
        if positive_count < 2:
            # Block DCA - less than 2 horizons are positive
            from freqtrade.loggers import logger
            horizons_status = []
            if pred_15m > self.ml_dca_threshold_15m.value:
                horizons_status.append("15m:✓")
            else:
                horizons_status.append("15m:✗")
            if pred_30m > self.ml_dca_threshold_30m.value:
                horizons_status.append("30m:✓")
            else:
                horizons_status.append("30m:✗")
            if pred_1h > self.ml_dca_threshold_1h.value:
                horizons_status.append("1h:✓")
            else:
                horizons_status.append("1h:✗")
            
            logger.info(
                f"{trade.pair}: DCA blocked by ML filter "
                f"({positive_count}/3 positive) - "
                f"{' '.join(horizons_status)} - "
                f"15m={pred_15m:.4f}, 30m={pred_30m:.4f}, 1h={pred_1h:.4f}"
            )
            return None
        
        # DCA allowed - at least 2/3 horizons are positive
        from freqtrade.loggers import logger
        horizons_positive = []
        if pred_15m > self.ml_dca_threshold_15m.value:
            horizons_positive.append("15m")
        if pred_30m > self.ml_dca_threshold_30m.value:
            horizons_positive.append("30m")
        if pred_1h > self.ml_dca_threshold_1h.value:
            horizons_positive.append("1h")
        
        logger.info(
            f"{trade.pair}: DCA allowed by ML filter "
            f"({positive_count}/3 positive: {'+'.join(horizons_positive)}) - "
            f"15m={pred_15m:.4f}, 30m={pred_30m:.4f}, 1h={pred_1h:.4f}"
        )
        
        tag = f"dca_ml_2of3_{'+'.join(horizons_positive)}_{current_profit*100:.1f}%"
        return next_stake, tag

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        CRITICAL: FreqAI must be called first.
        Calculate ATR for strategy use (separate from %-atr_pct for ML).
        """
        dataframe = self.freqai.start(dataframe, metadata, self)
        
        # Calculate ATR for DCA distance calculation
        # This is separate from %-atr_pct used by FreqAI
        dataframe["atr"] = ta.ATR(dataframe, timeperiod=10)
        
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        ML-driven entry logic: All 3 horizons must be positive.
        
        Entry signal generated when:
        - pred_15m > ml_entry_threshold_15m AND
        - pred_30m > ml_entry_threshold_30m AND
        - pred_1h > ml_entry_threshold_1h
        """
        # Get ML predictions for all 3 horizons
        pair = metadata["pair"]
        
        # Initialize columns
        dataframe["enter_long"] = 0
        dataframe["enter_tag"] = ""
        
        # Check if ML predictions are available
        if "&-s_close_15m" not in dataframe.columns:
            return dataframe
        
        # ML-based entry condition: ALL 3 horizons must be positive
        entry_condition = (
            (dataframe["&-s_close_15m"] > self.ml_entry_threshold_15m.value) &
            (dataframe["&-s_close_30m"] > self.ml_entry_threshold_30m.value) &
            (dataframe["&-s_close_1h"] > self.ml_entry_threshold_1h.value)
        )
        
        # Set entry signal
        dataframe.loc[entry_condition, "enter_long"] = 1
        
        # Create descriptive tags with prediction values
        for i in dataframe[entry_condition].index:
            pred_15m = dataframe.loc[i, "&-s_close_15m"]
            pred_30m = dataframe.loc[i, "&-s_close_30m"]
            pred_1h = dataframe.loc[i, "&-s_close_1h"]
            
            dataframe.loc[i, "enter_tag"] = (
                f"buy_ml_all_positive_"
                f"15m:{pred_15m:.4f}_"
                f"30m:{pred_30m:.4f}_"
                f"1h:{pred_1h:.4f}"
            )
        
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        return dataframe

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
        ML-driven exit logic with optional partial exit for profitable DCA orders.
        
        Exit signal generated when:
        - current_profit > min_profit_for_overbought_exit AND
        - At least 2 out of 3 predictions are below their exit thresholds
        
        Partial exit (optional):
        - Evaluates each DCA order individually
        - Closes profitable DCA orders when ML signals negative
        """
        # ========================================================================
        # PARTIAL EXIT FOR PROFITABLE DCA ORDERS (Optional)
        # ========================================================================
        if self.ml_partial_exit_enabled:
            filled_entries = trade.select_filled_orders(trade.entry_side)
            
            # Skip first order (only evaluate DCA orders)
            if len(filled_entries) > 1:
                # Get ML predictions
                pred_15m, pred_30m, pred_1h = self.get_ml_predictions(trade.pair)
                
                # Count negative horizons
                negative_count = sum([
                    pred_15m < self.ml_exit_threshold_15m.value,
                    pred_30m < self.ml_exit_threshold_30m.value,
                    pred_1h < self.ml_exit_threshold_1h.value
                ])
                
                # Check if ML signals exit (2 out of 3 negative)
                if negative_count >= 2:
                    # Evaluate each DCA order (skip first order at index 0)
                    for i, order in enumerate(filled_entries[1:], start=1):
                        # Calculate profit for this specific order
                        order_profit = (current_rate - order.average) / order.average
                        
                        # Check if this order is profitable enough
                        if order_profit > self.ml_partial_exit_profit_threshold.value:
                            # Partial exit: return negative stake to close this order
                            from freqtrade.loggers import logger
                            
                            horizons_negative = []
                            if pred_15m < self.ml_exit_threshold_15m.value:
                                horizons_negative.append("15m")
                            if pred_30m < self.ml_exit_threshold_30m.value:
                                horizons_negative.append("30m")
                            if pred_1h < self.ml_exit_threshold_1h.value:
                                horizons_negative.append("1h")
                            
                            logger.info(
                                f"{trade.pair}: Partial exit order #{i+1} - "
                                f"order_profit={order_profit*100:.2f}%, "
                                f"ML({negative_count}/3 negative: {'+'.join(horizons_negative)}) - "
                                f"closing stake={order.cost:.2f}"
                            )
                            
                            # Return negative stake to close this specific order
                            return (
                                -order.cost,
                                f"partial_exit_order_{i+1}_profit_{order_profit*100:.1f}%"
                            )
        
        # ========================================================================
        # FULL EXIT LOGIC (Original)
        # ========================================================================
        # Exit only if minimum profit reached
        if current_profit <= self.min_profit_for_overbought_exit.value:
            return None
        
        # Get ML predictions for all 3 horizons
        pred_15m, pred_30m, pred_1h = self.get_ml_predictions(trade.pair)
        
        # Count how many predictions are below exit thresholds (negative)
        negative_count = sum([
            pred_15m < self.ml_exit_threshold_15m.value,
            pred_30m < self.ml_exit_threshold_30m.value,
            pred_1h < self.ml_exit_threshold_1h.value
        ])
        
        # Exit if at least 2 out of 3 horizons are negative
        if negative_count >= 2:
            horizons_negative = []
            if pred_15m < self.ml_exit_threshold_15m.value:
                horizons_negative.append("15m")
            if pred_30m < self.ml_exit_threshold_30m.value:
                horizons_negative.append("30m")
            if pred_1h < self.ml_exit_threshold_1h.value:
                horizons_negative.append("1h")
            
            from freqtrade.loggers import logger
            logger.info(
                f"{trade.pair}: Exit triggered by ML "
                f"({negative_count}/3 negative: {'+'.join(horizons_negative)}) - "
                f"15m={pred_15m:.4f}, 30m={pred_30m:.4f}, 1h={pred_1h:.4f} - "
                f"profit={current_profit*100:.2f}%"
            )
            
            return f"sell_ml_2of3_negative_{'+'.join(horizons_negative)}_{current_profit*100:.1f}%"
        
        return None
