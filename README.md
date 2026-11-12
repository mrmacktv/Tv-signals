# TV Signals: TradingView indicator alerts sa Android phone mo

```
TradingView alert (invite-only indicator mo)
   │  webhook
   ▼
Backend (Node, naka-host sa Render)
   ▼
Android app (TV Signals): listahan ng signals + notification
```

## Kailangan
- **TradingView paid plan** (Essential pataas) para sa webhook alerts
- Libreng **GitHub** account (para i-build ang APK at i-host ang backend)
- Libreng **Render** account (render.com) para sa backend

---

## Step 1: I-upload sa GitHub
Gumawa ng bagong repo (hal. `tv-signals`) at i-upload ang buong folder na ito.

## Step 2: Kunin ang APK
Sa GitHub repo: **Actions** tab → **Build Android APK** → **Run workflow**.
Pagkatapos ng mga 10–15 min, buksan ang run → i-download ang **tv-signals-apk** → i-unzip → i-install ang `app-release.apk` sa phone (payagan ang "Install unknown apps").

## Step 3: I-deploy ang backend
1. Sa render.com: **New → Blueprint** → piliin ang GitHub repo mo. Babasahin nito ang `render.yaml`.
2. Pagkatapos mag-deploy, buksan ang service → **Environment** → kopyahin ang `WEBHOOK_SECRET` (auto-generated).
3. Ang URL mo ay parang `https://tv-signal-backend-xxxx.onrender.com`. Buksan mo ito sa browser; dapat "TV signal backend running" ang lumabas.

> Note: Ang free plan ng Render ay natutulog pagkalipas ng 15 min na walang activity, at pwedeng ma-miss ang unang alert habang nagigising ito. Para hindi matulog: gumamit ng libreng uptime monitor (hal. UptimeRobot) na nagbi-bisita sa `https://YOUR-URL/health` tuwing 5 min, o mag-upgrade sa $7/month plan.

## Step 4: I-connect ang app
Buksan ang TV Signals app → **Settings** → ilagay ang Server URL at ang `WEBHOOK_SECRET` → **I-save at i-connect**. Payagan ang notifications.

## Step 5: Gumawa ng alert sa TradingView
1. Buksan ang chart na may invite-only indicator mo → **Create Alert** (⏰).
2. **Condition**: piliin ang indicator mo, tapos ang signal nito (hal. "Buy Signal") o **"Any alert() function call"**.
3. **Notifications** tab → i-check ang **Webhook URL**: `https://YOUR-URL/webhook/YOUR_WEBHOOK_SECRET`
4. **Message**: kung pwede mong i-edit (para sa mga alertcondition), gamitin ito:
   ```json
   {"ticker":"{{ticker}}","price":"{{close}}","interval":"{{interval}}","action":"buy","message":"{{ticker}} BUY signal"}
   ```
   (Gumawa ng hiwalay na alert para sa SELL, palitan ang `buy` ng `sell`.)
   Kung "Any alert() function call" ang pinili mo, ang indicator mismo ang magpapadala ng message, at lalabas ito nang buo sa app. Kusa ring nakikita ang BUY/SELL sa text.
5. **Create**. Ulitin para sa bawat chart/timeframe na gusto mong bantayan.

## Test agad (kahit walang TradingView)
```
curl -X POST https://YOUR-URL/webhook/YOUR_SECRET -H "content-type: text/plain" -d "BUY XAUUSD 2650 test"
```
Dapat lumabas sa app at may notification.

## Tungkol sa notifications
- Habang bukas ang app: tinitingnan ang server tuwing 10 segundo.
- Kapag sarado ang app: tinitingnan ng Android tuwing ~15 min (limitasyon ng Android).
- Para sa **instant** push kahit sarado ang app, kailangan ng Firebase (libre). Pwede itong idagdag sa susunod na bersyon.
- Tip: sa phone settings, i-off ang battery optimization para sa TV Signals.

## Auto-execute sa MT5 (Windows)
Gusto mong i-execute ng MT5 mo ang bawat signal? Tingnan ang [`mt5-executor/README.md`](mt5-executor/README.md).

## Optional: AI summary
Ilagay ang `ANTHROPIC_API_KEY` sa Render environment para may maikling AI paliwanag ang bawat signal.
