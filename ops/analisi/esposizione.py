#!/usr/bin/env python3
"""Rendimento per unita' di esposizione — distingue "robusto" da "timido".

⭐ La timidezza e' gratis: qualunque strategia, anche pessima, ottiene meno
drawdown riducendo la size. Quindi confrontare due candidati a parametri di
rischio diversi non dice se uno e' migliore: dice solo che rischia meno.

adg / esposizione media risponde alla domanda giusta:
  - stesso rapporto con meno esposizione -> TIMIDO, la macchina e' la stessa
    e gira solo piu' piano
  - rapporto piu' alto -> ROBUSTO, ogni unita' di capitale a rischio rende di piu'

⚠️ Piu' il controllo che smaschera la timidezza mascherata: un candidato puo'
migliorare il peggior periodo **evitando di realizzare** invece che evitando di
perdere. Se le perdite realizzate crollano rispetto al baseline, il problema e'
stato spostato, non risolto (dalla sessione passivbot: spegnendo la loro griglia
di chiusura il loss_profit_ratio andava a 0,0 mentre il drawdown andava al 99,96%).

Uso: esposizione.py <backtest.zip> [saldo_iniziale]
"""

import sys

import numpy as np
import pandas as pd

from freqtrade.data.btanalysis import load_backtest_data, load_backtest_stats


ZIP = sys.argv[1]
CANDELE = "/opt/freqtrade/user_data/data/bybit/futures/HYPE_USDT_USDT-5m-futures.feather"

st = load_backtest_stats(ZIP)["strategy"]["RyLoSStrategy"]
saldo0 = float(sys.argv[2]) if len(sys.argv) > 2 else float(st.get("starting_balance", 7353))
df = load_backtest_data(ZIP)

c = pd.read_feather(CANDELE).set_index("date").sort_index()
c = c.loc[df["open_date"].min() : df["close_date"].max()]
tempi = c.index.values
chiusure = c["close"].values

# Esposizione nozionale candela per candela, ricostruita dai fill: si tiene
# conto delle uscite parziali, altrimenti l'esposizione resta gonfia fino alla
# chiusura finale e il rapporto viene sottostimato.
nozionale = np.zeros(len(c))
saldo = saldo0
saldi = np.full(len(c), saldo0)

for t in df.sort_values("open_date").itertuples():
    ordini = sorted(t.orders, key=lambda o: o.get("order_filled_timestamp") or 0)
    if not ordini:
        continue
    qta = 0.0
    tappe = [
        np.datetime64(int(o["order_filled_timestamp"]), "ms").astype("datetime64[ns]")
        for o in ordini
    ]
    tappe.append(np.datetime64(t.close_date.to_datetime64(), "ns"))
    for k, o in enumerate(ordini):
        if o.get("ft_is_entry"):
            qta += o["amount"]
        else:
            qta = max(qta - o["amount"], 0.0)
        if qta <= 0:
            continue
        i0 = np.searchsorted(tempi, tappe[k], side="left")
        i1 = np.searchsorted(tempi, tappe[k + 1], side="right")
        if i1 > i0:
            nozionale[i0:i1] += qta * chiusure[i0:i1]
    i_close = np.searchsorted(tempi, np.datetime64(t.close_date.to_datetime64(), "ns"), side="left")
    saldo += float(t.profit_abs)
    saldi[i_close:] = saldo

esposizione = nozionale / np.maximum(saldi, 1e-9)
in_mercato = float((nozionale > 0).mean())
esp_media = float(esposizione.mean())
esp_media_quando_dentro = float(esposizione[nozionale > 0].mean()) if in_mercato else 0.0
esp_max = float(esposizione.max())

giorni = (df["close_date"].max() - df["open_date"].min()).days or 1
tot = saldo / saldo0
adg = (tot ** (1 / giorni) - 1) * 100

perdite = df[df["profit_abs"] < 0]
profitti = df[df["profit_abs"] > 0]
somma_perdite = float(-perdite["profit_abs"].sum())
somma_profitti = float(profitti["profit_abs"].sum())

print(f"{ZIP.split('/')[-1]}")
print(f"saldo {saldo0:.0f} -> {saldo:.0f}  ({giorni} giorni, {len(df)} trade)")
print()
print(f"adg                          {adg:.4f}%/g")
print(f"esposizione media            {esp_media:.3f}x il conto")
print(f"  (solo quando in posizione) {esp_media_quando_dentro:.3f}x")
print(f"  massima                    {esp_max:.3f}x")
print(f"tempo in mercato             {in_mercato * 100:.1f}%")
print()
print(f"⭐ adg per unita di esposizione   {adg / esp_media if esp_media else 0:.4f}")
print()
print("--- il candidato perde meno perche' chiude meno? ---")
print(
    f"trade in perdita   {len(perdite)} su {len(df)}  ({len(perdite) / max(len(df), 1) * 100:.1f}%)"
)
print(f"perdite realizzate {somma_perdite:.0f} USDT")
print(f"profitti realizzati {somma_profitti:.0f} USDT")
print(f"loss/profit ratio  {somma_perdite / somma_profitti if somma_profitti else 0:.4f}")
print(f"durata massima     {df['trade_duration'].max() / 1440:.2f} giorni")
