"""RyLoSGridStrategy: la griglia passivbot dentro freqtrade, con ordini appoggiati.

Nata il 2026-09-02 da una constatazione misurata insieme alla sessione
passivbot: il gap fra i due bot (470x contro 32x sulla stessa finestra) non
sta nella strategia ma nell'esecuzione dei gradini. RyLoSStrategy compra il
gradino DCA alla chiusura della candela 5m, dopo un rimbalzo dello 0,3% dal
minimo e con 10 minuti di cooldown: la media si forma sempre piu' in alto del
livello. Passivbot con quei tre vincoli viene liquidato nel crash di marzo
2025. Qui i gradini sono ordini LIMITE appoggiati al livello e riempiti
intra-candela; con `--timeframe-detail 1m` il backtest li valuta ogni minuto.

Vincolo del motore: un solo ordine aperto per trade. Si alterna: resta
appoggiato l'ordine piu' vicino al prezzo, il gradino sotto o il take-profit
sopra, e `adjust_order_price` cambia lato quando il prezzo si sposta.

Niente stop loss: il rischio e' tutto non realizzato e lo contiene la
geometria (primo gradino piccolo, tetto di esposizione duro). Come passivbot.
"""

import os
from datetime import datetime

import numpy as np
import talib.abstract as ta
from pandas import DataFrame

from freqtrade.persistence import Order, Trade
from freqtrade.strategy import (
    CategoricalParameter,
    DecimalParameter,
    IntParameter,
    IStrategy,
    stoploss_from_absolute,
)


class RyLoSGridStrategy(IStrategy):
    INTERFACE_VERSION = 3

    timeframe = "5m"
    can_short = False
    process_only_new_candles = True
    startup_candle_count = 300

    # Nessuno stop: la liquidazione e' l'unico limite, come in passivbot.
    stoploss = -0.99
    use_custom_stoploss = True
    position_adjustment_enable = True
    max_entry_position_adjustment = -1

    minimal_roi = {"0": 100}
    use_exit_signal = True  # obbligatorio: senza, custom_exit non viene mai valutata
    exit_profit_only = False
    ignore_roi_if_entry_signal = False

    # Gli ordini appoggiati devono sopravvivere alla config: unfilledtimeout
    # va alzato nel json di run (qui non si puo' sovrascrivere).
    order_types = {
        "entry": "limit",
        "exit": "limit",
        "stoploss": "market",
        "stoploss_on_exchange": False,
    }
    order_time_in_force = {"entry": "GTC", "exit": "GTC"}

    CLOSE_GRID_MAX_CLIPS = 8

    # Leva e stop vanno scelti insieme: a margine isolato la liquidazione e'
    # a -1/leva dal prezzo medio (-25% a 4x, -33% a 3x). Lo stop e' in
    # frazione di PREZZO dal medio; sopra 1/leva e' di fatto spento.
    grid_leverage = IntParameter(3, 5, default=4, space="buy", optimize=False)
    stop_from_avg_pct = DecimalParameter(0.08, 0.30, default=0.22, space="sell", optimize=False)

    # ===== Ingresso: 4RSI + stocastico + banda EMA (default = passivbot live) =====
    osc_entry_threshold = DecimalParameter(-30, -8, default=-23.9, space="buy", optimize=True)
    entry_stoch_os = DecimalParameter(5, 44, default=12.7, space="buy", optimize=True)
    initial_ema_dist = DecimalParameter(-0.02, -0.004, default=-0.012, space="buy", optimize=True)
    ema_span_candles = IntParameter(40, 100, default=68, space="buy", optimize=False)
    # Crash guard di RyLoS: a 100 e' spento (passivbot non ce l'ha).
    crash_guard_pct = DecimalParameter(4.0, 100.0, default=100.0, space="buy", optimize=False)

    # ===== Geometria della griglia =====
    # Tetto di esposizione: notional massimo della posizione / saldo.
    total_wallet_exposure_limit = DecimalParameter(1.0, 3.0, default=2.93, space="buy", optimize=True)
    # Primo gradino, in frazione del saldo come STAKE (margine): notional = stake * leva.
    first_order_pct = DecimalParameter(0.002, 0.09, default=0.006, space="buy", optimize=True)
    # Ogni gradino aggiunge questa frazione della posizione corrente (passivbot
    # grid_double_down_factor): 0.32 = la posizione cresce di 1.32x a gradino.
    dca_ddf = DecimalParameter(0.15, 2.0, default=0.32, space="buy", optimize=True)
    # Spaziatura base fra i gradini, allargata da volatilita' ed esposizione.
    dca_distance = DecimalParameter(0.002, 0.045, default=0.006, space="buy", optimize=True)
    dca_atr_multiplier = DecimalParameter(0.0, 20.0, default=13.6, space="buy", optimize=True)
    dca_we_weight = DecimalParameter(0.0, 10.0, default=6.5, space="buy", optimize=True)
    # Da dove si misura il gradino: dall'ultimo fill (RyLoS) o dal prezzo
    # medio della posizione (passivbot). Geometrie diverse, decide la ricerca.
    dca_anchor = CategoricalParameter(["last_fill", "avg"], default="last_fill", space="buy", optimize=True)
    # Coda trailing: sopra questa esposizione la griglia si ferma e l'ultimo
    # pezzo entra in un colpo solo, dopo una discesa dal medio E un rimbalzo
    # confermato dal minimo. E' il trailing entry di RyLoS, ma solo dove
    # compra il fondo in grande: su tutti i gradini era fatale.
    tail_start = DecimalParameter(0.3, 1.0, default=0.7, space="buy", optimize=True)
    tail_drop_pct = DecimalParameter(0.02, 0.15, default=0.06, space="buy", optimize=True)
    tail_bounce_pct = DecimalParameter(0.005, 0.06, default=0.02, space="buy", optimize=True)
    tail_qty_mult = DecimalParameter(0.3, 2.0, default=1.0, space="buy", optimize=True)

    # ===== Uscite =====
    # Il 4RSI decide. Il limite di vendita appoggiato esiste solo sopra questa
    # esposizione: scarica le posizioni pesanti, non chiude quelle leggere.
    tp_exposure_start = DecimalParameter(0.1, 1.0, default=0.3, space="sell", optimize=True)
    # Markup del limite appoggiato: da start (a tp_exposure_start) a end (a
    # esposizione piena), lineare.
    close_grid_markup_start = DecimalParameter(-0.005, 0.03, default=0.003, space="sell", optimize=True)
    close_grid_markup_end = DecimalParameter(-0.04, 0.01, default=-0.0186, space="sell", optimize=True)
    # Frazione della posizione PIENA venduta a ogni clip.
    close_grid_qty_pct = DecimalParameter(0.1, 1.0, default=0.292, space="sell", optimize=True)
    # Exit 4RSI (passivbot close_panic_long): chiude tutto sul segnale, sopra
    # un profitto minimo con leva (0.65% di prezzo * 4 = 0.026).
    osc_exit_threshold = DecimalParameter(10, 32, default=18.049, space="sell", optimize=True)
    exit_stoch_ob = DecimalParameter(55, 92, default=78.3, space="sell", optimize=True)
    min_profit_for_overbought_exit = DecimalParameter(0.004, 0.08, default=0.026, space="sell", optimize=True)

    def __init__(self, config: dict) -> None:
        super().__init__(config)
        # Livello del gradino in attesa di essere piazzato, per pair: lo
        # calcola adjust_trade_position e lo legge custom_entry_price.
        self._pending_level: dict[str, float] = {}
        self._dbg = open(os.environ["GRID_DEBUG"], "a") if os.environ.get("GRID_DEBUG") else None

    def _log(self, *parts) -> None:
        if self._dbg is not None:
            self._dbg.write(" ".join(str(p) for p in parts) + "\n")

    # ------------------------------------------------------------------ #
    # Indicatori e segnali
    # ------------------------------------------------------------------ #
    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["ret6_pct"] = dataframe["close"].pct_change(6) * 100

        rsi_fast = ta.RSI(dataframe["close"], timeperiod=2)
        rsi_mid = ta.RSI(dataframe["close"], timeperiod=7)
        rsi_slow = ta.RSI(dataframe["close"], timeperiod=14)
        dataframe["osc_4rsi"] = (rsi_fast + rsi_mid + rsi_slow) / 3 - 50

        _, stoch_fastd = ta.STOCHF(
            dataframe["high"], dataframe["low"], dataframe["close"],
            fastk_period=14, fastd_period=3, fastd_matype=0,
        )
        dataframe["stoch_k"] = stoch_fastd

        dataframe["atr"] = ta.ATR(
            dataframe["high"], dataframe["low"], dataframe["close"], timeperiod=10
        )
        dataframe["ema_anchor"] = ta.EMA(
            dataframe["close"], timeperiod=self.ema_span_candles.value
        )
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        band = dataframe["ema_anchor"] * (1 + self.initial_ema_dist.value)
        dataframe.loc[
            (dataframe["osc_4rsi"] < self.osc_entry_threshold.value)
            & (dataframe["stoch_k"] < self.entry_stoch_os.value)
            & (dataframe["close"] < dataframe["open"])
            & (dataframe["close"] <= band)
            & (dataframe["ret6_pct"] > -self.crash_guard_pct.value)
            & (dataframe["volume"] > 0),
            ["enter_long", "enter_tag"],
        ] = (1, "grid_entry")
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        return dataframe

    def leverage(self, pair: str, current_time: datetime, current_rate: float,
                 proposed_leverage: float, max_leverage: float, entry_tag: str | None,
                 side: str, **kwargs) -> float:
        return float(self.grid_leverage.value)

    def custom_stake_amount(self, pair: str, current_time: datetime, current_rate: float,
                            proposed_stake: float, min_stake: float | None, max_stake: float,
                            leverage: float, entry_tag: str | None, side: str, **kwargs) -> float:
        stake = self.wallets.get_total_stake_amount() * self.first_order_pct.value
        if min_stake and stake < min_stake:
            stake = min_stake
        return min(stake, max_stake)

    # ------------------------------------------------------------------ #
    # Geometria
    # ------------------------------------------------------------------ #
    def _per_pair_notional_limit(self) -> float:
        max_open_trades = self.config.get("max_open_trades", 1)
        return (
            self.wallets.get_total_stake_amount() * self.total_wallet_exposure_limit.value
        ) / max_open_trades

    def _exposure_ratio(self, trade: Trade) -> float:
        limit = self._per_pair_notional_limit()
        return trade.stake_amount * trade.leverage / limit if limit > 0 else 0.0

    def _grid_distance(self, pair: str, price: float, exposure_ratio: float) -> float:
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        atr_pct = 0.0
        if len(dataframe) > 0:
            atr = dataframe["atr"].iat[-1]
            if atr is not None and not np.isnan(atr) and price > 0:
                atr_pct = atr / price
        return (
            self.dca_distance.value
            * (1 + atr_pct * self.dca_atr_multiplier.value)
            * (1 + exposure_ratio * self.dca_we_weight.value)
        )

    def _last_fill_price(self, trade: Trade) -> float | None:
        filled = trade.select_filled_orders(trade.entry_side)
        if not filled:
            return None
        return filled[-1].safe_price

    def _next_grid_level(self, trade: Trade) -> float | None:
        last = self._last_fill_price(trade)
        if last is None:
            return None
        anchor = trade.open_rate if self.dca_anchor.value == "avg" else last
        level = anchor * (1 - self._grid_distance(trade.pair, anchor, self._exposure_ratio(trade)))
        # Mai sopra l'ultimo fill: un gradino e' sempre una discesa.
        return min(level, last * (1 - self.dca_distance.value))

    def _next_grid_stake(self, trade: Trade, min_stake: float | None) -> float | None:
        limit = self._per_pair_notional_limit()
        remaining_notional = limit - trade.stake_amount * trade.leverage
        if remaining_notional <= 0:
            return None
        first_stake = self.wallets.get_total_stake_amount() * self.first_order_pct.value
        stake = min(
            max(trade.stake_amount * self.dca_ddf.value, first_stake),
            remaining_notional / trade.leverage,
        )
        if min_stake and stake < min_stake:
            # Il resto e' troppo piccolo per un ordine: la griglia e' piena.
            if remaining_notional / trade.leverage >= min_stake:
                stake = min_stake
            else:
                return None
        return stake

    def _tp_active(self, trade: Trade) -> bool:
        return self._exposure_ratio(trade) >= self.tp_exposure_start.value

    def _in_tail(self, trade: Trade) -> bool:
        return self._exposure_ratio(trade) >= self.tail_start.value

    def _tail_trigger(self, trade: Trade, current_rate: float) -> bool:
        """Discesa dal medio oltre tail_drop e rimbalzo dal minimo oltre tail_bounce."""
        filled = trade.select_filled_orders(trade.entry_side)
        if not filled:
            return False
        last_fill_time = filled[-1].order_filled_utc
        dataframe, _ = self.dp.get_analyzed_dataframe(trade.pair, self.timeframe)
        if len(dataframe) == 0 or last_fill_time is None:
            return False
        after = dataframe[dataframe["date"] > last_fill_time]
        if len(after) == 0:
            return False
        lows = after["low"].to_numpy()
        i_min = int(np.argmin(lows))
        low_min = min(float(lows[i_min]), current_rate)
        high_after = float(after["high"].to_numpy()[i_min:].max())
        max_since_min = max(high_after, current_rate)
        if low_min > trade.open_rate * (1 - self.tail_drop_pct.value):
            return False
        return max_since_min >= low_min * (1 + self.tail_bounce_pct.value)

    def _tail_stake(self, trade: Trade, min_stake: float | None) -> float | None:
        limit = self._per_pair_notional_limit()
        remaining_notional = limit - trade.stake_amount * trade.leverage
        if remaining_notional <= 0:
            return None
        stake = min(trade.stake_amount * self.tail_qty_mult.value, remaining_notional / trade.leverage)
        if min_stake and stake < min_stake:
            return None
        return stake

    def _tp_markup(self, trade: Trade) -> float:
        lo = self.tp_exposure_start.value
        span = max(1e-9, 1.0 - lo)
        t = min(1.0, max(0.0, (self._exposure_ratio(trade) - lo) / span))
        start, end = self.close_grid_markup_start.value, self.close_grid_markup_end.value
        return start + (end - start) * t

    def _tp_price(self, trade: Trade) -> float:
        return trade.open_rate * (1 + self._tp_markup(trade))

    def _tp_stake(self, trade: Trade, min_stake: float | None) -> float:
        """Stake da vendere al clip: frazione della posizione PIENA, piu' l'eccedenza."""
        full_stake = self._per_pair_notional_limit() / trade.leverage
        leftover = max(0.0, trade.stake_amount - full_stake)
        reduce_stake = min(
            trade.stake_amount, full_stake * self.close_grid_qty_pct.value + leftover
        )
        remaining = trade.stake_amount - reduce_stake
        if (
            trade.nr_of_successful_exits >= self.CLOSE_GRID_MAX_CLIPS
            or (min_stake and remaining < min_stake * 2)
        ):
            reduce_stake = trade.stake_amount
        return reduce_stake

    def _side_wanted(self, trade: Trade, current_rate: float) -> str:
        """Quale ordine tenere appoggiato: quello piu' vicino al prezzo."""
        if self._in_tail(trade):
            if self._tail_trigger(trade, current_rate) and self._tail_stake(trade, None) is not None:
                return "tail"
            return "tp" if self._tp_active(trade) else "none"
        level = self._next_grid_level(trade)
        if not self._tp_active(trade):
            return "dca"
        tp = self._tp_price(trade)
        if level is None:
            return "tp"
        if current_rate >= tp:
            return "tp"
        if current_rate <= level:
            return "dca"
        return "tp" if (tp - current_rate) <= (current_rate - level) else "dca"

    # ------------------------------------------------------------------ #
    # Ordini appoggiati
    # ------------------------------------------------------------------ #
    def adjust_trade_position(self, trade: Trade, current_time: datetime, current_rate: float,
                              current_profit: float, min_stake: float | None, max_stake: float,
                              current_entry_rate: float, current_exit_rate: float,
                              current_entry_profit: float, current_exit_profit: float,
                              **kwargs) -> float | None | tuple[float | None, str]:
        if trade.has_open_orders:
            self._log(current_time, "adjust: ordine aperto")
            return None
        side = self._side_wanted(trade, current_rate)
        if side == "tp":
            reduce_stake = self._tp_stake(trade, min_stake)
            self._log(current_time, "adjust: tp", round(reduce_stake, 2), round(self._tp_price(trade), 3))
            return -reduce_stake, f"tp_grid_{self._tp_markup(trade) * 100:.2f}%"
        if side == "none":
            return None
        if side == "tail":
            stake = self._tail_stake(trade, min_stake)
            if stake is None:
                return None
            self._pending_level[trade.pair] = current_rate
            self._log(current_time, "adjust: tail", "rate", current_rate, "stake", round(stake, 2),
                      "expo", round(self._exposure_ratio(trade), 3))
            return min(stake, max_stake), f"tail_{trade.nr_of_successful_entries + 1}"
        stake = self._next_grid_stake(trade, min_stake)
        level = self._next_grid_level(trade)
        self._log(current_time, "adjust: dca", "rate", current_rate, "level", level, "stake", stake,
                  "max_stake", round(max_stake, 2), "min_stake", min_stake,
                  "expo", round(self._exposure_ratio(trade), 3), "n", trade.nr_of_successful_entries)
        if stake is None or level is None:
            return None
        self._pending_level[trade.pair] = min(level, current_rate)
        return min(stake, max_stake), f"dca_{trade.nr_of_successful_entries + 1}"

    def custom_entry_price(self, pair: str, trade: Trade | None, current_time: datetime,
                           proposed_rate: float, entry_tag: str | None, side: str,
                           **kwargs) -> float:
        if trade is None:
            return proposed_rate
        self._log(current_time, "entry_price:", self._pending_level.get(pair), "proposed", proposed_rate)
        return self._pending_level.get(pair, proposed_rate)

    def custom_exit_price(self, pair: str, trade: Trade, current_time: datetime,
                          proposed_rate: float, current_profit: float, exit_tag: str | None,
                          **kwargs) -> float:
        if exit_tag and exit_tag.startswith("tp_grid"):
            return self._tp_price(trade)
        return proposed_rate

    def adjust_order_price(self, trade: Trade, order: Order | None, pair: str,
                           current_time: datetime, proposed_rate: float,
                           current_order_rate: float, entry_tag: str | None, side: str,
                           is_entry: bool, **kwargs) -> float | None:
        """Ogni candela: l'ordine appoggiato resta solo se e' ancora quello giusto."""
        if order is None:
            return current_order_rate
        wanted = self._side_wanted(trade, proposed_rate)
        self._log(current_time, "adjust_order:", "entry" if is_entry else "exit", "wanted", wanted,
                  "cur", current_order_rate, "proposed", proposed_rate, "n", trade.nr_of_successful_entries)
        if is_entry:
            if trade.nr_of_successful_entries == 0:
                # Primo ingresso: se non si e' riempito subito, lascialo cadere.
                return None
            if (order.ft_order_tag or "").startswith("tail"):
                return None if wanted != "tail" else current_order_rate
            if wanted != "dca":
                return None
            level = self._next_grid_level(trade)
            if level is None:
                return None
            level = min(level, proposed_rate)
            if abs(level / current_order_rate - 1) > 0.0005:
                self._pending_level[pair] = level
                return level
            return current_order_rate
        # ordine di vendita appoggiato
        if not (order.ft_order_tag or "").startswith("tp_grid"):
            return current_order_rate
        if wanted != "tp":
            return None
        return current_order_rate

    def check_entry_timeout(self, pair: str, trade: Trade, order: Order,
                            current_time: datetime, **kwargs) -> bool:
        return False

    def check_exit_timeout(self, pair: str, trade: Trade, order: Order,
                           current_time: datetime, **kwargs) -> bool:
        return False

    def custom_stoploss(self, pair: str, trade: Trade, current_time: datetime,
                        current_rate: float, current_profit: float, after_fill: bool,
                        **kwargs) -> float | None:
        stop_rate = trade.open_rate * (1 - self.stop_from_avg_pct.value)
        return stoploss_from_absolute(stop_rate, current_rate, is_short=trade.is_short,
                                      leverage=trade.leverage)

    # ------------------------------------------------------------------ #
    # Exit 4RSI: tutto, al segnale, sopra il profitto minimo
    # ------------------------------------------------------------------ #
    def custom_exit(self, pair: str, trade: Trade, current_time: datetime, current_rate: float,
                    current_profit: float, **kwargs) -> str | None:
        if current_profit <= self.min_profit_for_overbought_exit.value:
            return None
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        if len(dataframe) == 0:
            return None
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
