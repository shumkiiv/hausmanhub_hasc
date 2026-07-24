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
const TIME_PATTERN = /^([01]\d|2[0-3]):[0-5]\d$/;

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
    this._renderReadiness(shell.readiness, this._data.readiness);
    const snapshot = this._data.snapshot;
    if (!this._dirty.wizard) {
      this._renderContour(shell.contour, snapshot, this._settings.setup);
    }
    this._renderRooms(shell.rooms, snapshot);
    if (!this._dirty.profiles) this._renderProfiles(shell.profiles, this._settings.setup);
    if (!this._dirty.schedule) this._renderSchedule(shell.schedule, this._settings);
    if (!this._dirty.home) this._renderHome(shell.home, this._settings.home);
    if (!this._dirty.windows) this._renderWindows(shell.windows, this._settings.windows);
  }

  _ensureShell() {
    if (this._shell) return;
    const root = this.shadowRoot;
    const style = el("style");
    style.textContent = `
      :host { display: block; padding: 16px; max-width: 1100px; margin: 0 auto;
        font-family: var(--primary-font-family, sans-serif);
        color: var(--primary-text-color, #212121); }
      h1 { font-size: 22px; margin: 0 0 4px; }
      h2 { font-size: 17px; margin: 24px 0 8px; }
      h4 { font-size: 14px; margin: 12px 0 4px; }
      .muted { color: var(--secondary-text-color, #727272); font-size: 13px; }
      .banner { padding: 10px 14px; border-radius: 8px; margin: 12px 0;
        background: var(--error-color, #db4437); color: #fff; }
      .notice { padding: 10px 14px; border-radius: 8px; margin: 12px 0;
        background: var(--success-color, #43a047); color: #fff; }
      .cards { display: grid; grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
        gap: 12px; }
      .card { background: var(--card-background-color, #fff); border-radius: 12px;
        padding: 14px; box-shadow: var(--ha-card-box-shadow, 0 1px 3px rgba(0,0,0,0.2)); }
      .card h3 { margin: 0 0 6px; font-size: 15px; }
      .row { display: flex; justify-content: space-between; font-size: 14px;
        padding: 2px 0; gap: 8px; align-items: center; }
      .value { font-weight: 500; }
      button { font: inherit; border: none; border-radius: 8px; padding: 8px 14px;
        margin: 6px 8px 0 0; cursor: pointer;
        background: var(--primary-color, #03a9f4); color: #fff; }
      button.secondary { background: var(--secondary-background-color, #e5e5e5);
        color: var(--primary-text-color, #212121); }
      button:disabled { opacity: 0.5; cursor: default; }
      input[type="number"] { font: inherit; width: 72px; padding: 6px;
        border-radius: 8px; border: 1px solid var(--divider-color, #ccc);
        margin-right: 8px; }
      input[type="text"] { font: inherit; width: min(320px, 100%); padding: 6px;
        border-radius: 8px; border: 1px solid var(--divider-color, #ccc); }
      input[type="time"] { font: inherit; padding: 6px; border-radius: 8px;
        border: 1px solid var(--divider-color, #ccc); margin-right: 8px; }
      select { font: inherit; padding: 6px; border-radius: 8px;
        border: 1px solid var(--divider-color, #ccc); max-width: 260px; }
      label { font-size: 14px; display: block; margin: 8px 0 2px; }
      .reasons { font-size: 13px; margin: 6px 0 0; }
      .chip { display: inline-block; border-radius: 10px; padding: 2px 10px;
        font-size: 12px; background: var(--secondary-background-color, #e5e5e5);
        margin: 2px 4px 2px 0; }
      .room-block { border-top: 1px solid var(--divider-color, #ddd); margin-top: 14px;
        padding-top: 10px; }
      .device-option { margin: 4px 0; }
      .wizard-issues { color: var(--error-color, #db4437); font-size: 13px; margin-top: 6px; }
      .wizard-success { color: var(--success-color, #43a047); font-size: 13px; margin-top: 8px; }
    `;
    root.appendChild(style);
    const container = el("div");
    root.appendChild(container);
    container.appendChild(el("h1", null, "HausmanHub"));
    const banner = el("div", "banner", "Данные HausmanHub недоступны. Проверьте интеграцию и повторите.");
    banner.style.display = "none";
    container.appendChild(banner);
    const notice = el("div", "notice");
    notice.style.display = "none";
    container.appendChild(notice);
    const loading = el("div", "muted", "Загрузка…");
    loading.style.display = "none";
    container.appendChild(loading);
    const sections = {};
    ["readiness", "contour", "rooms", "profiles", "schedule", "home", "windows"].forEach((name) => {
      const node = el("div");
      container.appendChild(node);
      sections[name] = node;
    });
    this._shell = { banner, notice, loading, ...sections };
  }

  _clearDynamic() {
    ["readiness", "rooms"].forEach((name) => {
      this._shell[name].innerHTML = "";
    });
    if (!this._dirty.wizard) this._shell.contour.innerHTML = "";
    ["profiles", "schedule", "home", "windows"].forEach((name) => {
      if (!this._dirty[name]) this._shell[name].innerHTML = "";
    });
  }

  _renderReadiness(container, readiness) {
    container.innerHTML = "";
    container.appendChild(el("h2", null, "Состояние"));
    const card = el("div", "card");
    const labels = {
      ready: "Готов к управлению",
      not_ready: "Не готов",
      unavailable: "Недоступен",
      disabled: "Управление климатом выключено",
    };
    const statusRow = el("div", "row");
    statusRow.appendChild(el("span", null, "Статус"));
    statusRow.appendChild(el("span", "value", labels[readiness.status] || readiness.status));
    card.appendChild(statusRow);
    const modeRow = el("div", "row");
    modeRow.appendChild(el("span", null, "Режим"));
    modeRow.appendChild(el("span", "value", readiness.bridge_mode));
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
    if (!snapshot) return;
    container.appendChild(el("h2", null, "Комнаты"));
    const grid = el("div", "cards");
    (snapshot.rooms || []).forEach((room) => {
      const card = el("div", "card");
      card.appendChild(el("h3", null, room.name));
      this._row(card, "Температура", this._temp(room.temperature));
      this._row(card, "Влажность", this._humidity(room.humidity));
      this._row(card, "Цель", this._temp(room.target_temperature));
      this._row(card, "Режим", this._names("room_modes", room.mode));
      this._row(card, "Данные", this._names("data_statuses", room.actual && room.actual.data_status));
      (room.devices || []).forEach((device) => {
        this._row(card, device.name, this._names("device_states", device.state));
      });
      grid.appendChild(card);
    });
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
    this._wizard.open = true;
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
    const fields = { rooms: {}, candidateBoxes: {}, controls: [] };
    const issues = { rooms: {}, global: null, success: null };
    const card = el("div", "card");
    card.appendChild(el(
      "h3", null,
      editing ? "Изменение климатического контура" : "Создание климатического контура"
    ));

    const name = el("input");
    name.type = "text";
    name.value = setup.name || "Климат";
    name.addEventListener("input", () => this._wizardChanged());
    const nameRow = el("label", null, "Название контура");
    nameRow.appendChild(name);
    card.appendChild(nameRow);

    const mode = selectField(
      CONTOUR_MODE_ORDER.map((code) => ({ value: code, label: modes[code] || code })),
      setup.mode || "observe",
      () => this._wizardChanged()
    );
    const modeRow = el("label", null, "Режим");
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
      const include = el("input");
      include.type = "checkbox";
      include.value = room.id;
      include.checked = Boolean(currentRoom) || suggested;
      include.disabled = !canUseRoom;
      const includeRow = el("label", null, `Включить комнату «${room.name || room.id}»`);
      includeRow.appendChild(include);
      block.appendChild(includeRow);

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
      const temperatureRow = el("label", null, temperatureLabel);
      temperatureRow.appendChild(temperature);
      block.appendChild(temperatureRow);
      const humidityLabel = editing
        ? "Активный профиль: целевая влажность, %" : "Целевая влажность, %";
      const humidityRow = el("label", null, humidityLabel);
      humidityRow.appendChild(humidity);
      block.appendChild(humidityRow);
      const strategyRow = el("label", null, "Стратегия");
      strategyRow.appendChild(strategy);
      block.appendChild(strategyRow);

      const roomFields = {
        include, temperature, humidity, strategy, devices: [], canUseRoom, toggle: null,
      };
      const appendDevices = (title, allowedTypes) => {
        block.appendChild(el("h4", null, title));
        let count = 0;
        candidates.forEach((candidate) => {
          const currentDevice = currentDevices.get(candidate.candidate_id);
          const suggestedTypes = Array.isArray(candidate.suggested_types)
            ? candidate.suggested_types : [];
          const recommended = candidate.recommended_type || suggestedTypes[0];
          suggestedTypes.filter((type) => allowedTypes.has(type)).forEach((type) => {
            const checkbox = el("input");
            checkbox.type = "checkbox";
            checkbox.value = candidate.candidate_id;
            checkbox.checked = Boolean(
              (currentDevice && currentDevice.type === type)
              || (!editing && candidate.can_add === true
                && candidate.suggested_room_id === room.id && recommended === type)
            );
            checkbox.addEventListener("change", () => {
              if (checkbox.checked) {
                (fields.candidateBoxes[candidate.candidate_id] || []).forEach((peer) => {
                  if (peer !== checkbox) peer.checked = false;
                });
              }
              this._wizardChanged();
            });
            const label = el(
              "label", "device-option", `${candidate.name} - ${deviceTypes[type] || type}`
            );
            label.appendChild(checkbox);
            block.appendChild(label);
            const choice = { checkbox, candidateId: candidate.candidate_id, type };
            roomFields.devices.push(choice);
            fields.candidateBoxes[candidate.candidate_id] =
              fields.candidateBoxes[candidate.candidate_id] || [];
            fields.candidateBoxes[candidate.candidate_id].push(checkbox);
            count += 1;
          });
        });
        if (!count) block.appendChild(el("div", "muted", "Подходящих устройств нет."));
      };
      appendDevices("Устройства управления", ACTIVE_DEVICE_TYPES);
      appendDevices("Датчики", SENSOR_DEVICE_TYPES);

      const roomIssues = el("div", "wizard-issues");
      block.appendChild(roomIssues);
      issues.rooms[room.id] = roomIssues;
      roomFields.toggle = () => {
        const enabled = include.checked && canUseRoom;
        temperature.disabled = !enabled;
        humidity.disabled = !enabled;
        strategy.disabled = !enabled;
        roomFields.devices.forEach((device) => { device.checkbox.disabled = !enabled; });
      };
      include.addEventListener("change", () => {
        roomFields.toggle();
        this._wizardChanged();
      });
      roomFields.toggle();
      fields.rooms[room.id] = roomFields;
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

    const check = el("button", null, "Проверить контур");
    const save = el("button", null, "Сохранить контур");
    const cancel = el("button", "secondary", "Отмена");
    check.disabled = this._busy || (!editing && options.draft_creation_allowed !== true);
    save.disabled = true;
    cancel.disabled = this._busy;
    check.addEventListener("click", () => this._checkWizard());
    save.addEventListener("click", () => this._saveWizard());
    cancel.addEventListener("click", () => this._cancelWizard());
    card.appendChild(check);
    card.appendChild(save);
    card.appendChild(cancel);
    if (!editing && options.draft_creation_allowed !== true) {
      card.appendChild(
        el("div", "muted", "Создание недоступно: обновите данные комнат и устройств.")
      );
    }
    this._wizardFields = fields;
    this._wizardIssues = issues;
    this._wizardButtons = { check, save, cancel, editing, creationAllowed: options.draft_creation_allowed === true };
    container.appendChild(card);
  }

  _wizardChanged() {
    this._dirty.wizard = true;
    this._wizard.draft = null;
    this._wizard.validation = null;
    this._wizard.fingerprint = null;
    this._clearWizardIssues();
    if (this._wizardButtons) this._wizardButtons.save.disabled = true;
  }

  _clearWizardIssues() {
    if (!this._wizardIssues) return;
    Object.values(this._wizardIssues.rooms).forEach((node) => { node.innerHTML = ""; });
    this._wizardIssues.global.innerHTML = "";
    this._wizardIssues.success.innerHTML = "";
  }

  _collectWizardPayload() {
    const fields = this._wizardFields;
    const options = this._wizard.options;
    if (!fields || !options) return { error: "Мастер контура ещё не готов." };
    const name = String(fields.name.value || "").trim();
    if (!name || name.length > 120) {
      return { error: "Введите название контура длиной не более 120 символов." };
    }
    if (!CONTOUR_MODE_ORDER.includes(fields.mode.value)) {
      return { error: "Выберите режим климатического контура." };
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
        return { error: `Проверьте температуру в комнате «${room.name || room.id}»: 18-28 °C, шаг 0,5 °C.` };
      }
      if (
        rawHumidity === "" || !Number.isFinite(humidity)
        || humidity < 30 || humidity > 70 || !Number.isInteger(humidity / 5)
      ) {
        return { error: `Проверьте влажность в комнате «${room.name || room.id}»: 30-70 %, шаг 5 %.` };
      }
      if (!STRATEGY_ORDER.includes(entry.strategy.value)) {
        return { error: `Выберите стратегию для комнаты «${room.name || room.id}».` };
      }
      const devices = [];
      for (const choice of entry.devices) {
        if (!choice.checkbox.checked) continue;
        if (selectedCandidates.has(choice.candidateId)) {
          return { error: "Одно устройство нельзя выбрать для нескольких комнат или типов." };
        }
        selectedCandidates.add(choice.candidateId);
        devices.push({ candidate_id: choice.candidateId, type: choice.type });
      }
      if (!devices.length) {
        return { error: `Выберите хотя бы одно устройство в комнате «${room.name || room.id}».` };
      }
      rooms.push({
        room_id: room.id,
        target_temperature: temperature,
        target_humidity: humidity,
        strategy: entry.strategy.value,
        devices,
      });
    }
    if (!rooms.length) return { error: "Выберите хотя бы одну комнату." };
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

  _showWizardMessage(message) {
    this._clearWizardIssues();
    if (this._wizardIssues) this._wizardIssues.global.appendChild(el("div", null, message));
  }

  _showWizardValidation(validation) {
    this._clearWizardIssues();
    (validation.issues || []).forEach((issue) => {
      const target = issue.room_id && this._wizardIssues.rooms[issue.room_id]
        ? this._wizardIssues.rooms[issue.room_id] : this._wizardIssues.global;
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
  }

  _setWizardBusy(busy) {
    if (!this._wizardFields || !this._wizardButtons) return;
    this._wizardFields.name.disabled = busy;
    this._wizardFields.mode.disabled = busy;
    Object.values(this._wizardFields.rooms).forEach((room) => {
      room.include.disabled = busy || !room.canUseRoom;
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
    this._wizardButtons.cancel.disabled = busy;
  }

  async _checkWizard() {
    if (this._busy) return;
    const collected = this._collectWizardPayload();
    if (collected.error) {
      this._showWizardMessage(collected.error);
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
    if (!setup) return;
    container.appendChild(el("h2", null, "Профили «День» и «Ночь»"));
    const card = el("div", "card");
    if (setup.status === "not_configured") {
      card.appendChild(
        el("div", "muted", "Климатический контур ещё не настроен. Создайте его в разделе «Контур» выше.")
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
    (setup.rooms || []).forEach((room) => {
      card.appendChild(el("h3", null, room.name || room.id));
      fields[room.id] = {};
      ["day", "night"].forEach((profile) => {
        const values = (room.profiles && room.profiles[profile]) || {};
        const title = (setup.display_names && setup.display_names.profiles
          && setup.display_names.profiles[profile]) || profile;
        card.appendChild(el("h4", null, title));
        const temperature = numberField(
          values.target_temperature, 18, 28, 0.5,
          () => { this._dirty.profiles = true; }
        );
        const humidity = numberField(
          values.target_humidity, 30, 70, 5,
          () => { this._dirty.profiles = true; }
        );
        const strategy = selectField(
          STRATEGY_ORDER.map((code) => ({ value: code, label: strategies[code] || code })),
          values.strategy,
          () => { this._dirty.profiles = true; }
        );
        temperature.disabled = !editable;
        humidity.disabled = !editable;
        strategy.disabled = !editable;
        const tempRow = el("label", null, "Температура, °C");
        tempRow.appendChild(temperature);
        card.appendChild(tempRow);
        const humidityRow = el("label", null, "Влажность, %");
        humidityRow.appendChild(humidity);
        card.appendChild(humidityRow);
        const strategyRow = el("label", null, "Стратегия");
        strategyRow.appendChild(strategy);
        card.appendChild(strategyRow);
        fields[room.id][profile] = { temperature, humidity, strategy };
      });
    });
    if (!editable) {
      card.appendChild(
        el("div", "muted", "Редактирование недоступно: данные устройств устарели или изменились.")
      );
    }
    const saveButton = el("button", null, "Сохранить профили");
    saveButton.disabled = this._busy || !editable;
    saveButton.addEventListener("click", () => {
      const rooms = [];
      let invalid = false;
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
            invalid = true;
          }
          profiles[profile] = {
            target_temperature: temperature,
            target_humidity: Math.round(humidity),
            strategy: entry.strategy.value,
          };
        });
        rooms.push({ room_id: roomId, profiles });
      });
      if (invalid) {
        this._notice = "Проверьте температуру (18–28 °C, шаг 0,5) и влажность (30–70 %, шаг 5).";
        this._render();
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
    card.appendChild(saveButton);
    container.appendChild(card);
  }

  _renderSchedule(container, settings) {
    container.innerHTML = "";
    const setup = settings.setup;
    if (!setup || setup.status === "not_configured") return;
    container.appendChild(el("h2", null, "Расписание"));
    const card = el("div", "card");
    const schedule = setup.schedule || {};
    const managed = settings.mode && settings.mode.mode === "managed";
    const enabledBox = el("input");
    enabledBox.type = "checkbox";
    enabledBox.checked = schedule.enabled === true;
    enabledBox.disabled = this._busy || !managed;
    enabledBox.addEventListener("change", () => { this._dirty.schedule = true; });
    const enabledLabel = el("label", null,
      "Автоматическое переключение профилей (в управляемом режиме устройствам отправляются команды)"
    );
    enabledLabel.appendChild(enabledBox);
    card.appendChild(enabledLabel);
    if (!managed) {
      card.appendChild(
        el("div", "muted", "Включение расписания доступно после перевода климата в управляемый режим.")
      );
    }
    const dayStart = el("input");
    dayStart.type = "time";
    dayStart.value = schedule.day_start || "07:00";
    dayStart.addEventListener("input", () => { this._dirty.schedule = true; });
    const dayRow = el("label", null, "Начало дня");
    dayRow.appendChild(dayStart);
    card.appendChild(dayRow);
    const nightStart = el("input");
    nightStart.type = "time";
    nightStart.value = schedule.night_start || "23:00";
    nightStart.addEventListener("input", () => { this._dirty.schedule = true; });
    const nightRow = el("label", null, "Начало ночи");
    nightRow.appendChild(nightStart);
    card.appendChild(nightRow);
    const saveButton = el("button", null, "Сохранить расписание");
    saveButton.disabled = this._busy;
    saveButton.addEventListener("click", () => {
      const day = dayStart.value;
      const night = nightStart.value;
      if (!TIME_PATTERN.test(day) || !TIME_PATTERN.test(night) || day === night) {
        this._notice = "Проверьте время: формат ЧЧ:ММ, начала дня и ночи должны отличаться.";
        this._render();
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
    card.appendChild(saveButton);
    container.appendChild(card);
  }

  _renderHome(container, home) {
    container.innerHTML = "";
    if (!home || !home.home) return;
    container.appendChild(el("h2", null, "Сигналы дома"));
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
        label: "Датчик присутствия",
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
        this._dirty.home = true;
      });
      const row = el("label", null, binding.label);
      row.appendChild(select);
      card.appendChild(row);
      selects[binding.key] = select;
    });
    const high = numberField(
      values.heating_lockout_high, -40, 60, 0.5,
      () => { this._dirty.home = true; }
    );
    const highRow = el("label", null, "Блокировка отопления выше, °C");
    highRow.appendChild(high);
    card.appendChild(highRow);
    const low = numberField(
      values.heating_lockout_low, -40, 60, 0.5,
      () => { this._dirty.home = true; }
    );
    const lowRow = el("label", null, "Разблокировка отопления ниже, °C");
    lowRow.appendChild(low);
    card.appendChild(lowRow);
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
        this._notice = "Проверьте пороги: от -40 до 60 °C, нижний строго меньше верхнего.";
        this._render();
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
    card.appendChild(saveButton);
    container.appendChild(card);
  }

  _renderWindows(container, windows) {
    container.innerHTML = "";
    if (!windows) return;
    const rooms = windows.rooms || [];
    if (!rooms.length) return;
    container.appendChild(el("h2", null, "Окна комнат"));
    const card = el("div", "card");
    const options = [{ value: "", label: "Не привязано" }].concat(
      (windows.candidates || []).map((item) => ({
        value: item.entity_id,
        label: item.name === item.entity_id
          ? item.entity_id
          : `${item.name} (${item.entity_id})`,
      }))
    );
    const selects = {};
    rooms.forEach((room) => {
      const roomOptions = options.slice();
      this._appendMissingBinding(roomOptions, room.window_entity_id);
      const select = selectField(roomOptions, room.window_entity_id, () => {
        this._dirty.windows = true;
      });
      const row = el("label", null, room.name || room.id);
      row.appendChild(select);
      card.appendChild(row);
      selects[room.id] = { select, original: room.window_entity_id || "" };
    });
    const saveButton = el("button", null, "Сохранить привязки окон");
    saveButton.disabled = this._busy;
    saveButton.addEventListener("click", async () => {
      if (this._busy) return;
      const changed = Object.keys(selects).filter(
        (roomId) => selects[roomId].select.value !== (selects[roomId].original || "")
      );
      if (!changed.length) {
        this._notice = "Привязки окон не изменились.";
        this._render();
        return;
      }
      if (!window.confirm(`Сохранить привязки окон для комнат: ${changed.length}?`)) return;
      this._busy = true;
      this._notice = "";
      this._render();
      let failed = false;
      for (const roomId of changed) {
        try {
          await this._hass.callApi("POST", WINDOWS_API, {
            room_id: roomId,
            window_entity_id: selects[roomId].select.value || null,
          });
        } catch (error) {
          failed = true;
          break;
        }
      }
      this._dirty.windows = false;
      this._busy = false;
      this._notice = failed
        ? "Сохранить привязки окон не удалось. Данные обновлены, проверьте значения."
        : "Привязки окон сохранены.";
      await this._load();
    });
    card.appendChild(saveButton);
    container.appendChild(card);
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
    return typeof value === "number" ? `${value.toFixed(1)} °C` : "нет данных";
  }

  _humidity(value) {
    return typeof value === "number" ? `${Math.round(value)} %` : "нет данных";
  }
}

customElements.define("hausman-hub-panel", HausmanHubPanel);
