# Route Planner Backend (Фаза 8.1, ноутбучная часть) — дизайн

Дата: 2026-07-13. Статус: утверждён к реализации.
Витрина (страницы/слоты): `design/mcdu-button-map.md` §3.4 (SEC F-PLN), §3.5 (DIR).
Модель маршрутов: три плана F-PLN / SEC F-PLN / DIR (решение заказчика 2026-07-10).

## 1. Скоуп

**Делаем на ноуте (без игры):** сервис прокладки маршрутов поверх публичных API
Spansh + EDSM; профили FUEL-SAFE ⇄ FAST/RISKY; кандидаты DIRECT-TO; WS-команды
под уже построенные каркасы SEC F-PLN / DIR. Фронт (mcdu.js) НЕ трогаем — подключение
витрины отдельной итерацией позже.

**Gated на игру (НЕ в этом скоупе):** ввод проложенного маршрута в игру (драйв
галакарты / пошаговый выбор цели), т.е. фактический `ACTIVATE SEC` и исполнение DIR.
Команда `sec.activate` остаётся заглушкой с внятным сообщением.

## 2. Проверенные API (живые прогоны 2026-07-13 с этого ноута)

### 2.1 Spansh neutron plotter — профиль FAST/RISKY

```
POST https://spansh.co.uk/api/route
  form: efficiency=60&range=<LY>&from=<sys>&to=<sys>
  → {"job":"<uuid>","status":"queued"}
GET https://spansh.co.uk/api/results/<job>
  → пока в работе: {"status":"queued","state":"started",...}
  → готово: {"result":{"destination_system","source_system","distance",
       "system_jumps":[{"system","x","y","z","distance_jumped",
                        "distance_left","jumps","neutron_star","id64"},...]}}
```

- `system_jumps` — это WAYPOINT'ы (точки перепрокладки у нейтронок), НЕ каждый прыжок;
  `jumps` в записи = число прыжков от предыдущего waypoint'а. Итого прыжков = Σ jumps.
- Топливо не моделируется → scoopable-гарантий нет.
- Джоба на длинном маршруте (Sol→Colonia) сидит в очереди десятки секунд — поллинг
  с интервалом 3 с и общим таймаутом ≥300 с.

### 2.2 Spansh galaxy plotter — профиль FUEL-SAFE

```
POST https://spansh.co.uk/api/generic/route
  form: source, destination, is_supercharged=0, use_supercharge=0,
        use_injections=0, exclude_secondary=1,
        fuel_power, fuel_multiplier, optimal_mass, supercharge_multiplier,
        base_mass, tank_size, internal_tank_size, max_fuel_per_jump,
        range_boost, cargo
  → {"job","status"} ; GET /api/results/<job>
  → {"result":{"jumps":[{"name","x","y","z","distance",
       "distance_to_destination","fuel_in_tank","fuel_used",
       "is_scoopable","must_refuel","has_neutron","must_inject","id64"},...]}}
```

- Здесь `jumps` — КАЖДЫЙ прыжок, с расходом топлива и `must_refuel` на scoopable-звёздах.
- Параметры корабля — из сырого журнального `Loadout` (см. §3):
  `fuel_power` = size-константа FSD, `fuel_multiplier` = class-константа/1000,
  `optimal_mass`/`max_fuel_per_jump` — база из таблицы FSD с override из
  `Engineering.Modifiers` (`FSDOptimalMass`, `MaxFuelPerJump`),
  `base_mass` = UnladenMass + FuelCapacity.Reserve, `tank_size` = FuelCapacity.Main,
  `internal_tank_size` = FuelCapacity.Reserve, `range_boost` = guardian booster (таблица),
  `cargo` = 0 (v1).
- Таблицы констант FSD (size/class/max_fuel/optimal_mass, вкл. SCO-приводы и
  guardian-бустеры) — фактические данные игры; референс-реализация:
  Auto_Neutron (`auto_neutron/fsd.py`, `ship.py`, GPL) — таблицы перенести как данные,
  код писать свой.

### 2.3 EDSM — DIRECT-TO кандидаты и валидация систем

```
GET https://www.edsm.net/api-v1/sphere-systems
    ?systemName=<sys>&radius=<LY≤100>&showPrimaryStar=1&showCoordinates=1
  → [{"name","distance","coords":{x,y,z},
      "primaryStar":{"type","isScoopable"}|{}},...]   (включая саму систему, distance=0)
GET https://www.edsm.net/api-v1/system
    ?systemName=<sys>&showCoordinates=1&showPrimaryStar=1
  → {"name","coords",...} | [] если не существует
```

- `primaryStar.type` — строка вида `"M (Red dwarf) Star"`; scoopable-фильтр — по
  `isScoopable` (bool), НЕ по нашему KGBFOAM-сету.
- Браузерный `www.edsm.net/en/api-v1` отдаёт 403 ботам, но сами API-эндпоинты открыты.
- ⚠️ Cloudflare EDSM режет дефолтный UA `python-requests` (403) — сессии клиентов
  обязаны слать идентифицирующий User-Agent (`ED_Autopilot-RoutePlanner/1.0`);
  найдено live-дымом 2026-07-13.

## 3. Изменения ядра (EDJournal.py)

В обработку события `Loadout` добавить (аддитивно, существующие ключи не трогать):

- `self.ship['loadout_raw'] = log` — сырой dict события (нужен FSD-модели для §2.2);
- `self.ship['max_jump_range'] = log.get('MaxJumpRange')` — максимальная дальность
  прыжка (поле есть в журнале, сейчас не читается) — это `range` для neutron-плоттера.

Оба ключа инициализировать `None` в шаблоне `self.ship` (рядом с `location`).

## 4. Новый модуль `RoutePlanner.py` (корень репо; прецедент — CalibrationStore.py)

Зависимости: stdlib + `requests` (уже в requirements). Никаких импортов ED_AP на
верхнем уровне (`TYPE_CHECKING` при надобности). Всё блокирующее — вызывается
из webserver через `run_in_executor` (прецедент: `calibration.calibrate_target`).

```python
class PlotError(Exception): ...   # человекочитаемое сообщение → {"type":"error"}

# --- данные ---
FSD_BASE: dict[str, tuple]        # item-id → (size, class, max_fuel, optimal_mass[, sc_mult])
FSD_SIZE_CONST, FSD_CLASS_CONST, SCO_CLASS_CONST: dict
GUARDIAN_BOOSTER_RANGE: dict[str, float]

def ship_plot_params(loadout: dict) -> dict   # → форм-параметры §2.2; PlotError если нет FSD

class SpanshClient:               # session: requests.Session, инжектируемая (для offline-QA)
    def plot_fast(self, source, dest, range_ly, efficiency=60) -> dict     # → Route
    def plot_fuel_safe(self, source, dest, ship_params) -> dict            # → Route
    # внутри: _submit(url, form) → job; _poll(job, interval=3, timeout=300) → result

class EDSMClient:
    def sphere_systems(self, system, radius) -> list[dict]
    def system(self, name) -> dict | None      # None = не существует

class RoutePlanner:
    def __init__(self, ed_ap): self.ap = ed_ap; self._lock; self._busy;
                               self._secondary = None; self._dir = None; self._error = None
    def plot_secondary(self, dest: str | None, profile: str) -> None   # блокирующий
    def nearest(self, scoopable: bool) -> None                         # блокирующий
    def direct_to(self, name: str) -> bool                             # False = INVALID
    def snapshot(self) -> dict     # JSON-safe копия состояния (под broadcast)
```

**Route (нормализованный, одинаковый для обоих профилей):**

```json
{"profile": "FUEL-SAFE"|"FAST", "source": "...", "destination": "...",
 "jumps": N, "dist_ly": N.N, "scoops": N|null, "risk": "LOW"|"HIGH",
 "plotted_at": "<iso>",
 "systems": [{"system": "...", "dist_ly": N.N|null, "scoopable": bool|null,
              "neutron": bool, "must_refuel": bool}, ...]}
```

- FUEL-SAFE: `jumps` = len-1, `scoops` = Σ must_refuel, `risk` = "LOW".
- FAST: `jumps` = Σ jumps waypoint'ов, `scoops` = null (не моделируется),
  `risk` = "HIGH" (честно: топливо не гарантировано). `systems` = waypoint'ы.
- `systems[0]` — стартовая система (dist_ly null), формат совместим по духу с
  `map_nav_route` (webserver/server.py:41).

**Правила поведения:**

- Источник прокладки: `ed_ap.jn.ship_state()['location']`; нет локации → PlotError.
- `plot_secondary(dest=None, ...)`: dest по умолчанию = destination текущего
  secondary, иначе destination активного F-PLN (`ed_ap.nav_route`), иначе PlotError.
- FAST: `range_ly` = `ship_state()['max_jump_range']`; нет → посчитать из
  `loadout_raw` (формула дальности через FSD-модель); нет и его → PlotError.
- FUEL-SAFE: `ship_plot_params(ship_state()['loadout_raw'])`; нет loadout → PlotError.
- `nearest(scoopable)`: sphere-radius каскад 15→30→50 LY вокруг текущей системы,
  исключить `distance == 0`, при `scoopable=True` фильтр `primaryStar.isScoopable`,
  кандидат = минимальная дистанция → `self._dir = {"system","star_class","dist_ly","scoopable"}`.
- `direct_to(name)`: EDSM `system()`; не существует → False (фронт покажет INVALID);
  существует → кандидат с дистанцией от текущей системы (2-й запрос за координатами).
- `_busy`: пока идёт прокладка, повторный `plot_secondary` → PlotError "PLOT IN PROGRESS".
- Состояние в памяти процесса; персист secondary на диск — вне скоупа v1.

## 5. WS-команды (webserver/server.py, стиль — существующий elif-диспатч)

| Команда | Параметры | Ответ/поведение |
|---|---|---|
| `sec.plot` | `profile: "fuel_safe"\|"fast"`, `dest?: str` | ack `{"type":"sec_plot_started"}` → executor → broadcast `{"type":"sec_route","data":snapshot}` (ошибка — внутри snapshot.error) |
| `sec.get` | — | `{"type":"sec_route","data":snapshot + compare}` |
| `sec.activate` | — | `{"type":"error","text":"NOT AVAILABLE — требует ввода маршрута в игру (игровая часть 8.1)"}` |
| `dir.nearest` | `scoopable: bool` | ack `{"type":"dir_started"}` → executor → broadcast `{"type":"dir_state","data":snapshot}` |
| `dir.set` | `system: str` | executor → broadcast `dir_state`; несуществующая система → `{"type":"error","text":"INVALID"}` |

**COMPARE (в `sec.get`)** собирает сервер: primary-статистика из
`map_nav_route(ed_ap.nav_route.get_nav_route_data())` (jumps = len-1, dist = Σ dist_ly,
scoops = счёт scoopable), secondary — из snapshot. Планнер primary НЕ считает
(не дублировать map_nav_route).

Инстанс планнера — ленивый синглтон в server.py (прецедент `_get_calib_store()`).

## 6. Итерации и QA

1. **Итерация 1 (🟣):** `RoutePlanner.py` + правка `EDJournal.py` (§3) +
   `tools/qa_route_planner.py`. QA офлайн: фейковая session (канированные ответы §2)
   — нормализация обоих профилей, ship_plot_params с/без инженерии, nearest-каскад,
   direct_to invalid, busy-guard, PlotError-пути; `python -c "import RoutePlanner"`;
   `import EDAPGui` не сломан. Опция `--live` — дымовой прогон по реальным API
   (короткий маршрут), не входит в обязательный гейт.
2. **Итерация 2 (🔵):** WS-команды §5 + аддендум в `docs/web_api_contract.md`.
   QA: aiohttp TestClient поверх fake-ядра с подменённым планнером (без сети),
   все 5 команд + broadcast-путь.
3. **Позже (фронт, отдельно):** подключение SEC F-PLN / DIR страниц к командам —
   когда вернёмся к веб-морде.
4. **Gated на игру:** `sec.activate` по-настоящему (драйв галакарты), исполнение DIR.
