#!/usr/bin/env python3
"""Watchdog del bot freqtrade RyLoS (HYPE/USDT:USDT su bybit) su amazon.

Il bot non scrive su file: tutto il log vive nel buffer del tmux `ft`, quindi le
verifiche si fanno su `tmux capture-pane` piu' il database dei trade.

Esito -> healthchecks.io (check "freqtrade (bybit)"):
  - tutto ok  -> ping di successo con un riepilogo nel body
  - anomalia  -> ping /fail con la diagnosi nel body (Healthchecks notifica)
Se il cron o la macchina muoiono, il check scade da solo: e' il dead man switch.

RIAVVIO AUTOMATICO, solo se il processo e' ASSENTE (crash/OOM/kill). Il motivo e'
che `stoploss_on_exchange` e' disattivo per scelta: il guard-stop -0.721 vive nel
bot, quindi a bot morto una posizione aperta resta senza protezione. Un bot vivo
ma bloccato NON viene toccato: resta in allarme e decide Marco.
Freno: al massimo MAX_RESTARTS tentativi in RESTART_WINDOW_MIN minuti, e nessun
riavvio se esiste il file di manutenzione (fermate volute: deploy, cambio candidato).
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import subprocess
import time
import urllib.request
from pathlib import Path


BASE = Path.home() / "watchdog"
STATE = BASE / "ft_state.json"
ENV = BASE / "healthchecks.env"
# Se questo file esiste il watchdog non riavvia nulla: e' l'interruttore per le
# fermate volute (deploy, cambio candidato, manutenzione).
MAINTENANCE = BASE / "ft_maintenance"
FT_DIR = Path("/opt/freqtrade")
DB = FT_DIR / "tradesv3.sqlite"
TMUX_SESSION = "ft"
BOT_CMD = f"cd {FT_DIR} && .venv/bin/freqtrade trade -c user_data/config.json"

# Un bot che non riparte da solo ha un problema che il riavvio non risolve:
# dopo due tentativi si smette di provarci e si resta in allarme.
MAX_RESTARTS = 2
RESTART_WINDOW_MIN = 60
# Quanto aspettare che il processo si presenti dopo il lancio.
RESTART_WAIT_S = 90

# L'heartbeat esce ogni ~60s (a volte 65s). 10 minuti = oltre 9 battiti persi:
# anomalia vera e non jitter del loop.
HEARTBEAT_STALE_MIN = 10
# Finestra entro cui una riga ERROR e' considerata "in corso" e non storia vecchia
# gia' notificata in un giro precedente.
ERROR_WINDOW_MIN = 15
# Righe di buffer da leggere: l'heartbeat al minuto riempie in fretta, 400 righe
# coprono comodamente la finestra sopra.
CAPTURE_LINES = 400

# Tutto cio' che viene dal canale Telegram e' rumore di rete: il bot continua a
# operare e ormai l'allarme vero passa da Healthchecks. Non silenziato del tutto:
# finisce come conteggio nel body del ping, cosi' un'interruzione prolungata si vede.
# Misurato il 2026-08-06: la prima versione ha dato subito un falso positivo su
# "Exception happened while polling for updates" (telegram.ext.Updater).
TELEGRAM_RE = re.compile(r"telegram", re.IGNORECASE)
# Traceback dello spegnimento manuale (Ctrl-C): normale, non e' un guasto.
BENIGN = (
    "'NoneType' object has no attribute '_abort'",
    "Fatal exception!",
)

TS_RE = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}),\d+")
HEARTBEAT_RE = re.compile(r"Bot heartbeat\. PID=(\d+), version='([^']*)', state='([^']*)'")
LEVEL_RE = re.compile(r" - (ERROR|CRITICAL) - ")


def candidato_attivo() -> str:
    """Nome del candidato in esecuzione, dedotto dall'md5 del json dei params.

    Hardcodarlo significa dimenticarselo al deploy successivo: l'etichetta
    "T4G" era sopravvissuta a due cambi di candidato. Qui si confronta il json
    attivo con quelli archiviati in user_data/candidates/ e si usa il nome del
    file che combacia. Se nessuno combacia (params modificati a mano) si
    ripiega sull'md5 breve, che resta comunque identificativo.
    """
    attivo = FT_DIR / "user_data/strategies/RyLoSStrategy.json"
    try:
        h = hashlib.md5(attivo.read_bytes(), usedforsecurity=False).hexdigest()
    except OSError:
        return "?"
    for c in sorted((FT_DIR / "user_data/candidates").glob("*.json")):
        try:
            if hashlib.md5(c.read_bytes(), usedforsecurity=False).hexdigest() == h:
                return c.stem.split("_")[0].upper()
        except OSError:
            continue
    return h[:8]


def hc_url() -> str | None:
    """URL di ping: sta in un file separato perche' e' una credenziale."""
    if not ENV.exists():
        return None
    for line in ENV.read_text().splitlines():
        line = line.strip()
        if line.startswith("HC_FREQTRADE="):
            return line.split("=", 1)[1].strip().strip('"').strip("'") or None
    return None


def ping(ok: bool, body: str) -> None:
    url = hc_url()
    if not url:
        return
    if not ok:
        url = url.rstrip("/") + "/fail"
    try:
        req = urllib.request.Request(url, data=body.encode()[:9000])  # noqa: S310
        with urllib.request.urlopen(req, timeout=20) as r:  # noqa: S310
            r.read()
    except Exception as exc:  # il ping non deve mai far fallire il controllo
        log(f"ping fallito: {exc}")


def log(msg: str) -> None:
    stamp = time.strftime("%Y-%m-%d %H:%M:%S")
    with (BASE / "freqtrade_watchdog.log").open("a") as f:
        f.write(f"{stamp} {msg}\n")


def load_state() -> dict:
    if STATE.exists():
        try:
            return json.loads(STATE.read_text())
        except json.JSONDecodeError:
            pass
    return {}


def bot_pid() -> str | None:
    r = subprocess.run(
        ["pgrep", "-f", "bin/freqtrade"], capture_output=True, text=True, check=False
    )
    for p in r.stdout.split():
        if p.strip() and p.strip() != str(os.getpid()):
            return p.strip()
    return None


def tmux(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["tmux", *args], capture_output=True, text=True, check=False)


def try_restart(state: dict) -> list[str]:
    """Rilancia il bot nel tmux `ft`. Ritorna le righe di esito da mettere nel body."""
    if MAINTENANCE.exists():
        return [f"riavvio NON tentato: manutenzione attiva ({MAINTENANCE})"]

    now = time.time()
    recent = [t for t in state.get("restarts", []) if now - t < RESTART_WINDOW_MIN * 60]
    if len(recent) >= MAX_RESTARTS:
        state["restarts"] = recent
        return [
            (
                f"riavvio NON tentato: gia' {len(recent)} tentativi in "
                f"{RESTART_WINDOW_MIN} min, serve un intervento a mano"
            )
        ]

    out = []
    if tmux("has-session", "-t", TMUX_SESSION).returncode != 0:
        r = tmux("new-session", "-d", "-s", TMUX_SESSION, "-c", str(FT_DIR))
        if r.returncode != 0:
            return [f"riavvio FALLITO: impossibile creare la sessione tmux ({r.stderr.strip()})"]
        out.append(f"sessione tmux '{TMUX_SESSION}' ricreata (non esisteva)")

    r = tmux("send-keys", "-t", TMUX_SESSION, BOT_CMD, "Enter")
    if r.returncode != 0:
        return out + [f"riavvio FALLITO: send-keys ({r.stderr.strip()})"]

    recent.append(now)
    state["restarts"] = recent

    deadline = now + RESTART_WAIT_S
    while time.time() < deadline:
        time.sleep(5)
        pid = bot_pid()
        if pid:
            out.append(f"RIAVVIATO: nuovo pid {pid} dopo {time.time() - now:.0f}s")
            return out
    return out + [f"riavvio FALLITO: nessun processo dopo {RESTART_WAIT_S}s"]


def capture() -> list[str]:
    r = subprocess.run(
        ["tmux", "capture-pane", "-p", "-t", TMUX_SESSION, "-S", f"-{CAPTURE_LINES}"],
        capture_output=True,
        text=True,
        check=False,
    )
    return r.stdout.splitlines() if r.returncode == 0 else []


def line_age_min(line: str) -> float | None:
    """Eta' in minuti della riga; i log di freqtrade sono nell'ora locale del server."""
    m = TS_RE.match(line)
    if not m:
        return None
    try:
        t = time.mktime(time.strptime(m.group(1), "%Y-%m-%d %H:%M:%S"))
    except ValueError:
        return None
    return (time.time() - t) / 60


def open_trades() -> tuple[int, str]:
    """Trade aperti nel db (fonte di verita': il db e' in WAL, i mtime non dicono nulla)."""
    if not DB.exists():
        return -1, "db assente"
    try:
        c = sqlite3.connect(f"file:{DB}?mode=ro", uri=True, timeout=10)
        rows = c.execute(
            "select pair, open_date, amount, open_rate from trades where is_open = 1"
        ).fetchall()
        c.close()
    except sqlite3.Error as exc:
        return -1, f"db illeggibile: {exc}"
    if not rows:
        return 0, "nessun trade aperto"
    p, od, amt, rate = rows[0]
    return len(rows), f"{len(rows)} aperto: {p} {amt} @ {rate} dal {str(od)[:16]}"


def main() -> None:  # noqa: C901
    state = load_state()
    problems: list[str] = []
    info: list[str] = []
    just_restarted = False

    pid = bot_pid()
    if pid is None:
        problems.append(
            "processo freqtrade ASSENTE: il bot non sta operando "
            "(con un trade aperto la posizione resta senza guard-stop)"
        )
        problems.extend(try_restart(state))
        pid = bot_pid()
        # Dopo un riavvio il buffer contiene ancora l'ultimo heartbeat di prima del
        # crash: segnalarlo come "fermo da N min" sarebbe fuorviante.
        just_restarted = True
    elif state.get("pid") and state["pid"] != pid:
        info.append(f"bot riavviato (pid {state['pid']} -> {pid})")
    state["pid"] = pid

    lines = capture()
    if not lines:
        problems.append(f"buffer tmux '{TMUX_SESSION}' non leggibile (sessione chiusa?)")

    # Ultimo heartbeat: eta' e stato dichiarato dal bot.
    hb_age = None
    for line in reversed(lines):
        m = HEARTBEAT_RE.search(line)
        if m:
            hb_age = line_age_min(line)
            _hb_pid, version, hb_state = m.groups()
            info.append(f"{version}, state={hb_state}")
            if hb_state != "RUNNING" and not just_restarted:
                problems.append(f"stato del bot = {hb_state} (atteso RUNNING)")
            if hb_age is not None and hb_age > HEARTBEAT_STALE_MIN and not just_restarted:
                problems.append(
                    f"heartbeat fermo da {hb_age:.0f} min (normale <2): loop bloccato o rete persa"
                )
            break
    else:
        if lines and not just_restarted:
            problems.append("nessun heartbeat nel buffer tmux")

    # Errori recenti, separando il rumore Telegram dai guasti veri.
    recent = [
        line
        for line in lines
        if LEVEL_RE.search(line)
        and not any(b in line for b in BENIGN)
        and (line_age_min(line) or 999) <= ERROR_WINDOW_MIN
    ]
    tg_errs = [line for line in recent if TELEGRAM_RE.search(line)]
    errs = [line for line in recent if line not in tg_errs]
    if errs:
        problems.append(f"{len(errs)} righe ERROR/CRITICAL negli ultimi {ERROR_WINDOW_MIN} min")
        problems.extend("  " + e[:200] for e in errs[:3])
    if tg_errs:
        info.append(f"{len(tg_errs)} errori Telegram (rete, non bloccanti)")

    n_open, trades_desc = open_trades()
    if n_open < 0:
        problems.append(trades_desc)
    else:
        info.append(trades_desc)

    ok = not problems
    head = f"freqtrade RyLoS {candidato_attivo()} (amazon) — " + ("OK" if ok else "ANOMALIA")
    body = "\n".join([head, *(f"[!] {p}" for p in problems), *(f"- {i}" for i in info)])

    ping(ok, body)
    state["last_run"] = time.time()
    state["last_ok"] = ok
    STATE.write_text(json.dumps(state))
    if not ok:
        log(body.replace("\n", " | "))


if __name__ == "__main__":
    main()
