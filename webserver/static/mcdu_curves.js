/* McduCurves — RPY curve editor for ED Autopilot MCDU.
 * Single classic script, no dependencies. Renders an SVG graph in MCDU style.
 *
 * API:
 *   var editor = McduCurves.mount(container, points, opts);
 *     container  – DOM element
 *     points     – { "0.5": 6.0, "1.0": 10.47, ... }  (string→float dict)
 *     opts       – { onChange, title, xLabel, yLabel }  (all optional)
 *
 *   editor.getPoints()          → { "0.5": 6.0, ... }
 *   editor.setPoints(points)    → replace curve entirely
 *   editor.setSelectedValue(y)  → set Y of selected point (from scratchpad)
 *   editor.selectIndex(i)       → select point by index (0-based)
 *   editor.selectedIndex()      → current selected index, or -1
 *   editor.addPoint(x, y)       → add a point (also: double-click empty area)
 *   editor.deleteSelected()     → remove selected point (keeps at least one)
 *   editor.destroy()            → remove SVG, unbind listeners
 */
(function () {
  'use strict';

  /* ---- MCDU palette (synced with mcdu.css) ---- */
  var C = {
    amber:      '#E8973E',
    amberGlow:  'rgba(232,151,62,0.5)',
    cyan:       '#5aa9c9',
    txt:        '#c9c9c1',
    muted:      '#9a9a90',
    dim:        '#7a7a72',
    title:      '#5f96d6',
    bg:         '#0c0c0e',
    grid:       '#1e1e24',
    pointFill:  '#E8973E',
    pointStroke:'#0c0c0e',
    selStroke:  '#5aa9c9'
  };

  /* ---- helpers ---- */
  function toFloat(v) { var n = parseFloat(v); return isNaN(n) ? 0 : n; }

  function sortedEntries(obj) {
    return Object.keys(obj)
      .map(function (k) { return [toFloat(k), toFloat(obj[k])]; })
      .sort(function (a, b) { return a[0] - b[0]; });
  }

  function strDict(entries) {
    var d = {};
    for (var i = 0; i < entries.length; i++) {
      d[String(Math.round(entries[i][0] * 10) / 10)] = Math.round(entries[i][1] * 100) / 100;
    }
    return d;
  }

  /* ---- SVG namespace ---- */
  var SVGNS = 'http://www.w3.org/2000/svg';
  function el(name, attrs) {
    var e = document.createElementNS(SVGNS, name);
    if (attrs) for (var k in attrs) e.setAttribute(k, attrs[k]);
    return e;
  }

  /* ---- constructor ---- */
  function McduCurves(container, points, opts) {
    this.container = container;
    this.opts = opts || {};
    this.entries = sortedEntries(points || {});
    this.selIdx = -1;          // selected point index, -1 = none
    this.dragIdx = -1;         // index being dragged
    this._onChange = this.opts.onChange || null;

    this.margin = { top: 34, right: 16, bottom: 30, left: 48 };

    this._build();
    this._bind();
  }

  McduCurves.prototype = {

    /* ---- build DOM ---- */
    _build: function () {
      var self = this;
      var c = this.container;
      c.innerHTML = '';

      // wrapper
      this.wrap = document.createElement('div');
      this.wrap.className = 'mcv-wrap';
      this.wrap.style.cssText = 'position:relative;width:100%;height:100%;' +
        'background:' + C.bg + ';border-radius:6px;overflow:hidden;' +
        'font-family:\'VT323\',ui-monospace,\'Consolas\',\'Courier New\',monospace;' +
        'user-select:none;-webkit-user-select:none;touch-action:none;';
      c.appendChild(this.wrap);

      // dot-matrix overlay
      var dots = document.createElement('div');
      dots.className = 'mcv-dots';
      dots.style.cssText = 'position:absolute;inset:0;pointer-events:none;z-index:2;' +
        'background-image:radial-gradient(rgba(4,5,7,.45) 1px,transparent 1.5px);' +
        'background-size:3px 3px;opacity:.6;';
      this.wrap.appendChild(dots);

      // title bar
      var titleBar = document.createElement('div');
      titleBar.className = 'mcv-title';
      titleBar.style.cssText = 'position:absolute;top:0;left:0;right:0;z-index:3;' +
        'display:flex;align-items:baseline;justify-content:space-between;' +
        'padding:8px 14px 2px;color:' + C.title + ';font-size:16px;letter-spacing:1.5px;' +
        'pointer-events:none;';
      titleBar.textContent = this.opts.title || 'RPY CURVE';
      this.titleEl = titleBar;
      this.wrap.appendChild(titleBar);

      // selected point info (top right)
      this.infoEl = document.createElement('span');
      this.infoEl.style.cssText = 'color:' + C.muted + ';font-size:13px;';
      titleBar.appendChild(this.infoEl);

      // Y label
      if (this.opts.yLabel) {
        var ylbl = document.createElement('div');
        ylbl.style.cssText = 'position:absolute;left:6px;top:50%;z-index:3;' +
          'color:' + C.dim + ';font-size:11px;letter-spacing:1px;' +
          'transform:rotate(-90deg) translateX(-50%);transform-origin:left center;' +
          'white-space:nowrap;pointer-events:none;';
        ylbl.textContent = this.opts.yLabel;
        this.wrap.appendChild(ylbl);
      }

      // X label
      if (this.opts.xLabel) {
        var xlbl = document.createElement('div');
        xlbl.style.cssText = 'position:absolute;bottom:4px;left:50%;z-index:3;' +
          'color:' + C.dim + ';font-size:11px;letter-spacing:1px;' +
          'transform:translateX(-50%);white-space:nowrap;pointer-events:none;';
        xlbl.textContent = this.opts.xLabel;
        this.wrap.appendChild(xlbl);
      }

      // SVG
      this.svg = el('svg', { width: '100%', height: '100%' });
      this.svg.style.cssText = 'position:absolute;inset:0;z-index:1;';
      this.wrap.appendChild(this.svg);

      // groups
      this.gGrid   = el('g'); this.svg.appendChild(this.gGrid);
      this.gCurve  = el('g'); this.svg.appendChild(this.gCurve);
      this.gPoints = el('g'); this.svg.appendChild(this.gPoints);
      this.gSel    = el('g'); this.svg.appendChild(this.gSel);

      this._redraw();
    },

    /* ---- coordinate mapping ---- */
    _dataExtent: function () {
      var xs = [], ys = [];
      for (var i = 0; i < this.entries.length; i++) {
        xs.push(this.entries[i][0]);
        ys.push(this.entries[i][1]);
      }
      if (xs.length === 0) { xs = [0, 1]; ys = [0, 1]; }
      var xMin = 0;
      var xMax = Math.max.apply(null, xs) * 1.15 || 1;
      var yMin = 0;
      var yMax = Math.max.apply(null, ys) * 1.15 || 1;
      // round to nice numbers
      xMax = this._nice(xMax);
      yMax = this._nice(yMax);
      return { xMin: xMin, xMax: xMax, yMin: yMin, yMax: yMax };
    },

    _nice: function (v) {
      if (v <= 0) return 1;
      var exp = Math.floor(Math.log10(v));
      var m = v / Math.pow(10, exp);
      var nice;
      if (m <= 1.5) nice = 1.5;
      else if (m <= 3) nice = 3;
      else if (m <= 5) nice = 5;
      else if (m <= 7) nice = 7;
      else nice = 10;
      return nice * Math.pow(10, exp);
    },

    _plotArea: function () {
      var w = this.wrap.clientWidth;
      var h = this.wrap.clientHeight;
      return {
        x: this.margin.left,
        y: this.margin.top,
        w: w - this.margin.left - this.margin.right,
        h: h - this.margin.top - this.margin.bottom
      };
    },

    _toSvg: function (dx, dy, extent, area) {
      return {
        x: area.x + (dx - extent.xMin) / (extent.xMax - extent.xMin) * area.w,
        y: area.y + area.h - (dy - extent.yMin) / (extent.yMax - extent.yMin) * area.h
      };
    },

    _fromSvg: function (sx, sy, extent, area) {
      return {
        x: extent.xMin + (sx - area.x) / area.w * (extent.xMax - extent.xMin),
        y: extent.yMin + (area.y + area.h - sy) / area.h * (extent.yMax - extent.yMin)
      };
    },

    /* ---- redraw ---- */
    _redraw: function () {
      var extent = this._dataExtent();
      var area = this._plotArea();

      // grid
      this.gGrid.innerHTML = '';
      this._drawGrid(extent, area);
      this._drawAxes(extent, area);

      // polyline
      this.gCurve.innerHTML = '';
      this._drawCurve(extent, area);

      // points
      this.gPoints.innerHTML = '';
      this._drawPoints(extent, area);

      // selection highlight
      this.gSel.innerHTML = '';
      if (this.selIdx >= 0 && this.selIdx < this.entries.length) {
        var pt = this._toSvg(this.entries[this.selIdx][0], this.entries[this.selIdx][1], extent, area);
        this._addSelRing(pt.x, pt.y);
      }

      this._updateInfo();
    },

    _drawGrid: function (ext, area) {
      var nTicks = 5;
      for (var i = 0; i <= nTicks; i++) {
        var v = ext.xMin + (ext.xMax - ext.xMin) * i / nTicks;
        var sx = area.x + area.w * i / nTicks;
        var line = el('line', {
          x1: sx, y1: area.y, x2: sx, y2: area.y + area.h,
          stroke: C.grid, 'stroke-width': '1', 'stroke-dasharray': '2,3'
        });
        this.gGrid.appendChild(line);

        var label = el('text', {
          x: sx, y: area.y + area.h + 16,
          fill: C.dim, 'font-size': '11', 'text-anchor': 'middle',
          'font-family': '\'IBM Plex Mono\',ui-monospace,monospace'
        });
        label.textContent = (Math.round(v * 10) / 10).toString();
        this.gGrid.appendChild(label);
      }

      for (i = 0; i <= nTicks; i++) {
        v = ext.yMin + (ext.yMax - ext.yMin) * i / nTicks;
        var sy = area.y + area.h - area.h * i / nTicks;
        line = el('line', {
          x1: area.x, y1: sy, x2: area.x + area.w, y2: sy,
          stroke: C.grid, 'stroke-width': '1', 'stroke-dasharray': '2,3'
        });
        this.gGrid.appendChild(line);

        label = el('text', {
          x: area.x - 8, y: sy + 4,
          fill: C.dim, 'font-size': '11', 'text-anchor': 'end',
          'font-family': '\'IBM Plex Mono\',ui-monospace,monospace'
        });
        label.textContent = (Math.round(v * 10) / 10).toString();
        this.gGrid.appendChild(label);
      }
    },

    _drawAxes: function (ext, area) {
      // X axis
      var xAxis = el('line', {
        x1: area.x, y1: area.y + area.h, x2: area.x + area.w, y2: area.y + area.h,
        stroke: C.amber, 'stroke-width': '1.5', opacity: '0.7'
      });
      this.gGrid.appendChild(xAxis);
      // Y axis
      var yAxis = el('line', {
        x1: area.x, y1: area.y, x2: area.x, y2: area.y + area.h,
        stroke: C.amber, 'stroke-width': '1.5', opacity: '0.7'
      });
      this.gGrid.appendChild(yAxis);
    },

    _drawCurve: function (ext, area) {
      if (this.entries.length < 2) return;
      var d = '';
      for (var i = 0; i < this.entries.length; i++) {
        var pt = this._toSvg(this.entries[i][0], this.entries[i][1], ext, area);
        d += (i === 0 ? 'M' : 'L') + pt.x.toFixed(1) + ',' + pt.y.toFixed(1) + ' ';
      }
      var path = el('path', {
        d: d, fill: 'none', stroke: C.amber, 'stroke-width': '2',
        opacity: '0.85'
      });
      this.gCurve.appendChild(path);
    },

    _drawPoints: function (ext, area) {
      for (var i = 0; i < this.entries.length; i++) {
        var pt = this._toSvg(this.entries[i][0], this.entries[i][1], ext, area);
        var circle = el('circle', {
          cx: pt.x, cy: pt.y, r: '6',
          fill: C.pointFill, stroke: C.pointStroke, 'stroke-width': '2',
          cursor: 'pointer', 'data-idx': i
        });
        circle.style.transition = 'r 0.15s';
        this.gPoints.appendChild(circle);
      }
    },

    _addSelRing: function (x, y) {
      var ring = el('circle', {
        cx: x, cy: y, r: '10',
        fill: 'none', stroke: C.selStroke, 'stroke-width': '2.5',
        opacity: '0.9'
      });
      ring.style.animation = 'mcv-pulse 1.2s ease-in-out infinite';
      this.gSel.appendChild(ring);
    },

    _updateInfo: function () {
      if (this.selIdx >= 0 && this.selIdx < this.entries.length) {
        var e = this.entries[this.selIdx];
        this.infoEl.textContent = 'Pt' + (this.selIdx + 1) + '  ' +
          e[0].toFixed(1) + '° / ' + e[1].toFixed(2);
        this.infoEl.style.color = C.cyan;
      } else {
        this.infoEl.textContent = this.entries.length + ' pts';
        this.infoEl.style.color = C.muted;
      }
    },

    /* ---- find point under event ---- */
    _findPoint: function (clientX, clientY) {
      var rect = this.svg.getBoundingClientRect();
      var sx = clientX - rect.left;
      var sy = clientY - rect.top;
      var extent = this._dataExtent();
      var area = this._plotArea();

      var bestI = -1, bestD = Infinity;
      for (var i = 0; i < this.entries.length; i++) {
        var pt = this._toSvg(this.entries[i][0], this.entries[i][1], extent, area);
        var dx = sx - pt.x, dy = sy - pt.y;
        var d = Math.sqrt(dx * dx + dy * dy);
        if (d < 14 && d < bestD) { bestD = d; bestI = i; }
      }
      return bestI;
    },

    /* ---- clamp a dragged point ---- */
    _clamp: function (idx, rawX, rawY) {
      // X must be ≥ 0.1, Y must be ≥ 0, and between neighbours in X
      var x = Math.max(0.1, Math.round(rawX * 10) / 10);
      var y = Math.max(0, Math.round(rawY * 100) / 100);

      // enforce monotonic X within neighbours (allow small overlap)
      if (idx > 0) {
        var prevX = this.entries[idx - 1][0];
        if (x < prevX + 0.1) x = prevX + 0.1;
      }
      if (idx < this.entries.length - 1) {
        var nextX = this.entries[idx + 1][0];
        if (x > nextX - 0.1) x = nextX - 0.1;
      }

      return [x, y];
    },

    /* ---- event binding ---- */
    _bind: function () {
      var self = this;

      this._onMouseDown = function (e) {
        if (e.button !== 0) return;
        var idx = self._findPoint(e.clientX, e.clientY);
        if (idx >= 0) {
          e.preventDefault();
          self.dragIdx = idx;
          self.selIdx = idx;
          self._redraw();
        } else {
          self.selIdx = -1;
          self._redraw();
        }
      };

      this._onMouseMove = function (e) {
        if (self.dragIdx < 0) return;
        e.preventDefault();
        var rect = self.svg.getBoundingClientRect();
        var sx = e.clientX - rect.left;
        var sy = e.clientY - rect.top;
        var extent = self._dataExtent();
        var area = self._plotArea();
        var data = self._fromSvg(sx, sy, extent, area);
        var clamped = self._clamp(self.dragIdx, data.x, data.y);
        self.entries[self.dragIdx] = clamped;
        self._redraw();
      };

      this._onMouseUp = function () {
        if (self.dragIdx >= 0) {
          self.dragIdx = -1;
          self._redraw();
          if (self._onChange) self._onChange(strDict(self.entries));
        }
      };

      // touch
      this._onTouchStart = function (e) {
        if (e.touches.length !== 1) return;
        var t = e.touches[0];
        var idx = self._findPoint(t.clientX, t.clientY);
        if (idx >= 0) {
          e.preventDefault();
          self.dragIdx = idx;
          self.selIdx = idx;
          self._redraw();
        }
      };

      this._onTouchMove = function (e) {
        if (self.dragIdx < 0 || e.touches.length !== 1) return;
        e.preventDefault();
        var t = e.touches[0];
        var rect = self.svg.getBoundingClientRect();
        var sx = t.clientX - rect.left;
        var sy = t.clientY - rect.top;
        var extent = self._dataExtent();
        var area = self._plotArea();
        var data = self._fromSvg(sx, sy, extent, area);
        var clamped = self._clamp(self.dragIdx, data.x, data.y);
        self.entries[self.dragIdx] = clamped;
        self._redraw();
      };

      this._onTouchEnd = function () {
        if (self.dragIdx >= 0) {
          self.dragIdx = -1;
          self._redraw();
          if (self._onChange) self._onChange(strDict(self.entries));
        }
      };

      this._onDblClick = function (e) {
        if (self._findPoint(e.clientX, e.clientY) >= 0) return;
        var rect = self.svg.getBoundingClientRect();
        var extent = self._dataExtent();
        var area = self._plotArea();
        var data = self._fromSvg(e.clientX - rect.left, e.clientY - rect.top, extent, area);
        self.addPoint(data.x, data.y);
      };

      this.svg.addEventListener('dblclick', this._onDblClick);
      this.svg.addEventListener('mousedown', this._onMouseDown);
      document.addEventListener('mousemove', this._onMouseMove);
      document.addEventListener('mouseup', this._onMouseUp);
      this.svg.addEventListener('touchstart', this._onTouchStart, { passive: false });
      document.addEventListener('touchmove', this._onTouchMove, { passive: false });
      document.addEventListener('touchend', this._onTouchEnd);

      // debounced resize
      var resizeTimer = null;
      var ro = new ResizeObserver(function () {
        if (resizeTimer) clearTimeout(resizeTimer);
        resizeTimer = setTimeout(function () { self._redraw(); }, 80);
      });
      ro.observe(this.wrap);
      this._ro = ro;
    },

    /* ---- public API ---- */
    getPoints: function () {
      return strDict(this.entries);
    },

    setPoints: function (points) {
      this.entries = sortedEntries(points || {});
      this.selIdx = -1;
      this.dragIdx = -1;
      this._redraw();
    },

    setSelectedValue: function (y) {
      if (this.selIdx < 0 || this.selIdx >= this.entries.length) return false;
      var val = parseFloat(y);
      if (isNaN(val) || val < 0) return false;
      this.entries[this.selIdx][1] = Math.round(val * 100) / 100;
      this._redraw();
      if (this._onChange) this._onChange(strDict(this.entries));
      return true;
    },

    addPoint: function (x, y) {
      var px = Math.max(0.1, Math.round(toFloat(x) * 10) / 10);
      var py = Math.max(0, Math.round(toFloat(y) * 100) / 100);
      for (var i = 0; i < this.entries.length; i++) {
        if (Math.abs(this.entries[i][0] - px) < 0.05) return false; // angle taken
      }
      this.entries.push([px, py]);
      this.entries.sort(function (a, b) { return a[0] - b[0]; });
      for (i = 0; i < this.entries.length; i++) {
        if (this.entries[i][0] === px) { this.selIdx = i; break; }
      }
      this._redraw();
      if (this._onChange) this._onChange(strDict(this.entries));
      return true;
    },

    deleteSelected: function () {
      if (this.selIdx < 0 || this.selIdx >= this.entries.length) return false;
      if (this.entries.length <= 1) return false; // keep at least one point
      this.entries.splice(this.selIdx, 1);
      if (this.selIdx >= this.entries.length) this.selIdx = this.entries.length - 1;
      this._redraw();
      if (this._onChange) this._onChange(strDict(this.entries));
      return true;
    },

    selectIndex: function (i) {
      if (i >= 0 && i < this.entries.length) {
        this.selIdx = i;
        this._redraw();
      }
    },

    selectedIndex: function () {
      return (this.selIdx >= 0 && this.selIdx < this.entries.length) ? this.selIdx : -1;
    },

    destroy: function () {
      this.svg.removeEventListener('dblclick', this._onDblClick);
      this.svg.removeEventListener('mousedown', this._onMouseDown);
      document.removeEventListener('mousemove', this._onMouseMove);
      document.removeEventListener('mouseup', this._onMouseUp);
      this.svg.removeEventListener('touchstart', this._onTouchStart);
      document.removeEventListener('touchmove', this._onTouchMove);
      document.removeEventListener('touchend', this._onTouchEnd);
      if (this._ro) { this._ro.disconnect(); this._ro = null; }
      this.container.innerHTML = '';
    }
  };

  /* ---- static mount ---- */
  McduCurves.mount = function (container, points, opts) {
    return new McduCurves(container, points, opts);
  };

  /* ---- keyframe for selection pulse ---- */
  var style = document.createElement('style');
  style.textContent =
    '@keyframes mcv-pulse {' +
    '  0%,100% { opacity:0.9; r:10; }' +
    '  50%      { opacity:0.45; r:13; }' +
    '}';
  document.head.appendChild(style);

  /* ---- export ---- */
  window.McduCurves = McduCurves;
})();
