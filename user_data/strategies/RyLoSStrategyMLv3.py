from datetime import UTC, timedelta

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

    # Parametri entry ottimizzabili - Multi-Oscillator Oversold
    rsi_oversold_threshold = DecimalParameter(25, 40, default=25.333, space="buy", optimize=True)
    bb_oversold_threshold = DecimalParameter(0.1, 0.3, default=0.294, space="buy", optimize=True)
    stochrsi_oversold_threshold = DecimalParameter(
        0, 30, default=0.782, space="buy", optimize=True
    )
    williams_oversold_threshold = DecimalParameter(
        -90, -70, default=-74.991, space="buy", optimize=True
    )
    min_oversold_count = IntParameter(2, 4, default=2, space="buy", optimize=True)

    # Emergency DCA (prima della liquidazione)
    emergency_dca_threshold = DecimalParameter(
        -0.18, -0.10, default=-0.124, space="buy", optimize=True
    )
    emergency_critical_multiplier = DecimalParameter(
        1.05, 2.0, default=1.175, space="buy", optimize=True
    )

    # Parametri per exit ottimizzabili - Multi-Oscillator Overbought
    rsi_overbought_threshold = DecimalParameter(60, 85, default=63.146, space="sell", optimize=True)
    bb_overbought_threshold = DecimalParameter(0.7, 0.9, default=0.871, space="sell", optimize=True)
    atr_overbought_multiplier = DecimalParameter(
        0.5, 2.0, default=0.556, space="sell", optimize=True
    )
    stochrsi_overbought_threshold = DecimalParameter(
        70, 100, default=94.809, space="sell", optimize=True
    )
    williams_overbought_threshold = DecimalParameter(
        -30, -10, default=-24.965, space="sell", optimize=True
    )
    min_overbought_count = IntParameter(2, 5, default=4, space="sell", optimize=True)
    min_profit_for_overbought_exit = DecimalParameter(
        0.01, 0.10, default=0.017, space="sell", optimize=True
    )

    # Auto-Reduce per over-exposure (disabilitato)
    auto_reduce_enabled = False  # Disabilitato - causava Loss in backtest

    # Trailing stop (ottimizzato da hyperopt)
    trailing_stop = False  # DISABILITATO per test ML

    # ML Filtro DCA (NUOVO - Conservativo)
    ml_dca_block_threshold = DecimalParameter(-0.05, -0.01, default=-0.02, space="buy", optimize=True)

    # ML Exit (NUOVO - Predizione breve termine 15min)
    ml_exit_threshold = DecimalParameter(-0.01, 0.02, default=0.005, space="sell", optimize=True)  # noqa: E501

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
        """Features base per FreqAI"""
        dataframe["%-rsi"] = ta.RSI(dataframe["close"], timeperiod=10)
        dataframe["%-atr_pct"] = (ta.ATR(dataframe, timeperiod=10) / dataframe["close"]) * 100

        stoch_k, _ = ta.STOCHRSI(dataframe["close"], timeperiod=10,
                                  fastk_period=5, fastd_period=3)
        dataframe["%-stochrsi"] = stoch_k

        dataframe["%-williams"] = ta.WILLR(dataframe, timeperiod=10)
        dataframe["%-pct_change"] = dataframe["close"].pct_change()
        dataframe["%-pct_change_vol"] = dataframe["volume"].pct_change()

        return dataframe

    def feature_engineering_standard(self, dataframe: DataFrame, metadata: dict,
                                     **kwargs) -> DataFrame:
        """Features standard"""
        dataframe["%-adx"] = ta.ADX(dataframe, timeperiod=14)
        dataframe["%-hour"] = dataframe["date"].dt.hour
        dataframe["%-day_of_week"] = dataframe["date"].dt.dayofweek

        return dataframe

    def set_freqai_targets(self, dataframe: DataFrame, metadata: dict,
                          **kwargs) -> DataFrame:
        """Target: variazione prezzo a 12 candele (1h) per DCA e Exit"""
        # Target 1h per DCA e Exit (stesso target)
        dataframe["&-s_close"] = (
            (dataframe["close"].shift(-12) - dataframe["close"]) /
            dataframe["close"]
        )

        return dataframe

    def get_ml_prediction(self, pair: str) -> float:
        """Ottieni predizione ML corrente (1h - per DCA)"""
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        if len(dataframe) < 1 or "&-s_close" not in dataframe.columns:
            return 0.0

        return dataframe["&-s_close"].iloc[-1]

    def get_ml_prediction_short(self, pair: str) -> float:
        """Ottieni predizione ML (usa stesso target 1h per Exit)"""
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        if len(dataframe) < 1 or "&-s_close" not in dataframe.columns:
            return 0.0

        return dataframe["&-s_close"].iloc[-1]

    def _count_overbought_indicators(self, candle) -> int:
        """Conta quanti indicatori sono in zona overbought"""
        count = 0

        if candle["rsi"] > self.rsi_overbought_threshold.value:
            count += 1
        if candle["bb_percent"] > self.bb_overbought_threshold.value:
            count += 1
        if candle["close"] > (
            candle["high"] - candle["atr"] * self.atr_overbought_multiplier.value
        ):
            count += 1
        if candle["stochrsi"] > self.stochrsi_overbought_threshold.value:
            count += 1
        if candle["williams_r"] > self.williams_overbought_threshold.value:
            count += 1

        return count

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

        # Calcola perdita dall'ultimo DCA filled (non dalla media)
        current_loss_from_last = (current_rate - last_order_price) / last_order_price

        if (
            current_loss_from_last <= self.emergency_dca_threshold.value
            and trade.nr_of_successful_entries < max_orders
        ):  # Rispetta max_orders
            # Soglia critica = emergency_threshold * multiplier
            critical_threshold = (
                self.emergency_dca_threshold.value * self.emergency_critical_multiplier.value
            )

            if current_loss_from_last <= critical_threshold and current_rate < last_order_price:
                # Emergency DCA: SALTA controllo BB threshold
                # Calcola stake come un DCA normale
                next_dca_order = trade.nr_of_successful_entries + 1
                stake_pct = self.first_order_pct.value * (
                    self.dca_multiplier.value ** (next_dca_order - 1)
                )
                emergency_stake = total_balance * stake_pct

                # Calcola stake totale della posizione (inclusi DCA)
                total_stake = sum(order.cost for order in filled_entries if order.cost)

                # Controlli sicurezza per Emergency DCA (riduce stake se necessario)
                current_position_value = total_stake * 4
                emergency_position_value = emergency_stake * 4

                # Verifica limite per pair - RIDUCE invece di bloccare
                if current_position_value + emergency_position_value > per_pair_limit:
                    remaining_per_pair = per_pair_limit - current_position_value
                    emergency_stake = remaining_per_pair / 4
                    emergency_position_value = emergency_stake * 4

                # Verifica limite globale - RIDUCE invece di bloccare
                if current_global_exposure + emergency_position_value > global_limit:
                    remaining_global = global_limit - current_global_exposure
                    emergency_stake = remaining_global / 4

                # Verifica min_stake dopo riduzioni
                if emergency_stake >= min_stake:
                    loss_pct = abs(current_loss_from_last * 100)
                    return emergency_stake, f"emergency_dca_{loss_pct:.1f}%"

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

        # ML FILTER: blocca DCA standard se predizione negativa (SOLO per DCA standard, NON emergency)  # noqa: E501
        ml_pred = self.get_ml_prediction(trade.pair)
        if ml_pred < self.ml_dca_block_threshold.value:
            from freqtrade.loggers import logger
            logger.info(
                f"{trade.pair}: DCA blocked by ML filter "
                f"(pred={ml_pred:.4f} < threshold={self.ml_dca_block_threshold.value:.4f})"
            )
            return None

        return next_stake, f"dca_{entry_count + 1}_{current_profit*100:.1f}%"

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # FreqAI DEVE essere chiamato PRIMA
        dataframe = self.freqai.start(dataframe, metadata, self)

        # RSI periodo 10 per maggiore reattività su 5min
        dataframe["rsi"] = ta.RSI(dataframe["close"], timeperiod=10)

        # Stochastic RSI periodo 10 (configurazione 10-5-3)
        stochrsi_k, _ = ta.STOCHRSI(
            dataframe["close"], timeperiod=10, fastk_period=5, fastd_period=3
        )
        dataframe["stochrsi"] = stochrsi_k  # Usa %K (più reattivo)

        # Bollinger Bands %B (20 periodi standard)
        bb_upper, _, bb_lower = ta.BBANDS(
            dataframe["close"], timeperiod=20, nbdevup=2.0, nbdevdn=2.0
        )
        dataframe["bb_percent"] = (dataframe["close"] - bb_lower) / (bb_upper - bb_lower)

        # ATR periodo 10 per volatilità più reattiva
        dataframe["atr"] = ta.ATR(
            dataframe["high"], dataframe["low"], dataframe["close"], timeperiod=10
        )

        # Williams %R periodo 10
        dataframe["williams_r"] = ta.WILLR(
            dataframe["high"], dataframe["low"], dataframe["close"], timeperiod=10
        )

        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # Multi-Oscillator Oversold: conta quanti indicatori sono in oversold (4 attivi)
        rsi_oversold = (
            (dataframe["rsi"] < self.rsi_oversold_threshold.value).fillna(False).astype(int)
        )
        bb_oversold = (
            (dataframe["bb_percent"] < self.bb_oversold_threshold.value).fillna(False).astype(int)
        )

        # Stochastic RSI oversold: timing preciso
        stochrsi_oversold = (
            (dataframe["stochrsi"] < self.stochrsi_oversold_threshold.value)
            .fillna(False)
            .astype(int)
        )

        # Williams %R oversold
        williams_oversold = (
            (dataframe["williams_r"] < self.williams_oversold_threshold.value)
            .fillna(False)
            .astype(int)
        )

        oversold_count = (
            rsi_oversold + bb_oversold + stochrsi_oversold + williams_oversold
        )

        # Crea tag parlanti per indicare quali indicatori hanno scatenato l'entry
        dataframe["enter_tag"] = ""

        entry_condition = (oversold_count >= self.min_oversold_count.value) & (
            dataframe["close"] < dataframe["open"]
        )

        for i in range(len(dataframe)):
            if entry_condition.iloc[i]:
                indicators = []
                if rsi_oversold.iloc[i]:
                    indicators.append("rsi")
                if bb_oversold.iloc[i]:
                    indicators.append("bb")
                if stochrsi_oversold.iloc[i]:
                    indicators.append("stochrsi")
                if williams_oversold.iloc[i]:
                    indicators.append("wr")

                dataframe.loc[dataframe.index[i], "enter_tag"] = f"buy_({'+'.join(indicators)})"

        dataframe.loc[entry_condition, "enter_long"] = 1
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
        total_balance = self.wallets.get_total_stake_amount()
        max_open_trades = self.config.get("max_open_trades", 1)

        # Auto-Reduce: logica Passivbot (DISABILITATO)
        if self.auto_reduce_enabled:
            # Calcola exposure di QUESTO trade
            filled_entries = trade.select_filled_orders(trade.entry_side)
            total_stake = sum(order.cost for order in filled_entries if order.cost)
            position_exposure = total_stake * 4  # leverage 4x

            # Calcola limite per-pair
            per_pair_limit = (total_balance * 4) / max_open_trades
            exposure_ratio = position_exposure / per_pair_limit if per_pair_limit > 0 else 0

            # Trigger: se questo trade supera 101% del suo limite
            if exposure_ratio > 1.01:
                # Interpolazione lineare per calcolare ideal stake
                stake_lowered = total_stake * 0.9
                exposure_lowered = stake_lowered * 4

                target_exposure = per_pair_limit * 1.01

                # Interpolazione: ideal_stake = stake_lowered + (target - exposure_lowered) * (total_stake - stake_lowered) / (position_exposure - exposure_lowered)  # noqa: E501
                if position_exposure != exposure_lowered:
                    ideal_stake = stake_lowered + (target_exposure - exposure_lowered) * (total_stake - stake_lowered) / (position_exposure - exposure_lowered)  # noqa: E501
                else:
                    ideal_stake = total_stake

                # Calcola quanto ridurre
                auto_reduce_stake = total_stake - ideal_stake

                if auto_reduce_stake > 0:
                    return -auto_reduce_stake, f"sell_auto_reduce_{auto_reduce_stake:.2f}"

        # Exit Unificato: Multi-Oscillator Overbought + ML Conferma (15min)
        if current_profit > self.min_profit_for_overbought_exit.value:
            dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
            current_candle = dataframe.iloc[-1]

            # CONDIZIONE 1: Conta oscillatori overbought
            overbought_count = self._count_overbought_indicators(current_candle)

            # CONDIZIONE 2: Candela verde
            is_green_candle = current_candle["close"] > current_candle["open"]

            if overbought_count >= self.min_overbought_count.value and is_green_candle:
                # CONDIZIONE 3: ML conferma con predizione breve (15min)
                ml_pred_short = self.get_ml_prediction_short(trade.pair)

                # Exit se ML predice calo o stagnazione
                if ml_pred_short < self.ml_exit_threshold.value:
                    from freqtrade.loggers import logger
                    logger.info(
                        f"{trade.pair}: Exit overbought + ML confirmed "
                        f"(pred_1h={ml_pred_short:.4f} < {self.ml_exit_threshold.value:.4f})"
                    )
                    return f"sell_overbought_ml_{ml_pred_short*100:.2f}%"

        return None
