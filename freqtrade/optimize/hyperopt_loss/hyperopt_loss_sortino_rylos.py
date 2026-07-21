"""
SortinoRyLoSHyperOptLoss

Sortino-based loss function with passivbot-style guardrails.

Design notes (from passivbot optimizer research on grid/DCA strategies):
- On DCA strategies that close almost only in profit, realized-PnL Sortino is
  degenerate: downside deviation tends to 0 and the ratio explodes, rewarding
  configs that simply never close losing positions. The ratio is therefore
  capped, and the real risk (unrealized drawdown, time stuck in a position) is
  penalized explicitly.
- Guardrails mirror the passivbot optimize limits used for HYPE:
  relative drawdown > 45% and positions held longer than 20 days are penalized
  progressively (soft limits, not hard rejections).
"""

import math
from datetime import datetime

from pandas import DataFrame, date_range

from freqtrade.data.metrics import calculate_max_drawdown
from freqtrade.optimize.hyperopt import IHyperOptLoss


# Cap for the annualized Sortino ratio: above this the metric no longer
# discriminates (degenerate all-wins regime).
SORTINO_CAP = 15.0
# Soft limits (passivbot-style guardrails)
MAX_RELATIVE_DRAWDOWN = 0.45
MAX_POSITION_HELD_DAYS = 20.0
# Penalty scaling: 10% drawdown excess costs 4 Sortino points;
# each day held beyond the limit costs 0.2 points.
DRAWDOWN_PENALTY_SCALE = 40.0
HELD_DAYS_PENALTY_SCALE = 0.2


class SortinoRyLoSHyperOptLoss(IHyperOptLoss):
    """
    Defines the loss function for hyperopt.

    Annualized daily Sortino ratio (capped) minus progressive penalties on
    max relative drawdown and worst position holding time.
    """

    @staticmethod
    def hyperopt_loss_function(
        *,
        results: DataFrame,
        trade_count: int,
        min_date: datetime,
        max_date: datetime,
        starting_balance: float,
        **kwargs,
    ) -> float:
        sortino = SortinoRyLoSHyperOptLoss._daily_sortino(results, min_date, max_date)

        # Guardrail 1: max relative drawdown on the realized equity curve
        try:
            drawdown = calculate_max_drawdown(
                results, starting_balance=starting_balance, relative=True
            )
            max_dd = drawdown.relative_account_drawdown
        except ValueError:
            max_dd = 0.0
        dd_penalty = max(0.0, max_dd - MAX_RELATIVE_DRAWDOWN) * DRAWDOWN_PENALTY_SCALE

        # Guardrail 2: worst position holding time (anti-bag)
        max_held_days = results["trade_duration"].max() / (60 * 24)
        held_penalty = max(0.0, max_held_days - MAX_POSITION_HELD_DAYS) * HELD_DAYS_PENALTY_SCALE

        return -(sortino - dd_penalty - held_penalty)

    @staticmethod
    def _daily_sortino(results: DataFrame, min_date: datetime, max_date: datetime) -> float:
        resample_freq = "1D"
        slippage_per_trade_ratio = 0.0005
        days_in_year = 365
        minimum_acceptable_return = 0.0

        results.loc[:, "profit_ratio_after_slippage"] = (
            results["profit_ratio"] - slippage_per_trade_ratio
        )

        t_index = date_range(start=min_date, end=max_date, freq=resample_freq, normalize=True)
        sum_daily = (
            results.resample(resample_freq, on="close_date")
            .agg({"profit_ratio_after_slippage": "sum"})
            .reindex(t_index)
            .fillna(0)
        )

        total_profit = sum_daily["profit_ratio_after_slippage"] - minimum_acceptable_return
        expected_returns_mean = total_profit.mean()

        downside = total_profit.copy()
        downside[downside > 0] = 0.0
        down_stdev = math.sqrt((downside**2).sum() / len(downside))

        if down_stdev == 0:
            # All-wins regime: reward positive growth but never beyond the cap,
            # so "never realize a loss" cannot dominate the score.
            return SORTINO_CAP if expected_returns_mean > 0 else -20.0

        sortino = expected_returns_mean / down_stdev * math.sqrt(days_in_year)
        return min(sortino, SORTINO_CAP)
