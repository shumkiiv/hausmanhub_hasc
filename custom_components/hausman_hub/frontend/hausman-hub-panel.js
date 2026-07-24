/* HausmanHub admin panel: climate overview, management, and full settings. */
const PANEL_API = "hausman_hub/v1/admin/panel";
const MODE_API = "hausman_hub/v1/admin/climate-mode";
const HOME_API = "hausman_hub/v1/admin/home-environment";
const WINDOWS_API = "hausman_hub/v1/admin/climate-room-signals";
const DRAFT_API = "hausman_hub/v1/admin/climate-drafts";
const SETUP_API = "hausman_hub/v1/admin/climate-drafts/current";
const DRAFT_VALIDATE_API = `${DRAFT_API}/validate`;
const DRAFT_SAVE_API = `${DRAFT_API}/save`;
const PROFILES_API = "hausman_hub/v1/admin/climate-profiles";
const SCHEDULE_API = "hausman_hub/v1/admin/climate-schedule";
const REFRESH_MS = 30000;

const PROFILE_CONTRACT = { name: "hausman-hub-climate-profile-update-request", version: 1 };
const SCHEDULE_CONTRACT = { name: "hausman-hub-climate-schedule-update-request", version: 1 };
const STRATEGY_ORDER = ["soft", "normal", "aggressive"];
const CONTOUR_MODE_ORDER = ["observe", "automatic"];
const ACTIVE_DEVICE_TYPES = new Set([
  "air_conditioner", "radiator_thermostat", "humidifier", "floor_heating",
]);
const SENSOR_DEVICE_TYPES = new Set(["temperature_sensor", "humidity_sensor"]);
const ROOM_PRESENCE_DEVICE_CLASSES = new Set(["motion", "occupancy", "presence"]);
const TIME_PATTERN = /^([01]\d|2[0-3]):[0-5]\d$/;
const PANEL_SECTIONS = [
  { id: "overview", label: "Обзор" },
  { id: "contour", label: "Контур" },
  { id: "profiles", label: "Профили" },
  { id: "schedule", label: "Расписание" },
  { id: "home", label: "Дом" },
  { id: "windows", label: "Сигналы комнат" },
];
const READINESS_LABELS = {
  ready: "Система готова к управлению",
  not_ready: "Нужна настройка системы",
  unavailable: "Система временно недоступна",
  disabled: "Управление климатом выключено",
};

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined && text !== null) node.textContent = String(text);
  return node;
}

function requestId(prefix) {
  const random = Math.random().toString(36).slice(2, 10);
  return `${prefix}-${Date.now()}-${random}`.slice(0, 64);
}

function selectField(options, current, onChange) {
  const select = el("select");
  options.forEach((item) => {
    const option = el("option", null, item.label);
    option.value = item.value;
    select.appendChild(option);
  });
  select.value = current === null || current === undefined ? "" : String(current);
  select.addEventListener("change", onChange);
  return select;
}

function numberField(value, min, max, step, onChange) {
  const input = el("input");
  input.type = "number";
  input.min = min;
  input.max = max;
  input.step = step;
  input.value = value;
  input.addEventListener("input", onChange);
  return input;
}

function setAttr(node, name, value) {
  if (typeof node.setAttribute === "function") node.setAttribute(name, String(value));
  else node[name] = String(value);
}

function focusNode(node) {
  if (node && typeof node.focus === "function") node.focus();
}

function normalizedText(value) {
  return String(value || "").trim().toLocaleLowerCase("ru");
}

class HausmanHubPanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._hass = null;
    this._data = null;
    this._settings = { mode: null, home: null, windows: null, setup: null };
    this._error = false;
    this._busy = false;
    this._notice = "";
    this._timer = null;
    this._shell = null;
    this._activeSection = null;
    this._expandedWizardRooms = new Set();
    this._dirty = {
      wizard: false, home: false, windows: false, profiles: false, schedule: false, mode: false,
    };
    this._wizard = {
      open: false,
      loading: false,
      options: null,
      optionsError: false,
      draft: null,
      validation: null,
      fingerprint: null,
      setupRevision: null,
    };
    this._wizardFields = null;
    this._wizardIssues = null;
    this._wizardButtons = null;
    this._onVisible = () => {
      if (!document.hidden) this._load();
    };
  }

  set hass(value) {
    const first = this._hass === null;
    this._hass = value;
    if (first) this._load();
  }

  connectedCallback() {
    this._timer = setInterval(() => this._load(), REFRESH_MS);
    document.addEventListener("visibilitychange", this._onVisible);
    this._render();
  }

  disconnectedCallback() {
    if (this._timer) clearInterval(this._timer);
    this._timer = null;
    document.removeEventListener("visibilitychange", this._onVisible);
  }

  async _load() {
    if (!this._hass) return;
    try {
      const results = await Promise.all([
        this._hass.callApi("GET", PANEL_API),
        this._hass.callApi("GET", MODE_API).catch(() => null),
        this._hass.callApi("GET", HOME_API).catch(() => null),
        this._hass.callApi("GET", WINDOWS_API).catch(() => null),
        this._hass.callApi("GET", SETUP_API).catch(() => null),
      ]);
      this._data = results[0];
      this._settings = {
        mode: results[1],
        home: results[2],
        windows: results[3],
        setup: results[4],
      };
      this._error = false;
    } catch (error) {
      this._error = true;
    }
    this._render();
  }

  async _post(path, payload, confirmText) {
    if (this._busy) return false;
    if (confirmText && !window.confirm(confirmText)) return false;
    this._busy = true;
    this._notice = "";
    this._render();
    try {
      const receipt = await this._hass.callApi("POST", path, payload);
      this._notice = this._receiptText(receipt);
      this._error = false;
      await this._load();
      return true;
    } catch (error) {
      this._notice = "Действие не выполнено. Проверьте состояние климата.";
      this._render();
      return false;
    } finally {
      this._busy = false;
      this._render();
    }
  }

  async _save(section, path, payload, confirmText, successText, conflictText) {
    if (this._busy) return;
    if (confirmText && !window.confirm(confirmText)) return;
    this._busy = true;
    this._notice = "";
    this._render();
    try {
      await this._hass.callApi("POST", path, payload);
      this._dirty[section] = false;
      this._notice = successText;
      this._error = false;
    } catch (error) {
      this._dirty[section] = false;
      this._notice = error && error.status === 409 ? conflictText
        : "Сохранить не удалось. Проверьте значения и состояние климата.";
    } finally {
      this._busy = false;
    }
    await this._load();
  }

  _receiptText(receipt) {
    const statuses = {
      confirmed: "Применено и подтверждено наблюдением.",
      pending: "Команды отправлены, подтверждение ещё проверяется.",
      partial: "Применено частично.",
      unavailable: "Состояние климатического контура недоступно.",
      up_to_date: "Состояние уже соответствует сохранённому.",
      denied: "Действие отклонено защитой.",
      failed: "Действие не выполнено.",
    };
    const status = receipt && typeof receipt.status === "string" ? receipt.status : "";
    return statuses[status] || `Статус операции: ${status || "неизвестен"}.`;
  }

  _names(section, code) {
    const names = this._data && this._data.snapshot && this._data.snapshot.display_names;
    const group = names && names[section];
    return (group && group[code]) || code;
  }

  _render() {
    if (!this.shadowRoot) return;
    this._ensureShell();
    const shell = this._shell;
    shell.notice.textContent = "";
    shell.notice.style.display = "none";
    if (this._error) {
      shell.banner.style.display = "";
      this._clearDynamic();
      return;
    }
    shell.banner.style.display = "none";
    if (!this._data) {
      shell.loading.style.display = "";
      this._clearDynamic();
      return;
    }
    shell.loading.style.display = "none";
    if (this._notice) {
      shell.notice.textContent = this._notice;
      shell.notice.style.display = "";
    }
    this._chooseInitialSection();
    this._renderHeaderStatus(this._data.readiness);
    this._renderReadiness(shell.readiness, this._data.readiness);
    const snapshot = this._data.snapshot;
    this._renderOverviewSummary(shell.summary, this._settings.setup, snapshot);
    if (!this._dirty.wizard) {
      this._renderContour(shell.contour, snapshot, this._settings.setup);
    }
    this._renderRooms(shell.rooms, snapshot);
    if (!this._dirty.profiles) this._renderProfiles(shell.profiles, this._settings.setup);
    if (!this._dirty.schedule) this._renderSchedule(shell.schedule, this._settings);
    if (!this._dirty.home) this._renderHome(shell.home, this._settings.home);
    if (!this._dirty.windows) this._renderWindows(shell.windows, this._settings.windows);
    this._syncSectionVisibility();
  }

  _ensureShell() {
    if (this._shell) return;
    const root = this.shadowRoot;
    const style = el("style");
    style.textContent = `
      :host { display:block; box-sizing:border-box; width:100%; max-width:1440px; margin:0 auto;
        padding:28px 30px 48px; overflow-x:hidden; font-family:var(--primary-font-family,sans-serif);
        color:var(--primary-text-color,#212121); background:var(--primary-background-color,#fafafa); }
      *, *::before, *::after { box-sizing:border-box; }
      [hidden] { display:none !important; }
      h1 { margin:0; font-size:clamp(26px,3vw,36px); line-height:1.1; letter-spacing:-.02em; }
      h2 { margin:0 0 14px; font-size:22px; line-height:1.25; }
      h3 { margin:0; font-size:17px; line-height:1.3; }
      h4 { margin:16px 0 8px; font-size:13px; line-height:1.3; text-transform:uppercase;
        letter-spacing:.05em; color:var(--secondary-text-color,#727272); }
      .page-header { margin-bottom:18px; }
      .subtitle { margin:7px 0 10px; color:var(--secondary-text-color,#727272); font-size:15px; }
      .status-pill { display:inline-flex; align-items:center; min-height:32px; max-width:100%;
        padding:6px 12px; border-radius:999px; font-size:13px; font-weight:600;
        background:var(--secondary-background-color,#eceff1); color:var(--primary-text-color,#212121); }
      .status-pill::before { content:""; width:8px; height:8px; margin-right:8px; border-radius:50%;
        background:var(--warning-color,#ff9800); }
      .status-pill[data-status="ready"]::before { background:var(--success-color,#43a047); }
      .status-pill[data-status="unavailable"]::before { background:var(--error-color,#db4437); }
      .tab-bar { display:flex; gap:6px; margin:0 -4px 22px; padding:4px; overflow-x:auto;
        overscroll-behavior-inline:contain; scrollbar-width:thin; border-bottom:1px solid var(--divider-color,#ddd); }
      .tab { flex:0 0 auto; min-height:42px; margin:0; padding:9px 15px; border-radius:11px 11px 0 0;
        background:transparent; color:var(--secondary-text-color,#616161); font-weight:600; white-space:nowrap; }
      .tab[aria-current="page"] { background:var(--primary-color,#03a9f4); color:var(--text-primary-color,#fff); }
      .tab.is-dirty::after { content:" •"; color:currentColor; }
      section { min-width:0; }
      .section-intro { margin:-7px 0 18px; max-width:760px; color:var(--secondary-text-color,#727272);
        font-size:14px; line-height:1.5; }
      .muted { color:var(--secondary-text-color,#727272); font-size:13px; line-height:1.45; }
      .banner, .notice { padding:12px 15px; border-radius:12px; margin:0 0 16px; color:#fff; }
      .banner { background:var(--error-color,#db4437); }
      .notice { background:var(--success-color,#43a047); }
      .loading { min-height:72px; padding:20px; border-radius:16px; border:1px solid var(--divider-color,#ddd);
        background:var(--card-background-color,#fff); }
      .cards, .room-card-grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(280px,1fr)); gap:16px; }
      .card { min-width:0; padding:20px; border:1px solid var(--divider-color,#ddd); border-radius:18px;
        background:var(--card-background-color,#fff); box-shadow:var(--ha-card-box-shadow,0 2px 9px rgba(0,0,0,.08)); }
      .hero { padding:clamp(20px,3vw,30px); border-color:color-mix(in srgb,var(--primary-color,#03a9f4) 28%,var(--divider-color,#ddd));
        background:linear-gradient(135deg,color-mix(in srgb,var(--primary-color,#03a9f4) 10%,var(--card-background-color,#fff)),
        var(--card-background-color,#fff) 58%); box-shadow:0 8px 28px rgba(0,0,0,.12); }
      .hero-status { margin:0 0 16px; font-size:clamp(21px,2.4vw,28px); font-weight:700; }
      .overview-summary { display:grid; grid-template-columns:repeat(auto-fit,minmax(150px,1fr));
        gap:12px; margin:16px 0 24px; }
      .summary-item { min-width:0; padding:14px 16px; border:1px solid var(--divider-color,#ddd);
        border-radius:16px; background:var(--card-background-color,#fff); }
      .summary-value { display:block; margin-top:4px; font-size:18px; font-weight:650; overflow-wrap:anywhere; }
      .room-metrics { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:10px; margin:14px 0; }
      .metric { padding:12px; border-radius:13px; background:var(--secondary-background-color,#f2f4f5); }
      .metric strong { display:block; margin-top:3px; font-size:22px; line-height:1.1; }
      .row { display:flex; justify-content:space-between; align-items:flex-start; gap:12px;
        padding:5px 0; font-size:14px; }
      .row > :first-child { color:var(--secondary-text-color,#727272); }
      .value { max-width:62%; text-align:right; font-weight:600; overflow-wrap:anywhere; }
      button { min-height:40px; max-width:100%; margin:8px 8px 0 0; padding:9px 15px;
        border:0; border-radius:11px; font:inherit; font-weight:600; cursor:pointer;
        background:var(--primary-color,#03a9f4); color:var(--text-primary-color,#fff); }
      button.secondary { border:1px solid var(--divider-color,#ccc);
        background:var(--secondary-background-color,#eceff1); color:var(--primary-text-color,#212121); }
      button:disabled { opacity:1; cursor:not-allowed; background:var(--disabled-color,#bdbdbd);
        color:var(--disabled-text-color,var(--secondary-text-color,#616161)); }
      button:focus-visible, input:focus-visible, select:focus-visible {
        outline:3px solid color-mix(in srgb,var(--primary-color,#03a9f4) 58%,transparent);
        outline-offset:2px; }
      input, select { min-height:42px; max-width:100%; padding:8px 10px; border:1px solid var(--divider-color,#bbb);
        border-radius:11px; font:inherit; color:var(--primary-text-color,#212121);
        background:var(--card-background-color,#fff); }
      input[type="number"] { width:110px; }
      input[type="text"], input[type="search"] { width:min(420px,100%); }
      input[type="time"] { width:150px; }
      input[type="checkbox"] { width:18px; min-height:18px; height:18px; margin:2px 0 0; padding:0; accent-color:var(--primary-color,#03a9f4); }
      select { width:min(420px,100%); }
      label { display:block; margin:8px 0 2px; font-size:14px; }
      label.form-field { display:grid; grid-template-columns:minmax(180px,290px) minmax(0,420px);
        align-items:center; gap:12px 18px; margin:12px 0; }
      label.checkbox-field, label.device-option { display:flex; align-items:flex-start; gap:10px; margin:9px 0; }
      label.checkbox-field > input, label.device-option > input { order:-1; flex:0 0 auto; }
      .field-help { grid-column:2; margin-top:-7px; }
      .reasons { margin:10px 0 0; font-size:13px; }
      .chip { display:inline-flex; align-items:center; min-height:25px; margin:2px 5px 2px 0; padding:3px 9px;
        border-radius:999px; font-size:12px; background:var(--secondary-background-color,#e5e5e5);
        color:var(--primary-text-color,#212121); overflow-wrap:anywhere; }
      .room-block { margin-top:14px; padding:0; overflow:hidden; border:1px solid var(--divider-color,#ddd);
        border-radius:16px; background:var(--card-background-color,#fff); }
      .room-summary { display:flex; align-items:center; gap:12px; min-height:64px; padding:12px 14px;
        background:color-mix(in srgb,var(--secondary-background-color,#f2f4f5) 70%,var(--card-background-color,#fff)); }
      .room-summary .checkbox-field { flex:1 1 auto; min-width:180px; margin:0; font-size:15px; font-weight:650; }
      .room-summary-meta { flex:1 1 260px; min-width:0; font-size:12px; color:var(--secondary-text-color,#727272); }
      .room-expander { flex:0 0 auto; margin:0; }
      .room-error-badge { display:inline-flex; margin-top:4px; padding:2px 8px; border-radius:999px;
        color:#fff; background:var(--error-color,#db4437); font-size:11px; font-weight:700; }
      .room-editor { padding:8px 18px 20px; border-top:1px solid var(--divider-color,#ddd); }
      .entity-search { width:100%; margin:7px 0 10px; }
      .entity-groups { display:grid; grid-template-columns:repeat(auto-fit,minmax(230px,1fr)); gap:10px 18px; }
      .entity-group { min-width:0; padding:9px 12px; border:1px solid var(--divider-color,#ddd); border-radius:13px; }
      .entity-label { min-width:0; line-height:1.3; overflow-wrap:anywhere; }
      .entity-label strong, .entity-label small { display:block; }
      .entity-label small { margin-top:2px; color:var(--secondary-text-color,#727272); font-size:11px; }
      .wizard-issues, .field-error { margin-top:7px; color:var(--error-color,#db4437); font-size:13px; line-height:1.4; }
      .wizard-success { margin-top:9px; color:var(--success-color,#43a047); font-size:13px; }
      .action-help { margin-top:8px; }
      .unsaved { display:inline-flex; align-items:center; min-height:28px; margin:10px 0 0; padding:4px 10px;
        border-radius:999px; color:var(--warning-color,#ef6c00);
        background:color-mix(in srgb,var(--warning-color,#ef6c00) 12%,transparent); font-size:12px; font-weight:650; }
      .actions { display:flex; flex-wrap:wrap; align-items:flex-start; gap:2px; margin-top:16px;
        padding-top:14px; border-top:1px solid var(--divider-color,#ddd); }
      .profile-room { margin-bottom:16px; }
      .profile-columns { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:14px; margin-top:14px; }
      .profile-block { min-width:0; padding:14px; border-radius:14px; background:var(--secondary-background-color,#f2f4f5); }
      .profile-block h4 { margin-top:0; color:var(--primary-text-color,#212121); }
      .signal-room { margin-bottom:16px; }
      .empty-state { padding:22px; text-align:center; }
      @media (max-width:640px) {
        :host { padding:16px 16px 36px; }
        .tab-bar { margin-right:-16px; padding-right:16px; }
        .overview-summary { grid-template-columns:minmax(0,1fr); }
        .cards, .room-card-grid, .profile-columns { grid-template-columns:minmax(0,1fr); }
        label.form-field { grid-template-columns:minmax(0,1fr); gap:5px; }
        .field-help { grid-column:1; margin-top:-2px; }
        label.form-field > input, label.form-field > select { width:100%; max-width:none; }
        .room-summary { flex-wrap:wrap; }
        .room-summary .checkbox-field { min-width:0; }
        .room-summary-meta { order:3; flex-basis:100%; }
        .room-expander { margin-left:auto; }
        .room-editor { padding:8px 14px 18px; }
        .entity-groups { grid-template-columns:minmax(0,1fr); }
        .actions { flex-direction:column; }
        .actions button { width:100%; margin-right:0; }
      }
      @media (max-width:380px) {
        :host { padding-left:14px; padding-right:14px; }
        .card { padding:16px; }
        .room-summary { padding:11px 12px; }
        .room-expander { width:100%; margin:2px 0 0; }
        .room-metrics { grid-template-columns:minmax(0,1fr); }
      }
    `;
    root.appendChild(style);
    const container = el("main");
    root.appendChild(container);
    const header = el("header", "page-header");
    header.appendChild(el("h1", null, "HausmanHub"));
    header.appendChild(
      el("div", "subtitle", "Климат, комнаты и сценарии — в одном месте")
    );
    const statusPill = el("div", "status-pill", "Загрузка состояния…");
    setAttr(statusPill, "role", "status");
    header.appendChild(statusPill);
    container.appendChild(header);
    const banner = el("div", "banner", "Данные HausmanHub недоступны. Проверьте интеграцию и повторите.");
    setAttr(banner, "role", "alert");
    banner.style.display = "none";
    container.appendChild(banner);
    const notice = el("div", "notice");
    setAttr(notice, "role", "status");
    setAttr(notice, "aria-live", "polite");
    notice.style.display = "none";
    container.appendChild(notice);
    const loading = el("div", "loading muted", "Загрузка данных HausmanHub…");
    loading.style.display = "none";
    container.appendChild(loading);
    const nav = el("nav", "tab-bar");
    setAttr(nav, "aria-label", "Разделы HausmanHub");
    const tabs = {};
    PANEL_SECTIONS.forEach((section, index) => {
      const button = el("button", "tab", section.label);
      button.type = "button";
      setAttr(button, "data-section", section.id);
      setAttr(button, "aria-controls", `hausman-${section.id}`);
      button.addEventListener("click", () => this._activateSection(section.id));
      button.addEventListener("keydown", (event) => this._handleTabKey(event, index));
      nav.appendChild(button);
      tabs[section.id] = button;
    });
    container.appendChild(nav);
    const sectionNodes = {};
    PANEL_SECTIONS.forEach((section) => {
      const node = el("section");
      node.id = `hausman-${section.id}`;
      setAttr(node, "aria-label", section.label);
      container.appendChild(node);
      sectionNodes[section.id] = node;
    });
    const readiness = el("div");
    const summary = el("div");
    const rooms = el("div");
    sectionNodes.overview.appendChild(readiness);
    sectionNodes.overview.appendChild(summary);
    sectionNodes.overview.appendChild(rooms);
    this._shell = {
      banner, notice, loading, statusPill, tabs, sectionNodes,
      readiness, summary, rooms,
      contour: sectionNodes.contour,
      profiles: sectionNodes.profiles,
      schedule: sectionNodes.schedule,
      home: sectionNodes.home,
      windows: sectionNodes.windows,
    };
  }

  _clearDynamic() {
    ["readiness", "summary", "rooms"].forEach((name) => {
      this._shell[name].innerHTML = "";
    });
    if (!this._dirty.wizard) this._shell.contour.innerHTML = "";
    ["profiles", "schedule", "home", "windows"].forEach((name) => {
      if (!this._dirty[name]) this._shell[name].innerHTML = "";
    });
  }

  _chooseInitialSection() {
    if (this._activeSection) return;
    const setup = this._settings.setup;
    this._activeSection = setup && setup.status === "not_configured" ? "contour" : "overview";
  }

  _activateSection(section, focus = false) {
    if (!PANEL_SECTIONS.some((item) => item.id === section)) return;
    this._activeSection = section;
    this._syncSectionVisibility();
    if (focus) focusNode(this._shell && this._shell.tabs[section]);
  }

  _handleTabKey(event, index) {
    const key = event && event.key;
    let next = null;
    if (key === "ArrowRight") next = (index + 1) % PANEL_SECTIONS.length;
    if (key === "ArrowLeft") next = (index - 1 + PANEL_SECTIONS.length) % PANEL_SECTIONS.length;
    if (key === "Home") next = 0;
    if (key === "End") next = PANEL_SECTIONS.length - 1;
    if (next === null) return;
    if (event && typeof event.preventDefault === "function") event.preventDefault();
    this._activateSection(PANEL_SECTIONS[next].id, true);
  }

  _syncSectionVisibility() {
    if (!this._shell) return;
    const dirtyBySection = {
      contour: this._dirty.wizard,
      profiles: this._dirty.profiles,
      schedule: this._dirty.schedule,
      home: this._dirty.home,
      windows: this._dirty.windows,
    };
    PANEL_SECTIONS.forEach((section) => {
      const active = section.id === this._activeSection;
      this._shell.sectionNodes[section.id].hidden = !active;
      const tab = this._shell.tabs[section.id];
      setAttr(tab, "aria-current", active ? "page" : "false");
      tab.className = `tab${dirtyBySection[section.id] ? " is-dirty" : ""}`;
      tab.title = dirtyBySection[section.id] ? "Есть несохранённые изменения" : "";
    });
  }

  _renderHeaderStatus(readiness) {
    const status = readiness && readiness.status;
    this._shell.statusPill.textContent = READINESS_LABELS[status] || "Состояние уточняется";
    setAttr(this._shell.statusPill, "data-status", status || "unknown");
  }

  _renderOverviewSummary(container, setup, snapshot) {
    container.innerHTML = "";
    if (!setup && !snapshot) return;
    const summary = el("div", "overview-summary");
    const add = (label, value) => {
      const item = el("div", "summary-item");
      item.appendChild(el("span", "muted", label));
      item.appendChild(el("strong", "summary-value", value));
      summary.appendChild(item);
    };
    const setupSummary = (setup && setup.summary) || {};
    add("Активный контур", (setup && setup.name) || "Не настроен");
    add(
      "Режим контура",
      setup && setup.mode
        ? (((setup.display_names || {}).modes || {})[setup.mode] || setup.mode)
        : "Нет данных"
    );
    add("Комнат", setupSummary.room_count === undefined ? 0 : setupSummary.room_count);
    add("Устройств", setupSummary.device_count === undefined ? 0 : setupSummary.device_count);
    container.appendChild(summary);
  }

  _markDirty(section, indicator = null) {
    this._dirty[section] = true;
    if (indicator) indicator.hidden = false;
    this._syncSectionVisibility();
  }

  _bridgeModeName(code) {
    const labels = {
      managed: "Управляемый",
      disabled: "Выключен",
      shadow: "Наблюдение",
      canary: "Ограниченное управление",
    };
    return labels[code] || "Неизвестен";
  }

  _roomModeName(code) {
    const translated = this._names("room_modes", code);
    if (translated && translated !== code) return translated;
    const labels = {
      automatic: "Автоматический",
      observe: "Наблюдение",
      manual: "Ручной",
      disabled: "Выключен",
    };
    return labels[code] || "Нет данных";
  }

  _dataStatusName(code) {
    const translated = this._names("data_statuses", code);
    if (translated && translated !== code) return translated;
    const labels = {
      current: "Свежие данные",
      stale: "Данные устарели",
      unavailable: "Нет данных",
      missing: "Нет данных",
      suspect: "Данные требуют проверки",
    };
    return labels[code] || "Нет данных";
  }

  _renderReadiness(container, readiness) {
    container.innerHTML = "";
    container.appendChild(el("h2", null, "Обзор"));
    container.appendChild(
      el("div", "section-intro", "Текущее состояние климатического контура и комнат.")
    );
    const card = el("div", "card hero");
    card.appendChild(
      el("div", "hero-status", READINESS_LABELS[readiness.status] || "Состояние уточняется")
    );
    const modeRow = el("div", "row");
    modeRow.appendChild(el("span", null, "Режим управления"));
    modeRow.appendChild(el("span", "value", this._bridgeModeName(readiness.bridge_mode)));
    card.appendChild(modeRow);
    if (Array.isArray(readiness.reasons) && readiness.reasons.length) {
      const reasons = el("div", "reasons");
      readiness.reasons.forEach((reason) => {
        reasons.appendChild(el("span", "chip", this._names("blocked_reasons", reason)));
      });
      card.appendChild(reasons);
    }
    const modeSettings = this._settings.mode;
    if (modeSettings) {
      const switchRow = el("div", "row");
      const managed = modeSettings.mode === "managed";
      switchRow.appendChild(
        el("span", null, managed ? "Управление включено" : "Управление выключено")
      );
      const button = el(
        "button",
        managed ? "secondary" : null,
        managed ? "Выключить управление" : "Включить управление"
      );
      button.disabled = this._busy || (!managed && modeSettings.contour_configured !== true);
      button.addEventListener("click", () => {
        const target = managed ? "disabled" : "managed";
        this._save(
          "mode",
          MODE_API,
          { mode: target, expected_mode: modeSettings.mode, confirm: managed ? null : true },
          managed
            ? "Выключить управление климатом? Устройства больше не будут получать команды от HausmanHub."
            : "Включить управление климатом от HausmanHub? Убедитесь, что прежний модуль не управляет теми же устройствами.",
          managed ? "Управление климатом выключено." : "Управление климатом включено.",
          "Режим уже изменён в другом окне. Данные обновлены, повторите действие."
        );
      });
      switchRow.appendChild(button);
      card.appendChild(switchRow);
      if (!managed && modeSettings.contour_configured !== true) {
        card.appendChild(
          el("div", "muted", "Включение станет доступно после настройки климатического контура.")
        );
      }
    }
    container.appendChild(card);
  }

  _renderRooms(container, snapshot) {
    container.innerHTML = "";
    if (!snapshot) {
      const card = el(
        "div",
        "card empty-state muted",
        "Данные комнат появятся после настройки и запуска климатического контура."
      );
      container.appendChild(card);
      return;
    }
    container.appendChild(el("h2", null, "Комнаты"));
    const grid = el("div", "cards");
    (snapshot.rooms || []).forEach((room) => {
      const card = el("div", "card");
      card.appendChild(el("h3", null, room.name));
      const metrics = el("div", "room-metrics");
      const temperature = el("div", "metric");
      temperature.appendChild(el("span", "muted", "Температура"));
      temperature.appendChild(el("strong", null, this._temp(room.temperature)));
      metrics.appendChild(temperature);
      const humidity = el("div", "metric");
      humidity.appendChild(el("span", "muted", "Влажность"));
      humidity.appendChild(el("strong", null, this._humidity(room.humidity)));
      metrics.appendChild(humidity);
      card.appendChild(metrics);
      this._row(card, "Цель", this._temp(room.target_temperature));
      const activeProfile = room.active_profile || (room.targets && room.targets.profile);
      this._row(
        card,
        "Профиль и режим",
        [
          activeProfile && this._names("profiles", activeProfile),
          this._roomModeName(room.mode),
        ].filter(Boolean).join(" · ") || "Нет данных"
      );
      const dataStatus = this._dataStatusName(room.actual && room.actual.data_status);
      this._row(card, "Свежесть данных", dataStatus || "Нет данных");
      const devices = room.devices || [];
      const activeDevices = devices.filter((device) => (
        !["off", "idle", "unavailable", "unknown"].includes(device.state)
      )).length;
      this._row(
        card,
        "Устройства",
        devices.length ? `${devices.length}, активно: ${activeDevices}` : "Нет данных"
      );
      grid.appendChild(card);
    });
    if (!(snapshot.rooms || []).length) {
      grid.appendChild(el("div", "card empty-state muted", "Комнаты пока не добавлены."));
    }
    container.appendChild(grid);
  }

  _renderContourWizard(container, setup) {
    if (!setup) {
      container.appendChild(el("div", "card muted", "Настройка контура временно недоступна."));
      return;
    }
    const configured = setup.status !== "not_configured";
    if (configured && !this._wizard.open) {
      const card = el("div", "card");
      card.appendChild(el("h3", null, setup.name || "Климатический контур"));
      const modes = (setup.display_names && setup.display_names.modes) || {};
      this._row(card, "Режим", modes[setup.mode] || setup.mode);
      const summary = setup.summary || {};
      this._row(card, "Комнат", summary.room_count || 0);
      this._row(card, "Устройств", summary.device_count || 0);
      (setup.issues || []).forEach((issue) => {
        if (issue && issue.message) card.appendChild(el("div", "wizard-issues", issue.message));
      });
      const edit = el("button", null, "Изменить контур");
      edit.disabled = this._busy || setup.editing_allowed !== true;
      edit.addEventListener("click", () => this._openWizard(setup));
      card.appendChild(edit);
      if (setup.editing_allowed !== true) {
        card.appendChild(
          el("div", "muted", "Редактирование недоступно: данные устройств устарели или изменились.")
        );
      }
      container.appendChild(card);
      return;
    }

    if (!this._wizard.options) {
      const card = el("div", "card");
      card.appendChild(el(
        "h3", null,
        configured ? "Изменение климатического контура" : "Создание климатического контура"
      ));
      if (this._wizard.optionsError) {
        card.appendChild(el("div", "muted", "Не удалось загрузить комнаты и устройства."));
        const retry = el("button", "secondary", "Повторить загрузку");
        retry.disabled = this._wizard.loading;
        retry.addEventListener("click", () => this._loadWizardOptions(true));
        card.appendChild(retry);
      } else {
        card.appendChild(el("div", "muted", "Загрузка комнат и устройств..."));
        if (!this._wizard.loading) this._loadWizardOptions();
      }
      container.appendChild(card);
      return;
    }
    this._renderWizardForm(container, setup, this._wizard.options);
  }

  async _loadWizardOptions(force = false) {
    if (!this._hass || this._wizard.loading) return;
    if (this._wizard.options && !force) return;
    this._wizard.loading = true;
    this._wizard.optionsError = false;
    if (force) this._wizard.options = null;
    try {
      this._wizard.options = await this._hass.callApi("GET", DRAFT_API);
      this._wizard.optionsError = false;
    } catch (error) {
      this._wizard.options = null;
      this._wizard.optionsError = true;
    } finally {
      this._wizard.loading = false;
    }
    if (!this._dirty.wizard) this._render();
  }

  _openWizard(setup) {
    if (setup.status !== "not_configured" && setup.editing_allowed !== true) return;
    this._activateSection("contour");
    this._wizard.open = true;
    this._expandedWizardRooms.clear();
    this._wizard.setupRevision = setup.setup_revision;
    this._wizard.optionsError = false;
    this._wizard.draft = null;
    this._wizard.validation = null;
    this._wizard.fingerprint = null;
    this._dirty.wizard = false;
    this._render();
  }

  _cancelWizard() {
    this._wizard.open = false;
    this._expandedWizardRooms.clear();
    this._wizard.setupRevision = null;
    this._wizard.draft = null;
    this._wizard.validation = null;
    this._wizard.fingerprint = null;
    this._wizardFields = null;
    this._wizardIssues = null;
    this._wizardButtons = null;
    this._dirty.wizard = false;
    this._render();
  }

  _renderWizardForm(container, setup, options) {
    if (this._wizard.setupRevision === null) {
      this._wizard.setupRevision = setup.setup_revision;
    }
    const editing = setup.status !== "not_configured";
    const currentRooms = new Map((setup.rooms || []).map((room) => [room.id, room]));
    const deviceTypes = (options.display_names && options.display_names.device_types) || {};
    const strategies = (options.display_names && options.display_names.strategies) || {};
    const modes = (options.display_names && options.display_names.modes) || {};
    const fields = { rooms: {}, candidateBoxes: {}, controls: [], name: null, mode: null };
    const issues = { rooms: {}, global: null, success: null };
    const card = el("div", "card");
    card.appendChild(el(
      "h3", null,
      editing ? "Изменение климатического контура" : "Создание климатического контура"
    ));
    card.appendChild(el(
      "div",
      "section-intro",
      "Выберите комнаты, затем раскройте только те карточки, в которых нужно проверить цели и устройства."
    ));

    const name = el("input");
    name.type = "text";
    name.value = setup.name || "Климат";
    name.addEventListener("input", () => this._wizardChanged());
    const nameRow = el("label", "form-field", "Название контура");
    nameRow.appendChild(name);
    card.appendChild(nameRow);

    const mode = selectField(
      CONTOUR_MODE_ORDER.map((code) => ({ value: code, label: modes[code] || code })),
      setup.mode || "observe",
      () => this._wizardChanged()
    );
    const modeRow = el("label", "form-field", "Режим");
    modeRow.appendChild(mode);
    card.appendChild(modeRow);
    fields.name = name;
    fields.mode = mode;
    fields.controls.push(name, mode);

    (options.rooms || []).forEach((room) => {
      const currentRoom = currentRooms.get(room.id);
      const currentDevices = new Map(
        (((currentRoom && currentRoom.devices) || [])).map((device) => [device.candidate_id, device])
      );
      const candidates = (options.devices || []).filter((candidate) => (
        (candidate.room_id === room.id || candidate.room_id === "")
        && (candidate.can_add === true || currentDevices.has(candidate.candidate_id))
      ));
      const suggested = !editing && candidates.some(
        (candidate) => candidate.can_add === true && candidate.suggested_room_id === room.id
      );
      const canUseRoom = room.selectable === true || Boolean(currentRoom);
      const block = el("div", "room-block");
      setAttr(block, "data-room-id", room.id);
      const summary = el("div", "room-summary");
      const include = el("input");
      include.type = "checkbox";
      include.value = room.id;
      include.checked = Boolean(currentRoom) || suggested;
      include.disabled = !canUseRoom;
      const includeRow = el("label", "checkbox-field");
      includeRow.appendChild(include);
      includeRow.appendChild(el("span", null, room.name || room.id));
      summary.appendChild(includeRow);
      const summaryMeta = el("div", "room-summary-meta");
      summary.appendChild(summaryMeta);
      const summaryText = el("span");
      summaryMeta.appendChild(summaryText);
      const errorBadge = el("span", "room-error-badge", "Требует внимания");
      errorBadge.hidden = true;
      summaryMeta.appendChild(errorBadge);
      const expander = el("button", "secondary room-expander", "Настроить");
      expander.type = "button";
      setAttr(expander, "aria-expanded", "false");
      summary.appendChild(expander);
      block.appendChild(summary);
      const editor = el("div", "room-editor");
      editor.hidden = true;
      block.appendChild(editor);

      const profiles = (currentRoom && currentRoom.profiles) || {};
      const activeProfile = ["day", "night"].includes(profiles.active_profile)
        ? profiles.active_profile : "day";
      const activeSettings = profiles[activeProfile] || {};
      const temperature = numberField(
        activeSettings.target_temperature === undefined ? 22 : activeSettings.target_temperature,
        18, 28, 0.5, () => this._wizardChanged()
      );
      const humidity = numberField(
        activeSettings.target_humidity === undefined ? 45 : activeSettings.target_humidity,
        30, 70, 5, () => this._wizardChanged()
      );
      const strategy = selectField(
        STRATEGY_ORDER.map((code) => ({ value: code, label: strategies[code] || code })),
        activeSettings.strategy || "normal",
        () => this._wizardChanged()
      );
      const temperatureLabel = editing
        ? "Активный профиль: целевая температура, °C" : "Целевая температура, °C";
      const temperatureRow = el("label", "form-field", temperatureLabel);
      temperatureRow.appendChild(temperature);
      editor.appendChild(temperatureRow);
      editor.appendChild(el("div", "muted field-help", "Допустимо 18–28 °C, шаг 0,5 °C."));
      const humidityLabel = editing
        ? "Активный профиль: целевая влажность, %" : "Целевая влажность, %";
      const humidityRow = el("label", "form-field", humidityLabel);
      humidityRow.appendChild(humidity);
      editor.appendChild(humidityRow);
      editor.appendChild(el("div", "muted field-help", "Допустимо 30–70 %, шаг 5 %."));
      const strategyRow = el("label", "form-field", "Стратегия");
      strategyRow.appendChild(strategy);
      editor.appendChild(strategyRow);

      const roomFields = {
        include, temperature, humidity, strategy, devices: [], canUseRoom, toggle: null,
        editor, expander, summaryMeta, summaryText, errorBadge, expanded: false, everExpanded: false,
        setExpanded: null, updateSummary: null,
      };
      const appendDevices = (title, allowedTypes) => {
        editor.appendChild(el("h4", null, title));
        const choices = [];
        candidates.forEach((candidate, candidateIndex) => {
          const currentDevice = currentDevices.get(candidate.candidate_id);
          const suggestedTypes = Array.isArray(candidate.suggested_types)
            ? candidate.suggested_types : [];
          const recommended = candidate.recommended_type || suggestedTypes[0];
          suggestedTypes.filter((type) => allowedTypes.has(type)).forEach((type) => {
            const checked = Boolean(
              (currentDevice && currentDevice.type === type)
              || (!editing && candidate.can_add === true
                && candidate.suggested_room_id === room.id && recommended === type)
            );
            choices.push({
              candidate,
              type,
              checked,
              payloadOrder: (
                (ACTIVE_DEVICE_TYPES.has(type) ? 0 : 100000)
                + (candidateIndex * 100)
                + suggestedTypes.indexOf(type)
              ),
            });
          });
        });
        choices.sort((left, right) => (
          Number(right.checked) - Number(left.checked)
          || String(left.candidate.name).localeCompare(String(right.candidate.name), "ru")
        ));
        if (!choices.length) {
          editor.appendChild(el("div", "muted", "Подходящих устройств нет."));
          return;
        }
        const search = el("input", "entity-search");
        search.type = "search";
        search.placeholder = "Найти устройство";
        setAttr(search, "aria-label", `Поиск: ${title.toLocaleLowerCase("ru")}`);
        editor.appendChild(search);
        const groups = el("div", "entity-groups");
        const groupNodes = new Map();
        const optionNodes = [];
        choices.forEach(({ candidate, type, checked, payloadOrder }) => {
          if (!groupNodes.has(type)) {
            const group = el("div", "entity-group");
            group.appendChild(el("h4", null, deviceTypes[type] || type));
            groups.appendChild(group);
            groupNodes.set(type, group);
          }
            const checkbox = el("input");
            checkbox.type = "checkbox";
            checkbox.value = candidate.candidate_id;
            checkbox.checked = checked;
            checkbox.addEventListener("change", () => {
              if (checkbox.checked) {
                (fields.candidateBoxes[candidate.candidate_id] || []).forEach((peer) => {
                  if (peer !== checkbox) peer.checked = false;
                });
              }
              Object.values(fields.rooms).forEach((entry) => entry.updateSummary());
              this._wizardChanged();
            });
            const label = el("label", "device-option");
            label.appendChild(checkbox);
            const labelText = el("span", "entity-label");
            labelText.appendChild(el("strong", null, candidate.name));
            labelText.appendChild(el("small", null, deviceTypes[type] || type));
            label.appendChild(labelText);
            groupNodes.get(type).appendChild(label);
            optionNodes.push({
              node: label,
              searchText: normalizedText(`${candidate.name} ${deviceTypes[type] || type}`),
            });
            const choice = {
              checkbox, candidateId: candidate.candidate_id, type, label, payloadOrder,
            };
            roomFields.devices.push(choice);
            fields.candidateBoxes[candidate.candidate_id] =
              fields.candidateBoxes[candidate.candidate_id] || [];
            fields.candidateBoxes[candidate.candidate_id].push(checkbox);
        });
        search.addEventListener("input", () => {
          const query = normalizedText(search.value);
          optionNodes.forEach((option) => {
            option.node.hidden = Boolean(query) && !option.searchText.includes(query);
          });
        });
        editor.appendChild(groups);
      };
      appendDevices("Устройства управления", ACTIVE_DEVICE_TYPES);
      appendDevices("Датчики", SENSOR_DEVICE_TYPES);

      const roomIssues = el("div", "wizard-issues");
      setAttr(roomIssues, "aria-live", "polite");
      editor.appendChild(roomIssues);
      issues.rooms[room.id] = roomIssues;
      roomFields.updateSummary = () => {
        const active = roomFields.devices.filter((device) => (
          device.checkbox.checked && ACTIVE_DEVICE_TYPES.has(device.type)
        )).length;
        const sensors = roomFields.devices.filter((device) => (
          device.checkbox.checked && SENSOR_DEVICE_TYPES.has(device.type)
        )).length;
        summaryText.textContent = include.checked
          ? `Выбрано: управление — ${active}, датчики — ${sensors}`
          : "Комната не включена; выбранные привязки сохранены в форме";
      };
      roomFields.setExpanded = (expanded, shouldFocus = false) => {
        roomFields.expanded = expanded;
        if (expanded) {
          roomFields.everExpanded = true;
          this._expandedWizardRooms.add(room.id);
        } else {
          this._expandedWizardRooms.delete(room.id);
        }
        editor.hidden = !expanded;
        expander.textContent = expanded ? "Свернуть" : "Настроить";
        setAttr(expander, "aria-expanded", expanded ? "true" : "false");
        if (shouldFocus) focusNode(expander);
      };
      expander.addEventListener("click", () => {
        roomFields.setExpanded(!roomFields.expanded);
      });
      roomFields.toggle = () => {
        const enabled = include.checked && canUseRoom;
        temperature.disabled = !enabled;
        humidity.disabled = !enabled;
        strategy.disabled = !enabled;
        roomFields.devices.forEach((device) => { device.checkbox.disabled = !enabled; });
      };
      include.addEventListener("change", () => {
        roomFields.toggle();
        roomFields.updateSummary();
        if (include.checked && !roomFields.everExpanded) roomFields.setExpanded(true);
        this._wizardChanged();
      });
      roomFields.toggle();
      fields.rooms[room.id] = roomFields;
      roomFields.updateSummary();
      roomFields.setExpanded(this._expandedWizardRooms.has(room.id));
      fields.controls.push(include, temperature, humidity, strategy);
      roomFields.devices.forEach((device) => fields.controls.push(device.checkbox));
      card.appendChild(block);
    });

    const globalIssues = el("div", "wizard-issues");
    const success = el("div", "wizard-success");
    issues.global = globalIssues;
    issues.success = success;
    card.appendChild(globalIssues);
    card.appendChild(success);
    const dirtyNotice = el("div", "unsaved", "Есть несохранённые изменения");
    dirtyNotice.hidden = !this._dirty.wizard;
    card.appendChild(dirtyNotice);

    const check = el("button", null, "Проверить контур");
    const save = el("button", null, "Сохранить контур");
    const cancel = el("button", "secondary", "Отмена");
    const saveHint = el(
      "div",
      "muted action-help",
      "Сохранение станет доступно после успешной проверки контура."
    );
    check.disabled = this._busy || (!editing && options.draft_creation_allowed !== true);
    save.disabled = true;
    save.title = "Сначала проверьте контур.";
    cancel.disabled = this._busy;
    check.addEventListener("click", () => this._checkWizard());
    save.addEventListener("click", () => this._saveWizard());
    cancel.addEventListener("click", () => this._cancelWizard());
    const actions = el("div", "actions");
    actions.appendChild(check);
    actions.appendChild(save);
    actions.appendChild(cancel);
    card.appendChild(actions);
    card.appendChild(saveHint);
    if (!editing && options.draft_creation_allowed !== true) {
      const missingRooms = !(options.rooms || []).length;
      card.appendChild(el(
        "div",
        "muted action-help",
        missingRooms
          ? "Создание недоступно: в Home Assistant не найдены зоны (комнаты)."
          : "Создание недоступно: нет доступных климатических устройств."
      ));
      const refresh = el(
        "button",
        "secondary",
        "Обновить комнаты и устройства"
      );
      refresh.disabled = this._busy || this._wizard.loading;
      refresh.addEventListener("click", () => this._refreshWizardOptions());
      card.appendChild(refresh);
    }
    this._wizardFields = fields;
    this._wizardIssues = issues;
    this._wizardButtons = {
      check,
      save,
      cancel,
      saveHint,
      dirtyNotice,
      editing,
      creationAllowed: options.draft_creation_allowed === true,
    };
    container.appendChild(card);
  }

  async _refreshWizardOptions() {
    if (this._busy || this._wizard.loading) return;
    if (
      this._dirty.wizard
      && !window.confirm("Обновить комнаты и устройства? Несохранённые изменения формы будут сброшены.")
    ) return;
    this._dirty.wizard = false;
    this._wizard.draft = null;
    this._wizard.validation = null;
    this._wizard.fingerprint = null;
    this._wizardFields = null;
    this._wizardIssues = null;
    this._wizardButtons = null;
    await this._loadWizardOptions(true);
  }

  _wizardChanged() {
    this._dirty.wizard = true;
    this._wizard.draft = null;
    this._wizard.validation = null;
    this._wizard.fingerprint = null;
    this._clearWizardIssues();
    if (this._wizardButtons) {
      this._wizardButtons.dirtyNotice.hidden = false;
      this._wizardButtons.save.disabled = true;
      this._wizardButtons.save.title = "Сначала проверьте контур.";
      this._wizardButtons.saveHint.textContent =
        "Сохранение станет доступно после успешной проверки контура.";
    }
    this._syncSectionVisibility();
  }

  _clearWizardIssues() {
    if (!this._wizardIssues) return;
    Object.values(this._wizardIssues.rooms).forEach((node) => { node.innerHTML = ""; });
    if (this._wizardFields) {
      Object.values(this._wizardFields.rooms).forEach((room) => {
        room.errorBadge.hidden = true;
      });
    }
    this._wizardIssues.global.innerHTML = "";
    this._wizardIssues.success.innerHTML = "";
  }

  _collectWizardPayload() {
    const fields = this._wizardFields;
    const options = this._wizard.options;
    if (!fields || !options) return { error: "Мастер контура ещё не готов." };
    const name = String(fields.name.value || "").trim();
    if (!name || name.length > 120) {
      return {
        error: "Введите название контура длиной не более 120 символов.",
        control: fields.name,
      };
    }
    if (!CONTOUR_MODE_ORDER.includes(fields.mode.value)) {
      return { error: "Выберите режим климатического контура.", control: fields.mode };
    }
    const setupRevision = this._wizard.setupRevision;
    if (!Number.isSafeInteger(setupRevision) || setupRevision < 0) {
      return { error: "Настройки контура изменились. Обновите страницу и повторите." };
    }
    const rooms = [];
    const selectedCandidates = new Set();
    for (const room of options.rooms || []) {
      const entry = fields.rooms[room.id];
      if (!entry || !entry.include.checked) continue;
      const rawTemperature = entry.temperature.value;
      const rawHumidity = entry.humidity.value;
      const temperature = Number(rawTemperature);
      const humidity = Number(rawHumidity);
      if (
        rawTemperature === "" || !Number.isFinite(temperature)
        || temperature < 18 || temperature > 28 || !Number.isInteger(temperature * 2)
      ) {
        return {
          error: `Проверьте температуру в комнате «${room.name || room.id}»: 18-28 °C, шаг 0,5 °C.`,
          roomId: room.id,
          control: entry.temperature,
        };
      }
      if (
        rawHumidity === "" || !Number.isFinite(humidity)
        || humidity < 30 || humidity > 70 || !Number.isInteger(humidity / 5)
      ) {
        return {
          error: `Проверьте влажность в комнате «${room.name || room.id}»: 30-70 %, шаг 5 %.`,
          roomId: room.id,
          control: entry.humidity,
        };
      }
      if (!STRATEGY_ORDER.includes(entry.strategy.value)) {
        return {
          error: `Выберите стратегию для комнаты «${room.name || room.id}».`,
          roomId: room.id,
          control: entry.strategy,
        };
      }
      const devices = [];
      const selectedDevices = entry.devices
        .filter((choice) => choice.checkbox.checked)
        .sort((left, right) => left.payloadOrder - right.payloadOrder);
      for (const choice of selectedDevices) {
        if (selectedCandidates.has(choice.candidateId)) {
          return {
            error: "Одно устройство нельзя выбрать для нескольких комнат или типов.",
            roomId: room.id,
            control: choice.checkbox,
          };
        }
        selectedCandidates.add(choice.candidateId);
        devices.push({ candidate_id: choice.candidateId, type: choice.type });
      }
      if (!devices.length) {
        const firstDevice = entry.devices.find((choice) => ACTIVE_DEVICE_TYPES.has(choice.type))
          || entry.devices[0];
        return {
          error: `Выберите хотя бы одно устройство в комнате «${room.name || room.id}».`,
          roomId: room.id,
          control: firstDevice ? firstDevice.checkbox : entry.include,
        };
      }
      rooms.push({
        room_id: room.id,
        target_temperature: temperature,
        target_humidity: humidity,
        strategy: entry.strategy.value,
        devices,
      });
    }
    if (!rooms.length) {
      const firstRoom = (options.rooms || [])[0];
      return {
        error: "Выберите хотя бы одну комнату.",
        control: firstRoom && fields.rooms[firstRoom.id]
          ? fields.rooms[firstRoom.id].include : fields.name,
      };
    }
    return {
      payload: {
        snapshot_revision: options.snapshot_revision,
        setup_revision: setupRevision,
        name,
        mode: fields.mode.value,
        rooms,
      },
    };
  }

  _showWizardMessage(message, roomId = null, control = null) {
    this._clearWizardIssues();
    this._activateSection("contour");
    const room = roomId && this._wizardFields && this._wizardFields.rooms[roomId];
    if (room) {
      room.setExpanded(true);
      room.errorBadge.hidden = false;
      this._wizardIssues.rooms[roomId].appendChild(el("div", null, message));
    } else if (this._wizardIssues) {
      this._wizardIssues.global.appendChild(el("div", null, message));
    }
    focusNode(control || (room && room.expander));
  }

  _showWizardValidation(validation) {
    this._clearWizardIssues();
    let firstRoom = null;
    let firstControl = null;
    (validation.issues || []).forEach((issue) => {
      const room = issue.room_id && this._wizardFields.rooms[issue.room_id];
      if (room) {
        room.errorBadge.hidden = false;
        if (!firstRoom) firstRoom = room;
        if (!firstControl) {
          const candidate = issue.candidate_id
            ? room.devices.find((choice) => choice.candidateId === issue.candidate_id)
            : room.devices.find((choice) => ACTIVE_DEVICE_TYPES.has(choice.type));
          firstControl = candidate ? candidate.checkbox : room.include;
        }
      }
      const target = room ? this._wizardIssues.rooms[issue.room_id] : this._wizardIssues.global;
      target.appendChild(el("div", null, issue.message));
    });
    const ready = validation.status === "ready" && validation.save_allowed === true;
    if (ready) {
      this._wizardIssues.success.appendChild(
        el("div", null, "Контур проверен. Можно сохранять.")
      );
    } else if (!(validation.issues || []).length) {
      this._wizardIssues.global.appendChild(
        el("div", null, "Контур не прошёл проверку. Проверьте выбранные значения.")
      );
    }
    this._wizardButtons.save.disabled = this._busy || !ready;
    this._wizardButtons.save.title = ready ? "" : "Сначала исправьте замечания проверки.";
    this._wizardButtons.saveHint.textContent = ready
      ? "Контур проверен: сохранение доступно."
      : "Сохранение станет доступно после успешной проверки контура.";
    if (!ready) {
      this._activateSection("contour");
      if (firstRoom) firstRoom.setExpanded(true);
      focusNode(firstControl || (firstRoom ? firstRoom.include : this._wizardButtons.check));
    }
  }

  _setWizardBusy(busy) {
    if (!this._wizardFields || !this._wizardButtons) return;
    this._wizardFields.name.disabled = busy;
    this._wizardFields.mode.disabled = busy;
    Object.values(this._wizardFields.rooms).forEach((room) => {
      room.include.disabled = busy || !room.canUseRoom;
      room.expander.disabled = busy;
      if (busy) {
        room.temperature.disabled = true;
        room.humidity.disabled = true;
        room.strategy.disabled = true;
        room.devices.forEach((device) => { device.checkbox.disabled = true; });
      } else {
        room.toggle();
      }
    });
    this._wizardButtons.check.disabled = busy
      || (!this._wizardButtons.editing && !this._wizardButtons.creationAllowed);
    const ready = this._wizard.validation
      && this._wizard.validation.status === "ready"
      && this._wizard.validation.save_allowed === true;
    this._wizardButtons.save.disabled = busy || !ready;
    this._wizardButtons.save.title = ready
      ? (busy ? "Дождитесь завершения операции." : "")
      : "Сначала проверьте контур.";
    this._wizardButtons.cancel.disabled = busy;
  }

  async _checkWizard() {
    if (this._busy) return;
    const collected = this._collectWizardPayload();
    if (collected.error) {
      this._showWizardMessage(collected.error, collected.roomId, collected.control);
      return;
    }
    if (!window.confirm("Проверить климатический контур с выбранными комнатами и устройствами?")) return;
    this._busy = true;
    this._dirty.wizard = true;
    this._notice = "";
    this._setWizardBusy(true);
    try {
      const draft = await this._hass.callApi("POST", DRAFT_API, collected.payload);
      const validation = await this._hass.callApi("POST", DRAFT_VALIDATE_API, draft);
      this._wizard.draft = draft;
      this._wizard.validation = validation;
      this._wizard.fingerprint = JSON.stringify(collected.payload);
      this._showWizardValidation(validation);
    } catch (error) {
      if (error && error.status === 409) {
        await this._resetWizardAfterConflict();
      } else {
        this._showWizardMessage("Проверить контур не удалось. Проверьте значения и состояние устройств.");
      }
    } finally {
      this._busy = false;
      this._setWizardBusy(false);
      this._render();
    }
  }

  async _saveWizard() {
    if (this._busy) return;
    const validation = this._wizard.validation;
    if (
      !this._wizard.draft || !validation
      || validation.status !== "ready" || validation.save_allowed !== true
    ) return;
    const collected = this._collectWizardPayload();
    if (collected.error || JSON.stringify(collected.payload) !== this._wizard.fingerprint) {
      this._wizardChanged();
      this._showWizardMessage("Форма изменилась после проверки. Проверьте контур ещё раз.");
      return;
    }
    if (!window.confirm(
      "Сохранить климатический контур? Настройка будет записана атомарно, команды устройствам не отправятся."
    )) return;
    this._busy = true;
    this._setWizardBusy(true);
    try {
      await this._hass.callApi("POST", DRAFT_SAVE_API, this._wizard.draft);
      this._dirty.wizard = false;
      this._wizard.open = false;
      this._expandedWizardRooms.clear();
      this._wizard.setupRevision = null;
      this._wizard.draft = null;
      this._wizard.validation = null;
      this._wizard.fingerprint = null;
      this._wizard.options = null;
      this._wizardFields = null;
      this._wizardIssues = null;
      this._wizardButtons = null;
      this._notice = "Контур сохранён. Команды устройствам не отправлялись.";
      this._error = false;
      await this._load();
      await this._loadWizardOptions(true);
    } catch (error) {
      if (error && error.status === 409) {
        await this._resetWizardAfterConflict();
      } else {
        this._showWizardMessage("Сохранить контур не удалось. Проверьте значения и состояние устройств.");
      }
    } finally {
      this._busy = false;
      this._setWizardBusy(false);
      this._render();
    }
  }

  async _resetWizardAfterConflict() {
    this._dirty.wizard = false;
    this._wizard.open = false;
    this._expandedWizardRooms.clear();
    this._wizard.setupRevision = null;
    this._wizard.options = null;
    this._wizard.optionsError = false;
    this._wizard.draft = null;
    this._wizard.validation = null;
    this._wizard.fingerprint = null;
    this._wizardFields = null;
    this._wizardIssues = null;
    this._wizardButtons = null;
    this._notice = "Настройки изменились в другом окне. Данные обновлены, откройте мастер и повторите действие.";
    await this._load();
  }

  _renderContour(container, snapshot, setup) {
    container.innerHTML = "";
    if (!setup && !snapshot) return;
    container.appendChild(el("h2", null, "Контур"));
    container.appendChild(el(
      "div",
      "section-intro",
      "Состав комнат, цели и привязки климатических устройств. Сохранение не отправляет команды устройствам."
    ));
    this._renderContourWizard(container, setup);
    if (this._wizard.open || (setup && setup.status === "not_configured")) return;
    if (!snapshot) return;
    const contours = (snapshot.contours || []).filter((item) => item.kind === "climate");
    if (!contours.length) return;
    contours.forEach((contour) => {
      const card = el("div", "card");
      card.appendChild(el("h3", null, contour.name));
      this._row(card, "Статус", this._names("contour_statuses", contour.status));
      this._row(card, "Режим", this._names("contour_modes", contour.mode));
      if (contour.schedule && contour.schedule.enabled) {
        const next = contour.schedule.next_profile
          ? `${this._names("profiles", contour.schedule.next_profile)} · ${contour.schedule.next_change_at || ""}`
          : "Расписание включено";
        this._row(card, "Расписание", next);
      }
      if (Array.isArray(contour.reasons) && contour.reasons.length) {
        const reasons = el("div", "reasons");
        contour.reasons.forEach((reason) => {
          reasons.appendChild(el("span", "chip", this._names("contour_reasons", reason)));
        });
        card.appendChild(reasons);
      }

      const execution = contour.execution || {};
      const apply = execution.settings_apply || {};
      const applyButton = el("button", null, "Применить сохранённые настройки");
      applyButton.disabled = this._busy || apply.available !== true;
      applyButton.addEventListener("click", () => {
        this._post(
          `${PANEL_API}/apply`,
          {
            request_id: requestId("panel-apply"),
            contour_id: contour.id,
            confirm: true,
          },
          "Применить сохранённые настройки климата для всех комнат контура?"
        );
      });
      card.appendChild(applyButton);

      const temporary = execution.temporary_temperature || {};
      (contour.rooms || []).forEach((room) => {
        const block = el("div");
        block.appendChild(el("div", "muted", room.name || room.id));
        const input = el("input");
        input.type = "number";
        input.min = temporary.minimum;
        input.max = temporary.maximum;
        input.step = temporary.step;
        const current = room.temporary_temperature && room.temporary_temperature.active
          ? room.temporary_temperature.temperature
          : room.targets && room.targets.temperature;
        input.value = current;
        block.appendChild(input);
        const setButton = el("button", "secondary", "Временная температура");
        setButton.disabled = this._busy || !room.temporary_temperature || room.temporary_temperature.available !== true;
        setButton.addEventListener("click", () => {
          this._post(
            `${PANEL_API}/temporary-temperature`,
            {
              request_id: requestId("panel-temp"),
              contour_id: contour.id,
              room_id: room.id,
              action: "set",
              target_temperature: Number(input.value),
              confirm: true,
            },
            `Установить временную температуру ${input.value} °C в комнате «${room.name || room.id}» до следующей границы расписания?`
          );
        });
        block.appendChild(setButton);
        if (room.temporary_temperature && room.temporary_temperature.active) {
          const clearButton = el("button", "secondary", "Вернуться к расписанию");
          clearButton.disabled = this._busy;
          clearButton.addEventListener("click", () => {
            this._post(
              `${PANEL_API}/temporary-temperature`,
              {
                request_id: requestId("panel-temp"),
                contour_id: contour.id,
                room_id: room.id,
                action: "clear",
                target_temperature: null,
                confirm: true,
              },
              `Вернуть комнату «${room.name || room.id}» к расписанию?`
            );
          });
          block.appendChild(clearButton);
          block.appendChild(
            el("div", "muted", `Действует временная температура ${room.temporary_temperature.temperature} °C`)
          );
        }
        card.appendChild(block);
      });
      container.appendChild(card);
    });
  }

  _renderProfiles(container, setup) {
    container.innerHTML = "";
    if (!setup) {
      container.appendChild(el("h2", null, "Профили «День» и «Ночь»"));
      container.appendChild(el("div", "card empty-state muted", "Настройки профилей временно недоступны."));
      return;
    }
    container.appendChild(el("h2", null, "Профили «День» и «Ночь»"));
    container.appendChild(el(
      "div",
      "section-intro",
      "Комфортные цели каждой комнаты для дневного и ночного периодов."
    ));
    if (setup.status === "not_configured") {
      const card = el("div", "card empty-state");
      card.appendChild(
        el("div", "muted", "Климатический контур ещё не настроен. Сначала создайте его в разделе «Контур».")
      );
      const openWizard = el("button", "secondary", "Открыть мастер контура");
      openWizard.disabled = this._busy;
      openWizard.addEventListener("click", () => this._openWizard(setup));
      card.appendChild(openWizard);
      container.appendChild(card);
      return;
    }
    const editable = setup.editing_allowed === true;
    const strategies = (setup.display_names && setup.display_names.strategies) || {};
    const fields = {};
    const grid = el("div");
    (setup.rooms || []).forEach((room) => {
      const card = el("article", "card profile-room");
      card.appendChild(el("h3", null, room.name || room.id));
      const columns = el("div", "profile-columns");
      const roomError = el("div", "field-error");
      fields[room.id] = { error: roomError };
      ["day", "night"].forEach((profile) => {
        const values = (room.profiles && room.profiles[profile]) || {};
        const title = (setup.display_names && setup.display_names.profiles
          && setup.display_names.profiles[profile]) || profile;
        const profileBlock = el("div", "profile-block");
        profileBlock.appendChild(el("h4", null, title));
        const temperature = numberField(
          values.target_temperature, 18, 28, 0.5,
          () => this._markDirty("profiles", dirtyNotice)
        );
        const humidity = numberField(
          values.target_humidity, 30, 70, 5,
          () => this._markDirty("profiles", dirtyNotice)
        );
        const strategy = selectField(
          STRATEGY_ORDER.map((code) => ({ value: code, label: strategies[code] || code })),
          values.strategy,
          () => this._markDirty("profiles", dirtyNotice)
        );
        temperature.disabled = !editable;
        humidity.disabled = !editable;
        strategy.disabled = !editable;
        const tempRow = el("label", "form-field", "Температура, °C");
        tempRow.appendChild(temperature);
        profileBlock.appendChild(tempRow);
        profileBlock.appendChild(el("div", "muted field-help", "18–28 °C, шаг 0,5 °C."));
        const humidityRow = el("label", "form-field", "Влажность, %");
        humidityRow.appendChild(humidity);
        profileBlock.appendChild(humidityRow);
        profileBlock.appendChild(el("div", "muted field-help", "30–70 %, шаг 5 %."));
        const strategyRow = el("label", "form-field", "Стратегия");
        strategyRow.appendChild(strategy);
        profileBlock.appendChild(strategyRow);
        fields[room.id][profile] = { temperature, humidity, strategy };
        columns.appendChild(profileBlock);
      });
      card.appendChild(columns);
      card.appendChild(roomError);
      grid.appendChild(card);
    });
    container.appendChild(grid);
    if (!editable) {
      container.appendChild(
        el("div", "muted", "Редактирование недоступно: данные устройств устарели или изменились.")
      );
    }
    const validationSummary = el("div", "field-error");
    setAttr(validationSummary, "role", "alert");
    container.appendChild(validationSummary);
    const dirtyNotice = el("div", "unsaved", "Есть несохранённые изменения");
    dirtyNotice.hidden = !this._dirty.profiles;
    container.appendChild(dirtyNotice);
    const saveButton = el("button", null, "Сохранить профили");
    saveButton.disabled = this._busy || !editable;
    saveButton.addEventListener("click", () => {
      const rooms = [];
      let firstInvalid = null;
      Object.values(fields).forEach((room) => { room.error.textContent = ""; });
      validationSummary.textContent = "";
      Object.keys(fields).forEach((roomId) => {
        const profiles = {};
        ["day", "night"].forEach((profile) => {
          const entry = fields[roomId][profile];
          const rawTemperature = entry.temperature.value;
          const rawHumidity = entry.humidity.value;
          const temperature = Number(rawTemperature);
          const humidity = Number(rawHumidity);
          if (
            rawTemperature === "" || rawHumidity === ""
            || !Number.isFinite(temperature) || temperature < 18 || temperature > 28
            || !Number.isInteger(temperature * 2)
            || !Number.isFinite(humidity) || humidity < 30 || humidity > 70
            || !Number.isInteger(humidity / 5)
          ) {
            fields[roomId].error.textContent =
              "Проверьте температуру (18–28 °C, шаг 0,5) и влажность (30–70 %, шаг 5).";
            if (!firstInvalid) {
              firstInvalid = rawTemperature === "" || !Number.isFinite(temperature)
                || temperature < 18 || temperature > 28 || !Number.isInteger(temperature * 2)
                ? entry.temperature : entry.humidity;
            }
          }
          profiles[profile] = {
            target_temperature: temperature,
            target_humidity: Math.round(humidity),
            strategy: entry.strategy.value,
          };
        });
        rooms.push({ room_id: roomId, profiles });
      });
      if (firstInvalid) {
        validationSummary.textContent = "Исправьте отмеченные значения перед сохранением.";
        this._activateSection("profiles");
        focusNode(firstInvalid);
        return;
      }
      this._save(
        "profiles",
        PROFILES_API,
        {
          contract: PROFILE_CONTRACT,
          setup_revision: setup.setup_revision,
          rooms,
        },
        "Сохранить профили «День» и «Ночь» для всех комнат?",
        "Профили сохранены.",
        "Настройки изменились в другом окне. Данные обновлены, повторите сохранение."
      );
    });
    const actions = el("div", "actions");
    actions.appendChild(saveButton);
    container.appendChild(actions);
  }

  _renderSchedule(container, settings) {
    container.innerHTML = "";
    const setup = settings.setup;
    container.appendChild(el("h2", null, "Расписание"));
    container.appendChild(el(
      "div",
      "section-intro",
      "Границы дневного и ночного профилей и автоматическое переключение."
    ));
    if (!setup || setup.status === "not_configured") {
      container.appendChild(
        el("div", "card empty-state muted", "Расписание станет доступно после настройки контура.")
      );
      return;
    }
    const card = el("div", "card");
    const schedule = setup.schedule || {};
    const managed = settings.mode && settings.mode.mode === "managed";
    const enabledBox = el("input");
    enabledBox.type = "checkbox";
    enabledBox.checked = schedule.enabled === true;
    enabledBox.disabled = this._busy || !managed;
    const enabledLabel = el("label", "checkbox-field");
    enabledLabel.appendChild(enabledBox);
    enabledLabel.appendChild(el(
      "span",
      null,
      "Автоматическое переключение профилей (в управляемом режиме устройствам отправляются команды)"
    ));
    card.appendChild(enabledLabel);
    if (!managed) {
      card.appendChild(
        el("div", "muted", "Включение расписания доступно после перевода климата в управляемый режим.")
      );
    }
    const dayStart = el("input");
    dayStart.type = "time";
    dayStart.value = schedule.day_start || "07:00";
    const dayRow = el("label", "form-field", "Начало дня");
    dayRow.appendChild(dayStart);
    card.appendChild(dayRow);
    const nightStart = el("input");
    nightStart.type = "time";
    nightStart.value = schedule.night_start || "23:00";
    const nightRow = el("label", "form-field", "Начало ночи");
    nightRow.appendChild(nightStart);
    card.appendChild(nightRow);
    const validationError = el("div", "field-error");
    setAttr(validationError, "role", "alert");
    card.appendChild(validationError);
    const dirtyNotice = el("div", "unsaved", "Есть несохранённые изменения");
    dirtyNotice.hidden = !this._dirty.schedule;
    card.appendChild(dirtyNotice);
    enabledBox.addEventListener("change", () => this._markDirty("schedule", dirtyNotice));
    dayStart.addEventListener("input", () => this._markDirty("schedule", dirtyNotice));
    nightStart.addEventListener("input", () => this._markDirty("schedule", dirtyNotice));
    const saveButton = el("button", null, "Сохранить расписание");
    saveButton.disabled = this._busy;
    saveButton.addEventListener("click", () => {
      const day = dayStart.value;
      const night = nightStart.value;
      if (!TIME_PATTERN.test(day) || !TIME_PATTERN.test(night) || day === night) {
        validationError.textContent =
          "Проверьте время: формат ЧЧ:ММ, начала дня и ночи должны отличаться.";
        this._activateSection("schedule");
        focusNode(!TIME_PATTERN.test(day) || day === night ? dayStart : nightStart);
        return;
      }
      const enabled = enabledBox.checked === true;
      this._save(
        "schedule",
        SCHEDULE_API,
        {
          contract: SCHEDULE_CONTRACT,
          setup_revision: setup.setup_revision,
          schedule: { enabled, day_start: day, night_start: night },
          confirm_automatic_application: enabled,
        },
        enabled
          ? "Включить автоматическое переключение профилей по расписанию? В управляемом режиме устройствам будут отправляться команды."
          : "Сохранить расписание?",
        enabled ? "Расписание сохранено и включено." : "Расписание сохранено.",
        "Настройки изменились в другом окне. Данные обновлены, повторите сохранение."
      );
    });
    const actions = el("div", "actions");
    actions.appendChild(saveButton);
    card.appendChild(actions);
    container.appendChild(card);
  }

  _renderHome(container, home) {
    container.innerHTML = "";
    container.appendChild(el("h2", null, "Сигналы дома"));
    container.appendChild(el(
      "div",
      "section-intro",
      "Общее присутствие управляет политикой «дома/нет дома». Оно не заменяет комнатные датчики присутствия."
    ));
    if (!home || !home.home) {
      container.appendChild(el("div", "card empty-state muted", "Сигналы дома временно недоступны."));
      return;
    }
    const card = el("div", "card");
    const values = home.home || {};
    const candidates = home.candidates || {};
    const bindings = [
      {
        key: "outdoor_temperature_entity_id",
        label: "Датчик наружной температуры",
        options: candidates.outdoor_temperature || [],
      },
      {
        key: "presence_entity_id",
        label: "Общее присутствие дома",
        options: candidates.presence || [],
      },
      {
        key: "central_heating_entity_id",
        label: "Центральное отопление",
        options: candidates.central_heating || [],
      },
    ];
    const selects = {};
    bindings.forEach((binding) => {
      const options = [{ value: "", label: "Не привязано" }].concat(
        binding.options.map((item) => ({
          value: item.entity_id,
          label: item.name === item.entity_id
            ? item.entity_id
            : `${item.name} (${item.entity_id})`,
        }))
      );
      this._appendMissingBinding(options, values[binding.key]);
      const select = selectField(options, values[binding.key], () => {
        this._markDirty("home", dirtyNotice);
      });
      const row = el("label", "form-field", binding.label);
      row.appendChild(select);
      card.appendChild(row);
      selects[binding.key] = select;
    });
    const high = numberField(
      values.heating_lockout_high, -40, 60, 0.5,
      () => this._markDirty("home", dirtyNotice)
    );
    const highRow = el("label", "form-field", "Блокировка отопления выше, °C");
    highRow.appendChild(high);
    card.appendChild(highRow);
    const low = numberField(
      values.heating_lockout_low, -40, 60, 0.5,
      () => this._markDirty("home", dirtyNotice)
    );
    const lowRow = el("label", "form-field", "Разблокировка отопления ниже, °C");
    lowRow.appendChild(low);
    card.appendChild(lowRow);
    card.appendChild(
      el("div", "muted", "Пороги допустимы от −40 до 60 °C; нижний должен быть строго меньше верхнего.")
    );
    const validationError = el("div", "field-error");
    setAttr(validationError, "role", "alert");
    card.appendChild(validationError);
    const dirtyNotice = el("div", "unsaved", "Есть несохранённые изменения");
    dirtyNotice.hidden = !this._dirty.home;
    card.appendChild(dirtyNotice);
    const saveButton = el("button", null, "Сохранить сигналы дома");
    saveButton.disabled = this._busy;
    saveButton.addEventListener("click", () => {
      const rawHigh = high.value;
      const rawLow = low.value;
      const highValue = Number(rawHigh);
      const lowValue = Number(rawLow);
      if (
        rawHigh === "" || rawLow === ""
        || !Number.isFinite(highValue) || !Number.isFinite(lowValue)
        || highValue < -40 || highValue > 60 || lowValue < -40 || lowValue > 60
        || lowValue >= highValue
      ) {
        validationError.textContent =
          "Проверьте пороги: от -40 до 60 °C, нижний строго меньше верхнего.";
        this._activateSection("home");
        focusNode(
          rawHigh === "" || !Number.isFinite(highValue) || highValue < -40 || highValue > 60
            ? high : low
        );
        return;
      }
      this._save(
        "home",
        HOME_API,
        {
          outdoor_temperature_entity_id: selects.outdoor_temperature_entity_id.value || null,
          presence_entity_id: selects.presence_entity_id.value || null,
          central_heating_entity_id: selects.central_heating_entity_id.value || null,
          heating_lockout_high: highValue,
          heating_lockout_low: lowValue,
        },
        "Сохранить привязки сигналов дома и пороги блокировки отопления?",
        "Сигналы дома сохранены.",
        "Настройки изменились в другом окне. Данные обновлены, повторите сохранение."
      );
    });
    const actions = el("div", "actions");
    actions.appendChild(saveButton);
    card.appendChild(actions);
    container.appendChild(card);
  }

  _renderWindows(container, windows) {
    container.innerHTML = "";
    container.appendChild(el("h2", null, "Сигналы комнат"));
    container.appendChild(el(
      "div",
      "section-intro",
      "Окно — одиночная привязка. Комнатное присутствие — набор датчиков и пока не меняет температуру мгновенно: для этого нужна отдельная политика занятости."
    ));
    if (!windows) {
      container.appendChild(
        el("div", "card empty-state muted", "Сигналы комнат временно недоступны.")
      );
      return;
    }
    const rooms = windows.rooms || [];
    if (!rooms.length) {
      container.appendChild(
        el("div", "card empty-state muted", "Комнаты появятся здесь после настройки контура.")
      );
      return;
    }
    const windowOptions = [{ value: "", label: "Не привязано" }].concat(
      (windows.candidates || []).map((item) => ({
        value: item.entity_id,
        label: item.name === item.entity_id
          ? item.entity_id
          : `${item.name} (${item.entity_id})`,
      }))
    );
    const presenceCandidates = (
      windows.presence_candidates || windows.candidates || []
    ).filter((item) => (
      !item.device_class || ROOM_PRESENCE_DEVICE_CLASSES.has(item.device_class)
    ));
    const presenceById = new Map(
      presenceCandidates.map((item) => [item.entity_id, item])
    );
    rooms.forEach((room) => {
      (room.presence_entity_ids || []).forEach((entityId) => {
        if (!presenceById.has(entityId)) {
          presenceById.set(entityId, {
            entity_id: entityId,
            name: entityId,
            available: false,
          });
        }
      });
    });
    const fields = {};
    const presenceBoxes = {};
    const dirtyNotice = el("div", "unsaved", "Есть несохранённые изменения");
    dirtyNotice.hidden = !this._dirty.windows;
    const grid = el("div", "room-card-grid");
    rooms.forEach((room) => {
      const block = el("article", "card signal-room");
      block.appendChild(el("h3", null, room.name || room.id));
      const roomOptions = windowOptions.slice();
      this._appendMissingBinding(roomOptions, room.window_entity_id);
      const select = selectField(roomOptions, room.window_entity_id, () => {
        this._markDirty("windows", dirtyNotice);
      });
      const row = el("label", "form-field", "Датчик окна");
      row.appendChild(select);
      block.appendChild(row);
      block.appendChild(el("h4", null, "Датчики присутствия"));
      block.appendChild(
        el("div", "muted", "Можно выбрать несколько датчиков движения или занятости; один датчик относится только к одной комнате.")
      );
      const selected = new Set(room.presence_entity_ids || []);
      const boxes = [];
      const search = el("input", "entity-search");
      search.type = "search";
      search.placeholder = "Найти датчик присутствия";
      setAttr(search, "aria-label", `Поиск датчиков присутствия: ${room.name || room.id}`);
      block.appendChild(search);
      const groups = el("div", "entity-groups");
      const groupNodes = new Map();
      const optionNodes = [];
      const classNames = {
        motion: "Движение",
        occupancy: "Занятость",
        presence: "Присутствие",
        other: "Шаблонные датчики",
      };
      Array.from(presenceById.values())
        .sort((left, right) => (
          Number(selected.has(right.entity_id)) - Number(selected.has(left.entity_id))
          || String(left.name).localeCompare(String(right.name), "ru")
        ))
        .forEach((candidate) => {
        const category = ROOM_PRESENCE_DEVICE_CLASSES.has(candidate.device_class)
          ? candidate.device_class : "other";
        if (!groupNodes.has(category)) {
          const group = el("div", "entity-group");
          group.appendChild(el("h4", null, classNames[category]));
          groups.appendChild(group);
          groupNodes.set(category, group);
        }
        const checkbox = el("input");
        checkbox.type = "checkbox";
        checkbox.value = candidate.entity_id;
        checkbox.checked = selected.has(candidate.entity_id);
        checkbox.addEventListener("change", () => {
          if (checkbox.checked) {
            (presenceBoxes[candidate.entity_id] || []).forEach((peer) => {
              if (peer !== checkbox) peer.checked = false;
            });
          }
          this._markDirty("windows", dirtyNotice);
        });
        const label = el("label", "device-option");
        label.appendChild(checkbox);
        const labelText = el("span", "entity-label");
        labelText.appendChild(el("strong", null, candidate.name || candidate.entity_id));
        labelText.appendChild(el("small", null, candidate.entity_id));
        label.appendChild(labelText);
        groupNodes.get(category).appendChild(label);
        optionNodes.push({
          node: label,
          searchText: normalizedText(`${candidate.name} ${candidate.entity_id}`),
        });
        boxes.push(checkbox);
        presenceBoxes[candidate.entity_id] = presenceBoxes[candidate.entity_id] || [];
        presenceBoxes[candidate.entity_id].push(checkbox);
      });
      if (!boxes.length) {
        block.appendChild(
          el("div", "muted", "Подходящие binary_sensor пока не найдены.")
        );
      } else {
        block.appendChild(groups);
      }
      search.addEventListener("input", () => {
        const query = normalizedText(search.value);
        optionNodes.forEach((option) => {
          option.node.hidden = Boolean(query) && !option.searchText.includes(query);
        });
      });
      grid.appendChild(block);
      fields[room.id] = {
        select,
        boxes,
        originalWindow: room.window_entity_id || "",
        originalPresence: Array.from(selected).sort(),
      };
    });
    container.appendChild(grid);
    const selectedPresence = (roomId) => fields[roomId].boxes
      .filter((checkbox) => checkbox.checked)
      .map((checkbox) => checkbox.value)
      .sort();
    const saveButton = el("button", null, "Сохранить сигналы комнат");
    saveButton.disabled = this._busy;
    saveButton.addEventListener("click", async () => {
      if (this._busy) return;
      const changed = Object.keys(fields).filter((roomId) => (
        fields[roomId].select.value !== fields[roomId].originalWindow
        || JSON.stringify(selectedPresence(roomId))
          !== JSON.stringify(fields[roomId].originalPresence)
      ));
      if (!changed.length) {
        this._notice = "Сигналы комнат не изменились.";
        this._render();
        return;
      }
      if (!window.confirm(`Сохранить сигналы для комнат: ${changed.length}?`)) return;
      this._busy = true;
      saveButton.disabled = true;
      this._notice = "";
      this._render();
      let failed = false;
      try {
        await this._hass.callApi("POST", WINDOWS_API, {
          rooms: changed.map((roomId) => ({
            room_id: roomId,
            window_entity_id: fields[roomId].select.value || null,
            presence_entity_ids: selectedPresence(roomId),
          })),
        });
      } catch (error) {
        failed = true;
      }
      this._dirty.windows = false;
      this._busy = false;
      this._notice = failed
        ? "Сохранить сигналы комнат не удалось. Данные обновлены, проверьте значения."
        : "Сигналы комнат сохранены.";
      await this._load();
    });
    container.appendChild(dirtyNotice);
    const actions = el("div", "actions");
    actions.appendChild(saveButton);
    container.appendChild(actions);
  }

  _appendMissingBinding(options, current) {
    if (!current) return;
    if (options.some((item) => item.value === current)) return;
    options.push({ value: current, label: `${current} (недоступна)` });
  }

  _row(card, label, value) {
    const row = el("div", "row");
    row.appendChild(el("span", null, label));
    row.appendChild(el("span", "value", value));
    card.appendChild(row);
  }

  _temp(value) {
    return typeof value === "number" ? `${value.toFixed(1)} °C` : "Нет данных";
  }

  _humidity(value) {
    return typeof value === "number" ? `${Math.round(value)} %` : "Нет данных";
  }
}

customElements.define("hausman-hub-panel", HausmanHubPanel);
