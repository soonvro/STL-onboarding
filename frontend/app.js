const ROUTE_HOME = "/";
const ROUTE_ADMIN = "/admin";
const LOCAL_STORAGE_API_KEY = "smart_timelabs.apiBaseUrl";
const DEFAULT_LOCAL_API_BASE_URL = "http://localhost:8000";
const STATUS_OPTIONS = ["등록됨", "처리중", "완료됨"];

const root = document.querySelector("#app");

const state = {
  route: normalizeRoute(window.location.pathname),
  apiBaseUrl: resolveInitialApiBaseUrl(),
  configDraft: resolveInitialApiBaseUrl(),
  configNotice: null,
  publicForm: {
    name: "",
    email: "",
    phone: "",
    title: "",
    body: "",
  },
  publicSubmitting: false,
  publicNotice: null,
  admin: makeAdminState(),
};

root.addEventListener("click", handleClick);
root.addEventListener("submit", handleSubmit);
root.addEventListener("input", handleInput);
root.addEventListener("change", handleChange);
window.addEventListener("popstate", handlePopState);

render();

if (state.route === ROUTE_ADMIN && state.apiBaseUrl) {
  void ensureAdminSession();
}

function makeAdminState() {
  return {
    initialized: false,
    checkingSession: false,
    authenticated: false,
    authMessage: "",
    loginPassword: "",
    loginSubmitting: false,
    filterStatus: "",
    items: [],
    nextCursor: null,
    loadingList: false,
    listError: "",
    selectedId: "",
    detail: null,
    loadingDetail: false,
    detailError: "",
    updateStatus: STATUS_OPTIONS[0],
    updateResolution: "",
    updateSubmitting: false,
    updateMessage: null,
  };
}

function handlePopState() {
  state.route = normalizeRoute(window.location.pathname);
  render();
  if (state.route === ROUTE_ADMIN && state.apiBaseUrl) {
    void ensureAdminSession();
  }
}

function handleClick(event) {
  const routeTarget = event.target.closest("[data-route]");
  if (routeTarget) {
    event.preventDefault();
    navigateTo(routeTarget.dataset.route || ROUTE_HOME);
    return;
  }

  const actionTarget = event.target.closest("[data-action]");
  if (!actionTarget) {
    return;
  }

  const action = actionTarget.dataset.action;

  if (action === "reset-config") {
    event.preventDefault();
    resetApiConfiguration();
    return;
  }

  if (action === "logout") {
    event.preventDefault();
    void logoutAdmin();
    return;
  }

  if (action === "load-more") {
    event.preventDefault();
    void loadInquiries({ append: true });
    return;
  }

  if (action === "select-inquiry") {
    event.preventDefault();
    const inquiryId = actionTarget.dataset.inquiryId || "";
    if (inquiryId) {
      void selectInquiry(inquiryId);
    }
    return;
  }

  if (action === "set-filter") {
    event.preventDefault();
    const nextFilter = actionTarget.dataset.filterStatus || "";
    if (state.admin.filterStatus !== nextFilter) {
      state.admin.filterStatus = nextFilter;
      state.admin.selectedId = "";
      state.admin.detail = null;
      state.admin.detailError = "";
      void loadInquiries({ reset: true });
    }
  }
}

function handleSubmit(event) {
  const form = event.target;
  if (!(form instanceof HTMLFormElement)) {
    return;
  }

  const formName = form.dataset.form;
  if (!formName) {
    return;
  }

  event.preventDefault();

  if (formName === "config") {
    saveApiConfiguration();
    return;
  }

  if (formName === "public-inquiry") {
    void submitInquiry();
    return;
  }

  if (formName === "admin-login") {
    void loginAdmin();
    return;
  }

  if (formName === "admin-update") {
    void updateInquiryStatus();
  }
}

function handleInput(event) {
  const target = event.target;
  if (!(target instanceof HTMLInputElement || target instanceof HTMLTextAreaElement || target instanceof HTMLSelectElement)) {
    return;
  }

  const form = target.closest("form");
  const formName = form?.dataset.form;

  if (formName === "config" && target.name === "apiBaseUrl") {
    state.configDraft = target.value;
    return;
  }

  if (formName === "public-inquiry" && target.name in state.publicForm) {
    state.publicForm[target.name] = target.value;
    return;
  }

  if (formName === "admin-login" && target.name === "password") {
    state.admin.loginPassword = target.value;
    return;
  }

  if (formName === "admin-update") {
    if (target.name === "status") {
      state.admin.updateStatus = target.value;
      if (state.admin.updateStatus !== "완료됨") {
        state.admin.updateResolution = "";
      }
      state.admin.updateMessage = null;
      render();
      return;
    }

    if (target.name === "resolution") {
      state.admin.updateResolution = target.value;
      state.admin.updateMessage = null;
    }
  }
}

function handleChange(event) {
  const target = event.target;
  if (!(target instanceof HTMLInputElement || target instanceof HTMLTextAreaElement || target instanceof HTMLSelectElement)) {
    return;
  }

  const formName = target.closest("form")?.dataset.form;
  if (formName === "admin-update" && target.name === "status") {
    state.admin.updateStatus = target.value;
    state.admin.updateMessage = null;
    render();
  }
}

function navigateTo(route) {
  const normalized = normalizeRoute(route);
  if (normalized === state.route) {
    return;
  }

  window.history.pushState({}, "", normalized);
  state.route = normalized;
  render();

  if (normalized === ROUTE_ADMIN && state.apiBaseUrl) {
    void ensureAdminSession();
  }
}

function normalizeRoute(pathname) {
  const normalized = pathname.replace(/\/+$/, "") || ROUTE_HOME;
  if (normalized === ROUTE_ADMIN || normalized.startsWith(`${ROUTE_ADMIN}/`)) {
    return ROUTE_ADMIN;
  }
  return ROUTE_HOME;
}

function resolveInitialApiBaseUrl() {
  const searchOverride = normalizeApiBaseUrl(new URLSearchParams(window.location.search).get("apiBaseUrl") || "");
  if (searchOverride) {
    return searchOverride;
  }

  const configured = normalizeApiBaseUrl(window.APP_CONFIG?.apiBaseUrl || "");
  if (configured) {
    return configured;
  }

  const saved = normalizeApiBaseUrl(window.localStorage.getItem(LOCAL_STORAGE_API_KEY) || "");
  if (saved) {
    return saved;
  }

  if (isLocalHostname(window.location.hostname)) {
    return DEFAULT_LOCAL_API_BASE_URL;
  }

  return "";
}

function normalizeApiBaseUrl(value) {
  return String(value || "").trim().replace(/\/+$/, "");
}

function isLocalHostname(hostname) {
  return hostname === "localhost" || hostname === "127.0.0.1";
}

function saveApiConfiguration() {
  const normalized = normalizeApiBaseUrl(state.configDraft);
  if (!normalized) {
    state.configNotice = {
      type: "warn",
      text: "백엔드 API 주소를 입력해주세요.",
    };
    render();
    return;
  }

  window.localStorage.setItem(LOCAL_STORAGE_API_KEY, normalized);
  state.apiBaseUrl = normalized;
  state.configDraft = normalized;
  state.configNotice = {
    type: "ok",
    text: "브라우저에 API 주소를 저장했습니다.",
  };
  state.publicNotice = null;
  state.admin = makeAdminState();
  render();

  if (state.route === ROUTE_ADMIN) {
    void ensureAdminSession();
  }
}

function resetApiConfiguration() {
  window.localStorage.removeItem(LOCAL_STORAGE_API_KEY);
  state.apiBaseUrl = resolveInitialApiBaseUrl();
  state.configDraft = state.apiBaseUrl;
  state.configNotice = {
    type: "ok",
    text: state.apiBaseUrl
      ? "기본 API 주소로 되돌렸습니다."
      : "저장된 API 주소를 지웠습니다.",
  };
  state.publicNotice = null;
  state.admin = makeAdminState();
  render();

  if (state.route === ROUTE_ADMIN && state.apiBaseUrl) {
    void ensureAdminSession();
  }
}

async function submitInquiry() {
  if (!state.apiBaseUrl) {
    state.publicNotice = {
      type: "warn",
      text: "문의를 보내기 전에 백엔드 API 주소를 먼저 설정해주세요.",
    };
    render();
    return;
  }

  state.publicSubmitting = true;
  state.publicNotice = null;
  render();

  try {
    const response = await fetch(apiUrl("/api/v1/inquiries"), {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(state.publicForm),
    });
    const body = await parseResponseBody(response);

    if (!response.ok) {
      state.publicNotice = {
        type: response.status >= 500 ? "error" : "warn",
        text: responseMessage(body, "문의 등록에 실패했습니다."),
      };
      return;
    }

    const requestId = typeof body?.request_id === "string" ? body.request_id : "";
    state.publicForm = {
      name: "",
      email: "",
      phone: "",
      title: "",
      body: "",
    };
    state.publicNotice = {
      type: "ok",
      text: requestId
        ? `문의가 등록되었습니다. 요청 ID: ${requestId}`
        : "문의가 등록되었습니다.",
    };
  } catch (error) {
    state.publicNotice = {
      type: "error",
      text: error instanceof Error ? error.message : "네트워크 오류로 문의 등록에 실패했습니다.",
    };
  } finally {
    state.publicSubmitting = false;
    render();
  }
}

async function ensureAdminSession() {
  if (!state.apiBaseUrl || state.admin.checkingSession || state.admin.authenticated) {
    return;
  }

  state.admin.checkingSession = true;
  state.admin.authMessage = "";
  render();

  try {
    const response = await fetch(apiUrl("/api/v1/admin/session"), {
      credentials: "include",
    });

    if (response.status === 401) {
      state.admin = {
        ...makeAdminState(),
        initialized: true,
        authMessage: "관리자 비밀번호를 입력해주세요.",
      };
      render();
      return;
    }

    if (!response.ok) {
      const body = await parseResponseBody(response);
      state.admin = {
        ...makeAdminState(),
        initialized: true,
        authMessage: responseMessage(body, "관리자 세션 확인에 실패했습니다."),
      };
      render();
      return;
    }

    state.admin.authenticated = true;
    state.admin.initialized = true;
    state.admin.checkingSession = false;
    state.admin.authMessage = "";
    render();
    await loadInquiries({ reset: true });
  } catch (error) {
    state.admin = {
      ...makeAdminState(),
      initialized: true,
      authMessage: error instanceof Error ? error.message : "관리자 세션 확인 중 오류가 발생했습니다.",
    };
    render();
  } finally {
    state.admin.checkingSession = false;
    render();
  }
}

async function loginAdmin() {
  if (!state.apiBaseUrl) {
    state.admin.authMessage = "로그인 전에 백엔드 API 주소를 먼저 설정해주세요.";
    render();
    return;
  }

  state.admin.loginSubmitting = true;
  state.admin.authMessage = "";
  render();

  try {
    const response = await fetch(apiUrl("/api/v1/admin/session"), {
      method: "POST",
      credentials: "include",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ password: state.admin.loginPassword }),
    });
    const body = await parseResponseBody(response);

    if (!response.ok) {
      state.admin.authMessage = responseMessage(body, "관리자 로그인에 실패했습니다.");
      return;
    }

    state.admin.authenticated = true;
    state.admin.initialized = true;
    state.admin.loginPassword = "";
    state.admin.authMessage = "";
    render();
    await loadInquiries({ reset: true });
  } catch (error) {
    state.admin.authMessage = error instanceof Error ? error.message : "관리자 로그인 중 오류가 발생했습니다.";
  } finally {
    state.admin.loginSubmitting = false;
    render();
  }
}

async function logoutAdmin() {
  if (!state.apiBaseUrl) {
    state.admin = makeAdminState();
    render();
    return;
  }

  try {
    await fetch(apiUrl("/api/v1/admin/session"), {
      method: "DELETE",
      credentials: "include",
    });
  } catch (_error) {
    // Ignore logout transport errors and return to the login screen anyway.
  }

  state.admin = {
    ...makeAdminState(),
    initialized: true,
    authMessage: "관리자 세션이 종료되었습니다.",
  };
  render();
}

async function loadInquiries({ reset = false, append = false } = {}) {
  if (!state.admin.authenticated || !state.apiBaseUrl) {
    return;
  }

  if (append && !state.admin.nextCursor) {
    return;
  }

  const cursor = append ? state.admin.nextCursor : null;
  state.admin.loadingList = true;
  state.admin.listError = "";
  state.admin.updateMessage = null;
  render();

  try {
    const search = new URLSearchParams();
    if (state.admin.filterStatus) {
      search.set("status", state.admin.filterStatus);
    }
    search.set("page_size", "20");
    if (cursor) {
      search.set("cursor", cursor);
    }

    const response = await adminRequest(`/api/v1/admin/inquiries?${search.toString()}`);
    if (!response) {
      return;
    }

    const body = await parseResponseBody(response);
    if (!response.ok) {
      state.admin.listError = responseMessage(body, "문의 목록을 불러오지 못했습니다.");
      return;
    }

    const incomingItems = Array.isArray(body?.items) ? body.items : [];
    state.admin.items = append ? state.admin.items.concat(incomingItems) : incomingItems;
    state.admin.nextCursor = typeof body?.next_cursor === "string" ? body.next_cursor : null;

    const currentExists = state.admin.items.some((item) => item?.id === state.admin.selectedId);
    const nextSelectedId = currentExists ? state.admin.selectedId : state.admin.items[0]?.id || "";

    state.admin.selectedId = nextSelectedId;
    if (!nextSelectedId) {
      state.admin.detail = null;
      state.admin.detailError = "";
      return;
    }

    if (!state.admin.detail || state.admin.detail.id !== nextSelectedId || reset) {
      await loadInquiryDetail(nextSelectedId);
    }
  } catch (error) {
    state.admin.listError = error instanceof Error ? error.message : "문의 목록 조회 중 오류가 발생했습니다.";
  } finally {
    state.admin.loadingList = false;
    render();
  }
}

async function selectInquiry(inquiryId) {
  state.admin.selectedId = inquiryId;
  render();

  if (state.admin.detail?.id === inquiryId && !state.admin.detailError) {
    return;
  }

  await loadInquiryDetail(inquiryId);
}

async function loadInquiryDetail(inquiryId) {
  if (!state.admin.authenticated || !state.apiBaseUrl || !inquiryId) {
    return;
  }

  state.admin.loadingDetail = true;
  state.admin.detailError = "";
  render();

  try {
    const response = await adminRequest(`/api/v1/admin/inquiries/${encodeURIComponent(inquiryId)}`);
    if (!response) {
      return;
    }

    const body = await parseResponseBody(response);
    if (!response.ok) {
      state.admin.detailError = responseMessage(body, "문의 상세 정보를 불러오지 못했습니다.");
      state.admin.detail = null;
      return;
    }

    state.admin.detail = body;
    syncUpdateForm(body);
  } catch (error) {
    state.admin.detailError = error instanceof Error ? error.message : "문의 상세 조회 중 오류가 발생했습니다.";
    state.admin.detail = null;
  } finally {
    state.admin.loadingDetail = false;
    render();
  }
}

async function updateInquiryStatus() {
  if (!state.admin.authenticated || !state.admin.detail) {
    return;
  }

  if (state.admin.updateStatus === "완료됨" && !state.admin.updateResolution.trim()) {
    state.admin.updateMessage = {
      type: "warn",
      text: "완료됨으로 바꿀 때는 처리 결과를 입력해야 합니다.",
    };
    render();
    return;
  }

  state.admin.updateSubmitting = true;
  state.admin.updateMessage = null;
  render();

  try {
    const payload = {
      status: state.admin.updateStatus,
    };
    if (state.admin.updateStatus === "완료됨") {
      payload.resolution = state.admin.updateResolution.trim();
    }

    const response = await adminRequest(
      `/api/v1/admin/inquiries/${encodeURIComponent(state.admin.detail.id)}`,
      {
        method: "PATCH",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify(payload),
      },
    );
    if (!response) {
      return;
    }

    const body = await parseResponseBody(response);
    if (!response.ok) {
      state.admin.updateMessage = {
        type: response.status >= 500 ? "error" : "warn",
        text: responseMessage(body, "문의 상태 변경에 실패했습니다."),
      };
      return;
    }

    const inquiry = body?.inquiry;
    state.admin.detail = inquiry;
    syncUpdateForm(inquiry);
    patchInquiryListItem(inquiry);
    state.admin.updateMessage = {
      type: "ok",
      text: typeof body?.message === "string" ? body.message : "문의 상태가 반영되었습니다.",
    };

    if (state.admin.filterStatus && inquiry?.status !== state.admin.filterStatus) {
      await loadInquiries({ reset: true });
    }
  } catch (error) {
    state.admin.updateMessage = {
      type: "error",
      text: error instanceof Error ? error.message : "문의 상태 변경 중 오류가 발생했습니다.",
    };
  } finally {
    state.admin.updateSubmitting = false;
    render();
  }
}

async function adminRequest(path, options = {}) {
  const response = await fetch(apiUrl(path), {
    ...options,
    credentials: "include",
  });

  if (response.status === 401) {
    state.admin = {
      ...makeAdminState(),
      initialized: true,
      authMessage: "세션이 만료되었습니다. 다시 로그인해주세요.",
    };
    render();
    return null;
  }

  return response;
}

function patchInquiryListItem(inquiry) {
  if (!inquiry || !inquiry.id) {
    return;
  }

  state.admin.items = state.admin.items.map((item) => {
    if (item?.id !== inquiry.id) {
      return item;
    }

    return {
      ...item,
      status: inquiry.status,
      created_at: inquiry.created_at,
      title: inquiry.title,
      name: inquiry.name,
      email: inquiry.email,
      phone: inquiry.phone,
    };
  });
}

function syncUpdateForm(inquiry) {
  state.admin.updateStatus = inquiry?.status || STATUS_OPTIONS[0];
  state.admin.updateResolution = inquiry?.resolution || "";
}

function apiUrl(path) {
  if (!state.apiBaseUrl) {
    throw new Error("백엔드 API 주소가 설정되지 않았습니다.");
  }
  return `${state.apiBaseUrl}${path}`;
}

async function parseResponseBody(response) {
  const text = await response.text();
  if (!text) {
    return null;
  }

  try {
    return JSON.parse(text);
  } catch (_error) {
    return text;
  }
}

function responseMessage(payload, fallback) {
  if (typeof payload === "string" && payload.trim()) {
    return payload;
  }

  if (payload && typeof payload === "object") {
    if (typeof payload.message === "string" && payload.message.trim()) {
      return payload.message;
    }

    if (typeof payload.detail === "string" && payload.detail.trim()) {
      return payload.detail;
    }

    if (payload.detail && typeof payload.detail === "object") {
      if (typeof payload.detail.message === "string" && payload.detail.message.trim()) {
        return payload.detail.message;
      }
    }

    if (Array.isArray(payload.detail)) {
      return payload.detail
        .map((item) => {
          if (!item || typeof item !== "object") {
            return "";
          }
          const path = Array.isArray(item.loc) ? item.loc.slice(1).join(".") : "";
          const message = typeof item.msg === "string" ? item.msg : "";
          return [path, message].filter(Boolean).join(": ");
        })
        .filter(Boolean)
        .join(", ");
    }
  }

  return fallback;
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function formatDate(value) {
  if (!value) {
    return "-";
  }

  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }

  return new Intl.DateTimeFormat("ko-KR", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(date);
}

function renderNotice(notice) {
  if (!notice) {
    return "";
  }

  return `<div class="notice ${escapeHtml(notice.type)}">${escapeHtml(notice.text)}</div>`;
}

function render() {
  root.innerHTML = `
    <main class="shell">
      <section class="masthead">
        <div class="masthead-row">
          <div>
            <p class="eyebrow">Minimal Frontend</p>
            <h1>Smart Timelabs Onboarding</h1>
            <p>공개 문의 등록과 관리자 처리만 남긴 가장 얇은 정적 프론트엔드입니다. Vercel에 그대로 올리고 Cloud Run API만 연결하면 됩니다.</p>
          </div>
          <nav class="nav" aria-label="Primary">
            <a href="/" class="nav-link ${state.route === ROUTE_HOME ? "is-active" : ""}" data-route="/">문의 등록</a>
            <a href="/admin" class="nav-link ${state.route === ROUTE_ADMIN ? "is-active" : ""}" data-route="/admin">관리자</a>
          </nav>
        </div>
      </section>

      <section class="page-grid">
        ${renderConfigPanel()}
        ${state.route === ROUTE_ADMIN ? renderAdminPage() : renderPublicPage()}
      </section>
    </main>
  `;
}

function renderConfigPanel() {
  const apiBaseUrl = state.apiBaseUrl || "미설정";
  const panelNotice = renderNotice(state.configNotice);

  return `
    <section class="panel">
      <div class="panel-header">
        <div>
          <p class="eyebrow">Runtime Config</p>
          <h2>백엔드 연결</h2>
        </div>
        <span class="pill">${escapeHtml(apiBaseUrl)}</span>
      </div>
      ${panelNotice}
      <form class="stack" data-form="config">
        <div class="field">
          <label for="api-base-url">Cloud Run API 주소</label>
          <input
            id="api-base-url"
            name="apiBaseUrl"
            type="url"
            placeholder="https://qna-backend-xxxxx.a.run.app"
            value="${escapeHtml(state.configDraft)}"
            spellcheck="false"
          />
        </div>
        <div class="split-actions">
          <p class="muted">운영에서는 Cloud Run URL을 넣고, 로컬에서는 기본값으로 <code>${escapeHtml(DEFAULT_LOCAL_API_BASE_URL)}</code>를 씁니다.</p>
          <div class="nav">
            <button type="submit" class="secondary-button">저장</button>
            <button type="button" class="ghost-button" data-action="reset-config">초기화</button>
          </div>
        </div>
      </form>
      <div class="panel-note">
        관리자 화면은 크로스 오리진 쿠키를 쓰므로 백엔드의 <code>BACKEND_ALLOWED_ORIGINS</code>에 현재 프론트 도메인이 등록되어 있어야 합니다. 로컬 HTTP 테스트라면 <code>ADMIN_COOKIE_SECURE=false</code>가 필요합니다.
      </div>
    </section>
  `;
}

function renderPublicPage() {
  const disabled = !state.apiBaseUrl || state.publicSubmitting;

  return `
    <section class="panel">
      <div class="panel-header">
        <div>
          <p class="eyebrow">Public Inquiry</p>
          <h2>문의 등록</h2>
        </div>
      </div>
      <p class="muted">이름, 연락처, 제목, 내용을 입력하면 백엔드가 중복 등록을 검사하고 문의를 생성합니다.</p>
      <div class="panel-note">사용자용 상태 조회는 범위에서 제외했습니다. 등록 결과는 요청 ID로만 안내합니다.</div>
      <div style="height: 1rem"></div>
      ${renderNotice(state.publicNotice)}
      <form class="stack" data-form="public-inquiry">
        <div class="field-grid">
          <div class="field">
            <label for="name">이름</label>
            <input id="name" name="name" type="text" maxlength="100" value="${escapeHtml(state.publicForm.name)}" required />
          </div>
          <div class="field">
            <label for="email">이메일</label>
            <input id="email" name="email" type="email" value="${escapeHtml(state.publicForm.email)}" required />
          </div>
        </div>
        <div class="field-grid">
          <div class="field">
            <label for="phone">전화번호</label>
            <input id="phone" name="phone" type="tel" maxlength="30" value="${escapeHtml(state.publicForm.phone)}" required />
          </div>
          <div class="field">
            <label for="title">문의 제목</label>
            <input id="title" name="title" type="text" maxlength="200" value="${escapeHtml(state.publicForm.title)}" required />
          </div>
        </div>
        <div class="field">
          <label for="body">문의 내용</label>
          <textarea id="body" name="body" maxlength="5000" required>${escapeHtml(state.publicForm.body)}</textarea>
        </div>
        <div class="split-actions">
          <p class="muted">백엔드 미설정 상태에서는 제출할 수 없습니다.</p>
          <button class="primary-button" type="submit" ${disabled ? "disabled" : ""}>
            ${state.publicSubmitting ? "등록 중..." : "문의 등록"}
          </button>
        </div>
      </form>
    </section>
  `;
}

function renderAdminPage() {
  if (!state.apiBaseUrl) {
    return `
      <section class="panel">
        <div class="panel-header">
          <div>
            <p class="eyebrow">Admin Console</p>
            <h2>관리자</h2>
          </div>
        </div>
        <div class="empty-state">관리자 화면을 열기 전에 백엔드 API 주소를 먼저 설정해주세요.</div>
      </section>
    `;
  }

  if (state.admin.checkingSession && !state.admin.initialized) {
    return `
      <section class="panel">
        <div class="panel-header">
          <div>
            <p class="eyebrow">Admin Console</p>
            <h2>관리자 세션 확인 중</h2>
          </div>
        </div>
        <div class="empty-state">기존 관리자 세션을 확인하고 있습니다.</div>
      </section>
    `;
  }

  if (!state.admin.authenticated) {
    return `
      <section class="panel">
        <div class="panel-header">
          <div>
            <p class="eyebrow">Admin Console</p>
            <h2>관리자 로그인</h2>
          </div>
        </div>
        <p class="muted">별도 계정 시스템 없이 백엔드의 단일 관리자 비밀번호로 접근합니다.</p>
        <div style="height: 1rem"></div>
        ${state.admin.authMessage ? renderNotice({ type: "warn", text: state.admin.authMessage }) : ""}
        <form class="stack" data-form="admin-login">
          <div class="field">
            <label for="admin-password">비밀번호</label>
            <input
              id="admin-password"
              name="password"
              type="password"
              value="${escapeHtml(state.admin.loginPassword)}"
              autocomplete="current-password"
              required
            />
          </div>
          <div class="split-actions">
            <p class="muted">로그인 성공 시 세션 쿠키를 이용해 목록과 상세 화면을 호출합니다.</p>
            <button class="primary-button" type="submit" ${state.admin.loginSubmitting ? "disabled" : ""}>
              ${state.admin.loginSubmitting ? "로그인 중..." : "로그인"}
            </button>
          </div>
        </form>
      </section>
    `;
  }

  return `
    <section class="admin-grid">
      <section class="panel">
        <div class="panel-header">
          <div>
            <p class="eyebrow">Queue</p>
            <h2>문의 목록</h2>
          </div>
          <button class="ghost-button" type="button" data-action="logout">로그아웃</button>
        </div>
        <div class="toolbar">
          <div class="status-row" role="tablist" aria-label="Status filter">
            ${renderFilterChip("", "전체")}
            ${STATUS_OPTIONS.map((status) => renderFilterChip(status, status)).join("")}
          </div>
          ${state.admin.loadingList ? '<span class="muted">불러오는 중...</span>' : ""}
        </div>
        ${state.admin.listError ? renderNotice({ type: "error", text: state.admin.listError }) : ""}
        ${renderInquiryList()}
      </section>

      <section class="panel">
        <div class="panel-header">
          <div>
            <p class="eyebrow">Detail</p>
            <h2>문의 상세</h2>
          </div>
          ${state.admin.detail ? `<span class="pill">${escapeHtml(state.admin.detail.status)}</span>` : ""}
        </div>
        ${renderInquiryDetail()}
      </section>
    </section>
  `;
}

function renderFilterChip(status, label) {
  const active = state.admin.filterStatus === status;
  return `
    <button
      type="button"
      class="chip ${active ? "is-active" : ""}"
      data-action="set-filter"
      data-filter-status="${escapeHtml(status)}"
    >
      ${escapeHtml(label)}
    </button>
  `;
}

function renderInquiryList() {
  if (!state.admin.items.length) {
    return '<div class="empty-state">표시할 문의가 없습니다.</div>';
  }

  return `
    <div class="inquiry-list">
      ${state.admin.items
        .map((item) => {
          const active = item.id === state.admin.selectedId;
          return `
            <button
              type="button"
              class="inquiry-item ${active ? "is-active" : ""}"
              data-action="select-inquiry"
              data-inquiry-id="${escapeHtml(item.id)}"
            >
              <strong>${escapeHtml(item.title)}</strong>
              <div>${escapeHtml(item.name)} · ${escapeHtml(item.email)}</div>
              <div class="inquiry-meta">
                <span>${escapeHtml(item.status)}</span>
                <span>${escapeHtml(formatDate(item.created_at))}</span>
              </div>
            </button>
          `;
        })
        .join("")}
      ${
        state.admin.nextCursor
          ? `<button class="secondary-button" type="button" data-action="load-more" ${state.admin.loadingList ? "disabled" : ""}>더 보기</button>`
          : ""
      }
    </div>
  `;
}

function renderInquiryDetail() {
  if (state.admin.loadingDetail && !state.admin.detail) {
    return '<div class="empty-state">문의 상세를 불러오는 중입니다.</div>';
  }

  if (state.admin.detailError) {
    return renderNotice({ type: "error", text: state.admin.detailError });
  }

  if (!state.admin.detail) {
    return '<div class="empty-state">왼쪽 목록에서 문의를 선택해주세요.</div>';
  }

  const inquiry = state.admin.detail;
  const needsResolution = state.admin.updateStatus === "완료됨";

  return `
    <div class="detail-block">
      <dl class="detail-grid detail-card">
        <div>
          <dt>문의자</dt>
          <dd>${escapeHtml(inquiry.name)}</dd>
        </div>
        <div>
          <dt>연락처</dt>
          <dd>${escapeHtml(inquiry.phone)}</dd>
        </div>
        <div>
          <dt>이메일</dt>
          <dd>${escapeHtml(inquiry.email)}</dd>
        </div>
        <div>
          <dt>생성 시각</dt>
          <dd>${escapeHtml(formatDate(inquiry.created_at))}</dd>
        </div>
        <div>
          <dt>수정 시각</dt>
          <dd>${escapeHtml(formatDate(inquiry.updated_at))}</dd>
        </div>
        <div>
          <dt>Notion 페이지 ID</dt>
          <dd>${escapeHtml(inquiry.id)}</dd>
        </div>
      </dl>

      <div class="detail-card">
        <dt>문의 제목</dt>
        <dd>${escapeHtml(inquiry.title)}</dd>
      </div>

      <div class="detail-card">
        <dt>문의 내용</dt>
        <dd class="detail-body">${escapeHtml(inquiry.body)}</dd>
      </div>

      ${
        inquiry.resolution
          ? `
            <div class="detail-card">
              <dt>처리 결과</dt>
              <dd class="detail-body">${escapeHtml(inquiry.resolution)}</dd>
            </div>
          `
          : ""
      }

      <div class="detail-card">
        <div class="panel-header">
          <div>
            <p class="eyebrow">Update</p>
            <h3>상태 변경</h3>
          </div>
        </div>
        ${renderNotice(state.admin.updateMessage)}
        <form class="stack" data-form="admin-update">
          <div class="field">
            <label for="status">상태</label>
            <select id="status" name="status">
              ${STATUS_OPTIONS.map((status) => `<option value="${escapeHtml(status)}" ${state.admin.updateStatus === status ? "selected" : ""}>${escapeHtml(status)}</option>`).join("")}
            </select>
          </div>
          <div class="field">
            <label for="resolution">처리 결과 ${needsResolution ? "(필수)" : "(완료됨일 때만 사용)"}</label>
            <textarea
              id="resolution"
              name="resolution"
              placeholder="완료 처리 내용을 입력하세요."
              ${needsResolution ? "required" : ""}
            >${escapeHtml(state.admin.updateResolution)}</textarea>
          </div>
          <div class="split-actions">
            <p class="muted">"완료됨"으로 바꾸면 백엔드가 n8n 완료 워크플로우를 호출합니다.</p>
            <button class="primary-button" type="submit" ${state.admin.updateSubmitting ? "disabled" : ""}>
              ${state.admin.updateSubmitting ? "저장 중..." : "상태 저장"}
            </button>
          </div>
        </form>
      </div>
    </div>
  `;
}
