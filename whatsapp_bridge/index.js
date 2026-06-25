/**
 * WhatsApp Bridge — Node.js
 *
 * Responsibilities:
 *   - Maintain WhatsApp Web session via whatsapp-web.js
 *   - Capture incoming messages
 *   - Forward structured events to Python message handler via HTTP
 *   - Expose a local HTTP API for Python to send messages through
 *   - Handle reconnection automatically
 *
 * Python sends messages → POST /send
 * Node sends events    → POST http://localhost:3002/wa-event
 */

"use strict";

const { Client, LocalAuth, MessageMedia } = require("whatsapp-web.js");
const qrcode = require("qrcode-terminal");
const express = require("express");
const axios = require("axios");
const path = require("path");
const fs = require("fs");

// ── Config ────────────────────────────────────────────────────────────────────

const BRIDGE_PORT = parseInt(process.env.WA_BRIDGE_PORT || "3001");
const PYTHON_EVENTS_URL =
  process.env.PYTHON_EVENTS_URL ||
  `http://localhost:${parseInt(process.env.WA_EVENTS_PORT || "3002")}/wa-event`;

const SESSION_DIR = path.join(__dirname, ".wwebjs_auth");

// ── WhatsApp Client ───────────────────────────────────────────────────────────

const client = new Client({
  authStrategy: new LocalAuth({
    dataPath: SESSION_DIR,
    clientId: "leadgen-rosario",
  }),
  puppeteer: {
    headless: true,
    args: [
      "--no-sandbox",
      "--disable-setuid-sandbox",
      "--disable-dev-shm-usage",
      "--disable-accelerated-2d-canvas",
      "--no-first-run",
      "--no-zygote",
      "--disable-gpu",
    ],
  },
  webVersionCache: {
    type: "remote",
    remotePath:
      "https://raw.githubusercontent.com/wppconnect-team/wa-version/main/html/2.2412.54.html",
  },
});

let clientReady = false;

// ── Event forwarding ──────────────────────────────────────────────────────────

async function forwardToPython(event) {
  try {
    await axios.post(PYTHON_EVENTS_URL, event, {
      timeout: 5000,
      headers: { "Content-Type": "application/json" },
    });
  } catch (err) {
    // Python may not be running — log and continue
    console.error(
      `[bridge] Could not forward event to Python: ${err.message}`
    );
  }
}

// ── WhatsApp event handlers ───────────────────────────────────────────────────

client.on("qr", (qr) => {
  console.log("\n[bridge] Scan QR code with WhatsApp:\n");
  qrcode.generate(qr, { small: true });
});

client.on("authenticated", () => {
  console.log("[bridge] Session authenticated");
});

client.on("ready", () => {
  clientReady = true;
  console.log(`[bridge] WhatsApp client ready. Listening on port ${BRIDGE_PORT}`);
  forwardToPython({ type: "ready", timestamp: new Date().toISOString() });
});

client.on("disconnected", (reason) => {
  clientReady = false;
  console.warn(`[bridge] Disconnected: ${reason}. Restarting...`);
  forwardToPython({
    type: "disconnected",
    reason,
    timestamp: new Date().toISOString(),
  });
  setTimeout(() => client.initialize(), 5000);
});

client.on("auth_failure", (msg) => {
  clientReady = false;
  console.error(`[bridge] Auth failure: ${msg}`);
  forwardToPython({
    type: "auth_failure",
    message: msg,
    timestamp: new Date().toISOString(),
  });
});

client.on("message", async (message) => {
  // Only forward messages from contacts (not from ourselves)
  if (message.fromMe) return;

  const chat = await message.getChat().catch(() => null);
  const contact = await message.getContact().catch(() => null);

  const event = {
    type: "message",
    phone: message.from.replace("@c.us", "").replace("@g.us", ""),
    message: message.body || "",
    timestamp: new Date(message.timestamp * 1000).toISOString(),
    chat_id: message.from,
    is_group: chat?.isGroup || false,
    contact_name: contact?.pushname || contact?.name || "",
    has_media: message.hasMedia || false,
    message_type: message.type,
  };

  // Skip group messages — we only care about direct replies
  if (event.is_group) return;

  console.log(
    `[bridge] Message from ${event.phone}: ${event.message.slice(0, 60)}`
  );

  await forwardToPython(event);
});

client.on("message_reaction", async (reaction) => {
  const event = {
    type: "reaction",
    phone: reaction.senderId.replace("@c.us", ""),
    reaction: reaction.reaction,
    timestamp: new Date().toISOString(),
    message_id: reaction.msgId?._serialized || "",
  };

  console.log(`[bridge] Reaction from ${event.phone}: ${event.reaction}`);
  await forwardToPython(event);
});

// ── Express HTTP API (for Python to send messages) ────────────────────────────

const app = express();
app.use(express.json());

app.get("/health", (_req, res) => {
  res.json({ status: clientReady ? "ready" : "not_ready", timestamp: new Date().toISOString() });
});

/**
 * POST /send
 * Body: { phone: "5493415109798", message: "Hola!" }
 * Sends a WhatsApp message through the active session.
 */
app.post("/send", async (req, res) => {
  const { phone, message } = req.body;

  if (!phone || !message) {
    return res.status(400).json({ error: "phone and message required" });
  }

  if (!clientReady) {
    return res.status(503).json({ error: "WhatsApp client not ready" });
  }

  // Normalize number to WhatsApp chat ID
  const digits = phone.replace(/\D/g, "");
  const chatId = digits.includes("@") ? digits : `${digits}@c.us`;

  try {
    await client.sendMessage(chatId, message);
    console.log(`[bridge] Sent to ${phone}: ${message.slice(0, 60)}`);
    res.json({ ok: true, phone, timestamp: new Date().toISOString() });
  } catch (err) {
    console.error(`[bridge] Send error: ${err.message}`);
    res.status(500).json({ error: err.message });
  }
});

/**
 * POST /send-media
 * Body: { phone, mediaUrl, caption }
 * Sends a media message (image/file).
 */
app.post("/send-media", async (req, res) => {
  const { phone, mediaUrl, caption } = req.body;

  if (!phone || !mediaUrl) {
    return res.status(400).json({ error: "phone and mediaUrl required" });
  }

  if (!clientReady) {
    return res.status(503).json({ error: "WhatsApp client not ready" });
  }

  const digits = phone.replace(/\D/g, "");
  const chatId = `${digits}@c.us`;

  try {
    const media = await MessageMedia.fromUrl(mediaUrl, { unsafeMime: true });
    await client.sendMessage(chatId, media, { caption: caption || "" });
    res.json({ ok: true, phone });
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

// ── Start ─────────────────────────────────────────────────────────────────────

app.listen(BRIDGE_PORT, () => {
  console.log(`[bridge] HTTP API listening on http://localhost:${BRIDGE_PORT}`);
});

console.log("[bridge] Initializing WhatsApp client...");
client.initialize();

process.on("SIGTERM", async () => {
  console.log("[bridge] SIGTERM received, shutting down...");
  await client.destroy();
  process.exit(0);
});

process.on("SIGINT", async () => {
  console.log("[bridge] SIGINT received, shutting down...");
  await client.destroy();
  process.exit(0);
});
