import talib.abstract as ta
from pandas import DataFrame

from freqtrade.strategy import DecimalParameter, IntParameter, IStrategy, Trade


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
    first_order_pct = DecimalParameter(0.005, 0.10, default=0.081, space="buy", optimize=True)
    dca_distance = DecimalParameter(0.002, 0.05, default=0.034, space="buy", optimize=True)
    dca_multiplier = DecimalParameter(1.5, 3.0, default=2.734, space="buy", optimize=True)

    # Parametri entry ottimizzabili - Multi-Oscillator Oversold
    rsi_oversold_threshold = DecimalParameter(25, 40, default=37.778, space="buy", optimize=True)
    bb_oversold_threshold = DecimalParameter(0.1, 0.3, default=0.202, space="buy", optimize=True)
    atr_oversold_multiplier = DecimalParameter(0.5, 2.0, default=1.615, space="buy", optimize=True)
    macd_oversold_threshold = DecimalParameter(
        -0.01, -0.001, default=-0.003, space="buy", optimize=True
    )
    williams_oversold_threshold = DecimalParameter(
        -90, -70, default=-86.362, space="buy", optimize=True
    )
    min_oversold_count = IntParameter(2, 5, default=3, space="buy", optimize=True)

    # Emergency DCA (prima della liquidazione)
    emergency_dca_threshold = DecimalParameter(
        -0.18, -0.10, default=-0.104, space="buy", optimize=True
    )
    emergency_critical_multiplier = DecimalParameter(
        1.05, 2.0, default=1.467, space="buy", optimize=True
    )

    # Parametri per exit ottimizzabili - Multi-Oscillator Overbought
    rsi_overbought_threshold = DecimalParameter(60, 85, default=82.766, space="sell", optimize=True)
    bb_overbought_threshold = DecimalParameter(0.7, 0.9, default=0.895, space="sell", optimize=True)
    atr_overbought_multiplier = DecimalParameter(
        0.5, 2.0, default=0.527, space="sell", optimize=True
    )
    macd_overbought_threshold = DecimalParameter(
        0.001, 0.01, default=0.005, space="sell", optimize=True
    )
    williams_overbought_threshold = DecimalParameter(
        -30, -10, default=-10.143, space="sell", optimize=True
    )
    min_overbought_count = IntParameter(2, 5, default=3, space="sell", optimize=True)
    min_profit_for_overbought_exit = DecimalParameter(
        0.01, 0.10, default=0.013, space="sell", optimize=True
    )

    # Last DCA Profit Skimming
    last_dca_profit_threshold = DecimalParameter(
        0.01, 0.10, default=0.078, space="sell", optimize=True
    )

    # Auto-Reduce per over-exposure
    auto_reduce_threshold = DecimalParameter(1.0, 1.1, default=1.071, space="sell", optimize=True)
    auto_reduce_critical_threshold = DecimalParameter(
        1.06, 1.15, default=1.15, space="sell", optimize=True
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
        return 5.0

    def get_total_position_value(self) -> float:
        """Calcola il valore totale delle posizioni aperte su tutte le pairs"""
        total_value = 0
        open_trades = Trade.get_open_trades()

        for trade in open_trades:
            position_value = trade.stake_amount * 5
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
        global_limit = total_balance * 5
        per_pair_limit = global_limit / max_open_trades

        # Esposizione attuale globale
        current_global_exposure = self.get_total_position_value()
        remaining_global = global_limit - current_global_exposure

        # Primo ordine: percentuale del balance totale
        base_stake = total_balance * self.first_order_pct.value

        # Limita al rimanente globale e al limite per pair
        max_allowed_stake = min(remaining_global / 5, per_pair_limit / 5)

        return min(base_stake, max_allowed_stake, max_stake)

    def calculate_max_orders(self, total_balance: float) -> int:
        """Calcola dinamicamente il numero massimo di ordini basato sui parametri ottimizzati"""
        max_open_trades = self.config.get("max_open_trades", 1)
        per_pair_limit = (total_balance * 5) / max_open_trades

        cumulative_stake = 0
        order_count = 0

        # Simula gli ordini fino al limite per pair
        for i in range(20):  # Limite di sicurezza
            if i == 0:
                stake = total_balance * self.first_order_pct.value
            else:
                stake_pct = self.first_order_pct.value * (self.dca_multiplier.value ** i)
                stake = total_balance * stake_pct

            position_value = stake * 5

            if cumulative_stake + position_value > per_pair_limit:
                break

            cumulative_stake += position_value
            order_count += 1

        return order_count - 1  # -1 perché primo ordine non conta come adjustment

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
    ) -> float:
        total_balance = self.wallets.get_total_stake_amount()
        max_open_trades = self.config.get("max_open_trades", 1)

        # Calcola dinamicamente il numero massimo di ordini per questa pair
        max_orders = self.calculate_max_orders(total_balance)

        # Limiti globali e per pair (calcolo unificato)
        global_limit = total_balance * 5
        per_pair_limit = global_limit / max_open_trades
        current_global_exposure = self.get_total_position_value()

        # Emergency DCA con doppio controllo (rispetta max_orders)
        current_loss_from_avg = (current_rate - trade.open_rate) / trade.open_rate
        last_order_price = trade.orders[-1].price if trade.orders else trade.open_rate
        if last_order_price is None:
            last_order_price = trade.open_rate

        if (
            current_loss_from_avg <= self.emergency_dca_threshold.value
            and trade.nr_of_successful_entries < max_orders
        ):  # Rispetta max_orders
            # Soglia critica = emergency_threshold * multiplier
            critical_threshold = (
                self.emergency_dca_threshold.value * self.emergency_critical_multiplier.value
            )

            if current_loss_from_avg <= critical_threshold and current_rate < last_order_price:
                # Calcola stake come un DCA normale
                next_dca_order = trade.nr_of_successful_entries + 1
                stake_pct = self.first_order_pct.value * (
                    self.dca_multiplier.value ** (next_dca_order - 1)
                )
                emergency_stake = total_balance * stake_pct

                # Controlli sicurezza per Emergency DCA
                current_position_value = trade.stake_amount * 5
                emergency_position_value = emergency_stake * 5

                # Verifica limite globale
                if current_global_exposure + emergency_position_value > global_limit:
                    return None  # Blocca se supera limite globale

                # Verifica limite per pair
                if current_position_value + emergency_position_value > per_pair_limit:
                    return None  # Blocca se supera limite per pair

                # Verifica solo min_stake (logica coerente)
                if emergency_stake >= min_stake:
                    return emergency_stake

        # Se abbiamo raggiunto il numero massimo di ordini per questa pair
        if trade.nr_of_successful_entries > max_orders:
            return None

        # Verifica se abbiamo raggiunto il limite globale
        if current_global_exposure >= global_limit * 0.95:  # 95% del limite per sicurezza
            return None

        # Wallet disponibile e posizione corrente
        available_balance = self.wallets.get_available_stake_amount()
        current_position_value = trade.stake_amount * 5

        # Calcola il prossimo stake
        entry_count = trade.nr_of_successful_entries
        next_stake_pct = self.first_order_pct.value * (self.dca_multiplier.value**entry_count)
        next_stake = total_balance * next_stake_pct

        # Verifica se available_balance è sufficiente
        if next_stake > available_balance:
            return None  # Non abbastanza fondi

        next_position_value = next_stake * 5

        # Verifica limite per pair
        if current_position_value + next_position_value > per_pair_limit:
            remaining_per_pair = per_pair_limit - current_position_value
            next_stake = remaining_per_pair / 5
            if next_stake < min_stake:
                return None

        # Verifica limite globale
        remaining_global = global_limit - current_global_exposure
        if next_position_value > remaining_global:
            next_stake = remaining_global / 5
            if next_stake < min_stake:
                return None

        # Controlla distanza minima dall'ultimo ordine (solo in discesa)
        if trade.orders:
            last_order_rate = trade.orders[-1].price
            if last_order_rate is None:
                last_order_rate = trade.open_rate
            price_distance = abs(current_rate - last_order_rate) / last_order_rate

            # DCA solo se: distanza sufficiente E prezzo più basso dell'ultimo ordine
            if price_distance < self.dca_distance.value or current_rate >= last_order_rate:
                return None

        return next_stake

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # RSI usando close (default TradingView)
        dataframe["rsi"] = ta.RSI(dataframe["close"], timeperiod=14)

        # Bollinger Bands %B
        bb_upper, bb_middle, bb_lower = ta.BBANDS(
            dataframe["close"], timeperiod=20, nbdevup=2.0, nbdevdn=2.0
        )
        dataframe["bb_percent"] = (dataframe["close"] - bb_lower) / (bb_upper - bb_lower)

        # ATR (Average True Range)
        dataframe["atr"] = ta.ATR(
            dataframe["high"], dataframe["low"], dataframe["close"], timeperiod=14
        )

        # MACD
        macd, macdsignal, macdhist = ta.MACD(
            dataframe["close"], fastperiod=12, slowperiod=26, signalperiod=9
        )
        dataframe["macd"] = macd
        dataframe["macd_signal"] = macdsignal
        dataframe["macd_hist"] = macdhist

        # Williams %R
        dataframe["williams_r"] = ta.WILLR(
            dataframe["high"], dataframe["low"], dataframe["close"], timeperiod=14
        )

        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # Multi-Oscillator Oversold: conta quanti indicatori sono in oversold (tutti e 5)
        rsi_oversold = (
            (dataframe["rsi"] < self.rsi_oversold_threshold.value).fillna(False).astype(int)
        )
        bb_oversold = (
            (dataframe["bb_percent"] < self.bb_oversold_threshold.value).fillna(False).astype(int)
        )

        # ATR oversold: prezzo vicino al low recente (ATR-based)
        atr_low_threshold = dataframe["low"].rolling(14).min() + (
            dataframe["atr"] * self.atr_oversold_multiplier.value
        )
        atr_oversold = (dataframe["close"] < atr_low_threshold).fillna(False).astype(int)

        # MACD oversold: MACD sotto soglia negativa
        macd_oversold = (
            (dataframe["macd"] < self.macd_oversold_threshold.value).fillna(False).astype(int)
        )

        # Williams %R oversold
        williams_oversold = (
            (dataframe["williams_r"] < self.williams_oversold_threshold.value)
            .fillna(False)
            .astype(int)
        )

        oversold_count = (
            rsi_oversold + bb_oversold + atr_oversold + macd_oversold + williams_oversold
        )

        # Crea tag parlanti per indicare quali indicatori hanno scatenato l'entry
        dataframe["entry_tag"] = ""

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
                if atr_oversold.iloc[i]:
                    indicators.append("atr")
                if macd_oversold.iloc[i]:
                    indicators.append("macd")
                if williams_oversold.iloc[i]:
                    indicators.append("wr")

                dataframe.loc[dataframe.index[i], "entry_tag"] = f"buy_({'+'.join(indicators)})"

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

        # Auto-Reduce: protezione over-exposure con esclusione intelligente
        global_limit = total_balance * 5  # Limite globale con leva 5x
        current_global_exposure = self.get_total_position_value()
        exposure_ratio = current_global_exposure / global_limit if global_limit > 0 else 0

        if exposure_ratio > self.auto_reduce_threshold.value:
            # Controlla se ultimo DCA è profittevole (per esclusione intelligente)
            ultimo_dca_profittevole = False
            if trade.nr_of_successful_entries >= max_orders and trade.orders:
                last_order = trade.orders[-1]
                last_order_price = last_order.price
            if last_order_price is None:
                last_order_price = trade.open_rate
                ultimo_dca_profittevole = current_rate > last_order_price * (
                    1 + self.last_dca_profit_threshold.value
                )

            # Se siamo POCO over-exposed E ultimo DCA è profittevole
            if (
                exposure_ratio < self.auto_reduce_critical_threshold.value
                and ultimo_dca_profittevole
            ):
                # Prova PRIMA profit skimming (potrebbe risolvere over-exposure)
                if hasattr(trade.orders[-1], "cost") and trade.orders[-1].cost:
                    last_dca_stake = trade.orders[-1].cost
                else:
                    last_dca_stake = total_balance * 0.3

                last_dca_quantity = last_dca_stake / last_order_price
                current_value = last_dca_quantity * current_rate
                profit_only = current_value - last_dca_stake

                if profit_only > 0:
                    return f"sell_last_dca_skim_{profit_only:.2f}"

            # Altrimenti procedi con auto-reduce
            target_exposure = global_limit * self.auto_reduce_threshold.value
            over_exposure = current_global_exposure - target_exposure

            # Calcola quanto ridurre da questa posizione (proporzionale)
            current_position_exposure = trade.stake_amount * 5
            position_ratio = (
                current_position_exposure / current_global_exposure
                if current_global_exposure > 0
                else 0
            )
            reduce_exposure = over_exposure * position_ratio
            reduce_amount = reduce_exposure / 5  # Diviso leva per ottenere stake amount

            # Assicurati che non superi la posizione corrente
            reduce_amount = min(reduce_amount, trade.amount * 0.5)  # Max 50% della posizione

            if reduce_amount > 0:
                return f"sell_auto_reduce_{reduce_amount:.2f}"

        # Last DCA Profit Skimming (solo quando esposizione massima e NON over-exposed)
        if trade.nr_of_successful_entries >= max_orders and trade.orders:
            last_order = trade.orders[-1]
            last_order_price = last_order.price
            if last_order_price is None:
                last_order_price = trade.open_rate

            # Se prezzo attuale > prezzo ultimo DCA + soglia
            if current_rate > last_order_price * (1 + self.last_dca_profit_threshold.value):
                # Calcola solo il PROFITTO dell'ultimo DCA
                if hasattr(last_order, "cost") and last_order.cost:
                    last_dca_stake = last_order.cost
                else:
                    # Fallback: stima basata su parametri
                    last_dca_stake = total_balance * 0.3

                last_dca_quantity = last_dca_stake / last_order_price
                current_value = last_dca_quantity * current_rate
                profit_only = current_value - last_dca_stake

                if profit_only > 0:
                    return f"sell_last_dca_profit_{profit_only:.2f}"

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
            if current_candle["macd"] > self.macd_overbought_threshold.value:
                indicators.append("macd")
            if current_candle["williams_r"] > self.williams_overbought_threshold.value:
                indicators.append("wr")

            overbought_count = len(indicators)

            if (
                overbought_count >= self.min_overbought_count.value
                and current_candle["close"] > current_candle["open"]
            ):
                return f"sell_overbought_({'+'.join(indicators)})"

        return None
