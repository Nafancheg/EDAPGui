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

---

## ФАЗА 7.3 — приоритетные страницы MCDU ✅ (2026-07-10/11)

> Все четыре блока делались 🔵/🎨-субагентами по нормативной спеке `design/mcdu-button-map.md`; QA — прогоны на `tools/demo_mcdu_server.py` (fake-core) + node-проверки логики + `import ED_AP`. Каждый коммит явно закрыл свой TODO.

### 7.3.0 — Каркас HMI-контракта ✅ (коммит `d988897`)
- **STOP ALL** — hardware-кнопка в ряду slew под откидной hazard-крышкой (поднять → нажать; авто-закрытие 4 с), убрана с LSK R6 INIT.
- **Annunciator LED** на PROG (assist engaged) и FUEL PRED; приглушённые тона, без мигания (пороги 10/25% — до бэкенд-enum в 7.3.2).
- `setHeader()` — единый header-контракт, `OFFLINE` красным.
- **Scratchpad** — `INVALID`/`NOT ALLOWED`/`NOT CONNECTED` ~1.5 c С СОХРАНЕНИЕМ ввода; долгий CLR (≥600 мс) чистит всё; `+` с физ. клавиатуры.
- Нет данных = `---` s-muted везде; slew: списки только ←/→, низ зарезервирован под возврат к активной фазе PROG.

### 7.3.1 — PROG фазовая страница + PREFLIGHT + DIRECT-TO ✅ (коммиты `f605a55`, `4aecd02`, `4c2251c`)
- **PROG**: 6 фаз DEPART..LND по §3.1, boot default, slew-листание, автодетект активной фазы (эвристика v1), muted-индикатор при просмотре неактивной, ARRIVAL·STN, LND-каркас [план] с валидацией координат.
- **`ED_AP.request_action()`** — очередь one-shot действий в engine-loop (undock, request_docking, dock, enter_sc, honk, scoop, fss_scan, align_target); закрывает замечания 3 и 10 спеки; WS `action.request`.
- INIT → PREFLIGHT (§3.2), DIR → DIRECT-TO [план] (§3.5); старый перегруженный экран удалён.
- **Отступление от §1.3** (замечание 11): фазы Elite двунаправленны (петля ARRIVAL→DEPART, регресс из SC) → PREV/NEXT симметричны на L6/R6 (`stepPhase(delta)` с заворотом), а не пустой L6-корень. Фаза CLIMB отображается как **BOOST** (только label, id не тронут).

### 7.3.2 — FUEL PRED + LED из журнала ✅ (коммит `99b7514`)
- **EDJournal**: `fuel_used_hist` — `FuelUsed` последних 10 `FSDJump`.
- **`get_status_dict`**: fuel_level/capacity, avg_fuel_per_jump, jumps_to_refuel (порог `RefuelThreshold`), range_jumps, `fuel_status` normal/warning/critical/unknown; зеркало в demo FakeAP.
- **Страница FUEL PRED**: R1 %+тонны, R2 TO REFUEL, R3 AVG/JUMP, R4 RANGE, R5 порог [E] с валидацией+config.set; L1 → подстраница REFUEL SELECT (STAR THIS SYSTEM = action scoop, L6 RETURN); индикатор шапки = fuel status.
- LED FUEL PRED теперь от бэкенд-enum (клиентские пороги убраны).

### 7.3.3 — F-PLN к контракту §3.3 + доработки ✅ (коммиты `890c9f8`, `d720ba0`, `2639b9f`)
- Список приведён к §3.3, фикс FAST TRAVEL+DEST, кнопка REFRESH упразднена (автообновление на открытии + смене location).
- **Замечание 12** — по авиа-аналогии F-PLN стал непрерывной прокруткой (вертикальный slew, окно=строки) вместо страниц; строка `END OF PLAN` c `TOTAL N JMP · X.X LY` в конце.
- **Замечание 13**: левый LSK строки открывает под-страницу **SYSTEM** (класс/scoop/дистанция + BODIES из `fss_body_count` + EDSM [план] Ф8.1) вместо scratchpad-инфо. Круизные настройки сведены на новую **CRU OPT** (из RAD NAV INOP): FAST TRAVEL [T], ELW SCAN [T], HONK/FSS SCAN [A] — фаза CRUISE разгружена до FSD ROUTE + SCOOP NOW. `fss_body_count` добавлен в `get_status_dict`+demo.
- **Отложено** (Ф3/уточнение): интерлок FAST TRAVEL и scoop-skip (пересчёт топлива).

**Правки спеки:** замечания 11, 12, 13 зафиксированы в `design/mcdu-button-map.md`.

---

## ФАЗА 8.1 — Бэкенд плоттера маршрутов (ноутбучная часть) ✅ (2026-07-13)

> Решение заказчика: веб-морду не трогаем, берём фичу, разрабатываемую без игры. Бэкенд-часть 8.1 разgateна: Spansh/EDSM — публичные HTTP API, проверены живьём с ноута ДО реализации. **Дизайн-док: `design/route-planner-backend.md`** (нормативный: проверенные форматы API, структура модуля, WS-контракт, итерации+QA).

### Выбор плоттера (закрыт открытый вопрос из [[mcdu-route-model]])
- **FAST/RISKY** = Spansh neutron (`POST /api/route` → job → poll `/api/results/{job}`); `system_jumps` = waypoint'ы перепрокладки, `jumps` = прыжков на лег, топливо НЕ моделируется → risk HIGH.
- **FUEL-SAFE** = Spansh galaxy (`POST /api/generic/route`): параметры FSD из журнального `Loadout` (таблицы констант size/class + инженерия из `Engineering.Modifiers`); результат по-прыжковый с `fuel_used`/`must_refuel`/`is_scoopable` → scoops и risk LOW считаются честно.
- **DIR-кандидаты/валидация** = EDSM `sphere-systems`/`system` (поле `isScoopable` первичной звезды, каскад радиусов 15→30→50 LY).

### Итерация 1 — `RoutePlanner.py` (🟣 Opus-субагент, коммит `dc65ab0`)
- `RoutePlanner.py` в корне (прецедент CalibrationStore): FSD-таблицы (вкл. SCO/MkII/guardian-бустеры), `ship_plot_params()`, `max_range_from_loadout()` (fallback-формула дальности), SpanshClient/EDSMClient с инжектируемой session (офлайн-QA), нормализация обоих профилей в единый Route-dict, RoutePlanner с busy-guard/snapshot; PlotError на всех путях отказа. Никаких импортов ED_AP на верхнем уровне.
- `EDJournal.py` аддитивно: `loadout_raw` (сырой dict события Loadout) + `max_jump_range` (`MaxJumpRange`, ранее не читался).
- QA `tools/qa_route_planner.py`: 15/15 PASS офлайн (fake-session) + опция `--live`.
- ⚠️ **Находка live-дыма:** Cloudflare EDSM отдаёт 403 на дефолтный UA `python-requests` (curl проходит!) — клиенты обязаны слать идентифицирующий UA (`ED_Autopilot-RoutePlanner/1.0`). Live после фикса: EDSM ок, neutron Sol→Sgr A* = 356 прыжков / 25 900 LY. **Урок: дымить внешние API реальным HTTP-клиентом проекта, а не только curl — WAF различает клиентов.**

### Итерация 2 — WS-команды (🔵 Sonnet-субагент, коммит `e3a6ce6`)
- `webserver/server.py`: `sec.plot` (ack `sec_plot_started` → executor → broadcast `sec_route`), `sec.get` (синхронно, + `compare.primary` из `route_primary_stats()` поверх map_nav_route — планнер primary не считает), `sec.activate` (заглушка NOT AVAILABLE до игровой части), `dir.nearest` (ack `dir_started` → broadcast `dir_state`), `dir.set` (False → `INVALID`). `_get_route_planner()` — ленивый синглтон по образцу `_get_calib_store()`. Busy-guard прилетает исключением из executor-future → `{"type":"error"}`; остальные ошибки планнер кладёт в `snapshot.error`.
- `docs/web_api_contract.md` §7: контракт команд/событий, форматы Route/DirCandidate.
- QA `tools/qa_route_ws.py`: aiohttp TestClient поверх `create_app` с fake-ядром и fake-планнером, 8/8 PASS без сети; регресс qa_route_planner 15/15; `import EDAPGui` ок.

**Осталось в 8.1 (в TODO):** подключение страниц SEC F-PLN §3.4 / DIR §3.5 к командам (фронт, когда вернёмся к веб-морде); ⛔игра — ввод маршрута в игру (галакарта/нав-панель) → настоящий `sec.activate` и исполнение DIR.

### Фронт-итерация — SEC F-PLN / DIR подключены к плоттеру (🔵 Sonnet-субагент + инлайн-фиксы, 2026-07-13)
- Решение заказчика «хочу видеть в MCDU» отменило отложенность фронта. `mcdu.js`: PLOT FUEL-SAFE/FAST → `sec.plot` (busy-guard, `PLOTTING…`), SEC DEST [E] с дефолтом из активного плана, COMPARE R2–R5 живые, ACTIVATE SEC шлёт `sec.activate` (ответ NOT AVAILABLE ожидаем до игры), NEAREST/DIRECT TO → `dir.nearest`/`dir.set`, карточка кандидата R2/R3; новая страница **SEC LIST** (ур.2, формат F-PLN: окно 5 строк, slew, END OF PLAN, маркеры SCOOP/NTR/·RFL). `demo_mcdu_server.py`: FakeJournal c Loadout-фикстурой (Krait MkII 5A инж.) — реальный RoutePlanner работает на fake-ядре.
- **Инлайн-фиксы по живой проверке в браузере** (реальные Spansh/EDSM через демо-сервер): (1) scratchpad-фильтр не пропускал `'`/`*` — а это легальные символы имён систем ED (Barnard's Star, Sagittarius A*); (2) успешный `dir.set` не потреблял scratchpad — добавлен `S.dirPending`, подтверждающий `dir_state` съедает ввод, `INVALID` оставляет для правки.
- Живая проверка: FUEL-SAFE Devataru→Maia = 16 прыжков/502 LY/9 заправок/LOW на странице SEC; SEC LIST с реальными системами (LP 861-12, Wolf 359…); DIR NEAREST SCOOPABLE = LTT 6566 K·5.8 LY; `SAGITTARIUS A*` валидирован («Supermassive Black Hole · 25809 LY»); состояние восстанавливается после перезагрузки страницы (`sec.get`). Замечание 18 в спеке. QA: `qa_route_ws` 8/8, `node --check`, импорт демо-сервера.

---

## Jet Cone FSD Supercharge — полный пайплайн ✅ (2026-07-14, `0a1e265`)

Автоматический заход в джет-конус нейтронной звезды для суперзарядки FSD (×4 дальность). Полный цикл: обнаружение → выравнивание → заход → выход.

### Датасет и модель
- **Датасет:** `tools/jetcone_dataset.py` — загрузка YouTube-видео заходов в конус (yt-dlp) + покадровая нарезка (ffmpeg).
- **Прелейблинг:** `tools/prelabel_jetcone.py` — HSV-автомат детектирует ярко-синие/фиолетовые конусы на тёмном фоне, сохраняет YOLO-аннотации.
- **Модель:** `Yolo26/jetcone-model/` — YOLOv8n, обучена на 94 авторазмеченных кадрах, **mAP50 = 0.715**.

### JetConeService (`services/jetcone_service.py`, 523 строки)
- **Полный алгоритм входа с YOLO:**
  1. Прибытие к нейтронной звезде → STOP (throttle 0)
  2. Screen capture → YOLO детектирует позиции и углы конусов
  3. Roll до горизонтального положения звезды (конусы слева/справа: `>o<`)
  4. Roll +90° вправо → правый конус указывает ВВЕРХ
  5. Pitch/Yaw → выравнивание параллельно конусу, лёгкий угол к дальнему концу
  6. Throttle 50% → плавный вход → OCR: "WARNING! FSD OPERATING BEYOND SAFETY LIMITS"
  7. Ожидание в турбулентности → OCR: "FRAME SHIFT DRIVE SUPERCHARGED"
  8. Throttle 100% → выход из конуса (угол зависит от геометрии, турбулентный)
  9. Курс прочь от звезды
- **Fallback (без YOLO):** слепой pitch в сторону одного из полюсов, OCR-управляемый вход.
- **Self-training:** каждый успешный OCR-вход сохраняет прелейблированный кадр для дообучения.
- **Различение типов:** нейтронные звёзды (класс N, ×4 дальность) — полный заход; белые карлики (класс D, ×1.5) — пропускаются (слишком рискованно для малого выигрыша).

### JetConeDetection — датакласс геометрии (`ED_AP.py`)
- Поля: `core`, `left_jet`, `right_jet` (bounding boxes), `axis_angle` (угол оси звезды).
- Используется YOLO-предиктом и контрольным циклом входа.

### MachineLearning (`MachineLearning.py`, +40 строк)
- Новый тип модели `JetCone`, метод `model_predict_all()` — возвращает список `JetConeDetection`.
- Модель загружается лениво при первом вызове детекции конуса.

### OCR-детекторы (панели WARNING + INFO)
- `jet_cone_entry_ocr` — ловит "FSD OPERATING BEYOND SAFETY LIMITS" на WARNING-панели.
- `jet_cone_supercharged_ocr` — ловит "FRAME SHIFT DRIVE SUPERCHARGED" на INFO-панели.

### EDJournal (`EDJournal.py`, +17 строк)
- Новое событие: `Supercharged` — флаг `fsd_supercharged`, множитель `supercharge_multiplier`.
- Читается из игрового журнала, сбрасывается при прыжке.

### Локализация
- Новые ключи `FSD_SUPERCHARGED_MSG` + `FSD_SAFETY_LIMIT_MSG` во всех 5 локалях (en/ru/de/es/fr).

### Интеграция в jump_service
- `jump_service.py` (+10 строк): после прыжка в систему с нейтронной звездой вызывается `JetConeService.run()`.

### Статистика коммита
- 17 файлов, +1203/−4 строк. Ядро: `services/jetcone_service.py` (523), `ED_AP.py` (+226), `tools/` (351), ML (+40).

---

## Механика маршрутов: ShipFSD + стенд + FAST-exact + SEC FROM ✅ (2026-07-16, `e889d20`+`053156f`+`f99258c`)

Сессия «моделируем маршрутный конвейер на ноуте» (решения заказчика: тестируем МЕХАНИКУ — расчёты/массу/заправки, не интерфейс; FROM-поле в SEC F-PLN).

### 🐞 Регрессия jetcone-коммита (`e889d20`)
`0a1e265` вставил `is_supercharged()`/`get_supercharge_mult()` В СЕРЕДИНУ `EDJournal.ship_state()` — метод обрывался после `open_journal()` и молча возвращал `None`; всё, что читает состояние корабля (планнер, топливо, статус), было сломано с 14.07. Тело восстановлено, методы перенесены ниже. Урок: jetcone-работа шла без QA-гейта маршрутного блока.

### ShipFSD — единая физика FSD (`053156f`, в `RoutePlanner.py`)
- `jump_range(fuel, cargo, supercharge)` и `fuel_cost(dist, fuel, cargo, supercharge)`: точная формула гардиан-бустера `d_eff = d/mult · R/(R+boost)` (бустерные LY бесплатны; вместо прежней аппроксимации `dist−boost` в валидаторе) + суперзаряд ×4 (нейтронка) / ×6 (SCO MkII) и в дальности, и в топливе.
- `max_range_from_loadout` и `tools/route_validity_check.py` переведены на ShipFSD; валидатор стал supercharge-aware (профиль ≠ FUEL-SAFE ⇒ нейтронные леги множатся).

### Стенд механики `tools/route_mechanics_bench.py` (`053156f`)
- Живой кросс-чек «наша формула vs Spansh exact-plotter vs EDSM» лег-за-легом; exact-plotter отдаёт свой расчёт `fuel_used`/`fuel_in_tank` по прыжку — это эталон.
- 4 конфигурации: journal (Мандалай SCO инж.), Krait 5A+гардиан-бустер, DBX дальнобойный, Panther SCO MkII ×6+бустер; каждая в plain и use_supercharge=1.
- **Итог: расход ≤0.64% расхождения, геометрия точная, топливный леджер Spansh самосогласован, семантика `fuel_in_tank` = после прилёта и дозаправки.** На игровом ПК фикстура `journal` проверит реальный корабль.

### FAST → exact-plotter + SEC FROM (`f99258c`)
- FAST = exact-plotter c `use_supercharge=1`: нейтронки+MkII×6 ВМЕСТЕ с топливной моделью и точной конфигурацией корабля ⇒ заправки известны, FAST исполним посегментно. Нейтрон-плоттер (range-only) остался WS-профилем `ultra` (не в MCDU, для сверхдальних). `_normalize_fast` теперь метит `ULTRA`.
- `Route.systems[]` + `fuel_used`/`fuel_tank` (модель Spansh по легам — база для FUEL PRED и исполнителя маршрута).
- **SEC FROM [E]** (L4, Замечание 19 в спеке): ручной старт построения, EDSM-валидация до канонического имени (`sol`→`Sol`), пустое нажатие сбрасывает к журналу; `sec.plot {source}`; контракт §7 обновлён.
- QA: qa_route_planner 16/16 (новые проверки FAST/supercharge/fuel-полей), qa_route_ws 8/8, node --check, живой прогон Sol→Maia через FROM (FAST: 5 прыжков, нейтронка Jackson'а, scoops известны; кривой FROM → чистая ошибка).

### Остаток по «моделированию маршрута» (следующая ноутбучная итерация)
Поэтапное ИСПОЛНЕНИЕ на моках: RouteExecutor/секвенсер (активный лег, продвижение по FSDJump из мок-журнала, дозаправки по fuel_tank, абстракция GalaxyMapDriver со стабом) + симулированный полёт в демо-сервере. На игру остаётся только реальный драйвер галакарты.

---

## Поэтапное исполнение маршрута: RouteExecutor + мок-полёт ✅ (2026-07-16, `d08ca32`)

Ноутбучная часть исполнения 8.1 закрыта — на игру остаётся ТОЛЬКО реальный драйвер галакарты.

### RouteExecutor.py (корень, паттерн RoutePlanner: без импорта ядра в рантайме)
- Ведёт активированный SEC-маршрут по журнальной локации (питается 1 Гц-тиком сервера). **Посегментная стратегия:** драйверу галакарты уходит конец сегмента (следующая заправка `must_refuel`, затем пункт назначения) — между ними прыжки ведёт игра.
- `GalaxyMapDriver` — интерфейс+стаб (записывает целевую систему); игровой драйвер заменит его с тем же API.
- Состояния INACTIVE/ACTIVE/OFF ROUTE/COMPLETE; сход с маршрута ловится, возврат восстанавливает ACTIVE; back-jump по плану — не сход. `snapshot()` несёт `fuel_plan`(из маршрута)/`fuel_actual`(журнал) — живой кросс-чек топлива план-vs-факт.
- Активация: ULTRA-профиль отвергается (нет топливной модели), позиция подхватывается с середины маршрута, неизвестная локация = старт с origin.

### WS + MCDU
- `sec.activate` — ЖИВОЙ (заглушка снята); новые `exec.get`/`exec.stop`; `exec_state` бродкастится на каждом изменении (прыжок/сход/возврат/финиш). Контракт §7 дополнен payload'ом.
- SEC L5: `EXEC · NEXT <система>` + `<STATUS n/m` (нажатие = stop); RTE LIST — ▶-маркер текущей позиции; флэши SEC ACTIVATED / OFF ROUTE / ROUTE COMPLETE. Замечание 20 в спеке.

### tools/mock_flight.py — «полёт» без игры
- Дописывает настоящие FSDJump/FuelScoop-события в мок-журнал; сервер (реальное ядро + реальный EDJournal) сам двигает исполнителя. Опция `--deviate` — сход с плана посреди маршрута.
- **Живые прогоны:** FUEL-SAFE Devataru→Maia — 7/7 легов, COMPLETE; FAST (нейтронка Jackson's Lighthouse) 5/5 с девиацией: OFF ROUTE пойман, возврат, COMPLETE. Топливо план==журнал на каждом леге (до 0.01 т).
- Попутный фикс ядра: EDJournal терпит пустые строки в журнале (рваная запись не стопорит читателя).

### QA
- Новый `tools/qa_route_executor.py` — 25/25 (офлайн, полный жизненный цикл). `qa_route_ws.py` → 14/14: живой activate, продвижение через РЕАЛЬНЫЙ `_status_snapshot_loop` (запускается в тесте с fast-интервалом), OFF ROUTE/COMPLETE/stop; `collect()` научен пропускать периодические снапшоты. qa_route_planner 16/16.

### Остаток 8.1 (⛔игра)
Реальный GalaxyMapDriver (ввод системы в галакарту + Plot Route), живой прогон с планшета, замер «наш плоттер vs игровой» (приёмка).

### Корректировка исполнения: по-вейпоинтная метка вместо посегментного плоттинга ✅ (2026-07-16, `d651128`)
Решение заказчика: игровой прокладчик НЕ использовать вовсе — он не планирует через суперзаряд (×4/×6) и ломал бы FAST-маршруты; вместо «Plot Route» после каждого прыжка драйверу уходит следующая система нашего плана как **target lock** (`GalaxyMapDriver.set_target`, «поставить метку»). Цель всегда в текущей дальности (леги валидированы ShipFSD, вкл. буст). Сегменты остались индикацией (`segment_target`). Rejoin после OFF ROUTE перевыставляет метку; вызовы драйвера вне state-лока (реальный драйвер медленный). Замечание 21 в спеке. QA 29/29 + 14/14 + живой мок-полёт FAST с девиацией (map target == next waypoint на каждом леге, вкл. бустованный после нейтронки). **Игровой остаток 8.1 теперь = драйвер target lock** (существенно проще Plot Route: открыть карту/панель, выбрать систему, залочить; ядро выпиленного `EDGalaxyMap.py` из `f2ae525^` — референс).

### MkII-инцидент: точность констант + паритет со Spansh-сайтом ✅ (2026-07-17, `c5196ba`+cargo-фикс)
Заказчик сравнил лоб-в-лоб: наш FAST 28 прыжков vs 21 у spansh.co.uk (explorer_nx, Devataru→Plaa Thua CJ-F d12-0). Причины из job-JSON сайта: (1) **у SCO MkII собственные константы топливного уравнения** `fuel_power 2.5025, fuel_multiplier 0.011` — наша таблица (из Auto_Neutron) имела 2.9/0.004; max-range сверка это НЕ ловит (максимум почти одинаков, расходится кривая на неполных дистанциях) — отсюда задача самокалибровки по FuelUsed/JumpDist в Фазе 3; (2) опции оптимизатора: `algorithm=optimistic`+`max_time 60`+`refuel_every_scoopable=1` (теперь шлём всегда), `exclude_secondary=0` — только FAST (FUEL-SAFE держит 1: автопилот скупает звезду ПРИЛЁТА). После фикса — 21 прыжок, леги 5671 LY, 1:1 с сайтом. Зонд: `ship_build` (SLEF) API НЕ принимает (400) — сайт считает константы в JS, свои таблицы из контура не убрать. Попутно: **живой груз** из Status.json теперь в параметрах плоттера (`ship_plot_params(loadout, cargo)`, `RoutePlanner._live_cargo()`). Что живое из журнала всегда: инженерка FSD (FSDOptimalMass/MaxFuelPerJump), масса «болтов» (в UnladenMass), MaxJumpRange.

### Паспорт корабля в маршруте + детект смены профиля + загрузчик мок-корабля ✅ (2026-07-17, `f834b2a`)
Требование заказчика: до полёта 100% уверенность в профиле корабля, изменения детектить. (1) `ship_fingerprint()` — sha1-отпечаток всего влияющего на прыжковую физику (корпус/FSD+инженерка/бустер/баки); каждый exact-plotter маршрут несёт `ship`-паспорт (`ship_summary`: имя+отпечаток+дальности). (2) `RouteExecutor`: активация ОТКАЗЫВАЕТ при несовпадении отпечатка с текущим журнальным лоадаутом («SHIP CHANGED SINCE PLOT — REPLOT»); 1 Гц-тик следит за отпечатком В ПОЛЁТЕ → `exec_state.ship_mismatch` (алерт+флэш в MCDU, сбрасывается при возврате лоадаута). (3) `tools/set_mock_ship.py` — профили больше не вшиты: без аргументов инспектирует текущий профиль (паспорт+дальности), с файлом SLEF/Loadout — дозаписывает LoadGame+Loadout в мок-журнал как реальная пересадка (работающий сервер подхватывает живьём). Шапка построенного маршрута в MCDU показывает имя корабля плана. QA: qa_route_executor 36/36 (+8 проверок), 16/16, 14/14. Контракт: `Route.ship`, `exec_state.ship_mismatch`.
