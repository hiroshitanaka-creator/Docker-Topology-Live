/* Docker Topology Live – browser UI (D3 v7 force-directed graph) */
'use strict';

const API_TOPOLOGY  = '/api/topology';
const REFRESH_MS    = 15_000;
const NODE_R        = { container: 20, network: 14 };

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

// ── DOM helpers ──────────────────────────────────────────────
function $(id) { return document.getElementById(id); }
function show(el) { if (el) el.classList.remove('hidden'); }
function hide(el) { if (el) el.classList.add('hidden'); }

// ── Colour ───────────────────────────────────────────────────
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

// ── Graph data prep ──────────────────────────────────────────
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

// ── SVG init (once) ──────────────────────────────────────────
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

// ── Full render ───────────────────────────────────────────────
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

  // Container → circle
  nodeSel.filter(d => d.kind === 'container')
    .append('circle')
    .attr('r', NODE_R.container)
    .attr('fill', nodeColor);

  // Network → diamond
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

// ── Filter ───────────────────────────────────────────────────
function applyFilter() {
  if (!g) return;
  g.selectAll('.node').each(function (d) {
    d3.select(this).style('opacity', matchesFilter(d) ? 1 : 0.12);
  });
}

// ── Tooltip ───────────────────────────────────────────────────
function onNodeOver(event, d) {
  const t = $('tooltip');
  if (!t) return;
  let html = `<strong>${d.label}</strong><br>`;
  if (d.kind === 'container') {
    html += `Status: ${d.status || '?'}<br>Image: ${d.image || '?'}`;
  } else {
    html += `Driver: ${d.driver || '?'}<br>Scope: ${d.scope || '?'}`;
  }
  t.innerHTML = html;
  t.style.left = (event.clientX + 14) + 'px';
  t.style.top  = (event.clientY - 10) + 'px';
  show(t);
}
function onNodeOut() { hide($('tooltip')); }

// ── Detail panel ─────────────────────────────────────────────
function onNodeClick(event, d) {
  const panel = $('detail-panel');
  $('detail-title').textContent = d.label;
  const body = $('detail-body');

  if (d.kind === 'container') {
    body.innerHTML = `
      <table>
        <tr><th>ID</th><td>${d.id}</td></tr>
        <tr><th>Image</th><td>${d.image || '—'}</td></tr>
        <tr><th>Status</th><td class="status-${d.status}">${d.status || '—'}</td></tr>
        <tr><th>State</th><td>${d.state || '—'}</td></tr>
        <tr><th>Kind</th><td>container</td></tr>
      </table>`;
  } else {
    body.innerHTML = `
      <table>
        <tr><th>ID</th><td>${d.id}</td></tr>
        <tr><th>Driver</th><td>${d.driver || '—'}</td></tr>
        <tr><th>Scope</th><td>${d.scope || '—'}</td></tr>
        <tr><th>Internal</th><td>${d.internal ? 'yes' : 'no'}</td></tr>
        <tr><th>Kind</th><td>network</td></tr>
      </table>`;
  }

  show(panel);
  event.stopPropagation();
}

// ── Stats bar ─────────────────────────────────────────────────
function updateStats(data) {
  const s = data.summary || {};
  const nodes = data.nodes || [];

  ($('stat-containers') || {}).textContent =
    s.containers ?? nodes.filter(n => n.kind === 'container').length;
  ($('stat-running') || {}).textContent    = s.runningContainers ?? '?';
  ($('stat-networks') || {}).textContent   =
    s.networks  ?? nodes.filter(n => n.kind === 'network').length;
  ($('stat-links') || {}).textContent      = s.links ?? (data.links || []).length;

  if (data.sample) show($('sample-badge')); else hide($('sample-badge'));
  ($('status-msg') || {}).textContent = 'Updated ' + new Date().toLocaleTimeString();
}

// ── Load & render ─────────────────────────────────────────────
async function loadTopology() {
  try {
    const resp = await fetch(API_TOPOLOGY, { cache: 'no-store' });
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const data = await resp.json();
    render(data);
    updateStats(data);
  } catch (err) {
    console.error('topology fetch error', err);
    ($('status-msg') || {}).textContent = '⚠ ' + err.message;
  }
}

// ── Fit to view ───────────────────────────────────────────────
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

// ── Boot ──────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  initSVG();
  loadTopology();
  setInterval(loadTopology, REFRESH_MS);

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
