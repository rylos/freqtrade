"""
ProfitDrawdownDurationHyperOptLoss

Loss function che massimizza profit con:
- Penalità drawdown esponenziale continua (>20%) con formula (excess^1.5) * 6
- Penalità duration logaritmica (>5h)
- Reward sul numero di trade (incentiva configurazioni con più trade)
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
    - Penalità drawdown esponenziale continua sopra 20%: (excess^1.5) * 6
    - Penalità duration logaritmica per trade >5h
    - Reward sul numero di trade (incentiva configurazioni con più trade)
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

        Massimizza profit con:
        - Penalità drawdown esponenziale continua (>20%): (excess^1.5) * 6
        - Penalità duration logaritmica (>5h)
        - Reward sul numero di trade (incentiva scalping)
        """
        total_profit = results["profit_abs"].sum()
        trade_duration = results["trade_duration"].mean()
        trade_count = len(results)
        
        # Calcola max drawdown
        try:
            drawdown = calculate_max_drawdown(
                results, starting_balance=starting_balance, value_col="profit_abs"
            )
            max_drawdown_pct = drawdown.relative_account_drawdown
        except (ValueError, TypeError):
            max_drawdown_pct = 0

        # ============================================================================
        # DRAWDOWN PENALTY (esponenziale continua sopra 20%)
        # ============================================================================
        # Formula: (excess^1.5) * 6 per crescita progressiva smooth
        # Calibrata per avere penalty simili alla versione a soglie fisse:
        # - 25% drawdown → ~7% penalty (target 10%)
        # - 35% drawdown → ~35% penalty (target 35%)
        # - 45% drawdown → ~75% penalty (target 75%)
        if max_drawdown_pct > 0.20:
            excess = max_drawdown_pct - 0.20
            # Esponente 1.5 per crescita progressiva (tra lineare e quadratica)
            # Multiplier 6 calibrato sui target
            drawdown_penalty = (excess ** 1.5) * 6 * total_profit
        else:
            drawdown_penalty = 0

        # ============================================================================
        # DURATION PENALTY (logaritmica sopra 5h)
        # ============================================================================
        duration_penalty = ProfitDrawdownDurationHyperOptLoss._calculate_duration_penalty(
            trade_duration, total_profit
        )

        # ============================================================================
        # TRADE COUNT REWARD (incentiva configurazioni con più trade)
        # ============================================================================
        trade_count_reward = ProfitDrawdownDurationHyperOptLoss._calculate_trade_count_reward(
            trade_count, total_profit
        )

        # Risultato: massimizza profit, penalizza drawdown >20% e duration >5h, premia più trade
        result = -total_profit + drawdown_penalty + duration_penalty - trade_count_reward

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

    @staticmethod
    def _calculate_trade_count_reward(trade_count: int, total_profit: float) -> float:
        """
        Calculate reward based on number of trades to incentivize scalping.
        
        Reward grows logarithmically with trade count:
        - 100 trades → ~5% reward
        - 300 trades → ~10% reward
        - 500 trades → ~13% reward
        - 1000 trades → ~17% reward
        
        Formula: log(1 + trade_count / 100) / 10 → percentage of profit
        
        :param trade_count: Number of trades
        :param total_profit: Total profit to scale reward
        :return: Trade count reward (absolute value)
        """
        if trade_count <= 0:
            return 0
        
        # Reward logaritmico come percentuale del profit
        # Formula: log(1 + count/100) / 10 → percentuale
        # Es: 300 trade → log(4) / 10 = 0.139 = 13.9% del profit
        #     500 trade → log(6) / 10 = 0.179 = 17.9% del profit
        reward_percentage = math.log(1 + trade_count / 100) / 10
        reward = reward_percentage * abs(total_profit)
        
        return reward
