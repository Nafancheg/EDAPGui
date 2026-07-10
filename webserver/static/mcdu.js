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
    routePage: 0,
    statusline: '',
    routeLoc: null,          // location last used to refresh the route
    flash: null,             // transient scratchpad message
    flashSaved: '',
    logStick: true,
    curveAxis: 'RollRate',   // 'RollRate' | 'PitchRate' | 'YawRate'
    curveEditor: null,       // McduCurves instance
    curveSpeed: null,        // speed demand last received with curve data
    curveNeedsLoad: false,   // true when we should load curve data from server
    curvePending: false      // a curve.get is in flight — don't re-send on render ticks
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
          // stop re-requesting every render tick; re-entering PERF retries
          S.curvePending = false;
          S.curveNeedsLoad = false;
        }
        appendLog('[error] ' + (msg.text || ''), false, true);
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
        } else if (!S.curveEditor && S.page === 'PERF') {
          S.curveNeedsLoad = true;  // will be consumed when editor is built
          renderPERF();
        }
        break;
      case 'curve_saved':
        flash('CURVE UPDATED', 1500);
        break;
      case 'ship_saved':
        flash(msg.ok ? 'SAVED TO DISK' : 'SAVE FAILED', 1800);
        if (!msg.ok && msg.text) appendLog('[config] ' + msg.text, false, true);
        break;
      default:
        break;
    }
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
    var v = spInput.value.toUpperCase().replace(/[^A-Z0-9 ./+-]/g, '').slice(0, 22);
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
    if (S.page === 'PERF') S.curveNeedsLoad = true;
    render();
  }
  function throttleInput(v) {
    var n = v.trim();
    if (n !== '0' && n !== '50' && n !== '100') return false;
    if (!ensureConn()) return 'keep';
    var lvl = parseInt(n, 10);
    if (sendRaw({ cmd: 'throttle.set', level: lvl })) { S.throttle = lvl; if (S.page === 'PERF') S.curveNeedsLoad = true; render(); return true; }
    return 'keep';
  }

  function stopAllPress() {
    if (!ensureConn()) return;
    sendRaw({ cmd: 'assist.stop_all' });
    S.assist.fsd = false; S.assist.sc = false;
    render();
  }

  // per-system info to the scratchpad (spec §3.3): NN <system> · <class> · SCOOP · n.n LY
  function routeInfo(it, gi) {
    var num = pad2(gi + 1);
    var cls = it.star_class || '?';
    var scoop = it.scoopable ? 'SCOOP' : 'NO SCOOP';
    var dist = (gi === 0) ? 'ORIGIN'
      : (it.dist_ly === null || it.dist_ly === undefined ? '-- LY' : Number(it.dist_ly).toFixed(1) + ' LY');
    var msg = num + ' ' + (it.system || '?') + ' · ' + cls + ' · ' + scoop + ' · ' + dist;
    appendLog(msg, false, false);
    flash(msg, 1500);
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
    fill(4, { lv: '<FINAL DESCENT', lvs: 's-muted', rh: 'TGT COORDS', rv: '----/----', rvs: 's-cyan' });
    for (var i = 0; i < 5; i++) {
      actions.L[i] = { press: function () { flash('NOT AVAILABLE', 1500); }, input: null };
    }
    actions.R[4] = { press: null, input: lndCoordsInput };
  }

  // LND R5: lat/lon entry per spec §3.1 — two decimals separated by '/',
  // sign and fraction optional, lat in [-90,90], lon in [-180,180]
  function lndCoordsInput(v) {
    var m = /^([+-]?\d+(?:\.\d+)?)\/([+-]?\d+(?:\.\d+)?)$/.exec(v.trim());
    if (!m) return false;
    var lat = parseFloat(m[1]), lon = parseFloat(m[2]);
    if (lat < -90 || lat > 90 || lon < -180 || lon > 180) return false;
    flash('NOT AVAILABLE', 1500);   // valid entry; guidance backend arrives in Phase 8.2
    return 'keep';
  }

  function renderPhaseCRUISE() {
    var snap = S.snap;
    var fsdOn = isOn('fsd');

    var noJumps = (snap.jump_cnt === null || snap.jump_cnt === undefined)
      && (snap.total_jumps === null || snap.total_jumps === undefined);
    var jc = (snap.jump_cnt === null || snap.jump_cnt === undefined) ? '-' : snap.jump_cnt;
    var tj = (snap.total_jumps === null || snap.total_jumps === undefined) ? '-' : snap.total_jumps;
    fill(0, {
      lv: fsdOn ? '<FSD ROUTE ON' : '<FSD ROUTE OFF', lvs: fsdOn ? 's-on' : 's-off',
      rh: 'JUMPS', rv: noJumps ? '---' : jc + '/' + tj, rvs: noJumps ? 's-muted' : 's-normal'
    });
    actions.L[0] = { press: fsdToggle, input: null };

    fill(1, {
      lv: '<FSS SCAN', lvs: 's-normal',
      rh: 'ETA', rv: snap.eta ? String(snap.eta) : '---', rvs: snap.eta ? 's-normal' : 's-muted'
    });
    actions.L[1] = { press: function () { sendAction('fss_scan'); }, input: null };

    fill(2, {
      lv: '<HONK', lvs: 's-normal',
      rh: 'TARGET', rv: snap.target ? String(snap.target) : '---', rvs: snap.target ? 's-normal' : 's-muted'
    });
    actions.L[2] = { press: function () { sendAction('honk'); }, input: null };

    var elwOn = !!S.cfg.ElwScannerEnable;
    var hasDist = snap.total_dist_jumped !== null && snap.total_dist_jumped !== undefined;
    var distVal = hasDist
      ? Number(snap.total_dist_jumped).toFixed(1) + ' LY · ' + (snap.jumps_remaining ?? '-') + ' LEFT'
      : '---';
    fill(3, {
      lv: elwOn ? '<ELW SCAN ON' : '<ELW SCAN OFF', lvs: elwOn ? 's-on' : 's-off',
      rh: 'DIST', rv: distVal, rvs: hasDist ? 's-normal' : 's-muted'
    });
    actions.L[3] = { press: elwToggle, input: null };

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
    fill(2, { lv: '<PERF', lvs: 's-normal',
      rh: 'SHIP', rv: snap.ship_status ? String(snap.ship_status) : '---',
      rvs: snap.ship_status ? 's-normal' : 's-muted' });
    actions.L[2] = { press: function () { setPage('PERF'); }, input: null };
    fill(3, { lv: '<DATA', lvs: 's-muted', rh: 'FUEL', rv: f.t, rvs: f.s });
    actions.L[3] = { press: function () { flash('PAGE INOP', 1500); }, input: null };
    fill(4, { lv: '<SETTINGS', lvs: 's-muted',
      rh: 'LINK', rv: S.connected ? 'CONNECTED' : 'OFFLINE',
      rvs: S.connected ? 's-on' : 's-alert' });
    actions.L[4] = { press: function () { flash('PAGE INOP', 1500); }, input: null };
    fill(5, { rv: 'PROG>', rvs: 's-cyan' });
    actions.R[5] = { press: function () { setPage('PROG'); }, input: null };
  }

  function renderDIR() {
    setHeader('DIR', 'DIRECT-TO');
    clearActions();
    for (var i = 0; i < 6; i++) clearRow(i);
    fill(0, { lv: '<NEAREST SCOOPABLE', lvs: 's-muted',
      rh: 'DIRECT TO', rv: '________', rvs: 's-cyan' });
    actions.L[0] = { press: function () { flash('NOT AVAILABLE', 1500); }, input: null };
    actions.R[0] = { press: null, input: dirTargetInput };
    fill(1, { lv: '<NEAREST SYSTEM', lvs: 's-muted',
      rh: 'CAND', rv: '---', rvs: 's-muted' });
    actions.L[1] = { press: function () { flash('NOT AVAILABLE', 1500); }, input: null };
    fill(3, { lv: 'DIRECT-TO PLOTTER', lvs: 's-muted', center: true });
    fill(4, { lv: 'AWAITS BACKEND (PHASE 8.1)', lvs: 's-hint', center: true });
  }

  function dirTargetInput(v) {
    if (!v.trim()) return false;
    flash('NOT AVAILABLE', 1500);   // plotter backend arrives in Phase 8.1
    return 'keep';
  }

  // F-PLN · ACTIVE ROUTE, spec §3.3 + Замечание 12: the whole plan is one
  // continuous list scrolled with the vertical slew (like a real aircraft
  // F-PLN — no NEXT PAGE). Rows 1-4 are the scroll window (S.routePage = top
  // line index); fixed row 5 = FAST TRAVEL + DEST; row 6 = TOTAL jumps · LY.
  // Only the left LSK of a list row acts (per-system info to scratchpad).
  var ROUTE_WIN = 4;

  function routeTotalLy(sys) {
    var t = 0;
    for (var i = 0; i < sys.length; i++) {
      var d = Number(sys[i].dist_ly);
      if (!isNaN(d)) t += d;
    }
    return t;
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

    var maxScroll = Math.max(0, sys.length - ROUTE_WIN);
    if (S.routePage > maxScroll) S.routePage = maxScroll;
    if (S.routePage < 0) S.routePage = 0;
    var top = S.routePage;
    var bottom = Math.min(top + ROUTE_WIN, sys.length);
    setHeader('F-PLN', 'ROUTE ' + (top + 1) + '-' + bottom + '/' + sys.length + ' ↕');

    var loc = S.snap.location ? String(S.snap.location).toLowerCase() : null;

    for (var r = 0; r < ROUTE_WIN; r++) {
      var gi = top + r;
      if (gi >= sys.length) continue;
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
      (function (item, idx) {
        actions.L[r] = { press: function () { routeInfo(item, idx); }, input: null };
      })(it, gi);
    }

    // fixed row 5: FAST TRAVEL toggle (left) + DEST (right)
    fill(4, {
      lv: S.fastTravel ? '<FAST TRAVEL  ON' : '<FAST TRAVEL  OFF', lvs: S.fastTravel ? 's-on' : 's-off',
      rh: 'DEST', rv: S.route.destination ? String(S.route.destination) : '---',
      rvs: S.route.destination ? 's-normal' : 's-muted'
    });
    actions.L[4] = { press: ftToggle, input: null };

    // row 6: whole-plan total — jumps and light-years (display only)
    fill(5, {
      rh: 'TOTAL', rv: (sys.length - 1) + ' JMP · ' + routeTotalLy(sys).toFixed(1) + ' LY', rvs: 's-cyan'
    });
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

  function renderPERF() {
    setHeader('RPY CURVES', 'PERF');
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

    // Row 2: hint
    fill(2, { lv: 'DRAG PTS - DBL-CLICK ADDS', lvs: 's-hint', center: true });

    // Row 3: select prev/next point
    fill(3, {
      lh: '', lv: 'SEL PT<', lvs: 's-cyan',
      rh: '', rv: '>NEXT PT', rvs: 's-cyan'
    });
    actions.L[3] = { press: curveSelPrev, input: function () { return false; } };
    actions.R[3] = { press: curveSelNext, input: function () { return false; } };

    // Row 4: selected point info / set value from scratchpad
    fill(4, {
      lh: 'SET VAL',
      lv: curveSelLabel(),
      lvs: 's-normal',
      rh: '', rv: 'SAVE>', rvs: 's-on'
    });
    actions.L[4] = { press: function () {}, input: curveSetValue };
    actions.R[4] = { press: curveSave, input: function () { return 'keep'; } };

    // Row 5: save to disk / delete selected point
    fill(5, {
      lv: '<SAVE TO DISK', lvs: 's-on',
      rv: 'DEL PT>', rvs: 's-cyan'
    });
    actions.L[5] = { press: curveSaveAll, input: function () { return 'keep'; } };
    actions.R[5] = { press: curveDelPoint, input: function () { return false; } };

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
    renderPERF();
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
    renderPERF();
  }

  function curveSelNext() {
    if (!S.curveEditor) return;
    var idx = S.curveEditor.selectedIndex();
    S.curveEditor.selectIndex(idx + 1);
    renderPERF();
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
    renderPERF();
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
    renderPERF();
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
  var PAGE_FOR_KEY = { 'DIR': 'DIR', 'INIT': 'INIT', 'PROG': 'PROG', 'F-PLN': 'ROUTE', 'FUEL PRED': 'FUEL', 'PERF': 'PERF' };

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
    else if (S.page === 'PERF') renderPERF();
    else if (S.page === 'DIR') renderDIR();
    else renderINIT();

    // show/hide curve panel
    if (S.page !== 'PERF') hideCurvePanel();

    // highlight active function key (sub-pages light their parent key)
    var pageKey = (S.page === 'FUEL_SEL') ? 'FUEL' : S.page;
    fkEls.forEach(function (b) {
      var key = b.getAttribute('data-key');
      b.classList.toggle('fk-active', PAGE_FOR_KEY[key] === pageKey);
    });

    renderScratch();
  }

  function routeMaxScroll() {
    return Math.max(0, (S.route.systems || []).length - ROUTE_WIN);
  }
  function clampRoutePage() {
    var m = routeMaxScroll();
    if (S.routePage > m) S.routePage = m;
    if (S.routePage < 0) S.routePage = 0;
  }

  // ---- navigation ----
  function setPage(p) {
    if (S.page === p) return;
    if (S.page === 'PERF') hideCurvePanel();
    S.page = p;
    if (p === 'ROUTE' || p === 'INIT') { S.routeLoc = S.snap.location || null; sendRaw({ cmd: 'route.get' }); }
    if (p === 'PERF') S.curveNeedsLoad = true;
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
    } else if (S.page === 'PERF') {
      if (dir === 'l') curveSelPrev();
      else if (dir === 'r') curveSelNext();
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
      if (d === 'airport') flash('PAGE INOP', 1500);
      else slew(d);
    });
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
