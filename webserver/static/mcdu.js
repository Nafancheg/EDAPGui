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
  var spText = $('spText');
  var logView = $('logView');
  var connDot = $('connDot');
  var connLabel = $('connLabel');

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
    page: 'INIT',
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
    logStick: true
  };

  // actions[side][idx] = { press:fn, input:fn } or null. Rebuilt every render.
  var actions = { L: [null, null, null, null, null, null], R: [null, null, null, null, null, null] };

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
    if (!S.connected) { flash('NOT CONNECTED', 2000); return false; }
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
        appendLog('[error] ' + (msg.text || ''), false, true);
        break;
      case 'event':
        appendLog('[' + (msg.tag || 'event') + '] ' + bodyToStr(msg.body), false, false);
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

    if (S.page === 'LOG' && S.logStick) logView.scrollTop = logView.scrollHeight;
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

  function toggleSign() {
    if (S.flash) clearFlashNow();
    if (S.scratch.charAt(0) === '-') S.scratch = S.scratch.slice(1);
    else S.scratch = '-' + S.scratch;
    renderScratch();
  }

  function clr() {
    if (S.flash) { clearFlashNow(); return; }
    if (S.scratch) S.scratch = S.scratch.slice(0, -1);
    renderScratch();
  }

  function renderScratch() {
    if (S.flash) {
      spText.textContent = S.flash;
      scratchEl.className = 'scratchpad scol flash';
    } else {
      spText.textContent = S.scratch;
      scratchEl.className = 'scratchpad scol';
    }
  }

  // ---- LSK dispatch ----
  function doLSK(side, i) {
    var a = actions[side][i];
    if (S.scratch !== '') {
      if (a && a.input) {
        var res = a.input(S.scratch);
        if (res === true) { S.scratch = ''; renderScratch(); render(); }
        else if (res === 'keep') { /* accepted, keep scratch */ }
        else { flash('NOT ALLOWED', 1500); }
      } else {
        flash('NOT ALLOWED', 1500);
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

  function throttlePress() {
    if (!ensureConn()) return;
    var order = [0, 50, 100];
    var next = (S.throttle === null) ? 0 : order[(order.indexOf(S.throttle) + 1) % 3];
    if (sendRaw({ cmd: 'throttle.set', level: next })) S.throttle = next;
    render();
  }
  function throttleInput(v) {
    var n = v.trim();
    if (n !== '0' && n !== '50' && n !== '100') return false;
    if (!ensureConn()) return 'keep';
    var lvl = parseInt(n, 10);
    if (sendRaw({ cmd: 'throttle.set', level: lvl })) { S.throttle = lvl; render(); return true; }
    return 'keep';
  }

  function stopAllPress() {
    if (!ensureConn()) return;
    sendRaw({ cmd: 'assist.stop_all' });
    S.assist.fsd = false; S.assist.sc = false;
    render();
  }
  function stopAllInput() {
    if (!ensureConn()) return 'keep';
    sendRaw({ cmd: 'assist.stop_all' });
    S.assist.fsd = false; S.assist.sc = false;
    render();
    return 'keep';
  }

  function refreshRoute() {
    if (ensureConn()) sendRaw({ cmd: 'route.get' });
  }

  function routeInfo(it) {
    var name = it.system || '?';
    var msg = name + ': ' + (it.star_class || '?') + ' ' + (it.scoopable ? 'SCOOPABLE' : 'NOT SCOOPABLE');
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
  function renderINIT() {
    scrTitle.textContent = 'EDAUTOPILOT';
    scrInd.textContent = 'INIT';
    clearActions();

    var snap = S.snap;
    var fsdOn = isOn('fsd'), scOn = isOn('sc');
    var thr = (S.throttle === null) ? '---' : S.throttle + '%';

    fill(0, {
      lh: 'FSD ROUTE', lv: fsdOn ? '<ON' : '<OFF', lvs: fsdOn ? 's-on' : 's-off',
      rh: 'THROTTLE', rv: thr, rvs: (S.throttle === null) ? 's-muted' : 's-cyan'
    });
    actions.L[0] = { press: fsdToggle, input: function () { return false; } };
    actions.R[0] = { press: throttlePress, input: throttleInput };

    var f = fuelCell(snap.fuel_percent);
    fill(1, {
      lh: 'SUPERCRUISE', lv: scOn ? '<ON' : '<OFF', lvs: scOn ? 's-on' : 's-off',
      rh: 'FUEL', rv: f.t, rvs: f.s
    });
    actions.L[1] = { press: scToggle, input: function () { return false; } };

    fill(2, {
      lh: 'FAST TRAVEL', lv: S.fastTravel ? '<ON' : '<OFF', lvs: S.fastTravel ? 's-on' : 's-off',
      rh: 'SHIP', rv: snap.ship_status ? String(snap.ship_status) : '---', rvs: 's-normal'
    });
    actions.L[2] = { press: ftToggle, input: function () { return false; } };

    var starVal = '', starHead = '', starState = 's-normal';
    if (snap.star_class) {
      starHead = 'STAR';
      starVal = snap.star_class + ' ' + (snap.scoopable ? 'SCOOP' : '✗');
      starState = snap.scoopable ? 's-on' : 's-alert';
    }
    fill(3, {
      lh: 'SYSTEM', lv: snap.location ? String(snap.location) : '---', lvs: 's-normal',
      rh: starHead, rv: starVal, rvs: starState
    });

    var jc = (snap.jump_cnt === null || snap.jump_cnt === undefined) ? '-' : snap.jump_cnt;
    var tj = (snap.total_jumps === null || snap.total_jumps === undefined) ? '-' : snap.total_jumps;
    fill(4, {
      lh: 'JUMPS', lv: jc + '/' + tj, lvs: 's-normal',
      rh: 'ETA', rv: snap.eta ? String(snap.eta) : '---', rvs: 's-normal'
    });

    fill(5, {
      lh: 'TARGET', lv: snap.target ? String(snap.target) : '---', lvs: 's-normal',
      rh: 'STOP ALL', rv: 'STOP ALL>', rvs: 's-alert'
    });
    actions.R[5] = { press: stopAllPress, input: stopAllInput };
  }

  function renderROUTE() {
    scrTitle.textContent = 'F-PLN';
    clearActions();
    for (var i = 0; i < 6; i++) clearRow(i);

    var sys = S.route.systems || [];
    if (!S.route.active || sys.length === 0) {
      scrInd.textContent = 'ROUTE 1/1 →';
      fill(2, { lv: 'NO ACTIVE ROUTE', lvs: 's-muted', center: true });
      fill(3, { lv: 'PLOT ROUTE IN GALAXY MAP', lvs: 's-hint', center: true });
      fill(5, { rh: '', rv: 'REFRESH>', rvs: 's-cyan' });
      actions.R[5] = { press: refreshRoute, input: function () { return false; } };
      return;
    }

    var pages = routePages();
    if (S.routePage > pages - 1) S.routePage = pages - 1;
    if (S.routePage < 0) S.routePage = 0;
    scrInd.textContent = 'ROUTE ' + (S.routePage + 1) + '/' + pages + ' →';

    var start = S.routePage * 6;
    var loc = S.snap.location ? String(S.snap.location).toLowerCase() : null;
    var filled = 0;

    for (var r = 0; r < 6; r++) {
      var gi = start + r;
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
      (function (item) {
        var act = { press: function () { routeInfo(item); }, input: function () { return false; } };
        actions.L[filled] = act; actions.R[filled] = act;
      })(it);
      filled++;
    }

    // DEST / JUMPS footer in the first trailing empty row (if the page is not full)
    if (filled < 6) {
      fill(filled, {
        lh: 'TOTAL', lv: (sys.length - 1) + ' JUMPS', lvs: 's-cyan',
        rh: 'DEST', rv: S.route.destination ? String(S.route.destination) : '?', rvs: 's-normal'
      });
    }
  }

  function renderLOG() {
    scrTitle.textContent = 'DATA LOG';
    scrInd.textContent = 'LOG';
    clearActions();
    for (var i = 0; i < 6; i++) clearRow(i);
  }

  function renderFUEL() {
    scrTitle.textContent = 'FUEL PRED';
    scrInd.textContent = 'FUEL';
    clearActions();
    for (var i = 0; i < 6; i++) clearRow(i);

    var snap = S.snap;
    var f = fuelCell(snap.fuel_percent);
    fill(0, { lh: 'FUEL ONBOARD', lv: f.t, lvs: f.s });

    if (snap.star_class) {
      fill(1, {
        lh: 'CURRENT STAR', lv: String(snap.star_class), lvs: 's-normal',
        rv: snap.scoopable ? 'SCOOP' : '✗', rvs: snap.scoopable ? 's-on' : 's-alert'
      });
    } else {
      fill(1, { lh: 'CURRENT STAR', lv: '---', lvs: 's-muted' });
    }

    fill(5, { lv: 'FUEL PREDICTION AWAITS FUELSTATE (PHASE 3)', lvs: 's-msg', center: true });
  }

  // ---- top-level render ----
  var PAGE_FOR_KEY = { 'INIT': 'INIT', 'F-PLN': 'ROUTE', 'FUEL PRED': 'FUEL', 'DATA': 'LOG' };

  function renderSub() {
    var snap = S.snap;
    subL.textContent = 'AP: ' + (snap.ap_state || S.statusline || '---');
    subR.textContent = 'MODE ' + String(snap.ap_mode || '---').toUpperCase();
  }

  function renderConn() {
    connDot.className = 'dot ' + (S.connected ? 'on' : 'off');
    connLabel.textContent = S.connected ? 'CONNECTED' : 'OFFLINE';
  }

  function render() {
    core.className = 'core page-' + S.page.toLowerCase();
    renderConn();
    renderSub();

    if (S.page === 'ROUTE') renderROUTE();
    else if (S.page === 'LOG') renderLOG();
    else if (S.page === 'FUEL') renderFUEL();
    else renderINIT();

    // highlight active function key
    fkEls.forEach(function (b) {
      var p = PAGE_FOR_KEY[b.getAttribute('data-key')];
      b.classList.toggle('fk-active', p === S.page);
    });

    renderScratch();
  }

  function routePages() {
    return Math.max(1, Math.ceil((S.route.systems || []).length / 6));
  }
  function clampRoutePage() {
    var p = routePages();
    if (S.routePage > p - 1) S.routePage = p - 1;
    if (S.routePage < 0) S.routePage = 0;
  }

  // ---- navigation ----
  function setPage(p) {
    if (S.page === p) return;
    S.page = p;
    if (p === 'ROUTE') { S.routeLoc = S.snap.location || null; sendRaw({ cmd: 'route.get' }); }
    render();
    if (p === 'LOG') { S.logStick = true; logView.scrollTop = logView.scrollHeight; }
  }

  function fkPress(key) {
    var p = PAGE_FOR_KEY[key];
    if (p) setPage(p);
    else flash('PAGE INOP', 1500);
  }

  function slew(dir) {
    if (S.page === 'ROUTE') {
      if (dir === 'l' || dir === 'u') { S.routePage = Math.max(0, S.routePage - 1); render(); }
      else if (dir === 'r' || dir === 'd') { S.routePage = Math.min(routePages() - 1, S.routePage + 1); render(); }
    } else if (S.page === 'LOG') {
      if (dir === 'u') logView.scrollTop -= 60;
      else if (dir === 'd') logView.scrollTop += 60;
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

  document.querySelectorAll('.key').forEach(function (b) {
    b.addEventListener('click', function () {
      var ch = b.getAttribute('data-ch');
      var act = b.getAttribute('data-act');
      if (ch !== null) appendChar(ch);
      else if (act === 'sign') toggleSign();
      else if (act === 'ovfy') flash('PAGE INOP', 1500);
      else if (act === 'clr') clr();
    });
  });

  // physical keyboard (desktop debugging)
  window.addEventListener('keydown', function (e) {
    var tag = e.target && e.target.tagName;
    if (tag === 'INPUT' || tag === 'TEXTAREA') return;
    var k = e.key;
    if (k === 'Backspace') { e.preventDefault(); clr(); }
    else if (k === 'Escape') { if (S.flash) clearFlashNow(); S.scratch = ''; renderScratch(); }
    else if (k === ' ') { e.preventDefault(); appendChar(' '); }
    else if (k && k.length === 1 && /[a-zA-Z0-9./]/.test(k)) { appendChar(k.toUpperCase()); }
  });

  // ---- boot ----
  render();
  connect();
})();
