// 定义后端API接口的基础路径
const API_BASE = "/api";
// 存储当前登录的用户ID
let userId = "";
// 存储当前选中的角色对象
let currentRole = null;
// 存储当前对话的会话ID，默认使用default
let currentSessionId = "default";
// 存储用户上传的PDF文件列表
let uploadedFiles = [];

// 获取登录页面容器DOM元素
const loginView = document.getElementById("loginView");
// 获取主应用页面容器DOM元素
const appView = document.getElementById("appView");
// 获取显示当前用户名的DOM元素
const currentUserEl = document.getElementById("currentUser");
// 获取显示服务健康状态的DOM元素
const healthStatusEl = document.getElementById("healthStatus");
// 获取角色列表容器DOM元素
const roleListEl = document.getElementById("roleList");
// 获取角色列表加载错误提示DOM元素
const roleListErrorEl = document.getElementById("roleListError");
// 获取当前角色名称显示DOM元素
const currentRoleNameEl = document.getElementById("currentRoleName");
// 获取当前角色副标题显示DOM元素
const currentRoleSubtitleEl = document.getElementById("currentRoleSubtitle");
// 获取当前角色图标显示DOM元素
const currentRoleIconEl = document.getElementById("currentRoleIcon");
// 获取聊天消息展示框DOM元素
const chatBoxEl = document.getElementById("chatBox");
// 获取聊天输入框DOM元素
const messageInputEl = document.getElementById("messageInput");
// 获取聊天表单DOM元素
const chatFormEl = document.getElementById("chatForm");
// 获取退出登录按钮DOM元素
const logoutBtn = document.getElementById("logoutBtn");
// 获取PDF上传区域DOM元素
const uploadAreaEl = document.getElementById("uploadArea");
// 获取PDF文件选择输入框DOM元素
const pdfFileInputEl = document.getElementById("pdfFileInput");
// 获取已上传文件列表展示DOM元素
const uploadedFilesEl = document.getElementById("uploadedFiles");
// 获取PDF解析方式选择器DOM元素
const parseMethodSelectEl = document.getElementById("parseMethodSelect");
// 获取知识库构建按钮DOM元素
const buildKbBtn = document.getElementById("buildKbBtn");
// 获取知识库构建状态提示DOM元素
const kbBuildStatusEl = document.getElementById("kbBuildStatus");

// 获取登录/注册用户名字输入框DOM元素
const authUsernameInput = document.getElementById("authUsername");
// 获取登录/注册密码输入框DOM元素
const authPasswordInput = document.getElementById("authPassword");
// 获取验证码输入框DOM元素
const authCaptchaInput = document.getElementById("authCaptchaInput");
// 获取验证码文字展示DOM元素
const authCaptchaText = document.getElementById("authCaptchaText");
// 获取登录/注册提示信息DOM元素
const authTip = document.getElementById("authTip");
// 获取登录/注册提交按钮DOM元素
const authSubmitBtn = document.getElementById("authSubmitBtn");
// 获取登录标签按钮DOM元素
const loginTabBtn = document.getElementById("loginTabBtn");
// 获取注册标签按钮DOM元素
const registerTabBtn = document.getElementById("registerTabBtn");
// 获取刷新验证码按钮DOM元素
const refreshCaptchaBtn = document.getElementById("refreshCaptchaBtn");

// 存储当前生成的验证码字符串
let currentCaptcha = "";

// 生成随机验证码函数
function refreshCaptcha() {
  // 定义验证码可用字符（排除易混淆字符）
  const chars = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789";
  // 初始化验证码结果
  let result = "";
  // 循环生成4位验证码
  for (let i = 0; i < 4; i++) {
    // 随机选取一个字符拼接到结果中
    result += chars.charAt(Math.floor(Math.random() * chars.length));
  }
  // 将生成的验证码存入全局变量
  currentCaptcha = result;
  // 将验证码显示在页面上
  authCaptchaText.textContent = result;
}

// 页面加载时立即生成验证码
refreshCaptcha();
// 给刷新验证码按钮绑定点击事件，点击时刷新验证码
refreshCaptchaBtn.addEventListener("click", refreshCaptcha);

// 给登录标签绑定点击事件
loginTabBtn.addEventListener("click", () => {
  // 给登录标签添加激活样式
  loginTabBtn.classList.add("active");
  // 移除注册标签的激活样式
  registerTabBtn.classList.remove("active");
  // 将提交按钮文字改为“登录”
  authSubmitBtn.textContent = "登录";
});

// 给注册标签绑定点击事件
registerTabBtn.addEventListener("click", () => {
  // 给注册标签添加激活样式
  registerTabBtn.classList.add("active");
  // 移除登录标签的激活样式
  loginTabBtn.classList.remove("active");
  // 将提交按钮文字改为“注册”
  authSubmitBtn.textContent = "注册";
});

// 设置登录/未登录的界面显示状态
function setAuthedUI(isAuthed) {
  // 如果已登录，隐藏登录界面；否则显示
  loginView.classList.toggle("hidden", isAuthed);
  // 如果已登录，显示主界面；否则隐藏
  appView.classList.toggle("hidden", !isAuthed);
}

// 处理登录/注册表单提交
function handleAuthSubmit() {
  // 获取并去除用户名首尾空格
  const username = authUsernameInput.value.trim();
  // 获取并去除密码首尾空格
  const password = authPasswordInput.value.trim();
  // 获取并转换为大写的验证码
  const captcha = authCaptchaInput.value.trim().toUpperCase();

  // 校验用户名和密码是否为空
  if (!username || !password) {
    // 显示错误提示
    authTip.textContent = "用户名和密码不能为空。";
    // 终止执行
    return;
  }

  // 校验验证码是否正确
  if (captcha !== currentCaptcha) {
    // 显示验证码错误提示
    authTip.textContent = "验证码不正确，请重试。";
    // 刷新验证码
    refreshCaptcha();
    // 清空验证码输入框
    authCaptchaInput.value = "";
    // 终止执行
    return;
  }

  // 判断当前是注册模式还是登录模式
  const isRegister = registerTabBtn.classList.contains("active");
  // 根据模式选择对应的接口地址
  const endpoint = isRegister ? "/auth/register" : "/auth/login";

  // 发送登录/注册请求
  fetch(`${API_BASE}${endpoint}`, {
    // 请求方式为POST
    method: "POST",
    // 设置请求头为JSON格式
    headers: { "Content-Type": "application/json" },
    // 将用户名和密码转为JSON字符串作为请求体
    body: JSON.stringify({ username, password })
  })
  // 将响应结果转为JSON
  .then(res => res.json())
  .then(data => {
    // 如果后端返回成功
    if (data.success) {
      // 执行登录成功后的逻辑
      applyAuthSuccess(username);
      // 清空提示信息
      authTip.textContent = "";
    } else {
      // 显示后端返回的错误信息
      authTip.textContent = data.message || "操作失败";
      // 刷新验证码
      refreshCaptcha();
      // 清空验证码输入框
      authCaptchaInput.value = "";
    }
  })
  // 捕获网络请求异常
  .catch(() => {
    // 显示网络错误提示
    authTip.textContent = "网络请求失败";
  });
}

// 给登录/注册提交按钮绑定点击事件
authSubmitBtn.addEventListener("click", handleAuthSubmit);

// 登录成功后的初始化操作
function applyAuthSuccess(username) {
  // 将用户名存入全局变量
  userId = username;
  // 在页面显示当前用户名
  currentUserEl.textContent = userId;
  // 重置会话ID为默认值
  currentSessionId = "default";
  // 切换到已登录界面
  setAuthedUI(true);
  // 检查后端服务健康状态
  checkHealth();
  // 先加载角色列表，再加载会话列表；如果失败弹出错误提示
  loadRoles().then(() => loadSessions()).catch(error => {
    alert(`初始化失败：${error.message}`);
  });
}

// 检查后端服务健康状态
function checkHealth() {
  // 设置状态为检查中样式
  healthStatusEl.className = "status-pill checking";
  // 设置状态文字
  healthStatusEl.textContent = "检查中";

  // 请求健康检查接口
  fetch(`${API_BASE}/health`)
  .then(res => res.json())
  .then(data => {
    // 如果服务状态正常
    if (data.status === "healthy") {
      // 设置为正常样式
      healthStatusEl.className = "status-pill ok";
      // 设置状态文字
      healthStatusEl.textContent = "在线";
    } else {
      // 设置为异常样式
      healthStatusEl.className = "status-pill bad";
      // 设置状态文字
      healthStatusEl.textContent = "异常";
    }
  })
  // 请求失败
  .catch(() => {
    // 设置为离线样式
    healthStatusEl.className = "status-pill bad";
    // 设置状态文字
    healthStatusEl.textContent = "离线";
  });
}

// 异步加载角色列表
async function loadRoles() {
  try {
    // 清空角色错误提示
    roleListErrorEl.textContent = "";
    // 请求角色列表接口
    const res = await fetch(`${API_BASE}/roles`);
    // 如果响应状态不正常，抛出错误
    if (!res.ok) {
      throw new Error(`HTTP ${res.status}`);
    }
    // 将响应转为JSON
    const roles = await res.json();
    // 渲染角色列表
    renderRoles(roles);
  } catch (error) {
    // 打印错误日志
    console.error("加载角色列表失败:", error);
    // 显示错误提示
    roleListErrorEl.textContent = `加载角色失败: ${error.message}`;
    // 清空角色列表容器
    roleListEl.innerHTML = "";
  }
}

// 渲染角色列表到页面
function renderRoles(roles) {
  // 如果角色数据无效
  if (!roles || !Array.isArray(roles) || roles.length === 0) {
    // 显示暂无数据提示
    roleListErrorEl.textContent = "暂无角色数据";
    // 清空角色列表
    roleListEl.innerHTML = "";
    return;
  }

  // 拼接角色列表HTML并渲染
  roleListEl.innerHTML = roles.map(role => `
    <button class="role-item ${currentRole?.role_code === role.role_code ? 'active' : ''}" 
            data-role-code="${role.role_code}">
      <div class="role-avatar" style="background: ${role.icon_color}">${role.icon}</div>
      <div>
        <div class="role-item-name">${role.display_name}</div>
        <div class="role-item-subtitle">${role.subtitle}</div>
      </div>
    </button>
  `).join("");

  // 给每个角色项绑定点击事件
  roleListEl.querySelectorAll(".role-item").forEach(item => {
    item.addEventListener("click", () => {
      // 获取点击的角色编码
      const roleCode = item.dataset.roleCode;
      // 从角色列表中找到对应角色
      const role = roles.find(r => r.role_code === roleCode);
      // 如果角色存在
      if (role) {
        // 选中该角色
        selectRole(role);
      }
    });
  });

  // 如果还没有选中角色，默认选中第一个
  if (!currentRole && roles.length > 0) {
    selectRole(roles[0]);
  }
}

// 选中指定角色，更新页面显示
function selectRole(role) {
  // 将角色存入全局变量
  currentRole = role;
  // 更新角色名称
  currentRoleNameEl.textContent = role.display_name;
  // 更新角色副标题
  currentRoleSubtitleEl.textContent = role.subtitle;
  // 更新角色图标
  currentRoleIconEl.textContent = role.icon;
  // 更新角色图标背景色
  currentRoleIconEl.style.background = role.icon_color;

  // 高亮当前选中的角色
  roleListEl.querySelectorAll(".role-item").forEach(item => {
    item.classList.toggle("active", item.dataset.roleCode === role.role_code);
  });

  // 清空聊天框并显示角色欢迎语
  chatBoxEl.innerHTML = `
    <div class="message-row assistant">
      <div class="message-bubble">${role.greeting}</div>
    </div>
  `;

  // 重置会话ID为默认
  currentSessionId = "default";
}

// 退出登录按钮点击事件
logoutBtn.addEventListener("click", () => {
  // 请求退出登录接口
  fetch(`${API_BASE}/auth/logout`, { method: "POST" })
  .then(() => {
    // 切换到未登录界面
    setAuthedUI(false);
    // 清空用户名输入框
    authUsernameInput.value = "";
    // 清空密码输入框
    authPasswordInput.value = "";
    // 清空验证码输入框
    authCaptchaInput.value = "";
    // 刷新验证码
    refreshCaptcha();
  });
});

// 异步加载用户会话列表
async function loadSessions() {
  try {
    // 请求会话列表接口
    const res = await fetch(`${API_BASE}/sessions?user_id=${userId}`);
    // 如果响应不正常则直接返回
    if (!res.ok) return;
    // 解析响应数据
    const sessions = await res.json();
    // 渲染会话列表
    renderSessions(sessions);
  } catch (error) {
    // 打印错误日志
    console.error("加载会话失败:", error);
  }
}

// 渲染会话列表
function renderSessions(sessions) {
  // 获取会话列表容器
  const sessionListEl = document.getElementById("sessionList");
  // 如果会话列表为空
  if (!sessions || sessions.length === 0) {
    // 清空容器
    sessionListEl.innerHTML = "";
    return;
  }

  // 拼接会话列表HTML并渲染
  sessionListEl.innerHTML = sessions.map(session => `
    <button class="session-item ${currentSessionId === session.session_id ? 'active' : ''}" 
            data-session-id="${session.session_id}">
      <div class="session-title">${session.title || "未命名会话"}</div>
      <div class="session-meta">
        <span>${session.role_name}</span>
        <span>${session.created_at}</span>
      </div>
    </button>
  `).join("");
}

// 聊天表单提交事件
chatFormEl.addEventListener("submit", async (e) => {
  // 阻止表单默认刷新行为
  e.preventDefault();
  // 获取并去除输入内容首尾空格
  const content = messageInputEl.value.trim();
  // 如果内容为空或未选择角色，则不发送
  if (!content || !currentRole) return;

  // 清空输入框
  messageInputEl.value = "";

  // 将用户消息添加到聊天框
  addMessage("user", content);

  try {
    // 发送聊天请求
    const res = await fetch(`${API_BASE}/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        user_id: userId,
        role_code: currentRole.role_code,
        message: content,
        session_id: currentSessionId
      })
    });

    // 解析响应数据
    const data = await res.json();
    // 如果请求成功
    if (data.success) {
      // 将助手回复添加到聊天框
      addMessage("assistant", data.response);
    }
  } catch (error) {
    // 显示错误消息
    addMessage("assistant", `请求失败: ${error.message}`);
  }
});

// 向聊天框添加消息
function addMessage(role, content) {
  // 创建消息行元素
  const row = document.createElement("div");
  // 设置样式类（user/assistant）
  row.className = `message-row ${role}`;
  // 设置消息内容
  row.innerHTML = `<div class="message-bubble">${content}</div>`;
  // 将消息添加到聊天框
  chatBoxEl.appendChild(row);
  // 滚动到底部显示最新消息
  chatBoxEl.scrollTop = chatBoxEl.scrollHeight;
}

// 点击上传区域触发文件选择框
uploadAreaEl.addEventListener("click", () => {
  pdfFileInputEl.click();
});

// 拖拽文件经过上传区域时
uploadAreaEl.addEventListener("dragover", (e) => {
  // 阻止默认行为
  e.preventDefault();
  // 添加拖拽高亮样式
  uploadAreaEl.classList.add("dragover");
});

// 拖拽文件离开上传区域
uploadAreaEl.addEventListener("dragleave", () => {
  // 移除拖拽高亮样式
  uploadAreaEl.classList.remove("dragover");
});

// 拖拽文件释放
uploadAreaEl.addEventListener("drop", (e) => {
  // 阻止默认行为
  e.preventDefault();
  // 移除拖拽高亮样式
  uploadAreaEl.classList.remove("dragover");
  // 筛选出PDF文件
  const files = Array.from(e.dataTransfer.files).filter(f => f.type === "application/pdf");
  // 添加到上传列表
  addFiles(files);
});

// 文件选择框变化事件
pdfFileInputEl.addEventListener("change", (e) => {
  // 筛选出PDF文件
  const files = Array.from(e.target.files).filter(f => f.type === "application/pdf");
  // 添加到上传列表
  addFiles(files);
});

// 添加文件到上传列表
function addFiles(files) {
  // 遍历文件
  files.forEach(file => {
    // 如果文件不存在于列表中
    if (!uploadedFiles.find(f => f.name === file.name)) {
      // 添加到上传列表
      uploadedFiles.push(file);
    }
  });
  // 更新上传文件展示
  updateUploadedFiles();
}

// 更新已上传文件展示列表
function updateUploadedFiles() {
  // 如果没有上传文件
  if (uploadedFiles.length === 0) {
    // 清空展示区域
    uploadedFilesEl.innerHTML = "";
    // 禁用构建按钮
    buildKbBtn.disabled = true;
    return;
  }

  // 渲染已上传文件列表
  uploadedFilesEl.innerHTML = uploadedFiles.map((file, index) => `
    <div class="uploaded-file-item">
      <span class="filename">${file.name}</span>
      <button class="remove-btn" data-index="${index}">×</button>
    </div>
  `).join("");

  // 给删除按钮绑定事件
  uploadedFilesEl.querySelectorAll(".remove-btn").forEach(btn => {
    btn.addEventListener("click", (e) => {
      // 获取文件索引
      const index = parseInt(e.target.dataset.index);
      // 从列表中删除
      uploadedFiles.splice(index, 1);
      // 更新展示
      updateUploadedFiles();
    });
  });

  // 启用构建按钮
  buildKbBtn.disabled = false;
}

// 构建知识库按钮点击事件
buildKbBtn.addEventListener("click", async () => {
  // 如果未选择角色或未上传文件，直接返回
  if (!currentRole || uploadedFiles.length === 0) return;

  // 创建表单数据对象
  const formData = new FormData();
  // 将所有上传文件添加到表单
  uploadedFiles.forEach(file => {
    formData.append("files", file);
  });
  // 添加角色编码参数
  formData.append("role_code", currentRole.role_code);
  // 添加解析方式参数
  formData.append("parse_method", parseMethodSelectEl.value);

  // 禁用构建按钮
  buildKbBtn.disabled = true;
  // 显示构建中状态
  kbBuildStatusEl.textContent = "正在构建知识库...";
  kbBuildStatusEl.className = "kb-build-status building";

  try {
    // 发送构建知识库请求
    const res = await fetch(`${API_BASE}/knowledge/build_pdf`, {
      method: "POST",
      body: formData
    });

    // 如果响应不正常
    if (!res.ok) {
      // 解析错误信息
      const errorData = await res.json();
      // 抛出错误
      throw new Error(errorData.detail || "构建失败");
    }

    // 解析响应数据
    const data = await res.json();
    // 如果构建成功
    if (data.success) {
      // 显示成功信息
      kbBuildStatusEl.textContent = `构建成功！导入 ${data.files_count} 个文件，生成 ${data.chunks_count} 个文档块`;
      kbBuildStatusEl.className = "kb-build-status success";
      // 清空上传文件列表
      uploadedFiles = [];
      // 更新展示
      updateUploadedFiles();
    } else {
      // 显示失败信息
      kbBuildStatusEl.textContent = `构建失败: ${data.message || "未知错误"}`;
      kbBuildStatusEl.className = "kb-build-status error";
    }
  } catch (error) {
    // 显示请求异常信息
    kbBuildStatusEl.textContent = `请求失败: ${error.message}`;
    kbBuildStatusEl.className = "kb-build-status error";
  }

  // 5秒后清空状态提示
  setTimeout(() => {
    kbBuildStatusEl.textContent = "";
    kbBuildStatusEl.className = "kb-build-status";
    // 根据是否有文件设置按钮状态
    buildKbBtn.disabled = uploadedFiles.length === 0;
  }, 5000);
});