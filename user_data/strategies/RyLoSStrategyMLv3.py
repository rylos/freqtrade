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
    stoploss = -0.22  # Fallback stoploss (overridden by ML-driven logic in custom_stoploss)

    # ROI disabilitato - usa solo custom_exit
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
        0.015, 0.025, default=0.018, space="buy", optimize=True,
        load=True, decimals=4
    )
    ml_dca_distance_wide = DecimalParameter(
        0.035, 0.055, default=0.045, space="buy", optimize=True,
        load=True, decimals=4
    )
    
    # ML prediction range for DCA distance mapping
    # Strong positive → tight distance
    # Weak/negative → wide distance
    ml_dca_pred_min = DecimalParameter(
        -0.02, 0.0, default=-0.01, space="buy", optimize=True,
        load=True, decimals=4
    )
    ml_dca_pred_max = DecimalParameter(
        0.01, 0.04, default=0.02, space="buy", optimize=True,
        load=True, decimals=4
    )
    
    # ============================================================================
    # CORE DCA PARAMETERS (3 optimizable)
    # ============================================================================
    
    first_order_pct = DecimalParameter(
        0.005, 0.03, default=0.029, space="buy", optimize=True,
        load=True, decimals=4
    )
    dca_multiplier = DecimalParameter(
        1.5, 3.0, default=1.991, space="buy", optimize=True,
        load=True, decimals=3
    )
    
    # DCA dinamico basato su volatilità ATR
    dca_atr_multiplier = DecimalParameter(
        0.5, 3.0, default=2.306, space="buy", optimize=True,
        load=True, decimals=3
    )

    # DCA cooldown dinamico (numero di candele da aspettare)
    dca_cooldown_candles = IntParameter(
        1, 5, default=2, space="buy", optimize=False,
        load=True
    )

    # Exit parameters
    min_profit_for_overbought_exit = DecimalParameter(
        0.01, 0.10, default=0.017, space="sell", optimize=True,
        load=True, decimals=4
    )

    # Auto-Reduce per over-exposure (disabilitato)
    auto_reduce_enabled = False  # Disabilitato - causava Loss in backtest

    # Trailing stop (disabilitato)
    trailing_stop = False  # DISABILITATO per test ML

    # ============================================================================
    # ML THRESHOLD PARAMETERS (9 optimizable - Multi-Horizon)
    # ============================================================================
    
    # Entry Thresholds (2 out of 3 must be positive)
    ml_entry_threshold_5m = DecimalParameter(
        -0.01, 0.02, default=0.005, space="buy", optimize=True,
        load=True, decimals=4
    )
    ml_entry_threshold_15m = DecimalParameter(
        -0.01, 0.02, default=0.005, space="buy", optimize=True,
        load=True, decimals=4
    )
    ml_entry_threshold_30m = DecimalParameter(
        -0.01, 0.02, default=0.005, space="buy", optimize=True,
        load=True, decimals=4
    )
    
    # DCA Thresholds (2 out of 3 must be positive)
    ml_dca_threshold_5m = DecimalParameter(
        -0.05, 0.01, default=-0.01, space="buy", optimize=True,
        load=True, decimals=4
    )
    ml_dca_threshold_15m = DecimalParameter(
        -0.05, 0.01, default=-0.01, space="buy", optimize=True,
        load=True, decimals=4
    )
    ml_dca_threshold_30m = DecimalParameter(
        -0.05, 0.01, default=-0.01, space="buy", optimize=True,
        load=True, decimals=4
    )
    
    # Exit Threshold (only 5m for fastest reaction)
    ml_exit_threshold_5m = DecimalParameter(
        -0.02, -0.001, default=-0.005, space="sell", optimize=True,
        load=True, decimals=4
    )
    
    # ============================================================================
    # ML-DRIVEN DYNAMIC STOPLOSS PARAMETERS (5 optimizable)
    # ============================================================================
    
    # Enable/disable ML-driven dynamic stoploss
    ml_dynamic_stoploss_enabled = True  # Set to False to use fixed stoploss
    
    # Dynamic stoploss range based on ML confidence
    # When all 3 predictions are very negative → tight stoploss
    # When predictions are neutral/positive → loose stoploss
    ml_stoploss_tight = DecimalParameter(
        -0.18, -0.08, default=-0.12, space="sell", optimize=True,
        load=True, decimals=3
    )
    ml_stoploss_loose = DecimalParameter(
        -0.30, -0.18, default=-0.25, space="sell", optimize=True,
        load=True, decimals=3
    )
    
    # ML prediction range for stoploss mapping
    # Very negative prediction → tight stoploss
    # Neutral/positive prediction → loose stoploss
    ml_stoploss_pred_min = DecimalParameter(
        -0.10, -0.02, default=-0.05, space="sell", optimize=True,
        load=True, decimals=4
    )
    ml_stoploss_pred_max = DecimalParameter(
        -0.02, 0.02, default=0.0, space="sell", optimize=True,
        load=True, decimals=4
    )
    
    # Minimum loss to activate dynamic stoploss check
    ml_stoploss_activation_loss = DecimalParameter(
        -0.18, -0.05, default=-0.10, space="sell", optimize=True,
        load=True, decimals=3
    )
    
    # ============================================================================
    # ML CONFIDENCE-BASED STAKE SIZING (Optional - 2 optimizable)
    # ============================================================================
    
    # Enable/disable confidence-based stake sizing
    ml_stake_confidence_enabled = False  # Set to True to enable
    
    # Prediction range for confidence mapping
    ml_confidence_min = DecimalParameter(
        -0.02, 0.0, default=-0.01, space="buy", optimize=True,
        load=True, decimals=4
    )
    ml_confidence_max = DecimalParameter(
        0.01, 0.05, default=0.02, space="buy", optimize=True,
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
        """Multi-horizon targets: 5min, 15min, 30min price change predictions"""
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
        pred_5m, pred_15m, pred_30m = self.get_ml_predictions(trade.pair)
        
        positive_count = sum([
            pred_5m > self.ml_dca_threshold_5m.value,
            pred_15m > self.ml_dca_threshold_15m.value,
            pred_30m > self.ml_dca_threshold_30m.value
        ])
        
        if positive_count < 2:
            # Block DCA - less than 2 horizons are positive
            from freqtrade.loggers import logger
            horizons_status = []
            if pred_5m > self.ml_dca_threshold_5m.value:
                horizons_status.append("5m:✓")
            else:
                horizons_status.append("5m:✗")
            if pred_15m > self.ml_dca_threshold_15m.value:
                horizons_status.append("15m:✓")
            else:
                horizons_status.append("15m:✗")
            if pred_30m > self.ml_dca_threshold_30m.value:
                horizons_status.append("30m:✓")
            else:
                horizons_status.append("30m:✗")
            
            logger.info(
                f"{trade.pair}: DCA blocked by ML filter "
                f"({positive_count}/3 positive) - "
                f"{' '.join(horizons_status)} - "
                f"5m={pred_5m:.4f}, 15m={pred_15m:.4f}, 30m={pred_30m:.4f}"
            )
            return None
        
        # DCA allowed - at least 2/3 horizons are positive
        from freqtrade.loggers import logger
        horizons_positive = []
        if pred_5m > self.ml_dca_threshold_5m.value:
            horizons_positive.append("5m")
        if pred_15m > self.ml_dca_threshold_15m.value:
            horizons_positive.append("15m")
        if pred_30m > self.ml_dca_threshold_30m.value:
            horizons_positive.append("30m")
        
        logger.info(
            f"{trade.pair}: DCA allowed by ML filter "
            f"({positive_count}/3 positive: {'+'.join(horizons_positive)}) - "
            f"5m={pred_5m:.4f}, 15m={pred_15m:.4f}, 30m={pred_30m:.4f}"
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
        ML-driven entry logic: At least 2 out of 3 horizons must be positive.
        
        Entry signal generated when:
        - At least 2 of the following are true:
          * pred_5m > ml_entry_threshold_5m
          * pred_15m > ml_entry_threshold_15m
          * pred_30m > ml_entry_threshold_30m
        """
        # Get ML predictions for all 3 horizons
        pair = metadata["pair"]
        
        # Initialize columns
        dataframe["enter_long"] = 0
        dataframe["enter_tag"] = ""
        
        # Check if ML predictions are available
        if "&-s_close_5m" not in dataframe.columns:
            return dataframe
        
        # Count how many horizons are positive
        positive_5m = dataframe["&-s_close_5m"] > self.ml_entry_threshold_5m.value
        positive_15m = dataframe["&-s_close_15m"] > self.ml_entry_threshold_15m.value
        positive_30m = dataframe["&-s_close_30m"] > self.ml_entry_threshold_30m.value
        
        # ML-based entry condition: At least 2 out of 3 horizons must be positive
        positive_count = positive_5m.astype(int) + positive_15m.astype(int) + positive_30m.astype(int)
        entry_condition = positive_count >= 2
        
        # Set entry signal
        dataframe.loc[entry_condition, "enter_long"] = 1
        
        # Create descriptive tags with prediction values and which horizons are positive
        for i in dataframe[entry_condition].index:
            pred_5m = dataframe.loc[i, "&-s_close_5m"]
            pred_15m = dataframe.loc[i, "&-s_close_15m"]
            pred_30m = dataframe.loc[i, "&-s_close_30m"]
            
            horizons_positive = []
            if positive_5m.loc[i]:
                horizons_positive.append("5m")
            if positive_15m.loc[i]:
                horizons_positive.append("15m")
            if positive_30m.loc[i]:
                horizons_positive.append("30m")
            
            dataframe.loc[i, "enter_tag"] = (
                f"buy_ml_2of3_{'+'.join(horizons_positive)}_"
                f"5m:{pred_5m:.4f}_"
                f"15m:{pred_15m:.4f}_"
                f"30m:{pred_30m:.4f}"
            )
        
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
        ML-driven dynamic stoploss.
        
        Stoploss becomes tighter when ML predicts strong downtrend,
        looser when ML is neutral/positive.
        
        Only activates when:
        1. Loss exceeds activation threshold
        2. DCA is exhausted (no more capital or max orders reached)
        
        Returns:
            Stoploss value (negative float, e.g., -0.15 for -15%)
        """
        if not self.ml_dynamic_stoploss_enabled:
            return self.stoploss  # Use fixed stoploss
        
        # Only activate dynamic stoploss if loss exceeds threshold
        if current_profit >= self.ml_stoploss_activation_loss.value:
            return -1  # No stoploss (let DCA work)
        
        # CRITICAL: Only use dynamic stoploss if DCA is exhausted
        if self.can_dca_further(trade):
            from freqtrade.loggers import logger
            logger.info(
                f"{pair}: Dynamic stoploss NOT active - DCA still possible - "
                f"loss={current_profit*100:.2f}%, entries={trade.nr_of_successful_entries}"
            )
            return -1  # No stoploss (let DCA work)
        
        # Get ML predictions for all 3 horizons
        pred_5m, pred_15m, pred_30m = self.get_ml_predictions(trade.pair)
        avg_prediction = (pred_5m + pred_15m + pred_30m) / 3
        
        # Map prediction to stoploss: very negative → tight, neutral/positive → loose
        min_pred = self.ml_stoploss_pred_min.value
        max_pred = self.ml_stoploss_pred_max.value
        
        # Clamp prediction to range
        clamped_pred = max(min_pred, min(avg_prediction, max_pred))
        
        # Linear interpolation: [min_pred, max_pred] → [tight, loose]
        if max_pred > min_pred:
            stoploss_ratio = (clamped_pred - min_pred) / (max_pred - min_pred)
        else:
            stoploss_ratio = 0.5  # Fallback to middle
        
        dynamic_stoploss = (
            self.ml_stoploss_tight.value +
            stoploss_ratio * (self.ml_stoploss_loose.value - self.ml_stoploss_tight.value)
        )
        
        from freqtrade.loggers import logger
        logger.warning(
            f"{pair}: Dynamic stoploss ACTIVE - DCA exhausted - "
            f"avg_pred={avg_prediction:.4f}, "
            f"stoploss={dynamic_stoploss:.4f} "
            f"(tight={self.ml_stoploss_tight.value:.4f}, "
            f"loose={self.ml_stoploss_loose.value:.4f}) - "
            f"loss={current_profit*100:.2f}%, entries={trade.nr_of_successful_entries}"
        )
        
        return dynamic_stoploss
        """
        Check if DCA is still possible for this trade.
        
        Returns:
            True if DCA can continue, False if exhausted (capital or max orders)
        """
        total_balance = self.wallets.get_total_stake_amount()
        max_open_trades = self.config.get("max_open_trades", 1)
        
        # Check max orders limit
        max_orders = self.calculate_max_orders(total_balance)
        if trade.nr_of_successful_entries > max_orders:
            return False
        
        # Check global exposure limit
        global_limit = total_balance * 4
        current_global_exposure = self.get_total_position_value()
        if current_global_exposure >= global_limit * 0.95:
            return False
        
        # Check available balance for next DCA
        available_balance = self.wallets.get_available_stake_amount()
        entry_count = trade.nr_of_successful_entries
        next_stake_pct = self.first_order_pct.value * (self.dca_multiplier.value**entry_count)
        next_stake = total_balance * next_stake_pct
        
        if next_stake > available_balance:
            return False
        
        return True

    def can_dca_further(self, trade: Trade) -> bool:
        """
        Check if DCA is still possible for this trade.
        
        Returns:
            True if DCA can continue, False if exhausted (capital or max orders)
        """
        total_balance = self.wallets.get_total_stake_amount()
        max_open_trades = self.config.get("max_open_trades", 1)
        
        # Check max orders limit
        max_orders = self.calculate_max_orders(total_balance)
        if trade.nr_of_successful_entries > max_orders:
            return False
        
        # Check global exposure limit
        global_limit = total_balance * 4
        current_global_exposure = self.get_total_position_value()
        if current_global_exposure >= global_limit * 0.95:
            return False
        
        # Check available balance for next DCA
        available_balance = self.wallets.get_available_stake_amount()
        entry_count = trade.nr_of_successful_entries
        next_stake_pct = self.first_order_pct.value * (self.dca_multiplier.value**entry_count)
        next_stake = total_balance * next_stake_pct
        
        if next_stake > available_balance:
            return False
        
        return True

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
        ML-driven exit logic with smart stoploss.
        
        Exit scenarios:
        1. PROFIT EXIT: profit > min AND 5m horizon negative (fastest reaction)
        
        Note: Stoploss is now handled by custom_stoploss() method
        """
        # Get ML predictions for all 3 horizons
        pred_5m, pred_15m, pred_30m = self.get_ml_predictions(trade.pair)
        
        # ============================================================================
        # PROFIT EXIT (only 5m for fastest reaction)
        # ============================================================================
        if current_profit > self.min_profit_for_overbought_exit.value:
            if pred_5m < self.ml_exit_threshold_5m.value:
                from freqtrade.loggers import logger
                logger.info(
                    f"{trade.pair}: Profit exit triggered by ML 5m - "
                    f"5m={pred_5m:.4f} (threshold={self.ml_exit_threshold_5m.value:.4f}) - "
                    f"15m={pred_15m:.4f}, 30m={pred_30m:.4f} - "
                    f"profit={current_profit*100:.2f}%"
                )
                
                return f"sell_ml_5m_{current_profit*100:.1f}%"
        
        return None
