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

**Правило делегирования (обновлено 2026-07-07, по прямому указанию пользователя): ВСЁ идёт через субагентов, модель им выставляю Я САМ по тегам ниже. Пользователя про модель НЕ спрашивать и НЕ просить жать `/model` — это трата времени.**
Причина: модель основной сессии переключается только командой `/model` (доступна пользователю, не мне), а субагенту я могу назначить любую модель. Поэтому маршрут любой задачи — субагент с выставленной моделью.
- **Механические / переносы кода / GUI-чистка / локали** → 🔵 Sonnet-субагент (или 🐤 Haiku для тривиального).
- **Архитектура с трейд-оффами** (Фаза 3 FuelState, Фаза 4 Watchdog/state-machine, Фаза 6 focus-loss) → 🟣 Opus-субагент.
- **Контекстно-тяжёлые задачи (декомпозиция Фазы 2, где сервисы согласуются между собой) ТОЖЕ идут в субагента** — просто даю ему точный скоуп (список методов/сигнатур конструктора) И указываю на файлы контекста `.claude/planning/plans/*.md` + `.claude/planning/memory/*.md`, чтобы холодный старт был дешёвым. НЕ делать inline на текущей модели.
- После каждого кодового субагента → **read-only QA-субагент** (PASS/FAIL-отчёт, код не трогает, не коммитит) → затем Я коммичу+пушу из основной сессии.

Обозначения в задачах (историческое [DELEGATE]/[INLINE] больше не про «делать самому» — теперь ВСЁ делегируется):
- **[DELEGATE]** — самодостаточно, субагенту хватает списка файлов/строк.
- **[INLINE]** — раньше значило «в основной сессии»; теперь = «субагенту нужен общий контекст декомпозиции» → даю ему скоуп + указатель на `.claude/planning/`. Всё равно субагент, не основная сессия.

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

- [x] 🔵 [INLINE] `ED_AP.py` дефолтный конфиг: периферийные ключи удалены ещё в 1.2; перепроверено grep'ом — 0 совпадений Robigo/AFKCombat/TCE/GalMap/Waypoint. `EDMesg*Port` **сохранены** (EDMesg остаётся — их присутствие в этом списке было ошибкой плана). `ELWAdvisorEnabled` **не добавлен** — перенесён в Фазу 2.6 вместе с тумблером/сервисом, иначе ключ повиснет полу-подключённым. *(2026-07-07, коммита не потребовалось)*
- [x] 🐤 [DELEGATE→Sonnet] Вычищены `locales/{de,en,es,fr,ru}.json`: 104 ключа × 5 файлов = 520 удалений (Auto-FSS/AFSS вкл. `AFSS_BUSY`, TCE, `WPT_*`, Robigo, AFK, DSS Assist, GalMap, `INT_PNL_*`, `STN_SVCS`/`COMMODITIES`, Colonization). Все `ELW_*`/`FSS_HONK_*`/`NAV_PNL_*`/honk сохранены. QA-субагент (read-only) подтвердил: JSON валиден, 5×252 ключа идентичны, 174 ключа из кода все есть в en.json (0 висячих ссылок). Коммит `725bf6b`. *(2026-07-07)*

### Контроль конца Фазы 1 (ГОТОВО, 2026-07-07)
- [x] ⚠️ **Дозачистка Auto-FSS (была в плане 1.1, но без чекбокса в TODO — чуть не потерялась):** блок Auto-FSS (~660 строк) всё ещё оставался в `ED_AP.py` (1145–1822) + поля `_afss_*` в `__init__`, плюс GUI-хвосты (`test_auto_fss_click`/`auto_fss_scan_one_click`) и ключ `GalMap_SystemSelectDelay` в `EDAPGui.py`. Удалены целиком, ELW-советник (`fss_detect_elw`/`test_fss_scan`) не тронут. Коммит `a1b9931`.
- [x] 🔵 [INLINE] `python -c "import EDAPGui"` без ошибок.
- [x] 🔵 [INLINE] Запуск GUI (mock-env): окно открывается, стабильно 12с, без traceback (только baseline-WARNING про отсутствие окна ED + загрузка OCR). Вкладки = Main/Settings/Game/Debug-Test/Calibration — TCE/Colonization/Waypoints удалены. Тумблер ELW перенесён в 2.6.
- [x] 🛠️ **Побочно (разблокировало GUI-верификацию):** `tools/setup_mock_env.ps1` писал mock-файлы с UTF-8 BOM под Windows PowerShell 5.1 → `expat`/`json.loads` их отвергали, GUI падал на старте под 5.1. Переведён на BOM-независимую запись (`UTF8Encoding($false)`). Коммит `86e046c`.

**Открытый вопрос из прошлой сессии закрыт:** пользователь подтвердил — «GUI не работает / ошибка mouse input» больше НЕ воспроизводится (причина осталась неустановленной; при рецидиве — снять точный текст ошибки).

**Новые правила работы (в память):** (1) для не-дефолтной модели сам поднимаю субагента нужной модели, не прошу пользователя жать `/model` — [[feedback-delegate-model-via-subagent]]; (2) после каждого кодового субагента — read-only QA-субагент с PASS/FAIL-отчётом до коммита — [[feedback-qa-subagent-before-commit]].

---

## ФАЗА 2 — Декомпозиция `ED_AP.py` на сервисы (Этап 1.3, 1.7)

> 🖥️ **Держать в голове «MCDU-контракт» (см. [[web-ui-direction]]):** Фаза 7 сделает MCDU-фронтенд витриной этих сервисов. Значит сервисы Фаз 2-4 должны уметь отдавать **структурированные данные для страниц**, а не только скаляры для тумблеров: `navigation_service`+`NavRouteParser` → маршрут как список систем С флагами заправляемости (для ROUTE-страницы и сценария «SCOOP SEARCH»); `FuelState` (Фаза 3) → структура-прогноз (для FUEL-страницы). На этом этапе (чистый рефактор) поведение не меняем, но проектируя границы/сигнатуры сервисов — закладывать возможность такого чтения (напр. метод, возвращающий список-с-флагами, а не только «следующая цель»). Не строить сам веб сейчас — только не закрывать себе дорогу к нему.

> Порядок строгий, по одному сервису, `python -c "import EDAPGui"` + короткий FSD-прогон в игре после каждого. Все переносы — **чистый рефактор без изменения логики**.
> **Все [INLINE] на 🔵 Sonnet** (перенос по готовому списку методов), КРОМЕ решений о границах сервиса — там где неочевидно, поднять на 🟣. Причина не-делегирования в субагента: сервисы должны быть согласованы по сигнатурам конструкторов между собой (общий паттерн внедрения зависимостей `scr_reg/keys/status/jn/ap_ckb`), а субагент каждого сервиса не видит остальные.

- [x] 🔵 **2.1 `JsonConfigIO.py`** — вынос функций был сделан ещё в 1.2; здесь осталось удалить осиротевший `EDAPColonizeEditor.py` (git rm; `docs/ColonizationEditor.md` уже не было). QA: import ED_AP/EDAPGui чист, 0 ссылок на ColonizeEditor, round-trip чтения/записи JSON работает, GUI стартует. Коммит `9af93a5`. *(2026-07-07, Sonnet-субагент + QA-субагент)*
- [x] 🔵 **2.2 `services/fuel_service.py`** — `refuel_new` перенесён в класс `FuelService`; мёртвый `refuel` удалён (0 вызовов). QA: **паритет поведения IDENTICAL** (тело после `self.ap.`→`self.` совпало с оригиналом байт-в-байт), import чист, GUI стартует. Коммит `adcb09a`. *(2026-07-07, Sonnet-субагент + QA-субагент)*

> **🔑 DI-ШАБЛОН СЕРВИСОВ (принят в 2.2, применять в 2.3–2.6):** сервис — класс с единственным состоянием `self.ap = ed_ap`; всё остальное (`jn/config/status/vce/ship_control/keys/ap_ckb/set_throttle_*/sun_avoid/overheat_escape/interdiction_check/fss_detect_elw/locale_safe/…`) дёргается как `self.ap.<member>`. Инстанс создаётся в `ED_AP.__init__` рядом с `self.ship_control` (`self.<svc> = XService(self)`). Перенос метода = механическое `self.`→`self.ap.` в теле (у сервиса нет своих полей), сигнатуры и логика байт-в-байт. Вызовы из ED_AP делегируются в `self.<svc>.<method>`. Так поздние фазы могут мигрировать всё ещё-на-ED_AP callee'и без правки уже вынесенных сервисов. QA каждого сервиса обязан проверять нормализованный паритет тела метода.
>
> **⚡ QA-ГЕЙТ ОПТИМИЗИРОВАН (2026-07-07, по просьбе снизить токены):** QA больше НЕ отдельный субагент (жгли 45–75k токенов). Оркестратор запускает инлайн переиспользуемый скрипт `tools/qa_service_extraction.py --service-file … --service-module … --names a,b,c`: импорты (вкл. standalone сервиса), роутинг-инварианты (методы удалены из ED_AP; нет `self.<name>(` в ED_AP; нет `self.ap.<name>(` в сервисе; нет module-top `import ED_AP`), паритет каждого метода против `HEAD:ED_AP.py`. Плюс: проверить, что отложенно-импортируемые из `ED_AP` имена реально определены (import их не ловит — импорт внутри метода), и GUI-smoke = запуск на mock-env + `grep Traceback` (исполняет `EDAutopilot.__init__`, проверяет проводку `self.<svc>=…`). Коммит только при all-PASS. См. [[feedback-qa-subagent-before-commit]].
>
> **Кросс-сервисные вызовы (уточнено в 2.3):** сервис зовёт метод другого сервиса как `self.ap.<other_service>.<method>` (напр. `fuel_service` → `self.ap.nav_service.sun_avoid(...)`); ED_AP зовёт `self.<service>.<method>`; внешние файлы (`EDShipControl`/`EDAPGui`) — через инстанс ED_AP: `self.ap.nav_service.X` / `self.ed_ap.nav_service.X`. Wrapper'ов на ED_AP НЕ оставляем. Инвариант корректности роутинга статически греп-проверяем: в ED_AP не должно остаться `self.<moved>(`/`ed_ap.<moved>(`, в сервисе — `self.ap.<sibling_moved>(`.
>
> **Циклический импорт (решено в 2.3):** `ED_AP.py` импортирует классы сервисов на верхнем уровне, поэтому сервис НЕ импортирует из `ED_AP` на верхнем уровне. Если сервису нужны имена из `ED_AP.py` (типы-аннотации `TargetOffset`/`CompassOffset`/`ScTargetAlignReturn`, утилиты вроде `get_timestamped_filename`): `from __future__ import annotations` (аннотации → ленивые строки) + `if TYPE_CHECKING:`-импорты для типов + **функцио­нальные (отложенные) импорты** для рантайм-имён внутри методов. QA проверяет, что отложенные имена реально существуют в `ED_AP.py` и что на верхнем уровне сервиса нет `import ED_AP`.
- [x] 🔵 **2.3 `services/navigation_service.py`** — 10 методов вынесены (`get_nav_offset`, `get_target_offset`, `get_compass_target_offset`, `compass_align`, `sc_target_align`, `mnvr_to_target`, `sun_avoid`, `overheat_escape`, `is_sun_dead_ahead`, `interdiction_check`). Кросс-файловые вызыватели перевязаны (ED_AP 22+2, EDShipControl 9, EDAPGui 1, fuel_service 7). Циклический импорт разрулен (см. заметку ниже). QA: паритет всех 10, инварианты роутинга, standalone-импорт, GUI. Коммит `9ce4d53`. *(2026-07-07, Sonnet + QA)*
- [x] 🔵 **2.4 `services/jump_service.py`** — `honk`, `position`, `jump`, `fsd_assist` вынесены в `JumpService`. Осторожно с `honk` (метод, intra, вкл. thread-target `target=self.honk`) vs `honk_thread` (атрибут ED_AP). Отложенный импорт `FSDAssistReturn` + `strfdelta` из `ED_AP` (оба рантайм). Внешних вызывателей 2 (`self.fsd_assist`→`self.jump_service.fsd_assist`). QA: паритет 4/4 IDENTICAL, роутинг-инварианты, отложенные имена существуют, GUI. Коммит `937d3a3`. *(2026-07-07, Sonnet + инлайн-QA)*
- [x] 🔵 **2.5 `services/docking_service.py`** — 8 методов в `DockingService`: `sc_disengage`, `undock`, `request_docking`, `dock`, `undock_seq` (переименование уже было в 1.2), `sc_engage`, `supercruise_to_station` (добавлен — тот же SC/докинг-кластер), `sc_assist`. `request_docking` перегружен — `EDNavigationPanel.request_docking` НЕ тронут. `StationType` из `EDJournal` (модульный импорт, без цикла), `ScTargetAlignReturn` отложенно. Кросс-перевязки: nav→`self.ap.docking_service.sc_engage`, jump→`…undock_seq`, engine_loop→`…sc_assist`. QA: паритет 8/8 IDENTICAL, инварианты, GUI. Коммит `73b9f50`. *(2026-07-07, Sonnet + инлайн-QA)*
- [x] 🔵 **2.6a `services/elw_advisor.py`** (чистый вынос) — 6 методов (`_body_is_valuable`@staticmethod, `_announce_body`, `poll_body_scans`, `edsm_check_system`, `fss_detect_elw`, `test_fss_scan`) + `@property fss_screen` + `_fss_screen` + `EDFSS` привязаны к `ElwAdvisor`. `fss_detected` оставлен на ED_AP (пишется сервисом через `self.ap.`, читается overlay). Отложенный `get_timestamped_filename`. `EDFSS.py`/`EDAPCalibration`/`Screen_Regions` не тронуты. QA: паритет 6/6 IDENTICAL, инварианты, GUI. Коммит `5001df9`. *(2026-07-07, Sonnet + инлайн-QA)*

### 1.7 / 2.6b — ELW-советник опциональный → РЕШЕНО: НЕ ТРЕБУЕТСЯ (2026-07-07, решение пользователя)
- [x] Предпосылка плана устарела. После декомпозиции: советник **уже опционален** — `fss_detect_elw` (активный FSS-скан) гейтится существующим `ElwScannerEnable` (default False; чекбокс "ELW Scanner" уже есть в Settings + `set_fss_scan()`); `edsm_check_system` — `EDSMCheckEnable` (default True). Безусловен только `poll_body_scans` (пассивные голос/лог-объявления о ценных телах). Пользователь выбрал **не добавлять** третий тумблер `ELWAdvisorEnabled`/чекбокс (дубль рядом с "ELW Scanner" + смена дефолта). `poll_body_scans` оставлен пассивным/безусловным. **Отложенные из Фазы 1 пункты — 1.4 чекбокс "ELW/AW Advisor" и 1.5 ключ `ELWAdvisorEnabled` — закрыты как НЕ НУЖНЫЕ.**

### Контроль конца Фазы 2 — ✅ ФАЗА 2 ЗАВЕРШЕНА (2026-07-07)
- [x] Локально: `import EDAPGui` чист, GUI стартует на mock-env без traceback после каждого выноса (2.1–2.6a). `ED_AP.py` теперь оркестратор; вся лётная логика в `services/` (`fuel_service`/`navigation_service`/`jump_service`/`docking_service`/`elw_advisor`) + `JsonConfigIO`. Каждый вынос — паритет тела метода IDENTICAL против HEAD, коммит на шаг.
- [ ] 🎮 **In-game (на машине с ED, здесь недоступно):** полный прогон FSD Route Assist + докинг/ундок + заправка на реальном маршруте; регрессию (если всплывёт) привязывать к конкретному сервису по коммиту. ELW тумблер ("ELW Scanner") вкл/выкл — поведение как раньше.

---

## ➡️ ПОРЯДОК ФАЗ ПЕРЕСМОТРЕН (2026-07-07): ФАЗА 7 ПЕРЕД 3–4

**Решение пользователя.** После Фаз 1–2 следующей делается **Фаза 7 (веб-MCDU + headless)**, Фазы 3–4 откладываются до доступа к игре. Почему:
- **3–4 нельзя делать вслепую.** FuelState (3) и Watchdog/state-machine (4) проектируются и тюнятся по *реальным* потокам и отказам (живые `Fuel.FuelMain`/`FuelReservoir`, рассогласования источников, перегрев, провалы выравнивания, safe-state). На статичных заглушках dev-ноута (ED тут не стоит) пороги/правило голосования не на чем откалибровать. Непроверенный код надёжности опаснее его отсутствия.
- **Фаза 7 на ~80–90% делается без игры** (UI MCDU, HTTP/WebSocket, headless-вход, публикация из `ap_ckb`, роутинг команд, инвентаризация контракта `EDAPGui`); игра нужна только для финального end-to-end. Фазы 1–2 уже дали headless-ядро → 7 разблокирована.
- **7 раз-ослепляет 3–4:** веб-телеметрия = обсервабилити на планшете во время реального полёта; плюс ранний под-шаг **7.0 capture-харнесс** пишет сырые `Status.json`/журнал/`NavRoute` в реплей → 3–4 потом делаются на ноуте по реальным данным.

Фазы 3–6 остаются как есть (улучшение ядра), но **gated на игру**; порядок среди них — позже.

---

## ФАЗА 3 — Топливо: sensor fusion + route budget (Этап 2.A) 🟣 ОПUS

> ⛔ **GATED НА ИГРУ (2026-07-07):** делать ПОСЛЕ Фазы 7 и только при доступе к ED — иначе вслепую (см. «ПОРЯДОК ФАЗ ПЕРЕСМОТРЕН» выше). Идеально — на реальных/captured данных (7.0).
>
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

> **Решение 2026-07-06:** tkinter GUI (`EDAPGui.py`) **полностью заменяется** веб-интерфейсом. Автопилот → headless-сервис на игровом ПК; интерфейс → веб-страница на планшете/браузере рядом с клавиатурой (реальный MCDU-терминал, тема «авионика»). Делается ПОСЛЕ Фаз 1-2 (нужно headless-ядро). См. [[web-ui-direction]].
>
> **➡️ ЭТО СЛЕДУЮЩАЯ ФАЗА (2026-07-07):** идёт сразу после Фазы 2, ПЕРЕД 3–4 — её можно вести без игры на dev-ноуте (см. «ПОРЯДОК ФАЗ ПЕРЕСМОТРЕН» выше).

### 7.0 — Capture-харнесс (ранний под-шаг; питает и веб-реплей, и будущие Фазы 3–4)
- [x] 🔵 **СДЕЛАНО (2026-07-07, коммит `cb2ef30`)** — `tools/capture_telemetry.py` (standalone, без ED_AP/OCR/tkinter, WindowsKnownPaths-пути, дедуп/ротация/partial-safe, `--interval/--duration/--out-dir/--journal-events`, вывод `captures/*.jsonl` `{ts,source,data}`; `captures/` в .gitignore). Проверено на mock-env. **Пользователю:** запусти в игровую сессию для сбора реальных данных под Фазы 3–4. Изначальный скоуп: тонкий рекордер: во время реального полёта на игровом ПК писать в реплей-лог (напр. `captures/*.jsonl`) с таймстампами — снимки `Status.json` (вкл. `Fuel.FuelMain`/`FuelReservoir`, `Flags*`/`Flags2`), события журнала (fuel/scoop/FSD/docking/interdiction), `NavRoute.json`. Дёшево, не мешает автопилоту. Результат: реалистичные данные, на которых FuelState (3) и Watchdog (4) разрабатываются/тюнятся на dev-ноуте, а не на пустых заглушках; и основа оффлайн-реплея веб-телеметрии. Собрать данные можно уже в ближайшую игровую сессию, до старта самого веба.

### 7.1 — Опора на существующее (не строить с нуля)
- [x] 🟣 **РЕВИЗИЯ EDMesg СДЕЛАНА (2026-07-07).** Вердикт: (1) **транспорт** — EDMesg это **ZeroMQ** (`import zmq`, PUSH/PULL+PUB/SUB), браузер по нему говорить не может → **не годится как транспорт веб-MCDU**; HTTP+WebSocket (сделан в 7.2) обязателен независимо. (2) **`ap_ckb`→событийный поток формализован в 7.2** (`Broadcaster`). (3) **⚠️ НАХОДКА — EDMesg частично сломан после Фазы 1:** `EDAP_EDMesg_Server.py` дёргает удалённые `self.ap.waypoint`/`system_map`/`galaxy_map`/`tce_integration` (waypoint/карты/TCE-действия → `AttributeError` при вызове). Не падает только т.к. `EnableEDMesg=False` по умолчанию (сервер не стартует). Живые действия: `GetEDAPLocation`, `StopAllAssists` (через `ap_ckb`), `Launch`. **Решение:** EDMesg — отдельный дремлющий канал (сторонние интеграции), НЕ сливать с вебом, не вкладываться сейчас. Латентную поломку — зафиксировать как долг: опционально «ужать EDMesg до живых действий» отдельным шагом или в 7.4. См. [[web-ui-direction]].
- [x] 🔵 **СДЕЛАНО (2026-07-07)** → `docs/web_api_contract.md`. Инвентаризация всех точек `EDAPGui.py` ↔ ядро: ~19 чекбоксов + 27 полей (config-ключи+дефолты), 20 команд/кнопок, lifecycle (единый долгоживущий engine-loop-поток + флаги; stop = `ctype_async_raise`-инъекция), 11 `ap_ckb`-тегов (часть мёртвая), push-vs-poll состояния, и предложенный event/command/config-split для веб-API. **Ключевые выводы:** (1) структурной телеметрии в push нет — `get_status_lines()` богат, но pull-only и отдаёт строки → для веба нужен `status_snapshot`-event со структурой из `engine_loop`; (2) конфиг лучше отдавать generically (get/set по ключу), а не по-полю; (3) 8 tkinter-специфичных мест (калибровка рисует на игровом оверлее, CV-view, RPY-редактор, мини-панель, restart/exit) — переосмыслить для планшета; (4) `EDMesgServer` остаётся отдельным каналом.

### 7.2 — Headless-сервер ✅ ВЕРТИКАЛЬНЫЙ СРЕЗ ГОТОВ (2026-07-07, коммит `e59a59c`, стек aiohttp)
- [x] 🟣 Тонкий слой aiohttp (`webserver/server.py`): HTTP (статика) + WebSocket. `Broadcaster` мостит `ap_ckb` (worker-поток → asyncio через `call_soon_threadsafe`) в broadcast по WS; маппинг тегов→JSON-события; `status_snapshot` каждую 1с; диспатч команд (assist start/stop/stop_all, throttle, config.get); отдача статики.
- [x] 🟣 Точка входа `edap_headless.py`: `EDAutopilot(cb=Broadcaster)` без tkinter (do_thread=True), запуск сервера, чистый shutdown, `--host/--port/--duration`. + `ED_AP.get_status_dict()` — структурная телеметрия (read-only). **QA:** 13/13 веб-проверок in-process (aiohttp TestClient + fake-ядро, VPN-независимо, без OCR): статика, WS hello+snapshot, core→UI push, UI→core команды, config.get, битая команда→error. **Реальный core+сервер end-to-end — на игровом ПК** (тяжёлый OCR/connectivity под VPN тут не гоняю). Заглушка `webserver/static/index.html` — временная, заменится в 7.3.

### 7.3 — MCDU веб-фронтенд (ПОЛНЫЙ workflow, не декоративный)
> Модель взаимодействия как в реальном MCDU (см. [[web-ui-direction]]): **твёрдые кнопки = страницы-режимы** (`ROUTE`/`FUEL`/`SHIP`/`PROG`/`NAV` — выбирают ЧТО показать), **LSK (6/сторону) = контекстные действия над строкой напротив** (смысл меняется со страницей), **скретчпад = буфер** (напечатал значение → «забросил» в поле по LSK).
>
> **🎨 ДИЗАЙН-РЕФЕРЕНС ЕСТЬ (2026-07-07):** `design/web-mockup/` (коммиты `c7ed165`/`5ab078a`, отдельная сессия дизайна) — интерактивный `.dc`-прототип MCDU в стиле Airbus A320 (`EDAutopilot.dc.html`+`support.js`, скриншоты в `uploads/`) + `PLAN-MCDU.md` (план вертикального прибор-корпуса). Палитра: фон `#0a0a0a`, янтарь `#E8973E`, статусы `#5f96d6`; шрифты IBM Plex Mono (хром) + VT323 (ЭЛТ). ЭТО ВИЗУАЛЬНЫЙ ТАРГЕТ, но `.dc`+support.js в Python НЕ встроен → 7.3 = собрать **self-contained production-фронтенд** по этому дизайну, подключённый к WS-контракту `webserver/`, заменив заглушку `webserver/static/index.html`. NB: MCDU-модель взаимодействия (страницы/LSK/скретчпад) из плана богаче, чем текущий макет — свести оба при реализации.
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

**Модель для задач (обновлено 2026-07-07):** НЕ переключать `/model` в основной сессии и НЕ спрашивать пользователя. Каждая задача — субагент с моделью по метке: 🔵 → Sonnet-субагент, 🟣 → Opus-субагент, 🐤 → Haiku-субагент. Контекстно-тяжёлые (бывшие [INLINE]) — тоже субагент, со скоупом + указателем на `.claude/planning/`. После кодового субагента — QA-субагент до коммита. См. [[feedback-delegate-model-via-subagent]], [[feedback-qa-subagent-before-commit]].
