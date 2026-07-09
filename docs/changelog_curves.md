# Changelog — MCDU RPY Curve Editor

## 2026-07-09 (review fixes)

### Fixed
- **Критично: порядок ключей кривой.** JS сериализует целочисленные ключи
  (`"30"`) раньше дробных (`"0.5"`), а интерполяция в `EDShipControl`
  обходит dict в порядке вставки, ожидая возрастание углов. Теперь
  `curve.set` прогоняет данные через `_normalize_curve()`: валидация
  (углы > 0, rate ≥ 0), сортировка по углу, ключи в формате ядра
  (`"45.0"`, а не `"45"`). Пустые/битые данные отклоняются с ошибкой.
- **`_ensure_ship_cfg()` удалён.** Больше никакой подмены
  `current_ship_type` «первым попавшимся» кораблём и синтетического
  `_default`: если ядро ещё не определило корабль — честная ошибка
  `no ship config loaded`.
- **`config.save_ship` больше не «сохраняет» молча в никуда.**
  `ED_AP.update_ship_configs()` теперь возвращает `bool`; сервер отвечает
  `{"type":"ship_saved","ok":true|false}`, а фронт показывает
  `SAVED TO DISK` / `SAVE FAILED` по факту ответа (оптимистичный flash
  убран).
- **`curve.get` не мутирует конфиг** (читает через `.get()`, не создаёт
  пустых ключей).
- **Спам `curve.get`.** Флаг `S.curvePending`: запрос не переотправляется
  на каждый render-тик, ошибка сервера снимает флаг и не зацикливает
  повторы; ответ для «чужой» оси игнорируется.
- **Demo-сервер поддерживает редактор кривых**: у `FakeAP` появились
  `ship_configs`/`current_ship_cfg`/`speed_demand` с правдоподобными
  кривыми, `set_throttle_*` переключает `speed_demand`,
  `update_ship_configs()` логирует и возвращает `True`.
- Мёртвая проверка `isNaN` в `setSelectedValue` (теперь `parseFloat`
  напрямую).

### Added
- **Добавление точки**: двойной клик по свободному месту графика
  (`editor.addPoint(x, y)`).
- **Удаление точки**: R5 `DEL PT>` (`editor.deleteSelected()`, последняя
  точка не удаляется). L5 переименован в `<SAVE TO DISK`.

## 2026-07-09

### Added
- **`webserver/static/mcdu_curves.js`** — SVG-редактор кривых RPY в стиле MCDU.
  - Zero dependencies, classic IIFE, `window.McduCurves`.
  - API: `McduCurves.mount(container, points, {onChange, title, xLabel, yLabel})`.
  - Drag мышью и touch, selection с пульсирующим кольцом, автосортировка по X.
  - `getPoints()` / `setPoints(points)` / `setSelectedValue(y)` / `selectIndex(i)` / `destroy()`.
- **PERF page** в `mcdu.js` — страница редактора кривых на функциональной клавише PERF.
  - L1: переключение оси ROLL → PITCH → YAW (и со скретчпада: `ROLL`/`PITCH`/`YAW`).
  - R1: throttle 0/50/100% (общий с INIT).
  - L3/R3: выбор предыдущей/следующей точки.
  - L4: ввод значения Y для выбранной точки со скретчпада.
  - R4: сохранить кривую в память сервера.
  - L5: SAVE ALL SETTINGS → `ship_configs.json` на диск.
  - ← → (slew): перебор точек.
  - Drag автосохраняет в память при отпускании (`curve.set`).
  - Защита от перезаписи: `curveNeedsLoad` флаг — данные не откатываются при `status_snapshot`.
- **`curve.get` / `curve.set`** WebSocket-команды в `server.py`.
  - `curve.get {axis}` → текущая кривая для `speed_demand`.
  - `curve.set {axis, data}` → запись в `current_ship_cfg`.
  - `config.save_ship` → `ed_ap.update_ship_configs()` на диск.
  - `_ensure_ship_cfg()` — ленивая инициализация: journal → `ship_configs.json` → synthetic `_default`.
- **`<div id="curvePanel">`** в `index.html` — панель графика под прибором MCDU.
- **`.curve-panel`** стили в `mcdu.css` — тёмный CRT-экран с точечной матрицей.

### Files changed
| File | Change |
|---|---|
| `webserver/static/mcdu_curves.js` | **new** |
| `webserver/static/index.html` | +`<script src="mcdu_curves.js">`, +`<div id="curvePanel">` |
| `webserver/static/mcdu.css` | +`.curve-panel` / `.curve-panel-screen` / `.curve-view` |
| `webserver/static/mcdu.js` | +PERF page, +`curve*` actions, +`S.curve*` state |
| `webserver/server.py` | +`curve.get`, +`curve.set`, +`config.save_ship`, +`_ensure_ship_cfg` |
