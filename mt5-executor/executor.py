"""
TradingView signal -> MT5 auto-executor (Windows, MT5 desktop must be open and logged in).

Kinukuha ang bagong signals mula sa:
  source = "gmail"   -> direkta sa Gmail mo (IMAP + App Password). Pinakamabilis, walang Render na kailangan.
  source = "backend" -> sa TV Signals backend mo sa Render (/mt5/signals).
Tapos nag-o-open/close ng order sa MT5.

Run:   python executor.py              (gamit ang config.json)
Test:  python executor.py --parse "BUY XAUUSD SL 2640 TP 2660"   (tingnan lang kung paano babasahin, walang order)
"""
import email
import email.utils
import imaplib
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from email.header import decode_header, make_header

HERE = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(HERE, "config.json")
STATE_FILE = os.path.join(HERE, "state.json")
LOG_FILE = os.path.join(HERE, "executor.log")


def log(msg):
    line = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    print(line, flush=True)
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass


def load_json(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)


# ---------------------------------------------------------------- parsing

ACTIONS = [
    (r"\b(close|exit|flat)\b", "close"),
    (r"\b(strong\s+buy|buy|long|bullish)\b", "buy"),
    (r"\b(strong\s+sell|sell|short|bearish)\b", "sell"),
]
NUM = r"([0-9]+(?:[.,][0-9]+)?)"


def parse_action(text):
    """Returns 'buy' | 'sell' | 'close' | None. Earliest keyword in the text wins."""
    best = None
    for pattern, action in ACTIONS:
        m = re.search(pattern, text, re.I)
        if m and (best is None or m.start() < best[0]):
            best = (m.start(), action)
    return best[1] if best else None


def parse_price(text, label):
    m = re.search(rf"\b{label}\s*[:=@]?\s*{NUM}", text, re.I)
    return float(m.group(1).replace(",", ".")) if m else None


def parse_symbol(text, cfg):
    # 1) EXCHANGE:SYMBOL (hal. OANDA:XAUUSD, BINANCE:BTCUSDT)
    m = re.search(r"\b[A-Z][A-Z0-9_]*:([A-Z][A-Z0-9._!]*)", text)
    if m:
        return m.group(1)
    # 2) any symbol listed in symbol_map, or watch_symbols
    names = list(cfg.get("symbol_map", {}).keys()) + cfg.get("watch_symbols", [])
    for name in sorted(names, key=len, reverse=True):
        if re.search(rf"(?<![A-Z0-9]){re.escape(name)}(?![A-Z0-9])", text, re.I):
            return name.upper()
    # 3) fallback
    return cfg.get("default_symbol") or None


def parse_signal(text, cfg, ticker=None, action=None):
    text = " ".join(str(text).split())
    act = parse_action(text) or (parse_action(action) if action else None)
    sym = None
    if ticker:
        sym = str(ticker).split(":")[-1].upper()
    sym = sym or parse_symbol(text, cfg)
    return {
        "action": act,
        "symbol": sym,
        "sl": parse_price(text, "SL") or parse_price(text, "stop\\s*loss"),
        "tp": parse_price(text, "TP1?") or parse_price(text, "take\\s*profit"),
        "text": text,
    }


# ---------------------------------------------------------------- sources

class BackendSource:
    def __init__(self, cfg, state):
        self.url = cfg["backend_url"].rstrip("/")
        self.secret = cfg["backend_secret"]
        self.state = state

    def _get(self, after):
        q = urllib.parse.urlencode({"after": after}) if after else ""
        req = urllib.request.Request(f"{self.url}/mt5/signals?{q}", headers={"x-app-key": self.secret})
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.load(r)

    def init(self):
        if "backend_last_id" not in self.state:
            sigs = self._get("")
            self.state["backend_last_id"] = sigs[-1]["id"] if sigs else ""
            save_state(self.state)
            log(f"Backend connected. Luma signals hindi i-e-execute ({len(sigs)}).")

    def poll(self):
        out = []
        for s in self._get(self.state.get("backend_last_id", "")):
            text = " ".join(str(s.get(k, "")) for k in ("message", "ticker", "action") if s.get(k))
            ts = s.get("receivedAt")
            when = datetime.fromisoformat(ts.replace("Z", "+00:00")) if ts else datetime.now(timezone.utc)
            out.append((s["id"], text, when, s.get("ticker"), s.get("action")))
        return out

    def done(self, sid):
        self.state["backend_last_id"] = sid
        save_state(self.state)


class GmailSource:
    def __init__(self, cfg, state):
        self.user = cfg["gmail_address"]
        self.pw = cfg["gmail_app_password"].replace(" ", "")
        self.sender = cfg.get("gmail_from", "noreply@tradingview.com")
        self.state = state
        self.imap = None

    def _connect(self):
        self.imap = imaplib.IMAP4_SSL("imap.gmail.com")
        self.imap.login(self.user, self.pw)
        self.imap.select("INBOX", readonly=True)  # readonly: hindi nito gagalawin ang read/unread ng emails mo

    def _uids(self, criteria):
        typ, data = self.imap.uid("search", None, criteria)
        return [int(x) for x in data[0].split()] if typ == "OK" and data[0] else []

    def init(self):
        self._connect()
        if "gmail_last_uid" not in self.state:
            uids = self._uids(f'FROM "{self.sender}"')
            self.state["gmail_last_uid"] = max(uids) if uids else 0
            save_state(self.state)
            log(f"Gmail connected. Luma alert emails hindi i-e-execute ({len(uids)}).")
        else:
            log("Gmail connected.")

    def poll(self):
        try:
            self.imap.noop()
        except Exception:
            self._connect()
        last = self.state.get("gmail_last_uid", 0)
        out = []
        for uid in sorted(u for u in self._uids(f'UID {last + 1}:* FROM "{self.sender}"') if u > last):
            typ, data = self.imap.uid("fetch", str(uid), "(RFC822)")
            if typ != "OK" or not data or not isinstance(data[0], tuple):
                continue
            msg = email.message_from_bytes(data[0][1])
            subject = str(make_header(decode_header(msg.get("Subject", ""))))
            body = ""
            for part in msg.walk() if msg.is_multipart() else [msg]:
                if part.get_content_type() == "text/plain":
                    body = part.get_payload(decode=True).decode(part.get_content_charset() or "utf-8", "replace")
                    break
            if not body:  # html only
                for part in msg.walk() if msg.is_multipart() else [msg]:
                    if part.get_content_type() == "text/html":
                        html = part.get_payload(decode=True).decode(part.get_content_charset() or "utf-8", "replace")
                        body = re.sub(r"<[^>]+>", " ", html)
                        break
            lines = [l.strip() for l in body.splitlines() if l.strip()][:8]
            text = re.sub(r"^Alert:\s*", "", subject, flags=re.I) + " | " + " ".join(lines)
            try:
                when = email.utils.parsedate_to_datetime(msg.get("Date"))
            except Exception:
                when = datetime.now(timezone.utc)
            out.append((uid, text, when, None, None))
        return out

    def done(self, uid):
        self.state["gmail_last_uid"] = uid
        save_state(self.state)


# ---------------------------------------------------------------- MT5

class Trader:
    def __init__(self, cfg):
        import MetaTrader5 as mt5  # pip install MetaTrader5
        self.mt5 = mt5
        self.cfg = cfg
        self.magic = int(cfg.get("magic", 20261112))
        kw = {}
        if cfg.get("mt5_path"):
            kw["path"] = cfg["mt5_path"]
        if not mt5.initialize(**kw):
            raise SystemExit(f"Hindi maka-connect sa MT5: {mt5.last_error()}. Bukas at naka-login ba ang MT5?")
        acc = mt5.account_info()
        term = mt5.terminal_info()
        if acc is None:
            raise SystemExit("Walang naka-login na account sa MT5.")
        is_demo = acc.trade_mode == mt5.ACCOUNT_TRADE_MODE_DEMO
        log(f"MT5 OK: account {acc.login} @ {acc.server} | {'DEMO' if is_demo else 'REAL'} | balance {acc.balance} {acc.currency}")
        if not is_demo and not cfg.get("allow_live", False):
            raise SystemExit('REAL account ito. Para sa safety, demo muna. Kung sigurado ka na, gawing "allow_live": true sa config.json.')
        if term and not term.trade_allowed:
            log('WARNING: Naka-OFF ang "Algo Trading" button sa MT5. I-on mo para gumana ang orders.')

    def resolve(self, name):
        mt5 = self.mt5
        name = self.cfg.get("symbol_map", {}).get(name.upper(), name)
        candidates = [name, name + self.cfg.get("symbol_suffix", "")]
        for c in candidates:
            info = mt5.symbol_info(c)
            if info:
                if not info.visible:
                    mt5.symbol_select(c, True)
                return c
        return None

    def lot(self, symbol, base):
        lots = self.cfg.get("lots", {})
        return float(lots.get(symbol, lots.get(base, self.cfg.get("lot", 0.01))))

    def positions(self, symbol):
        return [p for p in (self.mt5.positions_get(symbol=symbol) or []) if p.magic == self.magic or self.cfg.get("manage_all_positions")]

    def _filling(self, info):
        mt5 = self.mt5
        fm = info.filling_mode
        if fm & 1:
            return mt5.ORDER_FILLING_FOK
        if fm & 2:
            return mt5.ORDER_FILLING_IOC
        return mt5.ORDER_FILLING_RETURN

    def _send(self, req, what):
        if self.cfg.get("dry_run"):
            log(f"  [DRY RUN] {what}: {req}")
            return True
        r = self.mt5.order_send(req)
        if r is None:
            log(f"  FAIL {what}: {self.mt5.last_error()}")
            return False
        if r.retcode not in (self.mt5.TRADE_RETCODE_DONE, self.mt5.TRADE_RETCODE_PLACED):
            log(f"  FAIL {what}: retcode {r.retcode} {r.comment}")
            return False
        log(f"  OK {what}: ticket {r.order} @ {r.price}")
        return True

    def close(self, pos):
        mt5 = self.mt5
        info = mt5.symbol_info(pos.symbol)
        tick = mt5.symbol_info_tick(pos.symbol)
        is_buy = pos.type == mt5.POSITION_TYPE_BUY
        return self._send({
            "action": mt5.TRADE_ACTION_DEAL, "symbol": pos.symbol, "volume": pos.volume, "position": pos.ticket,
            "type": mt5.ORDER_TYPE_SELL if is_buy else mt5.ORDER_TYPE_BUY,
            "price": tick.bid if is_buy else tick.ask, "deviation": int(self.cfg.get("slippage_points", 30)),
            "magic": self.magic, "comment": "TV close", "type_filling": self._filling(info),
        }, f"CLOSE {'BUY' if is_buy else 'SELL'} {pos.symbol} #{pos.ticket}")

    def execute(self, sig):
        mt5 = self.mt5
        sym = self.resolve(sig["symbol"])
        if not sym:
            log(f"  SKIP: walang symbol na '{sig['symbol']}' sa broker mo. Idagdag sa symbol_map sa config.json.")
            return
        mine = self.positions(sym)
        if sig["action"] == "close":
            if not mine:
                log(f"  Walang open position sa {sym}.")
            for p in mine:
                self.close(p)
            return

        want_buy = sig["action"] == "buy"
        same = [p for p in mine if (p.type == mt5.POSITION_TYPE_BUY) == want_buy]
        opposite = [p for p in mine if (p.type == mt5.POSITION_TYPE_BUY) != want_buy]
        if self.cfg.get("close_opposite", True):
            for p in opposite:
                self.close(p)
        if same and self.cfg.get("one_position_per_symbol", True):
            log(f"  SKIP: may open {sig['action'].upper()} na sa {sym}.")
            return

        info = mt5.symbol_info(sym)
        tick = mt5.symbol_info_tick(sym)
        if info is None or tick is None:
            log(f"  SKIP: walang presyo para sa {sym} (sarado ba ang market?).")
            return
        price = tick.ask if want_buy else tick.bid
        pt = info.point
        sl = sig.get("sl") if self.cfg.get("use_signal_sl_tp", True) else None
        tp = sig.get("tp") if self.cfg.get("use_signal_sl_tp", True) else None
        sl_pts, tp_pts = float(self.cfg.get("sl_points", 0)), float(self.cfg.get("tp_points", 0))
        if not sl and sl_pts:
            sl = price - sl_pts * pt if want_buy else price + sl_pts * pt
        if not tp and tp_pts:
            tp = price + tp_pts * pt if want_buy else price - tp_pts * pt
        # ignore SL/TP that is on the wrong side of price (bad parse)
        if sl and ((want_buy and sl >= price) or (not want_buy and sl <= price)):
            log(f"  SL {sl} mali ang side vs price {price}, hindi ginamit.")
            sl = None
        if tp and ((want_buy and tp <= price) or (not want_buy and tp >= price)):
            log(f"  TP {tp} mali ang side vs price {price}, hindi ginamit.")
            tp = None

        req = {
            "action": mt5.TRADE_ACTION_DEAL, "symbol": sym, "volume": self.lot(sym, sig["symbol"]),
            "type": mt5.ORDER_TYPE_BUY if want_buy else mt5.ORDER_TYPE_SELL, "price": price,
            "deviation": int(self.cfg.get("slippage_points", 30)), "magic": self.magic,
            "comment": "TV signal", "type_time": mt5.ORDER_TIME_GTC, "type_filling": self._filling(info),
        }
        if sl:
            req["sl"] = round(sl, info.digits)
        if tp:
            req["tp"] = round(tp, info.digits)
        self._send(req, f"{sig['action'].upper()} {req['volume']} {sym}")


# ---------------------------------------------------------------- main

def main():
    cfg = load_json(CONFIG_FILE, None)
    if cfg is None:
        raise SystemExit("Walang config.json (o may mali sa format). Kopyahin ang config.example.json bilang config.json.")

    if len(sys.argv) > 2 and sys.argv[1] == "--parse":
        print(json.dumps(parse_signal(" ".join(sys.argv[2:]), cfg), indent=2))
        return

    state = load_json(STATE_FILE, {})
    trader = Trader(cfg)
    source = GmailSource(cfg, state) if cfg.get("source", "gmail") == "gmail" else BackendSource(cfg, state)
    source.init()
    every = float(cfg.get("poll_seconds", 3))
    max_age = float(cfg.get("max_signal_age_seconds", 300))
    log(f"Naghihintay ng signals (source: {cfg.get('source', 'gmail')}, check every {every}s). Ctrl+C para itigil.")

    errors = 0
    while True:
        try:
            for sid, text, when, ticker, action in source.poll():
                sig = parse_signal(text, cfg, ticker, action)
                log(f"SIGNAL: {sig['text'][:200]}")
                log(f"  -> action={sig['action']} symbol={sig['symbol']} sl={sig['sl']} tp={sig['tp']}")
                age = (datetime.now(timezone.utc) - when.astimezone(timezone.utc)).total_seconds()
                if age > max_age:
                    log(f"  SKIP: luma na ang signal ({int(age)}s ago).")
                elif not sig["action"] or not sig["symbol"]:
                    log("  SKIP: hindi mabasa ang buy/sell o symbol.")
                else:
                    trader.execute(sig)
                source.done(sid)
            errors = 0
        except KeyboardInterrupt:
            raise
        except Exception as e:
            errors += 1
            log(f"Error: {e!r} (retry)")
            time.sleep(min(60, 5 * errors))
            if isinstance(source, GmailSource):
                try:
                    source._connect()
                except Exception:
                    pass
        time.sleep(every)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log("Itinigil.")
