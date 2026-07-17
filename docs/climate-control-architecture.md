# Климат через HASC: архитектура, реестр и Android API

Версия документа: 2026-07-17. Реализация относится к HASC 0.5.0.

## Итоговая схема

```text
Android-планшет
       ↕ локальный аутентифицированный HASC API
HASC: реестр комнат и устройств, публичные capabilities, проверка команд
       ↕ два фиксированных маршрута Climate API v1
существующий climate-core / Smart Home Center
       ↕ его текущие адаптеры, cooldown, safety и physical feedback
Home Assistant / Node-RED / физические устройства
```

HASC становится единственной точкой, которую должен знать Android. При этом
HASC не копирует климатические алгоритмы. Автоматический и ручной режим,
cooldown, выбор фактического исполнительного устройства, authority, защита от
устаревшего состояния и подтверждение физического результата остаются в
текущем климатическом контуре.

## Как описывается устройство

Владелец создаёт в реестре HASC логическое устройство. Одному устройству можно
назначить несколько приватных Home Assistant entities с фиксированными ролями:

- `control` — исполнитель;
- `temperature` и `humidity` — измерения;
- `physical_feedback` — подтверждение физического состояния;
- `fan`, `valve_position`, `child_lock`, `water_level` — дополнительные
  наблюдаемые части.

Android получает только стабильный HASC ID, имя, тип, доступность и список
возможностей. Он не получает `source_id` и `entity_id`.

Поддерживаемые типы:

| Тип HASC | Минимальные возможности | Исполнительный контракт |
| --- | --- | --- |
| `air_conditioner` | power, target temperature | `climate.*` |
| `radiator_thermostat` | target temperature | `trv.set_temperature` |
| `humidifier` | power, target humidity | `humidifier.*` |
| `floor_heating` | power, target temperature | `climate.*` или строго power через `switch.*` |
| `temperature_sensor` | только наблюдение | команд нет |
| `humidity_sensor` | только наблюдение | команд нет |

Реестр не создаётся из найденного оборудования автоматически. Сначала HASC
показывает администратору кандидатов из текущего Climate API, затем владелец
явно сохраняет полное соответствие. Это исключает случайный захват похожего
или перемещённого устройства.

Пример синтетической записи:

```json
{
  "version": 1,
  "rooms": [{"id": "living", "name": "Гостиная"}],
  "devices": [
    {
      "id": "living_ac",
      "name": "Кондиционер",
      "room_id": "living",
      "kind": "air_conditioner",
      "source_id": "private-climate-source",
      "control_scope": "canary",
      "control_owner": "climate_core",
      "capabilities": ["power", "target_temperature", "hvac_mode", "fan_mode"],
      "endpoints": [
        {"role": "control", "entity_id": "climate.private_control"}
      ]
    }
  ]
}
```

`source_id` и `entity_id` хранятся только в приватном Home Assistant Store и
видны только через локальный административный маршрут.

## Android API

Все маршруты требуют обычную Home Assistant Bearer-аутентификацию, разрешают
только loopback/RFC1918/ULA источник, не поддерживают CORS и возвращают
`Cache-Control: no-store`.

Для отдельного обычного пользователя планшета, состоящего ровно в стандартной
группе Home Assistant `system-users`:

- `GET /api/hausman_hub/v1/home` — комнаты, логические устройства, состояния,
  targets, capabilities и состояние сверки без приватных ID;
- `POST /api/hausman_hub/v1/actions` — только фиксированные типизированные
  действия.

Для локального администратора:

- `GET /api/hausman_hub/v1/admin/climate-import` — read-only кандидаты и
  расхождения с текущим Climate API;
- `GET /api/hausman_hub/v1/admin/climate-registry` — сохранённый приватный
  реестр;
- `POST /api/hausman_hub/v1/admin/climate-registry` — полная атомарная замена
  реестра после строгой проверки всех полей; в активном `canary` замена
  запрещена, сначала требуется вернуться в `shadow` или `disabled`.

Аккаунт планшета не может читать административные маршруты. Администратор не
подменяет обычный аккаунт на Android-маршрутах.

## Команды Android

Android отправляет только публичные ID HASC и типизированное значение:

```json
{
  "action": "set_room_target",
  "room_id": "living",
  "target_temperature": 24.5
}
```

Разрешены:

- для комнаты: `set_room_target`, `set_room_mode`, `set_room_min_target`,
  `set_room_target_strategy`, `turn_room_off`;
- для устройства: `set_device_power`, `set_device_target_temperature`,
  `set_device_target_humidity`, `set_device_hvac_mode`,
  `set_device_fan_mode`.

Температура ограничена диапазоном 18–28 °C и шагом 0,5 °C; humidity — целым
значением 30–70%; room mode — только `auto`/`manual`; target strategy — только
`soft`/`normal`/`aggressive`. Набор HVAC и fan modes также закрыт.

HASC сам находит приватный source, проверяет тип устройства и capability, а
затем переводит intent в существующий контракт climate-core. Клиент не может
передать service, backend command type, source ID, entity ID, произвольный URL
или произвольный вложенный payload.

## Disabled, shadow и canary

Климатический мост настраивается отдельно от прежнего режима наблюдения HASC.

- `disabled` — полный откат. Адрес и canary-комната удаляются из options,
  чтения и команды выключены; локальный администратор всё ещё может подготовить
  реестр.
- `shadow` — HASC читает Climate API, строит Android snapshot и проверяет
  перевод команд, но никогда не выполняет POST. Ответ действия имеет статус
  `shadow`.
- `canary` — POST разрешён только для одной явно выбранной комнаты.

Перед каждым canary POST HASC заново требует:

1. свежий Climate API snapshot;
2. точное совпадение комнаты и сохранённой привязки;
3. `authority_eligible=true` от текущего climate-core;
4. scope устройства `canary` или `managed` и owner `climate_core`;
5. объявленный самим climate-core точный backend command type.

Сам climate-core после этого сохраняет свои обычные safety, cooldown,
автоматическую политику и physical feedback. HTTP redirect, публичный адрес,
DNS-имя, credentials в URL, неизвестная команда, лишнее поле, большой или
повреждённый ответ закрывают операцию.

## Порядок первого включения

1. Установить HASC 0.5.0, оставить climate bridge в `disabled`.
2. В options выбрать `shadow` и указать только приватный literal-IP origin
   текущего Climate API, например `http://192.168.1.10:1880`.
3. Локальным администратором прочитать import-кандидатов и сохранить явный
   registry.
4. Проверить Android snapshot и shadow-действия. Ни одно из них не должно
   выполнить POST.
5. Выбрать одну authority-ready комнату, назначить её устройству scope
   `canary`, включить bridge mode `canary` и указать тот же room ID.
6. Проверить одно изменение target, затем перечитать snapshot и физическое
   подтверждение в существующем контуре.
7. При любом расхождении вернуть `disabled`: это удаляет адрес и room ID из
   options и немедленно закрывает командный путь.

В репозитории нет live-адреса и готового реестра конкретного дома. Версия
0.5.0 подготавливает проверяемый HASC backend; переключение установленного дома
и Android-приложения выполняется отдельным контролируемым этапом после shadow.
