import talib.abstract as ta
from pandas import DataFrame
from datetime import datetime, timedelta, timezone

from freqtrade.strategy import DecimalParameter, IntParameter, IStrategy, Trade, timeframe_to_minutes


class RyLoSStrategy(IStrategy):
    timeframe = "5m"
    can_short = False
    process_only_new_candles = True
    position_adjustment_enable = True
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
    trailing_stop = True
    trailing_stop_positive = 0.227
    trailing_stop_positive_offset = 0.315
    trailing_only_offset_is_reached = False

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
        """Calcola distanza DCA dinamica: dca_distance × (1 + ATR% × multiplier)"""
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        if len(dataframe) < 1:
            return self.dca_distance.value
        
        current_candle = dataframe.iloc[-1]
        atr = current_candle["atr"]
        
        # ATR normalizzato in percentuale
        atr_pct = atr / current_rate
        
        # Distanza dinamica: base × (1 + volatilità × multiplier)
        distance = self.dca_distance.value * (1 + atr_pct * self.dca_atr_multiplier.value)
        
        return distance

    def adjust_trade_position(
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
            last_order_time = filled_entries[-1].order_filled_date.replace(tzinfo=timezone.utc)
            cooldown_minutes = timeframe_to_minutes(self.timeframe) * self.dca_cooldown_candles.value
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

        return next_stake, f"dca_{entry_count + 1}_{current_profit*100:.1f}%"

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
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
        max_orders = self.calculate_max_orders(total_balance)

        # Auto-Reduce: logica Passivbot
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
                
                # Interpolazione: ideal_stake = stake_lowered + (target - exposure_lowered) * (total_stake - stake_lowered) / (position_exposure - exposure_lowered)
                if position_exposure != exposure_lowered:
                    ideal_stake = stake_lowered + (target_exposure - exposure_lowered) * (total_stake - stake_lowered) / (position_exposure - exposure_lowered)
                else:
                    ideal_stake = total_stake
                
                # Calcola quanto ridurre
                auto_reduce_stake = total_stake - ideal_stake
                
                if auto_reduce_stake > 0:
                    return -auto_reduce_stake, f"sell_auto_reduce_{auto_reduce_stake:.2f}"

        # Multi-Oscillator Exit
        if current_profit > self.min_profit_for_overbought_exit.value:
            dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
            current_candle = dataframe.iloc[-1]

            # Controlla quali indicatori sono overbought
            indicators = []
            if current_candle["rsi"] > self.rsi_overbought_threshold.value:
                indicators.append("rsi")
            if current_candle["bb_percent"] > self.bb_overbought_threshold.value:
                indicators.append("bb")
            if current_candle["close"] > (
                current_candle["high"]
                - current_candle["atr"] * self.atr_overbought_multiplier.value
            ):
                indicators.append("atr")
            if current_candle["stochrsi"] > self.stochrsi_overbought_threshold.value:
                indicators.append("stochrsi")
            if current_candle["williams_r"] > self.williams_overbought_threshold.value:
                indicators.append("wr")

            overbought_count = len(indicators)

            if (
                overbought_count >= self.min_overbought_count.value
                and current_candle["close"] > current_candle["open"]
            ):
                return f"sell_overbought_({'+'.join(indicators)})"

        return None
