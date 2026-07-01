"use strict";

const {
  default: makeWASocket,
  useMultiFileAuthState,
  DisconnectReason,
  fetchLatestBaileysVersion,
} = require("@whiskeysockets/baileys");
const qrcode = require("qrcode-terminal");
const express = require("express");
const path = require("path");
const fs = require("fs");
const pino = require("pino");

// ── Config ────────────────────────────────────────────────────────────────────

const BRIDGE_PORT  = parseInt(process.env.WA_BRIDGE_PORT || "3001");
const SESSION_DIR  = process.env.SESSION_DIR || path.join(__dirname, ".baileys_auth");
const BRIDGE_SECRET = process.env.BRIDGE_SECRET || "";

// ── State ─────────────────────────────────────────────────────────────────────

let sock        = null;
let clientReady = false;
let latestQR    = null;

// ── WhatsApp connection ───────────────────────────────────────────────────────

async function connectToWhatsApp() {
  fs.mkdirSync(SESSION_DIR, { recursive: true });

  const { state, saveCreds } = await useMultiFileAuthState(SESSION_DIR);
  const { version } = await fetchLatestBaileysVersion();

  sock = makeWASocket({
    version,
    auth: state,
    logger: pino({ level: "silent" }),
    printQRInTerminal: false,
    browser: ["Binario CRM", "Chrome", "120.0.0"],
    connectTimeoutMs: 60000,
    defaultQueryTimeoutMs: 60000,
  });

  sock.ev.on("creds.update", saveCreds);

  sock.ev.on("connection.update", ({ connection, lastDisconnect, qr }) => {
    if (qr) {
      latestQR = qr;
      console.log(
        `\n[bridge] QR listo — abrí http://localhost:${BRIDGE_PORT}/qr en el browser\n`
      );
      qrcode.generate(qr, { small: true });
    }

    if (connection === "close") {
      clientReady = false;
      const statusCode = lastDisconnect?.error?.output?.statusCode;
      const loggedOut  = statusCode === DisconnectReason.loggedOut;
      console.log(
        `[bridge] Conexión cerrada (código ${statusCode}). ${loggedOut ? "Sesión cerrada — limpiando y reiniciando..." : "Reconectando..."}`
      );
      if (loggedOut) {
        try {
          fs.readdirSync(SESSION_DIR).forEach((f) =>
            fs.rmSync(path.join(SESSION_DIR, f), { recursive: true, force: true })
          );
        } catch (e) {
          console.error(`[bridge] No se pudo limpiar la sesión: ${e.message}`);
        }
      }
      setTimeout(connectToWhatsApp, 5000);
    }

    if (connection === "open") {
      clientReady = true;
      latestQR    = null;
      console.log(`[bridge] WhatsApp conectado y listo en puerto ${BRIDGE_PORT}`);
    }
  });
}

// ── Express HTTP API ──────────────────────────────────────────────────────────

const app = express();
app.use(express.json());

function requireSecret(req, res, next) {
  if (!BRIDGE_SECRET) return next();
  const sent = req.headers["x-bridge-secret"] || req.query.secret || "";
  if (sent !== BRIDGE_SECRET) return res.status(401).json({ error: "Unauthorized" });
  next();
}

app.get("/health", (_req, res) => {
  res.json({ status: clientReady ? "ready" : "not_ready", timestamp: new Date().toISOString() });
});

app.get("/qr", (_req, res) => {
  if (clientReady) {
    return res.send(`<!DOCTYPE html><html><body style="font-family:sans-serif;text-align:center;padding:3rem">
      <h2 style="color:#25D366">✅ WhatsApp conectado</h2>
      <p>El bridge está activo y listo.</p>
    </body></html>`);
  }
  if (!latestQR) {
    return res.send(`<!DOCTYPE html><html><head><meta http-equiv="refresh" content="3"></head>
      <body style="font-family:sans-serif;text-align:center;padding:3rem">
        <h2>⏳ Iniciando conexión...</h2><p>Esta página se recarga sola.</p>
      </body></html>`);
  }
  const qrData = JSON.stringify(latestQR);
  res.send(`<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8">
  <meta http-equiv="refresh" content="30">
  <title>WhatsApp QR — Binario</title>
  <style>
    body{font-family:sans-serif;text-align:center;padding:2rem;background:#f5f5f5}
    #qr{display:inline-block;padding:1rem;background:#fff;border-radius:12px;margin:1.5rem 0}
    h2{color:#1a1a1a}p{color:#555;font-size:.9rem}
  </style>
</head>
<body>
  <h2>Escanear con WhatsApp</h2>
  <p>WhatsApp → Dispositivos vinculados → Vincular dispositivo</p>
  <div id="qr"></div>
  <p>Se recarga automáticamente cada 30s</p>
  <script src="https://cdnjs.cloudflare.com/ajax/libs/qrcodejs/1.0.0/qrcode.min.js"></script>
  <script>new QRCode(document.getElementById("qr"),{text:${qrData},width:280,height:280})</script>
</body>
</html>`);
});

app.get("/profile-pic", requireSecret, async (req, res) => {
  const { phone } = req.query;
  if (!phone) return res.status(400).json({ error: "phone required" });
  if (!sock || !clientReady) return res.status(503).json({ error: "WhatsApp not connected" });

  const digits = phone.replace(/\D/g, "");
  const jid    = `${digits}@s.whatsapp.net`;

  try {
    const url = await sock.profilePictureUrl(jid, "image");
    res.json({ url });
  } catch (_) {
    res.status(404).json({ error: "no profile picture" });
  }
});

app.post("/send", requireSecret, async (req, res) => {
  const { phone, message } = req.body;
  if (!phone || !message) return res.status(400).json({ error: "phone and message required" });
  if (!sock || !clientReady) return res.status(503).json({ error: "WhatsApp not connected" });

  const digits = phone.replace(/\D/g, "");
  const jid    = `${digits}@s.whatsapp.net`;

  try {
    await sock.sendMessage(jid, { text: message });
    console.log(`[bridge] Enviado a ${phone}: ${message.slice(0, 60)}`);
    res.json({ ok: true, phone, timestamp: new Date().toISOString() });
  } catch (err) {
    console.error(`[bridge] Error al enviar: ${err.message}`);
    res.status(500).json({ error: err.message });
  }
});

app.post("/send-media", requireSecret, async (req, res) => {
  const { phone, mediaUrl, caption } = req.body;
  if (!phone || !mediaUrl) return res.status(400).json({ error: "phone and mediaUrl required" });
  if (!sock || !clientReady) return res.status(503).json({ error: "WhatsApp not connected" });

  const digits = phone.replace(/\D/g, "");
  const jid    = `${digits}@s.whatsapp.net`;

  try {
    await sock.sendMessage(jid, { image: { url: mediaUrl }, caption: caption || "" });
    res.json({ ok: true, phone });
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

// ── Start ─────────────────────────────────────────────────────────────────────

app.listen(BRIDGE_PORT, "0.0.0.0", () => {
  console.log(`[bridge] HTTP API escuchando en 0.0.0.0:${BRIDGE_PORT}`);
});

console.log("[bridge] Iniciando conexión con WhatsApp...");
connectToWhatsApp().catch(console.error);

process.on("SIGTERM", async () => { await sock?.end(); process.exit(0); });
process.on("SIGINT",  async () => { await sock?.end(); process.exit(0); });
