import talib.abstract as ta
from pandas import DataFrame, Timestamp
from datetime import datetime, timedelta, timezone

from freqtrade.strategy import (
    CategoricalParameter,
    DecimalParameter,
    IntParameter,
    IStrategy,
    Trade,
    timeframe_to_minutes,
)


class RyLoSStrategy(IStrategy):
    """
    RyLoS Classic — multi-oscillator oversold entry + DCA progressivo,
    con meccaniche passivbot (trailing_grid_v7, config dd39 HYPE/bybit_02):
    - Entry iniziale ancorata a EMA (initial_ema_dist)
    - DCA con conferma trailing (threshold + retracement sul rimbalzo dal minimo)
    - Distanza DCA adattiva a volatilità (ATR) ED esposizione (we_weight)
    - Trailing close threshold+retracement (sostituisce il trailing stop statico)
    - Unstuck: riduzione parziale della posizione stuck vicino a EMA,
      con budget di perdita per clip (anti-bag, position_held_days_max)
    """

    timeframe = "5m"
    can_short = False
    process_only_new_candles = True
    startup_candle_count = 100  # warmup per EMA(68) e BB(20)
    position_adjustment_enable = True
    # max_entry_position_adjustment rimosso - calcolato dinamicamente
    stoploss = -1  # Disabilitato, gestito da custom_exit + unstuck

    # ROI disabilitato - usa solo custom_exit
    minimal_roi = {
        "0": 0.5
    }

    # Parametri ottimizzabili
    # Total wallet exposure limit (passivbot risk.total_wallet_exposure_limit,
    # bounds dd39 [2.5, 3]): il rischio massimo è balance * TWE,
    # disaccoppiato dalla leva exchange (4x, che determina solo il margine)
    total_wallet_exposure_limit = DecimalParameter(
        2.0, 3.0, default=3.0, space="buy", optimize=True
    )
    first_order_pct = DecimalParameter(0.01, 0.10, default=0.05, space="buy", optimize=True)
    dca_distance = DecimalParameter(0.005, 0.035, default=0.022, space="buy", optimize=True)
    dca_multiplier = DecimalParameter(1.2, 3.0, default=1.991, space="buy", optimize=True)

    # DCA dinamico basato su volatilità ATR
    dca_atr_multiplier = DecimalParameter(0.5, 5.0, default=2.306, space="buy", optimize=True)

    # DCA dinamico basato su esposizione (passivbot grid_spacing_we_weight):
    # più la posizione è carica, più le distanze si allargano
    dca_we_weight = DecimalParameter(0.0, 6.0, default=4.987, space="buy", optimize=True)

    # Trailing entry per DCA (passivbot entry trailing_retracement_pct):
    # dopo la discesa serve un rimbalzo confermato dal minimo prima di comprare
    dca_trailing_retracement_pct = DecimalParameter(
        0.002, 0.02, default=0.0138, space="buy", optimize=True
    )

    # Ancoraggio EMA per il primo ordine (passivbot initial_ema_dist):
    # entra solo se il prezzo è sotto EMA * (1 + dist), dist negativa
    initial_ema_dist = DecimalParameter(-0.02, 0.0, default=-0.0078, space="buy", optimize=True)
    # Span EMA in candele 5m (~340 min, passivbot ema_span 320/360)
    ema_span_candles = IntParameter(40, 100, default=68, space="buy", optimize=False)

    # DCA cooldown dinamico (numero di candele da aspettare)
    dca_cooldown_candles = IntParameter(1, 5, default=2, space="buy", optimize=False)

    # Entry: oscillatore 4RSI di RyLoS (istogramma continuo hyperoptabile
    # al posto del conteggio discreto: avg(RSI2, RSI7, RSI14) - 50)
    osc_entry_threshold = DecimalParameter(-40, -10, default=-25, space="buy", optimize=True)
    entry_stoch_os = DecimalParameter(10, 40, default=20, space="buy", optimize=True)

    # Emergency DCA (prima della liquidazione)
    emergency_dca_threshold = DecimalParameter(
        -0.18, -0.10, default=-0.124, space="buy", optimize=True
    )
    emergency_critical_multiplier = DecimalParameter(
        1.05, 2.0, default=1.175, space="buy", optimize=True
    )

    # Exit: oscillatore 4RSI lato overbought (continuo)
    osc_exit_threshold = DecimalParameter(10, 40, default=25, space="sell", optimize=True)
    exit_stoch_ob = DecimalParameter(60, 90, default=80, space="sell", optimize=True)
    min_profit_for_overbought_exit = DecimalParameter(
        0.01, 0.10, default=0.017, space="sell", optimize=True
    )

    # Trailing close passivbot (close trailing_threshold/retracement, config dd39):
    # exit quando il massimo dall'ultimo fill supera avg_price*(1+threshold)
    # e il prezzo ritraccia di retracement dal massimo
    close_trailing_threshold_pct = DecimalParameter(
        0.005, 0.03, default=0.0145, space="sell", optimize=True
    )
    close_trailing_retracement_pct = DecimalParameter(
        0.001, 0.01, default=0.0016, space="sell", optimize=True
    )

    # Close grid passivbot (dd39: markup_start 0.617% / end 0.261%,
    # qty_pct 0.49): realizza profitto a clip parziali appena il prezzo
    # supera il markup dal prezzo medio — è il meccanismo che tiene corte
    # le durate (position_held_days_max ~7gg nel BT dd39)
    close_grid_enabled = CategoricalParameter(
        [True, False], default=True, space="sell", optimize=True
    )
    close_grid_markup_pct = DecimalParameter(
        0.002, 0.010, default=0.006, space="sell", optimize=True
    )
    close_grid_qty_pct = DecimalParameter(0.2, 0.6, default=0.49, space="sell", optimize=True)
    # Dopo questo numero di clip, il trigger successivo chiude tutto:
    # evita il "moncherino" che resta aperto per settimane
    CLOSE_GRID_MAX_CLIPS = 2

    # Unstuck passivbot: riduzione parziale della posizione stuck
    unstuck_threshold = DecimalParameter(0.3, 0.7, default=0.445, space="sell", optimize=True)
    unstuck_close_pct = DecimalParameter(0.03, 0.10, default=0.051, space="sell", optimize=True)
    unstuck_ema_dist = DecimalParameter(-0.15, 0.0, default=-0.1076, space="sell", optimize=True)
    unstuck_loss_allowance_pct = DecimalParameter(
        0.005, 0.02, default=0.0101, space="sell", optimize=True
    )
    # Anti-bag: oltre questi giorni la posizione è considerata stuck comunque
    unstuck_max_held_days = IntParameter(5, 20, default=15, space="sell", optimize=True)

    # Trailing stop statico disabilitato: sostituito dal trailing close passivbot
    trailing_stop = False

    # Opt-out dal deepcopy del Trade nel strategy_safe_wrapper (patch fork):
    # i callback di questa strategia leggono soltanto l'oggetto trade.
    # Il deepcopy pesava ~40% del tempo di backtest.
    disable_trade_deepcopy = True

    # Cooldown tra clip unstuck (12 candele 5m = 1h): limita il numero di
    # ordini per trade (ogni ordine rende più costoso ogni callback successivo)
    UNSTUCK_COOLDOWN_CANDLES = 12

    # Cache per-epoch (svuotate in populate_entry_trend)
    _extremes_cache: dict = {}
    _fill_cache: dict = {}
    _last_unstuck: dict = {}
    _max_orders_cache: int | None = None

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
        """Valore totale delle posizioni aperte su tutte le pairs (stake corrente x leva)"""
        return sum(t.stake_amount for t in Trade.get_open_trades()) * 4

    def _entry_fill_info(self, trade: Trade) -> tuple[int, datetime, float] | None:
        """
        (n_entry_fillati, data_ultimo_fill, prezzo_ultimo_fill) con cache:
        select_filled_orders scandisce tutti gli ordini, qui viene rifatto
        solo quando il numero di ordini del trade cambia.
        """
        n_orders = len(trade.orders)
        cached = self._fill_cache.get(trade.id)
        if cached is not None and cached[0] == n_orders:
            return cached[1]
        filled = trade.select_filled_orders(trade.entry_side)
        info = None
        if filled:
            last = filled[-1]
            info = (
                len(filled),
                last.order_filled_date.replace(tzinfo=timezone.utc),
                last.average,
            )
        self._fill_cache[trade.id] = (n_orders, info)
        return info

    def _window_extremes(
        self, pair: str, anchor_time: datetime, current_time
    ) -> tuple[float, float] | None:
        """
        (max high, min low) delle candele tra anchor_time (escluso) e
        current_time (incluso). Chiamata a ogni candela durante il backtest:
        usa una cache incrementale per candela (O(1) ammortizzato) — i valori
        dipendono solo dalle candele, non dai parametri, quindi la cache è
        sempre valida per lo stesso anchor.
        """
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        if dataframe.empty:
            return None
        dates = dataframe["date"]
        # Timestamp pandas: i datetime Python live (precisione us) fanno
        # esplodere searchsorted su datetime64[ns] ("Cannot losslessly convert")
        start_idx = int(dates.searchsorted(Timestamp(anchor_time), side="right"))
        end_idx = int(dates.searchsorted(Timestamp(current_time), side="right"))
        if start_idx >= end_idx:
            return None

        key = (pair, anchor_time)
        cached = self._extremes_cache.get(key)
        if cached is not None and start_idx < cached[0] <= end_idx:
            scan_from, high_max, low_min = cached
        else:
            scan_from, high_max, low_min = start_idx, float("-inf"), float("inf")

        if end_idx > scan_from:
            segment = dataframe.iloc[scan_from:end_idx]
            high_max = max(high_max, segment["high"].max())
            low_min = min(low_min, segment["low"].min())

        self._extremes_cache[key] = (end_idx, high_max, low_min)
        return high_max, low_min

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

        # Limite globale e per pair (TWE passivbot, non la leva)
        global_limit = total_balance * self.total_wallet_exposure_limit.value
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
        """Calcola dinamicamente il numero massimo di ordini basato sui parametri ottimizzati.

        Il conteggio dipende solo dai rapporti (first_order_pct, dca_multiplier),
        non dal balance assoluto: viene cacheato per epoch.
        """
        if self._max_orders_cache is not None:
            return self._max_orders_cache
        max_open_trades = self.config.get("max_open_trades", 1)
        per_pair_limit = (
            total_balance * self.total_wallet_exposure_limit.value
        ) / max_open_trades

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

        self._max_orders_cache = order_count - 1  # primo ordine non conta come adjustment
        return self._max_orders_cache

    def get_dynamic_dca_distance(
        self, pair: str, current_rate: float, exposure_ratio: float
    ) -> float:
        """
        Distanza DCA dinamica (passivbot grid_spacing con volatility/we weight):
        dca_distance * (1 + ATR% * atr_mult) * (1 + exposure_ratio * we_weight)
        """
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        base = self.dca_distance.value
        if len(dataframe) < 1:
            return base

        # ATR normalizzato in percentuale (.iat: niente Series intermedia)
        atr_pct = dataframe["atr"].iat[-1] / current_rate

        distance = base * (1 + atr_pct * self.dca_atr_multiplier.value)
        # Scaling con l'esposizione: più la posizione è carica, più distanza serve
        distance *= 1 + max(0.0, exposure_ratio) * self.dca_we_weight.value

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
        # Non agire se ci sono ordini aperti
        if trade.has_open_orders:
            return None

        fill_info = self._entry_fill_info(trade)
        if fill_info is None:
            return None
        n_entries, last_fill_time, last_order_price = fill_info

        # Cooldown dinamico: aspetta N candele dall'ultimo ordine
        cooldown_minutes = timeframe_to_minutes(self.timeframe) * self.dca_cooldown_candles.value
        if (current_time - timedelta(minutes=cooldown_minutes)) < last_fill_time:
            return None

        max_open_trades = self.config.get("max_open_trades", 1)
        total_balance = None  # calcolato solo quando serve (wallets è costoso)

        # ===== CLOSE GRID (passivbot): take-profit a clip parziali =====
        # Prezzo sopra avg_entry * (1 + markup) -> vendi una clip; il resto
        # lo gestiscono trailing close / oscillatori / clip successive
        if self.close_grid_enabled.value and current_profit > 0:
            price_markup = (current_rate - trade.open_rate) / trade.open_rate
            if price_markup >= self.close_grid_markup_pct.value:
                n_exits = trade.nr_of_successful_exits
                reduce_stake = trade.stake_amount * self.close_grid_qty_pct.value
                remaining = trade.stake_amount - reduce_stake
                if n_exits >= self.CLOSE_GRID_MAX_CLIPS or (
                    min_stake and remaining < min_stake * 2
                ):
                    # basta clip: chiudi tutta la posizione residua
                    reduce_stake = trade.stake_amount
                return (
                    -reduce_stake,
                    f"tp_grid_{price_markup * 100:.2f}%",
                )

        # ===== UNSTUCK (passivbot): riduzione parziale della posizione stuck =====
        if current_profit < 0:
            held_days = (current_time - trade.open_date_utc).total_seconds() / 86400
            is_stuck = held_days >= self.unstuck_max_held_days.value
            if not is_stuck:
                total_balance = self.wallets.get_total_stake_amount()
                per_pair_limit = (
                    total_balance * self.total_wallet_exposure_limit.value
                ) / max_open_trades
                exposure_ratio = (
                    trade.stake_amount * 4 / per_pair_limit if per_pair_limit > 0 else 0.0
                )
                is_stuck = exposure_ratio >= self.unstuck_threshold.value
            if is_stuck:
                # Cooldown dedicato tra clip (limita anche il numero di ordini)
                last_unstuck = self._last_unstuck.get(trade.id)
                unstuck_wait = timedelta(
                    minutes=timeframe_to_minutes(self.timeframe) * self.UNSTUCK_COOLDOWN_CANDLES
                )
                if last_unstuck is None or (current_time - last_unstuck) >= unstuck_wait:
                    dataframe, _ = self.dp.get_analyzed_dataframe(trade.pair, self.timeframe)
                    if len(dataframe) > 0:
                        ema = dataframe["ema_anchor"].iat[-1]
                        # Vendi nella forza: solo se il prezzo è risalito vicino/sopra
                        # EMA * (1 + ema_dist) (ema_dist negativa = accetta sotto EMA)
                        if ema and current_rate >= ema * (1 + self.unstuck_ema_dist.value):
                            if total_balance is None:
                                total_balance = self.wallets.get_total_stake_amount()
                            reduce_stake = trade.stake_amount * self.unstuck_close_pct.value
                            # Budget di perdita per clip: non realizzare più di
                            # loss_allowance_pct del balance in una singola riduzione
                            estimated_loss = reduce_stake * abs(current_profit)
                            if (
                                estimated_loss
                                <= total_balance * self.unstuck_loss_allowance_pct.value
                            ):
                                self._last_unstuck[trade.id] = current_time
                                return (
                                    -reduce_stake,
                                    f"unstuck_{held_days:.1f}d_{current_profit * 100:.1f}%",
                                )

        # Calcola perdita dall'ultimo DCA filled (non dalla media)
        current_loss_from_last = (current_rate - last_order_price) / last_order_price

        if current_loss_from_last > self.emergency_dca_threshold.value and (
            current_rate >= last_order_price
            or (last_order_price - current_rate) / last_order_price < self.dca_distance.value
        ):
            # Fast path: nessun DCA possibile (né emergency né normale) —
            # la distanza dinamica è sempre >= dca_distance base
            return None

        if total_balance is None:
            total_balance = self.wallets.get_total_stake_amount()
        max_orders = self.calculate_max_orders(total_balance)
        global_limit = total_balance * self.total_wallet_exposure_limit.value
        per_pair_limit = global_limit / max_open_trades
        current_global_exposure = self.get_total_position_value()
        exposure_ratio = trade.stake_amount * 4 / per_pair_limit if per_pair_limit > 0 else 0.0
        filled_entries = trade.select_filled_orders(trade.entry_side)

        if (
            current_loss_from_last <= self.emergency_dca_threshold.value
            and n_entries < max_orders
        ):  # Rispetta max_orders
            # Soglia critica = emergency_threshold * multiplier
            critical_threshold = (
                self.emergency_dca_threshold.value * self.emergency_critical_multiplier.value
            )

            if current_loss_from_last <= critical_threshold and current_rate < last_order_price:
                # Emergency DCA: SALTA controllo BB threshold
                # Calcola stake come un DCA normale
                next_dca_order = n_entries + 1
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
        if n_entries > max_orders:
            return None

        # Verifica se abbiamo raggiunto il limite globale
        if current_global_exposure >= global_limit * 0.95:  # 95% del limite per sicurezza
            return None

        # Wallet disponibile e posizione corrente
        available_balance = self.wallets.get_available_stake_amount()
        current_position_value = trade.stake_amount * 4

        # Calcola il prossimo stake
        entry_count = n_entries
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

        # ===== DCA con trailing entry (passivbot threshold + retracement) =====
        # DCA solo in discesa rispetto all'ultimo fill
        if current_rate >= last_order_price:
            return None

        # Minimo raggiunto dall'ultimo fill
        extremes = self._window_extremes(trade.pair, last_fill_time, current_time)
        lowest_since_last = current_rate
        if extremes is not None:
            lowest_since_last = min(extremes[1], current_rate)

        # Threshold: la discesa dal fill al minimo deve superare la distanza dinamica
        drop_from_last = (last_order_price - lowest_since_last) / last_order_price
        dynamic_distance = self.get_dynamic_dca_distance(
            trade.pair, current_rate, exposure_ratio
        )
        if drop_from_last < dynamic_distance:
            return None

        # Retracement: serve un rimbalzo confermato dal minimo (compra sul rimbalzo,
        # non al volo in discesa)
        bounce_from_low = (
            (current_rate - lowest_since_last) / lowest_since_last if lowest_since_last > 0 else 0
        )
        if bounce_from_low < self.dca_trailing_retracement_pct.value:
            return None

        return next_stake, f"dca_{entry_count + 1}_{current_profit * 100:.1f}%"

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # Oscillatore 4RSI di RyLoS: avg(RSI2, RSI7, RSI14) - 50
        rsi_fast = ta.RSI(dataframe["close"], timeperiod=2)
        rsi_mid = ta.RSI(dataframe["close"], timeperiod=7)
        rsi_slow = ta.RSI(dataframe["close"], timeperiod=14)
        dataframe["osc_4rsi"] = (rsi_fast + rsi_mid + rsi_slow) / 3 - 50

        # Filtro stocastico del 4RSI: %K = SMA(stoch(14), 3) (= fastd di STOCHF)
        stoch_fastk, stoch_fastd = ta.STOCHF(
            dataframe["high"], dataframe["low"], dataframe["close"],
            fastk_period=14, fastd_period=3, fastd_matype=0,
        )
        dataframe["stoch_k"] = stoch_fastd

        # ATR periodo 10 per volatilità più reattiva
        dataframe["atr"] = ta.ATR(
            dataframe["high"], dataframe["low"], dataframe["close"], timeperiod=10
        )

        # EMA di ancoraggio (passivbot ema_span): entry iniziale e unstuck
        dataframe["ema_anchor"] = ta.EMA(
            dataframe["close"], timeperiod=self.ema_span_candles.value
        )

        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # Nuovo epoch/backtest: svuota la cache degli estremi (solo memoria,
        # i valori restano comunque validi tra epoch)
        self._extremes_cache.clear()

        # 4RSI oversold: istogramma sotto soglia + filtro stocastico
        osc_condition = (dataframe["osc_4rsi"] < self.osc_entry_threshold.value).fillna(False)
        stoch_condition = (dataframe["stoch_k"] < self.entry_stoch_os.value).fillna(False)

        # Ancoraggio EMA (passivbot initial_ema_dist): entra solo sotto la banda
        ema_condition = (
            dataframe["close"] <= dataframe["ema_anchor"] * (1 + self.initial_ema_dist.value)
        ).fillna(False)

        entry_condition = (
            osc_condition
            & stoch_condition
            & (dataframe["close"] < dataframe["open"])
            & ema_condition
        )

        dataframe["enter_tag"] = ""
        for idx in dataframe.index[entry_condition]:
            dataframe.loc[idx, "enter_tag"] = f"buy_4rsi_{dataframe.at[idx, 'osc_4rsi']:.0f}"

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
        # ===== Trailing close passivbot (threshold + retracement) =====
        # max_since_open = massimo dall'ultimo cambio di posizione (ultimo fill);
        # exit se ha superato avg_price*(1+threshold) e il prezzo ritraccia
        # di retracement_pct dal massimo. Chiude solo in profitto.
        if current_profit > 0:
            filled_entries = trade.select_filled_orders(trade.entry_side)
            if filled_entries:
                last_fill_time = filled_entries[-1].order_filled_date.replace(
                    tzinfo=timezone.utc
                )
                extremes = self._window_extremes(pair, last_fill_time, current_time)
                if extremes is not None:
                    max_since_open = max(extremes[0], current_rate)
                    threshold_price = trade.open_rate * (
                        1 + self.close_trailing_threshold_pct.value
                    )
                    retracement_price = max_since_open * (
                        1 - self.close_trailing_retracement_pct.value
                    )
                    if max_since_open >= threshold_price and current_rate <= retracement_price:
                        return f"sell_trailing_close_{current_profit * 100:.1f}%"

        # ===== 4RSI Overbought Exit (istogramma continuo) =====
        if current_profit > self.min_profit_for_overbought_exit.value:
            dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
            if len(dataframe) > 0:
                osc = dataframe["osc_4rsi"].iat[-1]
                stoch_k = dataframe["stoch_k"].iat[-1]
                candle_green = dataframe["close"].iat[-1] > dataframe["open"].iat[-1]
                if (
                    osc > self.osc_exit_threshold.value
                    and stoch_k > self.exit_stoch_ob.value
                    and candle_green
                ):
                    return f"sell_4rsi_{osc:.0f}_{current_profit * 100:.1f}%"

        return None
