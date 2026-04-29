// Main application entry point

const APP = {
  async init() {
    console.log("🚀 Initializing PLO Admin Panel");

    try {
      await STORE.init();
      SHELL.init();
      ROUTER.init();
      CONTROLLER.initGlobalListeners();

      console.log("✅ Application initialized");
    } catch (error) {
      console.error("❌ Application initialization failed:", error);
      this.showError("Failed to initialize application");
    }
  },

  showError(message) {
    alert(`Error: ${message}`);
  }
};

// Initialize on DOM ready
document.addEventListener("DOMContentLoaded", () => {
  APP.init();
});
