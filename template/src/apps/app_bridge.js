// Shared host bridge for MCP Apps (ext-apps 2026-01-26): JSON-RPC 2.0 over
// window.parent.postMessage. Python inlines this file into each app's HTML at the
// bridge placeholder (see src/apps/loader.py), so the app stays self-contained
// (the default CSP allows inline script and no network).
//
//   McpApp.connect({ appInfo, onFail })        handshake; the host sends nothing before it
//   McpApp.onNotification(method, fn)          e.g. "ui/notifications/tool-result"
//   McpApp.onRequest(method, fn)               host -> app requests; return the result
//   McpApp.onTeardown(fn)                      stop timers here; the bridge replies {}
//   McpApp.callTool(name, args)                tools/call through the host
//   McpApp.sendMessage(text)                   ui/message; call only from a user click
//   McpApp.openLink(url)                       ui/open-link, falling back to a new tab
//   McpApp.request / notify / applyHostContext / reportSize
(() => {
  "use strict";

  const PROTOCOL_VERSION = "2026-01-26";
  const pending = new Map();
  const notificationHandlers = {};
  const requestHandlers = {};
  const teardownHooks = [];
  let nextId = 1;

  function post(msg) { window.parent.postMessage(msg, "*"); }

  window.addEventListener("message", (event) => {
    if (event.source !== window.parent) return;
    const msg = event.data;
    if (!msg || msg.jsonrpc !== "2.0") return;

    // Response to one of our requests
    if (msg.method === undefined && msg.id !== undefined) {
      const p = pending.get(msg.id);
      if (!p) return;
      pending.delete(msg.id);
      clearTimeout(p.timer);
      if (msg.error) p.reject(new Error(msg.error.message || "Host error"));
      else p.resolve(msg.result);
      return;
    }

    // Request from the host
    if (msg.id !== undefined) {
      const handler = requestHandlers[msg.method];
      Promise.resolve(handler ? handler(msg.params || {}) : Promise.reject({ code: -32601, message: "Method not found" }))
        .then((result) => post({ jsonrpc: "2.0", id: msg.id, result: result || {} }))
        .catch((e) => post({ jsonrpc: "2.0", id: msg.id, error: { code: e.code || -32603, message: e.message || String(e) } }));
      return;
    }

    // Notification from the host
    const handler = notificationHandlers[msg.method];
    if (handler) handler(msg.params || {});
  });

  function request(method, params, timeoutMs = 120000) {
    const id = nextId++;
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => {
        pending.delete(id);
        reject(new Error("Timed out waiting for the host (" + method + ")"));
      }, timeoutMs);
      pending.set(id, { resolve, reject, timer });
      post({ jsonrpc: "2.0", id, method, params });
    });
  }

  function notify(method, params) { post({ jsonrpc: "2.0", method, params }); }

  // Call a tool through the host. Unwraps: isError -> throw the text; a
  // structuredContent holding only "result" -> that value; otherwise the
  // structuredContent; finally JSON.parse of the text, or the text itself.
  async function callTool(name, args) {
    const res = await request("tools/call", { name, arguments: args || {} });
    const text = (res.content || []).filter((c) => c.type === "text").map((c) => c.text).join("\n");
    if (res.isError) throw new Error(text || ("Error calling " + name));
    const sc = res.structuredContent;
    if (sc !== undefined && sc !== null) return ("result" in sc && Object.keys(sc).length === 1) ? sc.result : sc;
    try { return JSON.parse(text); } catch (_) { return text; }
  }

  // The spec defines content as one object, but some hosts expect an array:
  // send the object first and retry once with an array if the host rejects it.
  async function sendMessage(text) {
    try {
      await request("ui/message", { role: "user", content: { type: "text", text } });
    } catch (_) {
      await request("ui/message", { role: "user", content: [{ type: "text", text }] });
    }
  }

  function openLink(url) {
    request("ui/open-link", { url }).catch(() => { window.open(url, "_blank", "noopener"); });
  }

  function applyHostContext(ctx) {
    if (!ctx) return;
    if (ctx.theme) document.documentElement.dataset.theme = ctx.theme;
    const vars = ctx.styles && ctx.styles.variables;
    if (vars) for (const [k, v] of Object.entries(vars)) if (v) document.documentElement.style.setProperty(k, v);
    const fonts = ctx.styles && ctx.styles.css && ctx.styles.css.fonts;
    if (fonts && !document.getElementById("host-fonts")) {
      const style = document.createElement("style");
      style.id = "host-fonts";
      style.textContent = fonts;
      document.head.appendChild(style);
    }
  }

  // Report content size so the host can size the iframe.
  let lastSize = "";
  let sizeTimer = null;
  function reportSize() {
    clearTimeout(sizeTimer);
    sizeTimer = setTimeout(() => {
      // Measure the body, not documentElement: documentElement.scrollHeight never
      // drops below the iframe's current height, so the card could only grow.
      const rect = document.body.getBoundingClientRect();
      const width = Math.ceil(rect.width);
      const height = Math.ceil(rect.height);
      const key = width + "x" + height;
      if (key === lastSize) return;
      lastSize = key;
      notify("ui/notifications/size-changed", { width, height });
    }, 50);
  }
  new ResizeObserver(reportSize).observe(document.body);

  notificationHandlers["ui/notifications/host-context-changed"] = applyHostContext;
  requestHandlers["ping"] = () => ({});
  requestHandlers["ui/resource-teardown"] = () => {
    clearTimeout(sizeTimer);
    teardownHooks.forEach((fn) => { try { fn(); } catch (_) { /* keep tearing down */ } });
    return {};
  };

  function connect({ appInfo, onFail }) {
    return request("ui/initialize", {
      protocolVersion: PROTOCOL_VERSION,
      appInfo,
      appCapabilities: {},
    }, 10000).then((result) => {
      applyHostContext(result && result.hostContext);
      notify("ui/notifications/initialized", {});
    }).catch((e) => { if (onFail) onFail(e); });
  }

  window.McpApp = {
    request,
    notify,
    callTool,
    sendMessage,
    openLink,
    applyHostContext,
    reportSize,
    connect,
    onNotification(method, fn) { notificationHandlers[method] = fn; },
    onRequest(method, fn) { requestHandlers[method] = fn; },
    onTeardown(fn) { teardownHooks.push(fn); },
  };
})();
