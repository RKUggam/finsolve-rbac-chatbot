"use strict";

const messagesEl = document.getElementById("messages");
const innerEl = document.getElementById("messages-inner");
const form = document.getElementById("chat-form");
const input = document.getElementById("chat-input");
const sendBtn = document.getElementById("send-btn");
const deptListEl = document.getElementById("dept-list");
const suggestionsEl = document.getElementById("suggestions");

// Mirrors app/rbac/policy.py so the sidebar can show access before the first query.
const ROLE_DEPARTMENTS = {
  c_level: ["finance", "marketing", "hr", "engineering", "general"],
  finance: ["finance", "general"],
  marketing: ["marketing", "general"],
  hr: ["hr", "general"],
  engineering: ["engineering", "general"],
  employee: ["general"],
};

const ROLE_SUGGESTIONS = {
  finance: [
    "By what percentage did revenue grow in 2024?",
    "What was the total vendor services spend in 2024?",
    "Summarize the main financial risks for 2024.",
  ],
  marketing: [
    "How much did new customer acquisition increase in 2024?",
    "What was the ROI of our digital campaigns?",
    "Which marketing campaign performed best in 2024?",
  ],
  hr: [
    "What fields are in the employee dataset?",
    "What is the company's leave policy?",
    "Summarize the attendance and performance data.",
  ],
  engineering: [
    "Describe FinSolve's technical architecture.",
    "What CI/CD and DevOps practices do we follow?",
    "Which compliance standards does engineering follow?",
  ],
  c_level: [
    "Summarize 2024 revenue and customer acquisition growth.",
    "What are the top financial risks this year?",
    "Give me an overview of marketing performance.",
  ],
  employee: [
    "What are FinSolve's core values?",
    "What is the leave policy?",
    "What are the standard working hours?",
  ],
};

function initials(name) {
  const parts = name.replace(/\(.*?\)/g, "").trim().split(/\s+/).filter(Boolean);
  return ((parts[0]?.[0] || "") + (parts[1]?.[0] || "")).toUpperCase() || "U";
}

function prettyRole(role) {
  return role === "c_level" ? "C-Level Executive" : role.charAt(0).toUpperCase() + role.slice(1);
}

// ---- Bootstrap: verify session, populate identity + sidebar ----
(async function init() {
  try {
    const res = await fetch("/auth/me");
    if (!res.ok) throw new Error("unauthorised");
    const me = await res.json();
    document.getElementById("user-name").textContent = me.full_name;
    document.getElementById("user-role").textContent = prettyRole(me.role);
    document.getElementById("user-avatar").textContent = initials(me.full_name);
    renderDepartments(ROLE_DEPARTMENTS[me.role] || ["general"]);
    renderSuggestions(ROLE_SUGGESTIONS[me.role] || []);
  } catch {
    window.location.href = "/";
  }
})();

function renderDepartments(depts) {
  deptListEl.innerHTML = "";
  depts.forEach((d) => {
    const tag = document.createElement("span");
    tag.className = "dept-tag";
    tag.textContent = d;
    deptListEl.appendChild(tag);
  });
}

function renderSuggestions(list) {
  suggestionsEl.innerHTML = "";
  list.forEach((q) => {
    const btn = document.createElement("button");
    btn.className = "suggestion";
    btn.textContent = q;
    btn.addEventListener("click", () => {
      input.value = q;
      input.dispatchEvent(new Event("input"));
      form.requestSubmit();
    });
    suggestionsEl.appendChild(btn);
  });
}

document.getElementById("logout-btn").addEventListener("click", async () => {
  await fetch("/auth/logout", { method: "POST" });
  window.location.href = "/";
});

// ---- Composer behaviour ----
input.addEventListener("input", () => {
  input.style.height = "auto";
  input.style.height = Math.min(input.scrollHeight, 160) + "px";
});
input.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    form.requestSubmit();
  }
});

// ---- Rendering helpers ----
function escapeHtml(s) {
  const div = document.createElement("div");
  div.textContent = s;
  return div.innerHTML;
}

// Minimal, safe markdown: escape first, then apply inline + list/paragraph formatting.
function renderMarkdown(text) {
  const esc = escapeHtml(text)
    .replace(/`([^`]+)`/g, "<code>$1</code>")
    .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
  const lines = esc.split("\n");
  let html = "";
  let inList = false;
  let listTag = "ul";
  const closeList = () => { if (inList) { html += `</${listTag}>`; inList = false; } };

  for (const raw of lines) {
    const line = raw.trim();
    if (!line) { closeList(); continue; }
    const bullet = /^[-*]\s+(.*)/.exec(line);
    const numbered = /^\d+\.\s+(.*)/.exec(line);
    if (bullet) {
      if (!inList || listTag !== "ul") { closeList(); listTag = "ul"; html += "<ul>"; inList = true; }
      html += `<li>${bullet[1]}</li>`;
    } else if (numbered) {
      if (!inList || listTag !== "ol") { closeList(); listTag = "ol"; html += "<ol>"; inList = true; }
      html += `<li>${numbered[1]}</li>`;
    } else {
      closeList();
      html += `<p>${line}</p>`;
    }
  }
  closeList();
  return html;
}

function timeNow() {
  return new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

function scrollToBottom() {
  messagesEl.scrollTop = messagesEl.scrollHeight;
}

function addMessage(role, text, { markdown = false, blocked = false } = {}) {
  const wrap = document.createElement("div");
  wrap.className = `msg ${role} ${blocked ? "blocked" : ""}`.trim();

  const avatar = document.createElement("div");
  avatar.className = `avatar ${role}`;
  avatar.textContent = role === "assistant" ? "FS" : (document.getElementById("user-avatar").textContent || "U");

  const content = document.createElement("div");
  content.className = "msg-content";
  const bubble = document.createElement("div");
  bubble.className = "bubble";
  bubble.innerHTML = markdown ? renderMarkdown(text) : `<p>${escapeHtml(text)}</p>`;
  content.appendChild(bubble);

  wrap.appendChild(avatar);
  wrap.appendChild(content);
  innerEl.appendChild(wrap);
  scrollToBottom();
  return { wrap, content, bubble };
}

function addTyping() {
  const wrap = document.createElement("div");
  wrap.className = "msg assistant typing";
  wrap.innerHTML =
    `<div class="avatar assistant">FS</div>` +
    `<div class="msg-content"><div class="bubble"><span class="dot"></span><span class="dot"></span><span class="dot"></span></div></div>`;
  innerEl.appendChild(wrap);
  scrollToBottom();
  return wrap;
}

function addMetaRow(content, usage) {
  const row = document.createElement("div");
  row.className = "meta-row";
  const ts = document.createElement("span");
  ts.className = "timestamp";
  ts.textContent = timeNow();
  row.appendChild(ts);
  if (usage && usage.total_tokens) {
    const u = document.createElement("span");
    u.className = "usage";
    u.textContent = `${usage.total_tokens} tokens · $${usage.cost_usd.toFixed(5)}`;
    row.appendChild(u);
  }
  content.appendChild(row);
}

function addCitations(content, citations) {
  if (!citations || citations.length === 0) return;
  const box = document.createElement("div");
  box.className = "citations";
  const details = document.createElement("details");
  const summary = document.createElement("summary");
  summary.textContent = `Sources (${citations.length})`;
  details.appendChild(summary);
  citations.forEach((c) => {
    const item = document.createElement("div");
    item.className = "cite";
    item.innerHTML =
      `<div class="cite-head">${escapeHtml(c.title)}` +
      `<span class="cite-dept">${escapeHtml(c.department)} · ${escapeHtml(c.source)}</span></div>` +
      `<div class="cite-snip">${escapeHtml(c.snippet)}</div>`;
    details.appendChild(item);
  });
  box.appendChild(details);
  content.appendChild(box);
}

// ---- Submit ----
form.addEventListener("submit", async (e) => {
  e.preventDefault();
  const message = input.value.trim();
  if (!message) return;

  addMessage("user", message);
  const userContent = innerEl.lastChild.querySelector(".msg-content");
  addMetaRow(userContent, null);

  input.value = "";
  input.style.height = "auto";
  sendBtn.disabled = true;
  const typing = addTyping();

  try {
    const res = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message }),
    });
    if (res.status === 401) { window.location.href = "/"; return; }
    const data = await res.json();
    typing.remove();

    if (!res.ok) {
      addMessage("assistant", data.detail || "Something went wrong.", { blocked: true });
      return;
    }

    if (data.accessible_departments) renderDepartments(data.accessible_departments);

    const { content } = addMessage("assistant", data.answer, {
      markdown: !data.blocked,
      blocked: data.blocked,
    });
    addCitations(content, data.citations);
    addMetaRow(content, data.usage);
  } catch (err) {
    typing.remove();
    addMessage("assistant", "Network error: " + err.message, { blocked: true });
  } finally {
    sendBtn.disabled = false;
    input.focus();
  }
});
