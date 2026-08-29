#!/usr/bin/env python3
"""Report periodico del bot live RyLoS (freqtrade, HYPE/USDT:USDT su bybit).

Complementare al watchdog: quello avvisa quando il bot ROMPE (healthchecks.io),
questo segue i TRADE — apertura, gradini della griglia, chiusura — che e' l'unico
momento in cui c'e' davvero qualcosa da controllare.

⭐ Parla solo se e' successo qualcosa: un evento sui trade oppure un'anomalia.
Niente messaggi verdi periodici, perche' il vivo/morto lo copre gia' healthchecks
e un "va tutto bene" ogni sei ore insegna solo a non aprirli piu'. Il confronto e'
con la situazione dell'ultimo giro, salvata in ft_report_state.json.

Sola lettura: non riavvia, non tocca il bot, non scrive nel db.
Gemello di hl_report.py (ry-hl su passivbot), da cui prende la struttura.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import sqlite3
import subprocess
import tempfile
import time
import urllib.parse
import urllib.request
from datetime import UTC, datetime
from pathlib import Path


BASE = Path.home() / "watchdog"
CREDS = BASE / "telegram.json"
# Ultima situazione vista: serve a distinguere "e' successo qualcosa" da "e' tutto
# come al giro prima", che e' l'unica cosa che decide se si parla o si tace.
STATE = BASE / "ft_report_state.json"
FT_DIR = Path("/opt/freqtrade")
DB = FT_DIR / "tradesv3.sqlite"
TMUX_SESSION = "ft"
PAIR = "HYPE/USDT:USDT"
TICKER_URL = "https://api.bybit.com/v5/market/tickers?category=linear&symbol=HYPEUSDT"

# Gli md5 del candidato in produzione (T9, dal 2026-08-26). Se cambiano senza che
# sia stato fatto un deploy, il live non e' piu' quello misurato nel backtest.
PY_MD5 = "2c1c7083e795952e139be1259eacf133"
JSON_MD5 = "485a32f16332b05636b2dcf3695d26e8"

# Stesse finestre e stessi filtri di rumore del watchdog: vedi ops/README.md.
CAPTURE_LINES = 600
HEARTBEAT_STALE_MIN = 10
ERROR_WINDOW_H = 2
# Un bot fermo NON e' un allarme: mediana 4h, p99 41h, massimo storico 71h, e in
# mercato che sale senza storni la strategia non ha proprio niente da comprare.
# Le ore di attesa restano nel corpo del messaggio come contesto, non come giallo.

# Perdita non realizzata sulla posizione oltre la quale il report diventa giallo.
# Il vincolo di progetto e' il 30% sul conto: sulla singola posizione si guarda
# prima, perche' la griglia puo' ancora caricare.
UNREAL_ALERT_PCT = -25.0

TS_RE = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}),\d+")
HEARTBEAT_RE = re.compile(r"Bot heartbeat\. PID=(\d+), version='([^']*)', state='([^']*)'")
LEVEL_RE = re.compile(r" - (ERROR|CRITICAL) - ")
TELEGRAM_RE = re.compile(r"telegram", re.IGNORECASE)
WS_RE = re.compile(r"exchange_ws")
BENIGN = ("'NoneType' object has no attribute '_abort'", "Fatal exception!")


def esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def send(text: str) -> None:
    creds = json.loads(CREDS.read_text())
    data = urllib.parse.urlencode(
        {"chat_id": creds["chat_id"], "text": text, "parse_mode": "HTML"}
    ).encode()
    url = "https://api.telegram.org/bot" + creds["token"] + "/sendMessage"
    with urllib.request.urlopen(url, data=data, timeout=30) as r:
        r.read()


def bot_pid() -> str | None:
    r = subprocess.run(
        ["pgrep", "-f", "bin/freqtrade"], capture_output=True, text=True, check=False
    )
    for p in r.stdout.split():
        if p.strip() and p.strip() != str(os.getpid()):
            return p.strip()
    return None


def uptime_h(pid: str) -> float | None:
    """Ore di vita del processo, dal mtime di /proc/<pid> (il campo start e' in tick)."""
    try:
        return (time.time() - Path(f"/proc/{pid}").stat().st_mtime) / 3600
    except OSError:
        return None


def capture() -> list[str]:
    r = subprocess.run(
        ["tmux", "capture-pane", "-p", "-t", TMUX_SESSION, "-S", f"-{CAPTURE_LINES}"],
        capture_output=True,
        text=True,
        check=False,
    )
    return r.stdout.splitlines() if r.returncode == 0 else []


def line_age_min(line: str) -> float | None:
    m = TS_RE.match(line)
    if not m:
        return None
    try:
        return (time.time() - time.mktime(time.strptime(m.group(1), "%Y-%m-%d %H:%M:%S"))) / 60
    except ValueError:
        return None


def md5(path: Path) -> str:
    try:
        return hashlib.md5(path.read_bytes(), usedforsecurity=False).hexdigest()
    except OSError:
        return "?"


def last_price() -> float | None:
    """Prezzo corrente da bybit, endpoint pubblico: nessuna chiave, nessun ordine."""
    try:
        with urllib.request.urlopen(TICKER_URL, timeout=20) as r:
            d = json.load(r)
        return float(d["result"]["list"][0]["lastPrice"])
    except Exception:
        return None


def db_snapshot() -> sqlite3.Connection | None:
    """Copia dei tre file WAL in tmp: il db e' in WAL, leggerlo in piedi mente."""
    tmp = Path(tempfile.mkdtemp())
    try:
        for ext in ("", "-wal", "-shm"):
            src = Path(str(DB) + ext)
            if src.exists():
                shutil.copy(src, tmp / ("t.sqlite" + ext))
        return sqlite3.connect(tmp / "t.sqlite")
    except (OSError, sqlite3.Error):
        return None


def entry_fills(conn: sqlite3.Connection, trade_id: int) -> list:
    """Gradini della griglia gia' riempiti: sono gli ordini di ingresso eseguiti."""
    return conn.execute(
        "select average, filled, order_filled_date from orders "
        "where ft_trade_id = ? and ft_order_side = 'buy' and filled > 0 "
        "order by order_filled_date",
        (trade_id,),
    ).fetchall()


def load_state() -> dict:
    try:
        return json.loads(STATE.read_text())
    except (OSError, json.JSONDecodeError):
        return {}


def utc_ts(s: object) -> float | None:
    try:
        dt = datetime.strptime(str(s)[:19], "%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC)
    except ValueError:
        return None
    return dt.timestamp()


def main() -> None:  # noqa: C901
    rows: list[str] = []
    alert = False
    prev = load_state()

    pid = bot_pid()
    if pid is None:
        alert = True
        rows.append("pid: <b>ASSENTE</b>")
    else:
        up = uptime_h(pid)
        rows.append(f"pid {pid}" + (f", su da {up:.0f}h" if up is not None else ""))

    lines = capture()
    hb_age = None
    for line in reversed(lines):
        m = HEARTBEAT_RE.search(line)
        if m:
            hb_age = line_age_min(line)
            _p, version, state = m.groups()
            # PAUSED e STOPPED arrivano solo da un comando esplicito: sono
            # fermate volute, non guasti. Vedi ops/watchdog_freqtrade.py.
            if state not in ("RUNNING", "PAUSED", "STOPPED"):
                alert = True
            rows.append(
                f"{version}, state={state}"
                + (f", heartbeat {hb_age:.0f} min fa" if hb_age is not None else "")
            )
            break
    if hb_age is None:
        alert = True
        rows.append("<b>nessun heartbeat nel buffer tmux</b>")
    elif hb_age > HEARTBEAT_STALE_MIN:
        alert = True

    # Il candidato in produzione deve restare quello misurato nel backtest.
    py_ok = md5(FT_DIR / "user_data/strategies/RyLoSStrategy.py") == PY_MD5
    json_ok = md5(FT_DIR / "user_data/strategies/RyLoSStrategy.json") == JSON_MD5
    if py_ok and json_ok:
        rows.append("candidato T9 (md5 .py e .json ok)")
    else:
        alert = True
        rows.append(
            "<b>candidato CAMBIATO</b>: "
            f".py {'ok' if py_ok else 'DIVERSO'}, .json {'ok' if json_ok else 'DIVERSO'}"
        )

    conn = db_snapshot()
    eventi: list[str] = []
    firma: dict = {}
    if conn is None:
        alert = True
        rows.append("<b>db non leggibile</b>")
    else:
        price = last_price()
        n_chiusi, pl_tot = conn.execute(
            "select count(*), coalesce(sum(close_profit_abs), 0) from trades where is_open = 0"
        ).fetchone()
        aperti = conn.execute(
            "select id, amount, open_rate, stop_loss, open_date from trades where is_open = 1"
        ).fetchall()

        if aperti:
            tid, amount, open_rate, stop, open_date = aperti[0]
            gradini = entry_fills(conn, tid)
            firma = {"aperto": tid, "gradini": len(gradini), "chiusi": n_chiusi}
            ore = (time.time() - (utc_ts(open_date) or time.time())) / 3600

            pct_ora = (price / open_rate - 1) * 100 if price else None
            coda = f" · ora {price:.2f} ({pct_ora:+.1f}%)" if price else ""
            if prev.get("aperto") != tid:
                eventi.append(f"🟦 trade {tid} aperta · {open_rate:.2f}{coda}")
            elif prev.get("gradini", 0) < len(gradini):
                # La griglia ha caricato: e' il momento in cui il rischio cresce,
                # quindi si guarda il nuovo prezzo medio e lo stop ricalcolato.
                eventi.append(
                    f"🟦 trade {tid} · gradino {len(gradini)} · "
                    f"medio {open_rate:.2f}{coda}" + (f" · stop {stop:.2f}" if stop else "")
                )

            riga = f"trade {tid}, aperto da {ore:.0f}h · {len(gradini)} gradini · "
            riga += f"{amount} @ {open_rate:.3f}"
            if price:
                unreal = (price - open_rate) * amount
                pct = (price / open_rate - 1) * 100
                if pct <= UNREAL_ALERT_PCT:
                    alert = True
                riga += f" · ora {price:.3f} ({pct:+.1f}%, {unreal:+.0f} USDT)"
                if stop:
                    riga += f" · stop {stop:.2f} ({(stop / price - 1) * 100:+.1f}%)"
            rows.append(riga)
        else:
            firma = {"aperto": None, "gradini": 0, "chiusi": n_chiusi}
            ultimo = conn.execute(
                "select id, close_date, close_profit_abs, close_profit, exit_reason, open_date "
                "from trades where is_open = 0 order by close_date desc limit 1"
            ).fetchone()
            if prev.get("chiusi") is not None and prev["chiusi"] < n_chiusi and ultimo:
                tid, close_date, pl, pl_pct, reason, open_date = ultimo
                dur = ((utc_ts(close_date) or 0) - (utc_ts(open_date) or 0)) / 3600
                grad = len(entry_fills(conn, tid))
                eventi.append(
                    f"✅ trade {tid} chiusa · {pl:+.2f} USDT "
                    f"({(pl_pct or 0) * 100:+.1f}%) · {grad} gradin"
                    f"{'o' if grad == 1 else 'i'} · {dur:.0f}h · "
                    f"{esc(str(reason))} · totale {pl_tot + 0:+.0f}"
                )
            t = utc_ts(ultimo[1]) if ultimo else None
            flat_h = (time.time() - t) / 3600 if t else None
            rows.append(
                f"flat da {flat_h:.0f}h" if flat_h is not None else "flat, nessun trade nel db"
            )

        rows.append(f"totale: {n_chiusi} chiusi, {pl_tot:+.0f} USDT")
        conn.close()

    # Errori veri delle ultime 2h: telegram e websocket sono rumore noto (README).
    recent = [
        line
        for line in lines
        if LEVEL_RE.search(line)
        and not any(b in line for b in BENIGN)
        and (line_age_min(line) or 1e9) <= ERROR_WINDOW_H * 60
    ]
    veri = [line for line in recent if not TELEGRAM_RE.search(line) and not WS_RE.search(line)]
    rumore = len(recent) - len(veri)
    if veri:
        alert = True
    rows.append(f"{ERROR_WINDOW_H}h: {len(veri)} errori ({rumore} rumore noto)")
    if veri:
        rows.append("<code>" + esc(veri[-1][:200]) + "</code>")

    # Silenzio quando non e' successo niente: healthchecks copre gia' il vivo/morto,
    # e un messaggio verde ogni sei ore insegna solo a non aprirli piu'. Si parla
    # per un'anomalia o per un evento sui trade, che e' l'unico momento in cui c'e'
    # davvero qualcosa da controllare.
    STATE.write_text(json.dumps(firma))
    if not alert and not eventi:
        return

    # Un evento normale e' una riga sola, come il report passivbot: il blocco
    # diagnostico completo si apre solo quando c'e' qualcosa da guardare.
    # Un messaggio lungo per ogni chiusura regolare insegna solo a non aprirli.
    if not alert:
        send("\n".join(eventi))
        return

    send("\n".join(["🟠 <b>freqtrade da guardare</b>", *eventi, *rows]))


if __name__ == "__main__":
    main()
