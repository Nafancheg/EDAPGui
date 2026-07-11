# Паритет-аудит: tkinter GUI (`EDAPGui.py`) → веб-MCDU (для задачи 7.4)

> Дата: 2026-07-11, ветка `cleanup-decompose-avionics`. Read-only разведка Explore-агентом,
> сверено с актуальным кодом. Компаньон: `docs/web_api_contract.md` (инвентаризация 7.1).
> Легенда: ✅ покрыто вебом · 🟡 частично/с оговоркой · ❌ не покрыто · 🗑 GUI-специфично (умрёт без потери).

**Ключевой факт:** движок (`engine_loop`, `KThread`) и `ap_ckb`-мост уже headless —
`edap_headless.py` строит ядро без tkinter, GUI никогда не крутил AP-логику. Пробелы — в
Calibration, Game-вкладке, глобальных хоткеях и части Debug/Test.

## Вкладка MAIN

| Элемент GUI | Что делает | Покрытие |
|---|---|---|
| FSD Route Assist | `set_fsd_assist` | ✅ `assist.start/stop {fsd}`; PROG·CRUISE L1 |
| Supercruise Assist | `set_sc_assist` | ✅ `assist.start/stop {sc}`; PROG·APPROACH L1 |
| Fast Travel Mode | `config['FastTravelMode']` | ✅ CRU OPT L1 |
| Mini Panel | always-on-top Toplevel | 🗑 веб-MCDU и есть «мини-панель» |
| SunPitchUp+Time (SHIP, spinbox) | `ed_ap.sunpitchuptime` (per-ship) | ❌ нет ни в snapshot, ни в config/curve API |
| Enable Auto-tune RPY | `config['AutoTuneRPYRates']` | ❌ нет тумблера в вебе |
| 0/50/100% Throttle | `set_throttle_0/50/100` | ✅ `throttle.set`; PROG L3–L5, TUNING R1 |
| Align to Target | `nav_service.compass_align(scrReg)` | 🟡 веб-`align_target` зовёт `sc_target_align` — **другой метод**; для RPY-тюнинга нужен именно `compass_align` |
| Edit Roll/Pitch/Yaw Curve | `RPYLineEditor` (tk-плот) | ✅ `curve.get/set` + редактор SETTINGS→RPY TUNING |
| LOG-окно | `ap_ckb('log')` | ✅ MESSAGE LOG |
| Statusline + Jump count | `ap_ckb('statusline'/'jumpcount')` | ✅ header + лог + `status_snapshot` |

## Верхние кнопки

| Элемент | Метод | Покрытие |
|---|---|---|
| Load All Settings | `load_ship_configs()` | 🟡 веб-`config.load` зовёт `load_config()` (только AP.json); **перезагрузка ship-конфигов не покрыта** |
| Save All Settings | `update_config` + `update_ship_configs` + `save_ocr_calibration_data` | 🟡 первые два = `config.save`/`config.save_ship`; **`save_ocr_calibration_data` вебом не вызывается нигде** |
| Online HELP | webbrowser | 🗑 |

## Вкладка SETTINGS

Чекбоксы: ✅ Randomness (OPTIONS L4), AutomaticLogout (L5), Overlay (L2, живой сеттер),
ActivateEliteEachKey (CONFIG L1), Voice (L1, живой), ELW (CRU OPT L2).

| Пробелы | Ключ | Покрытие |
|---|---|---|
| Enable Hotkeys | `HotkeysEnable` + `setup_hotkeys()` | 🟡 тумблер есть (OPTIONS L3), но регистрацию хоткеев делает только GUI → **бессмыслен в headless** (см. «Хоткеи») |
| D-Scanner Button radio | `DSSButton` | ❌ |
| Language combobox | `config['Language']` + `locale.change_language()` | ❌ в вебе полностью отсутствует; generic `config.set` не дёргает `change_language` |
| SunBright/NavAlign/Jump/Docking/WaitAutodock | числа AP | ❌ (доступны через generic `config.set`, нет виджетов) |
| Scoop Timeout, Fuel Abort | `FuelScoopTimeOut`, `FuelThreasholdAbortAP` | ❌ |
| Overlay X/Y/FontSize | `OverlayText*` | ❌ + `set_overlay` их всё равно не применяет вживую (TODO в ядре) |
| Строки хоткеев | `HotKey_StartFSD/StartSC/StopAllAssists` | ❌ |
| Refuel Threshold | `RefuelThreshold` | ✅ FUEL PRED R5 |
| Key_ModDelay/DefHoldTime/RepeatDelay | тайминги | ✅ MAINT R1–R3 |

> `config.set` пропускает любой ключ, уже существующий в `ed_ap.config`, и зовёт
> `process_config_settings()` — все «❌» выше **дешёвые**: не хватает только веб-виджетов.

## Вкладка GAME

| Элемент | Метод | Покрытие |
|---|---|---|
| Bindings tree | `keys.keys_to_obtain` и др. | ❌ |
| Reload bindings | `keys.reload_bindings()` | ❌ (CFG L2 — заглушка, WS-команды нет) |
| Auto-assign missing keys | `keys.assign_missing_keyboard_binds()` | ❌ (нужен confirm-flow) |
| 10 таймингов AP Waits (`Wait_*`, `PlanetDepartureSCOTime`, `FCDepartureTime`) | `config[...]` | ❌ (generic `config.set` доступен) |
| Current game settings + Refresh | `EDGraphicsSettings()`/`EDPlayerSettings()`/`get_game_language()` | ❌ — полезная диагностика (borderless, brightness, язык) отсутствует |

## Вкладка DEBUG/TEST

✅ Debug Overlay/OCR/Images (MAINT L2–L4). 🟡 CV View (тумблер есть; x/y от tk-окна умрут — откроется в (0,0)).
❌ Debug-mode radio (вербозность LogDEBUG/INFO — в headless только CLI `--log-level`).
🟡 FSS-тест: веб-`fss_scan` зовёт `fss_detect_elw`, а кнопка GUI — `test_fss_scan` (диагностический прогон с вердиктом) — не покрыт.
🗑 Restart/Exit/Open Log/Updates/Changelog/Discord/About.

## Вкладка CALIBRATION (`EDAPCalibration.py`)

| Элемент | Покрытие |
|---|---|
| Редактор OCR-rect'ов (combobox + 4 spinbox) | ❌ полностью |
| Save All Calibrations (`save_ocr_calibration_data` → `configs/ocr_calibration.json`) | ❌ веб не зовёт нигде |
| Reset to Default | ❌ |
| Calibrate Target (`ed_ap.calibrate_target()`) | ❌ WS-команды нет |

**Механика headless-совместима**: и `calibrate_target`, и превью rect'ов рисуют на
**игровом оверлее** (ED-окно), не на tk-виджете. Но точка входа — только tkinter-вкладка.
Нужен WS-контракт (`calibration.get/set/save`, `calibration.calibrate_target`); превью на
планшете не видно без стрима скриншота → часть работ требует игры.

## Глобальные хоткеи — принципиальный вопрос

`keyboard.add_hotkey`/`setup_hotkeys` живут **только в `EDAPGui.py`** (grep: единственный
файл). В `edap_headless.py`/`webserver/` регистрации нет. При удалении tkinter хоткеи
Start FSD / Start SC / Stop All **никто не обслуживает**; тумблер HOTKEYS пишет флаг без
эффекта. Решение заказчика: перенести `keyboard`-листенер в headless-процесс ИЛИ признать
хоткеи умершими с GUI (веб-кнопки + guarded STOP ALL уже есть).

## Прочее

🗑 мёртвое: `MousePoint` (не используется), `up/down/left/right` пип-nudge (хоткеи
закомментированы, недостижимо), GUI-мьютекс чекбоксов FSD/SC.
🟡 `ship_changed`: веб лишь пишет «SHIP CHANGED» в лог; перечитывание SunPitchUp/ship-полей
в UI не сделано (связано с ❌ SunPitchUp).

---

# Вердикт

**(а) Покрыто — удаляется из tkinter смело:** ассисты, Stop All, Fast Travel, throttle-пресеты,
RPY-кривые, тумблеры Voice/Overlay/Randomness/AutoLogout/ActElite/ELW/Debug×3, тайминги
эмуляции, RefuelThreshold, лог, statusline, телеметрия, маршрут.

**(б) Закрывается на ноуте (без игры) — только веб-виджеты поверх готовых механизмов:**
поля Overlay X/Y/FontSize; числа AP (SunBright/NavAlign/Jump/Docking/WaitAutodock);
Scoop Timeout; Fuel Abort; 10 Game-таймингов; строки хоткеев; DSSButton; Auto-tune RPY;
вербозность логов; подключить `save_ocr_calibration_data` к веб-Save и `load_ship_configs`
к веб-Load.

**(в) Требует игры/решения заказчика:** Calibration целиком; Game-вкладка (bindings,
game settings); `test_fss_scan`; `compass_align` для тюнинга; **глобальные хоткеи**
(перенос листенера в headless — решение); смена `Language`/OCR-локали.

**(г) Умирает с tkinter без потери:** Mini Panel, CV-View-привязка к окну, Restart/Exit,
Open Log, Updates/Changelog/Discord/About/HELP, `GUI_*`-локализация виджетов, мёртвый код.

**Итог: tkinter удалять РАНО.** Сначала закрыть (б) на ноуте, принять решения по (в) —
минимум по хоткеям и калибровке, — затем проверка на игровом ПК и только потом 7.4.
