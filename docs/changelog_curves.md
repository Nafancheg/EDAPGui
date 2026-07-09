# Changelog — MCDU RPY Curve Editor

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
