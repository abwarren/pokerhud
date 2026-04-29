// Emoji helper utilities - High visibility system

const EMOJI = {
  status(status) {
    if (!status) return "•";

    const normalized = status.toLowerCase();

    if (normalized === "success" || normalized === "completed" || normalized === "approved") {
      return "✅🎯";
    }
    if (normalized === "warning" || normalized === "pending") {
      return "⚠️🚨";
    }
    if (normalized === "error" || normalized === "failed") {
      return "❌⛔";
    }
    if (normalized === "denied" || normalized === "blocked") {
      return "🔒⛔";
    }
    if (normalized === "online") {
      return "🟢⚡";
    }
    if (normalized === "offline") {
      return "🔴💀";
    }

    return "•";
  },

  level(level) {
    if (!level) return "•";

    const normalized = level.toLowerCase();

    if (normalized === "info") {
      return "📘ℹ️";
    }
    if (normalized === "warn" || normalized === "warning") {
      return "⚠️🚨";
    }
    if (normalized === "error") {
      return "❌⛔";
    }
    if (normalized === "debug") {
      return "🔍🐛";
    }

    return "•";
  },

  signal(type) {
    if (!type) return "•";

    const normalized = type.toLowerCase();

    // Signal-specific emojis
    if (normalized === "spike") {
      return "🔥📈";
    }
    if (normalized === "freeze") {
      return "🧊❄️";
    }
    if (normalized === "fake-pace" || normalized === "fakepace") {
      return "🎭⚠️";
    }
    if (normalized === "trap") {
      return "🎯🔥";
    }
    if (normalized === "reversal") {
      return "🔄📉";
    }
    if (normalized === "steam") {
      return "🚂📈";
    }

    return "•";
  }
};
