# TODO по плану `fss-glowing-island.md` — с распределением по моделям/агентам

Компаньон к `fss-glowing-island.md`. Тот файл — **почему/что** (обоснование, границы). Этот — **как/кто/в каком порядке**.
Отмечай `[x]` по ходу. Все пути — от корня репо `C:\Users\nafan\Documents\ED_Autopilot\` (git теперь в корне, HEAD `81071e7`).

---

## Легенда моделей и правило делегирования

| Метка | Кто | Когда |
|---|---|---|
| 🐤 **Haiku** | `claude-haiku-4-5` | Механические, самодостаточные: удаление файлов, вычистка строк локализации, простые текстовые правки без анализа сцепления. |
| 🔵 **Sonnet** | `claude-sonnet-5` | Правки кода с локальным анализом: вычистка импортов/инстансов, удаление GUI-веток, перенос методов в сервис по готовому списку. |
| 🟣 **Opus** | `claude-opus-4-8` | Архитектура и решения с неочевидными трейд-оффами: sensor-fusion топлива, Watchdog/state-machine, тайминги-по-кораблю, click-through окно. |

**Правило делегирования (согласовано): субагент — ТОЛЬКО если задача самодостаточна.**
Субагент стартует с холодного старта и заново вычитывает контекст. Делегировать выгодно, лишь когда входы/выходы описываются в 1-2 абзацах и агенту не нужно держать в голове остальной план. Задачи, завязанные на общий контекст декомпозиции (согласованность сервисов между собой), — **делаю сам, просто на нужной модели** (переключаю `/model` или прошу пользователя).

Обозначения в задачах:
- **[DELEGATE]** — годится в отдельного субагента (самодостаточна). Даю агенту точный список файлов/строк, он не исследует заново.
- **[INLINE]** — делаю в основной сессии на указанной модели (нужен общий контекст / согласованность).

---

## ФАЗА 0 — Подготовка (сделать до всего)

- [x] 🐤 Репо поднято в корень `ED_Autopilot/`, `.claude/` в `.gitignore`. *(сделано)*
- [x] 🔵 [INLINE] Создать рабочую ветку от `81071e7`: `cleanup-decompose-avionics` *(сделано)*
- [x] 🔵 [INLINE] Зафиксировать `.gitignore` отдельным коммитом (`07f445f`), старт ветки чистый. *(сделано)*
- [x] ✅ **Рабочая среда (новый комп, ED НЕ установлена):** Python 3.11.9 (winget) + venv `venv\` + 123 пакета из requirements.txt. *(сделано)*
- [x] ✅ **Мок-среда ED:** GUI требует файлы игры (settings/journal/binds/live-JSON) иначе `raise`. Скрипт `tools/setup_mock_env.ps1` (коммит `cfc522c`) кладёт заглушки в `%LOCALAPPDATA%`+`Saved Games`. GUI стартует чисто (exit 0). Игровая верификация — на др. машине с ED. *(сделано)*
- [x] ✅ Baseline: `.\venv\Scripts\python.exe -c "import EDAPGui"` OK + GUI запускается. Эталон для сравнения после каждого шага. *(сделано)*

---

## ФАЗА 1 — Расчистка периферии (Этап 1.1, 1.4, 1.5 плана)

> ⚠️ Уточнение по разведке: `ED_AP.py` **напрямую импортирует и инстанцирует** удаляемые модули в `__init__`. Удаление — не `rm`, а распутывание импортов + инстансов + использований. Поэтому это **Sonnet**, не Haiku. Точные точки сцепления (проверено):
> - `EDGalaxyMap`: import `ED_AP.py:25`, инстанс `:199` (`self.galaxy_map`), исп. `:733-734`, `:3992` (в удаляемом single-waypoint).
> - `EDSystemMap`: import `:29`, инстанс `:200`, **0 др. использований** → чистое.
> - `EDInternalStatusPanel`: import `:38`, инстанс `:198`, **0 др.** → чистое.
> - `EDStationServicesInShip`: import `:28`, инстанс `:201`, **0 др.** → чистое.
> - `AFK_Combat`: import `:37`, инстанс `:192` (`self.afk_combat`), исп. `:3956-3967` (весь AFK-блок).
> - `TceIntegration`: import `:46`, lazy-property `:296-300` (`self._tce_integration`, `:116`).
> - `EDMesgServer`: import `:24`, инстанс `:204`, исп. `:205-208` (старт сервера). **ОСТАЁТСЯ** — кандидат в фундамент веб-сервера, не удаляем (см. 1.1 и [[web-ui-direction]]).
> - `from EDWayPoint import *` (`:34`), `from Robigo import *` (`:45`) — звёздочные, найти реально используемые имена перед вырезанием.
> - `read_json_file`/`write_json_file`: `from EDAPColonizeEditor import ...` (`:18`) — эти ДВЕ функции переезжают в `JsonConfigIO.py` (см. Фаза 2), НЕ удалять пока.

### 1.1 — Удаление самодостаточных файлов (пачкой)

- [x] 🐤 [DELEGATE] Удалить файлы (git rm), список закрытый — агенту исследовать не нужно: *(сделано inline — 41 staged D: 12 кода + 5 тестов + 5 docs + 4 templates + 11 screen + waypoints/. EDMesg/EDAPColonizeEditor/EDFSS сохранены. NB: import EDAPGui сейчас СЛОМАН — чинится в 1.2.)*
  - Код: `Robigo.py`, `EDafk_combat.py`, `TCE_Integration.py`, `EDWayPoint.py`, `EDAPWaypointEditor.py`, `EDGalaxyMap.py`, `EDSystemMap.py`, `EDInternalStatusPanel.py`, `MarketParser.py`, `CargoParser.py`, `FleetCarrierMonitorDataParser.py`, `EDStationServicesInShip.py`
  - ⚠️ **EDMesg НЕ удаляем** (`EDAP_EDMesg_Server.py`, `_Client.py`, `_Interface.py`, каталог `EDMesg/`) — решение от 2026-07-06: веб-интерфейс заменит tkinter, EDMesg (ZeroMQ IPC внешнего управления) — кандидат в фундамент/референс веб-сервера. Оставить, пометить «пересмотреть в веб-фазе». См. [[web-ui-direction]]. В `ED_AP.py` его инстанс (`:204-208`) на время можно оставить как есть или обернуть в `if config['EnableEDMesg']` (уже так и есть, `:207`) — не трогать в Фазе 1.
  - Тесты: `Test_Routines.py`, `test_GalaxyMap.py`, `test_SystemMap.py`, `test_InternalStatusPanel.py`, `test_StationServicesInShip.py`
  - Docs: `docs/Robigo.md`, `docs/TCE.md`, `docs/ColonizationEditor.md`, `docs/Waypoint.md`, `docs/WaypointEditor.md`
  - templates: `templates/robigo-mines-selected.png`, `templates/sirius-atmos-selected.png`, `templates/completed-missions.png`, `templates/dest-sirius-atmos-HL.png`
  - screen: `screen/ColonizationEditor.png`, `screen/ColonizationEditorCommoditiesList.png`, `screen/ColonizationEditorConstructionsList.png`, `screen/TCE.png`, `screen/WaypointEditorShoppingList*.png` (6 файлов), `screen/WaypointEditorWaypoints*.png`
  - данные: каталог `waypoints/` (`BeaglePoint.json`, `completed.json`, `repeat.json`, `waypoints.json`)
  - ⚠️ НЕ удалять пока: `EDAPColonizeEditor.py` (из него ещё переезжают 2 функции — Фаза 2).
  - После удаления: `git status` для контроля, что ничего лишнего не задето.

- [x] > `EDWayPoint.py` — просмотрен: geo-математики посадки/координат НЕТ (нет lat/long/heading/haversine). Это trade-loop + waypoint-file оркестрация. Переносить нечего. **PR-заметка:** EDWayPoint.py удалён целиком, полезных для будущего waypoint-автопилота расчётов не содержал; восстановим из git при необходимости.

### 1.2 — Вычистка ядра `ED_AP.py` от удалённой периферии

- [x] 🔵 [INLINE] Удалить импорты `ED_AP.py`: EDGalaxyMap, EDStationServicesInShip, EDSystemMap, `EDWayPoint *`, `AFK_Combat`, `EDInternalStatusPanel`, `Robigo *`, `TceIntegration`. EDMesg **оставлен**. *(сделано)*
- [x] 🔵 [INLINE] Удалить инстансы в `__init__`: afk_combat, waypoint, robigo, internal_panel, galaxy_map, system_map, stn_svcs_in_ship. mesg_server **оставлен**. *(сделано)*
- [x] 🔵 [INLINE] Удалить lazy-property `tce_integration` + поле `_tce_integration`. *(сделано)*
- [x] 🔵 [INLINE] Вычистить использования: AFK-блок, весь waypoint-блок (`waypoint_assist`, `single_waypoint_assist`, `execute_trade`-код в EDWayPoint — удалён вместе с файлом), Robigo-блок, конфиг-ключи (HotKey_StartRobigo, Robigo_Single_Loop, AFKCombat_*, TCE*, WaypointFilepath, GalMap_SystemSelectDelay, FleetCarrierMonitorCAPIDataPath — и default-словарь, и upgrade-блок `if X not in cnf`). *(сделано)*
- [x] ⚠️ **Находка не в исходной разведке:** `waypoint_undock_seq()` вызывается из **core**-методов (`fsd_assist`, `supercruise_to_station`, `sc_assist`) — НЕ waypoint-only несмотря на имя. Восстановлен из git history, переименован в `undock_seq` (это и была идея плана 2.5, просто выполнена в 1.2 вместо 2.5, т.к. без него ED_AP.py не собирался). Обновлены все 4 call site + рудиментарные комментарии "waypoint file"/"Waypoint Assist". **План 2.5 больше не актуален** (переименование уже сделано) — снять при декомпозиции docking_service.
- [x] ⚠️ **Находка:** `EDAPColonizeEditor.py` тянул удалённый `FleetCarrierMonitorDataParser` на уровне модуля → ломало import `read_json_file`/`write_json_file` даже в ED_AP.py. Сделан мини-шаг 2.1 заранее: создан `JsonConfigIO.py`, туда перенесены обе функции, `ED_AP.py:18` и `EDAPColonizeEditor.py` переключены на импорт оттуда. **Фаза 2 п.2.1 частично сделана** — осталось только удалить `EDAPColonizeEditor.py` целиком (ждёт GUI-чистки 1.4, `ColonizeEditorTab` ещё используется в EDAPGui.py).
- [x] 🔵 [INLINE] После каждой пачки: `python -c "import ED_AP"` — чисто, `import EDAPGui` пока ломается на `ColonizeEditorTab`/`FleetCarrierMonitorDataParser` (ожидаемо, чинится в 1.4).

*Почему INLINE: правки в одном живом файле должны быть согласованы между собой; субагент, вычищая импорты вслепую, не увидит, что инстанс используется в другой строке. Держу весь `ED_AP.py`-контекст сам.*

### 1.3 — DSS Assist (подтверждён нерабочим)

- [x] 🔵 [INLINE] Удалить в `ED_AP.py`: `dss_assist`, тумблер `dss_assist_enabled`, `set_dss_assist`, ветку в `engine_loop`. **`honk()`/`DSSButton`/`Wait_DSSScan` СОХРАНЕНЫ** — используются общим кодом заряда сканера, не только DSS Assist. *(сделано)*
- [x] 🔵 [INLINE] Удалить в `EDAPGui.py`: `start_dss`/`stop_dss`, их вызовы в `callback()`, чекбоксы/ветки. *(сделано)*

### 1.4 — GUI-чистка `EDAPGui.py`

- [x] 🔵 [INLINE] `modes_check_fields`: убрать `Robigo Assist`, `AFK Combat Assist`, `Waypoint Assist`, `DSS Assist`; оставить `FSD Route Assist`, `Supercruise Assist`. *(сделано)*
- [x] 🔵 [INLINE] Удалить импорты `ColonizeEditorTab`, `WaypointEditorTab`. *(сделано)*
- [x] 🔵 [INLINE] Удалить методы `start_robigo`/`stop_robigo`, `start_waypoint`/`stop_waypoint`, `start_single_waypoint_assist`/`stop_single_waypoint_assist`, ветки в `callback()`. *(сделано)*
- [x] 🔵 [INLINE] Удалить `blk_afk_combat` LabelFrame, вкладки `page_tce_integration`(TCE Integration tab), `tab_colonize_editor`, `page_waypoint_editor`, "Single Waypoint Assist" LabelFrame. *(сделано)*
- [x] 🐤 Убрать комментарий-заметку про AFSS/SCAN1 — сделано inline вместе с остальной GUI-чисткой (не отдельным делегированием). Кнопка `btn_fss` + обработчик `test_fss_click` — ОСТАВЛЕНЫ. *(сделано)*
- [ ] 🟣 [INLINE] Добавить чекбокс "ELW/AW Advisor" (тумблер `ELWAdvisorEnabled`) в Settings — связано с 1.7, делаю вместе с ним. **НЕ сделано** — переносится на момент декомпозиции `elw_advisor.py` (Фаза 2.6), не раньше.
- [x] ⚠️ **Два непредвиденных бага, найденных только реальным запуском GUI** (не ловились `import`):
  - `Image_Templates.py` падал на `cv2.resize` (assertion `!ssize.empty()`) — грузил 4 удалённых Robigo-шаблона (`completed-missions.png`, `dest-sirius-atmos-HL.png`, `robigo-mines-selected.png`, `sirius-atmos-selected.png`). Убраны из `self.template{...}` init и `reload_templates()`.
  - `ED_AP.py` падал `NameError: ship_rpy_sc_50` — скрытая транзитивная зависимость: `ED_AP.py` раньше получал `ship_rpy_sc_50`/`Flags*`/`GuiFocus*` и др. из `EDAP_data.py` НЕ напрямую, а через цепочку `from EDWayPoint import *` → (`EDWayPoint.py` делал `from EDAP_data import *`). Удаление `EDWayPoint.py` разорвало цепочку молча. Добавлен явный `from EDAP_data import *` в `ED_AP.py:18`. **Урок: звёздочные импорты в этой кодовой базе прячут реальные межмодульные зависимости — при декомпозиции (Фаза 2) внимательно проверять, что каждый удаляемый/переносимый файл не был скрытым транзитным поставщиком имён.**
- [x] ✅ **Верификация реальным запуском** (не просто `import`): GUI запущен через `tools/setup_mock_env.ps1` + `python EDAPGui.py`, процесс стабилен 11+ секунд, лог чист (только ожидаемые ERROR про отсутствие окна ED — baseline), исключений нет.

### 1.5 — Конфиг и локализация

- [ ] 🔵 [INLINE] `ED_AP.py` дефолтный конфиг (`:351-428`): убрать `HotKey_StartRobigo`, `Robigo_Single_Loop`, `AFKCombat_*`, `TCEDestinationFilepath`, `EDMesg*Port`, `GalMap_*`, waypoint-ключи. Добавить `ELWAdvisorEnabled: True`.
- [ ] 🐤 [DELEGATE] Вычистить `locales/{de,en,es,fr,ru}.json` от строк удалённых фич (Robigo/AFK/TCE/Waypoint/DSS/Auto-FSS, включая `AFSS_BUSY`). **СОХРАНИТЬ** все `ELW_*` строки (напр. `ELW_FSS_NOT_OPEN`) — нужны ELW-советнику. Задача самодостаточна: дать агенту список ключей-на-удаление и список-на-сохранение, 5 файлов, механическая сверка. Агент возвращает: какие ключи удалил в каждом файле.

### Контроль конца Фазы 1 (частично)
- [ ] 🔵 [INLINE] `python -c "import EDAPGui"` без ошибок.
- [ ] 🟣 [INLINE] Запуск GUI: окно открывается, вкладки = минимальный набор (Main FSD/SC, Settings, Game, Debug/Test урезанный, Calibration + тумблер ELW).

---

## ФАЗА 2 — Декомпозиция `ED_AP.py` на сервисы (Этап 1.3, 1.7)

> 🖥️ **Держать в голове «MCDU-контракт» (см. [[web-ui-direction]]):** Фаза 7 сделает MCDU-фронтенд витриной этих сервисов. Значит сервисы Фаз 2-4 должны уметь отдавать **структурированные данные для страниц**, а не только скаляры для тумблеров: `navigation_service`+`NavRouteParser` → маршрут как список систем С флагами заправляемости (для ROUTE-страницы и сценария «SCOOP SEARCH»); `FuelState` (Фаза 3) → структура-прогноз (для FUEL-страницы). На этом этапе (чистый рефактор) поведение не меняем, но проектируя границы/сигнатуры сервисов — закладывать возможность такого чтения (напр. метод, возвращающий список-с-флагами, а не только «следующая цель»). Не строить сам веб сейчас — только не закрывать себе дорогу к нему.

> Порядок строгий, по одному сервису, `python -c "import EDAPGui"` + короткий FSD-прогон в игре после каждого. Все переносы — **чистый рефактор без изменения логики**.
> **Все [INLINE] на 🔵 Sonnet** (перенос по готовому списку методов), КРОМЕ решений о границах сервиса — там где неочевидно, поднять на 🟣. Причина не-делегирования в субагента: сервисы должны быть согласованы по сигнатурам конструкторов между собой (общий паттерн внедрения зависимостей `scr_reg/keys/status/jn/ap_ckb`), а субагент каждого сервиса не видит остальные.

- [ ] 🔵 [INLINE] **2.1 `JsonConfigIO.py`** — перенести `read_json_file`/`write_json_file` из `EDAPColonizeEditor.py`. Обновить импорт `ED_AP.py:18` → `from JsonConfigIO import ...`. Затем **удалить `EDAPColonizeEditor.py`** (git rm) + `docs/ColonizationEditor.md` если не удалён. Проверить: импорт, запись/чтение `AP.json`.
- [ ] 🔵 [INLINE] **2.2 `services/fuel_service.py`** — `refuel_new`; `refuel` (мёртвый) удалить сразу. Проверка в игре.
- [ ] 🔵 [INLINE] **2.3 `services/navigation_service.py`** — `get_nav_offset`, `get_target_offset`, `get_compass_target_offset`, `compass_align`, `sc_target_align`, `mnvr_to_target`, `sun_avoid`, `overheat_escape`, `is_sun_dead_ahead`, `interdiction_check`. Проверка.
- [ ] 🔵 [INLINE] **2.4 `services/jump_service.py`** — `jump`, `honk`, `position`, `fsd_assist`. Проверка.
- [ ] 🔵 [INLINE] **2.5 `services/docking_service.py`** — `dock`, `undock`, `request_docking`, `waypoint_undock_seq`→переименовать `undock_seq`, `sc_assist`, `sc_engage`, `sc_disengage`-связанное. Проверка.
- [ ] 🔵 [INLINE] **2.6 `services/elw_advisor.py`** — `fss_detect_elw`, `poll_body_scans`, `edsm_check_system`, `_body_is_valuable`, `_announce_body`, `test_fss_scan`. **+ привязать `EDFSS.py` и lazy-property `fss_screen` (`ED_AP.py:317-320`) сюда** (зависимость ELW, не удалять!). Одновременно — 1.7 (опциональность).

### 1.7 — ELW-советник опциональный (вместе с 2.6)
- [ ] 🟣 [INLINE] Сервис `elw_advisor.py` сам проверяет `config.get('ELWAdvisorEnabled', True)` внутри публичных методов (предпочтительный вариант — меньше разбросанных `if`). Вызовы из ядра (`position()`:3179, `refuel_new()`:3471, `engine_loop`:4379 → теперь через сервисы) всегда дёргают, сервис сам решает. Проверить оба положения тумблера.

### Контроль конца Фазы 2
- [ ] 🟣 [INLINE] Полный GUI + FSD Route Assist в игре + ELW тумблер вкл/выкл идентичен старому поведению при вкл.

---

## ФАЗА 3 — Топливо: sensor fusion + route budget (Этап 2.A) 🟣 ОПUS

> Целиком архитектурная, с трейд-оффами голосования источников — **Opus, [INLINE]**. Единственная делегируемая часть — сбор фактов о доступных полях (можно 🔵 Explore-агент).

- [ ] 🔵 [DELEGATE→Explore] Собрать точные сигнатуры источников топлива: что отдаёт `EDJournal.ship_state()` (поля `fuel_level`/`fuel_capacity`/`fuel_percent`), какие поля `Fuel.FuelMain`/`FuelReservoir` в `StatusParser`, флаг `FlagsLowFuel`. Вернуть таблицу «поле → тип → откуда → частота обновления». Самодостаточно, экономит мой контекст.
- [ ] 🟣 [INLINE] **`FuelState.py`** (отдельный файл, не часть fuel_service): сбор всех источников, статус достоверности `OK/STALE/DISAGREE/UNKNOWN`, правило голосования fail-safe (НЕ молчаливый `=10`, ср. `EDJournal.py:481-484`), учёт `FuelReservoir`.
- [ ] 🟣 [INLINE] Route budget: расширить **уже подключённый** `self.nav_route` (`ED_AP.py:196`; закомм. дубль `:3723` удалить). Прогноз «хватит ли на N прыжков». Пред-прыжковая проверка через `FuelState`+бюджет перед `mnvr_to_target`/`jump`.
- [ ] 🟣 [INLINE] Адаптивное завершение дозаправки в `fuel_service`: отслеживать скорость роста `fuel_percent`/`FuelMain`, ждать пока скорость >0, стоп при ~0 на N проверок. `FuelScoopTimeOut` — только крайний предохранитель.
- [ ] 🟣 [INLINE] Проверка в игре: маршрут с незаправляемыми звёздами подряд — предупреждение/стоп заблаговременно.

---

## ФАЗА 4 — Watchdog + Safe-State + State Machine (Этап 2.B) 🟣 ОПUS

> Ядро надёжности, [INLINE] на Opus целиком. Разбить на под-шаги, проверять по одному.

- [ ] 🟣 [INLINE] **Шаг 1 — Watchdog/Health Monitor** (независимый поток/тикер): следит за таймаутом шага, перегревом, топливом (`FuelState`), фокусом окна (Фаза 6). Два класса срабатываний:
  - Авария → throttle 0, `EDKeys.release_all_keys()`, корректная остановка AP с причиной (вместо тихого `except Exception` в `engine_loop`).
  - Потеря фокуса → пауза без сброса (Фаза 6).
- [ ] 🟣 [INLINE] **Шаг 2 — State Machine** (после обкатки Watchdog): `fsd_assist`/`mnvr_to_target`/`jump` → явные состояния `Aligning/Charging/Jumping/Refueling/Positioning/Aborting` с entry/exit/таймаутами. По одному переходу, проверка в игре.
- [ ] 🔵 [INLINE] Попутные фиксы: `interdiction_check()` внутрь `jump()`'s `wait_for_flag_on`; логирование `tar_behind`-веток в `sc_target_align`.
- [ ] 🟣 [INLINE] Проверка: спровоцировать неудачные выравнивания — Watchdog переводит в safe-state с сообщением, не виснет.

---

## ФАЗА 5 — Тайминги по профилю корабля (Этап 2.C) — НИЗКИЙ ПРИОРИТЕТ, ПОСЛЕДНЕЙ

> ⚠️ Делать только после обкатки 3/4/6. Источник данных — **`ship_configs` в `EDAP_data.py:213+`** (Python-словарь, НЕ `ship_configs.json` — того нет; хотя имя зарезервировано в `.gitignore:23` под локальный оверрайд).

- [ ] 🔵 [DELEGATE→Explore] Найти, где уже читается/применяется поле **`SunPitchUp+Time`** из `ship_configs` (в `sun_avoid`/`position`/`mnvr_to_target`?). Вернуть точные места. Критично: НЕ дублировать per-ship корректор времени ухода от звезды. Самодостаточно.
- [ ] 🟣 [INLINE] `Wait_PastSun` (`ED_AP.py:425`, 12.0) → функция от `PitchRate`/`RollRate` + согласование с существующим `SunPitchUp+Time`. Медленным (Тайп-9) больше, манёвренным (Мандалай) меньше. Event-driven с нижней границей по кораблю.
- [ ] 🐤 [DELEGATE] Poll-интервал `wait_for_flag_on/off` (`StatusParser.py:405-437`) 0.5s → 0.1-0.2s. Самое безопасное, механическое. Агент правит константу + проверяет импорт.
- [ ] — НЕ трогать: `Wait_HeatDissipate` (`:426`), `Wait_AfterJump` (`:427`), заряд FSD, время прыжка, остывание.
- [ ] 🟣 [INLINE] Проверка: одно и то же сближение со звездой на Мандалай vs Тайп-9 — тяжёлый получает больше времени.

---

## ФАЗА 6 — Пауза при потере фокуса игры (Этап 2.D) 🟣 ОПUS

> ⚠️ **Пересмотр из-за веб-решения (см. Фаза 7 / [[web-ui-direction]]):** проблема «мини-панель/оверлей перехватывает фокус» **исчезает сама**, если UI переезжает на планшет — оверлея поверх игры больше нет. Click-through окно тогда не нужно. НО «пауза при потере фокуса игры» (пользователь сам переключился в браузер/меню) как логика Watchdog — **остаётся нужной**. Итог: часть про click-through overlay — под вопросом (делать только если оверлей на игровом ПК всё же сохраняется как индикатор), часть про детект фокуса + пауза — остаётся.

- [ ] 🔵 [DELEGATE→Explore] В `Overlay.py` найти, где создаётся окно overlay/мини-панели (какой toolkit, где хендл окна). Вернуть точное место + как получить HWND. Самодостаточно. *(если оверлей сохраняется)*
- [ ] 🟣 [INLINE] **Click-through окно** *(только если оверлей на игровом ПК остаётся)*: `WS_EX_TRANSPARENT`/`WS_EX_LAYERED` через `pywin32`/`ctypes`.
- [ ] 🟣 [INLINE] **Watchdog детект фокуса** (тот же из Фазы 4): активное окно == Elite Dangerous? При потере — пауза отправки нажатий (заморозка шага, НЕ safe-state), лог+UI.
- [ ] 🟣 [INLINE] **Возобновление**: авто если фокус вернулся <30-60с; иначе кнопка «ПРОДОЛЖИТЬ» в GUI/мини-панели.
- [ ] 🟣 [INLINE] Проверка: навести мышь/кликнуть на панель при активном AP — инпуты доходят до игры; переключение окна и обратно восстанавливает.

---

## ФАЗА 7 — Веб-интерфейс: headless-сервер + MCDU на планшете 🟣 ОПUS

> **Решение 2026-07-06:** tkinter GUI (`EDAPGui.py`) **полностью заменяется** веб-интерфейсом. Автопилот → headless-сервис на игровом ПК; интерфейс → веб-страница на планшете/браузере рядом с клавиатурой (реальный MCDU-терминал, тема «авионика»). Делается ПОСЛЕ Фаз 1-2 (нужно headless-ядро). Порядок — выбор пользователя. См. [[web-ui-direction]].

### 7.1 — Опора на существующее (не строить с нуля)
- [ ] 🟣 [INLINE] Ревизия `EDMesg` (сохранён из Фазы 1): ZeroMQ IPC внешнего управления — оценить, годится ли как транспорт веб-сервера или нужен HTTP+WebSocket поверх/вместо. `ap_ckb` callback-мост (`ED_AP.py`) — существующий шов ядро↔UI, формализовать его в событийный поток для веба.
- [ ] 🔵 [DELEGATE→Explore] Инвентаризация: все точки, где `EDAPGui.py` читает состояние ядра и шлёт команды (тумблеры, кнопки, LOG). Вернуть список «сигнал → источник → как обновляется». Основа контракта веб-API. Самодостаточно.

### 7.2 — Headless-сервер
- [ ] 🟣 [INLINE] Тонкий слой: HTTP (отдать статику MCDU) + WebSocket (двусторонний: состояние→UI, команды←UI). Библиотека — TBD (`aiohttp` уже в requirements; или `fastapi`+`uvicorn`). Запуск сервиса без tkinter.
- [ ] 🟣 [INLINE] Точка входа: автопилот стартует как сервис (`ED_AP` без `EDAPGui`), сервер публикует состояние из `ap_ckb`-потока, принимает команды в те же методы, что дёргал GUI.

### 7.3 — MCDU веб-фронтенд (ПОЛНЫЙ workflow, не декоративный)
> Модель взаимодействия как в реальном MCDU (см. [[web-ui-direction]]): **твёрдые кнопки = страницы-режимы** (`ROUTE`/`FUEL`/`SHIP`/`PROG`/`NAV` — выбирают ЧТО показать), **LSK (6/сторону) = контекстные действия над строкой напротив** (смысл меняется со страницей), **скретчпад = буфер** (напечатал значение → «забросил» в поле по LSK).
- [ ] 🟣 [INLINE] Каркас MCDU: **один** экран с page-flip, 6 рабочих LSK/сторону, компактный скретчпад, без дублирования SHIP/статус-бара. Тема янтарь/зелёный, моноширинный, dot-leaders — сохранить. Адаптив под планшет (touch-таргеты ≥44px).
- [ ] 🟣 [INLINE] **ROUTE-страница** (эталонный сценарий пользователя): список систем маршрута, каждая с флагом заправляемости (✗ красным для не-заправляемых). LSK на строке → подменю (RSS-скан / инфо о теле / искать заправку в радиусе). LSK «SCOOP SEARCH» → радиус из скретчпада → страница перестраивается в список ближайших заправляемых, каждая с LSK «проложить через неё». Данные — из `navigation_service`/`NavRouteParser`/`FuelState`.
- [ ] 🟣 [INLINE] **FUEL-страница**: `FuelState` (бак, прогноз на N прыжков, где следующая заправка) — витрина Фазы 3.
- [ ] 🟣 [INLINE] Прогрессивно по страницам: сначала ROUTE + LOG + базовые тумблеры (FSD/SC/Fast Travel), потом FUEL/SHIP/PROG/NAV/CALIBRATION.

### 7.4 — Удаление tkinter
- [ ] 🟣 [INLINE] После паритета веб-UI со старым — удалить `EDAPGui.py`, `Overlay.py`, `sv_ttk/`, tkinter-зависимости. Финальная цель: единственный UI = веб.

### Проверка Фазы 7
- [ ] 🟣 Открыть MCDU с планшета/второго устройства по IP игрового ПК, погонять тумблеры/страницы, убедиться что команды доходят до ядра и состояние обновляется в реальном времени.

---

## Сводка делегирования (что реально уходит от основной сессии)

| Задача | Модель | Тип | Почему делегируемо |
|---|---|---|---|
| Baseline `import EDAPGui` | 🐤 | DELEGATE | Одна команда, эталон. |
| Удаление файлов пачкой (1.1) | 🐤 | DELEGATE | Закрытый список, `git rm`. |
| Комментарий AFSS/SCAN1 (1.4) | 🐤 | DELEGATE | 2 строки. |
| Вычистка `locales/*.json` (1.5) | 🐤 | DELEGATE | Список ключей вкл/выкл, 5 файлов. |
| Факты об источниках топлива (3) | 🔵 Explore | DELEGATE | Только чтение, возвращает таблицу. |
| Места `SunPitchUp+Time` (5) | 🔵 Explore | DELEGATE | Только чтение. |
| Poll-интервал 0.5→0.2 (5) | 🐤 | DELEGATE | Одна константа. |
| Место создания окна в `Overlay.py` (6) | 🔵 Explore | DELEGATE | Только чтение. |

**Всё остальное — INLINE**, на модели по метке (🔵 переносы/GUI-чистка, 🟣 архитектура). Причина: согласованность между сервисами/файлами требует общего контекста, который субагент восстанавливал бы дороже, чем экономит.

**Переключение модели для INLINE-задач:** там где помечено 🔵 — работать на Sonnet (`/model sonnet`), где 🟣 — на Opus (`/model opus`). Группировать однотипные подряд, чтобы реже переключаться.
