/* Docker Topology Live – browser UI (D3 v7 force-directed graph)
 *
 * Live-update strategy
 * --------------------
 * 1. One initial loadTopology() fetch on page load.
 * 2. EventSource('/api/events') for live Docker updates (SSE).
 *    - topology events  -> render/updateStats (existing path)
 *    - metrics events   -> applyMetrics/recordMetricsHistory/updateMetricsStatus
 *    - heartbeat events -> status bar update
 *    - docker-event     -> logged (topology follows within ~350 ms)
 *    - error events     -> warning shown; browser auto-reconnects
 *    - onerror          -> after SSE_MAX_ERRORS consecutive failures,
 *                          close EventSource and fall back to polling
 * 3. If EventSource is unsupported or fails repeatedly, fall back to
 *    15-second polling.
 *
 * Metric glow
 * -----------
 * Container nodes receive a CSS class (glow-low / glow-medium /
 * glow-high / glow-critical) based on CPU percent from the latest
 * metrics snapshot.  Glow is removed when no metrics are available.
 *
 * Metric history / sparklines
 * ---------------------------
 * A rolling in-memory history (metricsHistory Map) accumulates up to
 * METRIC_HISTORY_LIMIT samples per container from SSE metrics events.
 * When a container node is selected, renderMetricHistorySection() draws
 * small inline SVG sparklines (CPU%, Memory%, Net RX/TX, Block Write)
 * in the detail panel.  History is never persisted and never sent outside
 * the browser. If the detail panel is already open, incoming metrics events
 * refresh only the selected node's Recent metrics section.
 *
 * Security: no innerHTML is used anywhere in this file.
 */
'use strict';

const API_TOPOLOGY    = '/api/topology';
const API_EVENTS      = '/api/events';
const API_DIAGNOSTICS = '/api/diagnostics';
const REFRESH_MS      = 15_000;
const NODE_R          = { container: 20, network: 14 };
const SSE_MAX_ERRORS  = 3;

const STATUS_COLOR = {
  running:    '#4ade80',
  exited:     '#f87171',
  dead:       '#f87171',
  paused:     '#fb923c',
  restarting: '#60a5fa',
  created:    '#94a3b8',
  network:    '#818cf8',
};

// Glow thresholds (CPU percent)
const GLOW_CRITICAL = 80;
const GLOW_HIGH     = 40;
const GLOW_MEDIUM   = 15;
const GLOW_LOW      = 5;
const GLOW_CLASSES  = ['glow-low', 'glow-medium', 'glow-high', 'glow-critical'];

// Metric history: max samples kept per container (browser-local, never persisted)
const METRIC_HISTORY_LIMIT = 60;

let svg, g, zoomBehavior, simulation;
let filterText = '';

// SSE / polling state
let sseSource    = null;
let sseErrorCount = 0;
let pollingTimer = null;

// Metrics state: Map<containerNodeId, metricsObject>
let metricsMap = new Map();

// Metric history store: Map<containerNodeId, sample[]>
// Each sample: { ts, cpuPercent, memoryPercent, networkRxBytes, networkTxBytes,
//                blockReadBytes, blockWriteBytes, pids }
// Never sent outside the browser; never persisted to disk or browser storage.
const metricsHistory = new Map();

// Detail panel state. Used only to refresh the selected container's sparkline
// section when new metrics arrive; never causes a full graph re-render.
let selectedDetailNode = null;

// Diagnostics state: Map<nodeId, finding[]>
let diagMap = new Map();
let diagEnabled = false;

// DOM helpers
function $(id) { return document.getElementById(id); }
function show(el) { if (el) el.classList.remove('hidden'); }
function hide(el) { if (el) el.classList.add('hidden'); }
function closeDetailPanel() {
  selectedDetailNode = null;
  hide($('detail-panel'));
}

function updateStatus(msg) {
  const el = $('status-msg');
  if (el) el.textContent = msg;
}

function updateMetricsStatus(state, msg) {
  const el = $('metrics-status');
  if (!el) return;
  el.textContent = msg;
  el.className = ''; // reset
  if (state === 'live')   el.classList.add('metrics-live');
  if (state === 'sample') el.classList.add('metrics-sample');
  if (state === 'error')  el.classList.add('metrics-error');
}

// Colour
function nodeColor(d) {
  if (d.kind === 'network') return STATUS_COLOR.network;
  return STATUS_COLOR[d.status] || '#94a3b8';
}

function matchesFilter(d) {
  if (!filterText) return true;
  const hay = [d.label, d.kind, d.status || '', d.image || '', d.driver || '']
    .join(' ').toLowerCase();
  return hay.includes(filterText);
}

// Graph data prep
function buildGraph(data) {
  const nodeMap = new Map();
  const nodes   = [];
  const links   = [];

  for (const n of (data.nodes || [])) {
    const node = { ...n };
    nodes.push(node);
    nodeMap.set(n.id, node);
  }

  for (const l of (data.links || [])) {
    if (nodeMap.has(l.source) && nodeMap.has(l.target)) {
      links.push({ source: l.source, target: l.target, ip: l.label || '' });
    }
  }

  return { nodes, links };
}

// SVG init (once)
function initSVG() {
  svg = d3.select('#graph')
    .attr('width',  '100%')
    .attr('height', '100%');

  zoomBehavior = d3.zoom()
    .scaleExtent([0.08, 6])
    .on('zoom', e => g.attr('transform', e.transform));

  svg.call(zoomBehavior);
  g = svg.append('g');
}

// Full render
function render(data) {
  const W = ($('graph-container') || {}).clientWidth  || 800;
  const H = ($('graph-container') || {}).clientHeight || 600;

  g.selectAll('*').remove();

  const { nodes, links } = buildGraph(data);

  if (simulation) simulation.stop();

  simulation = d3.forceSimulation(nodes)
    .force('link',    d3.forceLink(links).id(d => d.id).distance(130))
    .force('charge',  d3.forceManyBody().strength(-380))
    .force('center',  d3.forceCenter(W / 2, H / 2))
    .force('collide', d3.forceCollide().radius(d => (NODE_R[d.kind] || 20) + 16));

  // Links
  const linkSel = g.append('g').attr('class', 'links')
    .selectAll('line').data(links).join('line')
    .attr('class', 'link');

  // IP labels on links
  const ipLabelSel = g.append('g').attr('class', 'link-labels')
    .selectAll('text').data(links.filter(l => l.ip)).join('text')
    .attr('font-size', 9)
    .attr('fill', '#475569')
    .attr('text-anchor', 'middle')
    .attr('pointer-events', 'none');

  // Node groups
  const nodeSel = g.append('g').attr('class', 'nodes')
    .selectAll('g').data(nodes).join('g')
    .attr('class', 'node')
    .call(d3.drag()
      .on('start', (e, d) => {
        if (!e.active) simulation.alphaTarget(0.3).restart();
        d.fx = d.x; d.fy = d.y;
      })
      .on('drag', (e, d) => { d.fx = e.x; d.fy = e.y; })
      .on('end',  (e, d) => {
        if (!e.active) simulation.alphaTarget(0);
        d.fx = null; d.fy = null;
      })
    )
    .on('mouseover', onNodeOver)
    .on('mouseout',  onNodeOut)
    .on('click',     onNodeClick);

  // Container -> circle
  nodeSel.filter(d => d.kind === 'container')
    .append('circle')
    .attr('r', NODE_R.container)
    .attr('fill', nodeColor);

  // Network -> diamond
  nodeSel.filter(d => d.kind === 'network')
    .append('polygon')
    .attr('points', () => {
      const r = NODE_R.network;
      return `0,${-r} ${r},0 0,${r} ${-r},0`;
    })
    .attr('fill', nodeColor);

  // Labels
  nodeSel.append('text')
    .attr('class', 'node-label')
    .attr('dy',  d => (NODE_R[d.kind] || 20) + 14)
    .attr('text-anchor', 'middle')
    .text(d => d.label);

  simulation.on('tick', () => {
    linkSel
      .attr('x1', d => d.source.x).attr('y1', d => d.source.y)
      .attr('x2', d => d.target.x).attr('y2', d => d.target.y);

    ipLabelSel
      .attr('x', d => (d.source.x + d.target.x) / 2)
      .attr('y', d => (d.source.y + d.target.y) / 2)
      .text(d => d.ip);

    nodeSel.attr('transform', d => `translate(${d.x ?? 0},${d.y ?? 0})`);
  });

  applyFilter();
  // Re-apply existing metrics glow after a full redraw
  applyMetricsGlow();
}

// Filter
function applyFilter() {
  if (!g) return;
  g.selectAll('.node').each(function (d) {
    d3.select(this).style('opacity', matchesFilter(d) ? 1 : 0.12);
  });
}

// ── Metric glow ───────────────────────────────────────────────────────────────

/**
 * Return the CSS glow class name for the given CPU percent, or '' for none.
 * Network nodes and containers with no metrics get no glow.
 */
function cpuGlowClass(cpuPercent) {
  if (cpuPercent == null || cpuPercent < GLOW_LOW) return '';
  if (cpuPercent >= GLOW_CRITICAL) return 'glow-critical';
  if (cpuPercent >= GLOW_HIGH)     return 'glow-high';
  if (cpuPercent >= GLOW_MEDIUM)   return 'glow-medium';
  return 'glow-low';
}

/**
 * Apply or remove glow CSS classes on all container nodes based on metricsMap.
 * Safe to call when metricsMap is empty (all glow is removed).
 */
function applyMetricsGlow() {
  if (!g) return;
  g.selectAll('.node').each(function (d) {
    if (d.kind !== 'container') return;
    const el  = d3.select(this);
    const m   = metricsMap.get(d.id);
    const cls = m ? cpuGlowClass(m.cpuPercent) : '';
    // Remove all glow classes then set the appropriate one
    for (const c of GLOW_CLASSES) el.classed(c, false);
    if (cls) el.classed(cls, true);
  });
}

// Safe DOM helpers
/**
 * Build a two-column <table> from an array of [header, value] pairs.
 * An optional third element is a CSS class applied to the <td>.
 * All text is set via textContent -- no innerHTML used anywhere.
 */
function _makeTable(rows) {
  const table = document.createElement('table');
  for (const [header, value, className] of rows) {
    const tr = document.createElement('tr');
    const th = document.createElement('th');
    th.textContent = header;
    const td = document.createElement('td');
    if (className) td.className = className;
    td.textContent = value;
    tr.appendChild(th);
    tr.appendChild(td);
    table.appendChild(tr);
  }
  return table;
}

function _fmtBytes(n) {
  if (n == null) return '—';
  if (n < 1024)           return n + ' B';
  if (n < 1024 * 1024)    return (n / 1024).toFixed(1) + ' KiB';
  if (n < 1024 ** 3)      return (n / 1024 / 1024).toFixed(1) + ' MiB';
  return (n / 1024 / 1024 / 1024).toFixed(2) + ' GiB';
}

// Tooltip
function onNodeOver(event, d) {
  const t = $('tooltip');
  if (!t) return;

  // Build tooltip content safely -- no innerHTML
  t.textContent = '';
  const strong = document.createElement('strong');
  strong.textContent = d.label;
  t.appendChild(strong);
  t.appendChild(document.createElement('br'));

  if (d.kind === 'container') {
    t.appendChild(document.createTextNode('Status: ' + (d.status || '?')));
    t.appendChild(document.createElement('br'));
    t.appendChild(document.createTextNode('Image: ' + (d.image || '?')));
    // Show CPU if metrics are available
    const m = metricsMap.get(d.id);
    if (m && m.cpuPercent != null) {
      t.appendChild(document.createElement('br'));
      t.appendChild(document.createTextNode('CPU: ' + m.cpuPercent.toFixed(1) + '%'));
    }
  } else {
    t.appendChild(document.createTextNode('Driver: ' + (d.driver || '?')));
    t.appendChild(document.createElement('br'));
    t.appendChild(document.createTextNode('Scope: ' + (d.scope || '?')));
  }

  t.style.left = (event.clientX + 14) + 'px';
  t.style.top  = (event.clientY - 10) + 'px';
  show(t);
}
function onNodeOut() { hide($('tooltip')); }

// Detail panel
function onNodeClick(event, d) {
  const panel = $('detail-panel');
  selectedDetailNode = d;
  $('detail-title').textContent = d.label;
  const body = $('detail-body');

  // Clear previous content safely -- no innerHTML
  body.textContent = '';

  if (d.kind === 'container') {
    body.appendChild(_makeTable([
      ['ID',     d.id],
      ['Image',  d.image  || '—'],
      ['Status', d.status || '—', 'status-' + (d.status || '')],
      ['State',  d.state  || '—'],
      ['Kind',   'container'],
    ]));

    // Ports
    const ports = d.ports || [];
    if (ports.length > 0) {
      const h = document.createElement('h4');
      h.textContent = 'Ports';
      body.appendChild(h);
      body.appendChild(_makeTable(ports.map(p => {
        const binding = p.hostPort != null
          ? p.hostPort + ':' + p.containerPort + '/' + (p.protocol || 'tcp')
          : p.containerPort + '/' + (p.protocol || 'tcp') + ' (not published)';
        return [String(p.containerPort), binding];
      })));
    }

    // Mounts
    const mounts = d.mounts || [];
    if (mounts.length > 0) {
      const h = document.createElement('h4');
      h.textContent = 'Mounts';
      body.appendChild(h);
      body.appendChild(_makeTable(mounts.map(m => {
        let srcPart = '';
        if (m.sourceRedacted) {
          // Source was redacted — show placeholder and safe category
          srcPart = '[redacted]';
          if (m.sourceCategory) srcPart += ' (' + m.sourceCategory + ')';
          srcPart += ' ';
        } else if (m.source) {
          srcPart = m.source + ' ';
        }
        return [
          m.destination || '?',
          srcPart + '(' + (m.type || 'volume') + ', ' + (m.rw ? 'rw' : 'ro') + ')',
        ];
      })));
    }

    // Compose
    if (d.compose_project) {
      const h = document.createElement('h4');
      h.textContent = 'Compose';
      body.appendChild(h);
      body.appendChild(_makeTable([
        ['Project', d.compose_project  || '—'],
        ['Service', d.compose_service  || '—'],
        ['Number',  d.compose_container_number || '—'],
      ]));
    }

    // Metrics (shown only if data is available for this container)
    const m = metricsMap.get(d.id);
    if (m) {
      const h = document.createElement('h4');
      h.textContent = 'Metrics';
      body.appendChild(h);
      body.appendChild(_makeTable([
        ['CPU',         (m.cpuPercent != null ? m.cpuPercent.toFixed(2) + '%' : '—')],
        ['Memory',      _fmtBytes(m.memoryUsageBytes) + ' / ' + _fmtBytes(m.memoryLimitBytes)],
        ['Mem %',       (m.memoryPercent != null ? m.memoryPercent.toFixed(2) + '%' : '—')],
        ['Net RX',      _fmtBytes(m.networkRxBytes)],
        ['Net TX',      _fmtBytes(m.networkTxBytes)],
        ['Block R',     _fmtBytes(m.blockReadBytes)],
        ['Block W',     _fmtBytes(m.blockWriteBytes)],
        ['PIDs',        m.pids != null ? String(m.pids) : '—'],
      ]));
    }

    // Metric history sparklines (shown only when history has accumulated)
    renderMetricHistorySection(d, body);

    // Diagnostics findings for this node
    renderFindingsForNode(d.id, body);

  } else {
    body.appendChild(_makeTable([
      ['ID',       d.id],
      ['Driver',   d.driver   || '—'],
      ['Scope',    d.scope    || '—'],
      ['Internal', d.internal ? 'yes' : 'no'],
      ['Kind',     'network'],
    ]));

    // Diagnostics findings for this network node
    renderFindingsForNode(d.id, body);
  }

  show(panel);
  event.stopPropagation();
}

// Stats bar
function updateStats(data) {
  const s = data.summary || {};
  const nodes = data.nodes || [];

  ($('stat-containers') || {}).textContent =
    s.containers ?? nodes.filter(n => n.kind === 'container').length;
  ($('stat-running') || {}).textContent    = s.runningContainers ?? '?';
  ($('stat-networks') || {}).textContent   =
    s.networks ?? nodes.filter(n => n.kind === 'network').length;
  ($('stat-links') || {}).textContent      = s.links ?? (data.links || []).length;

  if (data.sample) show($('sample-badge')); else hide($('sample-badge'));
}

// ── Diagnostics helpers ───────────────────────────────────────────────────────

/**
 * Update the #diag-bar topbar element from a diagnostics summary.
 * Shows severity badge counts; hides bar when no findings exist.
 */
function updateDiagnosticsBar(summary) {
  const bar = $('diag-bar');
  if (!bar) return;
  bar.textContent = '';   // clear -- no innerHTML

  const bySev = (summary && summary.bySeverity) || {};
  const total = (summary && summary.findings) || 0;

  if (total === 0) {
    bar.classList.add('hidden');
    return;
  }

  bar.classList.remove('hidden');

  // Label prefix
  const label = document.createElement('span');
  label.textContent = 'Findings:';
  label.style.color = 'var(--muted)';
  bar.appendChild(label);

  const severities = [
    ['high',   'H'],
    ['medium', 'M'],
    ['low',    'L'],
    ['info',   'I'],
  ];
  for (const [sev, abbr] of severities) {
    const count = bySev[sev] || 0;
    if (count === 0) continue;
    const badge = document.createElement('span');
    badge.className = 'diag-badge diag-' + sev;
    badge.textContent = abbr + ':' + count;
    bar.appendChild(badge);
  }
}

/**
 * Apply a diagnostics document to diagMap and refresh the bar.
 * Safe to call when data is missing or empty.
 */
function applyDiagnostics(data) {
  if (!data || !data.findings) return;
  diagEnabled = true;
  diagMap = new Map();
  for (const f of data.findings) {
    const tid = (f.target && f.target.id) || '';
    if (!tid) continue;
    if (!diagMap.has(tid)) diagMap.set(tid, []);
    diagMap.get(tid).push(f);
  }
  updateDiagnosticsBar(data.summary);
}

/**
 * Render findings for a node into the detail panel body.
 * Uses createElement/textContent only — no innerHTML.
 */
function renderFindingsForNode(nodeId, body) {
  const findings = diagMap.get(nodeId);
  if (!findings || findings.length === 0) return;

  const h = document.createElement('h4');
  h.textContent = 'Diagnostics (' + findings.length + ')';
  body.appendChild(h);

  for (const f of findings) {
    const row = document.createElement('div');
    row.className = 'finding-row';

    // Title line with severity badge
    const titleLine = document.createElement('div');
    titleLine.className = 'finding-title finding-sev-' + (f.severity || 'info');
    const sevIcon = { high: '⛔', medium: '⚠', low: '○', info: 'ℹ' }[f.severity] || '○';
    titleLine.textContent = sevIcon + ' ' + (f.title || f.ruleId || '');
    row.appendChild(titleLine);

    // Description
    if (f.description) {
      const desc = document.createElement('div');
      desc.className = 'finding-desc';
      desc.textContent = f.description;
      row.appendChild(desc);
    }

    // Recommendation
    if (f.recommendation) {
      const rec = document.createElement('div');
      rec.className = 'finding-rec';
      rec.textContent = '→ ' + f.recommendation;
      row.appendChild(rec);
    }

    body.appendChild(row);
  }
}

// Apply a metrics snapshot document to metricsMap and trigger glow update
function applyMetrics(data) {
  metricsMap = new Map();
  for (const c of (data.containers || [])) {
    if (c.id) metricsMap.set(c.id, c);
  }
  applyMetricsGlow();
  recordMetricsHistory(data);
  refreshSelectedMetricHistory();

  // Update metrics status badge
  const isSample = data.sample === true;
  const count    = (data.containers || []).length;
  if (isSample) {
    updateMetricsStatus('sample', 'Metrics (sample)  · ' + count + ' containers');
  } else {
    updateMetricsStatus('live', 'Metrics live  · ' + count + ' containers');
  }
}

// ── Metric history store ──────────────────────────────────────────────────────

/**
 * Append one sample per container from a metrics SSE document into metricsHistory.
 * Keeps only the most recent METRIC_HISTORY_LIMIT samples per container.
 * History is browser-local and never sent outside the browser.
 */
function recordMetricsHistory(metricsDoc) {
  const ts = metricsDoc.generatedAt || new Date().toISOString();
  for (const c of (metricsDoc.containers || [])) {
    if (!c.id) continue;
    if (!metricsHistory.has(c.id)) metricsHistory.set(c.id, []);
    const samples = metricsHistory.get(c.id);
    samples.push({
      ts:              ts,
      cpuPercent:      c.cpuPercent      != null ? c.cpuPercent      : 0,
      memoryPercent:   c.memoryPercent   != null ? c.memoryPercent   : 0,
      networkRxBytes:  c.networkRxBytes  != null ? c.networkRxBytes  : 0,
      networkTxBytes:  c.networkTxBytes  != null ? c.networkTxBytes  : 0,
      blockReadBytes:  c.blockReadBytes  != null ? c.blockReadBytes  : 0,
      blockWriteBytes: c.blockWriteBytes != null ? c.blockWriteBytes : 0,
      pids:            c.pids            != null ? c.pids            : null,
    });
    // Rolling window: discard samples beyond the limit
    if (samples.length > METRIC_HISTORY_LIMIT) {
      samples.splice(0, samples.length - METRIC_HISTORY_LIMIT);
    }
  }
}

/**
 * Return the history array for a container node, or [] if none recorded yet.
 */
function getMetricHistory(nodeId) {
  return metricsHistory.get(nodeId) || [];
}

// ── Sparkline rendering ───────────────────────────────────────────────────────

/**
 * Create a small inline SVG sparkline from an array of sample objects.
 * Returns an <svg> DOM element built with createElementNS — no innerHTML.
 *
 * @param {Array}  samples  - Array of sample objects from metricsHistory
 * @param {string} field    - Field name to extract from each sample
 * @param {Object} options  - { width, height, minY, maxY, color }
 * @returns {SVGElement}
 */
function makeSparkline(samples, field, options) {
  const opt   = options || {};
  const W     = opt.width  || 230;
  const H     = opt.height || 36;
  const color = opt.color  || '#22d3ee';
  const minY  = opt.minY   != null ? opt.minY : null;
  const maxY  = opt.maxY   != null ? opt.maxY : null;
  const PAD   = 3;

  const NS = 'http://www.w3.org/2000/svg';
  const svgEl = document.createElementNS(NS, 'svg');
  svgEl.setAttribute('width',   String(W));
  svgEl.setAttribute('height',  String(H));
  svgEl.setAttribute('viewBox', '0 0 ' + W + ' ' + H);
  svgEl.setAttribute('aria-hidden', 'true');
  svgEl.style.display = 'block';

  if (!samples || samples.length < 2) return svgEl;

  const values = samples.map(function (s) {
    const v = s[field];
    return (v == null || v !== v) ? 0 : Number(v);   // NaN check via v !== v
  });

  const lo = minY != null ? minY : Math.min.apply(null, values);
  const hi = maxY != null ? maxY : Math.max.apply(null, values);
  const range = (hi - lo) || 1;

  const innerW = W - PAD * 2;
  const innerH = H - PAD * 2;
  const xStep  = innerW / (values.length - 1);

  function toX(i) { return PAD + i * xStep; }
  function toY(v) { return PAD + innerH * (1 - (v - lo) / range); }

  // Closed fill polygon: go across the data, then back along the bottom
  const dataPts = values.map(function (v, i) { return toX(i) + ',' + toY(v); });
  const fillPts =
    (PAD + ',' + (H - PAD)) + ' ' +
    dataPts.join(' ') + ' ' +
    (toX(values.length - 1) + ',' + (H - PAD));

  const fill = document.createElementNS(NS, 'polygon');
  fill.setAttribute('points', fillPts);
  fill.setAttribute('fill', color);
  fill.setAttribute('fill-opacity', '0.12');
  svgEl.appendChild(fill);

  // Stroke polyline over the data
  const line = document.createElementNS(NS, 'polyline');
  line.setAttribute('points', dataPts.join(' '));
  line.setAttribute('fill', 'none');
  line.setAttribute('stroke', color);
  line.setAttribute('stroke-width', '1.5');
  line.setAttribute('stroke-linejoin', 'round');
  line.setAttribute('stroke-linecap',  'round');
  svgEl.appendChild(line);

  // Dot on the latest value
  const lastI = values.length - 1;
  const dot = document.createElementNS(NS, 'circle');
  dot.setAttribute('cx', String(toX(lastI)));
  dot.setAttribute('cy', String(toY(values[lastI])));
  dot.setAttribute('r',  '2.5');
  dot.setAttribute('fill', color);
  svgEl.appendChild(dot);

  return svgEl;
}

function metricHistorySectionId(nodeId) {
  return 'metric-history-' + String(nodeId || '').replace(/[^a-zA-Z0-9_-]/g, '-');
}

function buildMetricHistorySection(d) {
  const wrapper = document.createElement('div');
  wrapper.className = 'metric-history-section';
  wrapper.id = metricHistorySectionId(d.id);

  const h = document.createElement('h4');
  h.textContent = 'Recent metrics';
  wrapper.appendChild(h);

  const samples = getMetricHistory(d.id);

  if (samples.length < 2) {
    const msg = document.createElement('p');
    msg.className = 'sparkline-empty';
    msg.textContent = 'Not enough history yet.';
    wrapper.appendChild(msg);
    return wrapper;
  }

  const specs = [
    { label: 'CPU %',       field: 'cpuPercent',      minY: 0, maxY: 100, color: '#22d3ee' },
    { label: 'Memory %',    field: 'memoryPercent',   minY: 0, maxY: 100, color: '#4ade80' },
    { label: 'Net RX',      field: 'networkRxBytes',  minY: 0, maxY: null, color: '#818cf8' },
    { label: 'Net TX',      field: 'networkTxBytes',  minY: 0, maxY: null, color: '#fb923c' },
    { label: 'Block Write', field: 'blockWriteBytes', minY: 0, maxY: null, color: '#f87171' },
  ];

  for (const spec of specs) {
    const section = document.createElement('div');
    section.className = 'sparkline-section';

    const label = document.createElement('div');
    label.className = 'sparkline-label';
    label.textContent = spec.label;
    section.appendChild(label);

    section.appendChild(makeSparkline(samples, spec.field, {
      width:  230,
      height: 36,
      minY:   spec.minY,
      maxY:   spec.maxY,
      color:  spec.color,
    }));

    wrapper.appendChild(section);
  }

  return wrapper;
}

/**
 * Render the "Recent metrics" section with sparklines into the detail panel body.
 * Only rendered for container nodes; silently skips networks.
 * Uses createElement/createElementNS only — no innerHTML.
 *
 * @param {Object}  d    - Node data (must have .id and .kind)
 * @param {Element} body - Detail panel body DOM element to append into
 */
function renderMetricHistorySection(d, body) {
  if (d.kind !== 'container') return;
  body.appendChild(buildMetricHistorySection(d));
}

/**
 * Refresh only the selected container's Recent metrics section.
 * Called from applyMetrics() after new samples are recorded.
 * Does not redraw the graph, refetch topology, or rebuild the full detail panel.
 */
function refreshSelectedMetricHistory() {
  if (!selectedDetailNode || selectedDetailNode.kind !== 'container') return;
  const panel = $('detail-panel');
  if (!panel || panel.classList.contains('hidden')) return;
  const existing = $(metricHistorySectionId(selectedDetailNode.id));
  if (!existing) return;
  existing.replaceWith(buildMetricHistorySection(selectedDetailNode));
}

// Polling helpers
function startPolling() {
  if (pollingTimer) return;  // already running
  pollingTimer = setInterval(loadTopology, REFRESH_MS);
}

function stopPolling() {
  if (pollingTimer) {
    clearInterval(pollingTimer);
    pollingTimer = null;
  }
}

// One-shot topology fetch (initial load and polling fallback)
async function loadTopology() {
  try {
    const resp = await fetch(API_TOPOLOGY, { cache: 'no-store' });
    if (!resp.ok) throw new Error('HTTP ' + resp.status);
    const data = await resp.json();
    render(data);
    updateStats(data);
    updateStatus('Updated ' + new Date().toLocaleTimeString());
  } catch (err) {
    console.error('topology fetch error', err);
    updateStatus('⚠ ' + err.message);
  }
}

// Server-Sent Events
function startSSE() {
  if (!window.EventSource) {
    updateStatus('Polling (no SSE support)');
    return;
  }

  if (sseSource) {
    sseSource.close();
    sseSource = null;
  }

  sseSource = new EventSource(API_EVENTS);

  sseSource.onopen = () => {
    sseErrorCount = 0;
    stopPolling();
    updateStatus('● Live');
  };

  // Full topology snapshot (initial + after each relevant Docker event)
  sseSource.addEventListener('topology', e => {
    try {
      const data = JSON.parse(e.data);
      render(data);
      updateStats(data);
      updateStatus('● Live  · ' + new Date().toLocaleTimeString());
    } catch (err) {
      console.error('SSE topology parse error', err);
    }
  });

  // Container metrics snapshot (emitted only when --metrics is active)
  sseSource.addEventListener('metrics', e => {
    try {
      const data = JSON.parse(e.data);
      applyMetrics(data);
    } catch (err) {
      console.error('SSE metrics parse error', err);
      updateMetricsStatus('error', 'Metrics unavailable');
    }
  });

  // Diagnostics snapshot (emitted only when --diagnostics is active)
  sseSource.addEventListener('diagnostics', e => {
    try {
      const data = JSON.parse(e.data);
      applyDiagnostics(data);
    } catch (err) {
      console.error('SSE diagnostics parse error', err);
    }
  });

  // Heartbeat (sample mode idle signal)
  sseSource.addEventListener('heartbeat', () => {
    updateStatus('● Live (idle)  · ' + new Date().toLocaleTimeString());
  });

  // Normalized Docker event (topology snapshot follows ~350 ms later)
  sseSource.addEventListener('docker-event', e => {
    try {
      const ev = JSON.parse(e.data);
      console.debug('docker event:', ev.type, ev.action, ev.name);
    } catch (_) {}
  });

  // Server-side error (safe string, no traceback)
  sseSource.addEventListener('error', e => {
    try {
      const data = JSON.parse(e.data);
      const isMetricsErr = (data.error || '').toLowerCase().includes('metrics');
      if (isMetricsErr) {
        updateMetricsStatus('error', 'Metrics unavailable');
      } else {
        console.warn('SSE stream error:', data.error);
        updateStatus('⚠ ' + (data.error || 'stream error'));
      }
    } catch (_) {}
  });

  // Connection-level error (network drop, server restart, etc.)
  sseSource.onerror = () => {
    sseErrorCount++;
    if (sseErrorCount < SSE_MAX_ERRORS) {
      updateStatus('↺ Reconnecting… (' + sseErrorCount + '/' + SSE_MAX_ERRORS + ')');
    } else {
      if (sseSource) {
        sseSource.close();
        sseSource = null;
      }
      updateStatus('↻ Polling fallback');
      updateMetricsStatus('error', 'Metrics unavailable');
      startPolling();
    }
  };
}

// Fit to view
function fitToView() {
  if (!g || !svg) return;
  const bounds = g.node().getBBox();
  if (!bounds.width || !bounds.height) return;
  const svgEl = svg.node();
  const W = svgEl.clientWidth  || 800;
  const H = svgEl.clientHeight || 600;
  const scale = 0.85 / Math.max(bounds.width / W, bounds.height / H);
  const tx = (W - scale * (bounds.x * 2 + bounds.width))  / 2;
  const ty = (H - scale * (bounds.y * 2 + bounds.height)) / 2;
  svg.transition().duration(600)
    .call(zoomBehavior.transform, d3.zoomIdentity.translate(tx, ty).scale(scale));
}

// Boot
document.addEventListener('DOMContentLoaded', () => {
  initSVG();

  // 1. Immediate one-shot fetch so graph is visible before SSE connects
  loadTopology();

  // 2. Start polling as fallback; SSE.onopen stops it if SSE works
  startPolling();

  // 3. Attempt Server-Sent Events (stops polling on success)
  startSSE();

  // Controls
  ($('refresh-btn') || {}).addEventListener?.('click', loadTopology);
  ($('fit-btn')     || {}).addEventListener?.('click', fitToView);
  ($('detail-close')|| {}).addEventListener?.('click', e => {
    e.stopPropagation?.();
    closeDetailPanel();
  });
  ($('filter-input')|| {}).addEventListener?.('input', e => {
    filterText = e.target.value.trim().toLowerCase();
    applyFilter();
  });

  document.addEventListener('click', e => {
    if (!e.target.closest?.('.node') && !e.target.closest?.('#detail-panel')) {
      closeDetailPanel();
    }
  });
});
