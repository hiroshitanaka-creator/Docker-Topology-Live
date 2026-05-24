/* Docker Topology Live – browser UI (D3 v7 force-directed graph)
 *
 * Live-update strategy
 * --------------------
 * 1. One initial loadTopology() fetch on page load.
 * 2. EventSource('/api/events') for live Docker updates (SSE).
 *    - 'topology' events call the existing render/updateStats path.
 *    - 'heartbeat' events update the status bar only.
 *    - 'docker-event' events are logged (topology follows within ~350 ms).
 *    - 'error' events show a warning; the browser auto-reconnects.
 *    - onerror fires up to SSE_MAX_ERRORS times before falling back to polling.
 * 3. If EventSource is unsupported or fails SSE_MAX_ERRORS times,
 *    fall back to 15-second polling.
 *
 * Security: no innerHTML is used anywhere in this file.
 */
'use strict';

const API_TOPOLOGY  = '/api/topology';
const API_EVENTS    = '/api/events';
const REFRESH_MS    = 15_000;
const NODE_R        = { container: 20, network: 14 };
const SSE_MAX_ERRORS = 3;

const STATUS_COLOR = {
  running:    '#4ade80',
  exited:     '#f87171',
  dead:       '#f87171',
  paused:     '#fb923c',
  restarting: '#60a5fa',
  created:    '#94a3b8',
  network:    '#818cf8',
};

let svg, g, zoomBehavior, simulation;
let filterText = '';

// SSE / polling state
let sseSource    = null;
let sseErrorCount = 0;
let pollingTimer = null;

// DOM helpers
function $(id) { return document.getElementById(id); }
function show(el) { if (el) el.classList.remove('hidden'); }
function hide(el) { if (el) el.classList.add('hidden'); }

function updateStatus(msg) {
  const el = $('status-msg');
  if (el) el.textContent = msg;
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
}

// Filter
function applyFilter() {
  if (!g) return;
  g.selectAll('.node').each(function (d) {
    d3.select(this).style('opacity', matchesFilter(d) ? 1 : 0.12);
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
      body.appendChild(_makeTable(mounts.map(m => [
        m.destination || '?',
        (m.source ? m.source + ' ' : '') +
          '(' + (m.type || 'volume') + ', ' + (m.rw ? 'rw' : 'ro') + ')',
      ])));
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

  } else {
    body.appendChild(_makeTable([
      ['ID',       d.id],
      ['Driver',   d.driver   || '—'],
      ['Scope',    d.scope    || '—'],
      ['Internal', d.internal ? 'yes' : 'no'],
      ['Kind',     'network'],
    ]));
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

// One-shot topology fetch (used for initial load and polling fallback)
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
    // Browser doesn't support SSE; stay on polling
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

  // Heartbeat (sample mode idle signal)
  sseSource.addEventListener('heartbeat', () => {
    updateStatus('● Live (idle)  · ' + new Date().toLocaleTimeString());
  });

  // Normalized Docker event notification (topology snapshot follows ~350 ms later)
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
      console.warn('SSE stream error:', data.error);
      updateStatus('⚠ ' + (data.error || 'stream error'));
    } catch (_) {}
  });

  // Connection-level error (network drop, server restart, etc.)
  sseSource.onerror = () => {
    sseErrorCount++;
    if (sseErrorCount < SSE_MAX_ERRORS) {
      updateStatus('↺ Reconnecting… (' + sseErrorCount + '/' + SSE_MAX_ERRORS + ')');
    } else {
      // Give up on SSE; fall back to polling
      if (sseSource) {
        sseSource.close();
        sseSource = null;
      }
      updateStatus('↻ Polling fallback');
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

  // 1. Immediate one-shot fetch so the graph is populated before SSE connects
  loadTopology();

  // 2. Start polling as fallback; SSE.onopen will clear it if SSE works
  startPolling();

  // 3. Attempt Server-Sent Events (stops polling on success)
  startSSE();

  // Controls
  ($('refresh-btn') || {}).addEventListener?.('click', loadTopology);
  ($('fit-btn')     || {}).addEventListener?.('click', fitToView);
  ($('detail-close')|| {}).addEventListener?.('click', () => hide($('detail-panel')));
  ($('filter-input')|| {}).addEventListener?.('input', e => {
    filterText = e.target.value.trim().toLowerCase();
    applyFilter();
  });

  document.addEventListener('click', e => {
    if (!e.target.closest?.('.node')) hide($('detail-panel'));
  });
});
