"use strict";

const state = {
  baseUrl: sessionStorage.getItem("anythingllm.baseUrl") || "http://localhost:3001/api",
  apiKey: sessionStorage.getItem("anythingllm.apiKey") || "",
  workspaces: [],
  slug: "",
  sessionId: null,
  busy: false,
};

const $ = (id) => document.getElementById(id);

function setConnection(stateName, text) {
  const pill = $("connectionState");
  pill.dataset.state = stateName;
  pill.textContent = text;
}

function setStatus(id, stateName, text) {
  const node = $(id);
  node.dataset.state = stateName;
  node.textContent = text;
}

function normalizeBase(value) {
  return value.trim().replace(/\/+$/, "");
}

async function api(path, options = {}) {
  if (!state.apiKey) throw new Error("请先填写 API Key");
  if (!state.baseUrl) throw new Error("请先填写 API 地址");

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 60000);
  const headers = {
    Accept: "application/json",
    Authorization: `Bearer ${state.apiKey}`,
  };
  const init = { ...options, headers, signal: controller.signal };
  if (options.body && !(options.body instanceof FormData)) {
    headers["Content-Type"] = "application/json";
  }

  let response;
  try {
    response = await fetch(`${state.baseUrl}${path}`, init);
  } catch (error) {
    if (error.name === "AbortError") throw new Error("请求超时（60 秒）");
    throw new Error(`无法连接 AnythingLLM：${error.message}`);
  } finally {
    clearTimeout(timer);
  }

  const text = await response.text();
  let data = null;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    data = null;
  }

  if (!response.ok) {
    const message =
      (data && (data.error || data.message || data.detail)) ||
      text.slice(0, 300) ||
      `HTTP ${response.status}`;
    const error = new Error(
      response.status === 403 || response.status === 401
        ? `鉴权失败：${message}（请检查 API Key）`
        : message
    );
    error.status = response.status;
    throw error;
  }
  return data;
}

function renderWorkspaces(workspaces) {
  const select = $("workspaceSelect");
  select.replaceChildren();
  if (!workspaces.length) {
    const option = document.createElement("option");
    option.value = "";
    option.textContent = "没有工作区";
    select.append(option);
    select.disabled = true;
    $("workspaceMeta").textContent = "AnythingLLM 中还没有工作区。";
    return;
  }

  for (const workspace of workspaces) {
    const option = document.createElement("option");
    option.value = workspace.slug || workspace.name || "";
    option.textContent = `${workspace.name || workspace.slug}（${workspace.slug || "no-slug"}）`;
    select.append(option);
  }
  select.disabled = false;
  state.slug = select.value;
  select.dispatchEvent(new Event("change"));
}

async function connect() {
  state.baseUrl = normalizeBase($("baseUrl").value);
  state.apiKey = $("apiKey").value.trim();
  if (!state.apiKey) {
    setStatus("chatStatus", "error", "请填写 API Key。");
    return;
  }

  setConnection("loading", "连接中…");
  $("connectBtn").disabled = true;
  try {
    const data = await api("/v1/workspaces");
    state.workspaces = Array.isArray(data?.workspaces)
      ? data.workspaces
      : Array.isArray(data)
        ? data
        : [];
    sessionStorage.setItem("anythingllm.baseUrl", state.baseUrl);
    sessionStorage.setItem("anythingllm.apiKey", state.apiKey);
    renderWorkspaces(state.workspaces);
    setConnection("ok", `已连接 · ${state.workspaces.length} 个工作区`);
    $("refreshBtn").disabled = false;
    $("uploadBtn").disabled = false;
    setStatus("chatStatus", "ok", "连接成功，可以开始提问。");
  } catch (error) {
    setConnection("error", "连接失败");
    setStatus("chatStatus", "error", error.message);
    $("workspaceSelect").disabled = true;
  } finally {
    $("connectBtn").disabled = false;
  }
}

async function refreshWorkspaces() {
  if (!state.apiKey) return;
  setConnection("loading", "刷新中…");
  try {
    const data = await api("/v1/workspaces");
    state.workspaces = Array.isArray(data?.workspaces)
      ? data.workspaces
      : Array.isArray(data)
        ? data
        : [];
    renderWorkspaces(state.workspaces);
    setConnection("ok", `已连接 · ${state.workspaces.length} 个工作区`);
  } catch (error) {
    setConnection("error", "刷新失败");
    setStatus("chatStatus", "error", error.message);
  }
}

function onWorkspaceChange() {
  state.slug = $("workspaceSelect").value;
  state.sessionId = null;
  const workspace = state.workspaces.find(
    (item) => (item.slug || item.name) === state.slug
  );
  const count = Array.isArray(workspace?.documents)
    ? workspace.documents.length
    : 0;
  $("workspaceMeta").textContent = state.slug
    ? `slug：${state.slug} · 已挂载文档：${count}`
    : "尚未选择工作区。";
}

function appendMessage(role, text, sources = []) {
  const node = document.createElement("div");
  node.className = `msg ${role}`;
  node.textContent = text;
  if (sources.length) {
    const box = document.createElement("div");
    box.className = "sources";
    for (const source of sources.slice(0, 5)) {
      const item = document.createElement("div");
      item.className = "source";
      const title = source.title || source.name || "引用片段";
      const chunk = source.chunk || source.text || "";
      item.textContent = `${title}${chunk ? `：${String(chunk).slice(0, 300)}` : ""}`;
      box.append(item);
    }
    node.append(box);
  }
  const messages = $("messages");
  messages.append(node);
  messages.scrollTop = messages.scrollHeight;
}

async function sendQuestion(event) {
  event.preventDefault();
  if (state.busy) return;
  const question = $("question").value.trim();
  if (!question) return;
  if (!state.slug) {
    setStatus("chatStatus", "error", "请先连接并选择工作区。");
    return;
  }

  state.busy = true;
  $("sendBtn").disabled = true;
  $("question").value = "";
  appendMessage("user", question);
  setStatus("chatStatus", "loading", "正在等待 AnythingLLM 回答…");

  const mode = $("modeSelect").value;
  const payload = { message: question, mode };
  if (mode === "chat" && state.sessionId) payload.sessionId = state.sessionId;

  try {
    const data = await api(`/v1/workspace/${encodeURIComponent(state.slug)}/chat`, {
      method: "POST",
      body: JSON.stringify(payload),
    });
    const answer =
      data?.textResponse || data?.response || data?.answer || "（没有返回文本）";
    appendMessage("assistant", answer, data?.sources || []);
    if (mode === "chat" && data?.id) state.sessionId = data.id;
    setStatus("chatStatus", "ok", "回答完成。");
  } catch (error) {
    appendMessage("error", error.message);
    setStatus("chatStatus", "error", error.message);
  } finally {
    state.busy = false;
    $("sendBtn").disabled = false;
  }
}

async function uploadDocument(event) {
  event.preventDefault();
  const file = $("fileInput").files?.[0];
  if (!file) return;
  if (!state.slug) {
    setStatus("uploadStatus", "error", "请先连接并选择工作区。");
    return;
  }

  $("uploadBtn").disabled = true;
  setStatus("uploadStatus", "loading", `正在上传 ${file.name}…`);
  try {
    const form = new FormData();
    form.append("file", file);
    const uploaded = await api("/v1/document/upload", {
      method: "POST",
      body: form,
    });
    const documents = uploaded?.documents || [];
    const location =
      (documents[0] && (documents[0].location || documents[0].name)) ||
      uploaded?.location ||
      uploaded?.name ||
      "";
    if (!location) throw new Error("上传成功但未返回文档 location。");

    setStatus("uploadStatus", "loading", "正在加入工作区并向量化…");
    await api(`/v1/workspace/${encodeURIComponent(state.slug)}/update-embeddings`, {
      method: "POST",
      body: JSON.stringify({ adds: [location], deletes: [] }),
    });
    setStatus("uploadStatus", "ok", `已上传并加入工作区：${location}`);
    $("fileInput").value = "";
    await refreshWorkspaces();
  } catch (error) {
    setStatus("uploadStatus", "error", error.message);
  } finally {
    $("uploadBtn").disabled = false;
  }
}

function disconnect() {
  state.apiKey = "";
  state.workspaces = [];
  state.slug = "";
  state.sessionId = null;
  sessionStorage.removeItem("anythingllm.apiKey");
  $("apiKey").value = "";
  $("workspaceSelect").replaceChildren();
  $("workspaceSelect").disabled = true;
  $("workspaceMeta").textContent = "已清除密钥。";
  $("messages").replaceChildren();
  $("refreshBtn").disabled = true;
  $("uploadBtn").disabled = true;
  setConnection("idle", "未连接");
  setStatus("chatStatus", "ok", "已断开。");
}

function boot() {
  $("baseUrl").value = state.baseUrl;
  $("apiKey").value = state.apiKey;
  $("connectBtn").addEventListener("click", connect);
  $("disconnectBtn").addEventListener("click", disconnect);
  $("refreshBtn").addEventListener("click", refreshWorkspaces);
  $("workspaceSelect").addEventListener("change", onWorkspaceChange);
  $("chatForm").addEventListener("submit", sendQuestion);
  $("uploadForm").addEventListener("submit", uploadDocument);

  if (state.apiKey) {
    connect();
  }
}

boot();
