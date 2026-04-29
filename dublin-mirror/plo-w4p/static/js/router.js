// Client-side routing

const ROUTER = {
  currentPageModule: null,

  init() {
    const path = window.location.pathname;
    console.log("🗺️  Routing to:", path);

    // Cleanup previous page if it has a destroy method
    if (this.currentPageModule && this.currentPageModule.destroy) {
      this.currentPageModule.destroy();
    }

    // Set current page
    if (path === "/shell") {
      STORE.state.ui.currentPage = "shell";
      this.currentPageModule = SHELL_PAGE;
      SHELL_PAGE.init();
    } else if (path === "/remote") {
      STORE.state.ui.currentPage = "remote";
      this.currentPageModule = REMOTE_PAGE;
      REMOTE_PAGE.init();
    } else if (path === "/tables") {
      STORE.state.ui.currentPage = "tables";
      this.currentPageModule = TABLES_PAGE;
      TABLES_PAGE.init();
    } else if (path === "/collector") {
      STORE.state.ui.currentPage = "collector";
      this.currentPageModule = COLLECTOR_PAGE;
      COLLECTOR_PAGE.init();
    } else if (path === "/engine") {
      STORE.state.ui.currentPage = "engine";
      this.currentPageModule = ENGINE_PAGE;
      ENGINE_PAGE.init();
    } else if (path === "/bots") {
      STORE.state.ui.currentPage = "bots";
      this.currentPageModule = BOTS_PAGE;
      BOTS_PAGE.init();
    } else if (path === "/blm") {
      STORE.state.ui.currentPage = "blm";
      this.currentPageModule = BLM_PAGE;
      BLM_PAGE.init();
    } else if (path === "/admin/logs") {
      STORE.state.ui.currentPage = "logs";
      this.checkAdminAccess();
      this.currentPageModule = LOGS_PAGE;
      LOGS_PAGE.init();
    } else if (path === "/admin/logs/ledger") {
      STORE.state.ui.currentPage = "ledger";
      this.checkAdminAccess();
      this.currentPageModule = LEDGER_PAGE;
      LEDGER_PAGE.init();
    } else {
      console.warn("⚠️  Unknown route:", path);
    }
  },

  checkAdminAccess() {
    if (STORE.state.user.role !== "admin") {
      console.error("🔒 Access denied: admin role required");
      alert("Access denied. Admin privileges required.");
      window.location.href = "/shell";
    }
  }
};
