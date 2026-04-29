// Global state management

const STORE = {
  state: {
    user: {
      username: null,
      role: null,
      authenticated: false
    },
    ui: {
      currentPage: null,
      connectionStatus: "offline"
    },
    logs: {
      rows: [],
      filters: {}
    },
    ledger: {
      rows: [],
      filters: {}
    },
    tables: [],
    tableStatus: {},
    bots: []
  },

  async init() {
    console.log("📦 Initializing store");

    try {
      const session = await API.getSession();

      if (session && session.user) {
        this.state.user = session.user;
        this.state.ui.connectionStatus = "online";

        // Set role attribute on body for CSS targeting
        document.body.setAttribute("data-role", session.user.role);

        console.log("✅ Session loaded:", session.user.username, `(${session.user.role})`);
      } else {
        throw new Error("Invalid session response");
      }
    } catch (error) {
      console.error("❌ Failed to load session:", error);
      this.state.ui.connectionStatus = "offline";
      throw error;
    }
  },

  set(path, value) {
    const keys = path.split(".");
    let obj = this.state;

    for (let i = 0; i < keys.length - 1; i++) {
      obj = obj[keys[i]];
    }

    obj[keys[keys.length - 1]] = value;
  },

  get(path) {
    const keys = path.split(".");
    let obj = this.state;

    for (const key of keys) {
      obj = obj[key];
      if (obj === undefined) return undefined;
    }

    return obj;
  }
};
