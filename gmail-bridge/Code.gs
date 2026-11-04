/**
 * FREE TradingView bridge: TradingView alert email -> Gmail -> TV Signals backend.
 * For TradingView free plan (no webhook). Paste into https://script.google.com
 * then run setup() once and allow access.
 */
const BACKEND_URL = "https://YOUR-URL.onrender.com"; // Render backend URL
const SECRET = "YOUR_WEBHOOK_SECRET";               // same as WEBHOOK_SECRET
const LABEL = "tv-sent";

function setup() {
  GmailApp.createLabel(LABEL);
  ScriptApp.getProjectTriggers().forEach((t) => ScriptApp.deleteTrigger(t));
  ScriptApp.newTrigger("checkAlerts").timeBased().everyMinutes(1).create();
}

function checkAlerts() {
  const label = GmailApp.getUserLabelByName(LABEL) || GmailApp.createLabel(LABEL);
  const threads = GmailApp.search(`from:noreply@tradingview.com newer_than:1d -label:${LABEL}`, 0, 20);
  threads.reverse().forEach((t) => {
    t.getMessages().forEach((m) => {
      const subject = m.getSubject();             // e.g. "Alert: BUY BTCUSDT"
      const body = m.getPlainBody().split("\n").map((l) => l.trim()).filter(Boolean).slice(0, 6).join(" ");
      UrlFetchApp.fetch(`${BACKEND_URL}/webhook/${SECRET}`, {
        method: "post",
        contentType: "text/plain",
        payload: subject.replace(/^Alert:\s*/i, "") + " | " + body,
        muteHttpExceptions: true,
      });
    });
    t.addLabel(label);
  });
}
