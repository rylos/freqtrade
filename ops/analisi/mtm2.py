#!/usr/bin/env python3
"""Drawdown mark-to-market di un backtest, usando la STESSA funzione della loss.

Riusare `serie_mtm` invece di riscriverla evita che la misura di validazione e
quella che guida l'ottimizzazione divergano — cosa che e' appena successa con
una versione veloce che ignorava le uscite parziali (close-grid, profit-lock)
e sovrastimava il drawdown di due punti.

Uso: mtm2.py <backtest.zip> [saldo_iniziale]
"""

import sys

import pandas as pd


sys.path.insert(0, "/opt/freqtrade/user_data/hyperopts")
from SortinoRyLoSEquityHyperOptLoss import serie_mtm

from freqtrade.data.btanalysis import load_backtest_data, load_backtest_stats


ZIP = sys.argv[1]
CANDELE = "/opt/freqtrade/user_data/data/bybit/futures/HYPE_USDT_USDT-5m-futures.feather"

st = load_backtest_stats(ZIP)["strategy"]["RyLoSStrategy"]
saldo0 = float(sys.argv[2]) if len(sys.argv) > 2 else float(st.get("starting_balance", 7353))
df = load_backtest_data(ZIP)

candele = pd.read_feather(CANDELE)
candele = candele[
    (candele["date"] >= df["open_date"].min()) & (candele["date"] <= df["close_date"].max())
].reset_index(drop=True)

equity, finale = serie_mtm(df, candele, saldo0)
picco = equity.cummax()
dd = (equity / picco - 1.0) * 100
i = dd.idxmin()
# ⚠️ La serie mark-to-market puo' avere timestamp ripetuti (piu' fill nella
# stessa candela): .loc[i] restituirebbe una Series e il format fallisce.
val_eq = float(pd.Series(equity.loc[i]).iloc[0])
val_pk = float(pd.Series(picco.loc[i]).iloc[0])

print(f"{ZIP.split('/')[-1]}")
prof = st.get("profit_total", 0) * 100
print(f"saldo {saldo0:.0f} -> {finale:.0f} | trade {len(df)} | profitto {prof:.1f}%")
print()
print(f"DRAWDOWN MARK-TO-MARKET: {-dd.min():.2f}%   (il {i:%Y-%m-%d %H:%M})")
print(f"  equity {val_eq:.0f} contro picco {val_pk:.0f}")
print(f"drawdown sul realizzato (freqtrade): {st.get('max_drawdown_account', 0) * 100:.2f}%")
print()
for x in (10, 20, 25, 30):
    print(f"  tempo sotto il -{x}%: {(dd <= -x).mean() * 100:.2f}%")
print(f"  punti della serie: {len(equity)}")
