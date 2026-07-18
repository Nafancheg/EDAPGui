// MCDU UI localisation layer (руссификация, 2026-07-16).
// Applied at the RENDER layer only (fill/setHeader/flash in mcdu.js): the
// lookup translates exact label matches and known tokens; anything unknown
// (system names, numbers, values) passes through untouched, so no command
// or data path ever sees a translated string.
// Language is a pure UI preference: localStorage['mcdu_lang'] = 'ru'|'en',
// default 'ru'. The OCR "Language" setting of the core is unrelated.
(function () {
  'use strict';

  // ---- exact-match labels (arrows <> are stripped before lookup) ---------- //
  var DICT = {
    // page headers / titles
    'RTE PLAN': 'ПЛАН МАРШРУТА', 'ROUTE PLANNER': 'ПЛАНИРОВЩИК',
    'RTE LIST': 'СПИСОК МАРШРУТА', 'MCDU MENU': 'МЕНЮ MCDU',
    'SETTINGS': 'НАСТРОЙКИ', 'OPTIONS': 'ОПЦИИ', 'CONFIG': 'КОНФИГ',
    'MAINT': 'СЕРВИС', 'CALIB': 'КАЛИБРОВКА', 'CALIB REG': 'РЕГИОН КАЛИБ',
    'CALIBRATION': 'КАЛИБРОВКА', 'OCR REGIONS': 'РЕГИОНЫ OCR',
    'DATA': 'ДАННЫЕ', 'SYSTEM DATA': 'ДАННЫЕ СИСТЕМЫ',
    'EXTERNAL DATA': 'ВНЕШНИЕ ДАННЫЕ',
    'INIT': 'ИНИЦ', 'PREFLIGHT': 'ПРЕДПОЛЁТ', 'PROG': 'ПРОГ',
    'CRUISE': 'КРУИЗ', 'CRU OPT': 'ОПЦИИ КРУИЗА',
    'F-PLN': 'ПЛАН ПОЛЁТА', 'FUEL PRED': 'ПРОГНОЗ ТОПЛ',
    'REFUEL SELECT': 'ВЫБОР ЗАПРАВКИ',
    'DIR': 'ПРЯМО-НА', 'DIRECT-TO': 'ПРЯМО-НА', 'DIRECT TO': 'ПРЯМО НА',
    'RPY CURVES': 'КРИВЫЕ RPY', 'RPY TUNING': 'ТЮНИНГ RPY',
    'FLIGHT': 'ПОЛЁТ',

    // actions (left column)
    'PLOT FUEL-SAFE': 'ПОСТРОИТЬ ЭКОНОМ',
    'PLOT FAST/RISKY': 'ПОСТРОИТЬ БЫСТРЫЙ',
    'ACTIVATE SEC': 'АКТИВИРОВАТЬ SEC',
    'ACTIVATE SEC  CONFIRM?': 'АКТИВАЦИЯ — ТОЧНО?',
    'STOP EXEC': 'СТОП ИСПОЛН',
    'STOP EXEC  CONFIRM?': 'СТОП — ТОЧНО?',
    'RETURN': 'НАЗАД', 'NEXT PAGE': 'СЛЕД СТР',
    'NEXT PHASE': 'СЛЕД ФАЗА', 'PREV PHASE': 'ПРЕД ФАЗА',
    'SAVE ALL': 'СОХР ВСЁ', 'LOAD ALL': 'ЗАГР ВСЁ',
    'SAVE TO DISK': 'СОХР НА ДИСК', 'SAVE CALIB': 'СОХР КАЛИБ',
    'DEL PT': 'УДАЛ ТЧК', 'RESET ALL': 'СБРОС ВСЕХ',
    'RESET ALL  CONFIRM?': 'СБРОС — ТОЧНО?',
    'CAL TARGET': 'КАЛ ЦЕЛИ', 'ALIGN TGT': 'ВЫРАВН ЦЕЛЬ',
    'DOCK / LAND': 'СТЫК / ПОСАДКА', 'DROP TO OC': 'СХОД В OC',
    'ENTER SC': 'ВХОД В SC', 'FINAL DESCENT': 'ФИНАЛ СНИЖЕНИЯ',
    'GLIDE': 'ГЛАЙД', 'SURFACE APPR': 'ПОДХОД К ПОВЕРХН',
    'REQ DOCKING': 'ЗАПРОС СТЫКОВКИ', 'UNDOCK': 'РАССТЫКОВКА',
    'REFUEL·REPAIR': 'ЗАПРАВКА·РЕМОНТ', 'SCOOP NOW': 'СКУП СЕЙЧАС',
    'STAR THIS SYSTEM': 'ЗВЕЗДА ЭТОЙ СИС',
    'NEAREST SCOOPABLE': 'БЛИЖ СКУПИРУЕМАЯ',
    'NEAREST SYSTEM': 'БЛИЖ СИСТЕМА',
    'NEAREST STATION': 'БЛИЖ СТАНЦИЯ',
    'NEAREST RFL POINT': 'БЛИЖ ЗАПРАВКА',
    'ACTIVATE REFUEL': 'АКТИВ ЗАПРАВКУ',
    'FSD ROUTE ON': 'FSD МАРШРУТ ВКЛ', 'FSD ROUTE OFF': 'FSD МАРШРУТ ВЫКЛ',
    'SC ASSIST ON': 'SC АССИСТ ВКЛ', 'SC ASSIST OFF': 'SC АССИСТ ВЫКЛ',
    'THR 0': 'ТЯГА 0', 'THR 50': 'ТЯГА 50', 'THR 100': 'ТЯГА 100',
    'HONK': 'ХОНК', 'FSS SCAN': 'FSS СКАН', 'ELW SCAN': 'СКАН ELW',
    'DSS HONK': 'DSS ГУДОК',
    'FAST TRAVEL': 'БЫСТРЫЙ ПЕРЕЛЁТ',
    'EDSM FETCH': 'EDSM ЗАПРОС',
    'AUTO-ASSIGN KEYS': 'АВТОНАЗН КЛАВИШ',
    'RELOAD BINDINGS': 'ПЕРЕЧИТАТЬ БИНДЫ',
    'REFRESH GAME SET': 'ОБНОВИТЬ НАСТР ИГРЫ',
    'PITCH': 'ТАНГАЖ', 'ROLL': 'КРЕН', 'YAW': 'РЫСК',
    'TGT: POI': 'ЦЕЛЬ: POI',

    // toggle bases (used by the "  ON/OFF" suffix rule below)
    'ACT-ELITE KEY': 'ФОКУС ОКНА ED', 'AUTO LOGOUT': 'АВТОВЫХОД',
    'AUTO TUNE RPY': 'АВТОТЮН RPY', 'CV VIEW': 'ВИД CV',
    'DBG IMAGES': 'ОТЛ СНИМКИ', 'DBG OCR': 'ОТЛ OCR',
    'DBG OVERLAY': 'ОТЛ ОВЕРЛЕЙ', 'HOTKEYS': 'ХОТКЕИ',
    'OVERLAY': 'ОВЕРЛЕЙ', 'RANDOMNESS': 'РАНДОМИЗАЦИЯ', 'VOICE': 'ГОЛОС',

    // data labels (right column headers etc.)
    'SEC DEST': 'ЦЕЛЬ SEC', 'SEC FROM': 'ОТКУДА', 'FROM': 'ОТКУДА',
    'JUMPS': 'ПРЫЖКИ', 'DIST': 'ДИСТ', 'SCOOPS': 'ЗАПРАВКИ', 'RISK': 'РИСК',
    'HIGH': 'ВЫСОКИЙ', 'LOW': 'НИЗКИЙ',
    'DEST': 'ЦЕЛЬ', 'FUEL': 'ТОПЛИВО', 'AVG/JUMP': 'СРЕДН/ПРЖ',
    'TO REFUEL': 'ДО ЗАПРАВКИ', 'RANGE': 'ЗАПАС ХОДА',
    'RFL THRESHOLD': 'ПОРОГ ЗАПРАВКИ', 'SCOOP TIMEOUT': 'ТАЙМАУТ СКУПА',
    'FUEL ABORT': 'СТОП ПО ТОПЛИВУ',
    'TARGET': 'ЦЕЛЬ', 'CLASS': 'КЛАСС', 'BODIES': 'ТЕЛА', 'SCANS': 'СКАНЫ',
    'SKIP SCANS': 'БЕЗ СКАНОВ', 'STAR': 'ЗВЕЗДА', 'SHIP': 'КОРАБЛЬ',
    'MODE': 'РЕЖИМ', 'LINK': 'СВЯЗЬ', 'CONNECTED': 'ПОДКЛЮЧЕНО',
    'OFFLINE': 'ОФЛАЙН', 'NOT CONNECTED': 'НЕТ СВЯЗИ',
    'PRIMARY': 'ОСНОВНОЙ', 'SECONDARY': 'ЗАПАСНОЙ',
    'SPEED': 'СКОРОСТЬ', 'THROTTLE': 'ТЯГА', 'AXIS': 'ОСЬ',
    'CURVE': 'КРИВАЯ', 'PT': 'ТЧК', 'SET VAL': 'ЗНАЧЕНИЕ',
    'LAST POINT': 'ПОСЛ ТОЧКА', 'SELECT A POINT': 'ВЫБЕРИ ТОЧКУ',
    'NO POINTS': 'НЕТ ТОЧЕК',
    'POS': 'ПОЗ', 'ALT': 'ВЫС', 'HDG · BRG': 'КУРС · ПЕЛЕНГ',
    'DIST TO DROP': 'ДИСТ ДО СХОДА', 'DIST TO TGT': 'ДИСТ ДО ЦЕЛИ',
    'TGT COORDS': 'КООРД ЦЕЛИ',
    'ORIGIN': 'СТАРТ', 'END OF PLAN': 'КОНЕЦ ПЛАНА', 'TOTAL': 'ИТОГО',
    'SCOOPABLE': 'СКУПИРУЕМА', 'SCOOP': 'СКУП', 'CAND': 'КАНДИДАТ',
    'AUTODOCK WAIT': 'ОЖИД АВТОСТЫК', 'DOCK RETRIES': 'ПОПЫТКИ СТЫК',
    'JUMP TRIES': 'ПОПЫТКИ ПРЖ', 'NAV ALIGN TRIES': 'ПОПЫТКИ ВЫРАВН',
    'SUN BRIGHT': 'ЯРКОСТЬ СОЛНЦА', 'MOD DELAY': 'ЗАДЕРЖКА МОД',
    'REPEAT DLY': 'ЗАДЕРЖ ПОВТ', 'DEF HOLD': 'УДЕРЖ КЛАВ',
    'GAME': 'ИГРА', 'CORE': 'ЯДРО', 'BINDS': 'БИНДЫ',
    'YES': 'ДА', 'NO': 'НЕТ', 'ETA': 'ETA',

    // states / empty screens / long hints
    'NO DATA': 'НЕТ ДАННЫХ', 'NO ROUTE': 'НЕТ МАРШРУТА',
    'NO ACTIVE ROUTE': 'НЕТ АКТИВНОГО МАРШРУТА',
    'NO SECONDARY ROUTE': 'НЕТ ЗАПАСНОГО МАРШРУТА',
    'NO SYSTEM SELECTED': 'СИСТЕМА НЕ ВЫБРАНА',
    'NO REGION SELECTED': 'РЕГИОН НЕ ВЫБРАН',
    'PAGE INOP': 'СТРАНИЦА НЕ РАБОТАЕТ',
    'IN PROGRESS': 'ВЫПОЛНЯЕТСЯ',
    'AWAITS BACKEND (PHASE 8.1)': 'ЖДЁТ БЭКЕНД (ФАЗА 8.1)',
    'PLOT ROUTE IN GALAXY MAP': 'ПРОЛОЖИ В ГАЛАКАРТЕ',
    'ON GAME SCREEN': 'НА ЭКРАНЕ ИГРЫ',
    'READ-ONLY · DERIVED': 'ТОЛЬКО ЧТЕНИЕ · ВЫЧИСЛ',
    'LOADING CALIBRATION': 'ЗАГРУЗКА КАЛИБРОВКИ',
    'OVERLAY APPLIES ON RESTART': 'ОВЕРЛЕЙ ПОСЛЕ РЕСТАРТА',

    // flashes / statuses
    'PLOTTING…': 'ПОСТРОЕНИЕ…', 'PLOTTING···': 'ПОСТРОЕНИЕ···',
    'SEARCHING…': 'ПОИСК…',
    'SEC ACTIVATED': 'SEC АКТИВИРОВАН', 'ROUTE COMPLETE': 'МАРШРУТ ЗАВЕРШЁН',
    'OFF ROUTE': 'ВНЕ МАРШРУТА', 'ACTIVE': 'АКТИВЕН', 'COMPLETE': 'ЗАВЕРШЁН',
    'INVALID': 'ОШИБКА ВВОДА', 'NOT ALLOWED': 'НЕЛЬЗЯ',
    'NOT AVAILABLE': 'НЕДОСТУПНО', 'ENTER SEC DEST': 'ВВЕДИ ЦЕЛЬ SEC',
    'SETTINGS SAVED': 'НАСТРОЙКИ СОХР', 'SETTINGS LOADED': 'НАСТРОЙКИ ЗАГР',
    'SAVED TO DISK': 'СОХР НА ДИСК', 'SAVE FAILED': 'ОШИБКА СОХР',
    'CURVE UPDATED': 'КРИВАЯ ОБНОВЛЕНА',
    'CALIB SAVED': 'КАЛИБ СОХР', 'CALIB RESET': 'КАЛИБ СБРОШЕНА',
    'CAL TARGET DONE': 'КАЛ ЦЕЛИ ГОТОВО', 'CAL TARGET FAILED': 'КАЛ ЦЕЛИ ОШИБКА',
    'CAL TARGET RUNNING': 'КАЛ ЦЕЛИ ИДЁТ',
    'COPIED': 'СКОПИРОВАНО', 'NOTHING TO COPY': 'НЕЧЕГО КОПИРОВАТЬ',
    'CLIPBOARD EMPTY': 'БУФЕР ПУСТ',
    'PC CLIP EMPTY': 'БУФЕР ПК ПУСТ',
    'OFF': 'ВЫКЛ', 'MANUAL': 'РУЧН',
    'COPY FROM HERE': 'СКОПИРУЙ ОТСЮДА (ДОЛГИЙ ТАП)',
    'PASTE HERE': 'ВСТАВЬ СЮДА (ДОЛГИЙ ТАП)',
    'SHIP CHANGED — REPLOT': 'КОРАБЛЬ ИЗМЕНЁН — ПЕРЕСТРОЙ',
    'SHIP CHANGED SINCE PLOT — REPLOT': 'КОРАБЛЬ ИЗМЕНЁН — ПЕРЕСТРОЙ МАРШРУТ'
  };

  // ---- token pass for composed/dynamic strings (word boundaries, longest
  // first). Keep this list SHORT — it runs on strings DICT did not match. ---- //
  var TOKENS = [
    ['OFF ROUTE', 'ВНЕ МАРШРУТА'],
    ['ROUTE COMPLETE', 'МАРШРУТ ЗАВЕРШЁН'],
    ['DSS BTN', 'КН DSS'],
    ['LOG LVL', 'УРОВ ЛОГА'],
    ['LANGUAGE', 'ЯЗЫК OCR'],
    ['PLOTTED', 'ПОСТРОЕН'],
    ['COMPLETE', 'ЗАВЕРШЁН'],
    ['INACTIVE', 'ВЫКЛ'],
    ['ACTIVE', 'АКТИВЕН'],
    ['ROUTE', 'МАРШРУТ'],
    ['EXEC', 'ИСП'],
    ['NEXT', 'ДАЛЕЕ'],
    ['JMP', 'ПРЖ'],
    ['CONFIRM?', 'ТОЧНО?']
  ];
  var TOKEN_RE = TOKENS.map(function (p) {
    return [new RegExp('\\b' + p[0].replace(/[?]/g, '\\$&') + '(\\b|$)', 'g'), p[1]];
  });

  var lang = 'ru';
  try { lang = localStorage.getItem('mcdu_lang') || 'ru'; } catch (e) { /* file:// etc. */ }

  function translate(s) {
    if (lang !== 'ru' || typeof s !== 'string' || !s) return s;
    var pre = '', post = '', core = s;
    if (core.charAt(0) === '<') { pre = '<'; core = core.slice(1); }
    if (core.slice(-1) === '>') { post = '>'; core = core.slice(0, -1); }
    if (Object.prototype.hasOwnProperty.call(DICT, core)) return pre + DICT[core] + post;
    // "<NAME  ON" / "<NAME OFF" toggles: translate the base + ВКЛ/ВЫКЛ
    var m = core.match(/^(.*?)(\s+)(ON|OFF)$/);
    if (m && Object.prototype.hasOwnProperty.call(DICT, m[1])) {
      return pre + DICT[m[1]] + m[2] + (m[3] === 'ON' ? 'ВКЛ' : 'ВЫКЛ') + post;
    }
    var out = core;
    for (var i = 0; i < TOKEN_RE.length; i++) {
      out = out.replace(TOKEN_RE[i][0], TOKEN_RE[i][1]);
    }
    return pre + out + post;
  }

  window.MCDU_I18N = {
    t: translate,
    getLang: function () { return lang; },
    setLang: function (l) {
      lang = (l === 'en') ? 'en' : 'ru';
      try { localStorage.setItem('mcdu_lang', lang); } catch (e) { /* no-op */ }
    }
  };
})();
