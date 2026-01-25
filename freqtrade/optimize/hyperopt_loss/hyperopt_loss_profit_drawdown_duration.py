"""
ProfitDrawdownDurationHyperOptLoss

Loss function che massimizza profit con penalità drawdown (>30%) e duration (>5h)
"""

import math
from datetime import datetime

from pandas import DataFrame

from freqtrade.data.metrics import calculate_max_drawdown
from freqtrade.optimize.hyperopt import IHyperOptLoss


class ProfitDrawdownDurationHyperOptLoss(IHyperOptLoss):
    """
    Defines the loss function for hyperopt.

    Massimizza profit totale con:
    - Penalità drawdown solo se supera 30%
    - Penalità duration logaritmica per trade >5h
    """

    @staticmethod
    def hyperopt_loss_function(
        results: DataFrame,
        min_date: datetime,
        max_date: datetime,
        starting_balance: float,
        *args,
        **kwargs,
    ) -> float:
        """
        Objective function, returns smaller number for more optimal results.

        Massimizza profit con penalità drawdown (>30%) e duration (>5h)
        """
        total_profit = results["profit_abs"].sum()
        trade_duration = results["trade_duration"].mean()
        
        # Calcola max drawdown
        try:
            drawdown = calculate_max_drawdown(
                results, starting_balance=starting_balance, value_col="profit_abs"
            )
            max_drawdown_pct = drawdown.relative_account_drawdown
        except (ValueError, TypeError):
            max_drawdown_pct = 0

        # ============================================================================
        # DRAWDOWN PENALTY (progressiva sopra 30%)
        # ============================================================================
        if max_drawdown_pct > 0.40:
            # Penalità aggressiva oltre 40%
            base_penalty = 0.10 * total_profit * 2  # 30-40%: penalty fissa
            excess_over_40 = max_drawdown_pct - 0.40
            extra_penalty = excess_over_40 * total_profit * 4  # 4x oltre 40%
            drawdown_penalty = base_penalty + extra_penalty
        elif max_drawdown_pct > 0.30:
            # Penalità moderata tra 30-40%
            drawdown_excess = max_drawdown_pct - 0.30
            drawdown_penalty = drawdown_excess * total_profit * 2
        else:
            drawdown_penalty = 0

        # ============================================================================
        # DURATION PENALTY (logaritmica sopra 5h)
        # ============================================================================
        duration_penalty = ProfitDrawdownDurationHyperOptLoss._calculate_duration_penalty(
            trade_duration, total_profit
        )

        # Risultato: massimizza profit, penalizza drawdown >30% e duration >5h
        result = -total_profit + drawdown_penalty + duration_penalty

        return result

    @staticmethod
    def _calculate_duration_penalty(trade_duration_minutes: float, total_profit: float) -> float:
        """
        Calculate logarithmic duration penalty starting from 5 hours.
        
        Penalty is a percentage of profit to maintain proper scaling:
        - 5h → 0% penalty
        - 10h → ~18% penalty
        - 24h → ~30% penalty
        
        :param trade_duration_minutes: Average trade duration in minutes
        :param total_profit: Total profit to scale penalty
        :return: Duration penalty (absolute value)
        """
        if trade_duration_minutes <= 300:  # <= 5 hours
            return 0

        # Ore oltre le 5
        hours_over_threshold = (trade_duration_minutes - 300) / 60
        
        # Penalty logaritmico come percentuale del profit
        # Formula: log(1 + hours) / 10 → percentuale
        # Es: 10h → log(6)/10 = 0.179 = 17.9% del profit
        #     24h → log(20)/10 = 0.300 = 30% del profit
        penalty_percentage = math.log(1 + hours_over_threshold) / 10
        penalty = penalty_percentage * abs(total_profit)
        
        return penalty
