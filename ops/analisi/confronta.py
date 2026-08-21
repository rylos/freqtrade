#!/usr/bin/env python3
"""Confronta due backtest, ma PRIMA verifica che siano davvero diversi.

⚠️ Un A/B in cui il braccio modificato si comporta identicamente al baseline
non e' un risultato negativo: e' un esperimento NULLO, e va buttato senza
nemmeno guardare le metriche. Mi e' successo il 2026-08-22 confrontando due
configurazioni che differivano per un parametro sopra la sua soglia di
attivazione — la griglia di chiusura non scattava in nessuno dei due bracci e
il "nessuna differenza" sembrava una misura.

Il controllo guarda il COMPORTAMENTO (quanti trade, quanti fill, che durate,
che uscite), non il rendimento: se quello e' identico, non c'e' niente da
confrontare.

Uso: confronta.py <base.zip> <variante.zip> [etichetta_base] [etichetta_var]
"""

import sys

import pandas as pd

from freqtrade.data.btanalysis import load_backtest_data, load_backtest_stats


def profilo(z):
    df = load_backtest_data(z)
    st = load_backtest_stats(z)["strategy"]["RyLoSStrategy"]
    fill = df["orders"].apply(len).sum()
    uscite = (
        df["exit_reason"]
        .str.replace(r"_[0-9.]+%$", "", regex=True)
        .str.replace(r"_[0-9]+_", "_", regex=True)
        .value_counts()
    )
    return {
        "trade": len(df),
        "fill": int(fill),
        "durata_media_h": float(df["trade_duration"].mean() / 60),
        "durata_max_gg": float(df["trade_duration"].max() / 1440),
        "profitto%": float(st.get("profit_total", 0) * 100),
        "dd%": float(st.get("max_drawdown_account", 0) * 100),
        "pf": float(st.get("profit_factor", 0)),
        "perdite": int((df["profit_abs"] < 0).sum()),
        "uscite": uscite,
    }


A, B = sys.argv[1], sys.argv[2]
na = sys.argv[3] if len(sys.argv) > 3 else "base"
nb = sys.argv[4] if len(sys.argv) > 4 else "variante"
pa, pb = profilo(A), profilo(B)

chiavi_comportamento = ["trade", "fill", "durata_media_h", "durata_max_gg", "perdite"]
identici = all(
    abs(pa[k] - pb[k]) < 1e-9 or (pa[k] and abs(pa[k] - pb[k]) / abs(pa[k]) < 0.001)
    for k in chiavi_comportamento
)

print(f"{'':22} {na:>14} {nb:>14}")
for k in chiavi_comportamento:
    print(f"{k:22} {pa[k]:>14.2f} {pb[k]:>14.2f}")
print()
if identici:
    print("⛔ ESPERIMENTO NULLO: i due bracci si comportano allo stesso modo.")
    print("   Il meccanismo modificato non era attivo. Non leggere le metriche.")
    raise SystemExit(2)

print("✅ i due bracci si comportano diversamente: il confronto ha senso")
print()
for k in ["profitto%", "dd%", "pf"]:
    print(f"{k:22} {pa[k]:>14.2f} {pb[k]:>14.2f}")
print()
print("--- uscite ---")
u = pd.DataFrame({na: pa["uscite"], nb: pb["uscite"]}).fillna(0).astype(int)
print(u.head(8).to_string())
