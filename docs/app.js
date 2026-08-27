/* Coal Cover — static dashboard over the CEA daily coal stock report.
   All data comes from JSON written into ./data by the scheduled job. */

const BANDS = [
  ['supercritical', 0,   3,   '--c-supercritical'],
  ['critical',      3,   7,   '--c-critical'],
  ['low',           7,   12,  '--c-low'],
  ['adequate',      12,  20,  '--c-adequate'],
  ['comfortable',   20,  1e9, '--c-comfortable'],
];

const css = n => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
const $ = id => document.getElementById(id);
const fmt = (v, d = 1) => v === null || v === undefined || Number.isNaN(v)
  ? '\u2013' : Number(v).toLocaleString('en-IN', { minimumFractionDigits: d, maximumFractionDigits: d });
const int = v => v === null || v === undefined ? '\u2013' : Math.round(v).toLocaleString('en-IN');

function bandOf(days) {
  if (days === null || days === undefined) return ['unknown', '--c-unknown'];
  const b = BANDS.find(([, lo, hi]) => days >= lo && days < hi) || BANDS[BANDS.length - 1];
  return [b[0], b[3]];
}

const state = {
  index: null, day: null, prev: null, trend: null, series: null,
  baseline: 'prev', baselineDate: null,
  sort: { key: 'cover', dir: 'asc' },
  selected: null,
  charts: {},
};

const filters = {
  q: '', coverMin: 0, coverMax: 999, basisActual: false,
  state: [], utility: [], ownership: [], section: [], mode: [],
  critical: false, noreceipt: false, drawdown: false, imported: false,
  includeIdle: false,
};

/* ---------- loading ---------- */

async function json(path) {
  const r = await fetch(path, { cache: 'no-cache' });
  if (!r.ok) throw new Error(`${path} returned ${r.status}`);
  return r.json();
}

async function boot() {
  try {
    state.index = await json('data/index.json');
  } catch (e) {
    document.body.insertAdjacentHTML('afterbegin',
      `<div class="banner">No data yet. Run <code>python -m scraper.cli update</code> (or wait for the scheduled job) to populate ./docs/data.</div>`);
    return;
  }
  $('built').textContent = (state.index.generated || '').replace('T', ' ').replace('Z', ' UTC');

  const sel = $('date-select');
  sel.innerHTML = state.index.dates.slice().reverse()
    .map(d => `<option value="${d}">${prettyDate(d)}</option>`).join('');
  sel.addEventListener('change', () => loadDate(sel.value));

  state.trend = await json('data/trend.json').catch(() => []);
  json('data/manifest.json').then(renderDownloads).catch(() => {});

  const wanted = new URLSearchParams(location.hash.slice(1)).get('date');
  const start = state.index.dates.includes(wanted) ? wanted : state.index.latest;
  sel.value = start;
  await loadDate(start);
  wireControls();
  readHash();
}

function prettyDate(iso) {
  return new Date(iso + 'T00:00:00Z').toLocaleDateString('en-IN',
    { day: 'numeric', month: 'short', year: 'numeric', timeZone: 'UTC' });
}

// The comparison date is the latest report on or before the target, so a
// gap in publication shifts the baseline rather than blanking the deltas.
function resolveBaseline(date) {
  const dates = state.index.dates;
  const i = dates.indexOf(date);
  if (i <= 0) return null;
  if (state.baseline === 'prev') return dates[i - 1];
  if (state.baseline === 'first') return dates[0];
  const back = Number(state.baseline);
  const target = new Date(date + 'T00:00:00Z');
  target.setUTCDate(target.getUTCDate() - back);
  const iso = target.toISOString().slice(0, 10);
  const earlier = dates.slice(0, i).filter(d => d <= iso);
  return earlier.length ? earlier[earlier.length - 1] : dates[0];
}

async function loadDate(date) {
  state.day = await json(`data/daily/${date}.json`);
  state.baselineDate = resolveBaseline(date);
  state.prev = state.baselineDate
    ? await json(`data/daily/${state.baselineDate}.json`).catch(() => null) : null;
  $('demo-banner').hidden = !state.day.demo;
  $('source-link').href =
    `https://npp.gov.in/public-reports/cea/daily/fuel/${date.split('-').reverse().join('-')}/dailyCoal1-${date}.pdf`;
  buildFacets();
  renderAll();
  writeHash();
}

/* ---------- filtering ---------- */

const cover = p => filters.basisActual ? p.cover_days_actual : p.cover_days_normative;

function apply() {
  const q = filters.q.trim().toLowerCase();
  return state.day.plants.filter(p => {
    const c = cover(p);
    // Section C stations are mothballed: they report zero stock and zero burn,
    // which would otherwise park them at the head of every cover ranking.
    if (!filters.includeIdle && p.section === 'C' && !filters.section.includes('C')) return false;
    if (q && !(`${p.plant} ${p.state} ${p.utility}`.toLowerCase().includes(q))) return false;
    if (filters.coverMin > 0 || filters.coverMax < 999) {
      if (c === null || c === undefined) return false;
      if (c < filters.coverMin || c > filters.coverMax) return false;
    }
    if (filters.state.length && !filters.state.includes(p.state)) return false;
    if (filters.utility.length && !filters.utility.includes(p.utility)) return false;
    if (filters.ownership.length && !filters.ownership.includes(p.ownership)) return false;
    if (filters.section.length && !filters.section.includes(p.section)) return false;
    if (filters.mode.length && !filters.mode.includes(p.mode_of_transport)) return false;
    if (filters.critical && !p.is_critical) return false;
    if (filters.noreceipt && !p.no_receipt) return false;
    if (filters.drawdown && !(p.net_change_kt !== null && p.net_change_kt < 0)) return false;
    if (filters.imported && !(p.stock_import_kt > 0)) return false;
    return true;
  });
}

function buildFacets() {
  const uniq = key => [...new Set(state.day.plants.map(p => p[key]).filter(Boolean))].sort();
  fill('f-state', uniq('state'));
  fill('f-utility', uniq('utility'));
  fill('f-ownership', uniq('ownership'));
  fill('f-mode', uniq('mode_of_transport'));
  const secs = [...new Set(state.day.plants.map(p => p.section))].sort();
  const label = { A: 'A \u2014 domestic coal', B: 'B \u2014 imported coal', C: 'C \u2014 not in operation', D: 'D \u2014 washery rejects' };
  $('f-section').innerHTML = secs.map(s => `<option value="${s}">${label[s] || s}</option>`).join('');
}

function fill(id, values) {
  const el = $(id);
  const keep = new Set([...el.selectedOptions].map(o => o.value));
  el.innerHTML = values.map(v => `<option value="${esc(v)}"${keep.has(v) ? ' selected' : ''}>${esc(v)}</option>`).join('');
}

const esc = s => String(s).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));

/* ---------- render ---------- */

function activeFilterCount() {
  let n = 0;
  if (filters.q) n++;
  if (filters.coverMin > 0 || filters.coverMax < 999) n++;
  ['state', 'utility', 'ownership', 'section', 'mode'].forEach(k => { if (filters[k].length) n++; });
  ['critical', 'noreceipt', 'drawdown', 'imported', 'includeIdle'].forEach(k => { if (filters[k]) n++; });
  return n;
}

function renderDownloads(manifest) {
  const list = (manifest.partitions || []).slice().reverse();
  $('dl-list').innerHTML = list.map(f => {
    const month = f.split('/').pop().replace('.csv', '');
    const label = new Date(month + '-01T00:00:00Z').toLocaleDateString('en-IN',
      { month: 'long', year: 'numeric', timeZone: 'UTC' });
    return `<li><a href="data/${f}" download>${label}</a></li>`;
  }).join('');
}

function renderAll() {
  const rows = apply();
  const n = activeFilterCount();
  $('filter-count').textContent = n ? `(${n})` : '';
  renderKpis(rows);
  renderStrip(rows);
  renderTable(rows);
  renderTrend();
  renderStateChart(rows);
}

function renderKpis(rows) {
  const s = state.day.summary;
  const prev = state.prev && state.prev.summary;
  const sum = (k) => rows.reduce((a, p) => a + (p[k] || 0), 0);
  const shown = rows.length !== state.day.plants.length;

  const cards = [
    ['Stations shown', int(rows.length), shown ? `of ${state.day.plants.length} in report` : 'all in report', null],
    ['Coal stock', fmt(sum('stock_total_kt') / 1000, 2), 'million t',
      prev ? delta((s.stock_total_kt - prev.stock_total_kt) / 1000, 'Mt', 2) : null],
    ['All-India cover', fmt(s.cover_days_normative, 1), 'days',
      prev ? delta(s.cover_days_normative - prev.cover_days_normative, 'd', 1) : null],
    ['Stock vs normative', fmt(s.pct_of_norm, 0) + '%', '',
      prev ? delta(s.pct_of_norm - prev.pct_of_norm, 'pp', 0) : null],
    ['Critical stations', int(rows.filter(p => p.is_critical).length), 'under 25%',
      prev ? delta(s.critical - prev.critical, '', 0, true) : null],
    ['Under 7 days cover', int(rows.filter(p => (cover(p) ?? 999) < 7).length), 'stations',
      prev ? delta(s.under_7_days - prev.under_7_days, '', 0, true) : null],
    ['Capacity at risk', int(rows.filter(p => (cover(p) ?? 999) < 7).reduce((a, p) => a + (p.capacity_mw || 0), 0) / 1000), 'GW under 7 days', null],
    ['Net movement', fmt(sum('receipt_kt') - sum('consumption_kt'), 0), "'000 t receipts less burn", null],
  ];

  $('kpis').innerHTML = cards.map(([label, value, unit, d]) => `
    <dl class="kpi">
      <dt>${label}</dt>
      <dd>${value}${unit ? `<small>${unit}</small>` : ''}</dd>
      ${d || ''}
    </dl>`).join('');
}

// For counts of stressed plants, a rise is bad — invert the colour.
function delta(v, unit, dp, inverse = false) {
  if (v === null || v === undefined || Number.isNaN(v)) return '';
  const good = inverse ? v < 0 : v > 0;
  const cls = Math.abs(v) < (dp ? 0.05 : 0.5) ? 'flat' : (good ? 'up' : 'down');
  const sign = v > 0 ? '+' : '';
  const since = state.baselineDate ? ` vs ${prettyDate(state.baselineDate)}` : '';
  return `<span class="delta ${cls}">${sign}${fmt(v, dp)}${unit ? ' ' + unit : ''}${since}</span>`;
}

function renderStrip(rows) {
  const sorted = rows.slice().sort((a, b) => (cover(a) ?? 1e9) - (cover(b) ?? 1e9));
  const maxCap = Math.max(1, ...sorted.map(p => p.capacity_mw || 0));
  const strip = $('strip');
  strip.innerHTML = sorted.map(p => {
    const c = cover(p);
    const [, varName] = bandOf(c);
    // Height reads cover (capped at 30 days); width reads capacity.
    const h = Math.max(6, Math.min(100, ((c ?? 30) / 30) * 100));
    const grow = 0.35 + 0.65 * ((p.capacity_mw || 0) / maxCap);
    return `<b data-id="${p.id}" style="height:${h}%;flex-grow:${grow.toFixed(3)};background:var(${varName})"></b>`;
  }).join('');
  $('strip-caption').textContent = sorted.length
    ? `${sorted.length} stations, shortest cover on the left. Bar height is days of cover, width is capacity.`
    : 'No stations match the current filters.';

  strip.querySelectorAll('b').forEach(b => {
    b.addEventListener('mouseenter', e => showTip(e, b.dataset.id));
    b.addEventListener('mousemove', e => moveTip(e));
    b.addEventListener('mouseleave', hideTip);
    b.addEventListener('click', () => select(b.dataset.id));
  });
  markSelected();
}

function showTip(e, id) {
  const p = state.day.plants.find(x => x.id === id);
  if (!p) return;
  const tip = $('tooltip');
  tip.innerHTML = `<strong>${esc(p.plant)}</strong><br>
    <span>${esc(p.state || p.utility)} &middot; ${int(p.capacity_mw)} MW</span><br>
    ${fmt(cover(p), 1)} days cover &middot; ${fmt(p.stock_total_kt, 0)} kt in stock`;
  tip.hidden = false;
  moveTip(e);
}
function moveTip(e) {
  const tip = $('tooltip');
  const x = Math.min(e.clientX + 14, window.innerWidth - tip.offsetWidth - 10);
  tip.style.left = x + 'px';
  tip.style.top = (e.clientY + 16) + 'px';
}
function hideTip() { $('tooltip').hidden = true; }

/* ---------- table ---------- */

const COLUMNS = [
  { key: 'plant', label: 'Station', cls: 'name', fn: p => `<span class="dot" style="background:var(${bandOf(cover(p))[1]})"></span>${esc(p.plant)}` },
  { key: 'state', label: 'State', cls: 'sub', fn: p => esc(p.state || '\u2013') },
  { key: 'utility', label: 'Group', cls: 'sub', fn: p => esc(p.utility || '\u2013') },
  { key: 'capacity_mw', label: 'MW', fn: p => int(p.capacity_mw) },
  { key: 'cover', label: 'Days cover', cls: 'cover', fn: p => fmt(cover(p), 1) },
  { key: 'stock_total_kt', label: "Stock '000 t", fn: p => fmt(p.stock_total_kt, 0) },
  { key: 'pct_of_norm', label: '% of normative', fn: p => fmt(p.pct_of_norm, 0) + '%' },
  { key: 'receipt_kt', label: 'Received', fn: p => fmt(p.receipt_kt, 1) },
  { key: 'consumption_kt', label: 'Burnt', fn: p => fmt(p.consumption_kt, 1) },
  { key: 'net_change_kt', label: 'Net', fn: p => `<span class="${p.net_change_kt < 0 ? 'neg' : 'pos'}">${p.net_change_kt > 0 ? '+' : ''}${fmt(p.net_change_kt, 1)}</span>` },
  { key: 'dcover', label: '\u0394 cover', fn: p => { const d = deltaCover(p); return d === null ? '\u2013' : `<span class="${d < 0 ? 'neg' : 'pos'}">${d > 0 ? '+' : ''}${fmt(d, 1)}</span>`; } },
  { key: 'plf_pct', label: 'PLF', fn: p => fmt(p.plf_pct, 0) + '%' },
  { key: 'mode_of_transport', label: 'Transport', cls: 'sub', fn: p => esc(p.mode_of_transport || '\u2013') },
];

function deltaCover(p) {
  if (!state.prev) return null;
  const before = state.prev.plants.find(x => x.id === p.id);
  if (!before) return null;
  const a = filters.basisActual ? before.cover_days_actual : before.cover_days_normative;
  const b = cover(p);
  return (a === null || b === null || a === undefined || b === undefined) ? null : b - a;
}

function sortValue(p, key) {
  if (key === 'cover') return cover(p) ?? 1e9;
  if (key === 'dcover') return deltaCover(p) ?? 1e9;
  const v = p[key];
  return typeof v === 'number' ? v : String(v ?? '').toLowerCase();
}

function renderTable(rows) {
  $('thead-row').innerHTML = COLUMNS.map(c => {
    const on = state.sort.key === c.key;
    return `<th data-key="${c.key}" aria-sort="${on ? (state.sort.dir === 'asc' ? 'ascending' : 'descending') : 'none'}">${c.label}</th>`;
  }).join('');
  $('thead-row').querySelectorAll('th').forEach(th => th.addEventListener('click', () => {
    const k = th.dataset.key;
    state.sort = { key: k, dir: state.sort.key === k && state.sort.dir === 'asc' ? 'desc' : 'asc' };
    renderTable(apply()); writeHash();
  }));

  const dir = state.sort.dir === 'asc' ? 1 : -1;
  const sorted = rows.slice().sort((a, b) => {
    const x = sortValue(a, state.sort.key), y = sortValue(b, state.sort.key);
    return x < y ? -dir : x > y ? dir : 0;
  });

  $('tbody').innerHTML = sorted.map(p =>
    `<tr data-id="${p.id}">${COLUMNS.map(c => `<td class="${c.cls || ''}">${c.fn(p)}</td>`).join('')}</tr>`
  ).join('');
  $('tbody').querySelectorAll('tr').forEach(tr =>
    tr.addEventListener('click', () => select(tr.dataset.id)));

  const total = state.day.plants.length;
  $('table-count').textContent = rows.length === total
    ? `${total} stations` : `${rows.length} of ${total} stations`;
  $('empty').hidden = rows.length > 0;
  markSelected();
}

/* ---------- charts ---------- */

const gridColour = () => css('--line');
const baseScale = () => ({
  grid: { color: gridColour(), drawTicks: false },
  border: { display: false },
  ticks: { color: css('--ink-dim'), font: { family: 'IBM Plex Mono', size: 10 } },
});

function renderTrend() {
  if (!state.trend || !state.trend.length) return;
  const labels = state.trend.map(t => t.date.slice(5));
  const data = {
    labels,
    datasets: [
      { label: 'Days of cover', data: state.trend.map(t => t.cover_days_normative), yAxisID: 'y',
        borderColor: css('--c-comfortable'), backgroundColor: 'transparent', tension: .25, pointRadius: 0, borderWidth: 2 },
      { label: 'Critical stations', data: state.trend.map(t => t.critical), yAxisID: 'y1',
        borderColor: css('--c-critical'), backgroundColor: 'transparent', tension: .25, pointRadius: 0, borderWidth: 1.5, borderDash: [4, 3] },
    ],
  };
  upsert('trend', 'chart-trend', {
    type: 'line', data,
    options: {
      responsive: true, maintainAspectRatio: false, interaction: { mode: 'index', intersect: false },
      plugins: { legend: { labels: { color: css('--ink-mid'), boxWidth: 10, font: { size: 11 } } } },
      scales: {
        x: baseScale(),
        y: { ...baseScale(), position: 'left', title: { display: true, text: 'days', color: css('--ink-dim'), font: { size: 10 } } },
        y1: { ...baseScale(), position: 'right', grid: { display: false }, title: { display: true, text: 'critical', color: css('--ink-dim'), font: { size: 10 } } },
      },
    },
  });
}

function renderStateChart(rows) {
  const by = new Map();
  rows.forEach(p => {
    if (!p.state) return;
    const s = by.get(p.state) || { stock: 0, req: 0, cap: 0 };
    s.stock += p.stock_total_kt || 0; s.req += p.daily_req_kt || 0; s.cap += p.capacity_mw || 0;
    by.set(p.state, s);
  });
  const entries = [...by.entries()]
    .filter(([, s]) => s.req > 0)
    .map(([k, s]) => [k, s.stock / s.req])
    .sort((a, b) => a[1] - b[1]).slice(0, 16);

  upsert('states', 'chart-state', {
    type: 'bar',
    data: {
      labels: entries.map(e => e[0]),
      datasets: [{
        label: 'Days of cover',
        data: entries.map(e => +e[1].toFixed(1)),
        backgroundColor: entries.map(e => css(bandOf(e[1])[1])),
        borderWidth: 0, barPercentage: .82,
      }],
    },
    options: {
      indexAxis: 'y', responsive: true, maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      scales: { x: baseScale(), y: { ...baseScale(), grid: { display: false }, ticks: { ...baseScale().ticks, font: { family: 'IBM Plex Sans', size: 10.5 } } } },
    },
  });
  $('chart-state-cap').textContent = `Days of cover by state \u2014 ${entries.length} tightest`;
}

function upsert(name, canvasId, cfg) {
  if (state.charts[name]) state.charts[name].destroy();
  state.charts[name] = new Chart($(canvasId), cfg);
}

/* ---------- station drawer ---------- */

async function select(id) {
  state.selected = id;
  const p = state.day.plants.find(x => x.id === id);
  if (!p) return;
  // The series file is a megabyte or so; only fetch it when someone actually
  // opens a station.
  if (!state.series) {
    state.series = await json('data/plants-recent.json').catch(() => ({ series: {} }));
  }
  const s = state.series.series[id];
  const c = cover(p);

  $('drawer-body').innerHTML = `
    <h3>${esc(p.plant)}</h3>
    <p class="where">${esc(p.state || '')}${p.state && p.utility !== p.state ? ' &middot; ' : ''}${esc(p.utility !== p.state ? p.utility : '')}
      &middot; ${int(p.capacity_mw)} MW &middot; ${esc(p.mode_of_transport || '')}</p>
    <dl class="stat-grid">
      <div><dt>Days of cover</dt><dd style="color:var(${bandOf(c)[1]})">${fmt(c, 1)}</dd></div>
      <div><dt>Stock</dt><dd>${fmt(p.stock_total_kt, 0)}<small> kt</small></dd></div>
      <div><dt>Of normative</dt><dd>${fmt(p.pct_of_norm, 0)}%</dd></div>
      <div><dt>Daily need @85% PLF</dt><dd>${fmt(p.daily_req_kt, 1)}<small> kt</small></dd></div>
      <div><dt>Received</dt><dd>${fmt(p.receipt_kt, 1)}<small> kt</small></dd></div>
      <div><dt>Burnt</dt><dd>${fmt(p.consumption_kt, 1)}<small> kt</small></dd></div>
      <div><dt>Imported share</dt><dd>${fmt(p.import_share_pct, 0)}%</dd></div>
      <div><dt>Month PLF</dt><dd>${fmt(p.plf_pct, 0)}%</dd></div>
    </dl>
    ${p.days_to_empty ? `<p class="remark">At the current draw of ${fmt(Math.abs(p.net_change_kt), 1)} kt a day, stock reaches zero in about ${fmt(p.days_to_empty, 0)} days.</p>` : ''}
    ${p.remarks ? `<p class="remark">CEA remark: ${esc(p.remarks)}</p>` : ''}
    ${s ? `<canvas id="chart-plant" height="150"></canvas>
      <p class="where">Last ${s.points.length} reports. Full history is in the monthly CSVs.</p>`
      : '<p class="where">No history yet for this station.</p>'}
  `;
  $('drawer').hidden = false;

  if (s) {
    const pts = s.points;
    upsert('plant', 'chart-plant', {
      type: 'line',
      data: {
        labels: pts.map(x => x[0].slice(5)),
        datasets: [
          { label: 'Days cover', data: pts.map(x => x[2]), borderColor: css('--c-comfortable'), tension: .25, pointRadius: 0, borderWidth: 2, yAxisID: 'y' },
          { label: 'Received', data: pts.map(x => x[3]), borderColor: css('--c-adequate'), tension: .25, pointRadius: 0, borderWidth: 1.2, yAxisID: 'y1' },
          { label: 'Burnt', data: pts.map(x => x[4]), borderColor: css('--c-critical'), tension: .25, pointRadius: 0, borderWidth: 1.2, yAxisID: 'y1' },
        ],
      },
      options: {
        responsive: true, maintainAspectRatio: false, interaction: { mode: 'index', intersect: false },
        plugins: { legend: { labels: { color: css('--ink-mid'), boxWidth: 10, font: { size: 10.5 } } } },
        scales: { x: baseScale(), y: baseScale(), y1: { ...baseScale(), position: 'right', grid: { display: false } } },
      },
    });
  }
  markSelected();
}

function markSelected() {
  document.querySelectorAll('.strip b').forEach(b =>
    b.classList.toggle('is-sel', b.dataset.id === state.selected));
}

/* ---------- controls ---------- */

function wireControls() {
  const rerender = () => { renderAll(); writeHash(); };

  $('q').addEventListener('input', e => { filters.q = e.target.value; rerender(); });

  $('cover-presets').addEventListener('click', e => {
    const chip = e.target.closest('.chip'); if (!chip) return;
    [...$('cover-presets').children].forEach(c => c.classList.toggle('is-on', c === chip));
    filters.coverMin = +chip.dataset.min; filters.coverMax = +chip.dataset.max;
    $('cover-min').value = filters.coverMin; $('cover-max').value = filters.coverMax;
    rerender();
  });

  ['cover-min', 'cover-max'].forEach(id => $(id).addEventListener('input', () => {
    filters.coverMin = +$('cover-min').value || 0;
    filters.coverMax = +$('cover-max').value || 999;
    [...$('cover-presets').children].forEach(c => c.classList.remove('is-on'));
    rerender();
  }));

  $('cover-basis').addEventListener('change', e => {
    filters.basisActual = e.target.checked;
    $('cover-basis-hint').textContent = filters.basisActual
      ? "Stock \u00f7 the previous day's actual burn."
      : 'Stock \u00f7 daily requirement at 85% PLF.';
    rerender();
  });

  [['f-state', 'state'], ['f-utility', 'utility'], ['f-ownership', 'ownership'],
   ['f-section', 'section'], ['f-mode', 'mode']].forEach(([id, key]) =>
    $(id).addEventListener('change', e => {
      filters[key] = [...e.target.selectedOptions].map(o => o.value); rerender();
    }));

  [['t-critical', 'critical'], ['t-noreceipt', 'noreceipt'],
   ['t-drawdown', 'drawdown'], ['t-import', 'imported'],
   ['t-idle', 'includeIdle']].forEach(([id, key]) =>
    $(id).addEventListener('change', e => { filters[key] = e.target.checked; rerender(); }));

  $('reset').addEventListener('click', () => {
    Object.assign(filters, { q: '', coverMin: 0, coverMax: 999, state: [], utility: [],
      ownership: [], section: [], mode: [], critical: false, noreceipt: false,
      drawdown: false, imported: false, includeIdle: false });
    document.querySelectorAll('.filters input[type=checkbox]').forEach(c => { c.checked = false; });
    document.querySelectorAll('.filters select').forEach(s => { [...s.options].forEach(o => o.selected = false); });
    $('q').value = ''; $('cover-min').value = 0; $('cover-max').value = 999;
    filters.basisActual = false;
    [...$('cover-presets').children].forEach((c, i) => c.classList.toggle('is-on', i === 0));
    rerender();
  });

  $('compare').addEventListener('change', async e => {
    state.baseline = e.target.value;
    await loadDate(state.day.date);
  });

  const sheet = () => document.body.classList.contains('filters-open');
  const setSheet = on => {
    document.body.classList.toggle('filters-open', on);
    $('filter-toggle').setAttribute('aria-expanded', String(on));
  };
  $('filter-toggle').addEventListener('click', () => setSheet(!sheet()));
  $('filter-done').addEventListener('click', () => setSheet(false));

  $('export').addEventListener('click', exportCsv);
  $('drawer-close').addEventListener('click', () => { $('drawer').hidden = true; state.selected = null; markSelected(); });
  document.addEventListener('keydown', e => {
    if (e.key === 'Escape' && !$('drawer').hidden) $('drawer-close').click();
  });
  window.addEventListener('hashchange', readHash);
}

function exportCsv() {
  const rows = apply();
  const cols = ['plant', 'state', 'utility', 'ownership', 'section', 'mode_of_transport',
    'capacity_mw', 'plf_pct', 'daily_req_kt', 'norm_stock_kt', 'stock_indigenous_kt',
    'stock_import_kt', 'stock_total_kt', 'pct_of_norm', 'receipt_kt', 'consumption_kt',
    'cover_days_normative', 'cover_days_actual', 'net_change_kt', 'is_critical', 'remarks'];
  const q = v => `"${String(v ?? '').replace(/"/g, '""')}"`;
  const csv = [cols.join(','), ...rows.map(r => cols.map(c => q(r[c])).join(','))].join('\n');
  const url = URL.createObjectURL(new Blob([csv], { type: 'text/csv;charset=utf-8' }));
  const a = document.createElement('a');
  a.href = url; a.download = `coal-cover-${state.day.date}.csv`; a.click();
  URL.revokeObjectURL(url);
}

/* ---------- shareable state ---------- */

function writeHash() {
  const p = new URLSearchParams();
  p.set('date', state.day.date);
  if (filters.q) p.set('q', filters.q);
  if (filters.coverMin) p.set('min', filters.coverMin);
  if (filters.coverMax < 999) p.set('max', filters.coverMax);
  if (filters.basisActual) p.set('basis', 'actual');
  ['state', 'utility', 'ownership', 'section', 'mode'].forEach(k => {
    if (filters[k].length) p.set(k, filters[k].join('~'));
  });
  ['critical', 'noreceipt', 'drawdown', 'imported', 'includeIdle'].forEach(k => { if (filters[k]) p.set(k, '1'); });
  if (state.sort.key !== 'cover' || state.sort.dir !== 'asc') p.set('sort', `${state.sort.key}:${state.sort.dir}`);
  history.replaceState(null, '', '#' + p.toString());
}

function readHash() {
  const p = new URLSearchParams(location.hash.slice(1));
  if (!p.has('q') && !p.has('min') && !p.has('state')) return;
  filters.q = p.get('q') || '';
  filters.coverMin = +(p.get('min') || 0);
  filters.coverMax = +(p.get('max') || 999);
  filters.basisActual = p.get('basis') === 'actual';
  ['state', 'utility', 'ownership', 'section', 'mode'].forEach(k => {
    filters[k] = p.get(k) ? p.get(k).split('~') : [];
  });
  ['critical', 'noreceipt', 'drawdown', 'imported', 'includeIdle'].forEach(k => { filters[k] = p.get(k) === '1'; });
  if (p.get('sort')) { const [key, dir] = p.get('sort').split(':'); state.sort = { key, dir }; }

  $('q').value = filters.q;
  $('cover-min').value = filters.coverMin; $('cover-max').value = filters.coverMax;
  $('cover-basis').checked = filters.basisActual;
  [['f-state', 'state'], ['f-utility', 'utility'], ['f-ownership', 'ownership'],
   ['f-section', 'section'], ['f-mode', 'mode']].forEach(([id, key]) =>
    [...$(id).options].forEach(o => { o.selected = filters[key].includes(o.value); }));
  [['t-critical', 'critical'], ['t-noreceipt', 'noreceipt'], ['t-drawdown', 'drawdown'],
   ['t-import', 'imported'], ['t-idle', 'includeIdle']].forEach(([id, key]) => { $(id).checked = filters[key]; });
  renderAll();
}

boot();
