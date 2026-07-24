from __future__ import annotations

import copy
import json
from pathlib import Path
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
PANEL_JS = (
    ROOT
    / "custom_components"
    / "hausman_hub"
    / "frontend"
    / "hausman-hub-panel.js"
)

PANEL_PAYLOAD = {
    "contract": {"name": "hausman-hub-admin-panel", "version": 2},
    "snapshot": None,
    "readiness": {
        "status": "disabled",
        "bridge_mode": "disabled",
        "reasons": ["bridge_disabled"],
    },
}
MODE_PAYLOAD = {"mode": "disabled", "contour_configured": False}
HOME_PAYLOAD = {
    "home": {
        "outdoor_temperature_entity_id": None,
        "presence_entity_id": None,
        "central_heating_entity_id": None,
        "heating_lockout_high": 18.0,
        "heating_lockout_low": 16.0,
    },
    "candidates": {
        "outdoor_temperature": [],
        "presence": [],
        "central_heating": [],
    },
}
WINDOWS_PAYLOAD = {"rooms": [], "candidates": []}
DISPLAY_NAMES = {
    "modes": {"observe": "Наблюдение", "automatic": "Автоматический"},
    "strategies": {"soft": "Плавно", "normal": "Обычно", "aggressive": "Быстро"},
    "profiles": {"day": "День", "night": "Ночь"},
    "device_types": {
        "air_conditioner": "Кондиционер",
        "radiator_thermostat": "Радиаторный термостат",
        "humidifier": "Увлажнитель",
        "floor_heating": "Тёплый пол",
        "temperature_sensor": "Датчик температуры",
        "humidity_sensor": "Датчик влажности",
    },
}
NOT_CONFIGURED_SETUP = {
    "contract": {"name": "hausman-hub-climate-current-setup", "version": 1},
    "generated_at": 1784280000,
    "snapshot_revision": 77,
    "setup_revision": 5,
    "status": "not_configured",
    "editing_allowed": False,
    "display_names": DISPLAY_NAMES,
    "name": None,
    "mode": None,
    "schedule": None,
    "rooms": [],
    "issues": [],
    "summary": {"room_count": 0, "device_count": 0},
}
CONFIGURED_SETUP = {
    "contract": {"name": "hausman-hub-climate-current-setup", "version": 1},
    "generated_at": 1784280000,
    "snapshot_revision": 77,
    "setup_revision": 123,
    "status": "ready",
    "editing_allowed": True,
    "display_names": DISPLAY_NAMES,
    "name": "Домашний климат",
    "mode": "automatic",
    "schedule": {"enabled": False, "day_start": "07:00", "night_start": "23:00"},
    "rooms": [
        {
            "id": "living",
            "name": "Гостиная",
            "devices": [
                {"candidate_id": "candidate_ac", "name": "Кондиционер", "type": "air_conditioner", "type_name": "Кондиционер"},
                {"candidate_id": "candidate_temp_1", "name": "Температура у окна", "type": "temperature_sensor", "type_name": "Датчик температуры"},
                {"candidate_id": "candidate_temp_2", "name": "Температура у двери", "type": "temperature_sensor", "type_name": "Датчик температуры"},
                {"candidate_id": "candidate_humidity", "name": "Влажность гостиной", "type": "humidity_sensor", "type_name": "Датчик влажности"},
            ],
            "profiles": {
                "day": {"target_temperature": 24.5, "target_humidity": 50, "strategy": "aggressive"},
                "night": {"target_temperature": 21.0, "target_humidity": 45, "strategy": "soft"},
                "active_profile": "day",
            },
            "temporary_temperature": None,
        }
    ],
    "issues": [{"code": "attention", "room_id": "living", "message": "Проверьте датчик"}],
    "summary": {"room_count": 1, "device_count": 4},
}
DRAFT_OPTIONS = {
    "contract": {"name": "hausman-hub-climate-setup-options", "version": 1},
    "generated_at": 1784280000,
    "snapshot_revision": 77,
    "data_status": "current",
    "draft_creation_allowed": True,
    "display_names": DISPLAY_NAMES,
    "rooms": [
        {"id": "living", "name": "Гостиная", "status": "available", "selectable": True},
        {"id": "kids", "name": "Детская", "status": "available", "selectable": True},
    ],
    "devices": [
        {
            "candidate_id": "candidate_ac", "name": "Кондиционер", "room_id": "living",
            "suggested_types": ["air_conditioner"], "recommended_type": "air_conditioner",
            "status": "available", "suggested_room_id": "living", "suggested_room_name": "Гостиная",
            "reason": "detected_room", "can_add": True,
        },
        {
            "candidate_id": "candidate_temp_1", "name": "Температура у окна", "room_id": "living",
            "suggested_types": ["temperature_sensor"], "recommended_type": "temperature_sensor",
            "status": "available", "suggested_room_id": "living", "suggested_room_name": "Гостиная",
            "reason": "detected_room", "can_add": True,
        },
        {
            "candidate_id": "candidate_temp_2", "name": "Температура у двери", "room_id": "",
            "suggested_types": ["temperature_sensor"], "recommended_type": "temperature_sensor",
            "status": "available", "suggested_room_id": "living", "suggested_room_name": "Гостиная",
            "reason": "detected_room", "can_add": True,
        },
        {
            "candidate_id": "candidate_humidity", "name": "Влажность гостиной", "room_id": "living",
            "suggested_types": ["humidity_sensor"], "recommended_type": "humidity_sensor",
            "status": "available", "suggested_room_id": "living", "suggested_room_name": "Гостиная",
            "reason": "detected_room", "can_add": True,
        },
        {
            "candidate_id": "candidate_trv", "name": "Батарея детской", "room_id": "kids",
            "suggested_types": ["radiator_thermostat"], "recommended_type": "radiator_thermostat",
            "status": "available", "suggested_room_id": "kids", "suggested_room_name": "Детская",
            "reason": "detected_room", "can_add": True,
        },
        {
            "candidate_id": "candidate_kids_temp", "name": "Температура детской", "room_id": "kids",
            "suggested_types": ["temperature_sensor"], "recommended_type": "temperature_sensor",
            "status": "available", "suggested_room_id": "kids", "suggested_room_name": "Детская",
            "reason": "detected_room", "can_add": True,
        },
    ],
}


def get_payloads(
    *,
    setup: dict | None = None,
    options: dict | None = None,
    panel: dict | None = None,
    windows: dict | None = None,
) -> dict:
    return {
        "hausman_hub/v1/admin/panel": panel or PANEL_PAYLOAD,
        "hausman_hub/v1/admin/climate-mode": MODE_PAYLOAD,
        "hausman_hub/v1/admin/home-environment": HOME_PAYLOAD,
        "hausman_hub/v1/admin/climate-room-signals": windows or WINDOWS_PAYLOAD,
        "hausman_hub/v1/admin/climate-drafts/current": setup or NOT_CONFIGURED_SETUP,
        "hausman_hub/v1/admin/climate-drafts": options or DRAFT_OPTIONS,
    }


def panel_script(get_table: dict, post_table: dict, assertions: str) -> str:
    return f"""
      const fs = require("fs");
      const vm = require("vm");

      class FakeElement {{
        constructor(tag = "element") {{
          this.tagName = tag.toUpperCase();
          this.children = [];
          this.className = "";
          this.textContent = "";
          this.disabled = false;
          this.style = {{}};
          this.value = "";
          this.checked = false;
          this._listeners = {{}};
        }}
        appendChild(child) {{
          this.children.push(child);
          return child;
        }}
        addEventListener(type, handler) {{
          (this._listeners[type] = this._listeners[type] || []).push(handler);
        }}
        fire(type) {{
          (this._listeners[type] || []).forEach((handler) => handler());
        }}
        set innerHTML(value) {{
          if (value === "") this.children = [];
        }}
      }}

      global.document = {{
        hidden: false,
        createElement: (tag) => new FakeElement(tag),
        addEventListener() {{}},
        removeEventListener() {{}},
      }};
      global.window = {{ confirm: () => true }};
      global.HTMLElement = class {{
        attachShadow() {{
          this.shadowRoot = new FakeElement("shadow-root");
          return this.shadowRoot;
        }}
      }};
      const registry = new Map();
      global.customElements = {{
        define: (name, value) => registry.set(name, value),
      }};
      vm.runInThisContext(
        fs.readFileSync({str(PANEL_JS)!r}, "utf8"),
        {{ filename: {str(PANEL_JS)!r} }}
      );

      const getTable = {json.dumps(get_table, ensure_ascii=False)};
      const postTable = {json.dumps(post_table, ensure_ascii=False)};
      const postIndexes = {{}};
      const calls = [];
      const hass = {{
        callApi: (method, path, payload) => {{
          calls.push({{ method, path, payload }});
          if (method === "GET") {{
            if (!(path in getTable)) return Promise.reject(new Error("unexpected GET " + path));
            const result = getTable[path];
            if (result && result.__fail) return Promise.reject(new Error("GET failed"));
            return Promise.resolve(result);
          }}
          let result = postTable[path];
          if (Array.isArray(result)) {{
            const index = postIndexes[path] || 0;
            postIndexes[path] = index + 1;
            result = result[Math.min(index, result.length - 1)];
          }}
          if (result && result.__fail) {{
            const error = new Error("POST failed");
            error.status = result.__fail;
            return Promise.reject(error);
          }}
          return Promise.resolve(result || {{ status: "up_to_date" }});
        }},
      }};

      const visit = (node, action) => {{
        action(node);
        node.children.forEach((child) => visit(child, action));
      }};
      const findAll = (root, predicate) => {{
        const found = [];
        visit(root, (node) => {{ if (predicate(node)) found.push(node); }});
        return found;
      }};
      const textOf = (root) => {{
        const parts = [];
        visit(root, (node) => parts.push(node.textContent));
        return parts.join("\\n");
      }};
      const tick = async (count = 8) => {{
        for (let index = 0; index < count; index += 1) {{
          await new Promise((resolve) => setImmediate(resolve));
        }}
      }};

      (async () => {{
        const Panel = registry.get("hausman-hub-panel");
        const panel = new Panel();
        panel.hass = hass;
        await tick();
        {assertions}
      }})().catch((error) => {{
        console.error(error);
        process.exit(1);
      }});
    """


def run_panel_script(script: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ("node", "--input-type=commonjs", "--eval", script),
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
    )


def draft_for(rooms: list[dict], *, name: str = "Дом", mode: str = "automatic") -> dict:
    device_count = sum(len(room["devices"]) for room in rooms)
    return {
        "contract": {"name": "hausman-hub-climate-contour-draft", "version": 1},
        "generated_at": 1784280000,
        "snapshot_revision": 77,
        "draft_revision": 9001,
        "status": "created",
        "save_allowed": False,
        "validation_required": True,
        "display_names": {
            "modes": DISPLAY_NAMES["modes"],
            "strategies": DISPLAY_NAMES["strategies"],
        },
        "name": name,
        "mode": mode,
        "rooms": rooms,
        "summary": {"room_count": len(rooms), "device_count": device_count},
    }


def ready_validation(draft: dict) -> dict:
    return {
        "contract": {"name": "hausman-hub-climate-contour-validation", "version": 1},
        "generated_at": 1784280001,
        "snapshot_revision": draft["snapshot_revision"],
        "draft_revision": draft["draft_revision"],
        "status": "ready",
        "save_allowed": True,
        "command_allowed": False,
        "checks": {"rooms_have_active_devices": True},
        "issues": [],
        "summary": draft["summary"],
    }


class PanelContourWizardTest(unittest.TestCase):
    def test_not_configured_renders_rooms_multiple_sensors_and_keeps_dirty_form(self) -> None:
        script = panel_script(
            get_payloads(),
            {},
            """
        const text = textOf(panel.shadowRoot);
        if (!text.includes("Создание климатического контура")) throw new Error("create title missing");
        if (!text.includes("Устройства управления") || !text.includes("Датчики")) {
          throw new Error("device group headings missing");
        }
        if (!text.includes("Температура у окна") || !text.includes("Температура у двери")) {
          throw new Error("multiple temperature sensors missing");
        }
        const living = panel._wizardFields.rooms.living;
        const temperatureSensors = living.devices.filter((choice) => choice.type === "temperature_sensor");
        if (temperatureSensors.length !== 2) throw new Error("expected two selectable temperature sensors");
        if (!temperatureSensors.every((choice) => choice.checkbox.checked)) {
          throw new Error("suggested temperature sensors were not preselected");
        }
        panel._wizardFields.name.value = "Несохранённый контур";
        panel._wizardFields.name.fire("input");
        getTable["hausman_hub/v1/admin/climate-drafts/current"] = {
          ...getTable["hausman_hub/v1/admin/climate-drafts/current"], setup_revision: 6
        };
        await panel._load();
        if (panel._wizardFields.name.value !== "Несохранённый контур") {
          throw new Error("background refresh clobbered dirty wizard");
        }
        if (panel._dirty.wizard !== true) throw new Error("wizard dirty flag missing");
        const collected = panel._collectWizardPayload();
        if (panel._settings.setup.setup_revision !== 6) {
          throw new Error("background setup did not refresh");
        }
        if (collected.error || collected.payload.setup_revision !== 5) {
          throw new Error("dirty wizard did not keep its original setup revision");
        }
        const rendered = textOf(panel.shadowRoot);
        if (rendered.includes("entity_id") || rendered.includes("source_id")) {
          throw new Error("private binding name rendered");
        }
            """,
        )
        completed = run_panel_script(script)
        self.assertEqual(0, completed.returncode, completed.stderr)

    def test_happy_path_posts_exact_request_validates_and_saves_exact_draft(self) -> None:
        living_devices = [
            {"candidate_id": "candidate_ac", "name": "Кондиционер", "type": "air_conditioner", "type_name": "Кондиционер"},
            {"candidate_id": "candidate_temp_1", "name": "Температура у окна", "type": "temperature_sensor", "type_name": "Датчик температуры"},
            {"candidate_id": "candidate_temp_2", "name": "Температура у двери", "type": "temperature_sensor", "type_name": "Датчик температуры"},
            {"candidate_id": "candidate_humidity", "name": "Влажность гостиной", "type": "humidity_sensor", "type_name": "Датчик влажности"},
        ]
        kids_devices = [
            {"candidate_id": "candidate_trv", "name": "Батарея детской", "type": "radiator_thermostat", "type_name": "Радиаторный термостат"},
            {"candidate_id": "candidate_kids_temp", "name": "Температура детской", "type": "temperature_sensor", "type_name": "Датчик температуры"},
        ]
        draft = draft_for(
            [
                {"id": "kids", "name": "Детская", "targets": {"target_temperature": 20.5, "target_humidity": 40, "strategy": "soft"}, "devices": kids_devices},
                {"id": "living", "name": "Гостиная", "targets": {"target_temperature": 24, "target_humidity": 50, "strategy": "aggressive"}, "devices": living_devices},
            ]
        )
        post_table = {
            "hausman_hub/v1/admin/climate-drafts": draft,
            "hausman_hub/v1/admin/climate-drafts/validate": ready_validation(draft),
            "hausman_hub/v1/admin/climate-drafts/save": {
                "status": "saved", "commands_sent": False, "restart_required": False
            },
        }
        expected_request = {
            "snapshot_revision": 77,
            "setup_revision": 5,
            "name": "Дом",
            "mode": "automatic",
            "rooms": [
                {
                    "room_id": "living", "target_temperature": 24, "target_humidity": 50,
                    "strategy": "aggressive",
                    "devices": [
                        {"candidate_id": "candidate_ac", "type": "air_conditioner"},
                        {"candidate_id": "candidate_temp_1", "type": "temperature_sensor"},
                        {"candidate_id": "candidate_temp_2", "type": "temperature_sensor"},
                        {"candidate_id": "candidate_humidity", "type": "humidity_sensor"},
                    ],
                },
                {
                    "room_id": "kids", "target_temperature": 20.5, "target_humidity": 40,
                    "strategy": "soft",
                    "devices": [
                        {"candidate_id": "candidate_trv", "type": "radiator_thermostat"},
                        {"candidate_id": "candidate_kids_temp", "type": "temperature_sensor"},
                    ],
                },
            ],
        }
        script = panel_script(
            get_payloads(),
            post_table,
            f"""
        const fields = panel._wizardFields;
        fields.name.value = "Дом";
        fields.name.fire("input");
        fields.mode.value = "automatic";
        fields.mode.fire("change");
        fields.rooms.living.temperature.value = "24";
        fields.rooms.living.temperature.fire("input");
        fields.rooms.living.humidity.value = "50";
        fields.rooms.living.humidity.fire("input");
        fields.rooms.living.strategy.value = "aggressive";
        fields.rooms.living.strategy.fire("change");
        fields.rooms.kids.temperature.value = "20.5";
        fields.rooms.kids.temperature.fire("input");
        fields.rooms.kids.humidity.value = "40";
        fields.rooms.kids.humidity.fire("input");
        fields.rooms.kids.strategy.value = "soft";
        fields.rooms.kids.strategy.fire("change");
        const check = findAll(panel.shadowRoot, (node) => node.tagName === "BUTTON")
          .find((node) => node.textContent === "Проверить контур");
        check.fire("click");
        await tick();
        const create = calls.find((call) => call.method === "POST" && call.path === "hausman_hub/v1/admin/climate-drafts");
        const expected = {json.dumps(expected_request, ensure_ascii=False)};
        if (!create || JSON.stringify(create.payload) !== JSON.stringify(expected)) {{
          throw new Error("create payload mismatch: " + JSON.stringify(create && create.payload));
        }}
        const validation = calls.find((call) => call.method === "POST" && call.path.endsWith("/validate"));
        const expectedDraft = {json.dumps(draft, ensure_ascii=False)};
        if (!validation || JSON.stringify(validation.payload) !== JSON.stringify(expectedDraft)) {{
          throw new Error("validation did not receive exact draft");
        }}
        const save = findAll(panel.shadowRoot, (node) => node.tagName === "BUTTON")
          .find((node) => node.textContent === "Сохранить контур");
        if (!save || save.disabled) throw new Error("ready draft did not enable save");
        save.fire("click");
        await tick(12);
        const saved = calls.find((call) => call.method === "POST" && call.path.endsWith("/save"));
        if (!saved || JSON.stringify(saved.payload) !== JSON.stringify(expectedDraft)) {{
          throw new Error("save did not receive exact draft");
        }}
        if (!textOf(panel.shadowRoot).includes("Контур сохранён. Команды устройствам не отправлялись.")) {{
          throw new Error("truthful save notice missing");
        }}
            """,
        )
        completed = run_panel_script(script)
        self.assertEqual(0, completed.returncode, completed.stderr)

    def test_blocked_issue_is_grouped_by_room_then_active_device_allows_ready(self) -> None:
        options = copy.deepcopy(DRAFT_OPTIONS)
        options["rooms"] = [options["rooms"][0]]
        options["devices"] = [options["devices"][0], options["devices"][1]]
        options["devices"][0]["suggested_room_id"] = None
        options["devices"][0]["suggested_room_name"] = None
        sensor_device = [
            {"candidate_id": "candidate_temp_1", "name": "Температура у окна", "type": "temperature_sensor", "type_name": "Датчик температуры"}
        ]
        active_device = [
            {"candidate_id": "candidate_ac", "name": "Кондиционер", "type": "air_conditioner", "type_name": "Кондиционер"},
            *sensor_device,
        ]
        blocked_draft = draft_for(
            [{"id": "living", "name": "Гостиная", "targets": {"target_temperature": 22, "target_humidity": 45, "strategy": "normal"}, "devices": sensor_device}],
            name="Климат",
            mode="observe",
        )
        ready_draft = draft_for(
            [{"id": "living", "name": "Гостиная", "targets": {"target_temperature": 22, "target_humidity": 45, "strategy": "normal"}, "devices": active_device}],
            name="Климат",
            mode="observe",
        )
        blocked = {
            "status": "blocked", "save_allowed": False, "command_allowed": False,
            "issues": [{"code": "no_controllable_device", "room_id": "living", "message": "В комнате нет устройства управления"}],
            "summary": blocked_draft["summary"],
        }
        script = panel_script(
            get_payloads(options=options),
            {
                "hausman_hub/v1/admin/climate-drafts": [blocked_draft, ready_draft],
                "hausman_hub/v1/admin/climate-drafts/validate": [blocked, ready_validation(ready_draft)],
            },
            """
        const check = findAll(panel.shadowRoot, (node) => node.tagName === "BUTTON")
          .find((node) => node.textContent === "Проверить контур");
        check.fire("click");
        await tick();
        if (!textOf(panel._wizardIssues.rooms.living).includes("В комнате нет устройства управления")) {
          throw new Error("room issue missing");
        }
        if (!panel._wizardButtons.save.disabled) throw new Error("blocked draft enabled save");
        const active = panel._wizardFields.rooms.living.devices
          .find((choice) => choice.type === "air_conditioner");
        active.checkbox.checked = true;
        active.checkbox.fire("change");
        if (textOf(panel._wizardIssues.rooms.living).includes("нет устройства")) {
          throw new Error("stale issue survived form edit");
        }
        check.fire("click");
        await tick();
        if (panel._wizardButtons.save.disabled) throw new Error("ready validation did not enable save");
        if (!textOf(panel.shadowRoot).includes("Контур проверен. Можно сохранять.")) {
          throw new Error("ready message missing");
        }
            """,
        )
        completed = run_panel_script(script)
        self.assertEqual(0, completed.returncode, completed.stderr)

    def test_invalid_comfort_steps_are_rejected_before_any_draft_post(self) -> None:
        script = panel_script(
            get_payloads(),
            {},
            """
        const living = panel._wizardFields.rooms.living;
        const check = findAll(panel.shadowRoot, (node) => node.tagName === "BUTTON")
          .find((node) => node.textContent === "Проверить контур");
        living.temperature.value = "17.5";
        living.temperature.fire("input");
        check.fire("click");
        await tick();
        if (!textOf(panel.shadowRoot).includes("18-28 °C")) {
          throw new Error("temperature contract hint missing");
        }
        living.temperature.value = "22";
        living.temperature.fire("input");
        living.humidity.value = "41";
        living.humidity.fire("input");
        check.fire("click");
        await tick();
        if (!textOf(panel.shadowRoot).includes("шаг 5 %")) {
          throw new Error("humidity contract hint missing");
        }
        if (calls.some((call) => call.method === "POST")) {
          throw new Error("invalid comfort values reached backend");
        }
            """,
        )
        completed = run_panel_script(script)
        self.assertEqual(0, completed.returncode, completed.stderr)

    def test_edit_mode_fetches_lazily_and_prefills_existing_multiple_sensors(self) -> None:
        options = copy.deepcopy(DRAFT_OPTIONS)
        options["draft_creation_allowed"] = False
        options["rooms"] = [options["rooms"][0]]
        options["devices"] = options["devices"][:4]
        for candidate in options["devices"]:
            candidate["status"] = "already_configured"
            candidate["can_add"] = False
        panel_payload = copy.deepcopy(PANEL_PAYLOAD)
        panel_payload["snapshot"] = {
            "display_names": {},
            "rooms": [{"id": "living", "name": "Гостиная", "temperature": 23.5, "humidity": 46, "target_temperature": 24.5, "mode": "automatic", "actual": {"data_status": "current"}, "devices": []}],
            "contours": [],
        }
        windows = {"rooms": [{"id": "living", "name": "Гостиная", "window_entity_id": None}], "candidates": []}
        configured_setup = copy.deepcopy(CONFIGURED_SETUP)
        configured_setup["rooms"][0]["profiles"]["active_profile"] = "night"
        script = panel_script(
            get_payloads(setup=configured_setup, options=options, panel=panel_payload, windows=windows),
            {},
            """
        if (calls.some((call) => call.method === "GET" && call.path === "hausman_hub/v1/admin/climate-drafts")) {
          throw new Error("configured summary fetched options eagerly");
        }
        const initial = textOf(panel.shadowRoot);
        const order = ["Состояние", "Контур", "Комнаты", "Профили", "Расписание", "Сигналы дома", "Окна комнат"];
        let cursor = -1;
        order.forEach((heading) => {
          const next = initial.indexOf(heading, cursor + 1);
          if (next <= cursor) throw new Error("section order broken at " + heading);
          cursor = next;
        });
        const edit = findAll(panel.shadowRoot, (node) => node.tagName === "BUTTON")
          .find((node) => node.textContent === "Изменить контур");
        edit.fire("click");
        await tick();
        const optionGets = calls.filter((call) => call.method === "GET" && call.path === "hausman_hub/v1/admin/climate-drafts");
        if (optionGets.length !== 1) throw new Error("edit did not fetch options exactly once");
        const fields = panel._wizardFields;
        if (fields.name.value !== "Домашний климат" || fields.mode.value !== "automatic") {
          throw new Error("contour values not prefilled");
        }
        const living = fields.rooms.living;
        if (!living.include.checked || String(living.temperature.value) !== "21" || String(living.humidity.value) !== "45") {
          throw new Error("active profile targets not prefilled");
        }
        const collected = panel._collectWizardPayload();
        if (collected.error || collected.payload.setup_revision !== 123) {
          throw new Error("edit setup revision missing");
        }
        const checkedSensors = living.devices.filter((choice) =>
          choice.type.endsWith("_sensor") && choice.checkbox.checked);
        if (checkedSensors.length !== 3) throw new Error("existing sensors not kept checkable");
        const checkedTemperature = checkedSensors.filter((choice) => choice.type === "temperature_sensor");
        if (checkedTemperature.length !== 2) throw new Error("multiple existing temperature sensors not prefilled");
        const rendered = textOf(panel.shadowRoot);
        if (rendered.includes("entity_id") || rendered.includes("source_id")) {
          throw new Error("private binding rendered in edit mode");
        }
            """,
        )
        completed = run_panel_script(script)
        self.assertEqual(0, completed.returncode, completed.stderr)

    def test_save_conflict_shows_notice_and_reloads_current_setup(self) -> None:
        one_room_options = copy.deepcopy(DRAFT_OPTIONS)
        one_room_options["rooms"] = [one_room_options["rooms"][0]]
        one_room_options["devices"] = [one_room_options["devices"][0]]
        device = [
            {"candidate_id": "candidate_ac", "name": "Кондиционер", "type": "air_conditioner", "type_name": "Кондиционер"}
        ]
        draft = draft_for(
            [{"id": "living", "name": "Гостиная", "targets": {"target_temperature": 22, "target_humidity": 45, "strategy": "normal"}, "devices": device}],
            name="Климат",
            mode="observe",
        )
        script = panel_script(
            get_payloads(options=one_room_options),
            {
                "hausman_hub/v1/admin/climate-drafts": draft,
                "hausman_hub/v1/admin/climate-drafts/validate": ready_validation(draft),
                "hausman_hub/v1/admin/climate-drafts/save": {"__fail": 409},
            },
            """
        const check = findAll(panel.shadowRoot, (node) => node.tagName === "BUTTON")
          .find((node) => node.textContent === "Проверить контур");
        check.fire("click");
        await tick();
        panel._wizardButtons.save.fire("click");
        await tick(12);
        const text = textOf(panel.shadowRoot);
        if (!text.includes("изменились в другом окне")) throw new Error("conflict notice missing");
        const setupGets = calls.filter((call) =>
          call.method === "GET" && call.path === "hausman_hub/v1/admin/climate-drafts/current");
        if (setupGets.length < 2) throw new Error("current setup was not reloaded after conflict");
        const optionGets = calls.filter((call) =>
          call.method === "GET" && call.path === "hausman_hub/v1/admin/climate-drafts");
        if (optionGets.length < 2) throw new Error("wizard options were not reloaded after conflict");
        if (panel._dirty.wizard !== false) throw new Error("conflict left stale dirty form active");
            """,
        )
        completed = run_panel_script(script)
        self.assertEqual(0, completed.returncode, completed.stderr)


if __name__ == "__main__":
    unittest.main()
