# MT5 Auto-Executor: TradingView signal → order sa MT5

Kung ano ang signal ng indicator mo sa TradingView (BUY / SELL / CLOSE), yun din ang i-e-execute ng MT5 mo sa Windows PC.

```
TradingView alert (email) → Gmail → executor.py (sa PC mo, tumatakbo sa cmd) → MT5
```

> ⚠️ **DEMO ACCOUNT MUNA.** Kusang ayaw tumakbo ng script sa REAL account hangga't hindi mo ginagawang `"allow_live": true`. Mag-test muna ng ilang araw sa demo. Hindi ito financial advice; ikaw ang responsable sa trades.

> ⏱️ **May delay.** Dahil email ang daan (free TradingView), mga **10–60 segundo** bago ma-execute ang signal. Hindi ito para sa scalping na segundo ang pagitan.

---

## Kailangan
- Windows PC na laging bukas habang gusto mong mag-trade
- **MT5 desktop** (bukas at naka-login sa broker mo)
- **Python 3** (libre)
- Gmail na tumatanggap ng TradingView alert emails

## Step 1: I-install ang Python
1. Download sa https://www.python.org/downloads/windows/
2. Sa installer, **i-check ang "Add python.exe to PATH"** bago i-click ang Install.

## Step 2: I-download ang script
I-download ang folder na `mt5-executor` (o ang buong repo bilang ZIP mula sa GitHub → **Code → Download ZIP**) at i-extract, hal. sa `C:\mt5-executor`.

## Step 3: I-install ang MetaTrader5 package
Buksan ang **cmd** at i-type:
```
cd C:\mt5-executor
pip install -r requirements.txt
```

## Step 4: Gumawa ng Gmail App Password
Para mabasa ng script ang TradingView emails mo (read-only; hindi nito gagalawin ang emails mo):
1. Dapat naka-ON ang **2-Step Verification** sa Google account mo.
2. Pumunta sa https://myaccount.google.com/apppasswords
3. Gumawa ng app password (pangalan: `mt5`). Kopyahin ang 16 letters.
4. Siguraduhing naka-ON ang IMAP: Gmail → ⚙️ Settings → See all settings → **Forwarding and POP/IMAP** → Enable IMAP.

## Step 5: I-setup ang config.json
Kopyahin ang `config.example.json` bilang `config.json`, tapos buksan sa Notepad:

| Setting | Ano ito |
|---|---|
| `gmail_address` | Gmail mo |
| `gmail_app_password` | yung 16-letter app password |
| `lot` | lot size ng bawat trade (hal. `0.01`) |
| `lots` | iba't ibang lot per symbol, hal. `{"XAUUSD": 0.02}` |
| `symbol_map` | pangalan sa TradingView → pangalan sa broker mo. Hal. kung `XAUUSDm` sa Exness: `{"XAUUSD": "XAUUSDm"}` |
| `symbol_suffix` | kung lahat ng symbols ng broker mo may dagdag sa dulo (hal. `"m"`, `".pro"`) |
| `default_symbol` | kung walang symbol sa alert message, ito ang gagamitin |
| `use_signal_sl_tp` | `true` = gagamitin ang SL/TP kung nasa message (hal. `SL 2640 TP 2660`) |
| `sl_points` / `tp_points` | default SL/TP sa **points** kung wala sa message (`0` = wala) |
| `close_opposite` | `true` = kapag may BUY signal, isasara muna ang open SELL (at vice versa) |
| `one_position_per_symbol` | `true` = hindi magdadagdag ng BUY kung may open BUY na |
| `max_signal_age_seconds` | hindi i-e-execute ang signal na mas luma dito (default 5 min) |
| `dry_run` | `true` = ipapakita lang ang order, hindi talaga mag-o-order |
| `allow_live` | `false` = demo lang. `true` = papayagan ang real account |

## Step 6: I-on ang Algo Trading sa MT5
Sa MT5: i-click ang **Algo Trading** button sa toolbar (dapat green ▶).
Siguraduhing nasa **Market Watch** ang symbols na gagamitin mo.

## Step 7: Patakbuhin
Double-click ang **`start.bat`**, o sa cmd:
```
cd C:\mt5-executor
python executor.py
```
Dapat lumabas:
```
MT5 OK: account 12345678 @ Broker-Demo | DEMO | balance 10000 USD
Gmail connected.
Naghihintay ng signals ...
```
Huwag isara ang cmd window habang gusto mong tumakbo. `Ctrl+C` para itigil. Ang lahat ng nangyari ay naka-save sa `executor.log`.

---

## Paano binabasa ang signal
Babasahin ng script ang subject at laman ng alert email:
- **Action**: `buy`, `long`, `bullish`, `strong buy` → BUY · `sell`, `short`, `bearish` → SELL · `close`, `exit` → isasara ang position
- **Symbol**: `OANDA:XAUUSD` na format, o kahit anong symbol na nasa `symbol_map`, o ang `default_symbol`
- **SL/TP**: `SL 2640`, `SL: 2640`, `TP 2660`, `TP1=2660`

I-test kung paano babasahin ang message ng indicator mo (walang order na mangyayari):
```
python executor.py --parse "BUY XAUUSD SL 2640 TP 2660"
```

## Alternative: gamit ang backend (Render)
Kung naka-deploy na ang TV Signals backend mo, pwede ring doon kumuha ng signals: gawing `"source": "backend"` at ilagay ang `backend_url` at `backend_secret`. Mas mabagal ito ng mga 1 minuto (dahil sa Gmail bridge), kaya `gmail` ang recommended.

## Troubleshooting
- **"Hindi maka-connect sa MT5"**: bukas at naka-login ba ang MT5? Kung marami kang MT5, ilagay ang path sa `mt5_path`, hal. `"C:\\Program Files\\MetaTrader 5\\terminal64.exe"`.
- **"walang symbol na ... sa broker mo"**: tingnan ang eksaktong pangalan sa Market Watch ng MT5 at idagdag sa `symbol_map`.
- **retcode 10027**: naka-OFF ang Algo Trading button.
- **retcode 10030 / unsupported filling**: sabihin mo lang, aayusin natin.
- **Gmail login failed**: app password ang gamitin, hindi ang normal na password mo.
