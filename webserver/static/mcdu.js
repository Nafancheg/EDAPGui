/* ED Autopilot MCDU client. Single classic script, no dependencies. */
(function () {
  'use strict';

  var $ = function (id) { return document.getElementById(id); };

  // ---- element refs ----
  var core = $('core');
  var scrTitle = $('scrTitle');
  var scrInd = $('scrInd');
  var subL = $('subL');
  var subR = $('subR');
  var scratchEl = $('scratch');
  var spInput = $('spInput');
  var logView = $('logView');
  var connDot = $('connDot');
  var connLabel = $('connLabel');
  var curvePanel = $('curvePanel');
  var curveView = $('curveView');
  var ledProg = $('ledProg');
  var ledFuel = $('ledFuel');

  var rows = [].slice.call(document.querySelectorAll('.core .row')).map(function (el) {
    return {
      el: el,
      lhead: el.querySelector('.lhead'),
      rhead: el.querySelector('.rhead'),
      lval: el.querySelector('.lval'),
      rval: el.querySelector('.rval')
    };
  });

  // ---- state ----
  var S = {
    page: 'PROG',
    phase: null,             // viewed PROG phase; null = follow the active one
    snap: {},
    cfg: {},
    route: { active: false, destination: null, systems: [] },
    scratch: '',
    throttle: null,          // last level we sent (server does not report it)
    assist: { fsd: false, sc: false },
    fastTravel: false,
    connected: false,
    routePage: 0,           // top line index of the F-PLN scroll window
    cfgPage: 0,              // CONFIG sub-page index 0-4, parity-gap ext. (7.4б)
    sysInfoIdx: null,        // route system index open on the SYSINFO sub-page
    statusline: '',
    routeLoc: null,          // location last used to refresh the route
    flash: null,             // transient scratchpad message
    flashSaved: '',
    logStick: true,
    curveAxis: 'RollRate',   // 'RollRate' | 'PitchRate' | 'YawRate'
    curveEditor: null,       // McduCurves instance
    curveSpeed: null,        // speed demand last received with curve data
    curveNeedsLoad: false,   // true when we should load curve data from server
    curvePending: false,     // a curve.get is in flight — don't re-send on render ticks
    secConfirm: false,       // SEC F-PLN L3 <ACTIVATE SEC two-step confirm armed?
    sec: null,                // last sec_route payload: {secondary, dir, busy, error, compare}
    secDest: '',              // local SEC DEST [E] input (SEC R1)
    secFrom: '',              // local SEC FROM [E] override (SEC L4); empty = journal location
    secBusy: false,           // true between sec_plot_started and the next sec_route
    exec: null,               // last exec_state payload (activated-route executor)
    secListPage: 0,           // SECLIST scroll: top line index of the SECLIST_WIN window
    dir: null,                // last DirCandidate from dir_state (DIR page)
    dirPending: null,         // dir.set entry awaiting async validation (consumed on dir_state)
    lndCoords: null,         // LND R5 accepted target 'lat/lon'; guidance itself is Phase 8.2
    calib: null,             // OCR calibration snapshot from the server (7.4в), key -> {rect,text,readonly}
    calibPage: 0,            // CALIB list scroll: top line index of the CALIB_WIN window
    calibKey: null,          // key open on the CALIBREG drill-in sub-page
    calibResetConfirm: false,// CALIB R5 RESET ALL> two-step confirm armed?
    calibTargetConfirm: false,// CALIB R6 CAL TARGET> two-step confirm armed?
    calibRunning: false      // true between calib_target_started and calib_target_done
  };

  // actions[side][idx] = { press:fn, input:fn } or null. Rebuilt every render.
  var actions = { L: [null, null, null, null, null, null], R: [null, null, null, null, null, null] };

  // PROG phase model (spec §3.1). Order is the NEXT PHASE> cycle.
  var PHASES = ['DEPART', 'CLIMB', 'CRUISE', 'APPROACH', 'ARRIVAL', 'LND'];
  // display labels (phase ids stay stable for logic); CLIMB shows as BOOST —
  // the accelerate-out-to-supercruise leg, not an aviation "climb"
  var PHASE_LABEL = { CLIMB: 'BOOST' };
  function phaseLabel(ph) { return PHASE_LABEL[ph] || ph; }

  // Which phase is really active, from telemetry. Heuristic v1 (no game yet):
  // docked/undocking -> DEPART, docking flow -> ARRIVAL, fsd assist -> CRUISE,
  // sc assist -> APPROACH, plain supercruise -> CRUISE, normal space -> CLIMB.
  function detectActivePhase() {
    var st = String(S.snap.ship_status || '');
    var mode = S.snap.ap_mode;
    if (st === 'in_station' || st === 'starting_undocking' || st === 'in_undocking') return 'DEPART';
    if (st === 'dockinggranted' || st === 'dockingdenied' || st === 'starting_docking' || st === 'in_docking') return 'ARRIVAL';
    if (mode === 'fsd') return 'CRUISE';
    if (mode === 'sc') return 'APPROACH';
    if (st === 'in_supercruise') return 'CRUISE';
    if (st === 'in_space') return 'CLIMB';
    return 'CRUISE';
  }
  function viewedPhase() { return S.phase || detectActivePhase(); }

  // ---- WebSocket ----
  var ws = null;
  var reconnectT = null;
  var secConfirmT = null;   // SEC F-PLN ACTIVATE SEC confirm-window timeout id
  var calibResetConfirmT = null;   // CALIB RESET ALL confirm-window timeout id
  var calibTargetConfirmT = null;  // CALIB CAL TARGET confirm-window timeout id

  function wsURL() {
    return (location.protocol === 'https:' ? 'wss:' : 'ws:') + '//' + location.host + '/ws';
  }

  function connect() {
    ws = new WebSocket(wsURL());
    ws.onopen = function () {
      S.connected = true;
      sendRaw({ cmd: 'config.get' });
      if (S.page === 'ROUTE') { S.routeLoc = S.snap.location || null; sendRaw({ cmd: 'route.get' }); }
      render();
    };
    ws.onclose = function () {
      S.connected = false;
      render();
      if (reconnectT) clearTimeout(reconnectT);
      reconnectT = setTimeout(connect, 2000);
    };
    ws.onerror = function (e) { console.error('WS error', e); };
    ws.onmessage = function (m) {
      var msg;
      try { msg = JSON.parse(m.data); } catch (e) { return; }
      handle(msg);
    };
  }

  function sendRaw(obj) {
    if (!ws || ws.readyState !== 1) return false;
    ws.send(JSON.stringify(obj));
    return true;
  }

  // require a live connection before sending a state-changing command
  function ensureConn() {
    if (!S.connected) { flash('NOT CONNECTED', 1500); return false; }
    return true;
  }

  // ---- inbound messages ----
  function handle(msg) {
    switch (msg.type) {
      case 'hello':
        break;
      case 'status_snapshot':
        S.snap = msg.data || {};
        if (S.page === 'ROUTE' && S.snap.location !== S.routeLoc) {
          S.routeLoc = S.snap.location;
          sendRaw({ cmd: 'route.get' });
        }
        render();
        break;
      case 'log':
        appendLog(msg.text || '', !!msg.voice, false);
        break;
      case 'statusline':
        S.statusline = msg.text || '';
        renderSub();
        break;
      case 'jumpcount':
        appendLog('[jumps] ' + (msg.text || ''), false, false);
        break;
      case 'assist':
        if (msg.mode === 'fsd' || msg.mode === 'sc') S.assist[msg.mode] = !!msg.running;
        render();
        break;
      case 'ship_changed':
        appendLog('SHIP CHANGED', false, false);
        break;
      case 'config':
        S.cfg = msg.data || {};
        S.fastTravel = !!S.cfg.FastTravelMode;
        render();
        break;
      case 'route':
        S.route = msg.data || { active: false, systems: [] };
        if (!S.route.systems) S.route.systems = [];
        clampRoutePage();
        render();
        break;
      case 'error':
        if (S.curvePending) {
          // most likely our curve.get failed (e.g. ship not detected yet):
          // stop re-requesting every render tick; re-entering TUNING retries
          S.curvePending = false;
          S.curveNeedsLoad = false;
        }
        if (S.page === 'DIR' && msg.text === 'INVALID') flash('INVALID', 1500);
        S.dirPending = null;   // rejected/failed dir.set: leave the entry for correction
        appendLog('[error] ' + (msg.text || ''), false, true);
        break;
      case 'sec_plot_started':
        S.secBusy = true;
        flash('PLOTTING…', 1500);
        if (S.page === 'SEC') render();
        break;
      case 'sec_route':
        S.sec = msg.data || null;
        S.secBusy = false;
        if (S.sec && S.sec.error) {
          appendLog('[sec] ' + S.sec.error, false, true);
          flash(shortenMsg(S.sec.error), 1800);
        }
        render();
        break;
      case 'dir_started':
        flash('SEARCHING…', 1500);
        break;
      case 'exec_state': {
        var prevStatus = S.exec && S.exec.status;
        S.exec = msg.data || null;
        var st = S.exec && S.exec.status;
        if (st && st !== prevStatus) {
          if (st === 'ACTIVE' && prevStatus !== 'OFF ROUTE') flash('SEC ACTIVATED', 1800);
          else if (st === 'OFF ROUTE') flash('OFF ROUTE', 1800);
          else if (st === 'COMPLETE') flash('ROUTE COMPLETE', 2500);
        }
        if (S.page === 'SEC' || S.page === 'SECLIST' || S.page === 'PROG') render();
        break;
      }
      case 'dir_state':
        S.dir = (msg.data && msg.data.dir) || null;
        // a confirming dir_state consumes the scratch entry that produced it
        // (MCDU convention: a successful LSK entry is eaten by the field)
        if (S.dirPending && S.scratch === S.dirPending) {
          S.scratch = '';
          renderScratch();
        }
        S.dirPending = null;
        if (S.page === 'DIR') render();
        break;
      case 'event':
        appendLog('[' + (msg.tag || 'event') + '] ' + bodyToStr(msg.body), false, false);
        break;
      case 'curve':
        S.curvePending = false;
        if (msg.axis && msg.axis !== S.curveAxis) break; // stale reply for a previous axis
        S.curveSpeed = msg.speed || null;
        if (S.curveNeedsLoad && S.curveEditor) {
          S.curveEditor.setPoints(msg.data || {});
          S.curveNeedsLoad = false;
        } else if (!S.curveEditor && S.page === 'TUNING') {
          S.curveNeedsLoad = true;  // will be consumed when editor is built
          renderTUNING();
        }
        break;
      case 'curve_saved':
        flash('CURVE UPDATED', 1500);
        break;
      case 'ship_saved':
        flash(msg.ok ? 'SAVED TO DISK' : 'SAVE FAILED', 1800);
        if (!msg.ok && msg.text) appendLog('[config] ' + msg.text, false, true);
        break;
      case 'config_saved':
        flash(msg.ok ? 'SETTINGS SAVED' : 'SAVE FAILED', 1800);
        break;
      case 'config_loaded':
        flash('SETTINGS LOADED', 1800);
        break;
      case 'calibration':
        S.calib = msg.data || {};
        clampCalibPage();
        render();
        break;
      case 'calib_preview':
        flash('ON GAME SCREEN', 1500);
        break;
      case 'calib_saved':
        flash('CALIB SAVED', 1800);
        break;
      case 'calib_reset':
        flash('CALIB RESET', 1800);
        break;
      case 'calib_target_started':
        S.calibRunning = true;
        flash('CAL TARGET RUNNING', 1800);
        render();
        break;
      case 'calib_target_done':
        S.calibRunning = false;
        flash(msg.ok ? 'CAL TARGET DONE' : 'CAL TARGET FAILED', 1800);
        render();
        break;
      default:
        break;
    }
  }

  // shorten a long backend error/status string for a transient flash() cell
  // (the scratchpad row is ~22 chars); the full text still goes to the log.
  function shortenMsg(text) {
    var t = String(text || '');
    return t.length > 20 ? t.slice(0, 19) + '…' : t;
  }

  function bodyToStr(b) {
    if (b === null || b === undefined) return '';
    if (typeof b === 'object') { try { return JSON.stringify(b); } catch (e) { return String(b); } }
    return String(b);
  }

  // ---- log ----
  function timeNow() {
    return new Date().toTimeString().slice(0, 8);
  }

  function appendLog(text, voice, isErr) {
    var line = document.createElement('div');
    line.className = 'log-line';

    var t = document.createElement('span');
    t.className = 'lt';
    t.textContent = timeNow() + ' ';
    line.appendChild(t);

    if (voice) {
      var v = document.createElement('span');
      v.className = 'lvc';
      v.textContent = '♪ ';
      line.appendChild(v);
    }

    var lvl = isErr ? 'l-alert' : (/warn|error/i.test(text) ? 'l-warn' : 'l-normal');
    var x = document.createElement('span');
    x.className = 'lx ' + lvl;
    x.textContent = text;
    line.appendChild(x);

    logView.appendChild(line);
    while (logView.childElementCount > 400) logView.removeChild(logView.firstChild);

    if (S.logStick) logView.scrollTop = logView.scrollHeight;
  }

  logView.addEventListener('scroll', function () {
    S.logStick = (logView.scrollTop + logView.clientHeight >= logView.scrollHeight - 6);
  });

  // ---- scratchpad ----
  function flash(msg, dur) {
    if (!S.flash) S.flashSaved = S.scratch;
    S.flash = msg;
    renderScratch();
    if (flash._t) clearTimeout(flash._t);
    flash._t = setTimeout(function () {
      S.flash = null;
      S.scratch = S.flashSaved;
      renderScratch();
    }, dur);
  }

  function clearFlashNow() {
    if (flash._t) clearTimeout(flash._t);
    S.flash = null;
    S.scratch = S.flashSaved;
    renderScratch();
  }

  function appendChar(ch) {
    if (S.flash) clearFlashNow();
    if (S.scratch.length >= 22) return;
    S.scratch += ch;
    renderScratch();
  }

  function clr() {
    if (S.flash) { clearFlashNow(); return; }
    if (S.scratch) S.scratch = S.scratch.slice(0, -1);
    renderScratch();
  }

  // long CLR: holding Backspace >=600 ms clears the whole scratchpad
  var clrHoldT = null;
  function clrHoldStart() {
    if (clrHoldT) clearTimeout(clrHoldT);
    clrHoldT = setTimeout(function () {
      if (S.flash) clearFlashNow();
      S.scratch = '';
      if (spInput.value) spInput.value = '';
      renderScratch();
    }, 600);
  }
  function clrHoldEnd() {
    if (clrHoldT) { clearTimeout(clrHoldT); clrHoldT = null; }
  }

  function renderScratch() {
    if (S.flash) {
      spInput.value = S.flash;
      spInput.readOnly = true;
      scratchEl.className = 'scratchpad scol flash';
    } else {
      if (spInput.value !== S.scratch) spInput.value = S.scratch;
      spInput.readOnly = false;
      scratchEl.className = 'scratchpad scol';
    }
  }

  // Non-Latin keyboard layout (e.g. Cyrillic): map by PHYSICAL key position,
  // so typing without switching layout still yields the MCDU Latin charset.
  function physicalLatin(e) {
    if (e.ctrlKey || e.altKey || e.metaKey) return null;
    var m = /^Key([A-Z])$/.exec(e.code || '');
    if (m && e.key && e.key.length === 1 && !/[a-zA-Z0-9]/.test(e.key)) return m[1];
    return null;
  }

  // direct typing / clipboard paste into the scratchpad input
  spInput.addEventListener('input', function () {
    if (S.flash) { renderScratch(); return; }
    // charset covers ED system names too: apostrophe (Barnard's Star) and
    // asterisk (Sagittarius A*) are legal DIR / SEC DEST input
    var v = spInput.value.toUpperCase().replace(/[^A-Z0-9 ./+'*-]/g, '').slice(0, 22);
    if (spInput.value !== v) spInput.value = v;
    S.scratch = v;
  });
  spInput.addEventListener('keydown', function (e) {
    if (e.key === 'Backspace' && !e.repeat) clrHoldStart();
    if (e.key === 'Escape') {
      if (S.flash) clearFlashNow();
      S.scratch = '';
      renderScratch();
    } else if (e.key === 'Enter') {
      e.preventDefault();
    } else {
      var L = physicalLatin(e);
      if (L !== null) {
        e.preventDefault();
        if (!S.flash && S.scratch.length < 22) { S.scratch += L; renderScratch(); }
      }
    }
  });
  spInput.addEventListener('keyup', function (e) {
    if (e.key === 'Backspace') clrHoldEnd();
  });

  // ---- LSK dispatch ----
  function doLSK(side, i) {
    var a = actions[side][i];
    if (S.scratch !== '') {
      if (a && a.input) {
        var res = a.input(S.scratch);
        if (res === true) { S.scratch = ''; renderScratch(); render(); }
        else if (res === 'keep') { /* accepted, keep scratch */ }
        else { flash('INVALID', 1500); }   // handler rejected the entry format
      } else {
        flash('NOT ALLOWED', 1500);        // this LSK takes no scratchpad entry
      }
    } else if (a && a.press) {
      a.press();
    }
  }

  // ---- commands / actions ----
  function isOn(mode) { return S.assist[mode] || S.snap.ap_mode === mode; }

  function fsdToggle() {
    if (!ensureConn()) return;
    if (isOn('fsd')) { if (sendRaw({ cmd: 'assist.stop', mode: 'fsd' })) S.assist.fsd = false; }
    else { if (sendRaw({ cmd: 'assist.start', mode: 'fsd' })) S.assist.fsd = true; }
    render();
  }
  function scToggle() {
    if (!ensureConn()) return;
    if (isOn('sc')) { if (sendRaw({ cmd: 'assist.stop', mode: 'sc' })) S.assist.sc = false; }
    else { if (sendRaw({ cmd: 'assist.start', mode: 'sc' })) S.assist.sc = true; }
    render();
  }
  function ftToggle() {
    if (!ensureConn()) return;
    var nv = !S.fastTravel;
    if (sendRaw({ cmd: 'config.set', key: 'FastTravelMode', value: nv })) S.fastTravel = nv;
    render();
  }

  function sendAction(name) {
    if (!ensureConn()) return;
    sendRaw({ cmd: 'action.request', action: name });
  }
  function elwToggle() {
    if (!ensureConn()) return;
    var nv = !S.cfg.ElwScannerEnable;
    if (sendRaw({ cmd: 'config.set', key: 'ElwScannerEnable', value: nv })) S.cfg.ElwScannerEnable = nv;
    render();
  }

  // MCDU MENU · SETTINGS toggles, spec §3.9. Each writes straight through
  // config.set — the backend already applies the effect live.
  function voiceToggle() {
    if (!ensureConn()) return;
    var nv = !S.cfg.VoiceEnable;
    if (sendRaw({ cmd: 'config.set', key: 'VoiceEnable', value: nv })) S.cfg.VoiceEnable = nv;
    render();
  }
  function overlayToggle() {
    if (!ensureConn()) return;
    var nv = !S.cfg.OverlayTextEnable;
    if (sendRaw({ cmd: 'config.set', key: 'OverlayTextEnable', value: nv })) S.cfg.OverlayTextEnable = nv;
    render();
  }
  function hotkeysToggle() {
    if (!ensureConn()) return;
    var nv = !S.cfg.HotkeysEnable;
    if (sendRaw({ cmd: 'config.set', key: 'HotkeysEnable', value: nv })) S.cfg.HotkeysEnable = nv;
    render();
  }
  function randomnessToggle() {
    if (!ensureConn()) return;
    var nv = !S.cfg.EnableRandomness;
    if (sendRaw({ cmd: 'config.set', key: 'EnableRandomness', value: nv })) S.cfg.EnableRandomness = nv;
    render();
  }
  function autoLogoutToggle() {
    if (!ensureConn()) return;
    var nv = !S.cfg.AutomaticLogout;
    if (sendRaw({ cmd: 'config.set', key: 'AutomaticLogout', value: nv })) S.cfg.AutomaticLogout = nv;
    render();
  }
  function actEliteToggle() {
    if (!ensureConn()) return;
    var nv = !S.cfg.ActivateEliteEachKey;
    if (sendRaw({ cmd: 'config.set', key: 'ActivateEliteEachKey', value: nv })) S.cfg.ActivateEliteEachKey = nv;
    render();
  }
  // Enable_CV_View is an int 0/1 flag on the backend, not a bool — send/store 1/0.
  function cvViewToggle() {
    if (!ensureConn()) return;
    var nv = !S.cfg.Enable_CV_View;
    if (sendRaw({ cmd: 'config.set', key: 'Enable_CV_View', value: nv ? 1 : 0 })) S.cfg.Enable_CV_View = nv ? 1 : 0;
    render();
  }
  function dbgOverlayToggle() {
    if (!ensureConn()) return;
    var nv = !S.cfg.DebugOverlay;
    if (sendRaw({ cmd: 'config.set', key: 'DebugOverlay', value: nv })) S.cfg.DebugOverlay = nv;
    render();
  }
  function dbgOcrToggle() {
    if (!ensureConn()) return;
    var nv = !S.cfg.DebugOCR;
    if (sendRaw({ cmd: 'config.set', key: 'DebugOCR', value: nv })) S.cfg.DebugOCR = nv;
    render();
  }
  function dbgImagesToggle() {
    if (!ensureConn()) return;
    var nv = !S.cfg.DebugImages;
    if (sendRaw({ cmd: 'config.set', key: 'DebugImages', value: nv })) S.cfg.DebugImages = nv;
    render();
  }
  // shared [E] input handler factory for the MAINT float settings (§3.9):
  // accepts a non-negative number, rejects anything else with INVALID.
  function floatCfgInput(key) {
    return function (v) {
      var n = v.trim();
      if (!/^\d*\.?\d+$/.test(n)) return false;
      var val = parseFloat(n);
      if (isNaN(val) || val < 0) return false;
      if (!ensureConn()) return 'keep';
      if (sendRaw({ cmd: 'config.set', key: key, value: val })) {
        S.cfg[key] = val;
        render();
        return true;
      }
      return 'keep';
    };
  }

  // shared [E] input handler factory for integer config settings (CONFIG
  // 2/5-3/5, parity-gap ext. 7.4б): a plain non-negative integer, optionally
  // clamped to [min, max] (max omitted = unbounded), INVALID otherwise.
  function intCfgInput(key, min, max) {
    return function (v) {
      var n = v.trim();
      if (!/^\d+$/.test(n)) return false;
      var val = parseInt(n, 10);
      if (val < min || (max !== undefined && val > max)) return false;
      if (!ensureConn()) return 'keep';
      if (sendRaw({ cmd: 'config.set', key: key, value: val })) {
        S.cfg[key] = val;
        render();
        return true;
      }
      return 'keep';
    };
  }

  // format a CONFIG numeric cell: '---' muted when unset, else fmt(v) cyan.
  // fmt defaults to a plain String() when omitted.
  function cfgNumCell(v, fmt) {
    if (v === null || v === undefined) return { rv: '---', rvs: 's-muted' };
    return { rv: fmt ? fmt(v) : String(v), rvs: 's-cyan' };
  }

  // CONFIG 2/5 toggles/cycles (parity-gap ext. 7.4б).
  function dssButtonToggle() {
    if (!ensureConn()) return;
    var nv = (S.cfg.DSSButton === 'Secondary') ? 'Primary' : 'Secondary';
    if (sendRaw({ cmd: 'config.set', key: 'DSSButton', value: nv })) S.cfg.DSSButton = nv;
    render();
  }
  function autoTuneToggle() {
    if (!ensureConn()) return;
    var nv = !S.cfg.AutoTuneRPYRates;
    if (sendRaw({ cmd: 'config.set', key: 'AutoTuneRPYRates', value: nv })) S.cfg.AutoTuneRPYRates = nv;
    render();
  }
  var CFG_LANGUAGES = ['en', 'de', 'es', 'fr', 'ru'];
  function languageToggle() {
    if (!ensureConn()) return;
    var cur = String(S.cfg.Language || 'en').toLowerCase();
    var nv = CFG_LANGUAGES[(CFG_LANGUAGES.indexOf(cur) + 1) % CFG_LANGUAGES.length];
    if (sendRaw({ cmd: 'config.set', key: 'Language', value: nv })) S.cfg.Language = nv;
    render();
  }
  // ERROR -> INFO -> DEBUG -> ERROR, one config.set per step (the backend
  // normalises the LogDEBUG/LogINFO pair off that single key — see
  // _apply_config_side_effects in webserver/server.py). Predict both flags
  // locally to the level's target state so the label updates immediately
  // instead of waiting for the config broadcast round-trip.
  function logLevelToggle() {
    if (!ensureConn()) return;
    var lvl = S.cfg.LogDEBUG ? 'DEBUG' : (S.cfg.LogINFO ? 'INFO' : 'ERROR');
    var key, val, tgtDebug, tgtInfo;
    if (lvl === 'ERROR') { key = 'LogINFO'; val = true; tgtDebug = false; tgtInfo = true; }
    else if (lvl === 'INFO') { key = 'LogDEBUG'; val = true; tgtDebug = true; tgtInfo = false; }
    else { key = 'LogDEBUG'; val = false; tgtDebug = false; tgtInfo = false; }
    if (sendRaw({ cmd: 'config.set', key: key, value: val })) {
      S.cfg.LogDEBUG = tgtDebug; S.cfg.LogINFO = tgtInfo;
    }
    render();
  }

  function throttlePreset(lvl) {
    if (!ensureConn()) return;
    if (sendRaw({ cmd: 'throttle.set', level: lvl })) S.throttle = lvl;
    render();
  }

  function throttlePress() {
    if (!ensureConn()) return;
    var order = [0, 50, 100];
    var next = (S.throttle === null) ? 0 : order[(order.indexOf(S.throttle) + 1) % 3];
    if (sendRaw({ cmd: 'throttle.set', level: next })) S.throttle = next;
    if (S.page === 'TUNING') S.curveNeedsLoad = true;
    render();
  }
  function throttleInput(v) {
    var n = v.trim();
    if (n !== '0' && n !== '50' && n !== '100') return false;
    if (!ensureConn()) return 'keep';
    var lvl = parseInt(n, 10);
    if (sendRaw({ cmd: 'throttle.set', level: lvl })) { S.throttle = lvl; if (S.page === 'TUNING') S.curveNeedsLoad = true; render(); return true; }
    return 'keep';
  }

  function stopAllPress() {
    if (!ensureConn()) return;
    sendRaw({ cmd: 'assist.stop_all' });
    S.assist.fsd = false; S.assist.sc = false;
    render();
  }

  // ---- render helpers ----
  function fill(i, o) {
    var r = rows[i];
    r.lhead.textContent = o.lh || '';
    r.rhead.textContent = o.rh || '';
    r.lval.textContent = o.lv || '';
    r.rval.textContent = o.rv || '';
    r.lval.className = 'lval' + (o.lvs ? ' ' + o.lvs : '');
    r.rval.className = 'rval' + (o.rvs ? ' ' + o.rvs : '');
    r.el.classList.toggle('row--center', !!o.center);
  }
  function clearRow(i) { fill(i, {}); }
  function clearActions() {
    for (var i = 0; i < 6; i++) { actions.L[i] = null; actions.R[i] = null; }
  }
  function pad2(n) { return n < 10 ? '0' + n : '' + n; }

  function fuelCell(v) {
    if (v === null || v === undefined || v === '') return { t: '---', s: 's-muted' };
    var n = Number(v);
    if (isNaN(n)) return { t: '---', s: 's-muted' };
    var s = n < 10 ? 's-alert' : (n < 25 ? 's-warn' : 's-cyan');
    return { t: n.toFixed(1) + ' %', s: s };
  }

  // ---- pages ----
  function renderPROG() {
    var ph = viewedPhase();
    var active = detectActivePhase();
    var ind = (ph === 'ARRIVAL') ? 'ARRIVAL·STN' : phaseLabel(ph);  // station branch is the default until target-type telemetry exists
    setHeader('PROG', ind, ph !== active);
    clearActions();
    for (var i = 0; i < 6; i++) clearRow(i);
    if (ph === 'CRUISE') renderPhaseCRUISE();
    else if (ph === 'APPROACH') renderPhaseAPPROACH();
    else if (ph === 'DEPART') renderPhaseDEPART();
    else if (ph === 'CLIMB') renderPhaseCLIMB();
    else if (ph === 'ARRIVAL') renderPhaseARRIVAL();
    else renderPhaseLND();
    // Phase nav is bidirectional here (unlike an aircraft's one-way flow):
    // the ARRIVAL->DEPART leg loops and a phase can regress, so PREV/NEXT are
    // symmetric on L6/R6. Deliberate deviation from spec §1.3 (see Замечание 11).
    fill(5, { lv: '<PREV PHASE', lvs: 's-cyan', rv: 'NEXT PHASE>', rvs: 's-cyan' });
    actions.L[5] = { press: prevPhase, input: null };
    actions.R[5] = { press: nextPhase, input: null };
  }

  function stepPhase(delta) {
    var order = PHASES;
    var idx = order.indexOf(viewedPhase());
    S.phase = order[(idx + delta + order.length) % order.length];
    render();
  }
  function nextPhase() { stepPhase(1); }
  function prevPhase() { stepPhase(-1); }

  function renderPhaseDEPART() {
    var snap = S.snap;
    var thr = (S.throttle === null) ? '---' : S.throttle + '%';

    fill(0, {
      lv: '<UNDOCK', lvs: 's-normal',
      rh: 'THROTTLE', rv: thr, rvs: (S.throttle === null) ? 's-muted' : 's-cyan'
    });
    actions.L[0] = { press: function () { sendAction('undock'); }, input: null };
    actions.R[0] = { press: null, input: throttleInput };

    fill(1, {
      rh: 'SHIP', rv: snap.ship_status ? String(snap.ship_status) : '---', rvs: snap.ship_status ? 's-normal' : 's-muted'
    });

    fill(2, {
      lv: '<THR 0', lvs: 's-normal',
      rh: 'TARGET', rv: snap.target ? String(snap.target) : '---', rvs: snap.target ? 's-normal' : 's-muted'
    });
    actions.L[2] = { press: function () { throttlePreset(0); }, input: null };

    fill(3, {
      lv: '<THR 50', lvs: 's-normal',
      rh: 'ROUTE',
      rv: S.route.active ? S.route.destination + ' · ' + (S.route.systems.length - 1) + ' JMP' : '---',
      rvs: S.route.active ? 's-normal' : 's-muted'
    });
    actions.L[3] = { press: function () { throttlePreset(50); }, input: null };

    fill(4, { lv: '<THR 100', lvs: 's-normal' });
    actions.L[4] = { press: function () { throttlePreset(100); }, input: null };
  }

  function renderPhaseCLIMB() {
    var snap = S.snap;
    var thr = (S.throttle === null) ? '---' : S.throttle + '%';

    fill(0, {
      lv: '<ENTER SC', lvs: 's-normal',
      rh: 'THROTTLE', rv: thr, rvs: (S.throttle === null) ? 's-muted' : 's-cyan'
    });
    actions.L[0] = { press: function () { sendAction('enter_sc'); }, input: null };
    actions.R[0] = { press: null, input: throttleInput };

    fill(1, {
      lv: '<ALIGN TGT', lvs: 's-normal',
      rh: 'SHIP', rv: snap.ship_status ? String(snap.ship_status) : '---', rvs: snap.ship_status ? 's-normal' : 's-muted'
    });
    actions.L[1] = { press: function () { sendAction('align_target'); }, input: null };

    fill(2, {
      lv: '<THR 0', lvs: 's-normal',
      rh: 'TARGET', rv: snap.target ? String(snap.target) : '---', rvs: snap.target ? 's-normal' : 's-muted'
    });
    actions.L[2] = { press: function () { throttlePreset(0); }, input: null };

    fill(3, { lv: '<THR 50', lvs: 's-normal' });
    actions.L[3] = { press: function () { throttlePreset(50); }, input: null };

    fill(4, { lv: '<THR 100', lvs: 's-normal' });
    actions.L[4] = { press: function () { throttlePreset(100); }, input: null };
  }

  function renderPhaseARRIVAL() {
    var snap = S.snap;

    fill(0, { lv: '<REQ DOCKING', lvs: 's-normal' });
    actions.L[0] = { press: function () { sendAction('request_docking'); }, input: null };

    fill(1, {
      lv: '<DOCK / LAND', lvs: 's-normal',
      rh: 'SHIP', rv: snap.ship_status ? String(snap.ship_status) : '---', rvs: snap.ship_status ? 's-normal' : 's-muted'
    });
    actions.L[1] = { press: function () { sendAction('dock'); }, input: null };

    fill(2, {
      lv: '<REFUEL·REPAIR', lvs: 's-muted',
      rh: 'TARGET', rv: snap.target ? String(snap.target) : '---', rvs: snap.target ? 's-normal' : 's-muted'
    });
    actions.L[2] = { press: function () { flash('NOT AVAILABLE', 1500); }, input: null };
  }

  function renderPhaseLND() {
    fill(0, { lv: '<DROP TO OC', lvs: 's-muted', rh: 'ALT', rv: '---', rvs: 's-muted' });
    fill(1, { lv: '<GLIDE', lvs: 's-muted', rh: 'POS', rv: '---', rvs: 's-muted' });
    fill(2, { lv: '<SURFACE APPR', lvs: 's-muted', rh: 'HDG · BRG', rv: '---', rvs: 's-muted' });
    fill(3, { lv: '<TGT: POI', lvs: 's-muted', rh: 'DIST TO TGT', rv: '---', rvs: 's-muted' });
    fill(4, { lv: '<FINAL DESCENT', lvs: 's-muted', rh: 'TGT COORDS', rv: S.lndCoords || '----/----', rvs: 's-cyan' });
    for (var i = 0; i < 5; i++) {
      actions.L[i] = { press: function () { flash('NOT AVAILABLE', 1500); }, input: null };
    }
    actions.R[4] = { press: null, input: lndCoordsInput };
  }

  // LND R5: lat/lon entry per spec §3.1 — two decimals separated by '/',
  // sign and fraction optional, lat in [-90,90], lon in [-180,180]. Per the
  // contract a valid entry is ACCEPTED and shown in the TGT COORDS cell (the
  // scratchpad clears); the actual guidance/descent to the point is Phase 8.2.
  function lndCoordsInput(v) {
    var m = /^([+-]?\d+(?:\.\d+)?)\/([+-]?\d+(?:\.\d+)?)$/.exec(v.trim());
    if (!m) return false;
    var lat = parseFloat(m[1]), lon = parseFloat(m[2]);
    if (lat < -90 || lat > 90 || lon < -180 || lon > 180) return false;
    // accepted: recognised coords are shown in the R5 cell (that is the
    // confirmation), scratchpad clears (return true). No flash() here — flash
    // saves and later restores the scratch text, which would fight the clear.
    // The guidance/descent to the point itself arrives in Phase 8.2.
    S.lndCoords = m[1] + '/' + m[2];
    render();
    return true;
  }

  function renderPhaseCRUISE() {
    var snap = S.snap;
    var fsdOn = isOn('fsd');

    var noJumps = (snap.jump_cnt === null || snap.jump_cnt === undefined)
      && (snap.total_jumps === null || snap.total_jumps === undefined);
    var jc = (snap.jump_cnt === null || snap.jump_cnt === undefined) ? '-' : snap.jump_cnt;
    var tj = (snap.total_jumps === null || snap.total_jumps === undefined) ? '-' : snap.total_jumps;
    // scans and modes (FSS/HONK/ELW/FAST TRAVEL) now live on CRU OPT (RAD NAV
    // key); CRUISE keeps only the two in-flight actions FSD ROUTE and SCOOP NOW.
    fill(0, {
      lv: fsdOn ? '<FSD ROUTE ON' : '<FSD ROUTE OFF', lvs: fsdOn ? 's-on' : 's-off',
      rh: 'JUMPS', rv: noJumps ? '---' : jc + '/' + tj, rvs: noJumps ? 's-muted' : 's-normal'
    });
    actions.L[0] = { press: fsdToggle, input: null };

    fill(1, { rh: 'ETA', rv: snap.eta ? String(snap.eta) : '---', rvs: snap.eta ? 's-normal' : 's-muted' });

    fill(2, { rh: 'TARGET', rv: snap.target ? String(snap.target) : '---', rvs: snap.target ? 's-normal' : 's-muted' });

    var hasDist = snap.total_dist_jumped !== null && snap.total_dist_jumped !== undefined;
    var distVal = hasDist
      ? Number(snap.total_dist_jumped).toFixed(1) + ' LY · ' + (snap.jumps_remaining ?? '-') + ' LEFT'
      : '---';
    fill(3, { rh: 'DIST', rv: distVal, rvs: hasDist ? 's-normal' : 's-muted' });

    var f = fuelCell(snap.fuel_percent);
    var scoopSuffix = snap.star_class ? (snap.scoopable ? ' · SCOOP' : ' · ✗') : '';
    fill(4, {
      lv: '<SCOOP NOW', lvs: 's-normal',
      rh: 'FUEL', rv: f.t + scoopSuffix, rvs: f.s
    });
    actions.L[4] = { press: function () { sendAction('scoop'); }, input: null };
  }

  function renderPhaseAPPROACH() {
    var snap = S.snap;
    var scOn = isOn('sc');

    fill(0, {
      lv: scOn ? '<SC ASSIST ON' : '<SC ASSIST OFF', lvs: scOn ? 's-on' : 's-off',
      rh: 'DIST TO DROP', rv: '---', rvs: 's-muted'
    });
    actions.L[0] = { press: scToggle, input: null };

    fill(1, {
      lv: '<ALIGN TGT', lvs: 's-normal',
      rh: 'SHIP', rv: snap.ship_status ? String(snap.ship_status) : '---', rvs: snap.ship_status ? 's-normal' : 's-muted'
    });
    actions.L[1] = { press: function () { sendAction('align_target'); }, input: null };

    fill(2, {
      rh: 'TARGET', rv: snap.target ? String(snap.target) : '---', rvs: snap.target ? 's-normal' : 's-muted'
    });
  }

  function renderINIT() {
    setHeader('INIT', 'PREFLIGHT');
    clearActions();
    for (var i = 0; i < 6; i++) clearRow(i);
    var snap = S.snap;
    var f = fuelCell(snap.fuel_percent);
    fill(0, { lv: '<F-PLN', lvs: 's-normal',
      rh: 'DEST', rv: S.route.active ? String(S.route.destination) : '---',
      rvs: S.route.active ? 's-normal' : 's-muted' });
    actions.L[0] = { press: function () { setPage('ROUTE'); }, input: null };
    fill(1, { lv: '<FUEL PRED', lvs: 's-normal',
      rh: 'JUMPS', rv: S.route.active ? String(S.route.systems.length - 1) : '---',
      rvs: S.route.active ? 's-normal' : 's-muted' });
    actions.L[1] = { press: function () { setPage('FUEL'); }, input: null };
    fill(2, { rh: 'SHIP', rv: snap.ship_status ? String(snap.ship_status) : '---',
      rvs: snap.ship_status ? 's-normal' : 's-muted' });
    fill(3, { lv: '<DATA', lvs: 's-normal', rh: 'FUEL', rv: f.t, rvs: f.s });
    actions.L[3] = { press: function () { setPage('DATA'); }, input: null };
    fill(4, { lv: '<SETTINGS', lvs: 's-normal',
      rh: 'LINK', rv: S.connected ? 'CONNECTED' : 'OFFLINE',
      rvs: S.connected ? 's-on' : 's-alert' });
    actions.L[4] = { press: function () { setPage('SETTINGS'); }, input: null };
    fill(5, { rv: 'PROG>', rvs: 's-cyan' });
    actions.R[5] = { press: function () { setPage('PROG'); }, input: null };
  }

  // DIR · DIRECT-TO, spec §3.5, wired to the Phase 8.1 route-planner backend
  // (§7 of docs/web_api_contract.md): dir.nearest / dir.set commands, dir_state
  // events. star_class comes back as a long descriptive string (e.g. "G
  // (White-Yellow) Star") — dirClassShort() trims it to the leading letter(s)
  // before the first parenthesis for the cramped R3 cell.
  function dirClassShort(cls) {
    if (!cls) return '';
    var s = String(cls);
    var i = s.indexOf('(');
    return (i >= 0 ? s.slice(0, i) : s).trim();
  }

  function renderDIR() {
    setHeader('DIR', 'DIRECT-TO');
    clearActions();
    for (var i = 0; i < 6; i++) clearRow(i);

    fill(0, { lv: '<NEAREST SCOOPABLE', lvs: 's-normal',
      rh: 'DIRECT TO', rv: '________', rvs: 's-cyan' });
    actions.L[0] = { press: function () { if (ensureConn()) sendRaw({ cmd: 'dir.nearest', scoopable: true }); }, input: null };
    actions.R[0] = { press: null, input: dirTargetInput };

    var cand = S.dir;
    fill(1, { lv: '<NEAREST SYSTEM', lvs: 's-normal',
      rh: 'CAND', rv: cand ? String(cand.system) : '---', rvs: cand ? 's-normal' : 's-muted' });
    actions.L[1] = { press: function () { if (ensureConn()) sendRaw({ cmd: 'dir.nearest', scoopable: false }); }, input: null };

    var classVal = '---';
    if (cand) {
      var cls = dirClassShort(cand.star_class) || '?';
      var dist = (cand.dist_ly === null || cand.dist_ly === undefined) ? '--' : Number(cand.dist_ly).toFixed(1);
      classVal = cls + ' · ' + dist + ' LY';
    }
    fill(2, { rv: classVal, rvs: cand ? 's-normal' : 's-muted' });
  }

  // R1 DIRECT TO [E]: fire-and-forget — dir.set is sent immediately, no local
  // echo of the typed value (the candidate card on R2/R3 is the confirmation
  // once dir_state comes back). Validation is async, so 'keep' here; the
  // pending entry is consumed on the confirming dir_state (handle()) while an
  // INVALID reply leaves it in the scratchpad for correction.
  function dirTargetInput(v) {
    var t = v.trim();
    if (!t) return false;
    if (!ensureConn()) return 'keep';
    sendRaw({ cmd: 'dir.set', system: t });
    S.dirPending = t;
    return 'keep';
  }

  // SEC F-PLN · SECONDARY ROUTE, spec §3.4, wired to the Phase 8.1
  // route-planner backend (§7 of docs/web_api_contract.md): sec.plot /
  // sec.get / sec.activate commands, sec_route events. compare.primary comes
  // from the server (built off the active F-PLN); the secondary-side numbers
  // are read straight off S.sec.secondary per the contract.
  function secCompareNum(v) { return (v === null || v === undefined) ? '---' : String(v); }

  // distances: whole LY once >=100 (keeps the cell narrow), one decimal below
  function secDist(v) {
    if (v === null || v === undefined) return '---';
    var n = Number(v);
    if (isNaN(n)) return '---';
    return n >= 100 ? String(Math.round(n)) : n.toFixed(1);
  }

  function renderSEC() {
    setHeader('RTE PLAN', 'ROUTE PLANNER');
    clearActions();
    for (var i = 0; i < 6; i++) clearRow(i);

    var sec = S.sec || {};
    var primary = (sec.compare && sec.compare.primary) || {};
    var secondary = sec.secondary || null;
    var busy = !!S.secBusy;

    var destVal = S.secDest || (S.route.active ? S.route.destination : '') || '________';
    fill(0, {
      lh: secondary ? (secondary.profile + ' · PLOTTED') : '',
      lv: '<PLOT FUEL-SAFE', lvs: busy ? 's-muted' : 's-normal',
      rh: 'SEC DEST', rv: destVal, rvs: 's-cyan'
    });
    actions.L[0] = { press: function () { secPlotPress('fuel_safe'); },
                     input: function (v) { return secPlotInput(v, 'fuel_safe'); } };
    actions.R[0] = { press: null, input: secDestInput };

    fill(1, {
      lv: '<PLOT FAST/RISKY', lvs: busy ? 's-muted' : 's-normal',
      rh: 'JUMPS', rv: 'P ' + secCompareNum(primary.jumps) + ' / S ' + secCompareNum(secondary && secondary.jumps),
      rvs: 's-normal'
    });
    actions.L[1] = { press: function () { secPlotPress('fast'); },
                     input: function (v) { return secPlotInput(v, 'fast'); } };

    fill(2, {
      lv: S.secConfirm ? '<ACTIVATE SEC  CONFIRM?' : '<ACTIVATE SEC',
      lvs: S.secConfirm ? 's-alert' : (secondary ? 's-normal' : 's-muted'),
      rh: 'DIST', rv: 'P ' + secDist(primary.dist_ly) + ' / S ' + secDist(secondary && secondary.dist_ly) + ' LY',
      rvs: 's-normal'
    });
    actions.L[2] = { press: secActivatePress, input: null };

    var pScoops = secCompareNum(primary.scoops);
    var sScoops = secCompareNum(secondary && secondary.scoops);
    // L4 SEC FROM [E]: manual plot origin (default — current journal
    // location); lets a route be planned "from anywhere" before flying there.
    var fromVal = S.secFrom || (S.snap && S.snap.location) || '________';
    fill(3, {
      lh: 'SEC FROM', lv: fromVal, lvs: S.secFrom ? 's-cyan' : 's-muted',
      rh: 'SCOOPS', rv: 'P ' + pScoops + ' / S ' + sScoops, rvs: 's-normal'
    });
    // empty-scratchpad press reverts the override to the journal location
    actions.L[3] = { press: function () { if (S.secFrom) { S.secFrom = ''; render(); } },
                     input: secFromInput };

    var risk = secondary && secondary.risk;
    // L5 EXEC: state of the activated-route executor (contract exec_state).
    // Shown once a route was ever activated; press stops/clears the executor.
    var ex = S.exec;
    if (ex && ex.status && ex.status !== 'INACTIVE') {
      var exLabel = ex.status + (ex.jumps_total ? ' ' + ex.jumps_done + '/' + ex.jumps_total : '');
      fill(4, {
        lh: 'EXEC · ' + (ex.next_system ? 'NEXT ' + ex.next_system : (ex.destination || '')),
        lv: '<' + exLabel,
        lvs: ex.status === 'OFF ROUTE' ? 's-alert' : (ex.status === 'COMPLETE' ? 's-on' : 's-normal'),
        rh: 'RISK', rv: risk || '---', rvs: risk ? (risk === 'HIGH' ? 's-warn' : 's-on') : 's-muted'
      });
      actions.L[4] = { press: function () { if (ensureConn()) sendRaw({ cmd: 'exec.stop' }); },
                       input: null };
    } else {
      fill(4, { rh: 'RISK', rv: risk || '---', rvs: risk ? (risk === 'HIGH' ? 's-warn' : 's-on') : 's-muted' });
    }

    if (secondary) {
      fill(5, { rv: 'NEXT PAGE>', rvs: 's-cyan' });
      actions.R[5] = { press: function () { setPage('SECLIST'); }, input: null };
    }
    // L6 stays empty — SEC is a root page (spec §1.3: no RETURN).
  }

  // R1 SEC DEST [E]: local override for the plot destination; default (shown
  // when empty) is the active F-PLN destination. Accepting clears the
  // scratchpad (contract: the entered value now shows in the R1 cell).
  function secDestInput(v) {
    var t = v.trim();
    if (!t) return false;
    S.secDest = t;
    render();
    return true;
  }

  // L4 SEC FROM [E]: plot-origin override. Validation is server-side (EDSM);
  // an unknown system comes back as a sec_route error from sec.plot.
  function secFromInput(v) {
    var t = v.trim();
    if (!t) return false;
    S.secFrom = t;
    render();
    return true;
  }

  // L1/L2 PLOT actions: while a plot is already running (S.secBusy, set from
  // sec_plot_started until the matching sec_route lands) further presses just
  // flash instead of re-sending — the backend's own busy-guard would reject
  // the retry anyway (see PlotError("PLOT IN PROGRESS") in RoutePlanner.py).
  // With no destination anywhere (no SEC DEST, no active F-PLN) the press is
  // refused locally with a hint instead of a round-trip backend error.
  function secPlotPress(profile) {
    if (S.secBusy) { flash('PLOTTING…', 1200); return; }
    if (!S.secDest && !(S.route.active && S.route.destination)) {
      flash('ENTER SEC DEST', 1800);
      return;
    }
    if (!ensureConn()) return;
    var body = { cmd: 'sec.plot', profile: profile };
    if (S.secDest) body.dest = S.secDest;
    if (S.secFrom) body.source = S.secFrom;
    sendRaw(body);
  }

  // Scratchpad entry on a PLOT LSK: treat the typed text as the destination
  // and plot straight away (otherwise doLSK would reject the press with
  // NOT ALLOWED — an easy trap when F-PLN is empty and SEC DEST is blank).
  function secPlotInput(v, profile) {
    var t = v.trim();
    if (!t) return false;
    if (S.secBusy) { flash('PLOTTING…', 1200); return 'keep'; }
    if (!ensureConn()) return 'keep';
    S.secDest = t;
    var body = { cmd: 'sec.plot', profile: profile, dest: t };
    if (S.secFrom) body.source = S.secFrom;
    sendRaw(body);
    render();
    return true;
  }

  // Two-step confirm per §3.4: 1st press arms a 5s confirm window (label
  // flips to CONFIRM?); 2nd press within the window sends sec.activate — the
  // backend still stubs this as NOT AVAILABLE until the in-game part of
  // Phase 8.1 lands (§7 of the API contract), which surfaces as a normal
  // 'error' log line, not a local flash. The window auto-disarms on timeout,
  // and setPage() disarms it on leaving the SEC page so CONFIRM? never sticks.
  function secActivatePress() {
    if (S.secConfirm) {
      if (secConfirmT) { clearTimeout(secConfirmT); secConfirmT = null; }
      S.secConfirm = false;
      if (ensureConn()) sendRaw({ cmd: 'sec.activate' });
      render();
      return;
    }
    S.secConfirm = true;
    if (secConfirmT) clearTimeout(secConfirmT);
    secConfirmT = setTimeout(function () {
      secConfirmT = null;
      S.secConfirm = false;
      if (S.page === 'SEC') render();
    }, 5000);
    render();
  }

  // SECLIST · secondary-route system list (level 2, from SEC R6), spec §3.4
  // "R6 NEXT PAGE> — страницы списка SEC-маршрута (формат как F-PLN)". Same
  // continuous vertical-slew list idiom as F-PLN (renderROUTE/ROUTE_WIN), but
  // the Route.systems entries have no star_class (see §7 of the API
  // contract), so the row header is just the index. neutron gets an NTR tag
  // (whole line recolored s-warn — a single cell can't mix two text colors);
  // must_refuel has no dedicated icon in this data shape, so it is a ·RFL
  // text suffix; scoopable reuses the exact F-PLN SCOOP/✗ marker on the right.
  var SECLIST_WIN = 5;

  function secListSystems() { return (S.sec && S.sec.secondary && S.sec.secondary.systems) || []; }
  function secListItemCount() { var n = secListSystems().length; return n ? n + 1 : 0; }
  function secListMaxScroll() { return Math.max(0, secListItemCount() - SECLIST_WIN); }
  function clampSecListPage() {
    var m = secListMaxScroll();
    if (S.secListPage > m) S.secListPage = m;
    if (S.secListPage < 0) S.secListPage = 0;
  }

  function renderSECLIST() {
    clearActions();
    for (var i = 0; i < 6; i++) clearRow(i);

    var sys = secListSystems();
    var route = (S.sec && S.sec.secondary) || null;
    if (!route || sys.length === 0) {
      setHeader('RTE LIST', '---');
      fill(2, { lv: 'NO SECONDARY ROUTE', lvs: 's-muted', center: true });
      fill(5, { lv: '<RETURN', lvs: 's-normal' });
      actions.L[5] = { press: function () { setPage('SEC'); }, input: null };
      return;
    }

    clampSecListPage();
    var top = S.secListPage;
    var bottom = Math.min(top + SECLIST_WIN, sys.length);
    setHeader('RTE LIST', (top + 1) + '-' + bottom + '/' + sys.length + ' ↕');

    for (var r = 0; r < SECLIST_WIN; r++) {
      var gi = top + r;
      if (gi > sys.length) continue;
      if (gi === sys.length) {
        var totJumps = (route.jumps === null || route.jumps === undefined) ? (sys.length - 1) : route.jumps;
        var totLy = secDist(route.dist_ly);
        fill(r, {
          lh: 'END OF PLAN', lv: totJumps + ' JMP', lvs: 's-cyan',
          rh: 'TOTAL', rv: totLy + ' LY', rvs: 's-cyan'
        });
        continue;
      }
      var it = sys[gi];
      var dist = (gi === 0) ? 'ORIGIN'
        : (it.dist_ly === null || it.dist_ly === undefined ? '--' : Number(it.dist_ly).toFixed(1) + ' LY');
      // ▶ marks the executor's current position when this very route is the
      // activated one (same destination — a re-plot after activation unpins it)
      var here = S.exec && S.exec.active && S.exec.idx === gi &&
                 S.exec.destination === route.destination;
      var name = (here ? '▶' : '') + (it.system || '?') +
                 (it.neutron ? ' NTR' : '') + (it.must_refuel ? ' ·RFL' : '');
      fill(r, {
        lh: pad2(gi + 1), rh: dist,
        lv: name, lvs: here ? 's-on' : (it.neutron ? 's-warn' : 's-normal'),
        rv: it.scoopable ? 'SCOOP' : '✗', rvs: it.scoopable ? 's-on' : 's-alert'
      });
    }

    fill(5, { lv: '<RETURN', lvs: 's-normal' });
    actions.L[5] = { press: function () { setPage('SEC'); }, input: null };
  }

  // F-PLN · ACTIVE ROUTE, spec §3.3 + Замечания 12/13: the whole plan is one
  // continuous list scrolled with the vertical slew (like a real aircraft
  // F-PLN — no NEXT PAGE). 5-row window (S.routePage = top line index); the
  // plan total (jumps · LY) is the last scrolled line (END OF PLAN), not a
  // static row. Left LSK on a system drills into its SYSINFO page. FAST TRAVEL
  // moved off F-PLN to CRU OPT.
  var ROUTE_WIN = 5;

  function routeTotalLy(sys) {
    var t = 0;
    for (var i = 0; i < sys.length; i++) {
      var d = Number(sys[i].dist_ly);
      if (!isNaN(d)) t += d;
    }
    return t;
  }
  // list length includes a trailing END-OF-PLAN line when a route is active
  function routeItemCount() {
    var n = (S.route.systems || []).length;
    return n ? n + 1 : 0;
  }

  function renderROUTE() {
    clearActions();
    for (var i = 0; i < 6; i++) clearRow(i);

    var sys = S.route.systems || [];
    if (!S.route.active || sys.length === 0) {
      setHeader('F-PLN', 'NO ROUTE');
      fill(2, { lv: 'NO ACTIVE ROUTE', lvs: 's-muted', center: true });
      fill(3, { lv: 'PLOT ROUTE IN GALAXY MAP', lvs: 's-hint', center: true });
      return;
    }

    var total = routeItemCount();          // systems + END OF PLAN line
    var maxScroll = Math.max(0, total - ROUTE_WIN);
    if (S.routePage > maxScroll) S.routePage = maxScroll;
    if (S.routePage < 0) S.routePage = 0;
    var top = S.routePage;
    var bottom = Math.min(top + ROUTE_WIN, sys.length);
    setHeader('F-PLN', 'ROUTE ' + (top + 1) + '-' + bottom + '/' + sys.length + ' ↕');

    var loc = S.snap.location ? String(S.snap.location).toLowerCase() : null;

    for (var r = 0; r < ROUTE_WIN; r++) {
      var gi = top + r;
      if (gi > sys.length) continue;
      if (gi === sys.length) {
        // END OF PLAN — plan total scrolls into view at the end (not static)
        fill(r, {
          lh: 'END OF PLAN', lv: (sys.length - 1) + ' JMP', lvs: 's-cyan',
          rh: 'TOTAL', rv: routeTotalLy(sys).toFixed(1) + ' LY', rvs: 's-cyan'
        });
        continue;
      }
      var it = sys[gi];
      var head = pad2(gi + 1) + ' ' + (it.star_class || '?');
      var dist = (gi === 0) ? 'ORIGIN'
        : (it.dist_ly === null || it.dist_ly === undefined ? '--' : Number(it.dist_ly).toFixed(1) + ' LY');
      var cur = it.system && loc && String(it.system).toLowerCase() === loc;
      fill(r, {
        lh: head, rh: dist,
        lv: (cur ? '>' : '') + (it.system || '?'), lvs: cur ? 's-cyan' : 's-normal',
        rv: it.scoopable ? 'SCOOP' : '✗', rvs: it.scoopable ? 's-on' : 's-alert'
      });
      (function (idx) {
        actions.L[r] = { press: function () { openSysInfo(idx); }, input: null };
      })(gi);
    }
  }

  // FUEL PRED main page, spec §3.6. Header indicator mirrors the LED status.
  function renderFUEL() {
    var snap = S.snap;
    var st = snap.fuel_status;
    setHeader('FUEL PRED', st && st !== 'unknown' ? st.toUpperCase() : 'FUEL',
              !st || st === 'unknown');
    clearActions();
    for (var i = 0; i < 6; i++) clearRow(i);

    var f = fuelCell(snap.fuel_percent);
    var tons = (snap.fuel_level !== null && snap.fuel_level !== undefined && snap.fuel_capacity)
      ? ' · ' + snap.fuel_level + '/' + snap.fuel_capacity + ' T' : '';
    fill(0, { lv: '<ACTIVATE REFUEL', lvs: 's-normal',
      rh: 'FUEL', rv: f.t + tons, rvs: f.s });
    actions.L[0] = { press: function () { setPage('FUEL_SEL'); }, input: null };

    var tr = snap.jumps_to_refuel;
    fill(1, { rh: 'TO REFUEL',
      rv: (tr === null || tr === undefined) ? '---' : tr + ' JMP',
      rvs: (tr === null || tr === undefined) ? 's-muted' : (tr <= 2 ? 's-warn' : 's-normal') });

    var avg = snap.avg_fuel_per_jump;
    fill(2, { rh: 'AVG/JUMP',
      rv: avg ? avg + ' T' : '---', rvs: avg ? 's-normal' : 's-muted' });

    var rng = snap.range_jumps;
    fill(3, { rh: 'RANGE',
      rv: (rng === null || rng === undefined) ? '---' : rng + ' JMP',
      rvs: (rng === null || rng === undefined) ? 's-muted' : 's-normal' });

    var thr = S.cfg.RefuelThreshold;
    fill(4, { rh: 'RFL THRESHOLD',
      rv: (thr === null || thr === undefined) ? '---' : thr + '%',
      rvs: (thr === null || thr === undefined) ? 's-muted' : 's-cyan' });
    actions.R[4] = { press: null, input: thresholdInput };
  }

  function thresholdInput(v) {
    var n = v.trim();
    if (!/^\d{1,3}$/.test(n)) return false;
    var val = parseInt(n, 10);
    if (val < 0 || val > 100) return false;
    if (!ensureConn()) return 'keep';
    if (sendRaw({ cmd: 'config.set', key: 'RefuelThreshold', value: val })) {
      S.cfg.RefuelThreshold = val;
      render();
      return true;
    }
    return 'keep';
  }

  // REFUEL SELECT sub-page (level 2, from FUEL PRED L1), spec §3.6
  function renderFUELSEL() {
    var snap = S.snap;
    setHeader('REFUEL SELECT', 'FUEL');
    clearActions();
    for (var i = 0; i < 6; i++) clearRow(i);

    var starVal = snap.star_class
      ? snap.star_class + (snap.scoopable ? ' SCOOP' : ' ✗') : '---';
    fill(0, { lv: '<STAR THIS SYSTEM', lvs: 's-normal',
      rh: 'STAR', rv: starVal,
      rvs: !snap.star_class ? 's-muted' : (snap.scoopable ? 's-on' : 's-alert') });
    actions.L[0] = { press: function () { sendAction('scoop'); }, input: null };

    fill(1, { lv: '<NEAREST STATION', lvs: 's-muted', rh: 'STN', rv: '---', rvs: 's-muted' });
    actions.L[1] = { press: function () { flash('NOT AVAILABLE', 1500); }, input: null };
    fill(2, { lv: '<NEAREST RFL POINT', lvs: 's-muted', rh: 'PT', rv: '---', rvs: 's-muted' });
    actions.L[2] = { press: function () { flash('NOT AVAILABLE', 1500); }, input: null };

    fill(5, { lv: '<RETURN', lvs: 's-normal' });
    actions.L[5] = { press: function () { setPage('FUEL'); }, input: null };
  }

  // CRU OPT (repurposed RAD NAV key): cruise-behaviour settings collected in one
  // place — FAST TRAVEL and ELW SCAN as persistent [T]; HONK and FSS SCAN as
  // one-shot [A] for the current system (no auto-mode backend yet).
  function renderCRUOPT() {
    setHeader('CRU OPT', 'CRUISE');
    clearActions();
    for (var i = 0; i < 6; i++) clearRow(i);

    fill(0, {
      lv: S.fastTravel ? '<FAST TRAVEL  ON' : '<FAST TRAVEL  OFF', lvs: S.fastTravel ? 's-on' : 's-off',
      rh: 'MODE', rv: 'SKIP SCANS', rvs: 's-muted'
    });
    actions.L[0] = { press: ftToggle, input: null };

    var elwOn = !!S.cfg.ElwScannerEnable;
    fill(1, { lv: elwOn ? '<ELW SCAN  ON' : '<ELW SCAN  OFF', lvs: elwOn ? 's-on' : 's-off' });
    actions.L[1] = { press: elwToggle, input: null };

    fill(2, { lv: '<HONK', lvs: 's-normal' });
    actions.L[2] = { press: function () { sendAction('honk'); }, input: null };

    fill(3, { lv: '<FSS SCAN', lvs: 's-normal' });
    actions.L[3] = { press: function () { sendAction('fss_scan'); }, input: null };
  }

  // SYSINFO: per-system detail, opened from a left LSK on F-PLN (spec §3.3 drill-
  // in). Journal gives us basics; body count and external data (EDSM/Spansh)
  // arrive in Phase 8.1, shown as [план] until then.
  function renderSYSINFO() {
    var sys = S.route.systems || [];
    var idx = S.sysInfoIdx;
    var it = (idx !== null && idx >= 0 && idx < sys.length) ? sys[idx] : null;
    setHeader('SYSTEM', it ? pad2(idx + 1) + '/' + sys.length : '---', !it);
    clearActions();
    for (var i = 0; i < 6; i++) clearRow(i);

    if (!it) {
      fill(2, { lv: 'NO SYSTEM SELECTED', lvs: 's-muted', center: true });
      fill(5, { lv: '<RETURN', lvs: 's-normal' });
      actions.L[5] = { press: function () { setPage('ROUTE'); }, input: null };
      return;
    }

    var loc = S.snap.location ? String(S.snap.location).toLowerCase() : null;
    var isCurrent = it.system && loc && String(it.system).toLowerCase() === loc;

    fill(0, {
      lh: 'SYSTEM', lv: (isCurrent ? '>' : '') + (it.system || '?'), lvs: isCurrent ? 's-cyan' : 's-normal',
      rh: 'CLASS', rv: it.star_class || '---', rvs: it.star_class ? 's-normal' : 's-muted'
    });
    fill(1, {
      lh: 'SCOOPABLE', lv: it.scoopable ? 'YES' : 'NO', lvs: it.scoopable ? 's-on' : 's-alert',
      rh: 'DIST', rv: (idx === 0) ? 'ORIGIN'
        : (it.dist_ly === null || it.dist_ly === undefined ? '---' : Number(it.dist_ly).toFixed(1) + ' LY'),
      rvs: 's-normal'
    });

    // body count: only the current system is scanned; journal gives fss_body_count
    var bodies = isCurrent && S.snap.fss_body_count ? String(S.snap.fss_body_count) : '---';
    fill(2, { lh: 'BODIES', lv: bodies, lvs: (bodies === '---') ? 's-muted' : 's-normal',
      rh: 'EDSM', rv: 'NO DATA', rvs: 's-muted' });

    // scan actions only make sense for the system we are in
    if (isCurrent) {
      fill(3, { lv: '<HONK', lvs: 's-normal', rh: '', rv: '' });
      actions.L[3] = { press: function () { sendAction('honk'); }, input: null };
      fill(4, { lv: '<FSS SCAN', lvs: 's-normal' });
      actions.L[4] = { press: function () { sendAction('fss_scan'); }, input: null };
    } else {
      fill(3, { lv: 'EXTERNAL DATA', lvs: 's-muted', center: true });
      fill(4, { lv: 'AWAITS BACKEND (PHASE 8.1)', lvs: 's-hint', center: true });
    }

    fill(5, { lv: '<RETURN', lvs: 's-normal' });
    actions.L[5] = { press: function () { setPage('ROUTE'); }, input: null };
  }

  function openSysInfo(gi) {
    S.sysInfoIdx = gi;
    setPage('SYSINFO');
  }

  // DATA · SYSTEM DATA, spec §3.8: reference readout for the current system —
  // system, arrival star, scan/EDSM summaries. EDSM fetch and the scan/EDSM
  // summary rows are [план] until the backend lands in Phase 8.1, shown as
  // muted NO DATA / a NOT AVAILABLE flash until then. Reached only from INIT
  // L4 (sub-page of PREFLIGHT), so L6 returns there like SYSINFO returns to ROUTE.
  function renderDATA() {
    setHeader('DATA', 'SYSTEM DATA');
    clearActions();
    for (var i = 0; i < 6; i++) clearRow(i);

    var loc = S.snap.location ? String(S.snap.location) : null;
    var locLower = loc ? loc.toLowerCase() : null;
    var sys = S.route.systems || [];
    var cur = null;
    for (var si = 0; si < sys.length; si++) {
      if (sys[si].system && locLower && String(sys[si].system).toLowerCase() === locLower) {
        cur = sys[si];
        break;
      }
    }

    fill(0, { lv: '<EDSM FETCH', lvs: 's-normal',
      rh: 'SYSTEM', rv: loc || '---', rvs: loc ? 's-normal' : 's-muted' });
    actions.L[0] = { press: function () { flash('NOT AVAILABLE', 1500); }, input: null };

    var starVal = cur && cur.star_class
      ? cur.star_class + ' ' + (cur.scoopable ? 'SCOOP' : '✗') : '---';
    fill(1, { rh: 'STAR', rv: starVal,
      rvs: (cur && cur.star_class) ? (cur.scoopable ? 's-on' : 's-alert') : 's-muted' });

    fill(2, { rh: 'SCANS', rv: 'NO DATA', rvs: 's-muted' });
    fill(3, { rh: 'EDSM', rv: 'NO DATA', rvs: 's-muted' });

    fill(5, { lv: '<RETURN', lvs: 's-normal', rv: 'NEXT PAGE>', rvs: 's-muted' });
    actions.L[5] = { press: function () { setPage('INIT'); }, input: null };
    actions.R[5] = { press: function () { flash('PAGE INOP', 1500); }, input: null };
  }

  // MCDU MENU · SETTINGS root, spec §3.9. Reached from the MCDU MENU
  // hardware key; L1-L3 drill into OPTIONS/CONFIG/MAINT sub-pages. LOAD ALL
  // / SAVE ALL are [план] — no backend command yet.
  function renderSETTINGS() {
    setHeader('MCDU MENU', 'SETTINGS');
    clearActions();
    for (var i = 0; i < 6; i++) clearRow(i);

    fill(0, { lv: '<OPTIONS', lvs: 's-normal',
      rh: 'CORE', rv: S.connected ? 'CONNECTED' : 'OFFLINE',
      rvs: S.connected ? 's-on' : 's-alert' });
    actions.L[0] = { press: function () { setPage('OPTIONS'); }, input: null };

    fill(1, { lv: '<CONFIG', lvs: 's-normal',
      rh: 'GAME', rv: '---', rvs: 's-muted' });
    actions.L[1] = { press: function () { setPage('CFG'); }, input: null };

    fill(2, { lv: '<MAINT', lvs: 's-normal' });
    actions.L[2] = { press: function () { setPage('MAINT'); }, input: null };

    fill(3, { lv: '<RPY TUNING', lvs: 's-normal' });
    actions.L[3] = { press: function () { setPage('TUNING'); }, input: null };

    fill(4, { lv: '<LOAD ALL', lvs: 's-normal' });
    actions.L[4] = { press: function () { if (ensureConn()) sendRaw({ cmd: 'config.load' }); }, input: null };

    fill(5, { lv: '<SAVE ALL', lvs: 's-normal' });
    actions.L[5] = { press: function () { if (ensureConn()) sendRaw({ cmd: 'config.save' }); }, input: null };
  }

  // MCDU MENU · OPTIONS sub-page, spec §3.9. Persistent behaviour toggles.
  function renderOPTIONS() {
    setHeader('OPTIONS', 'SETTINGS');
    clearActions();
    for (var i = 0; i < 6; i++) clearRow(i);

    var voiceOn = !!S.cfg.VoiceEnable;
    fill(0, { lv: voiceOn ? '<VOICE  ON' : '<VOICE  OFF', lvs: voiceOn ? 's-on' : 's-off' });
    actions.L[0] = { press: voiceToggle, input: null };

    var overlayOn = !!S.cfg.OverlayTextEnable;
    fill(1, { lv: overlayOn ? '<OVERLAY  ON' : '<OVERLAY  OFF', lvs: overlayOn ? 's-on' : 's-off' });
    actions.L[1] = { press: overlayToggle, input: null };

    var hotkeysOn = !!S.cfg.HotkeysEnable;
    fill(2, { lv: hotkeysOn ? '<HOTKEYS  ON' : '<HOTKEYS  OFF', lvs: hotkeysOn ? 's-on' : 's-off' });
    actions.L[2] = { press: hotkeysToggle, input: null };

    var randOn = !!S.cfg.EnableRandomness;
    fill(3, { lv: randOn ? '<RANDOMNESS  ON' : '<RANDOMNESS  OFF', lvs: randOn ? 's-on' : 's-off' });
    actions.L[3] = { press: randomnessToggle, input: null };

    var logoutOn = !!S.cfg.AutomaticLogout;
    fill(4, { lv: logoutOn ? '<AUTO LOGOUT  ON' : '<AUTO LOGOUT  OFF', lvs: logoutOn ? 's-on' : 's-off' });
    actions.L[4] = { press: autoLogoutToggle, input: null };

    fill(5, { lv: '<RETURN', lvs: 's-normal' });
    actions.L[5] = { press: function () { setPage('SETTINGS'); }, input: null };
  }

  // MCDU MENU · CONFIG sub-page, spec §3.9 + parity-gap extension (7.4б,
  // Замечание 16 — docs/tkinter_parity_audit.md §(б)). Now 5 pages: 1/5 is
  // the original bindings page (RELOAD BINDINGS / AUTO-ASSIGN KEYS / REFRESH
  // GAME SET are still [план] — no backend command yet); 2/5-5/5 add
  // settings ported from the tkinter GUI that had no web equivalent. R6
  // NEXT PAGE> and slew ←/→ cycle 1..5; L6 RETURN always goes to SETTINGS
  // regardless of which CONFIG page is open.
  function renderCFG() {
    setHeader('CONFIG', (S.cfgPage + 1) + '/5 →');
    clearActions();
    for (var i = 0; i < 6; i++) clearRow(i);

    if (S.cfgPage === 1) renderCFG2();
    else if (S.cfgPage === 2) renderCFG3();
    else if (S.cfgPage === 3) renderCFG4();
    else if (S.cfgPage === 4) renderCFG5();
    else renderCFG1();

    fill(5, { lv: '<RETURN', lvs: 's-normal', rv: 'NEXT PAGE>', rvs: 's-normal' });
    actions.L[5] = { press: function () { setPage('SETTINGS'); }, input: null };
    actions.R[5] = { press: function () { S.cfgPage = (S.cfgPage + 1) % 5; render(); }, input: null };
  }

  // CONFIG 1/5 — key bindings (unchanged from the pre-7.4б single page).
  function renderCFG1() {
    var eliteOn = !!S.cfg.ActivateEliteEachKey;
    fill(0, { lv: eliteOn ? '<ACT-ELITE KEY  ON' : '<ACT-ELITE KEY  OFF', lvs: eliteOn ? 's-on' : 's-off' });
    actions.L[0] = { press: actEliteToggle, input: null };

    fill(1, { lv: '<RELOAD BINDINGS', lvs: 's-normal', rh: 'BINDS', rv: '---', rvs: 's-muted' });
    actions.L[1] = { press: function () { flash('NOT AVAILABLE', 1500); }, input: null };

    fill(2, { lv: '<AUTO-ASSIGN KEYS', lvs: 's-normal' });
    actions.L[2] = { press: function () { flash('NOT AVAILABLE', 1500); }, input: null };

    fill(3, { lv: '<REFRESH GAME SET', lvs: 's-normal' });
    actions.L[3] = { press: function () { flash('NOT AVAILABLE', 1500); }, input: null };
  }

  // CONFIG 2/5 — AP behaviour (parity-gap ext. 7.4б).
  function renderCFG2() {
    var dssSecondary = S.cfg.DSSButton === 'Secondary';
    var sb = cfgNumCell(S.cfg.SunBrightThreshold);
    fill(0, { lv: '<DSS BTN  ' + (dssSecondary ? 'SECONDARY' : 'PRIMARY'), lvs: 's-cyan',
      rh: 'SUN BRIGHT', rv: sb.rv, rvs: sb.rvs });
    actions.L[0] = { press: dssButtonToggle, input: null };
    actions.R[0] = { press: null, input: intCfgInput('SunBrightThreshold', 0, 255) };

    var tuneOn = !!S.cfg.AutoTuneRPYRates;
    var nat = cfgNumCell(S.cfg.NavAlignTries);
    fill(1, { lv: tuneOn ? '<AUTO TUNE RPY  ON' : '<AUTO TUNE RPY  OFF', lvs: tuneOn ? 's-on' : 's-off',
      rh: 'NAV ALIGN TRIES', rv: nat.rv, rvs: nat.rvs });
    actions.L[1] = { press: autoTuneToggle, input: null };
    actions.R[1] = { press: null, input: intCfgInput('NavAlignTries', 1) };

    var jt = cfgNumCell(S.cfg.JumpTries);
    fill(2, { lv: '<LANGUAGE  ' + String(S.cfg.Language || 'en').toUpperCase(), lvs: 's-cyan',
      rh: 'JUMP TRIES', rv: jt.rv, rvs: jt.rvs });
    actions.L[2] = { press: languageToggle, input: null };
    actions.R[2] = { press: null, input: intCfgInput('JumpTries', 1) };

    var lvl = S.cfg.LogDEBUG ? 'DEBUG' : (S.cfg.LogINFO ? 'INFO' : 'ERROR');
    var dr = cfgNumCell(S.cfg.DockingRetries);
    fill(3, { lv: '<LOG LVL  ' + lvl, lvs: 's-cyan',
      rh: 'DOCK RETRIES', rv: dr.rv, rvs: dr.rvs });
    actions.L[3] = { press: logLevelToggle, input: null };
    actions.R[3] = { press: null, input: intCfgInput('DockingRetries', 1) };

    var wt = cfgNumCell(S.cfg.WaitForAutoDockTimer, function (v) { return v + ' S'; });
    fill(4, { rh: 'AUTODOCK WAIT', rv: wt.rv, rvs: wt.rvs });
    actions.R[4] = { press: null, input: floatCfgInput('WaitForAutoDockTimer') };
  }

  // CONFIG 3/5 — fuel / overlay (parity-gap ext. 7.4б). Overlay X/Y/font are
  // read by the core only at start, hence the ON RESTART hint (core TODO).
  function renderCFG3() {
    var st = cfgNumCell(S.cfg.FuelScoopTimeOut, function (v) { return v + ' S'; });
    fill(0, { rh: 'SCOOP TIMEOUT', rv: st.rv, rvs: st.rvs });
    actions.R[0] = { press: null, input: floatCfgInput('FuelScoopTimeOut') };

    var fa = cfgNumCell(S.cfg.FuelThreasholdAbortAP, function (v) { return v + '%'; });
    fill(1, { lv: 'OVERLAY APPLIES ON RESTART', lvs: 's-hint',
      rh: 'FUEL ABORT', rv: fa.rv, rvs: fa.rvs });
    actions.R[1] = { press: null, input: intCfgInput('FuelThreasholdAbortAP', 0, 100) };

    var ox = cfgNumCell(S.cfg.OverlayTextXOffset);
    fill(2, { rh: 'OVL X', rv: ox.rv, rvs: ox.rvs });
    actions.R[2] = { press: null, input: intCfgInput('OverlayTextXOffset', 0) };

    var oy = cfgNumCell(S.cfg.OverlayTextYOffset);
    fill(3, { rh: 'OVL Y', rv: oy.rv, rvs: oy.rvs });
    actions.R[3] = { press: null, input: intCfgInput('OverlayTextYOffset', 0) };

    var of = cfgNumCell(S.cfg.OverlayTextFontSize);
    fill(4, { rh: 'OVL FONT', rv: of.rv, rvs: of.rvs });
    actions.R[4] = { press: null, input: intCfgInput('OverlayTextFontSize', 1) };
  }

  // CONFIG 4/5 and 5/5 — game wait timers (parity-gap ext. 7.4б), R1-R5
  // only, all floats >=0 rendered as "n.n S".
  function renderWaitRows(list) {
    for (var i = 0; i < list.length; i++) {
      var key = list[i][0], label = list[i][1];
      var c = cfgNumCell(S.cfg[key], function (v) { return Number(v).toFixed(1) + ' S'; });
      fill(i, { rh: label, rv: c.rv, rvs: c.rvs });
      actions.R[i] = { press: null, input: floatCfgInput(key) };
    }
  }
  function renderCFG4() {
    renderWaitRows([
      ['Wait_FSSDetect', 'FSS DETECT'],
      ['Wait_DockApproach', 'DOCK APPROACH'],
      ['Wait_ShipStop', 'SHIP STOP'],
      ['Wait_OccludedReposition', 'OCCLUDED REPOS'],
      ['Wait_DSSScan', 'DSS SCAN']
    ]);
  }
  function renderCFG5() {
    renderWaitRows([
      ['Wait_PastSun', 'PAST SUN'],
      ['Wait_HeatDissipate', 'HEAT DISSIP'],
      ['Wait_AfterJump', 'AFTER JUMP'],
      ['PlanetDepartureSCOTime', 'PLANET DEP SCO'],
      ['FCDepartureTime', 'FC DEPART']
    ]);
  }

  // MCDU MENU · MAINT sub-page (dev/debug), spec §3.9. CV VIEW is an int 0/1
  // flag on the backend, not a bool — toggle sends/stores 1/0.
  function renderMAINT() {
    setHeader('MAINT', 'DEV');
    clearActions();
    for (var i = 0; i < 6; i++) clearRow(i);

    var cvOn = !!S.cfg.Enable_CV_View;
    var md = S.cfg.Key_ModDelay;
    fill(0, { lv: cvOn ? '<CV VIEW  ON' : '<CV VIEW  OFF', lvs: cvOn ? 's-on' : 's-off',
      rh: 'MOD DELAY', rv: (md === null || md === undefined) ? '---' : Number(md).toFixed(2) + ' S',
      rvs: (md === null || md === undefined) ? 's-muted' : 's-cyan' });
    actions.L[0] = { press: cvViewToggle, input: null };
    actions.R[0] = { press: null, input: floatCfgInput('Key_ModDelay') };

    var dbgOverlayOn = !!S.cfg.DebugOverlay;
    var dh = S.cfg.Key_DefHoldTime;
    fill(1, { lv: dbgOverlayOn ? '<DBG OVERLAY  ON' : '<DBG OVERLAY  OFF', lvs: dbgOverlayOn ? 's-on' : 's-off',
      rh: 'DEF HOLD', rv: (dh === null || dh === undefined) ? '---' : Number(dh).toFixed(2) + ' S',
      rvs: (dh === null || dh === undefined) ? 's-muted' : 's-cyan' });
    actions.L[1] = { press: dbgOverlayToggle, input: null };
    actions.R[1] = { press: null, input: floatCfgInput('Key_DefHoldTime') };

    var dbgOcrOn = !!S.cfg.DebugOCR;
    var rd = S.cfg.Key_RepeatDelay;
    fill(2, { lv: dbgOcrOn ? '<DBG OCR  ON' : '<DBG OCR  OFF', lvs: dbgOcrOn ? 's-on' : 's-off',
      rh: 'REPEAT DLY', rv: (rd === null || rd === undefined) ? '---' : Number(rd).toFixed(2) + ' S',
      rvs: (rd === null || rd === undefined) ? 's-muted' : 's-cyan' });
    actions.L[2] = { press: dbgOcrToggle, input: null };
    actions.R[2] = { press: null, input: floatCfgInput('Key_RepeatDelay') };

    var dbgImgOn = !!S.cfg.DebugImages;
    fill(3, { lv: dbgImgOn ? '<DBG IMAGES  ON' : '<DBG IMAGES  OFF', lvs: dbgImgOn ? 's-on' : 's-off' });
    actions.L[3] = { press: dbgImagesToggle, input: null };

    fill(4, { lv: '<CALIBRATION', lvs: 's-normal' });
    actions.L[4] = { press: function () { setPage('CALIB'); }, input: null };

    fill(5, { lv: '<RETURN', lvs: 's-normal' });
    actions.L[5] = { press: function () { setPage('SETTINGS'); }, input: null };
  }

  // CALIB · OCR REGIONS, spec §3.9 / 7.4в (web replacement for the tkinter
  // Calibration tab). Reached only from MAINT L5 <CALIBRATION. Root list
  // page: a vertically-scrolled window over the calibration key/value store
  // (idiom copied from F-PLN's ROUTE_WIN scroll), left LSK on a row drills
  // into the CALIBREG sub-page for that key.
  var CALIB_WIN = 4;

  function calibKeys() {
    return S.calib ? Object.keys(S.calib).sort() : [];
  }

  // Keys are "ClassName.field[.subregion.sub]" and can run well past the 24-
  // char cell width (e.g. "EDGalaxyMap.full_panel.subregion.cartographics").
  // The class-name prefix carries the least information for telling rows
  // apart at a glance, so drop it first; if the remainder still overflows,
  // keep its tail (closest to the leaf field name) rather than its head.
  function shortKey(key) {
    var dot = key.indexOf('.');
    var rest = dot >= 0 ? key.slice(dot + 1) : key;
    return rest.length <= 24 ? rest : ('…' + rest.slice(-23));
  }
  // class prefix for the row header — disambiguates same-suffix keys
  // (five different classes all carry a 'full_panel' region)
  function calibClass(key) {
    var dot = key.indexOf('.');
    var cls = dot >= 0 ? key.slice(0, dot) : key;
    return cls.replace(/^ED/, '');
  }

  function calibMaxScroll() {
    return Math.max(0, calibKeys().length - CALIB_WIN);
  }
  function clampCalibPage() {
    var m = calibMaxScroll();
    if (S.calibPage > m) S.calibPage = m;
    if (S.calibPage < 0) S.calibPage = 0;
  }

  function renderCALIB() {
    clearActions();
    for (var i = 0; i < 6; i++) clearRow(i);
    var keys = calibKeys();
    var total = keys.length;

    if (!S.calib) {
      setHeader('CALIB', 'OCR REGIONS');
      fill(2, { lv: 'LOADING CALIBRATION', lvs: 's-hint', center: true });
    } else {
      clampCalibPage();
      var top = S.calibPage;
      var bottom = Math.min(top + CALIB_WIN, total);
      setHeader('CALIB', total ? (top + 1) + '-' + bottom + '/' + total : 'OCR REGIONS');
      for (var r = 0; r < CALIB_WIN; r++) {
        var gi = top + r;
        if (gi >= total) continue;
        var key = keys[gi];
        var entry = S.calib[key];
        fill(r, {
          lh: pad2(gi + 1) + ' ' + calibClass(key), lv: shortKey(key), lvs: 's-normal',
          rv: (entry && entry.readonly) ? 'RO' : '', rvs: 's-muted'
        });
        (function (k) {
          actions.L[r] = { press: function () { S.calibKey = k; setPage('CALIBREG'); }, input: null };
        })(key);
      }
    }

    fill(4, {
      lv: '<SAVE CALIB', lvs: 's-normal',
      rv: S.calibResetConfirm ? 'RESET ALL  CONFIRM?' : 'RESET ALL>',
      rvs: S.calibResetConfirm ? 's-alert' : 's-cyan'
    });
    actions.L[4] = { press: function () { if (ensureConn()) sendRaw({ cmd: 'calibration.save' }); }, input: null };
    actions.R[4] = { press: calibResetPress, input: null };

    var targetLabel = S.calibRunning ? 'CALIBRATING…'
      : (S.calibTargetConfirm ? 'CAL TARGET  CONFIRM?' : 'CAL TARGET>');
    fill(5, {
      lv: '<RETURN', lvs: 's-normal',
      rv: targetLabel, rvs: S.calibRunning ? 's-muted' : (S.calibTargetConfirm ? 's-alert' : 's-cyan')
    });
    actions.L[5] = { press: function () { setPage('MAINT'); }, input: null };
    actions.R[5] = { press: calibTargetPress, input: null };
  }

  // R5 RESET ALL>: two-step confirm (arm -> CONFIRM? -> act), same window/
  // timeout idiom as SEC F-PLN's secActivatePress.
  function calibResetPress() {
    if (!ensureConn()) return;
    if (S.calibResetConfirm) {
      if (calibResetConfirmT) { clearTimeout(calibResetConfirmT); calibResetConfirmT = null; }
      S.calibResetConfirm = false;
      sendRaw({ cmd: 'calibration.reset' });
      render();
      return;
    }
    S.calibResetConfirm = true;
    if (calibResetConfirmT) clearTimeout(calibResetConfirmT);
    calibResetConfirmT = setTimeout(function () {
      calibResetConfirmT = null;
      S.calibResetConfirm = false;
      if (S.page === 'CALIB') render();
    }, 5000);
    render();
  }

  // R6 CAL TARGET>: two-step confirm, then a long blocking scan on the
  // backend — while it runs the label reads CALIBRATING… and further presses
  // just flash IN PROGRESS instead of re-arming.
  function calibTargetPress() {
    if (S.calibRunning) { flash('IN PROGRESS', 1500); return; }
    if (!ensureConn()) return;
    if (S.calibTargetConfirm) {
      if (calibTargetConfirmT) { clearTimeout(calibTargetConfirmT); calibTargetConfirmT = null; }
      S.calibTargetConfirm = false;
      sendRaw({ cmd: 'calibration.calibrate_target' });
      render();
      return;
    }
    S.calibTargetConfirm = true;
    if (calibTargetConfirmT) clearTimeout(calibTargetConfirmT);
    calibTargetConfirmT = setTimeout(function () {
      calibTargetConfirmT = null;
      S.calibTargetConfirm = false;
      if (S.page === 'CALIB') render();
    }, 5000);
    render();
  }

  // CALIBREG · drill-in for one region key, opened from a CALIB row.
  // R1-R4 edit rect[0..3] (X0/Y0/X1/Y1) via [E]; readonly regions show the
  // values muted with no input. L1 previews the quad on the game monitor;
  // L2-L4 show the region's instruction text (first ~3 non-blank lines).
  var CALIB_RECT_LABELS = ['X0', 'Y0', 'X1', 'Y1'];

  function calibTextLines(text) {
    var raw = String(text || '').split('\n');
    var out = [];
    for (var i = 0; i < raw.length && out.length < 3; i++) {
      var line = raw[i].trim();
      if (!line) continue;
      out.push(line.length > 24 ? line.slice(0, 23) + '…' : line);
    }
    return out;
  }

  function renderCALIBREG() {
    clearActions();
    for (var i = 0; i < 6; i++) clearRow(i);
    var key = S.calibKey;
    var entry = (S.calib && key) ? S.calib[key] : null;
    setHeader('CALIB REG', key ? (calibClass(key) + '·' + shortKey(key)).slice(0, 26) : '---');

    if (!entry) {
      fill(2, { lv: 'NO REGION SELECTED', lvs: 's-muted', center: true });
      fill(5, { lv: '<RETURN', lvs: 's-normal' });
      actions.L[5] = { press: function () { setPage('CALIB'); }, input: null };
      return;
    }

    var rect = entry.rect || [0, 0, 0, 0];
    var ro = !!entry.readonly;
    var textLines = calibTextLines(entry.text);

    for (var i = 0; i < 4; i++) {
      var val = (rect[i] === null || rect[i] === undefined) ? '---' : Number(rect[i]).toFixed(4);
      var row = { rh: CALIB_RECT_LABELS[i], rv: val, rvs: ro ? 's-muted' : 's-cyan' };
      if (i === 0) { row.lv = '<PREVIEW'; row.lvs = 's-normal'; }
      else { row.lv = textLines[i - 1] || ''; row.lvs = 's-hint'; }
      fill(i, row);
      if (!ro) actions.R[i] = { press: null, input: calibRectInput(key, i) };
    }
    actions.L[0] = { press: function () { if (ensureConn()) sendRaw({ cmd: 'calibration.preview', key: key }); }, input: null };

    if (ro) fill(4, { lv: 'READ-ONLY · DERIVED', lvs: 's-hint', center: true });

    fill(5, { lv: '<RETURN', lvs: 's-normal' });
    actions.L[5] = { press: function () { setPage('CALIB'); }, input: null };
  }

  // shared [E] input handler factory for one rect component: 0..1 float,
  // sends the FULL rect (backend contract) with just this component swapped.
  // Local validation is number + range only; x0<x1/y0<y1 is server-side (an
  // error there arrives as a MESSAGE LOG line, not a local INVALID).
  function calibRectInput(key, idx) {
    return function (v) {
      var n = parseFloat(v.trim());
      if (isNaN(n) || n < 0 || n > 1) return false;
      var entry = S.calib && S.calib[key];
      if (!entry) return false;
      var rect = (entry.rect || [0, 0, 0, 0]).slice();
      rect[idx] = n;
      if (!ensureConn()) return 'keep';
      if (sendRaw({ cmd: 'calibration.set_rect', key: key, rect: rect })) return true;
      return 'keep';
    };
  }

  // RPY TUNING · spec §3.7. Formerly the top-level PERF page; moved under
  // SETTINGS as a ship-tuning sub-page (заказчик: настройка корабля, не
  // лётная механика — Замечание 14). Reached only via SETTINGS > RPY TUNING.
  function renderTUNING() {
    setHeader('RPY CURVES', 'SETTINGS');
    clearActions();
    for (var i = 0; i < 6; i++) clearRow(i);

    var axisNames = { RollRate: 'ROLL', PitchRate: 'PITCH', YawRate: 'YAW' };
    var axisLabels = { RollRate: 'Deg/Sec', PitchRate: 'Deg/Sec', YawRate: 'Deg/Sec' };
    var axis = S.curveAxis;

    var thr = (S.throttle === null) ? '---' : S.throttle + '%';
    var spd = S.curveSpeed || '---';

    // Row 0: axis selector (L1-L3) + throttle (R1)
    fill(0, {
      lh: 'AXIS',
      lv: axis === 'RollRate' ? '<ROLL' : axis === 'PitchRate' ? '<PITCH' : '<YAW',
      lvs: 's-on',
      rh: 'THROTTLE', rv: thr, rvs: (S.throttle === null) ? 's-muted' : 's-cyan'
    });
    actions.L[0] = { press: curveAxisCycle, input: curveAxisInput };
    actions.R[0] = { press: throttlePress, input: throttleInput };

    // Row 1: axis labels
    fill(1, {
      lh: 'CURVE',
      lv: axisNames[axis] + ' RATE',
      lvs: 's-normal',
      rh: 'SPEED', rv: spd, rvs: 's-muted'
    });

    // Row 2: hint — point selection now happens via slew (see slew()), not an LSK row
    fill(2, { lv: 'DRAG PTS · DBL-CLICK ADDS · SLEW ↔ SEL PT', lvs: 's-hint', center: true });

    // Row 3: save to disk / delete selected point (moved up from row 5)
    fill(3, {
      lv: '<SAVE TO DISK', lvs: 's-on',
      rv: 'DEL PT>', rvs: 's-cyan'
    });
    // input: null — these keys take no scratchpad entry, so a non-empty
    // scratch correctly gets the standard NOT ALLOWED flash (entry preserved)
    // instead of being silently swallowed ('keep') or mislabelled INVALID.
    actions.L[3] = { press: curveSaveAll, input: null };
    actions.R[3] = { press: curveDelPoint, input: null };

    // Row 4: selected point info / set value from scratchpad
    fill(4, {
      lh: 'SET VAL',
      lv: curveSelLabel(),
      lvs: 's-normal',
      rh: '', rv: 'SAVE>', rvs: 's-on'
    });
    actions.L[4] = { press: function () {}, input: curveSetValue };
    actions.R[4] = { press: curveSave, input: null };

    // Row 5: return to SETTINGS root
    fill(5, { lv: '<RETURN', lvs: 's-normal' });
    actions.L[5] = { press: function () { setPage('SETTINGS'); }, input: null };

    // show the curve editor panel below the instrument
    curvePanel.hidden = false;
    if (!S.curveEditor) {
      S.curveEditor = McduCurves.mount(curveView, {}, {
        title: axisNames[axis] + ' RATE',
        xLabel: 'Angle (deg)',
        yLabel: axisLabels[axis],
        onChange: curveOnChange
      });
      S.curveNeedsLoad = true;
    }
    // request current curve data — only when needed and not already in flight
    if (S.curveNeedsLoad && !S.curvePending) {
      if (sendRaw({ cmd: 'curve.get', axis: axis })) S.curvePending = true;
    }
  }

  function curveSwitchAxis(axis) {
    S.curveAxis = axis;
    // clear and rebuild editor for new axis
    if (S.curveEditor) { S.curveEditor.destroy(); S.curveEditor = null; }
    curveView.innerHTML = '';
    S.curveNeedsLoad = true;
    S.curvePending = false;
    renderTUNING();
  }

  function curveAxisCycle() {
    var order = ['RollRate', 'PitchRate', 'YawRate'];
    var idx = order.indexOf(S.curveAxis);
    curveSwitchAxis(order[(idx + 1) % 3]);
  }

  function curveAxisInput(v) {
    var m = { 'ROLL': 'RollRate', 'PITCH': 'PitchRate', 'YAW': 'YawRate' };
    var axis = m[v.trim().toUpperCase()];
    if (!axis) return false;
    curveSwitchAxis(axis);
    return true;
  }

  function curveSelPrev() {
    if (!S.curveEditor) return;
    var idx = S.curveEditor.selectedIndex();
    if (idx < 0) idx = 0;
    S.curveEditor.selectIndex(Math.max(0, idx - 1));
    renderTUNING();
  }

  function curveSelNext() {
    if (!S.curveEditor) return;
    var idx = S.curveEditor.selectedIndex();
    S.curveEditor.selectIndex(idx + 1);
    renderTUNING();
  }

  function curveSelLabel() {
    if (!S.curveEditor) return '---';
    var idx = S.curveEditor.selectedIndex();
    if (idx < 0) return 'NO SELECTION';
    var pts = S.curveEditor.getPoints();
    var keys = Object.keys(pts).sort(function (a, b) { return parseFloat(a) - parseFloat(b); });
    var k = keys[idx];
    return k + '° → ' + pts[k];
  }

  function curveSetValue(v) {
    if (!S.curveEditor) return false;
    var n = parseFloat(v.trim());
    if (isNaN(n) || n < 0) return false;
    if (!S.curveEditor.setSelectedValue(n)) { flash('SELECT A POINT', 1500); return 'keep'; }
    renderTUNING();
    return true;
  }

  function curveHasPoints() {
    return S.curveEditor && Object.keys(S.curveEditor.getPoints()).length > 0;
  }

  function curveSave() {
    if (!S.curveEditor || !ensureConn()) return;
    if (!curveHasPoints()) { flash('NO POINTS', 1500); return; }
    sendRaw({ cmd: 'curve.set', axis: S.curveAxis, data: S.curveEditor.getPoints() });
  }

  function curveSaveAll() {
    if (!ensureConn()) return;
    // save current curve first (skip an empty one — the server rejects it)
    if (curveHasPoints()) {
      sendRaw({ cmd: 'curve.set', axis: S.curveAxis, data: S.curveEditor.getPoints() });
    }
    // then trigger full config save on server (ship configs to disk);
    // the result flash comes from the server's ship_saved reply
    sendRaw({ cmd: 'config.save_ship' });
  }

  function curveDelPoint() {
    if (!S.curveEditor) return;
    if (S.curveEditor.selectedIndex() < 0) { flash('SELECT A POINT', 1500); return; }
    if (!S.curveEditor.deleteSelected()) { flash('LAST POINT', 1500); return; }
    renderTUNING();
  }

  function curveOnChange(data) {
    // auto-save on every drag release — curve is updated in memory on the server
    sendRaw({ cmd: 'curve.set', axis: S.curveAxis, data: data });
  }

  function hideCurvePanel() {
    curvePanel.hidden = true;
  }

  // ---- top-level render ----
  // DIR doubles as "back to the main screen" until it gets a real Direct-To page
  var PAGE_FOR_KEY = { 'DIR': 'DIR', 'INIT': 'INIT', 'PROG': 'PROG', 'F-PLN': 'ROUTE', 'RTE PLAN': 'SEC', 'FUEL PRED': 'FUEL', 'CRU OPT': 'CRUOPT', 'DATA': 'DATA', 'MCDU MENU': 'SETTINGS' };

  // header contract: row 1 = page title + context indicator (page N/M or phase
  // name; muted when the viewed context is not the active one), row 2 = AP/MODE
  function setHeader(title, ind, muted) {
    scrTitle.textContent = title;
    scrInd.textContent = ind || '';
    scrInd.className = 'title-ind' + (muted ? ' muted' : '');
  }

  function renderSub() {
    if (!S.connected) {
      subL.textContent = 'AP: ---';
      subR.textContent = 'OFFLINE';
      subR.className = 'sub-right offline';
      return;
    }
    subR.className = 'sub-right';
    var snap = S.snap;
    subL.textContent = 'AP: ' + (snap.ap_state || S.statusline || '---');
    subR.textContent = 'MODE ' + String(snap.ap_mode || '---').toUpperCase();
  }

  function renderConn() {
    connDot.className = 'dot ' + (S.connected ? 'on' : 'off');
    connLabel.textContent = S.connected ? 'CONNECTED' : 'OFFLINE';
  }

  // annunciator LEDs: PROG = assist engaged; FUEL PRED = fuel status.
  // Fuel status is derived on the client from fuel_percent until the backend
  // fuel-state enum arrives (Phase 7.3.2): <10% critical, <25% warning.
  function renderLeds() {
    var engaged = isOn('fsd') || isOn('sc');
    ledProg.className = 'fk-led' + (engaged ? ' led-g' : '');
    // FUEL PRED LED follows the backend fuel_status enum; unknown/offline = dark
    var map = { normal: ' led-g', warning: ' led-y', critical: ' led-r' };
    var cls = S.connected ? (map[S.snap.fuel_status] || '') : '';
    ledFuel.className = 'fk-led' + cls;
  }

  function render() {
    core.className = 'core page-' + S.page.toLowerCase();
    renderConn();
    renderSub();
    renderLeds();

    if (S.page === 'PROG') renderPROG();
    else if (S.page === 'ROUTE') renderROUTE();
    else if (S.page === 'FUEL') renderFUEL();
    else if (S.page === 'FUEL_SEL') renderFUELSEL();
    else if (S.page === 'TUNING') renderTUNING();
    else if (S.page === 'DIR') renderDIR();
    else if (S.page === 'SEC') renderSEC();
    else if (S.page === 'SECLIST') renderSECLIST();
    else if (S.page === 'CRUOPT') renderCRUOPT();
    else if (S.page === 'SYSINFO') renderSYSINFO();
    else if (S.page === 'DATA') renderDATA();
    else if (S.page === 'SETTINGS') renderSETTINGS();
    else if (S.page === 'OPTIONS') renderOPTIONS();
    else if (S.page === 'CFG') renderCFG();
    else if (S.page === 'MAINT') renderMAINT();
    else if (S.page === 'CALIB') renderCALIB();
    else if (S.page === 'CALIBREG') renderCALIBREG();
    else renderINIT();

    // show/hide curve panel
    if (S.page !== 'TUNING') hideCurvePanel();

    // highlight active function key (sub-pages light their parent key)
    var pageKey = (S.page === 'FUEL_SEL') ? 'FUEL' : (S.page === 'SYSINFO') ? 'ROUTE' :
      (S.page === 'SECLIST') ? 'SEC' :
      (S.page === 'OPTIONS' || S.page === 'CFG' || S.page === 'MAINT' || S.page === 'TUNING' ||
       S.page === 'CALIB' || S.page === 'CALIBREG') ? 'SETTINGS' : S.page;
    fkEls.forEach(function (b) {
      var key = b.getAttribute('data-key');
      b.classList.toggle('fk-active', PAGE_FOR_KEY[key] === pageKey);
    });

    renderScratch();
  }

  function routeMaxScroll() {
    return Math.max(0, routeItemCount() - ROUTE_WIN);
  }
  function clampRoutePage() {
    var m = routeMaxScroll();
    if (S.routePage > m) S.routePage = m;
    if (S.routePage < 0) S.routePage = 0;
  }

  // ---- navigation ----
  function setPage(p) {
    if (S.page === p) return;
    if (S.page === 'TUNING') hideCurvePanel();
    if (S.page === 'SEC' && S.secConfirm) {
      if (secConfirmT) { clearTimeout(secConfirmT); secConfirmT = null; }
      S.secConfirm = false;
    }
    if (S.page === 'CALIB' && (S.calibResetConfirm || S.calibTargetConfirm)) {
      if (calibResetConfirmT) { clearTimeout(calibResetConfirmT); calibResetConfirmT = null; }
      if (calibTargetConfirmT) { clearTimeout(calibTargetConfirmT); calibTargetConfirmT = null; }
      S.calibResetConfirm = false;
      S.calibTargetConfirm = false;
    }
    S.page = p;
    if (p === 'ROUTE' || p === 'INIT' || p === 'DATA' || p === 'SEC') { S.routeLoc = S.snap.location || null; sendRaw({ cmd: 'route.get' }); }
    if (p === 'SEC') { sendRaw({ cmd: 'sec.get' }); sendRaw({ cmd: 'exec.get' }); }
    if (p === 'TUNING') S.curveNeedsLoad = true;
    if (p === 'CALIB') sendRaw({ cmd: 'calibration.get' });
    render();
  }

  function fkPress(key) {
    var p = PAGE_FOR_KEY[key];
    if (p) setPage(p);
    else flash('PAGE INOP', 1500);
  }

  function slew(dir) {
    if (S.page === 'PROG') {
      var idx = PHASES.indexOf(viewedPhase());
      if (dir === 'l') { S.phase = PHASES[(idx + PHASES.length - 1) % PHASES.length]; render(); }
      else if (dir === 'r') { S.phase = PHASES[(idx + 1) % PHASES.length]; render(); }
      else if (dir === 'd') { S.phase = null; render(); }  // return to the active phase
      return;
    }
    if (S.page === 'ROUTE') {
      // F-PLN scrolls as one list: up/down by a line, left/right by a window
      var m = routeMaxScroll();
      if (dir === 'u') S.routePage = Math.max(0, S.routePage - 1);
      else if (dir === 'd') S.routePage = Math.min(m, S.routePage + 1);
      else if (dir === 'l') S.routePage = Math.max(0, S.routePage - ROUTE_WIN);
      else if (dir === 'r') S.routePage = Math.min(m, S.routePage + ROUTE_WIN);
      render();
    } else if (S.page === 'TUNING') {
      if (dir === 'l') curveSelPrev();
      else if (dir === 'r') curveSelNext();
    } else if (S.page === 'CFG') {
      // CONFIG pages cycle 1..5, same as R6 NEXT PAGE> (parity-gap ext. 7.4б)
      if (dir === 'l') { S.cfgPage = (S.cfgPage + 4) % 5; render(); }
      else if (dir === 'r') { S.cfgPage = (S.cfgPage + 1) % 5; render(); }
    } else if (S.page === 'CALIB') {
      // CALIB list scrolls like F-PLN: up/down by a line, left/right by a window
      var cm = calibMaxScroll();
      if (dir === 'u') S.calibPage = Math.max(0, S.calibPage - 1);
      else if (dir === 'd') S.calibPage = Math.min(cm, S.calibPage + 1);
      else if (dir === 'l') S.calibPage = Math.max(0, S.calibPage - CALIB_WIN);
      else if (dir === 'r') S.calibPage = Math.min(cm, S.calibPage + CALIB_WIN);
      render();
    } else if (S.page === 'SECLIST') {
      // SECLIST scrolls like F-PLN: up/down by a line, left/right by a window
      var sm = secListMaxScroll();
      if (dir === 'u') S.secListPage = Math.max(0, S.secListPage - 1);
      else if (dir === 'd') S.secListPage = Math.min(sm, S.secListPage + 1);
      else if (dir === 'l') S.secListPage = Math.max(0, S.secListPage - SECLIST_WIN);
      else if (dir === 'r') S.secListPage = Math.min(sm, S.secListPage + SECLIST_WIN);
      render();
    }
  }

  // ---- wiring ----
  document.querySelectorAll('.lsk').forEach(function (b) {
    b.addEventListener('click', function () {
      doLSK(b.getAttribute('data-side'), parseInt(b.getAttribute('data-idx'), 10));
    });
  });

  rows.forEach(function (r, i) {
    r.lval.addEventListener('click', function () { doLSK('L', i); });
    r.rval.addEventListener('click', function () { doLSK('R', i); });
  });

  var fkEls = [].slice.call(document.querySelectorAll('.fk[data-key]'));
  fkEls.forEach(function (b) {
    b.addEventListener('click', function () { fkPress(b.getAttribute('data-key')); });
  });

  document.querySelectorAll('[data-slew]').forEach(function (b) {
    b.addEventListener('click', function () {
      var d = b.getAttribute('data-slew');
      if (d === 'clr') {           // ex-AIRPORT: dedicated scratchpad clear
        S.scratch = '';
        renderScratch();
      } else slew(d);
    });
  });

  // ---- on-screen keypad (KBD toggle in the slew row) ----
  // Keys write through spInput + an 'input' event so the same charset filter
  // and length cap apply as for real typing; toggle state survives reloads.
  var kbdPanel = $('kbdPanel');
  var kbdToggle = $('kbdToggle');
  function kbdShow(on) {
    if (on) kbdPanel.removeAttribute('hidden');
    else kbdPanel.setAttribute('hidden', '');
    kbdToggle.classList.toggle('fk-active', on);
    try { localStorage.setItem('mcduKbd', on ? '1' : '0'); } catch (e) { /* private mode */ }
  }
  kbdToggle.addEventListener('click', function () { kbdShow(kbdPanel.hasAttribute('hidden')); });
  try { if (localStorage.getItem('mcduKbd') === '1') kbdShow(true); } catch (e) { /* private mode */ }
  kbdPanel.addEventListener('click', function (e) {
    var t = e.target;
    if (!t || !t.getAttribute) return;
    if (S.flash) return;                       // don't type over an active flash
    if (t.getAttribute('data-bs')) {
      spInput.value = S.scratch.slice(0, -1);
    } else {
      var ch = t.getAttribute('data-ch');
      if (ch === null) return;
      spInput.value = S.scratch + ch;
    }
    spInput.dispatchEvent(new Event('input'));
  });

  // STOP ALL: guarded hardware button (outside the LSK grid).
  // Tap the lid to lift it, then press the red button; the lid re-closes on
  // a second tap, on any click elsewhere, or automatically after 4 s.
  var estopEl = $('estop');
  var estopBtn = $('estopBtn');
  var estopCover = $('estopCover');
  var estopT = null;
  function estopDisarm() {
    estopEl.classList.remove('armed');
    if (estopT) { clearTimeout(estopT); estopT = null; }
  }
  estopCover.addEventListener('click', function () {
    if (estopEl.classList.contains('armed')) { estopDisarm(); return; }
    estopEl.classList.add('armed');
    if (estopT) clearTimeout(estopT);
    estopT = setTimeout(estopDisarm, 4000);
  });
  estopBtn.addEventListener('click', function () {
    if (!estopEl.classList.contains('armed')) return;
    stopAllPress();
    estopDisarm();
  });
  document.addEventListener('click', function (ev) {
    if (estopEl.classList.contains('armed') && !estopEl.contains(ev.target)) estopDisarm();
  });

  // physical keyboard (scratchpad input; on-screen keypads removed by design)
  window.addEventListener('keydown', function (e) {
    var tag = e.target && e.target.tagName;
    if (tag === 'INPUT' || tag === 'TEXTAREA') return;
    var k = e.key;
    if (k === 'Backspace') {
      e.preventDefault();
      if (!e.repeat) { clr(); clrHoldStart(); }
    }
    else if (k === 'Escape') { if (S.flash) clearFlashNow(); S.scratch = ''; renderScratch(); }
    else if (k === ' ') { e.preventDefault(); appendChar(' '); }
    else if (physicalLatin(e) !== null) { appendChar(physicalLatin(e)); }
    else if (k && k.length === 1 && /[a-zA-Z0-9./+-]/.test(k)) { appendChar(k.toUpperCase()); }
  });
  window.addEventListener('keyup', function (e) {
    if (e.key === 'Backspace') clrHoldEnd();
  });

  // ---- boot ----
  render();
  connect();
})();
