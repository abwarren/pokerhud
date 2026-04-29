// Shell layout management

const SHELL = {
  init() {
    console.log("🐚 Initializing shell");
    this.renderSidebar();
    this.renderTopbar();
    this.applyRoleVisibility();
  },

  renderSidebar() {
    const role = STORE.state.user.role;
    const page = STORE.state.ui.currentPage;

    let nav = `
      <a href="/shell" class="nav-item ${page === "shell" ? "active" : ""}">
        <span>✅🎛️</span><span>Shell Control</span>
      </a>
      <a href="/remote" class="nav-item ${page === "remote" ? "active" : ""}">
        <span>🎮🃏</span><span>Remote Control</span>
      </a>
      <a href="/tables" class="nav-item ${page === "tables" ? "active" : ""}">
        <span>📊🗃️</span><span>Tables</span>
      </a>
      <a href="/collector" class="nav-item ${page === "collector" ? "active" : ""}">
        <span>📋✂️</span><span>Hand Collector</span>
      </a>
      <a href="/engine" class="nav-item ${page === "engine" ? "active" : ""}">
        <span>🧮🔢</span><span>Equity Engine</span>
      </a>
      <a href="/bots" class="nav-item ${page === "bots" ? "active" : ""}">
        <span>🤖🎰</span><span>Bot Manager</span>
      </a>
      <a href="/blm" class="nav-item ${page === "blm" ? "active" : ""}">
        <span>🏀📊</span><span>BLM Monitor</span>
      </a>
    `;

    if (role === "admin") {
      nav += `
        <a href="/admin/logs" class="nav-item ${page === "logs" ? "active" : ""}">
          <span>📋📊</span><span>Activity Logs</span>
        </a>
        <a href="/admin/logs/ledger" class="nav-item ${page === "ledger" ? "active" : ""}">
          <span>💰💸</span><span>Ledger System</span>
        </a>
      `;
    }

    setHTML("#sidebar", nav);
  },

  renderTopbar() {
    const user = STORE.state.user;
    const status = STORE.state.ui.connectionStatus;

    setHTML("#topbar", `
      <div class="topbar-left">
        <h1>${this.pageTitle()}</h1>
      </div>
      <div class="topbar-right">
        <span class="status-badge ${status}">${status === "online" ? "🟢⚡" : "🔴💀"} ${status === "online" ? "System Online" : "System Offline"}</span>
        <span class="role-badge">${user.role === "admin" ? "🔒🛡️" : "👤🎮"} ${user.role === "admin" ? "Admin" : "Operator"}</span>
        <span class="user-badge">👤 ${user.username}</span>
      </div>
    `);
  },

  pageTitle() {
    switch (STORE.state.ui.currentPage) {
      case "remote":
        return "🎮🃏 Remote Control";
      case "tables":
        return "📊🗃️ Tables";
      case "collector":
        return "📋✂️ Hand Collector";
      case "engine":
        return "🧮🔢 Equity Engine";
      case "bots":
        return "🤖🎰 Bot Manager";
      case "blm":
        return "🏀📊 BLM Monitor";
      case "logs":
        return "📋📊 Activity Logs";
      case "ledger":
        return "💰💸 Ledger System";
      default:
        return "✅🎛️ Shell Control";
    }
  },

  applyRoleVisibility() {
    if (STORE.state.user.role !== "admin") {
      const adminElements = document.querySelectorAll(".admin-only");
      adminElements.forEach(el => el.classList.add("hidden"));
    }
  }
};

// Shell page logic
const SHELL_PAGE = {
  init() {
    console.log("✅ Initializing shell page");
    this.render();
  },

  render() {
    const user = STORE.state.user;
    const status = STORE.state.ui.connectionStatus;

    setHTML("#page-content", `
      <section class="summary-grid">
        <div class="summary-card ${status === "online" ? "positive" : "negative"}">
          <div class="summary-title">${status === "online" ? "🟢⚡" : "🔴💀"} System Status</div>
          <div class="summary-value">${status === "online" ? "Online" : "Offline"}</div>
        </div>

        <div class="summary-card neutral">
          <div class="summary-title">${user.role === "admin" ? "🔒🛡️" : "👤🎮"} Access Role</div>
          <div class="summary-value">${user.role === "admin" ? "Admin" : "Operator"}</div>
        </div>

        <div class="summary-card neutral">
          <div class="summary-title">👤📛 Active User</div>
          <div class="summary-value">${user.username || "Unknown"}</div>
        </div>
      </section>

      <section class="summary-card">
        <div class="summary-title">ℹ️👋 Welcome Message</div>
        <p style="color: var(--text-secondary); margin-top: 8px; font-size: 12px;">
          You are logged in as <strong>${user.username}</strong> with <strong>${user.role}</strong> privileges.
          ${user.role === "admin" ? "✅ Use the sidebar to access admin features." : "⚠️ Contact an administrator for elevated access."}
        </p>
      </section>
    `);
  }
};

// Helper functions
function setHTML(selector, html) {
  const el = document.querySelector(selector);
  if (el) {
    el.innerHTML = html;
  } else {
    console.warn("⚠️  Element not found:", selector);
  }
}

function getValue(selector) {
  const el = document.querySelector(selector);
  return el ? el.value : "";
}

function hide(selector) {
  const el = document.querySelector(selector);
  if (el) {
    el.classList.add("hidden");
  }
}

function show(selector) {
  const el = document.querySelector(selector);
  if (el) {
    el.classList.remove("hidden");
  }
}
