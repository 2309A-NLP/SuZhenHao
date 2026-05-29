-- MySQL 表结构定义（用户、角色、会话、消息、知识库文档等）。

-- 用户信息
CREATE TABLE IF NOT EXISTS users (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  user_id VARCHAR(64) NOT NULL UNIQUE,
  display_name VARCHAR(128) NOT NULL,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);

-- 角色信息（支持多角色扩展）
CREATE TABLE IF NOT EXISTS roles (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  role_code VARCHAR(64) NOT NULL UNIQUE,
  role_name VARCHAR(128) NOT NULL,
  prompt_template TEXT NOT NULL,
  is_active TINYINT DEFAULT 1,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);

-- 用户角色绑定
CREATE TABLE IF NOT EXISTS user_roles (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  user_id BIGINT NOT NULL,
  role_id BIGINT NOT NULL,
  is_default TINYINT DEFAULT 0,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY uniq_user_role (user_id, role_id),
  CONSTRAINT fk_user_roles_user FOREIGN KEY (user_id) REFERENCES users(id),
  CONSTRAINT fk_user_roles_role FOREIGN KEY (role_id) REFERENCES roles(id)
);

-- 知识库文档元信息（用于动态更新管理）
CREATE TABLE IF NOT EXISTS kb_documents (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  doc_code VARCHAR(128) NOT NULL UNIQUE,
  title VARCHAR(512) NOT NULL,
  source VARCHAR(256) NOT NULL,
  category VARCHAR(128),
  version VARCHAR(64),
  status VARCHAR(32) DEFAULT 'active',
  updated_by VARCHAR(64),
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 对话会话（用户的会话列表）
CREATE TABLE IF NOT EXISTS chat_sessions (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  user_id VARCHAR(64) NOT NULL,
  role_code VARCHAR(64) NOT NULL,
  session_id VARCHAR(64) NOT NULL,
  title VARCHAR(255) DEFAULT '新对话',
  last_message TEXT,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  last_active_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY uniq_user_role_session (user_id, role_code, session_id),
  INDEX idx_user_role_last_active (user_id, role_code, last_active_at)
);

-- 对话消息（存问题/回答）
CREATE TABLE IF NOT EXISTS chat_messages (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  user_id VARCHAR(64) NOT NULL,
  role_code VARCHAR(64) NOT NULL,
  session_id VARCHAR(64) NOT NULL,
  role VARCHAR(16) NOT NULL,
  content TEXT NOT NULL,
  ts TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  sources_json LONGTEXT,
  INDEX idx_user_role_session_ts (user_id, role_code, session_id, ts)
);
