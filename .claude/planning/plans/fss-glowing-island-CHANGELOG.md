# CHANGELOG по плану `fss-glowing-island.md` — выполненное, решения, находки

> Компаньон к `fss-glowing-island-TODO.md` (активные задачи) и `fss-glowing-island.md` (почему/что).
> Сюда переезжают завершённые блоки TODO целиком: даты, коммиты, находки, уроки.
> Ветка: `cleanup-decompose-avionics`, старт от `81071e7`.

---

## ФАЗА 0 — Подготовка ✅ (2026-07-06)

- Репо поднято в корень `ED_Autopilot/`, `.claude/` в `.gitignore`; `.gitignore` отдельным коммитом (`07f445f`).
- Рабочая ветка от `81071e7`: `cleanup-decompose-avionics`.
- **Рабочая среда (новый комп, ED НЕ установлена):** Python 3.11.9 (winget) + venv `venv\` + 123 пакета из requirements.txt.
- **Мок-среда ED:** GUI требует файлы игры (settings/journal/binds/live-JSON) иначе `raise`. Скрипт `tools/setup_mock_env.ps1` (коммит `cfc522c`) кладёт заглушки в `%LOCALAPPDATA%`+`Saved Games`. GUI стартует чисто (exit 0). Игровая верификация — на др. машине с ED.
- Baseline: `.\venv\Scripts\python.exe -c "import EDAPGui"` OK + GUI запускается — эталон для сравнения после каждого шага.

---

## ФАЗА 1 — Расчистка периферии ✅ (2026-07-07)

**Разведка точек сцепления** (`ED_AP.py` напрямую импортирует и инстанцирует периферию в `__init__` → удаление = распутывание, не `rm`):
- `EDGalaxyMap`: import `:25`, инстанс `:199`, исп. `:733-734`, `:3992`. `EDSystemMap` `:29`/`:200` (0 исп.). `EDInternalStatusPanel` `:38`/`:198` (0). `EDStationServicesInShip` `:28`/`:201` (0). `AFK_Combat` `:37`/`:192`, исп. `:3956-3967`. `TceIntegration` `:46`, lazy `:296-300`. `EDMesgServer` `:24`/`:204-208` — тогда ОСТАВЛЕН (позже удалён в 7.1). Звёздочные `EDWayPoint *`/`Robigo *`. `read_json_file`/`write_json_file` из `EDAPColonizeEditor` → уехали в `JsonConfigIO.py`.

### 1.1 — Удаление самодостаточных файлов
- 41 staged D: 12 кода (`Robigo.py`, `EDafk_combat.py`, `TCE_Integration.py`, `EDWayPoint.py`, `EDAPWaypointEditor.py`, `EDGalaxyMap.py`, `EDSystemMap.py`, `EDInternalStatusPanel.py`, `MarketParser.py`, `CargoParser.py`, `FleetCarrierMonitorDataParser.py`, `EDStationServicesInShip.py`) + 5 тестов + 5 docs + 4 templates + 11 screen + `waypoints/`.
- `EDWayPoint.py` просмотрен перед удалением: geo-математики посадки НЕТ (нет lat/long/haversine) — trade-loop + waypoint-file оркестрация, переносить нечего. Восстановим из git при необходимости.

### 1.2 — Вычистка ядра `ED_AP.py`
- Удалены импорты/инстансы/использования всей периферии + конфиг-ключи (HotKey_StartRobigo, Robigo_Single_Loop, AFKCombat_*, TCE*, WaypointFilepath, GalMap_SystemSelectDelay, FleetCarrierMonitorCAPIDataPath) из default-словаря и upgrade-блока.
- ⚠️ **Находка:** `waypoint_undock_seq()` вызывается из core-методов (`fsd_assist`, `supercruise_to_station`, `sc_assist`) — НЕ waypoint-only. Восстановлен из git, переименован в `undock_seq`, обновлены 4 call site (план 2.5 «переименование» тем самым выполнен досрочно).
- ⚠️ **Находка:** `EDAPColonizeEditor.py` тянул удалённый `FleetCarrierMonitorDataParser` на уровне модуля → создан `JsonConfigIO.py`, обе функции туда, импорты переключены (мини-шаг 2.1 досрочно).

### 1.3 — DSS Assist (подтверждён нерабочим)
- Удалены `dss_assist`/тумблер/`set_dss_assist`/ветка `engine_loop` + GUI-обвязка. **`honk()`/`DSSButton`/`Wait_DSSScan` СОХРАНЕНЫ** — общий код заряда сканера.

### 1.4 — GUI-чистка `EDAPGui.py`
- `modes_check_fields` → только FSD/SC; удалены методы/ветки Robigo/waypoint/AFK, вкладки TCE/Colonize/WaypointEditor, LabelFrame'ы.
- ⚠️ **Два бага, найденных только реальным запуском GUI** (import не ловил):
  - `Image_Templates.py` падал на `cv2.resize` — грузил 4 удалённых Robigo-шаблона; убраны из init и `reload_templates()`.
  - `NameError: ship_rpy_sc_50` — `ED_AP.py` получал имена из `EDAP_data.py` транзитивно через `from EDWayPoint import *`. Добавлен явный `from EDAP_data import *`. **Урок: звёздочные импорты прячут межмодульные зависимости — удаляемый файл может быть скрытым транзитным поставщиком имён.**
- Верификация реальным запуском: mock-env, стабильно 11+ c, лог чист.

### 1.5 — Конфиг и локализация
- Дефолтный конфиг перепроверен grep'ом — 0 периферийных ключей. `EDMesg*Port` тогда сохранены (их присутствие в списке плана было ошибкой).
- `locales/{de,en,es,fr,ru}.json`: 104 ключа × 5 = 520 удалений (Auto-FSS/AFSS, TCE, `WPT_*`, Robigo, AFK, DSS Assist, GalMap, `INT_PNL_*`, `STN_SVCS`/`COMMODITIES`, Colonization). `ELW_*`/`FSS_HONK_*`/`NAV_PNL_*` сохранены. QA: JSON валиден, 5×252 ключа идентичны, 0 висячих ссылок из кода. Коммит `725bf6b`.

### Контроль конца Фазы 1
- ⚠️ **Дозачистка Auto-FSS** (была в плане 1.1 без чекбокса — чуть не потерялась): блок ~660 строк в `ED_AP.py` (1145–1822) + `_afss_*` + GUI-хвосты + `GalMap_SystemSelectDelay`. Удалены, ELW-советник не тронут. Коммит `a1b9931`.
- `import EDAPGui` чист; GUI на mock-env стабилен, вкладки Main/Settings/Game/Debug-Test/Calibration.
- 🛠️ Побочно: `tools/setup_mock_env.ps1` писал mock-файлы с UTF-8 BOM под PowerShell 5.1 → GUI падал. Переведён на `UTF8Encoding($false)`. Коммит `86e046c`.
- Открытый вопрос прошлой сессии закрыт: «GUI не работает / ошибка mouse input» НЕ воспроизводится (причина неустановлена; при рецидиве снять точный текст).

---

## ФАЗА 2 — Декомпозиция `ED_AP.py` на сервисы ✅ (2026-07-07)

ED_AP.py 4574→1527 строк; вся лётная логика в `services/` + `JsonConfigIO`. Каждый вынос: Sonnet-субагент → QA → коммит; паритет тела каждого метода **IDENTICAL** против `HEAD:ED_AP.py`.

- **2.1 `JsonConfigIO.py`** — вынос был в 1.2; удалён осиротевший `EDAPColonizeEditor.py`. Коммит `9af93a5`.
- **2.2 `services/fuel_service.py`** — `refuel_new` → `FuelService`; мёртвый `refuel` удалён (0 вызовов). Коммит `adcb09a`. Здесь принят DI-шаблон (см. «Инженерные правила» в TODO).
- **2.3 `services/navigation_service.py`** — 10 методов (`get_nav_offset`, `get_target_offset`, `get_compass_target_offset`, `compass_align`, `sc_target_align`, `mnvr_to_target`, `sun_avoid`, `overheat_escape`, `is_sun_dead_ahead`, `interdiction_check`). Перевязаны вызыватели: ED_AP 22+2, EDShipControl 9, EDAPGui 1, fuel_service 7. Решён циклический импорт (правило в TODO). Коммит `9ce4d53`.
- **2.4 `services/jump_service.py`** — `honk`, `position`, `jump`, `fsd_assist`. Тонкость: `honk` (метод, вкл. thread-target) vs `honk_thread` (атрибут). Отложенные `FSDAssistReturn`+`strfdelta`. Коммит `937d3a3`.
- **2.5 `services/docking_service.py`** — 8 методов: `sc_disengage`, `undock`, `request_docking`, `dock`, `undock_seq`, `sc_engage`, `supercruise_to_station`, `sc_assist`. `EDNavigationPanel.request_docking` (перегрузка имени) не тронут. Коммит `73b9f50`.
- **2.6a `services/elw_advisor.py`** — 6 методов (`_body_is_valuable`, `_announce_body`, `poll_body_scans`, `edsm_check_system`, `fss_detect_elw`, `test_fss_scan`) + `fss_screen` property + `EDFSS`. `fss_detected` остался на ED_AP (пишет сервис, читает overlay). Коммит `5001df9`.
- **QA-гейт оптимизирован** (по просьбе снизить токены): вместо QA-субагента (45–75k токенов) — инлайн-скрипт `tools/qa_service_extraction.py --service-file … --service-module … --names a,b,c`: импорты, роутинг-инварианты, паритет против HEAD, отложенные имена, GUI-smoke на mock-env. Коммит только при all-PASS.

### 1.7 / 2.6b — тумблер ELW-советника → НЕ ТРЕБУЕТСЯ (решение пользователя)
- После декомпозиции советник уже опционален: `fss_detect_elw` гейтится `ElwScannerEnable` (чекбокс есть), `edsm_check_system` — `EDSMCheckEnable`. Безусловен только пассивный `poll_body_scans`. Третий тумблер `ELWAdvisorEnabled` решено НЕ добавлять; отложенные из Фазы 1 пункты (чекбокс 1.4, ключ 1.5) закрыты как не нужные.

---

## ПОРЯДОК ФАЗ ПЕРЕСМОТРЕН (2026-07-07, решение пользователя): ФАЗА 7 ПЕРЕД 3–4

- **3–4 нельзя делать вслепую:** FuelState и Watchdog проектируются/тюнятся по реальным потокам игры (живые `Fuel.FuelMain`/`FuelReservoir`, рассогласования, перегрев, провалы выравнивания); на статичных заглушках dev-ноута пороги не откалибровать. Непроверенный код надёжности опаснее его отсутствия.
- **Фаза 7 на ~80–90% делается без игры** (Фазы 1–2 дали headless-ядро) и раз-ослепляет 3–4: веб-телеметрия = обсервабилити, а capture-харнесс (7.0) даёт реальные данные для разработки 3–4 на ноуте.

---

## ФАЗА 7 (частично) — 7.0, 7.1, 7.2 ✅ (2026-07-07)

### 7.0 — Capture-харнесс
- `tools/capture_telemetry.py` (standalone, без ED_AP/OCR/tkinter; WindowsKnownPaths, дедуп/ротация/partial-safe; `--interval/--duration/--out-dir/--journal-events`; вывод `captures/*.jsonl` `{ts,source,data}`; `captures/` в .gitignore). Проверен на mock-env. Коммит `cb2ef30`. **Ждёт запуска в реальную игровую сессию** (задача в TODO).

### 7.1 — Ревизия EDMesg → УДАЛЁН ЦЕЛИКОМ (решение пользователя «мёртвый груз, мочи»)
- Вердикт ревизии: транспорт = ZeroMQ → браузер говорить не может, как транспорт веб-MCDU не годится; HTTP+WS обязателен независимо.
- ⚠️ Находка: `EDAP_EDMesg_Server.py` дёргал удалённые в Фазе 1 `self.ap.waypoint`/`system_map`/`galaxy_map`/`tce_integration` → частично сломан; не падал только из-за `EnableEDMesg=False`.
- Вырезано: `EDAP_EDMesg_Server/Client/Interface.py`, каталог `EDMesg/`, инстанс `mesg_server`, ключи `EnableEDMesg`/`EDMesgActionsPort`/`EDMesgEventsPort`, зависимость `pyzmq`. QA: 0 ссылок, import чист, GUI стартует. Понадобится внешнее управление — bespoke под конкретную нужду.

### 7.1 — Инвентаризация контракта GUI↔ядро → `docs/web_api_contract.md`
- ~19 чекбоксов + 27 полей (config-ключи+дефолты), 20 команд, lifecycle (долгоживущий engine-loop-поток; stop = `ctype_async_raise`), 11 `ap_ckb`-тегов (часть мёртвая), push-vs-poll.
- Выводы: (1) структурной телеметрии в push не было — нужен `status_snapshot`-event; (2) конфиг отдавать generic get/set по ключу; (3) 8 tkinter-специфичных мест переосмыслить для планшета.

### 7.2 — Headless-сервер (вертикальный срез, стек aiohttp). Коммит `e59a59c`
- `webserver/server.py`: HTTP-статика + WebSocket; `Broadcaster` мостит `ap_ckb` (worker-поток → asyncio через `call_soon_threadsafe`); маппинг тегов→JSON; `status_snapshot` 1 Гц; диспатч команд (assist start/stop/stop_all, throttle, config.get).
- `edap_headless.py`: `EDAutopilot(cb=Broadcaster)` без tkinter, чистый shutdown, `--host/--port/--duration`. + `ED_AP.get_status_dict()`.
- QA: 13/13 in-process проверок (aiohttp TestClient + fake-ядро, без OCR/VPN): статика, WS hello+snapshot, core→UI push, UI→core команды, config.get, битая команда→error. Реальный end-to-end — на игровом ПК.

### 7.3 (начато) — MCDU-фронтенд, что уже в `webserver/static/` (коммиты `eefbadd`…`ffe88d9`, 2026-07-09/10)
- Геометрия экрана rock-solid; scratchpad — реальный input (печать + буфер обмена, фикс. высота); кирилл-раскладка через физические клавиши; DIR временно возвращает на INIT-экран; PERF-страница с drag-SVG редактором RPY-кривых; `tools/demo_mcdu_server.py` — fake-core сервер для дев/QA фронтенда без ядра.

### Дизайн MCDU: сравнение 4 вариантов и нормативная спека (2026-07-10, коммиты `84b5dd2`, `c2eb4b7`)
- По ТЗ `design/mcdu-avionics-prompt.md` собраны 4 независимые выдачи (DeepSeek, MCDU_HMI_Spec, Grok, Claude). Сравнение по критериям ТЗ → `design/mcdu-design-comparison.md`; победитель — `design/mcdu-button-map.md` (полнота + контракт), в него влиты SCOOP NOW (CRUISE L5) и scoopable в R5. Проигравшие файлы удалены из рабочей копии (полные тексты — в коммите `84b5dd2`).
