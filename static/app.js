// ── Design tokens ─────────────────────────────────────────────────────────────

var C = {
  ink:     '#16243b',
  mut:     '#5b6675',
  faint:   '#8a93a1',
  line:    '#e6e9ee',
  bg:      '#f4f6f8',
  primary: '#15428a',
  green:   '#1f8a5b',
  amber:   '#c08a1f',
  red:     '#c0392b',
};

var LINE_COLORS = {
  '1':  { bg: '#FFCE00', text: '#16243b' },
  '2':  { bg: '#003CA6' },
  '3':  { bg: '#837902' },
  '3B': { bg: '#6EC4E8', text: '#16243b' },
  '4':  { bg: '#CF009E' },
  '5':  { bg: '#FF7E2E' },
  '6':  { bg: '#6ECA97', text: '#16243b' },
  '7':  { bg: '#FA9ABA' },
  '7B': { bg: '#6ECA97', text: '#16243b' },
  '8':  { bg: '#E19BDF' },
  '9':  { bg: '#B6BD00', text: '#16243b' },
  '10': { bg: '#C9910D' },
  '11': { bg: '#704B1C' },
  '12': { bg: '#007852' },
  '13': { bg: '#6EC4E8', text: '#16243b' },
  '14': { bg: '#62259D' },
  'A':  { bg: '#E2231A' },
  'B':  { bg: '#479FD3' },
  'C':  { bg: '#FFDD00', text: '#16243b' },
  'D':  { bg: '#00814F' },
  'E':  { bg: '#BF8600' },
};

// ── State ─────────────────────────────────────────────────────────────────────

var S = {
  screen:      'search',
  from:        '',
  to:          '',
  timeMode:    'now',   // 'now' | 'depart' | 'arrive'
  time:        '08:30',
  date:        '',
  cardStyle:   'B',
  filters:     { access: false, crowd: false, air: false },
  results:     null,
  selectedIdx: 0,
  loading:     false,
  error:       null,
};

// Autocomplete debounce timers (per field)
var acTimers = { from: null, to: null };

// ── Utils ─────────────────────────────────────────────────────────────────────

function esc(str) {
  return String(str || '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function pad(n) { return String(n).padStart(2, '0'); }

// Initialise la date à aujourd'hui
(function() { var d = new Date(); S.date = d.getFullYear() + '-' + pad(d.getMonth() + 1) + '-' + pad(d.getDate()); })();

function todayStr() {
  var d = new Date();
  return d.getFullYear() + '-' + pad(d.getMonth() + 1) + '-' + pad(d.getDate());
}

function maxDateStr() {
  var d = new Date();
  d.setDate(d.getDate() + 16);
  return d.getFullYear() + '-' + pad(d.getMonth() + 1) + '-' + pad(d.getDate());
}

function formatDateShort(dateStr) {
  var mois = ['jan.','fév.','mars','avr.','mai','juin','juil.','août','sept.','oct.','nov.','déc.'];
  var parts = (dateStr || '').split('-');
  var d = parseInt(parts[2], 10) || 1;
  var m = (parseInt(parts[1], 10) || 1) - 1;
  var y = parseInt(parts[0], 10) || new Date().getFullYear();
  var today = todayStr();
  if (dateStr === today) return "Aujourd'hui";
  var tom = new Date(); tom.setDate(tom.getDate() + 1);
  var tomStr = tom.getFullYear() + '-' + pad(tom.getMonth() + 1) + '-' + pad(tom.getDate());
  if (dateStr === tomStr) return 'Demain';
  return d + ' ' + mois[m] + ' ' + y;
}

function toDatetime(timeStr) {
  var dp = (S.date || todayStr()).split('-');
  var y  = parseInt(dp[0], 10) || new Date().getFullYear();
  var mo = parseInt(dp[1], 10) || (new Date().getMonth() + 1);
  var dy = parseInt(dp[2], 10) || new Date().getDate();
  var parts = (timeStr || '').split(':');
  var h = parseInt(parts[0], 10) || 0;
  var m = parseInt(parts[1], 10) || 0;
  return '' + y + pad(mo) + pad(dy) + 'T' + pad(h) + pad(m) + '00';
}

function buildDatetime() {
  if (S.timeMode === 'now') {
    var now = new Date();
    return '' + now.getFullYear() + pad(now.getMonth() + 1) + pad(now.getDate()) +
      'T' + pad(now.getHours()) + pad(now.getMinutes()) + '00';
  }
  return toDatetime(S.time);
}

function buildDatetimeRepresents() {
  return S.timeMode === 'arrive' ? 'arrival' : 'departure';
}

function setTimeMode(mode) {
  S.timeMode = mode;
  if (mode !== 'now' && !S.date) S.date = todayStr();
  render();
  // After render, if a time input is now visible, focus it for keyboard users
  if (mode !== 'now') {
    var inp = document.getElementById('inp-time');
    if (inp) inp.focus();
  }
}

function openTimePicker() {
  var inp = document.getElementById('inp-time');
  if (!inp) return;
  if (inp.showPicker) {
    try { inp.showPicker(); } catch (e) { inp.focus(); }
  } else {
    inp.focus();
  }
}

function openDatePicker() {
  var inp = document.getElementById('inp-date');
  if (!inp) return;
  if (inp.showPicker) {
    try { inp.showPicker(); } catch (e) { inp.focus(); }
  } else {
    inp.focus();
  }
}

function creneau(it) {
  // Deux trains d'une meme ligne peuvent ne differer que par l'horaire :
  // sans lui, les options paraissent identiques a l'ecran.
  if (!it.heure_depart || !it.heure_arrivee) return '';
  return it.heure_depart + ' → ' + it.heure_arrivee;
}

function formatLine(label) {
  if (!label) return '?';
  if (/^[A-E]$/i.test(label.trim())) return 'RER ' + label.toUpperCase();
  if (/^\d{1,2}[Bb]?$/.test(label.trim())) return 'M ' + label;
  return label;
}

function lineColor(label) {
  if (!label) return { bg: '#888' };
  var key = label.replace(/^RER\s*/i, '').replace(/^M\s*/i, '').toUpperCase().trim();
  return LINE_COLORS[key] || { bg: '#5b6675' };
}

function buildTitle(lignes, nb) {
  if (!lignes || !lignes.length) return 'Itinéraire';
  var parts = lignes.map(formatLine);
  if (parts.length === 1 && nb === 0) return parts[0] + ' direct';
  return parts.join(' + ');
}

function bandFor(score) {
  if (score >= 7) return { label: 'Confortable',   color: C.green };
  if (score >= 5) return { label: 'Acceptable',    color: C.amber };
  return              { label: 'Inconfortable', color: C.red   };
}

function alertMeta(text) {
  var t = (text || '').toLowerCase();
  if (/affluence|charg/.test(t))              return { ic: 'users',    col: C.amber   };
  if (/non document|non renseign/.test(t))                 return { ic: 'accessibility', col: C.mut };
  if (/ascenseur|panne/.test(t))              return { ic: 'alert',    col: C.red     };
  if (/climati|ventil/.test(t))               return { ic: 'wind',     col: '#3f6f8a' };
  if (/équipement|toilette|fontaine/.test(t)) return { ic: 'droplet',  col: '#2f8f7f' };
  if (/correspond/.test(t))                   return { ic: 'transfer', col: C.mut     };
  if (/pluie|aérien/.test(t))                 return { ic: 'droplet',  col: '#3f6f8a' };
  if (/canicule|chaleur/.test(t))             return { ic: 'alert',    col: C.amber   };
  return                                             { ic: 'alert',    col: C.mut     };
}

// ── Filter helpers ────────────────────────────────────────────────────────────

function accessibiliteLabel(acc) {
  // "Non renseigné" n'est pas "Stable" : sans donnée IDFM, on ne certifie rien.
  if (acc.statut === 'panne')   return acc.pannes.length + ' panne(s)';
  if (acc.statut === 'inconnu') return 'Non documenté';
  return acc.nb_checked + ' arrêt(s) documenté(s)';
}

// Les seuils des trois filtres sont définis côté API (_flags_filtres) et
// renvoyés par itinéraire dans `filtres_compatibles`. Le front ne les
// redéfinit pas : deux implémentations divergeaient silencieusement.
function compatible(it, cle) {
  var f = it.filtres_compatibles;
  return !!(f && f[cle]);
}

function availableFilters() {
  if (!S.results || !S.results.itineraires.length) {
    return { access: true, crowd: true, air: true };
  }
  var all = S.results.itineraires;
  return {
    access: all.some(function(it) { return compatible(it, 'accessible'); }),
    crowd:  all.some(function(it) { return compatible(it, 'peu_de_monde'); }),
    air:    all.some(function(it) { return compatible(it, 'climatise'); }),
  };
}

function syncFilters() {
  var avail = availableFilters();
  ['access', 'crowd', 'air'].forEach(function(k) {
    if (S.filters[k] && !avail[k]) S.filters[k] = false;
  });
}

function estMeilleur(it) {
  // L'API trie par confort decroissant : le meilleur d'un sous-ensemble
  // filtre cote client est simplement son premier element. Le badge exige en
  // plus une qualite absolue suffisante, pour ne pas "recommander" le moins
  // mauvais d'une mauvaise serie.
  if (it.recommandation !== 'Recommandé') return false;
  var visibles = filteredItineraires();
  return visibles.length > 0 && visibles[0] === it;
}

function filteredItineraires() {
  if (!S.results) return [];
  return S.results.itineraires.filter(function(it) {
    if (S.filters.access && !compatible(it, 'accessible'))   return false;
    if (S.filters.crowd  && !compatible(it, 'peu_de_monde')) return false;
    if (S.filters.air    && !compatible(it, 'climatise'))    return false;
    return true;
  });
}

// ── SVG icons ─────────────────────────────────────────────────────────────────

var ICON_PATHS = {
  alert:         { p: ['m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z','M12 9v4','M12 17h.01'] },
  users:         { p: ['M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2','M22 21v-2a4 4 0 0 0-3-3.87','M16 3.13a4 4 0 0 1 0 7.75'], c: [[9,7,4]] },
  wind:          { p: ['M12.8 19.6A2 2 0 1 0 14 16H2','M17.5 8a2.5 2.5 0 1 1 2 4H2','M9.8 4.4A2 2 0 1 1 11 8H2'] },
  droplet:       { p: ['M12 22a7 7 0 0 0 7-7c0-2-1-3.9-3-5.5s-3.5-4-4-6.5c-.5 2.5-2 4.9-4 6.5C6 11.1 5 13 5 15a7 7 0 0 0 7 7z'] },
  transfer:      { p: ['m16 3 4 4-4 4','M20 7H4','m8 21-4-4 4-4','M4 17h16'] },
  walk:          { p: ['M4 16v-2.38C4 11.5 2.97 10.5 3 8c.03-2.72 1.49-6 4.5-6C9.37 2 10 3.8 10 5.5c0 3.11-2 5.66-2 8.68V16a2 2 0 1 1-4 0Z','M20 20v-2.38c0-2.12 1.03-3.12 1-5.62-.03-2.72-1.49-6-4.5-6C14.63 6 14 7.8 14 9.5c0 3.11 2 5.66 2 8.68V20a2 2 0 1 0 4 0Z','M16 17h4','M4 13h4'] },
  clock:         { p: ['M12 6v6l4 2'], c: [[12,12,10]] },
  arrow:         { p: ['M5 12h14','m12 5 7 7-7 7'] },
  back:          { p: ['m12 19-7-7 7-7','M19 12H5'] },
  swap:          { p: ['m17 4 3 3-3 3','M20 7H8','m7 20-3-3 3-3','M4 17h12'] },
  accessibility: { p: ['m18 19 1-7-6 1','m5 8 3-3 5.5 3-2.36 3.5','M4.24 14.5a5 5 0 0 0 6.88 6','M13.76 17.5a5 5 0 0 0-3.4-6.4'], c: [[16,4,1]] },
  pin:           { p: ['M20 10c0 4.993-5.539 10.193-7.399 11.799a1 1 0 0 1-1.202 0C9.539 20.193 4 14.993 4 10a8 8 0 0 1 16 0'], c: [[12,10,3]] },
  search:        { p: ['m21 21-4.34-4.34'], c: [[11,11,8]] },
  nav:           { p: ['m3 11 19-9-9 19-2-8-8-2z'] },
  calendar:      { p: ['M8 2v4','M16 2v4','M3 10h18','M21 8.5V17a4 4 0 0 1-4 4H7a4 4 0 0 1-4-4V8.5a4 4 0 0 1 4-4h10a4 4 0 0 1 4 4z'] },
};

function icon(name, size, color, sw) {
  size  = size  || 18;
  color = color || 'currentColor';
  sw    = sw    || 2;
  var d = ICON_PATHS[name] || { p: [] };
  var paths   = (d.p || []).map(function(dd) { return '<path d="' + dd + '"/>'; }).join('');
  var circles = (d.c || []).map(function(cc) { return '<circle cx="' + cc[0] + '" cy="' + cc[1] + '" r="' + cc[2] + '"/>'; }).join('');
  return '<svg width="' + size + '" height="' + size + '" viewBox="0 0 24 24" fill="none" stroke="' + color + '" stroke-width="' + sw + '" stroke-linecap="round" stroke-linejoin="round">' + paths + circles + '</svg>';
}

// ── UI components ─────────────────────────────────────────────────────────────

function gauge(score, size, sw) {
  sw = sw || 5;
  var color = score >= 7 ? C.green : score >= 5 ? C.amber : C.red;
  var r  = size / 2 - sw / 2 - 1;
  var cx = size / 2;
  var fs = Math.round(size * 0.3);
  var pct = Math.min(100, Math.round(score * 10));
  return '<svg width="' + size + '" height="' + size + '" viewBox="0 0 ' + size + ' ' + size + '">' +
    '<circle cx="' + cx + '" cy="' + cx + '" r="' + r + '" fill="none" stroke="#eceff3" stroke-width="' + sw + '"/>' +
    '<circle cx="' + cx + '" cy="' + cx + '" r="' + r + '" fill="none" stroke="' + color + '" stroke-width="' + sw + '" stroke-linecap="round" pathLength="100" stroke-dasharray="' + pct + ' 100" transform="rotate(-90 ' + cx + ' ' + cx + ')"/>' +
    '<text x="' + cx + '" y="' + cx + '" text-anchor="middle" dominant-baseline="central" style="font:700 ' + fs + 'px \'IBM Plex Mono\';fill:' + C.ink + '">' + score + '</text>' +
    '</svg>';
}

function bar(value) {
  var color = value >= 7 ? C.green : value >= 5 ? C.amber : C.red;
  var pct   = Math.min(100, Math.round(value * 10));
  return '<div style="height:8px;width:100%;background:#eceff3;border-radius:99px;overflow:hidden">' +
    '<div style="height:100%;width:' + pct + '%;background:' + color + ';border-radius:99px"></div>' +
    '</div>';
}

function lineBadge(label) {
  var c = lineColor(label);
  return '<span style="display:inline-flex;align-items:center;padding:3px 8px;border-radius:7px;background:' + c.bg + ';color:' + (c.text || '#fff') + ';font:700 12px \'IBM Plex Mono\';line-height:1.15;white-space:nowrap">' + esc(formatLine(label)) + '</span>';
}

function recommendedBadge(size) {
  var fs = size === 'sm' ? '10px' : '11px';
  var py = size === 'sm' ? '2px' : '3px';
  return '<span style="background:#eaf6ef;color:' + C.green + ';font:600 ' + fs + ' \'Libre Franklin\';padding:' + py + ' 9px;border-radius:999px">Recommandé</span>';
}

function alertPillSmall(text) {
  var m = alertMeta(text);
  return '<span style="display:inline-flex;align-items:center;gap:6px;background:#f6f8fa;border:1px solid #eceff3;border-radius:999px;padding:5px 11px 5px 9px">' +
    icon(m.ic, 15, m.col, 2.2) + '<span style="font:500 12px \'Libre Franklin\';color:' + C.mut + '">' + esc(text) + '</span></span>';
}

function alertRow(text) {
  var m = alertMeta(text);
  return '<div style="display:flex;align-items:center;gap:9px">' +
    icon(m.ic, 16, m.col, 2.2) + '<span style="font:500 13px \'Libre Franklin\';color:' + C.mut + '">' + esc(text) + '</span></div>';
}

function alertInline(text) {
  var m = alertMeta(text);
  return '<span style="display:inline-flex;align-items:center;gap:6px">' +
    icon(m.ic, 14, m.col, 2.2) + '<span style="font:500 12px \'Libre Franklin\';color:' + C.faint + '">' + esc(text) + '</span></span>';
}

// ── Filter chips ──────────────────────────────────────────────────────────────

// Pourquoi un filtre est indisponible sur cette recherche. Textes d'affichage
// uniquement : les seuils restent definis cote API.
function filterReason(cle, all) {
  if (cle === 'access') {
    var statuts = all.map(function(it) { return it.dimensions.accessibilite.statut; });
    if (statuts.length && statuts.every(function(s) { return s === 'inconnu'; })) {
      return 'embarquement en fauteuil non documenté par IDFM à ces arrêts';
    }
    return 'ascenseur en panne ou non vérifié sur tous les itinéraires';
  }
  if (cle === 'crowd') return 'tous les itinéraires sont chargés à cette heure';
  return 'aucune ligne climatisée sur ce trajet';
}

function filterChips() {
  var avail = availableFilters();
  var all   = S.results ? S.results.itineraires : [];
  var defs  = [
    ['access', 'Ascenseurs',   'accessibility'],
    ['crowd',  'Peu de monde', 'users'],
    ['air',    'Climatisé',    'wind'],
  ];

  // Une puce indisponible reste affichée, désactivée et expliquée : la faire
  // disparaître laissait l'utilisateur sans rien comprendre.
  var chips = defs.map(function(d) {
    if (!avail[d[0]]) {
      return '<span aria-disabled="true" title="' + esc(filterReason(d[0], all)) + '" ' +
        'style="display:inline-flex;align-items:center;gap:7px;border-radius:999px;padding:8px 14px 8px 12px;' +
        'font:600 13px \'Libre Franklin\';border:1px dashed ' + C.line + ';background:#f7f8fa;' +
        'color:' + C.faint + ';cursor:not-allowed">' +
        icon(d[2], 15, C.faint, 2.2) + '<span>' + d[1] + '</span></span>';
    }
    var on = S.filters[d[0]];
    return '<button onclick="toggleFilter(\'' + d[0] + '\')" style="display:inline-flex;align-items:center;gap:7px;border-radius:999px;padding:8px 14px 8px 12px;font:600 13px \'Libre Franklin\';border:' + (on ? '1px solid ' + C.primary : '1px solid ' + C.line) + ';background:' + (on ? '#eaf0fb' : '#fff') + ';color:' + (on ? C.primary : C.mut) + ';transition:all .15s">' +
      icon(d[2], 15, on ? C.primary : C.faint, 2.2) + '<span>' + d[1] + '</span></button>';
  }).join('');

  return chips;
}

// Rendu separe des chips : evite que filterChips() ferme une balise du parent.
function filterReasons() {
  var avail = availableFilters();
  var all   = S.results ? S.results.itineraires : [];
  var lignes = [
    ['access', 'Ascenseurs'],
    ['crowd',  'Peu de monde'],
    ['air',    'Climatisé'],
  ].filter(function(d) { return !avail[d[0]]; }).map(function(d) {
    return '<div style="font:400 12px/1.5 \'Libre Franklin\';color:' + C.faint + '">' +
      '<strong style="font-weight:600">' + d[1] + '</strong> indisponible — ' +
      esc(filterReason(d[0], all)) + '.</div>';
  }).join('');

  return lignes
    ? '<div style="margin-top:10px;display:flex;flex-direction:column;gap:3px">' + lignes + '</div>'
    : '';
}
function switcher() {
  var opts = [['A','Sobre'],['B','Carte'],['C','Comparatif']];
  return '<div style="display:flex;gap:3px;background:#e7ebef;border-radius:10px;padding:3px">' +
    opts.map(function(o) {
      var on = S.cardStyle === o[0];
      return '<button onclick="setCardStyle(\'' + o[0] + '\')" style="border:none;border-radius:8px;padding:6px 11px;font:600 12px \'Libre Franklin\';background:' + (on ? '#fff' : 'transparent') + ';color:' + (on ? C.primary : C.mut) + ';box-shadow:' + (on ? '0 1px 2px rgba(20,40,80,.12)' : 'none') + ';transition:all .15s">' + o[1] + '</button>';
    }).join('') + '</div>';
}

// ── Autocomplete ──────────────────────────────────────────────────────────────

function renderAcDropdown(dd, acState) {
  if (!acState.items.length) { dd.style.display = 'none'; return; }
  dd.innerHTML = acState.items.map(function(name, i) {
    var active = i === acState.activeIdx;
    return '<div data-ac-name="' + esc(name) + '" style="padding:10px 16px;' +
      'font:500 14px \'Libre Franklin\';' +
      'color:' + (active ? C.primary : C.ink) + ';' +
      'background:' + (active ? '#f0f5ff' : '#fff') + ';' +
      'cursor:pointer;' +
      (i < acState.items.length - 1 ? 'border-bottom:1px solid #f4f6f8;' : '') +
      '">' + esc(name) + '</div>';
  }).join('');
  dd.style.display = 'block';
}

function attachAC(rowId, inputId, field) {
  var row = document.getElementById(rowId);
  var inp = document.getElementById(inputId);
  if (!row || !inp) return;

  // One dropdown per row, recreated on each render()
  var dd = document.createElement('div');
  dd.style.cssText =
    'display:none;position:absolute;top:calc(100% + 1px);left:0;right:0;' +
    'background:#fff;border:1px solid ' + C.line + ';border-radius:12px;' +
    'box-shadow:0 8px 24px rgba(20,40,80,.1);z-index:200;' +
    'overflow:hidden;max-height:240px;overflow-y:auto';
  row.appendChild(dd);

  var acState = { items: [], activeIdx: -1 };

  // Click/tap selection — use mousedown to fire before blur
  dd.addEventListener('mousedown', function(e) {
    var item = e.target.closest('[data-ac-name]');
    if (!item) return;
    e.preventDefault(); // prevent blur from closing before we act
    var name = item.getAttribute('data-ac-name');
    inp.value = name;
    S[field]  = name;
    dd.style.display = 'none';
    acState.items = []; acState.activeIdx = -1;
  });

  // Debounced fetch on typing
  inp.addEventListener('input', function() {
    var val = this.value;
    S[field] = val;
    if (val.length < 2) { dd.style.display = 'none'; acState.items = []; return; }

    if (acTimers[field]) clearTimeout(acTimers[field]);
    acTimers[field] = setTimeout(function() {
      // Guard: DOM element might no longer exist after a render()
      if (document.getElementById(inputId) !== inp) return;
      fetch('/stations?q=' + encodeURIComponent(val))
        .then(function(r) { return r.json(); })
        .then(function(data) {
          if (document.getElementById(inputId) !== inp) return;
          acState.items    = data.stations || [];
          acState.activeIdx = -1;
          renderAcDropdown(dd, acState);
        })
        .catch(function() {});
    }, 250);
  });

  // Keyboard navigation
  inp.addEventListener('keydown', function(e) {
    if (dd.style.display === 'none' || !acState.items.length) return;
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      acState.activeIdx = Math.min(acState.activeIdx + 1, acState.items.length - 1);
      renderAcDropdown(dd, acState);
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      acState.activeIdx = Math.max(acState.activeIdx - 1, 0);
      renderAcDropdown(dd, acState);
    } else if (e.key === 'Enter' && acState.activeIdx >= 0) {
      e.preventDefault();
      var name = acState.items[acState.activeIdx];
      inp.value = name;
      S[field]  = name;
      dd.style.display = 'none';
      acState.items = []; acState.activeIdx = -1;
    } else if (e.key === 'Escape') {
      dd.style.display = 'none';
    }
  });

  // Close on blur (timeout allows mousedown on dropdown to fire first)
  inp.addEventListener('blur', function() {
    setTimeout(function() { dd.style.display = 'none'; }, 180);
  });

  // Re-open if items exist on re-focus
  inp.addEventListener('focus', function() {
    if (acState.items.length) renderAcDropdown(dd, acState);
  });
}

function initAutocomplete() {
  if (S.screen !== 'search') return;
  attachAC('ac-from-row', 'inp-from', 'from');
  attachAC('ac-to-row',   'inp-to',   'to');
}

// ── Card style A – Sobre ──────────────────────────────────────────────────────

function cardA(it, idx) {
  var sc    = it.score_confort;
  var band  = bandFor(sc);
  var rec   = estMeilleur(it);
  var title = buildTitle(it.lignes, it.nb_correspondances);
  var alts  = it.business_summary.alertes.slice(0, 3);

  return '<div onclick="selectIt(' + idx + ')" style="background:#fff;border:1px solid ' + C.line + ';border-radius:16px;padding:18px;display:flex;gap:16px;align-items:center;cursor:pointer">' +
    '<div style="flex:1;min-width:0">' +
      '<div style="display:flex;align-items:center;gap:8px;margin-bottom:10px;flex-wrap:wrap">' +
        it.lignes.map(lineBadge).join('') + (rec ? recommendedBadge() : '') +
      '</div>' +
      '<div style="display:flex;align-items:baseline;gap:10px;flex-wrap:wrap">' +
        '<span style="font:600 16px \'Libre Franklin\';color:' + C.ink + '">' + esc(title) + '</span>' +
        '<span style="font:600 13px \'IBM Plex Mono\';color:' + C.mut + '">' + it.duree_min + ' min' + (creneau(it) ? ' · ' + creneau(it) : '') + '</span>' +
      '</div>' +
      '<div style="display:flex;flex-wrap:wrap;gap:7px;margin-top:11px">' + alts.map(alertPillSmall).join('') + '</div>' +
    '</div>' +
    '<div style="display:flex;flex-direction:column;align-items:center;gap:6px;flex-shrink:0">' +
      gauge(sc, 50, 5) +
      '<span style="font:600 11px \'Libre Franklin\';color:' + band.color + '">' + band.label + '</span>' +
    '</div>' +
  '</div>';
}

// ── Card style B – Carte ──────────────────────────────────────────────────────

function cardB(it, idx) {
  var sc    = it.score_confort;
  var band  = bandFor(sc);
  var rec   = estMeilleur(it);
  var title = buildTitle(it.lignes, it.nb_correspondances);
  var alts  = it.business_summary.alertes.slice(0, 3);

  return '<div onclick="selectIt(' + idx + ')" style="position:relative;background:#fff;border:1px solid #eaedf1;border-radius:18px;padding:20px 20px 20px 26px;cursor:pointer;box-shadow:0 6px 20px rgba(20,40,80,.06);overflow:hidden">' +
    '<div style="position:absolute;left:0;top:0;bottom:0;width:4px;background:' + band.color + '"></div>' +
    '<div style="display:flex;align-items:flex-start;gap:16px">' +
      '<div style="flex:1;min-width:0">' +
        '<div style="display:flex;align-items:center;gap:8px;margin-bottom:12px;flex-wrap:wrap">' +
          it.lignes.map(lineBadge).join('') + (rec ? recommendedBadge() : '') +
        '</div>' +
        '<div style="display:flex;align-items:baseline;gap:10px;flex-wrap:wrap;margin-bottom:14px">' +
          '<span style="font:700 17px \'Libre Franklin\';color:' + C.ink + '">' + esc(title) + '</span>' +
          '<span style="font:600 13px \'IBM Plex Mono\';color:' + C.mut + '">' + it.duree_min + ' min' + (creneau(it) ? ' · ' + creneau(it) : '') + '</span>' +
        '</div>' +
        '<div style="display:flex;flex-direction:column;gap:9px">' + alts.map(alertRow).join('') + '</div>' +
      '</div>' +
      '<div style="display:flex;flex-direction:column;align-items:center;gap:7px;flex-shrink:0">' +
        gauge(sc, 76, 7) +
        '<span style="font:600 11px \'Libre Franklin\';color:' + band.color + '">' + band.label + '</span>' +
      '</div>' +
    '</div>' +
  '</div>';
}

// ── Card style C – Comparatif ─────────────────────────────────────────────────

function cardC(it, idx) {
  var sc    = it.score_confort;
  var band  = bandFor(sc);
  var rec   = estMeilleur(it);
  var title = buildTitle(it.lignes, it.nb_correspondances);
  var alts  = it.business_summary.alertes.slice(0, 2);
  var rowBg = rec ? 'background:#eef6f1;border:1px solid #cfe6da' : 'background:transparent;border:1px solid transparent';

  return '<div onclick="selectIt(' + idx + ')" style="display:flex;align-items:center;gap:14px;padding:14px;border-radius:12px;cursor:pointer;' + rowBg + '">' +
    '<div style="width:92px;flex-shrink:0">' +
      '<div style="display:flex;gap:6px;margin-bottom:7px;flex-wrap:wrap">' + it.lignes.map(lineBadge).join('') + '</div>' +
      '<div style="font:500 12px \'IBM Plex Mono\';color:' + C.faint + '">' + it.duree_min + ' min' + (creneau(it) ? '<br>' + creneau(it) : '') + '</div>' +
    '</div>' +
    '<div style="flex:1;min-width:0">' +
      '<div style="display:flex;align-items:center;gap:8px;margin-bottom:9px;flex-wrap:wrap">' +
        '<span style="font:600 14px \'Libre Franklin\';color:' + C.ink + '">' + esc(title) + '</span>' +
        (rec ? recommendedBadge('sm') : '') +
      '</div>' +
      bar(sc) +
      '<div style="display:flex;flex-wrap:wrap;gap:5px 12px;margin-top:10px">' + alts.map(alertInline).join('') + '</div>' +
    '</div>' +
    '<div style="flex-shrink:0;display:flex;align-items:baseline;gap:2px;width:52px;justify-content:flex-end">' +
      '<span style="font:700 22px \'IBM Plex Mono\';color:' + band.color + '">' + sc + '</span>' +
      '<span style="font:500 12px \'IBM Plex Mono\';color:' + C.faint + '">/10</span>' +
    '</div>' +
  '</div>';
}

// ── Header ────────────────────────────────────────────────────────────────────

function header() {
  return '<header style="position:sticky;top:0;z-index:20;background:rgba(244,246,248,.82);backdrop-filter:blur(10px);-webkit-backdrop-filter:blur(10px);border-bottom:1px solid ' + C.line + '">' +
    '<div style="max-width:760px;margin:0 auto;padding:13px 20px;display:flex;align-items:center;justify-content:space-between;gap:14px">' +
      '<div onclick="goSearch()" style="display:flex;align-items:center;gap:10px;cursor:pointer">' +
        '<div style="width:32px;height:32px;border-radius:10px;background:' + C.primary + ';display:flex;align-items:center;justify-content:center">' + icon('nav', 17, '#fff', 2.2) + '</div>' +
        '<div>' +
          '<div style="font:700 17px/1 \'Libre Franklin\';color:' + C.ink + ';letter-spacing:-.01em">confort<span style="color:' + C.primary + '">+</span></div>' +
          '<div style="font:500 9px/1 \'IBM Plex Mono\';color:' + C.faint + ';margin-top:4px;letter-spacing:.12em">COUCHE MOBILITÉS</div>' +
        '</div>' +
      '</div>' +
      (S.screen === 'results' ? switcher() : '') +
    '</div>' +
  '</header>';
}

// ── Time mode helper ──────────────────────────────────────────────────────────

function _timeModeBtn(mode, label) {
  var on = S.timeMode === mode;
  return '<button onclick="setTimeMode(\'' + mode + '\')" style="flex:1;display:flex;align-items:center;justify-content:center;gap:6px;padding:9px 10px;border-radius:10px;font:600 12px \'Libre Franklin\';border:' + (on ? '1.5px solid ' + C.primary : '1px solid ' + C.line) + ';background:' + (on ? '#eaf0fb' : '#f8f9fb') + ';color:' + (on ? C.primary : C.mut) + ';transition:all .15s;white-space:nowrap">' + label + '</button>';
}

// ── Screen: Search ────────────────────────────────────────────────────────────

function screenSearch() {
  var errHtml = S.error
    ? '<div style="background:#fef3f2;border:1px solid #fecdca;border-radius:12px;padding:14px 16px;margin-bottom:16px;display:flex;align-items:center;gap:10px;font:500 14px \'Libre Franklin\';color:' + C.red + '">' + icon('alert', 16, C.red, 2.2) + '<span>' + esc(S.error) + '</span></div>'
    : '';

  return '<div class="fade-up" style="max-width:520px;margin:0 auto">' +
    '<div style="margin:14px 0 22px">' +
      '<h1 style="font:700 28px/1.15 \'Libre Franklin\';letter-spacing:-.02em;margin:0 0 8px">Où allez-vous ?</h1>' +
      '<p style="font:400 15px/1.5 \'Libre Franklin\';color:' + C.mut + ';margin:0">Le confort de chaque itinéraire, évalué avant le départ — affluence, accessibilité, climatisation.</p>' +
    '</div>' +
    errHtml +

    // Station inputs card
    '<div style="background:#fff;border:1px solid ' + C.line + ';border-radius:16px;position:relative;box-shadow:0 1px 2px rgba(20,40,80,.04)">' +
      // From row — position:relative for the autocomplete dropdown
      '<div id="ac-from-row" style="display:flex;align-items:center;gap:12px;padding:15px 56px 15px 16px;position:relative">' +
        icon('pin', 16, C.green, 2.2) +
        '<input id="inp-from" value="' + esc(S.from) + '" oninput="S.from=this.value" onkeydown="if(event.key===\'Enter\'&&!acActive(\'from\'))doSearch()" placeholder="Départ" autocomplete="off" style="border:none;outline:none;background:transparent;font:500 16px \'Libre Franklin\';color:' + C.ink + ';width:100%"/>' +
      '</div>' +
      '<div style="height:1px;background:#eef1f4;margin:0 16px"></div>' +
      // To row
      '<div id="ac-to-row" style="display:flex;align-items:center;gap:12px;padding:15px 56px 15px 16px;position:relative">' +
        icon('pin', 16, C.red, 2.2) +
        '<input id="inp-to" value="' + esc(S.to) + '" oninput="S.to=this.value" onkeydown="if(event.key===\'Enter\'&&!acActive(\'to\'))doSearch()" placeholder="Arrivée" autocomplete="off" style="border:none;outline:none;background:transparent;font:500 16px \'Libre Franklin\';color:' + C.ink + ';width:100%"/>' +
      '</div>' +
      '<button onclick="swapStations()" style="position:absolute;right:14px;top:50%;transform:translateY(-50%);width:36px;height:36px;border-radius:10px;border:1px solid ' + C.line + ';background:#fff;display:flex;align-items:center;justify-content:center;cursor:pointer;box-shadow:0 1px 2px rgba(20,40,80,.06)">' + icon('swap', 16, C.mut, 2) + '</button>' +
    '</div>' +

    // Time mode selector
    '<div style="background:#fff;border:1px solid ' + C.line + ';border-radius:16px;padding:14px 16px;margin-top:12px">' +
      '<div style="display:flex;gap:6px;margin-bottom:' + (S.timeMode === 'now' ? '0' : '12') + 'px">' +
        _timeModeBtn('now',    icon('clock', 14, S.timeMode === 'now'    ? C.primary : C.faint, 2.2) + ' Maintenant') +
        _timeModeBtn('depart', icon('arrow', 14, S.timeMode === 'depart' ? C.primary : C.faint, 2.2) + ' Partir à') +
        _timeModeBtn('arrive', icon('back',  14, S.timeMode === 'arrive' ? C.primary : C.faint, 2.2) + ' Arriver à') +
      '</div>' +
      (S.timeMode !== 'now'
        ? (function() {
            var lblTime = S.timeMode === 'depart' ? 'Heure de départ' : 'Heure d\'arrivée souhaitée';
            var minD = todayStr();
            var maxD = maxDateStr();
            return '<div onclick="openDatePicker()" style="display:flex;align-items:center;gap:12px;padding:10px 0;border-top:1px solid #f0f3f6;cursor:pointer">' +
              icon('calendar', 18, C.primary, 2.2) +
              '<span style="font:500 13px \'Libre Franklin\';color:' + C.mut + ';flex:1">Date</span>' +
              '<input type="date" id="inp-date" value="' + esc(S.date) + '" min="' + minD + '" max="' + maxD + '" oninput="S.date=this.value" onclick="event.stopPropagation()" style="width:148px;text-align:right;border:none;background:transparent;outline:none;font:600 15px \'IBM Plex Mono\';color:' + C.ink + ';cursor:pointer"/>' +
            '</div>' +
            '<div onclick="openTimePicker()" style="display:flex;align-items:center;gap:12px;padding:10px 0;border-top:1px solid #f0f3f6;cursor:pointer">' +
              icon('clock', 18, C.primary, 2.2) +
              '<span style="font:500 13px \'Libre Franklin\';color:' + C.mut + ';flex:1">' + lblTime + '</span>' +
              '<input type="time" id="inp-time" value="' + esc(S.time) + '" oninput="S.time=this.value" onclick="event.stopPropagation()" style="width:84px;text-align:right;border:none;background:transparent;outline:none;font:600 15px \'IBM Plex Mono\';color:' + C.ink + ';cursor:pointer"/>' +
            '</div>';
          })()
        : ''
      ) +
    '</div>' +

    // Search button
    '<button onclick="doSearch()" ' + (S.loading ? 'disabled' : '') + ' style="width:100%;margin-top:16px;display:flex;align-items:center;justify-content:center;gap:9px;padding:16px;border:none;border-radius:14px;background:' + C.primary + ';color:#fff;font:600 16px \'Libre Franklin\';cursor:' + (S.loading ? 'wait' : 'pointer') + ';box-shadow:0 5px 16px rgba(21,66,138,.26);opacity:' + (S.loading ? '.7' : '1') + '">' +
      (S.loading ? '<div class="spinner"></div> Recherche en cours…' : icon('search', 18, '#fff', 2.4) + ' Rechercher') +
    '</button>' +

    '<div style="text-align:center;margin-top:14px;font:500 13px \'Libre Franklin\';color:' + C.faint + '">Sans compte · sans données personnelles</div>' +
  '</div>';
}

// acActive: returns true if the autocomplete dropdown for a field is open and has an active item
function acActive(field) {
  var dd = document.getElementById('ac-dd-tmp-' + field);
  // Since we don't track dd by id, check via acState — simplified: always false so Enter submits
  return false;
}

// ── Screen: Results ───────────────────────────────────────────────────────────

function screenResults() {
  var all  = S.results.itineraires;
  var opts = filteredItineraires();

  if (!all.length) {
    return '<div class="fade-up">' +
      '<div onclick="goSearch()" style="font:600 14px \'Libre Franklin\';color:' + C.primary + ';cursor:pointer;margin-bottom:20px;display:inline-flex;align-items:center;gap:6px">' + icon('back', 16, C.primary, 2.2) + ' Modifier la recherche</div>' +
      '<div style="text-align:center;padding:48px 20px;background:#fff;border:1px dashed #cdd4dd;border-radius:16px;color:' + C.faint + ';font:500 14px \'Libre Franklin\'">Aucun itinéraire trouvé. Essayez d\'autres stations ou une autre heure.</div>' +
    '</div>';
  }

  var cardsHtml;
  if (!opts.length) {
    cardsHtml = '<div style="text-align:center;padding:48px 20px;background:#fff;border:1px dashed #cdd4dd;border-radius:16px;color:' + C.faint + ';font:500 14px \'Libre Franklin\'">Aucun itinéraire ne correspond à ces filtres.</div>';
  } else if (S.cardStyle === 'A') {
    cardsHtml = '<div style="display:flex;flex-direction:column;gap:12px">' + opts.map(function(it) { return cardA(it, all.indexOf(it)); }).join('') + '</div>';
  } else if (S.cardStyle === 'B') {
    cardsHtml = '<div style="display:flex;flex-direction:column;gap:14px">' + opts.map(function(it) { return cardB(it, all.indexOf(it)); }).join('') + '</div>';
  } else {
    cardsHtml = '<div style="background:#fff;border:1px solid ' + C.line + ';border-radius:18px;padding:10px;display:flex;flex-direction:column;gap:4px">' + opts.map(function(it) { return cardC(it, all.indexOf(it)); }).join('') + '</div>';
  }

  return '<div class="fade-up">' +
    '<div onclick="goSearch()" style="display:flex;align-items:center;gap:14px;background:#fff;border:1px solid ' + C.line + ';border-radius:14px;padding:14px 16px;cursor:pointer;margin-bottom:18px">' +
      '<div style="flex:1;min-width:0">' +
        '<div style="display:flex;align-items:center;gap:8px;font:600 15px \'Libre Franklin\';color:' + C.ink + ';flex-wrap:wrap">' +
          '<span style="white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:180px">' + esc(S.from) + '</span>' +
          icon('arrow', 16, C.faint, 2) +
          '<span style="white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:180px">' + esc(S.to) + '</span>' +
        '</div>' +
        '<div style="font:500 12px \'IBM Plex Mono\';color:' + C.faint + ';margin-top:5px">' + formatDateShort(S.date) + ' · ' + (S.timeMode === 'arrive' ? 'Arriver à ' : 'Départ ') + esc(S.time) + ' · ' + all.length + ' itinéraire' + (all.length > 1 ? 's' : '') + '</div>' +
      '</div>' +
      '<div style="font:600 13px \'Libre Franklin\';color:' + C.primary + ';flex-shrink:0">Modifier</div>' +
    '</div>' +

    '<div style="display:flex;align-items:baseline;justify-content:space-between;gap:12px;margin-bottom:11px">' +
      '<div style="font:600 12px \'Libre Franklin\';color:' + C.mut + ';text-transform:uppercase;letter-spacing:.05em">Filtres confort</div>' +
      '<div style="font:500 12px \'IBM Plex Mono\';color:' + C.faint + '">' + opts.length + ' / ' + all.length + '</div>' +
    '</div>' +
    '<div style="display:flex;flex-wrap:wrap;gap:8px">' + filterChips() + '</div>' +
    filterReasons() +
    '<div style="margin-top:20px">' + cardsHtml + '</div>' +
  '</div>';
}

// ── Screen: Detail ────────────────────────────────────────────────────────────

function screenDetail() {
  var it = S.results && S.results.itineraires[S.selectedIdx];
  if (!it) { S.screen = 'results'; render(); return ''; }

  var sc    = it.score_confort;
  var band  = bandFor(sc);
  var rec   = estMeilleur(it);
  var title = buildTitle(it.lignes, it.nb_correspondances);
  var d     = it.dimensions;

  var dims = [
    { label: 'Affluence',       weight: 35,   score: d.affluence.score,       extra: d.affluence.label },
    { label: 'Accessibilité',   weight: 30,   score: d.accessibilite.score,   extra: accessibiliteLabel(d.accessibilite) },
    { label: 'Correspondances', weight: 20,   score: d.correspondances.score, extra: d.correspondances.nb === 0 ? 'Direct' : (d.correspondances.nb + ' corresp.') },
    { label: 'Équipements',     weight: 15,   score: d.equipements.score,     extra: [d.equipements.toilettes && 'toilettes', d.equipements.fontaines && 'fontaines'].filter(Boolean).join(', ') || 'aucun' },
    { label: 'Climatisation',   weight: null, score: d.climatisation.score,   extra: d.climatisation.label },
    { label: 'Annonces',        weight: null, score: d.accessibilite_sensorielle.score, extra: d.accessibilite_sensorielle.label },
  ];
  if (d.meteo && (d.meteo.alertes.length > 0 || d.meteo.score < 10)) {
    dims.push({ label: 'Météo', weight: null, score: d.meteo.score, extra: d.meteo.temperature !== null ? Math.round(d.meteo.temperature) + '°C' : '' });
  }

  var dimsHtml = dims.map(function(dim) {
    return '<div>' +
      '<div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:8px">' +
        '<div style="display:flex;align-items:center;gap:8px">' +
          '<span style="font:600 14px \'Libre Franklin\';color:' + C.ink + '">' + dim.label + '</span>' +
          '<span style="font:500 11px \'IBM Plex Mono\';color:' + C.faint + ';background:#f4f6f8;border-radius:6px;padding:2px 6px">' + (dim.weight ? dim.weight + '%' : 'info') + '</span>' +
          (dim.extra ? '<span style="font:400 12px \'Libre Franklin\';color:' + C.faint + '">' + esc(dim.extra) + '</span>' : '') +
        '</div>' +
        '<span style="font:600 13px \'IBM Plex Mono\';color:' + C.mut + '">' + dim.score + '/10</span>' +
      '</div>' +
      bar(dim.score) +
    '</div>';
  }).join('');

  // Journey steps
  var segs     = it.sections_resume || [];
  var segsHtml = '';
  if (segs.length) {
    var items = segs.map(function(seg, i) {
      var isLast = i === segs.length - 1;
      var ic, lbl, sub, badge;
      if (seg.kind === 'walk') {
        ic = 'walk'; lbl = 'Marche'; sub = seg.to ? 'Vers ' + seg.to : seg.duration_min + ' min'; badge = '';
      } else if (seg.kind === 'transfer') {
        ic = 'transfer'; lbl = 'Correspondance'; sub = seg.to ? 'Vers ' + seg.to : seg.duration_min + ' min'; badge = '';
      } else {
        ic = 'nav'; lbl = seg.ligne ? formatLine(seg.ligne) : 'Transport'; sub = seg.to ? 'Direction ' + seg.to : ''; badge = seg.ligne ? lineBadge(seg.ligne) : '';
      }
      return '<div style="display:flex;gap:14px">' +
        '<div style="display:flex;flex-direction:column;align-items:center;width:34px;flex-shrink:0">' +
          '<div style="width:34px;height:34px;border-radius:10px;background:#f4f6f8;border:1px solid ' + C.line + ';display:flex;align-items:center;justify-content:center">' + icon(ic, 16, C.mut, 2) + '</div>' +
          (!isLast ? '<div style="flex:1;width:2px;background:' + C.line + ';margin:4px 0;min-height:14px"></div>' : '') +
        '</div>' +
        '<div style="flex:1;padding-bottom:' + (isLast ? '4' : '18') + 'px">' +
          '<div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap">' +
            badge +
            '<span style="font:600 14px \'Libre Franklin\';color:' + C.ink + '">' + esc(lbl) + '</span>' +
            '<span style="font:500 12px \'IBM Plex Mono\';color:' + C.faint + '">' + seg.duration_min + ' min</span>' +
          '</div>' +
          (sub ? '<div style="font:400 13px \'Libre Franklin\';color:' + C.mut + ';margin-top:3px">' + esc(sub) + '</div>' : '') +
        '</div>' +
      '</div>';
    }).join('');

    segsHtml = '<div style="background:#fff;border:1px solid ' + C.line + ';border-radius:18px;padding:22px;margin-top:14px">' +
      '<div style="font:700 15px \'Libre Franklin\';color:' + C.ink + ';margin-bottom:18px">Votre trajet</div>' +
      '<div style="display:flex;flex-direction:column">' + items + '</div>' +
    '</div>';
  }

  var pertHtml = '';
  if (it.perturbations && it.perturbations.length) {
    pertHtml = '<div style="background:#fff;border:1px solid ' + C.line + ';border-radius:18px;padding:22px;margin-top:14px">' +
      '<div style="font:700 15px \'Libre Franklin\';color:' + C.ink + ';margin-bottom:14px">Perturbations</div>' +
      it.perturbations.map(function(p) {
        return '<div style="display:flex;gap:11px;background:#fef3f2;border:1px solid #fecdca;border-radius:10px;padding:12px 14px;margin-bottom:8px">' +
          '<div>' + icon('alert', 16, C.red, 2.2) + '</div>' +
          '<div><div style="font:600 12px \'Libre Franklin\';color:' + C.red + ';margin-bottom:2px">' + esc(p.severite) + '</div>' +
          '<div style="font:400 13px \'Libre Franklin\';color:' + C.mut + '">' + esc(p.message) + '</div></div></div>';
      }).join('') +
    '</div>';
  }

  return '<div class="fade-up" style="max-width:560px;margin:0 auto">' +
    '<button onclick="goResults()" style="display:inline-flex;align-items:center;gap:7px;background:none;border:none;cursor:pointer;font:600 14px \'Libre Franklin\';color:' + C.ink + ';padding:0;margin-bottom:18px">' +
      icon('back', 18, C.ink, 2.2) + ' Retour aux itinéraires' +
    '</button>' +

    '<div style="background:#fff;border:1px solid ' + C.line + ';border-radius:18px;padding:22px;box-shadow:0 1px 2px rgba(20,40,80,.04)">' +
      '<div style="display:flex;align-items:flex-start;gap:18px">' +
        '<div style="flex:1;min-width:0">' +
          '<div style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:12px">' +
            it.lignes.map(lineBadge).join('') + (rec ? recommendedBadge() : '') +
          '</div>' +
          '<div style="font:700 20px \'Libre Franklin\';color:' + C.ink + ';margin-bottom:5px">' + esc(title) + '</div>' +
          '<div style="font:500 13px \'IBM Plex Mono\';color:' + C.mut + '">' + esc(S.from) + ' → ' + esc(S.to) + ' · ' + it.duree_min + ' min' + (creneau(it) ? ' · ' + creneau(it) : '') + '</div>' +
        '</div>' +
        '<div style="display:flex;flex-direction:column;align-items:center;gap:8px;flex-shrink:0">' +
          gauge(sc, 76, 7) +
          '<span style="font:600 11px \'Libre Franklin\';color:' + band.color + '">' + band.label + '</span>' +
        '</div>' +
      '</div>' +
    '</div>' +

    '<div style="background:#fff;border:1px solid ' + C.line + ';border-radius:18px;padding:22px;margin-top:14px">' +
      '<div style="font:700 15px \'Libre Franklin\';color:' + C.ink + ';margin-bottom:3px">Détail du score de confort</div>' +
      '<div style="font:400 13px \'Libre Franklin\';color:' + C.faint + ';margin-bottom:18px">Score pondéré sur 4 dimensions actives</div>' +
      '<div style="display:flex;flex-direction:column;gap:16px">' + dimsHtml + '</div>' +
    '</div>' +

    segsHtml + pertHtml +
  '</div>';
}

// ── Actions ───────────────────────────────────────────────────────────────────

function goSearch() { S.screen = 'search'; S.error = null; render(); }

function goResults() {
  if (S.results) { S.screen = 'results'; render(); window.scrollTo(0, 0); }
  else goSearch();
}

function selectIt(idx) {
  S.selectedIdx = idx;
  S.screen      = 'detail';
  render();
  window.scrollTo(0, 0);
}

function swapStations() { var t = S.from; S.from = S.to; S.to = t; render(); }
function setCardStyle(s) { S.cardStyle = s; render(); }
function toggleFilter(k) { S.filters[k] = !S.filters[k]; render(); }

function doSearch() {
  if (!S.from.trim() || !S.to.trim()) {
    S.error = 'Veuillez renseigner le départ et l\'arrivée.';
    render();
    return;
  }
  // Validation date (modes depart / arrive uniquement)
  if (S.timeMode !== 'now' && S.date) {
    if (S.date < todayStr()) {
      S.error = 'La date ne peut pas être dans le passé.';
      render();
      return;
    }
    if (S.date > maxDateStr()) {
      S.error = 'Les prévisions sont limitées à 16 jours.';
      render();
      return;
    }
  }
  // Reset filters for the new search
  S.filters = { access: false, crowd: false, air: false };
  fetchItineraries();
}

// ── API ───────────────────────────────────────────────────────────────────────

function fetchItineraries() {
  S.loading = true;
  S.error   = null;
  render();

  var dt   = buildDatetime();
  var repr = buildDatetimeRepresents();

  // Snapshot the display time/date for the results header
  if (S.timeMode === 'now') {
    var nowD = new Date();
    S.time = pad(nowD.getHours()) + ':' + pad(nowD.getMinutes());
    S.date = todayStr();
  }

  fetch('/itineraries', {
    method:  'POST',
    headers: { 'Content-Type': 'application/json' },
    body:    JSON.stringify({ depart: S.from, arrivee: S.to, datetime: dt, datetime_represents: repr }),
  })
  .then(function(res) {
    return res.json().then(function(data) {
      if (!res.ok) throw new Error(data.detail || 'Erreur ' + res.status);
      return data;
    });
  })
  .then(function(data) {
    S.results     = data;
    S.screen      = 'results';
    S.selectedIdx = 0;
    S.loading     = false;
    S.error       = null;
    syncFilters(); // reset any filter no longer applicable
    render();
  })
  .catch(function(e) {
    S.loading = false;
    S.error   = e.message;
    render();
  });
}

// ── Render ────────────────────────────────────────────────────────────────────

function render() {
  var main;
  if      (S.screen === 'results' && S.results) main = screenResults();
  else if (S.screen === 'detail'  && S.results) main = screenDetail();
  else                                           main = screenSearch();

  document.getElementById('app').innerHTML =
    header() +
    '<main style="max-width:760px;margin:0 auto;padding:24px 20px 72px">' + main + '</main>';

  initAutocomplete();
}

// ── Init ──────────────────────────────────────────────────────────────────────

render();
