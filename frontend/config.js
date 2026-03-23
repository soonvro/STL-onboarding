window.APP_CONFIG = Object.freeze({
  // Local development falls back to http://localhost:8000 in app.js.
  apiBaseUrl:
    window.location.hostname === "localhost" || window.location.hostname === "127.0.0.1"
      ? ""
      : "https://qna-backend-d7f5tykl6a-du.a.run.app",
});
