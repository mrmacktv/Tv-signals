import React, { useEffect, useState, useCallback, useRef } from "react";
import {
  SafeAreaView, FlatList, Text, View, RefreshControl, StyleSheet, StatusBar,
  TextInput, TouchableOpacity, Alert, AppState, Platform,
} from "react-native";
import AsyncStorage from "@react-native-async-storage/async-storage";
import * as Notifications from "expo-notifications";
import * as TaskManager from "expo-task-manager";
import * as BackgroundTask from "expo-background-task";
import Constants from "expo-constants";

const BG_TASK = "tv-signal-poll";
const K = { url: "cfg.url", key: "cfg.key", last: "state.lastId" };

Notifications.setNotificationHandler({
  handleNotification: async () => ({
    shouldShowBanner: true, shouldShowList: true, shouldPlaySound: true, shouldSetBadge: false,
  }),
});

async function getCfg() {
  const [url, key] = await Promise.all([AsyncStorage.getItem(K.url), AsyncStorage.getItem(K.key)]);
  return { url: (url || "").replace(/\/+$/, ""), key: key || "" };
}

async function fetchSignals(cfg) {
  const r = await fetch(`${cfg.url}/signals`, { headers: { "x-app-key": cfg.key } });
  if (!r.ok) throw new Error(`Server error ${r.status}`);
  return r.json();
}

export function titleOf(s) {
  return [s.action ? String(s.action).toUpperCase() : "SIGNAL", s.ticker, s.price ? `@ ${s.price}` : ""]
    .filter(Boolean).join(" ");
}

// Notify for signals newer than the last one we have seen (fallback when push isn't set up)
async function notifyNew(signals) {
  const last = await AsyncStorage.getItem(K.last);
  if (!signals.length) return;
  const newest = signals[0].id;
  if (last && last !== newest) {
    const fresh = [];
    for (const s of signals) { if (s.id === last) break; fresh.push(s); }
    for (const s of fresh.slice(0, 5).reverse()) {
      if (s.pushed) continue; // backend already sent a real push for this one
      await Notifications.scheduleNotificationAsync({
        content: { title: titleOf(s), body: s.message || s.indicator || "Bagong signal", sound: "default" },
        trigger: Platform.OS === "android" ? { channelId: "signals" } : null,
      });
    }
  }
  await AsyncStorage.setItem(K.last, newest);
}

TaskManager.defineTask(BG_TASK, async () => {
  try {
    const cfg = await getCfg();
    if (cfg.url) await notifyNew(await fetchSignals(cfg));
    return BackgroundTask.BackgroundTaskResult.Success;
  } catch {
    return BackgroundTask.BackgroundTaskResult.Failed;
  }
});

async function setupNotifications(cfg) {
  if (Platform.OS === "android") {
    await Notifications.setNotificationChannelAsync("signals", {
      name: "Trading signals", importance: Notifications.AndroidImportance.MAX, sound: "default",
      vibrationPattern: [0, 300, 200, 300],
    });
  }
  const { status } = await Notifications.requestPermissionsAsync();
  if (status !== "granted") return "Walang permission sa notifications";
  try { await BackgroundTask.registerTaskAsync(BG_TASK, { minimumInterval: 15 }); } catch {}
  // Instant push (needs Firebase/EAS set up). Falls back to polling if unavailable.
  try {
    const projectId = Constants.expoConfig?.extra?.eas?.projectId;
    if (!projectId) return "polling";
    const token = (await Notifications.getExpoPushTokenAsync({ projectId })).data;
    await fetch(`${cfg.url}/register`, {
      method: "POST", headers: { "x-app-key": cfg.key, "content-type": "application/json" },
      body: JSON.stringify({ token }),
    });
    return "push";
  } catch { return "polling"; }
}

function Settings({ initial, onSave }) {
  const [url, setUrl] = useState(initial.url);
  const [key, setKey] = useState(initial.key);
  const [busy, setBusy] = useState(false);
  const save = async () => {
    const cfg = { url: url.trim().replace(/\/+$/, ""), key: key.trim() };
    setBusy(true);
    try {
      await fetchSignals(cfg);
      await AsyncStorage.multiSet([[K.url, cfg.url], [K.key, cfg.key]]);
      onSave(cfg);
    } catch (e) {
      Alert.alert("Hindi maka-connect", `${e.message}\nI-check ang Server URL at Secret key.`);
    }
    setBusy(false);
  };
  return (
    <View style={{ marginTop: 8 }}>
      <Text style={s.label}>Server URL</Text>
      <TextInput style={s.input} value={url} onChangeText={setUrl} autoCapitalize="none"
        placeholder="https://your-backend.onrender.com" placeholderTextColor="#64748b" />
      <Text style={s.label}>Secret key (WEBHOOK_SECRET)</Text>
      <TextInput style={s.input} value={key} onChangeText={setKey} autoCapitalize="none"
        secureTextEntry placeholder="secret" placeholderTextColor="#64748b" />
      <TouchableOpacity style={s.btn} onPress={save} disabled={busy}>
        <Text style={s.btnText}>{busy ? "Kumokonekta..." : "I-save at i-connect"}</Text>
      </TouchableOpacity>
    </View>
  );
}

export default function App() {
  const [cfg, setCfg] = useState(null);
  const [editing, setEditing] = useState(false);
  const [signals, setSignals] = useState([]);
  const [loading, setLoading] = useState(false);
  const [mode, setMode] = useState("");
  const [err, setErr] = useState("");
  const timer = useRef(null);

  useEffect(() => { getCfg().then((c) => { setCfg(c); if (!c.url) setEditing(true); }); }, []);

  const load = useCallback(async (quiet) => {
    if (!cfg?.url) return;
    if (!quiet) setLoading(true);
    try {
      const list = await fetchSignals(cfg);
      setSignals(list); setErr("");
      await notifyNew(list);
    } catch (e) { setErr(e.message); }
    if (!quiet) setLoading(false);
  }, [cfg]);

  useEffect(() => {
    if (!cfg?.url || editing) return;
    setupNotifications(cfg).then(setMode);
    load();
    const start = () => { clearInterval(timer.current); timer.current = setInterval(() => load(true), 10000); };
    start();
    const sub = AppState.addEventListener("change", (st) => (st === "active" ? (load(true), start()) : clearInterval(timer.current)));
    const n = Notifications.addNotificationReceivedListener(() => load(true));
    return () => { clearInterval(timer.current); sub.remove(); n.remove(); };
  }, [cfg, editing, load]);

  const color = (a = "") => (/buy|long/i.test(a) ? "#16a34a" : /sell|short/i.test(a) ? "#dc2626" : "#64748b");

  if (!cfg) return <SafeAreaView style={s.root} />;

  return (
    <SafeAreaView style={s.root}>
      <StatusBar barStyle="light-content" backgroundColor="#0f172a" />
      <View style={s.header}>
        <Text style={s.h1}>TV Signals</Text>
        <TouchableOpacity onPress={() => setEditing(!editing)}>
          <Text style={s.link}>{editing ? "Isara" : "⚙ Settings"}</Text>
        </TouchableOpacity>
      </View>
      {editing ? (
        <Settings initial={cfg} onSave={(c) => { setCfg(c); setEditing(false); }} />
      ) : (
        <>
          {err ? <Text style={s.err}>⚠ {err}</Text> : null}
          {mode ? <Text style={s.muted}>{mode === "push" ? "🔔 Instant push: ON" : mode === "polling" ? "🔔 Notifications: ON (checking ng server)" : mode}</Text> : null}
          <FlatList
            data={signals}
            keyExtractor={(i) => i.id}
            refreshControl={<RefreshControl refreshing={loading} onRefresh={() => load()} />}
            ListEmptyComponent={<Text style={s.muted}>Wala pang signal. Hintayin ang unang alert mula sa TradingView.</Text>}
            renderItem={({ item }) => (
              <View style={s.card}>
                <View style={s.row}>
                  <Text style={[s.badge, { backgroundColor: color(item.action) }]}>{(item.action || "signal").toUpperCase()}</Text>
                  <Text style={s.ticker}>{item.ticker} {item.price ? `@ ${item.price}` : ""}</Text>
                </View>
                {item.indicator || item.interval ? <Text style={s.muted}>{[item.indicator, item.interval].filter(Boolean).join(" · ")}</Text> : null}
                {item.message ? <Text style={s.text}>{item.message}</Text> : null}
                {item.summary ? <Text style={s.ai}>🤖 {item.summary}</Text> : null}
                <Text style={s.time}>{new Date(item.receivedAt).toLocaleString()}</Text>
              </View>
            )}
          />
        </>
      )}
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  root: { flex: 1, backgroundColor: "#0f172a", paddingHorizontal: 16, paddingTop: StatusBar.currentHeight || 0 },
  header: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", marginVertical: 16 },
  h1: { color: "#fff", fontSize: 22, fontWeight: "700" },
  link: { color: "#93c5fd", fontSize: 15 },
  label: { color: "#cbd5e1", marginTop: 12, marginBottom: 6 },
  input: { backgroundColor: "#1e293b", color: "#fff", borderRadius: 10, padding: 12 },
  btn: { backgroundColor: "#2563eb", borderRadius: 10, padding: 14, marginTop: 20, alignItems: "center" },
  btnText: { color: "#fff", fontWeight: "700" },
  card: { backgroundColor: "#1e293b", borderRadius: 12, padding: 14, marginBottom: 10 },
  row: { flexDirection: "row", alignItems: "center", gap: 8 },
  badge: { color: "#fff", fontWeight: "700", paddingHorizontal: 8, paddingVertical: 2, borderRadius: 6, overflow: "hidden" },
  ticker: { color: "#fff", fontSize: 16, fontWeight: "600" },
  text: { color: "#e2e8f0", marginTop: 6 },
  ai: { color: "#93c5fd", marginTop: 8, fontStyle: "italic" },
  muted: { color: "#94a3b8", marginTop: 4, marginBottom: 6 },
  err: { color: "#fca5a5", marginBottom: 6 },
  time: { color: "#64748b", fontSize: 12, marginTop: 8 },
});
