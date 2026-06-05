// ═══════════════════════════════════════════════════════════
// 招股说明书智能问答 — 极简风格 JS + PDF管理
// ═══════════════════════════════════════════════════════════

// ── i18n ───────────────────────────────────────────────────
const i18n = {
  zh: {
    pageTitle: "招股说明书智能问答",
    appTitle: "招股说明书智能问答",
    welcomeTitle: "招股说明书智能问答",
    welcomeDesc: "基于 RAG 技术，智能解析招股说明书，精准回答您的问题",
    sug1: "公司的主营业务是什么？",
    sug2: "公司面临的主要风险因素有哪些？",
    sug3: "公司最近三年的营业收入是多少？",
    sug4: "公司的发展战略和未来规划是什么？",
    inputPlaceholder: "输入您的问题...",
    inputHint: "按 Enter 发送，Shift+Enter 换行",
    newChat: "新对话",
    historyLabel: "历史记录",
    clearHistory: "清空记录",
    pdfManage: "文档管理",
    pdfModalTitle: "文档管理",
    pdfListTitle: "已上传文档",
    pdfActiveHint: "勾选的文档将参与检索问答",
    rebuildIndex: "重建索引",
    uploadHint: "拖放 PDF 到此处，或点击选择",
    selectPdfBtn: "选择文件",
    confidence: "置信度",
    sourcesTitle: "参考来源",
    refPrefix: "参考",
    pageLabel: "第",
    pageSuffix: "页",
    similarityLabel: "相似度",
    copyBtn: "复制",
    copiedBtn: "已复制",
    retryBtn: "重试",
    thumbUp: "有帮助",
    thumbDown: "无帮助",
    toastCopied: "已复制到剪贴板",
    toastMicPerm: "请允许麦克风权限",
    toastNoSpeech: "未检测到语音，请重试",
    toastSttError: "语音识别出错，请重试",
    toastSttFail: "启动语音识别失败",
    toastNoVoice: "未识别到有效语音",
    toastSttUnavailable: "浏览器不支持语音输入",
    toastSttConnFail: "语音识别服务连接失败",
    toastNetworkError: "网络错误，请检查后端服务",
    toastRequestFail: "请求失败，请稍后重试",
    toastHistoryCleared: "历史记录已清空",
    toastPdfUploaded: "PDF 上传成功",
    toastPdfDeleted: "文件已删除",
    toastIndexRebuilt: "索引重建完成",
    toastActiveUpdated: "检索范围已更新",
    confirmDelete: "确定删除此文件？",
    confirmRebuild: "确定重建索引？这可能需要一些时间。",
    rebuilding: "正在重建索引，请稍候...",
    imageAnalyzing: "正在分析图片...",
    imageAnalysisDone: "图片分析完成",
    imageUploadSuccess: "图片上传成功",
    imageError: "图片分析失败",
    imageNotConfigured: "图片处理服务未配置",
    imageTooLarge: "图片文件过大",
    imageUnsupported: "不支持的图片格式",
    ragMode: "知识库模式",
    ragModeRAG: "传统 RAG",
    ragModeLightRAG: "LightRAG (图增强)",
    toastRagModeSwitched: "已切换到 {mode} 模式",
  },
  en: {
    pageTitle: "Prospectus Q&A",
    appTitle: "Prospectus Q&A",
    welcomeTitle: "Prospectus Q&A Assistant",
    welcomeDesc: "RAG-powered intelligent Q&A for prospectus documents",
    sug1: "What is the company's main business?",
    sug2: "What are the main risk factors?",
    sug3: "What is the revenue for the last three years?",
    sug4: "What is the company's development strategy?",
    inputPlaceholder: "Type your question...",
    inputHint: "Press Enter to send, Shift+Enter for new line",
    newChat: "New Chat",
    historyLabel: "History",
    clearHistory: "Clear History",
    pdfManage: "Documents",
    pdfModalTitle: "Document Management",
    pdfListTitle: "Uploaded Documents",
    pdfActiveHint: "Checked documents will be used for Q&A",
    rebuildIndex: "Rebuild Index",
    uploadHint: "Drag & drop PDF here, or click to select",
    selectPdfBtn: "Select File",
    confidence: "Confidence",
    sourcesTitle: "References",
    refPrefix: "Ref",
    pageLabel: "P.",
    pageSuffix: "",
    similarityLabel: "Similarity",
    copyBtn: "Copy",
    copiedBtn: "Copied",
    retryBtn: "Retry",
    thumbUp: "Helpful",
    thumbDown: "Not helpful",
    toastCopied: "Copied to clipboard",
    toastMicPerm: "Please allow microphone permission",
    toastNoSpeech: "No speech detected, please retry",
    toastSttError: "Speech recognition error",
    toastSttFail: "Failed to start speech recognition",
    toastNoVoice: "No valid speech recognized",
    toastSttUnavailable: "Browser does not support voice input",
    toastSttConnFail: "Speech recognition service connection failed",
    toastNetworkError: "Network error, please check backend",
    toastRequestFail: "Request failed, please retry later",
    toastHistoryCleared: "History cleared",
    toastPdfUploaded: "PDF uploaded successfully",
    toastPdfDeleted: "File deleted",
    toastIndexRebuilt: "Index rebuilt",
    toastActiveUpdated: "Search scope updated",
    confirmDelete: "Delete this file?",
    confirmRebuild: "Rebuild index? This may take a while.",
    rebuilding: "Rebuilding index, please wait...",
    imageAnalyzing: "Analyzing image...",
    imageAnalysisDone: "Image analysis complete",
    imageUploadSuccess: "Image uploaded",
    imageError: "Image analysis failed",
    imageNotConfigured: "Image service not configured",
    imageTooLarge: "Image file too large",
    imageUnsupported: "Unsupported image format",
    ragMode: "Knowledge Base",
    ragModeRAG: "Traditional RAG",
    ragModeLightRAG: "LightRAG (Graph-enhanced)",
    toastRagModeSwitched: "Switched to {mode} mode",
  },
};

let currentLang = localStorage.getItem("lang") || "zh";

function t(key) {
  return (i18n[currentLang] && i18n[currentLang][key]) || (i18n.zh[key]) || key;
}

function applyI18n() {
  document.documentElement.lang = currentLang === "zh" ? "zh-CN" : "en";
  document.title = t("pageTitle");

  document.querySelectorAll("[data-i18n]").forEach((el) => {
    const key = el.getAttribute("data-i18n");
    if (key && i18n[currentLang][key] !== undefined) {
      el.innerHTML = i18n[currentLang][key];
    }
  });

  document.querySelectorAll("[data-i18n-placeholder]").forEach((el) => {
    const key = el.getAttribute("data-i18n-placeholder");
    if (key && i18n[currentLang][key] !== undefined) {
      el.placeholder = i18n[currentLang][key];
    }
  });

  if (recognition) recognition.lang = currentLang === "zh" ? "zh-CN" : "en-US";

  const langLabel = document.getElementById("langLabel");
  if (langLabel) langLabel.textContent = currentLang === "zh" ? "English" : "中文";

  document.querySelectorAll(".suggestion").forEach((btn) => {
    const qAttr = currentLang === "zh" ? "data-query-zh" : "data-query-en";
    const query = btn.getAttribute(qAttr);
    if (query) btn.dataset.query = query;
  });
}

function switchLang() {
  currentLang = currentLang === "zh" ? "en" : "zh";
  localStorage.setItem("lang", currentLang);
  applyI18n();
}

// ── DOM ────────────────────────────────────────────────────
const chatArea = document.getElementById("chatArea");
const inputEl = document.getElementById("queryInput");
const sendBtn = document.getElementById("sendBtn");
const toastEl = document.getElementById("toast");
const voiceBtn = document.getElementById("voiceBtn");
const inputWrap = document.getElementById("inputWrap");
const menuBtn = document.getElementById("menuBtn");
const sidebar = document.getElementById("sidebar");
const newChatBtn = document.getElementById("newChatBtn");
const clearHistoryBtn = document.getElementById("clearHistoryBtn");
const langSwitchBtn = document.getElementById("langSwitchBtn");
const welcomeScreen = document.getElementById("welcomeScreen");
const pdfManageBtn = document.getElementById("pdfManageBtn");
const pdfModal = document.getElementById("pdfModal");
const pdfModalClose = document.getElementById("pdfModalClose");
const pdfDropzone = document.getElementById("pdfDropzone");
const selectPdfBtn = document.getElementById("selectPdfBtn");
const pdfFileInput = document.getElementById("pdfFileInput");
const uploadProgress = document.getElementById("uploadProgress");
const uploadProgressText = document.getElementById("uploadProgressText");
const pdfList = document.getElementById("pdfList");
const rebuildBtn = document.getElementById("rebuildBtn");
const pdfBadge = document.getElementById("pdfBadge");
const pdfBadgeText = document.getElementById("pdfBadgeText");
const retrievalModeWrap = document.getElementById("retrievalModeWrap");
let currentRetrievalMode = localStorage.getItem("retrievalMode") || "hybrid";
let currentRagMode = localStorage.getItem("ragMode") || "rag";

let isLoading = false;
let chatHistory = JSON.parse(localStorage.getItem("chatHistory") || "[]");
let currentChatId = null;
let pdfData = []; // 当前PDF列表

// ── Sidebar ────────────────────────────────────────────────
menuBtn.addEventListener("click", () => sidebar.classList.toggle("open"));

document.addEventListener("click", (e) => {
  if (window.innerWidth <= 768 && sidebar.classList.contains("open")) {
    if (!sidebar.contains(e.target) && e.target !== menuBtn && !menuBtn.contains(e.target)) {
      sidebar.classList.remove("open");
    }
  }
});

// ── History ────────────────────────────────────────────────
function renderHistory() {
  const nav = document.getElementById("sidebarNav");
  nav.querySelectorAll(".history-item").forEach((el) => el.remove());
  chatHistory.forEach((item) => {
    const el = document.createElement("div");
    el.className = `history-item${item.id === currentChatId ? " active" : ""}`;
    el.innerHTML = `
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <path d="M21 15a2 2 0 01-2 2H7l-4 4V5a2 2 0 012-2h14a2 2 0 012 2z"/>
      </svg>
      <span>${escapeHtml(item.title)}</span>
    `;
    el.addEventListener("click", () => loadChat(item.id));
    nav.appendChild(el);
  });
}

function saveChat(title, messages) {
  let chat = chatHistory.find((c) => c.id === currentChatId);
  if (!chat) {
    chat = { id: Date.now().toString(), title, messages: [], createdAt: Date.now() };
    chatHistory.unshift(chat);
    currentChatId = chat.id;
  }
  chat.messages = messages;
  chat.updatedAt = Date.now();
  if (chatHistory.length > 50) chatHistory = chatHistory.slice(0, 50);
  localStorage.setItem("chatHistory", JSON.stringify(chatHistory));
  renderHistory();
}

function loadChat(id) {
  const chat = chatHistory.find((c) => c.id === id);
  if (!chat) return;
  currentChatId = id;
  chatArea.innerHTML = "";
  chat.messages.forEach((msg) => {
    if (msg.role === "user") addUserMessageDOM(msg.text, false);
    else addBotMessageDOM(msg.data);
  });
  renderHistory();
  sidebar.classList.remove("open");
}

newChatBtn.addEventListener("click", () => {
  currentChatId = null;
  chatArea.innerHTML = "";
  const welcome = welcomeScreen.cloneNode(true);
  chatArea.appendChild(welcome);
  bindSuggestions();
  renderHistory();
  sidebar.classList.remove("open");
});

clearHistoryBtn.addEventListener("click", () => {
  chatHistory = [];
  localStorage.removeItem("chatHistory");
  renderHistory();
  showToast(t("toastHistoryCleared"));
});

function getChatMessages() {
  const messages = [];
  chatArea.querySelectorAll(".message-group").forEach((group) => {
    const userBubble = group.querySelector(".message-row.user .bubble");
    if (userBubble) messages.push({ role: "user", text: userBubble.textContent });
    const botRow = group.querySelector(".message-row:not(.user)");
    if (botRow && botRow.dataset.response) messages.push({ role: "bot", data: JSON.parse(botRow.dataset.response) });
  });
  return messages;
}

// ── PDF Modal ──────────────────────────────────────────────
pdfManageBtn.addEventListener("click", () => {
  pdfModal.classList.add("show");
  loadPDFList();
  sidebar.classList.remove("open");
});

pdfModalClose.addEventListener("click", () => pdfModal.classList.remove("show"));
pdfModal.addEventListener("click", (e) => { if (e.target === pdfModal) pdfModal.classList.remove("show"); });

// Upload
selectPdfBtn.addEventListener("click", (e) => { e.stopPropagation(); pdfFileInput.click(); });
pdfDropzone.addEventListener("click", (e) => { if (e.target !== selectPdfBtn) pdfFileInput.click(); });

pdfDropzone.addEventListener("dragover", (e) => { e.preventDefault(); pdfDropzone.classList.add("drag-over"); });
pdfDropzone.addEventListener("dragleave", () => pdfDropzone.classList.remove("drag-over"));
pdfDropzone.addEventListener("drop", (e) => {
  e.preventDefault(); pdfDropzone.classList.remove("drag-over");
  const file = e.dataTransfer.files[0];
  if (file && file.name.toLowerCase().endsWith(".pdf")) uploadPDF(file);
});

pdfFileInput.addEventListener("change", () => {
  if (pdfFileInput.files[0]) uploadPDF(pdfFileInput.files[0]);
});

async function uploadPDF(file) {
  uploadProgress.style.display = "flex";
  uploadProgressText.textContent = currentLang === "zh" ? "上传中..." : "Uploading...";

  const formData = new FormData();
  formData.append("file", file);

  try {
    const res = await fetch("/api/upload-pdf", { method: "POST", body: formData });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || "Upload failed");
    }
    showToast(t("toastPdfUploaded"));
    loadPDFList();
  } catch (e) {
    showToast(e.message);
  } finally {
    uploadProgress.style.display = "none";
    pdfFileInput.value = "";
  }
}

// ── PDF List ───────────────────────────────────────────────
async function loadPDFList() {
  try {
    const res = await fetch("/api/pdfs");
    if (!res.ok) throw new Error("Failed to load PDFs");
    const data = await res.json();
    pdfData = data.pdfs || [];
    renderPDFList();
    updatePDFBadge();
  } catch (e) {
    pdfList.innerHTML = `<div class="pdf-hint" style="padding:12px;text-align:center;">加载失败</div>`;
  }
}

function renderPDFList() {
  if (pdfData.length === 0) {
    pdfList.innerHTML = `<div class="pdf-hint" style="padding:16px;text-align:center;">暂无文档，请上传 PDF 文件</div>`;
    return;
  }

  pdfList.innerHTML = pdfData.map((pdf) => `
    <div class="pdf-item${pdf.active ? " active" : ""}" data-name="${escapeHtml(pdf.name)}">
      <input type="checkbox" class="pdf-checkbox" ${pdf.active ? "checked" : ""} data-name="${escapeHtml(pdf.name)}" />
      <div class="pdf-icon">PDF</div>
      <div class="pdf-info">
        <div class="pdf-name" title="${escapeHtml(pdf.name)}">${escapeHtml(pdf.name)}</div>
        <div class="pdf-size">${pdf.size_mb} MB</div>
      </div>
      <button class="pdf-delete-btn" data-name="${escapeHtml(pdf.name)}" title="删除">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6m3 0V4a2 2 0 012-2h4a2 2 0 012 2v2"/>
        </svg>
      </button>
    </div>
  `).join("");

  // Bind checkboxes
  pdfList.querySelectorAll(".pdf-checkbox").forEach((cb) => {
    cb.addEventListener("change", handlePDFCheck);
  });

  // Bind delete buttons
  pdfList.querySelectorAll(".pdf-delete-btn").forEach((btn) => {
    btn.addEventListener("click", (e) => {
      e.stopPropagation();
      handlePDFDelete(btn.dataset.name);
    });
  });
}

async function handlePDFCheck(e) {
  const checkboxes = pdfList.querySelectorAll(".pdf-checkbox");
  const checkedNames = Array.from(checkboxes)
    .filter((cb) => cb.checked)
    .map((cb) => cb.dataset.name);

  // 如果全部取消勾选，视为全部激活
  const pdfNames = checkedNames.length === 0 ? null : checkedNames;

  showRebuilding();
  try {
    const res = await fetch("/api/set-active-pdfs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ pdf_names: pdfNames }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || "Failed");
    }
    showToast(t("toastActiveUpdated"));
    loadPDFList();
  } catch (e) {
    showToast(e.message);
  } finally {
    hideRebuilding();
  }
}

async function handlePDFDelete(name) {
  if (!confirm(t("confirmDelete"))) return;

  try {
    const res = await fetch(`/api/pdfs/${encodeURIComponent(name)}`, { method: "DELETE" });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || "Delete failed");
    }
    showToast(t("toastPdfDeleted"));
    loadPDFList();
  } catch (e) {
    showToast(e.message);
  }
}

rebuildBtn.addEventListener("click", async () => {
  if (!confirm(t("confirmRebuild"))) return;
  showRebuilding();
  try {
    const res = await fetch("/api/rebuild-index", { method: "POST" });
    if (!res.ok) throw new Error("Rebuild failed");
    showToast(t("toastIndexRebuilt"));
  } catch (e) {
    showToast(e.message);
  } finally {
    hideRebuilding();
  }
});

function updatePDFBadge() {
  const activeCount = pdfData.filter((p) => p.active).length;
  const total = pdfData.length;
  if (total === 0) {
    pdfBadgeText.textContent = currentLang === "zh" ? "无文档" : "No docs";
  } else if (activeCount === total) {
    pdfBadgeText.textContent = `${total} ${currentLang === "zh" ? "个文档" : "docs"}`;
  } else {
    pdfBadgeText.textContent = `${activeCount}/${total} ${currentLang === "zh" ? "个文档" : "docs"}`;
  }
}

// ── Retrieval Mode Segmented Control ─────────────────────
if (retrievalModeWrap) {
  const modeBtns = retrievalModeWrap.querySelectorAll(".retrieval-mode-btn");

  // 初始化选中状态
  modeBtns.forEach((btn) => {
    if (btn.dataset.mode === currentRetrievalMode) {
      btn.classList.add("active");
    } else {
      btn.classList.remove("active");
    }
  });

  // 监听点击事件
  modeBtns.forEach((btn) => {
    btn.addEventListener("click", async () => {
      const newMode = btn.dataset.mode;
      if (newMode === currentRetrievalMode) return;
      if (currentRagMode === "lightrag") {
        showToast("LightRAG 模式下无法切换检索模式");
        return;
      }
      showRebuilding();
      try {
        const res = await fetch("/api/retrieval-mode", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ mode: newMode }),
        });
        if (!res.ok) {
          const err = await res.json().catch(() => ({}));
          throw new Error(err.detail || "Failed");
        }
        currentRetrievalMode = newMode;
        localStorage.setItem("retrievalMode", newMode);
        // 更新按钮状态
        modeBtns.forEach((b) => b.classList.remove("active"));
        btn.classList.add("active");
        const modeNames = { hybrid: "混合", vector: "向量", bm25: "全文" };
        showToast(currentLang === "zh" ? `已切换到${modeNames[newMode] || newMode}检索` : `Switched to ${newMode} retrieval`);
      } catch (e) {
        showToast(e.message);
      } finally {
        hideRebuilding();
      }
    });
  });
}

// ── RAG Mode Toggle ─────────────────────────────────────
const ragModeWrap = document.getElementById("ragModeWrap");
if (ragModeWrap) {
  const ragBtns = ragModeWrap.querySelectorAll(".rag-mode-btn");

  // 初始化选中状态
  ragBtns.forEach((btn) => {
    if (btn.dataset.rag === currentRagMode) {
      btn.classList.add("active");
    } else {
      btn.classList.remove("active");
    }
  });

  ragBtns.forEach((btn) => {
    btn.addEventListener("click", async () => {
      const newMode = btn.dataset.rag;
      if (newMode === currentRagMode) return;
      
      // LightRAG 模式需要切换检索模式到 lightrag
      // RAG 模式恢复到之前的检索模式
      const targetRetrievalMode = newMode === "lightrag" ? "lightrag" : (localStorage.getItem("prevRetrievalMode") || "hybrid");
      
      if (newMode === "lightrag") {
        localStorage.setItem("prevRetrievalMode", currentRetrievalMode);
      }
      
      showRebuilding();
      try {
        const res = await fetch("/api/retrieval-mode", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ mode: targetRetrievalMode }),
        });
        if (!res.ok) {
          const err = await res.json().catch(() => ({}));
          throw new Error(err.detail || "Failed");
        }
        currentRagMode = newMode;
        currentRetrievalMode = targetRetrievalMode;
        localStorage.setItem("ragMode", newMode);
        localStorage.setItem("retrievalMode", targetRetrievalMode);
        
        // 更新 RAG 模式按钮状态
        ragBtns.forEach((b) => b.classList.remove("active"));
        btn.classList.add("active");
        
        // 更新检索模式按钮状态
        const retrievalBtns = retrievalModeWrap?.querySelectorAll(".retrieval-mode-btn");
        if (retrievalBtns) {
          retrievalBtns.forEach((b) => {
            b.classList.toggle("active", b.dataset.mode === targetRetrievalMode);
          });
        }
        
        const modeNames = { rag: "RAG", lightrag: "LightRAG" };
        const msg = t("toastRagModeSwitched").replace("{mode}", modeNames[newMode] || newMode);
        showToast(msg);
      } catch (e) {
        showToast(e.message);
      } finally {
        hideRebuilding();
      }
    });
  });
}

// ── Rebuilding overlay ─────────────────────────────────────
let rebuildingEl = null;

function showRebuilding() {
  if (rebuildingEl) return;
  rebuildingEl = document.createElement("div");
  rebuildingEl.className = "rebuilding-overlay";
  rebuildingEl.innerHTML = `
    <div class="rebuilding-card">
      <div class="spinner"></div>
      <p>${t("rebuilding")}</p>
    </div>
  `;
  document.body.appendChild(rebuildingEl);
}

function hideRebuilding() {
  if (rebuildingEl) {
    rebuildingEl.remove();
    rebuildingEl = null;
  }
}

// ── Language ───────────────────────────────────────────────
langSwitchBtn.addEventListener("click", switchLang);

// ── Voice ──────────────────────────────────────────────────
let recognition = null;
let isRecording = false;
let mediaRecorder = null;
let audioChunks = [];

function checkSpeechSupport() {
  if (window.SpeechRecognition || window.webkitSpeechRecognition) return "browser";
  if (navigator.mediaDevices && navigator.mediaDevices.getUserMedia) return "server";
  return "none";
}

function initBrowserSpeech() {
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  recognition = new SR();
  recognition.lang = currentLang === "zh" ? "zh-CN" : "en-US";
  recognition.interimResults = true;
  recognition.continuous = true;
  recognition.maxAlternatives = 1;

  let finalTranscript = "";

  recognition.onstart = () => {
    isRecording = true; finalTranscript = "";
    voiceBtn.classList.add("recording");
    voiceBtn.querySelector(".mic-icon").style.display = "none";
    voiceBtn.querySelector(".recording-indicator").style.display = "flex";
  };

  recognition.onresult = (event) => {
    let interim = "";
    for (let i = event.resultIndex; i < event.results.length; i++) {
      const t = event.results[i][0].transcript;
      if (event.results[i].isFinal) finalTranscript += t; else interim += t;
    }
    inputEl.value = finalTranscript + interim;
    autoResizeInput(); updateSendBtn();
  };

  recognition.onerror = (event) => {
    stopRecording();
    if (event.error === "not-allowed") showToast(t("toastMicPerm"));
    else if (event.error === "no-speech") showToast(t("toastNoSpeech"));
    else showToast(t("toastSttError"));
  };

  recognition.onend = () => {
    if (isRecording) { stopRecordingUI(); if (inputEl.value.trim()) sendQuery(); }
  };
}

function startRecording() {
  const support = checkSpeechSupport();
  if (support === "browser") {
    if (!recognition) initBrowserSpeech();
    try { recognition.start(); } catch (e) { showToast(t("toastSttFail")); }
  } else if (support === "server") {
    startServerRecording();
  } else {
    showToast(t("toastSttUnavailable"));
  }
}

async function startServerRecording() {
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    mediaRecorder = new MediaRecorder(stream, { mimeType: "audio/webm;codecs=opus" });
    audioChunks = [];
    mediaRecorder.ondataavailable = (e) => { if (e.data.size > 0) audioChunks.push(e.data); };
    mediaRecorder.onstop = async () => {
      stream.getTracks().forEach((t) => t.stop());
      await sendAudioToServer(new Blob(audioChunks, { type: "audio/webm" }));
    };
    isRecording = true;
    voiceBtn.classList.add("recording");
    voiceBtn.querySelector(".mic-icon").style.display = "none";
    voiceBtn.querySelector(".recording-indicator").style.display = "flex";
    mediaRecorder.start();
  } catch (e) { showToast(t("toastMicPerm")); }
}

async function sendAudioToServer(blob) {
  try {
    const fd = new FormData();
    fd.append("audio", blob, "recording.webm");
    fd.append("lang", currentLang);
    const res = await fetch("/api/stt", { method: "POST", body: fd });
    if (!res.ok) { showToast(t("toastSttError")); return; }
    const data = await res.json();
    if (data.text?.trim()) {
      inputEl.value = data.text.trim();
      autoResizeInput(); updateSendBtn(); sendQuery();
    } else { showToast(t("toastNoVoice")); }
  } catch (e) { showToast(t("toastSttConnFail")); }
}

function stopRecording() {
  if (!isRecording) return; isRecording = false;
  if (recognition) try { recognition.stop(); } catch (_) {}
  if (mediaRecorder?.state === "recording") mediaRecorder.stop();
  stopRecordingUI();
}

function stopRecordingUI() {
  voiceBtn.classList.remove("recording");
  voiceBtn.querySelector(".mic-icon").style.display = "block";
  voiceBtn.querySelector(".recording-indicator").style.display = "none";
}

voiceBtn.addEventListener("click", () => isRecording ? stopRecording() : startRecording());

// ── Image ──────────────────────────────────────────────────
const imageBtn = document.getElementById("imageBtn");
const imageFileInput = document.getElementById("imageFileInput");
let selectedImageFile = null;

imageBtn.addEventListener("click", () => imageFileInput.click());

imageFileInput.addEventListener("change", () => {
  const file = imageFileInput.files[0];
  if (file) {
    selectedImageFile = file;
    // 显示预览并让用户输入问题
    showImagePreview(file);
  }
});

function showImagePreview(file) {
  const reader = new FileReader();
  reader.onload = (e) => {
    // 在输入框上方显示预览
    let preview = document.getElementById("imagePreview");
    if (!preview) {
      preview = document.createElement("div");
      preview.id = "imagePreview";
      preview.className = "image-preview";
      inputWrap.parentNode.insertBefore(preview, inputWrap);
    }
    preview.innerHTML = `
      <div class="image-preview-inner">
        <img src="${e.target.result}" alt="预览" />
        <div class="image-preview-info">
          <span class="image-preview-name">${escapeHtml(file.name)}</span>
          <span class="image-preview-size">${(file.size / 1024).toFixed(1)} KB</span>
        </div>
        <button class="image-preview-close" id="removeImageBtn" type="button">&times;</button>
      </div>
    `;
    preview.style.display = "block";

    document.getElementById("removeImageBtn").addEventListener("click", () => {
      selectedImageFile = null;
      preview.style.display = "none";
      imageFileInput.value = "";
    });
  };
  reader.readAsDataURL(file);
}

async function sendImageQuery() {
  if (!selectedImageFile) return;

  const query = inputEl.value.trim();
  isLoading = true;
  updateSendBtn();

  const welcome = chatArea.querySelector(".welcome");
  if (welcome) welcome.style.display = "none";

  // 添加用户消息（带图片预览）
  const imageUrl = URL.createObjectURL(selectedImageFile);
  const displayQuery = query
    ? `${query}`
    : "";
  addUserMessageDOM(displayQuery || "图片分析", true, imageUrl, selectedImageFile.name);

  // 清除预览
  const preview = document.getElementById("imagePreview");
  if (preview) preview.style.display = "none";
  inputEl.value = "";
  autoResizeInput();
  addLoading();

  try {
    const formData = new FormData();
    formData.append("file", selectedImageFile);
    if (query) formData.append("query", query);
    formData.append("lang", currentLang);

    const res = await fetch("/api/image-chat", {
      method: "POST",
      body: formData,
    });

    removeLoading();

    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `HTTP ${res.status}`);
    }

    const data = await res.json();

    // 构建回答数据
    let answerData;
    if (data.qa_result) {
      answerData = {
        ...data.qa_result,
        answer: `[📷 图片分析]\n${data.image_analysis.analysis}\n\n---\n\n${data.qa_result.answer}`,
      };
    } else {
      answerData = {
        query: query || "",
        answer: data.image_analysis.analysis,
        confidence: 0.9,
        sources: [],
      };
    }

    addBotMessageDOM(answerData);
    saveChat(displayQuery.substring(0, 40), getChatMessages());
  } catch (e) {
    removeLoading();
    addErrorDOM(e.message);
  } finally {
    isLoading = false;
    updateSendBtn();
    selectedImageFile = null;
    imageFileInput.value = "";
  }
}

// ── Input ──────────────────────────────────────────────────
function autoResizeInput() {
  inputEl.style.height = "auto";
  inputEl.style.height = Math.min(inputEl.scrollHeight, 200) + "px";
}

function updateSendBtn() { sendBtn.disabled = !inputEl.value.trim() || isLoading; }

inputEl.addEventListener("input", () => { autoResizeInput(); updateSendBtn(); });
inputEl.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); if (!sendBtn.disabled) sendQuery(); }
});
sendBtn.addEventListener("click", () => { if (!sendBtn.disabled) sendQuery(); });

// ── Query ──────────────────────────────────────────────────
async function sendQuery(query) {
  // 如果有选中的图片，走图片问答流程
  if (selectedImageFile) {
    return sendImageQuery();
  }

  query = query || inputEl.value.trim();
  if (!query || isLoading) return;

  isLoading = true; updateSendBtn();
  const welcome = chatArea.querySelector(".welcome");
  if (welcome) welcome.style.display = "none";

  addUserMessageDOM(query, true);
  inputEl.value = ""; autoResizeInput();

  // 构建历史消息（只取最近 10 轮，避免 token 过多）
  const historyMessages = buildHistoryMessages();

  try {
    // 使用流式接口
    const res = await fetch("/api/chat/stream", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query, lang: currentLang, history: historyMessages, retrieval_mode: currentRetrievalMode }),
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `HTTP ${res.status}`);
    }

    // 创建空的 bot 消息气泡，后续逐步填充
    const { group, bubbleEl, metaEl, sourcesContainer } = createStreamingBotMessage();
    chatArea.appendChild(group);
    scrollToBottom();

    // 读取 SSE 流
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    let fullAnswer = "";
    let metadata = null;

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n\n");
      buffer = lines.pop() || "";

      for (const line of lines) {
        if (!line.startsWith("data: ")) continue;
        try {
          const data = JSON.parse(line.slice(6));

          if (data.type === "metadata") {
            metadata = data;
          } else if (data.type === "content") {
            fullAnswer += data.content;
            bubbleEl.innerHTML = formatAnswer(fullAnswer);
            scrollToBottom();
          } else if (data.type === "done") {
            // 流结束
          }
        } catch (e) {
          // 忽略解析错误
        }
      }
    }

    // 流结束后，填充元数据（sources、confidence 等）
    if (metadata) {
      finalizeStreamingMessage(group, bubbleEl, metaEl, sourcesContainer, {
        query: metadata.query || query,
        answer: fullAnswer,
        sources: metadata.sources || [],
        confidence: metadata.confidence || 0,
      });
    }

    saveChat(query.substring(0, 40), getChatMessages());
  } catch (e) {
    removeLoading();
    addErrorDOM(e.message);
  } finally {
    isLoading = false; updateSendBtn();
  }
}

/**
 * 从当前聊天区域构建历史消息列表（最近 10 轮）
 */
function buildHistoryMessages() {
  const messages = [];
  const groups = chatArea.querySelectorAll(".message-group");
  // 遍历所有 message-group，提取 user 和 bot 消息
  groups.forEach((group) => {
    const userRow = group.querySelector(".message-row.user .bubble");
    const botRow = group.querySelector(".message-row:not(.user)");
    if (userRow) {
      messages.push({ role: "user", content: userRow.textContent });
    }
    if (botRow && botRow.dataset.response) {
      try {
        const data = JSON.parse(botRow.dataset.response);
        messages.push({ role: "assistant", content: data.answer || "" });
      } catch (e) {}
    }
  });
  // 只保留最近 10 轮（20 条消息）
  return messages.slice(-20);
}

/**
 * 创建一个空的 bot 流式消息 DOM 结构
 */
function createStreamingBotMessage() {
  const group = document.createElement("div");
  group.className = "message-group";

  const inner = document.createElement("div");
  inner.className = "message-inner";

  const row = document.createElement("div");
  row.className = "message-row";

  // Bot avatar
  const avatar = document.createElement("div");
  avatar.className = "avatar bot-avatar";
  avatar.innerHTML = `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>`;

  const body = document.createElement("div");
  body.className = "message-body";

  const bubble = document.createElement("div");
  bubble.className = "bubble bot";
  // 流式加载时显示光标动画
  bubble.innerHTML = `<span class="streaming-cursor"></span>`;

  const meta = document.createElement("div");
  meta.className = "message-meta";
  meta.style.display = "none";

  const sourcesContainer = document.createElement("div");
  sourcesContainer.className = "sources";
  sourcesContainer.style.display = "none";

  const actions = document.createElement("div");
  actions.className = "message-actions";
  actions.style.display = "none";

  body.appendChild(bubble);
  body.appendChild(meta);
  body.appendChild(sourcesContainer);
  body.appendChild(actions);

  row.appendChild(avatar);
  row.appendChild(body);
  inner.appendChild(row);
  group.appendChild(inner);

  return { group, bubbleEl: bubble, metaEl: meta, sourcesContainer, actionsEl: actions };
}

/**
 * 流结束后，填充元数据和操作按钮
 */
function finalizeStreamingMessage(group, bubbleEl, metaEl, sourcesContainer, data) {
  // 移除光标
  const cursor = bubbleEl.querySelector(".streaming-cursor");
  if (cursor) cursor.remove();

  // 更新 dataset.response
  const botRow = group.querySelector(".message-row:not(.user)");
  if (botRow) botRow.dataset.response = JSON.stringify(data);

  // 置信度
  const conf = data.confidence || 0;
  const confClass = conf >= 0.7 ? "confidence-high" : conf >= 0.4 ? "confidence-medium" : "confidence-low";
  metaEl.innerHTML = `<span class="confidence-badge"><span class="confidence-dot ${confClass}"></span>${t("confidence")} ${(conf * 100).toFixed(1)}%</span>`;
  metaEl.style.display = "";

  // 参考来源
  if (data.sources && data.sources.length > 0) {
    const items = data.sources.map((s, i) =>
      `<div class="source-item">
        <span class="source-page">${t("refPrefix")}${i + 1} · ${t("pageLabel")}${s.page ?? "?"}${t("pageSuffix")}</span>
        ${s.source ? `<span class="source-file">${escapeHtml(s.source)}</span>` : ""}
        <span class="source-similarity">${t("similarityLabel")} ${(s.similarity * 100).toFixed(1)}%</span>
      </div>`
    ).join("");

    sourcesContainer.innerHTML = `
      <button class="sources-toggle" type="button">
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="6 9 12 15 18 9"/></svg>
        ${t("sourcesTitle")} (${data.sources.length})
      </button>
      <div class="sources-list">${items}</div>`;
    sourcesContainer.style.display = "";

    // 绑定折叠/展开
    const toggle = sourcesContainer.querySelector(".sources-toggle");
    if (toggle) toggle.addEventListener("click", () => {
      toggle.classList.toggle("expanded");
      toggle.nextElementSibling.classList.toggle("show");
    });
  }

  // 操作按钮
  const actionsEl = group.querySelector(".message-actions");
  if (actionsEl) {
    actionsEl.innerHTML = `
      <button class="action-btn" title="${t("copyBtn")}" data-action="copy">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"/><path d="M5 15H4a2 2 0 01-2-2V4a2 2 0 012-2h9a2 2 0 012 2v1"/></svg>
      </button>
      <button class="action-btn" title="${t("retryBtn")}" data-action="retry">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="23 4 23 10 17 10"/><path d="M20.49 15a9 9 0 11-2.12-9.36L23 10"/></svg>
      </button>
      <button class="action-btn" title="${t("thumbUp")}" data-action="up">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 9V5a3 3 0 00-3-3l-4 9v11h11.28a2 2 0 002-1.7l1.38-9a2 2 0 00-2-2.3zM7 22H4a2 2 0 01-2-2v-7a2 2 0 012-2h3"/></svg>
      </button>
      <button class="action-btn" title="${t("thumbDown")}" data-action="down">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M10 15v4a3 3 0 003 3l4-9V2H5.72a2 2 0 00-2 1.7l-1.38 9a2 2 0 002 2.3zm7-13h2.67A2.31 2.31 0 0122 4v7a2.31 2.31 0 01-2.33 2H17"/></svg>
      </button>`;
    actionsEl.style.display = "";
    actionsEl.querySelectorAll(".action-btn").forEach((btn) => btn.addEventListener("click", () => handleAction(btn, data)));
  }
}

// ── DOM Builders ───────────────────────────────────────────
function escapeHtml(text) {
  const div = document.createElement("div");
  div.textContent = text;
  return div.innerHTML;
}

function formatAnswer(text) {
  let html = escapeHtml(text);
  html = html.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
  html = html.replace(/```(\w*)\n([\s\S]*?)```/g, "<pre><code>$2</code></pre>");
  html = html.replace(/`([^`]+)`/g, "<code>$1</code>");
  html = html.replace(/\n/g, "<br>");
  return html;
}

function addUserMessageDOM(text, animate = true, imageUrl = null, imageName = "") {
  const group = document.createElement("div");
  group.className = "message-group";
  const imageHtml = imageUrl ? `
    <div class="user-image-wrap">
      <img src="${imageUrl}" alt="${escapeHtml(imageName)}" class="user-image-thumb" onclick="openLightbox('${imageUrl}')" />
      ${imageName ? `<span class="user-image-name">${escapeHtml(imageName)}</span>` : ""}
    </div>
  ` : "";
  const textHtml = text ? `<div class="bubble">${escapeHtml(text)}</div>` : "";
  group.innerHTML = `
    <div class="message-inner">
      <div class="message-row user">
        <div class="avatar user-avatar">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
            <path d="M12 12c2.7 0 4.8-2.1 4.8-4.8S14.7 2.4 12 2.4 7.2 4.5 7.2 7.2 9.3 12 12 12zm0 2.4c-3.2 0-9.6 1.6-9.6 4.8v2.4h19.2v-2.4c0-3.2-6.4-4.8-9.6-4.8z"/>
          </svg>
        </div>
        <div class="message-body">${imageHtml}${textHtml}</div>
      </div>
    </div>
  `;
  if (animate) group.style.opacity = "0";
  chatArea.appendChild(group);
  if (animate) requestAnimationFrame(() => { group.style.transition = "opacity 0.2s"; group.style.opacity = "1"; });
  scrollToBottom();
}

function addBotMessageDOM(data) {
  const group = document.createElement("div");
  group.className = "message-group";

  let sourcesHtml = "";
  if (data.sources?.length) {
    const items = data.sources.map((s, i) =>
      `<div class="source-item">
        <span class="source-page">${t("refPrefix")}${i + 1} · ${t("pageLabel")}${s.page ?? "?"}${t("pageSuffix")}</span>
        ${s.source ? `<span class="source-file">${escapeHtml(s.source)}</span>` : ""}
        <span class="source-similarity">${t("similarityLabel")} ${(s.similarity * 100).toFixed(1)}%</span>
      </div>`
    ).join("");

    sourcesHtml = `
      <div class="sources">
        <button class="sources-toggle" type="button">
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="6 9 12 15 18 9"/></svg>
          ${t("sourcesTitle")} (${data.sources.length})
        </button>
        <div class="sources-list">${items}</div>
      </div>`;
  }

  const conf = data.confidence || 0;
  const confClass = conf >= 0.7 ? "confidence-high" : conf >= 0.4 ? "confidence-medium" : "confidence-low";

  group.innerHTML = `
    <div class="message-inner">
      <div class="message-row">
        <div class="avatar bot-avatar">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/><polyline points="14 2 14 8 20 8"/>
          </svg>
        </div>
        <div class="message-body">
          <div class="bubble bot">${formatAnswer(data.answer)}</div>
          <div class="message-meta">
            <span class="confidence-badge"><span class="confidence-dot ${confClass}"></span>${t("confidence")} ${(conf * 100).toFixed(1)}%</span>
          </div>
          ${sourcesHtml}
          <div class="message-actions">
            <button class="action-btn" title="${t("copyBtn")}" data-action="copy">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"/><path d="M5 15H4a2 2 0 01-2-2V4a2 2 0 012-2h9a2 2 0 012 2v1"/></svg>
            </button>
            <button class="action-btn" title="${t("retryBtn")}" data-action="retry">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="23 4 23 10 17 10"/><path d="M20.49 15a9 9 0 11-2.12-9.36L23 10"/></svg>
            </button>
            <button class="action-btn" title="${t("thumbUp")}" data-action="up">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 9V5a3 3 0 00-3-3l-4 9v11h11.28a2 2 0 002-1.7l1.38-9a2 2 0 00-2-2.3zM7 22H4a2 2 0 01-2-2v-7a2 2 0 012-2h3"/></svg>
            </button>
            <button class="action-btn" title="${t("thumbDown")}" data-action="down">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M10 15v4a3 3 0 003 3l4-9V2H5.72a2 2 0 00-2 1.7l-1.38 9a2 2 0 002 2.3zm7-13h2.67A2.31 2.31 0 0122 4v7a2.31 2.31 0 01-2.33 2H17"/></svg>
            </button>
          </div>
        </div>
      </div>
    </div>`;

  const botRow = group.querySelector(".message-row:not(.user)");
  botRow.dataset.response = JSON.stringify(data);

  group.querySelectorAll(".action-btn").forEach((btn) => btn.addEventListener("click", () => handleAction(btn, data)));

  const toggle = group.querySelector(".sources-toggle");
  if (toggle) toggle.addEventListener("click", () => {
    toggle.classList.toggle("expanded");
    toggle.nextElementSibling.classList.toggle("show");
  });

  group.style.opacity = "0";
  chatArea.appendChild(group);
  requestAnimationFrame(() => { group.style.transition = "opacity 0.25s"; group.style.opacity = "1"; });
  scrollToBottom();
}

function addErrorDOM(message) {
  const group = document.createElement("div");
  group.className = "message-group";
  group.innerHTML = `
    <div class="message-inner">
      <div class="message-row">
        <div class="avatar bot-avatar">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#ef4444" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/></svg>
        </div>
        <div class="message-body"><div class="bubble bot" style="color:#ef4444;">${escapeHtml(message)}</div></div>
      </div>
    </div>`;
  chatArea.appendChild(group);
  scrollToBottom();
}

function addLoading() {
  const row = document.createElement("div");
  row.className = "loading-row"; row.id = "loadingIndicator";
  row.innerHTML = `
    <div class="loading-inner">
      <div class="avatar bot-avatar">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>
      </div>
      <div class="typing-indicator"><span class="typing-dot"></span><span class="typing-dot"></span><span class="typing-dot"></span></div>
    </div>`;
  chatArea.appendChild(row);
  scrollToBottom();
}

function removeLoading() { document.getElementById("loadingIndicator")?.remove(); }

// ── Actions ────────────────────────────────────────────────
function handleAction(btn, data) {
  const action = btn.dataset.action;
  if (action === "copy") {
    navigator.clipboard.writeText(data.answer).then(() => {
      btn.classList.add("copied");
      btn.innerHTML = `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="20 6 9 17 4 12"/></svg>`;
      showToast(t("toastCopied"));
      setTimeout(() => { btn.classList.remove("copied"); btn.innerHTML = `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"/><path d="M5 15H4a2 2 0 01-2-2V4a2 2 0 012-2h9a2 2 0 012 2v1"/></svg>`; }, 2000);
    });
  }
  if (action === "retry") {
    const userBubble = chatArea.querySelector(".message-group:last-of-type .message-row.user .bubble");
    if (userBubble) {
      inputEl.value = userBubble.textContent;
      const groups = chatArea.querySelectorAll(".message-group");
      if (groups.length) groups[groups.length - 1].remove();
      sendQuery();
    }
  }
  if (action === "up" || action === "down") {
    const parent = btn.parentElement;
    parent.querySelectorAll(".action-btn").forEach((b) => { if (b.dataset.action === "up" || b.dataset.action === "down") b.style.opacity = "0.3"; });
    btn.style.opacity = "1"; btn.style.color = "var(--primary)";
  }
}

// ── Suggestions ────────────────────────────────────────────
function bindSuggestions() {
  document.querySelectorAll(".suggestion").forEach((btn) => {
    btn.addEventListener("click", () => sendQuery(btn.dataset.query || btn.textContent));
  });
}
bindSuggestions();

// ── Utils ──────────────────────────────────────────────────
function scrollToBottom(smooth = true) {
  requestAnimationFrame(() => chatArea.scrollTo({ top: chatArea.scrollHeight, behavior: smooth ? "smooth" : "auto" }));
}

function showToast(msg) {
  toastEl.textContent = msg;
  toastEl.classList.add("show");
  setTimeout(() => toastEl.classList.remove("show"), 2500);
}

// ── Init ───────────────────────────────────────────────────
applyI18n();
renderHistory();
loadPDFList();

// ── Lightbox ───────────────────────────────────────────────
function openLightbox(imageUrl) {
  let overlay = document.getElementById("lightboxOverlay");
  if (!overlay) {
    overlay = document.createElement("div");
    overlay.id = "lightboxOverlay";
    overlay.className = "lightbox-overlay";
    overlay.innerHTML = `
      <div class="lightbox-content">
        <img id="lightboxImage" src="" alt="" />
        <button class="lightbox-close" id="lightboxClose">&times;</button>
      </div>
    `;
    document.body.appendChild(overlay);

    overlay.addEventListener("click", (e) => {
      if (e.target === overlay || e.target.id === "lightboxClose") {
        overlay.classList.remove("show");
      }
    });

    document.getElementById("lightboxClose").addEventListener("click", () => {
      overlay.classList.remove("show");
    });
  }

  document.getElementById("lightboxImage").src = imageUrl;
  overlay.classList.add("show");
}

// ESC 键关闭 lightbox
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape") {
    const overlay = document.getElementById("lightboxOverlay");
    if (overlay) overlay.classList.remove("show");
  }
});
