// TradingView alert webhook -> store -> AI summary (optional) -> Expo push to phone
import express from "express";
import fs from "fs";

const PORT = process.env.PORT || 3000;
const SECRET = process.env.WEBHOOK_SECRET || "change-me";
const AI_KEY = process.env.ANTHROPIC_API_KEY;
const AI_MODEL = process.env.AI_MODEL || "claude-haiku-5-5";
const DB = process.env.DATA_FILE || "./data.json";

const db = fs.existsSync(DB) ? JSON.parse(fs.readFileSync(DB, "utf8")) : { signals: [], tokens: [] };
const save = () => fs.writeFileSync(DB, JSON.stringify(db, null, 2));

const app = express();
app.use(express.json());
app.use(express.text({ type: "text/*" })); // TradingView sends text/plain if message isn't valid JSON

async function aiSummary(sig) {
  if (!AI_KEY) return null;
  try {
    const r = await fetch("https://api.anthropic.com/v1/messages", {
      method: "POST",
      headers: { "x-api-key": AI_KEY, "anthropic-version": "2023-06-01", "content-type": "application/json" },
      body: JSON.stringify({
        model: AI_MODEL,
        max_tokens: 200,
        messages: [{
          role: "user",
          content: `You are a trading assistant. In 2 short sentences (Taglish ok), explain this TradingView indicator signal and what to watch out for. Not financial advice.\n\n${JSON.stringify(sig)}`,
        }],
      }),
    });
    const j = await r.json();
    return j.content?.[0]?.text ?? null;
  } catch (e) { console.error("AI error", e); return null; }
}

async function push(sig) {
  if (!db.tokens.length) return false;
  const title = `${sig.action?.toUpperCase() || "SIGNAL"} ${sig.ticker || ""} ${sig.price ? "@ " + sig.price : ""}`.trim();
  const messages = db.tokens.map((to) => ({
    to, sound: "default", title, body: sig.summary || sig.message || sig.indicator || "New TradingView signal", data: { id: sig.id },
  }));
  try {
    const r = await fetch("https://exp.host/--/api/v2/push/send", {
      method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(messages),
    });
    const j = await r.json();
    return Array.isArray(j.data) && j.data.some((t) => t.status === "ok");
  } catch (e) { console.error("push error", e); return false; }
}

// TradingView alert webhook
app.post("/webhook/:secret", async (req, res) => {
  if (req.params.secret !== SECRET) return res.sendStatus(401);
  let body = req.body;
  if (typeof body === "string") { try { body = JSON.parse(body); } catch { body = { message: body.trim() }; } }
  if (!body || typeof body !== "object") body = {};
  // Invite-only indicators often send plain text (e.g. "BUY BTCUSDT 68000"); guess action from text
  if (!body.action && body.message) {
    const m = String(body.message).match(/\b(strong buy|strong sell|buy|sell|long|short|exit|tp|sl)\b/i);
    if (m) body.action = m[1].toLowerCase();
  }
  const sig = { id: Date.now().toString() + Math.random().toString(36).slice(2, 6), receivedAt: new Date().toISOString(), ...body };
  res.sendStatus(200); // reply fast; TradingView times out after ~3s
  sig.summary = await aiSummary(sig);
  db.signals.unshift(sig); db.signals = db.signals.slice(0, 500);
  sig.pushed = await push(sig);
  save();
});

// Mobile app endpoints (protected by same secret)
const auth = (req, res, next) => (req.get("x-app-key") === SECRET ? next() : res.sendStatus(401));
app.get("/signals", auth, (req, res) => res.json(db.signals.slice(0, 100)));
app.post("/register", auth, (req, res) => {
  const { token } = req.body || {};
  if (token && !db.tokens.includes(token)) { db.tokens.push(token); save(); }
  res.json({ ok: true });
});
app.get("/", (_, res) => res.send("TV signal backend running"));
app.get("/health", (_, res) => res.json({ ok: true, signals: db.signals.length }));

app.listen(PORT, () => console.log(`Listening on :${PORT}`));
