// ── 国际化 (i18n) ──────────────────────────────────────────
const i18n = {
  zh: {
    pageTitle: "招股说明书智能问答",
    appTitle: "招股说明书智能问答",
    appSubtitle: "基于 RAG 的文档问答助手",
    welcomeTitle: "您好，有什么可以帮您？",
    welcomeDesc: "请输入关于招股说明书的问题，我将为您检索并解答",
    sug1: "主营业务",
    sug2: "风险因素",
    sug3: "营业收入",
    sug4: "主要产品",
    inputPlaceholder: "输入您的问题，或点击右侧麦克风语音输入...",
    inputHintSend: '按 <kbd>Enter</kbd> 发送，<kbd>Shift+Enter</kbd> 换行',
    inputHintVoice: "| 点击 🎤 语音输入",
    voiceListening: "正在聆听，请说话...",
    voiceRecording: "正在录音，点击麦克风停止...",
    voiceRecognizing: "正在识别语音...",
    voiceCancelHint: "点击麦克风按钮停止",
    // 动态文本
    toastCopied: "已复制到剪贴板",
    toastCopiedShare: "已复制分享内容",
    toastThanks: "感谢反馈",
    toastMicPerm: "请允许麦克风权限后重试",
    toastNoSpeech: "未检测到语音，请重试",
    toastSttError: "语音识别出错，请重试",
    toastSttFail: "启动语音识别失败，请重试",
    toastNoVoice: "未识别到有效语音，请重试",
    toastSttUnavailable: "您的浏览器不支持语音输入功能",
    toastSttConnFail: "语音识别服务连接失败，请检查后端",
    confidence: "置信度",
    sourcesTitle: "参考来源",
    refPrefix: "参考",
    pageLabel: "第",
    pageSuffix: "页",
    similarityLabel: "相似度",
    copyBtn: "复制",
    retryBtn: "再试一次",
    shareBtn: "分享",
    networkError: "网络错误",
    serverNotStarted: "请确认后端服务已启动。",
    requestFail: "请求失败，请稍后重试。",
    thumbUpTitle: "有帮助",
    thumbDownTitle: "无帮助",
    shareTitle: "招股说明书问答",
    askPrefix: "问：",
    answerPrefix: "答：",
  },
  en: {
    pageTitle: "Prospectus Q&A Assistant",
    appTitle: "Prospectus Q&A Assistant",
    appSubtitle: "RAG-based Document Q&A Assistant",
    welcomeTitle: "Hello, how can I help you?",
    welcomeDesc: "Enter a question about the prospectus, and I will search and answer for you",
    sug1: "Main Business",
    sug2: "Risk Factors",
    sug3: "Revenue",
    sug4: "Main Products",
    inputPlaceholder: "Type your question, or click the mic for voice input...",
    inputHintSend: 'Press <kbd>Enter</kbd> to send, <kbd>Shift+Enter</kbd> for new line',
    inputHintVoice: "| Click 🎤 for voice input",
    voiceListening: "Listening, please speak...",
    voiceRecording: "Recording, click mic to stop...",
    voiceRecognizing: "Recognizing speech...",
    voiceCancelHint: "Click mic button to stop",
    toastCopied: "Copied to clipboard",
    toastCopiedShare: "Share content copied",
    toastThanks: "Thanks for your feedback",
    toastMicPerm: "Please allow microphone permission and try again",
    toastNoSpeech: "No speech detected, please try again",
    toastSttError: "Speech recognition error, please try again",
    toastSttFail: "Failed to start speech recognition, please try again",
    toastNoVoice: "No valid speech recognized, please try again",
    toastSttUnavailable: "Your browser does not support voice input",
    toastSttConnFail: "Speech recognition service connection failed, please check the backend",
    confidence: "Confidence",
    sourcesTitle: "References",
    refPrefix: "Ref",
    pageLabel: "P.",
    pageSuffix: "",
    similarityLabel: "Similarity",
    copyBtn: "Copy",
    retryBtn: "Retry",
    shareBtn: "Share",
    networkError: "Network error",
    serverNotStarted: "Please make sure the backend service is running.",
    requestFail: "Request failed, please try again later.",
    thumbUpTitle: "Helpful",
    thumbDownTitle: "Not helpful",
    shareTitle: "Prospectus Q&A",
    askPrefix: "Q: ",
    answerPrefix: "A: ",
  },
};

let currentLang = localStorage.getItem("lang") || "zh";

function t(key) {
  return (i18n[currentLang] && i18n[currentLang][key]) || (i18n.zh[key]) || key;
}

function applyI18n() {
  // 更新 <html> lang 属性
  document.documentElement.lang = currentLang === "zh" ? "zh-CN" : "en";

  // 更新 title
  document.title = t("pageTitle");

  // 更新所有带 data-i18n 的元素
  document.querySelectorAll("[data-i18n]").forEach((el) => {
    const key = el.getAttribute("data-i18n");
    if (key && i18n[currentLang][key] !== undefined) {
      el.innerHTML = i18n[currentLang][key];
    }
  });

  // 更新 placeholder
  document.querySelectorAll("[data-i18n-placeholder]").forEach((el) => {
    const key = el.getAttribute("data-i18n-placeholder");
    if (key && i18n[currentLang][key] !== undefined) {
      el.placeholder = i18n[currentLang][key];
    }
  });

  // 更新语音识别语言
  if (recognition) {
    recognition.lang = currentLang === "zh" ? "zh-CN" : "en-US";
  }

  // 更新语言按钮显示
  const langLabel = document.getElementById("langLabel");
  if (langLabel) {
    langLabel.textContent = currentLang === "zh" ? "EN" : "中";
  }

  // 更新建议按钮的 data-query
  document.querySelectorAll(".suggestion").forEach((btn) => {
    const qAttr = currentLang === "zh" ? "data-query-zh" : "data-query-en";
    const query = btn.getAttribute(qAttr);
    if (query) {
      btn.dataset.query = query;
    }
  });
}

function switchLang() {
  currentLang = currentLang === "zh" ? "en" : "zh";
  localStorage.setItem("lang", currentLang);
  applyI18n();
}

// ── DOM 元素 ───────────────────────────────────────────────
const chatArea = document.getElementById("chatArea");
const inputEl = document.getElementById("queryInput");
const sendBtn = document.getElementById("sendBtn");
const clearBtn = document.getElementById("clearBtn");
const scrollBtn = document.getElementById("scrollBottom");
const toastEl = document.getElementById("toast");
const voiceBtn = document.getElementById("voiceBtn");
const voiceStatus = document.getElementById("voiceStatus");
const voiceStatusText = document.getElementById("voiceStatusText");
const recTimeEl = document.getElementById("recTime");
const inputWrap = document.getElementById("inputWrap");
const inputHint = document.getElementById("inputHint");
const voiceHint = document.getElementById("voiceHint");
const langSwitchBtn = document.getElementById("langSwitch");

let docInfo = { name: "招股说明书1", type: "PDF", size_mb: 0 };
let isLoading = false;
let lastUserQuery = "";

// ── 语言切换按钮事件 ──────────────────────────────────────
if (langSwitchBtn) {
  langSwitchBtn.addEventListener("click", switchLang);
}

// ── 语音识别 ──────────────────────────────────────────────
let recognition = null;
let isRecording = false;
let mediaRecorder = null;
let audioChunks = [];
let recTimer = null;
let recSeconds = 0;
let useServerSTT = false;

function checkSpeechSupport() {
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (SpeechRecognition) {
    return "browser";
  }
  if (navigator.mediaDevices && navigator.mediaDevices.getUserMedia) {
    return "server";
  }
  return "none";
}

function formatRecTime(seconds) {
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return `${m}:${s.toString().padStart(2, "0")}`;
}

function startRecTimer() {
  recSeconds = 0;
  recTimeEl.textContent = "0:00";
  recTimer = setInterval(() => {
    recSeconds++;
    recTimeEl.textContent = formatRecTime(recSeconds);
  }, 1000);
}

function stopRecTimer() {
  if (recTimer) {
    clearInterval(recTimer);
    recTimer = null;
  }
}

function initBrowserSpeech() {
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  recognition = new SpeechRecognition();
  recognition.lang = currentLang === "zh" ? "zh-CN" : "en-US";
  recognition.interimResults = true;
  recognition.continuous = true;
  recognition.maxAlternatives = 1;

  let finalTranscript = "";

  recognition.onstart = () => {
    isRecording = true;
    finalTranscript = "";
    voiceBtn.classList.add("recording");
    voiceBtn.querySelector(".mic-icon").style.display = "none";
    voiceBtn.querySelector(".recording-indicator").style.display = "flex";
    voiceStatus.style.display = "flex";
    voiceStatusText.textContent = t("voiceListening");
    startRecTimer();
  };

  recognition.onresult = (event) => {
    let interimTranscript = "";
    for (let i = event.resultIndex; i < event.results.length; i++) {
      const transcript = event.results[i][0].transcript;
      if (event.results[i].isFinal) {
        finalTranscript += transcript;
      } else {
        interimTranscript += transcript;
      }
    }
    inputEl.value = finalTranscript + interimTranscript;
    autoResizeInput();
  };

  recognition.onerror = (event) => {
    console.error("语音识别错误:", event.error);
    stopRecording();
    if (event.error === "not-allowed") {
      showToast(t("toastMicPerm"));
    } else if (event.error === "no-speech") {
      showToast(t("toastNoSpeech"));
    } else {
      showToast(t("toastSttError"));
    }
  };

  recognition.onend = () => {
    if (isRecording) {
      stopRecordingUI();
      if (finalTranscript.trim()) {
        sendQuery(inputEl.value);
      }
    }
  };
}

async function initServerSTT() {
  // placeholder
}

function startRecording() {
  setRecordingState(true);
  const support = checkSpeechSupport();
  if (support === "browser") {
    if (!recognition) initBrowserSpeech();
    try {
      recognition.start();
    } catch (e) {
      console.error("启动语音识别失败:", e);
      showToast(t("toastSttFail"));
      setRecordingState(false);
    }
  } else if (support === "server") {
    startServerRecording();
  } else {
    showToast(t("toastSttUnavailable"));
    setRecordingState(false);
  }
}

async function startServerRecording() {
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    mediaRecorder = new MediaRecorder(stream, { mimeType: "audio/webm;codecs=opus" });
    audioChunks = [];

    mediaRecorder.ondataavailable = (e) => {
      if (e.data.size > 0) audioChunks.push(e.data);
    };

    mediaRecorder.onstop = async () => {
      stream.getTracks().forEach((t) => t.stop());
      const blob = new Blob(audioChunks, { type: "audio/webm" });
      await sendAudioToServer(blob);
    };

    isRecording = true;
    voiceBtn.classList.add("recording");
    voiceBtn.querySelector(".mic-icon").style.display = "none";
    voiceBtn.querySelector(".recording-indicator").style.display = "flex";
    voiceStatus.style.display = "flex";
    voiceStatusText.textContent = t("voiceRecording");
    startRecTimer();
    mediaRecorder.start();
  } catch (e) {
    console.error("获取麦克风失败:", e);
    showToast(t("toastMicPerm"));
  }
}

async function sendAudioToServer(blob) {
  voiceStatusText.textContent = t("voiceRecognizing");
  try {
    const formData = new FormData();
    formData.append("audio", blob, "recording.webm");
    // 将语言参数传递给后端
    formData.append("lang", currentLang);
    const res = await fetch("/api/stt", { method: "POST", body: formData });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: currentLang === "en" ? "Speech recognition service unavailable" : "语音识别服务不可用" }));
      showToast(err.detail || t("toastSttError"));
      return;
    }
    const data = await res.json();
    if (data.text && data.text.trim()) {
      inputEl.value = data.text.trim();
      autoResizeInput();
      sendQuery(inputEl.value);
    } else {
      showToast(t("toastNoVoice"));
    }
  } catch (e) {
    console.error("语音转文字请求失败:", e);
    showToast(t("toastSttConnFail"));
  }
}

function stopRecording() {
  if (!isRecording) return;
  isRecording = false;
  stopRecTimer();

  if (recognition) {
    try { recognition.stop(); } catch (_) {}
  }
  if (mediaRecorder && mediaRecorder.state === "recording") {
    mediaRecorder.stop();
  }
  stopRecordingUI();
}

function stopRecordingUI() {
  voiceBtn.classList.remove("recording");
  voiceBtn.querySelector(".mic-icon").style.display = "block";
  voiceBtn.querySelector(".recording-indicator").style.display = "none";
  voiceStatus.style.display = "none";
  setRecordingState(false);
  updateClearBtn();
}

function toggleRecording() {
  if (isRecording) {
    stopRecording();
  } else {
    startRecording();
  }
}

// ── 清空按钮逻辑 ──────────────────────────────────────────
function updateClearBtn() {
  clearBtn.style.display = inputEl.value.trim() ? "flex" : "none";
}

clearBtn.addEventListener("click", () => {
  inputEl.value = "";
  autoResizeInput();
  updateClearBtn();
  inputEl.focus();
});

// ── 录音状态增强 ──────────────────────────────────────────
function setRecordingState(recording) {
  if (recording) {
    inputWrap.classList.add("recording");
    if (inputHint) inputHint.style.display = "none";
  } else {
    inputWrap.classList.remove("recording");
    if (inputHint) inputHint.style.display = "flex";
  }
}

// 语音按钮事件
voiceBtn.addEventListener("click", toggleRecording);

async function loadDocInfo() {
  try {
    const res = await fetch("/api/doc-info");
    if (res.ok) docInfo = await res.json();
  } catch (_) {}
}

function showToast(msg) {
  toastEl.textContent = msg;
  toastEl.classList.add("show");
  setTimeout(() => toastEl.classList.remove("show"), 2000);
}

function escapeHtml(text) {
  const div = document.createElement("div");
  div.textContent = text;
  return div.innerHTML;
}

function formatAnswer(text) {
  let html = escapeHtml(text);
  html = html.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
  html = html.replace(/\n/g, "<br>");
  html = html.replace(/<br><br>/g, "</p><p>");
  return `<p>${html}</p>`;
}

function scrollToBottom(smooth = true) {
  chatArea.scrollTo({
    top: chatArea.scrollHeight,
    behavior: smooth ? "smooth" : "auto",
  });
}

function removeWelcome() {
  const welcome = chatArea.querySelector(".welcome");
  if (welcome) welcome.remove();
}

function createFileCard() {
  const card = document.createElement("div");
  card.className = "file-card";
  card.innerHTML = `
    <div class="file-icon">PDF</div>
    <div class="file-info">
      <div class="name">${escapeHtml(docInfo.name || "招股说明书1")}</div>
      <div class="meta">${docInfo.type || "PDF"}, ${docInfo.size_mb || "—"} MB</div>
    </div>
  `;
  return card;
}

function addUserMessage(text, showFile = true) {
  removeWelcome();
  const row = document.createElement("div");
  row.className = "message-row user";
  row.innerHTML = `
    <div class="avatar user-avatar" aria-hidden="true">
      <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor"><path d="M12 12c2.7 0 4.8-2.1 4.8-4.8S14.7 2.4 12 2.4 7.2 4.5 7.2 7.2 9.3 12 12 12zm0 2.4c-3.2 0-9.6 1.6-9.6 4.8v2.4h19.2v-2.4c0-3.2-6.4-4.8-9.6-4.8z"/></svg>
    </div>
    <div class="message-content"></div>
  `;
  const content = row.querySelector(".message-content");
  const bubble = document.createElement("div");
  bubble.className = "bubble user";
  bubble.textContent = text;
  content.appendChild(bubble);
  if (showFile) content.appendChild(createFileCard());
  chatArea.appendChild(row);
  scrollToBottom();
  return row;
}

function addLoading() {
  const row = document.createElement("div");
  row.className = "loading-row";
  row.id = "loadingIndicator";
  row.innerHTML = `
    <div class="avatar bot-avatar"></div>
    <div class="loading-dots"><span></span><span></span><span></span><span></span></div>
  `;
  chatArea.appendChild(row);
  scrollToBottom();
}

function removeLoading() {
  const el = document.getElementById("loadingIndicator");
  if (el) el.remove();
}

function addBotMessage(data) {
  const row = document.createElement("div");
  row.className = "message-row";
  row.dataset.query = data.query;

  let sourcesHtml = "";
  if (data.sources && data.sources.length) {
    const items = data.sources
      .map(
        (s, i) =>
          `${t("refPrefix")}${i + 1}：${t("pageLabel")}${s.page ?? "?"}${t("pageSuffix")}（${t("similarityLabel")} ${(s.similarity * 100).toFixed(1)}%）`
      )
      .join("；");
    sourcesHtml = `<div class="sources"><div class="sources-title">${t("sourcesTitle")}</div>${escapeHtml(items)}</div>`;
  }

  row.innerHTML = `
    <div class="avatar bot-avatar"></div>
    <div class="message-content">
      <div class="bubble bot">${formatAnswer(data.answer)}</div>
      <div class="confidence">${t("confidence")}：${(data.confidence * 100).toFixed(1)}%</div>
      ${sourcesHtml}
      <div class="actions">
        <div class="actions-left">
          <button class="action-btn copy-btn" type="button">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 01-2-2V4a2 2 0 012-2h9a2 2 0 012 2v1"/></svg>
            ${t("copyBtn")}
          </button>
          <button class="action-btn retry-btn" type="button">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M1 4v6h6"/><path d="M3.51 15a9 9 0 102.13-9.36L1 10"/></svg>
            ${t("retryBtn")}
          </button>
          <button class="action-btn share-btn" type="button">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="18" cy="5" r="3"/><circle cx="6" cy="12" r="3"/><circle cx="18" cy="19" r="3"/><path d="M8.59 13.51l6.83 3.98M15.41 6.51l-6.82 3.98"/></svg>
            ${t("shareBtn")}
          </button>
        </div>
        <div class="feedback">
          <button type="button" class="thumb-up" title="${t("thumbUpTitle")}">👍</button>
          <button type="button" class="thumb-down" title="${t("thumbDownTitle")}">👎</button>
        </div>
      </div>
    </div>
  `;

  chatArea.appendChild(row);

  row.querySelector(".copy-btn").addEventListener("click", () => {
    navigator.clipboard.writeText(data.answer).then(() => showToast(t("toastCopied")));
  });

  row.querySelector(".retry-btn").addEventListener("click", () => {
    if (!isLoading && data.query) sendQuery(data.query, false);
  });

  row.querySelector(".share-btn").addEventListener("click", async () => {
    const text = `${t("askPrefix")}${data.query}\n${t("answerPrefix")}${data.answer}`;
    if (navigator.share) {
      try {
        await navigator.share({ title: t("shareTitle"), text });
      } catch (_) {
        navigator.clipboard.writeText(text).then(() => showToast(t("toastCopiedShare")));
      }
    } else {
      navigator.clipboard.writeText(text).then(() => showToast(t("toastCopiedShare")));
    }
  });

  row.querySelectorAll(".feedback button").forEach((btn) => {
    btn.addEventListener("click", () => {
      row.querySelectorAll(".feedback button").forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      showToast(t("toastThanks"));
    });
  });

  scrollToBottom();
}

async function sendQuery(query, showFileOnUser = true) {
  if (isLoading || !query.trim()) return;
  isLoading = true;
  lastUserQuery = query.trim();
  sendBtn.disabled = true;
  inputEl.value = "";
  updateClearBtn();
  autoResizeInput();

  addUserMessage(lastUserQuery, showFileOnUser);
  addLoading();

  try {
    const res = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query: lastUserQuery, lang: currentLang }),
    });
    const data = await res.json();
    removeLoading();

    if (!res.ok) {
      addBotMessage({
        query: lastUserQuery,
        answer: data.detail || t("requestFail"),
        confidence: 0,
        sources: [],
      });
      return;
    }

    addBotMessage(data);
  } catch (err) {
    removeLoading();
    addBotMessage({
      query: lastUserQuery,
      answer: `${t("networkError")}：${err.message}。${t("serverNotStarted")}`,
      confidence: 0,
      sources: [],
    });
  } finally {
    isLoading = false;
    sendBtn.disabled = false;
    inputEl.focus();
  }
}

function autoResizeInput() {
  inputEl.style.height = "auto";
  inputEl.style.height = Math.min(inputEl.scrollHeight, 120) + "px";
}

sendBtn.addEventListener("click", () => sendQuery(inputEl.value));
inputEl.addEventListener("input", () => {
  autoResizeInput();
  updateClearBtn();
});
inputEl.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    sendQuery(inputEl.value);
  }
});

chatArea.addEventListener("scroll", () => {
  const nearBottom =
    chatArea.scrollHeight - chatArea.scrollTop - chatArea.clientHeight < 120;
  scrollBtn.classList.toggle("visible", !nearBottom && chatArea.children.length > 1);
});

scrollBtn.addEventListener("click", () => scrollToBottom());

document.querySelectorAll(".suggestion").forEach((btn) => {
  btn.addEventListener("click", () => {
    // 使用当前语言对应的查询
    const qAttr = currentLang === "zh" ? "data-query-zh" : "data-query-en";
    const query = btn.getAttribute(qAttr) || btn.dataset.query;
    sendQuery(query);
  });
});

// ── 初始化 ────────────────────────────────────────────────
applyI18n();
loadDocInfo();