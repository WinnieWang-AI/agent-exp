/**
 * Three-layer plan comparison visualization.
 *
 * Renders three execution plans (ideal / predicted / actual) side-by-side
 * with gap highlighting and a diagnosis panel.
 *
 * Data source: PlanCompareViewDisplayBlock from AnalyzeAgentGraph(mode="compare").
 */

// ---- Palette ----
const PC_STYLES = {
  node: {
    delegation: { bg: '#1e2a4a', border: '#3b82f6', text: '#93c5fd', shape: 'round-rectangle' },
    tool_call:  { bg: '#1a2e28', border: '#10b981', text: '#6ee7b7', shape: 'ellipse' },
    decision:   { bg: '#2a1f4e', border: '#8b5cf6', text: '#c4b5fd', shape: 'diamond' },
    read:       { bg: '#332820', border: '#b45309', text: '#fbbf24', shape: 'ellipse' },
    write:      { bg: '#3b1c2e', border: '#be185d', text: '#f9a8d4', shape: 'ellipse' },
  },
  gap: {
    error:   '#ef4444',
    warning: '#f59e0b',
    info:    '#6b7280',
  },
  layer: {
    ideal:     { accent: '#10b981', label: 'Ideal Plan' },
    predicted: { accent: '#3b82f6', label: 'Prompt Prediction' },
    actual:    { accent: '#f59e0b', label: 'Actual Behavior' },
  },
};

// ---- State ----
let pcData = null;
let pcInstances = {};  // { ideal: cy, predicted: cy, actual: cy }

// ---- Helpers ----
function _pcEsc(s) {
  if (typeof s !== 'string') s = String(s ?? '');
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

// ---- Convert a single ExecutionPlan to cytoscape elements ----
function pcPlanToElements(plan, gapStepIds) {
  if (!plan) return { nodes: [], edges: [] };
  const nodes = [];
  const edges = [];
  let eidx = 0;

  const stepById = {};
  for (const s of plan.steps) stepById[s.id] = s;

  // Build nodes
  for (const step of plan.steps) {
    const hasGap = gapStepIds.has(step.id);
    nodes.push({
      data: {
        id: step.id,
        label: step.label,
        fullLabel: step.agent ? `${step.agent}/${step.label}` : step.label,
        nodeType: step.kind,
        agent: step.agent || '',
        tool: step.tool || '',
        rationale: step.rationale || '',
        resources_in: step.resources_in || [],
        resources_out: step.resources_out || [],
        parallel_group: step.parallel_group || '',
        result_summary: step.result_summary || '',
        is_error: step.is_error || false,
        hasGap,
        raw: step,
      },
    });
  }

  // Build edges from step_order (sequential between batches)
  const order = plan.step_order || [];
  for (let i = 1; i < order.length; i++) {
    const prevBatch = order[i - 1];
    const curBatch = order[i];
    for (const src of prevBatch) {
      for (const dst of curBatch) {
        if (stepById[src] && stepById[dst]) {
          edges.push({
            data: {
              id: `pc_e${eidx++}`,
              source: src,
              target: dst,
              edgeType: 'flow',
            },
          });
        }
      }
    }
  }

  // Mark parallel within batch
  for (const batch of order) {
    if (batch.length > 1) {
      for (let i = 1; i < batch.length; i++) {
        edges.push({
          data: {
            id: `pc_e${eidx++}`,
            source: batch[0],
            target: batch[i],
            edgeType: 'parallel',
          },
        });
      }
    }
  }

  return { nodes, edges };
}

// ---- Stylesheet ----
function pcBuildStylesheet() {
  const styles = [
    {
      selector: 'node',
      style: {
        'label': 'data(label)',
        'text-valign': 'center',
        'text-halign': 'center',
        'font-size': 10,
        'font-weight': 500,
        'text-wrap': 'ellipsis',
        'text-max-width': 100,
        'width': 'label',
        'height': 26,
        'padding': '6px',
        'border-width': 2,
      },
    },
    {
      selector: 'edge',
      style: {
        'curve-style': 'bezier',
        'target-arrow-shape': 'triangle',
        'arrow-scale': 0.7,
        'width': 1.5,
        'line-color': '#4b5563',
        'target-arrow-color': '#4b5563',
      },
    },
    {
      selector: 'edge[edgeType="parallel"]',
      style: {
        'line-style': 'dashed',
        'line-color': '#6b7280',
        'target-arrow-color': '#6b7280',
        'target-arrow-shape': 'none',
      },
    },
  ];

  for (const [kind, s] of Object.entries(PC_STYLES.node)) {
    styles.push({
      selector: `node[nodeType="${kind}"]`,
      style: {
        'background-color': s.bg,
        'border-color': s.border,
        'color': s.text,
        'shape': s.shape,
      },
    });
  }

  // Gap highlight
  styles.push({
    selector: 'node[?hasGap]',
    style: {
      'border-color': '#ef4444',
      'border-width': 3,
    },
  });

  // Error node
  styles.push({
    selector: 'node[?is_error]',
    style: {
      'background-color': '#3b1520',
      'border-color': '#ef4444',
    },
  });

  // Dimmed
  styles.push({ selector: '.pc-dimmed', style: { 'opacity': 0.15 } });
  styles.push({ selector: '.pc-highlight', style: { 'border-width': 4, 'border-color': '#fff', 'z-index': 999 } });

  return styles;
}

// ---- Render one lane ----
function pcRenderLane(containerId, plan, gapStepIds) {
  const container = document.getElementById(containerId);
  if (!container) return null;
  if (!plan) {
    container.innerHTML = '<div style="display:flex;align-items:center;justify-content:center;height:100%;color:var(--text-dim);font-size:12px;">No data</div>';
    return null;
  }

  // Clear
  container.innerHTML = '';
  const cyDiv = document.createElement('div');
  cyDiv.style.cssText = 'width:100%;height:100%;';
  container.appendChild(cyDiv);

  const { nodes, edges } = pcPlanToElements(plan, gapStepIds);

  const cy = cytoscape({
    container: cyDiv,
    elements: { nodes, edges },
    style: pcBuildStylesheet(),
    layout: {
      name: 'dagre',
      rankDir: 'TB',
      nodeSep: 20,
      rankSep: 35,
      animate: false,
    },
    minZoom: 0.3,
    maxZoom: 3,
    wheelSensitivity: 0.3,
    userPanningEnabled: true,
    userZoomingEnabled: true,
    boxSelectionEnabled: false,
  });

  cy.on('tap', 'node', evt => {
    const nd = evt.target.data();
    pcShowStepDetail(nd);
    // Highlight across all lanes
    pcHighlightStep(nd.id);
  });

  cy.on('tap', evt => {
    if (evt.target === cy) {
      pcClearHighlight();
      pcHideDetail();
    }
  });

  setTimeout(() => cy.fit(undefined, 20), 100);
  return cy;
}

// ---- Highlight matching step across lanes ----
function pcHighlightStep(stepId) {
  // Find matching steps by label/agent/tool signature
  for (const [key, cy] of Object.entries(pcInstances)) {
    if (!cy) continue;
    cy.elements().removeClass('pc-highlight pc-dimmed');
    const match = cy.nodes().filter(n => {
      const d = n.data();
      return d.id === stepId || d.label === stepId;
    });
    if (match.length > 0) {
      const hood = match.closedNeighborhood();
      cy.elements().not(hood).addClass('pc-dimmed');
      match.addClass('pc-highlight');
    }
  }
}

function pcClearHighlight() {
  for (const cy of Object.values(pcInstances)) {
    if (cy) cy.elements().removeClass('pc-highlight pc-dimmed');
  }
}

// ---- Step detail panel ----
function pcShowStepDetail(nd) {
  const panel = document.getElementById('pc-detail');
  const body = document.getElementById('pc-detail-body');
  const title = document.getElementById('pc-detail-title');
  if (!panel || !body) return;

  title.textContent = nd.fullLabel || nd.label;
  let h = '';

  const kindStyle = PC_STYLES.node[nd.nodeType] || PC_STYLES.node.tool_call;
  h += `<span style="display:inline-block;padding:1px 8px;border-radius:8px;font-size:10px;font-weight:600;background:${kindStyle.border};color:#fff;margin-bottom:6px;">${nd.nodeType}</span>`;
  if (nd.agent) {
    h += ` <span style="display:inline-block;padding:1px 8px;border-radius:8px;font-size:10px;font-weight:600;background:#1e40af;color:#93c5fd;">${_pcEsc(nd.agent)}</span>`;
  }

  if (nd.tool) {
    h += `<div style="margin-top:8px;font-size:11px;"><strong style="color:#6ee7b7;">Tool:</strong> ${_pcEsc(nd.tool)}</div>`;
  }

  if (nd.rationale) {
    h += `<div style="margin-top:8px;font-size:11px;color:var(--text-mid);"><strong>Rationale:</strong> ${_pcEsc(nd.rationale)}</div>`;
  }

  if (nd.resources_in && nd.resources_in.length) {
    h += `<div style="margin-top:6px;font-size:10px;"><strong style="color:#fbbf24;">Inputs:</strong> ${nd.resources_in.map(r => _pcEsc(r)).join(', ')}</div>`;
  }
  if (nd.resources_out && nd.resources_out.length) {
    h += `<div style="margin-top:4px;font-size:10px;"><strong style="color:#f9a8d4;">Outputs:</strong> ${nd.resources_out.map(r => _pcEsc(r)).join(', ')}</div>`;
  }

  if (nd.result_summary) {
    const rc = nd.is_error ? '#ef4444' : '#6ee7b7';
    h += `<div style="margin-top:8px;font-size:10px;color:${rc};"><strong>${nd.is_error ? 'Error' : 'Result'}:</strong> ${_pcEsc(nd.result_summary)}</div>`;
  }

  if (nd.parallel_group) {
    h += `<div style="margin-top:6px;font-size:10px;color:#f59e0b;">Parallel group: ${_pcEsc(nd.parallel_group)}</div>`;
  }

  // Show gaps for this step
  if (pcData && pcData.comparison && pcData.comparison.gaps) {
    const stepGaps = pcData.comparison.gaps.filter(g => g.step_id === nd.id);
    if (stepGaps.length) {
      h += `<div style="margin-top:10px;border-top:1px solid var(--border);padding-top:8px;">`;
      h += `<strong style="font-size:11px;">Gaps (${stepGaps.length}):</strong>`;
      for (const g of stepGaps) {
        const gc = PC_STYLES.gap[g.severity] || '#6b7280';
        h += `<div style="margin-top:6px;padding:4px 8px;border-left:3px solid ${gc};background:rgba(0,0,0,0.2);border-radius:0 4px 4px 0;font-size:10px;">`;
        h += `<span style="color:${gc};font-weight:600;">[${g.severity}]</span> ${_pcEsc(g.gap_type)} (${g.layers[0]} vs ${g.layers[1]})<br>`;
        h += `${_pcEsc(g.description)}`;
        if (g.suggestion) h += `<br><span style="color:var(--text-dim);">&rarr; ${_pcEsc(g.suggestion)}</span>`;
        h += `</div>`;
      }
      h += `</div>`;
    }
  }

  body.innerHTML = h;
  panel.classList.add('open');
}

function pcHideDetail() {
  const panel = document.getElementById('pc-detail');
  if (panel) panel.classList.remove('open');
}

// ---- Gap summary panel ----
function pcRenderGapSummary(container, comparison) {
  if (!container || !comparison) return;
  const gaps = comparison.gaps || [];
  let h = '';

  // Diagnosis
  if (comparison.diagnosis) {
    h += `<div style="padding:8px 10px;background:var(--surface2);border-radius:6px;margin-bottom:10px;font-size:11px;line-height:1.6;color:var(--text);">${_pcEsc(comparison.diagnosis)}</div>`;
  }

  // Stats
  const nErr = gaps.filter(g => g.severity === 'error').length;
  const nWarn = gaps.filter(g => g.severity === 'warning').length;
  const nInfo = gaps.filter(g => g.severity === 'info').length;
  h += `<div style="font-size:11px;color:var(--text-mid);margin-bottom:8px;">`;
  h += `Gaps: <span style="color:#ef4444;font-weight:600">${nErr} errors</span>, `;
  h += `<span style="color:#f59e0b;font-weight:600">${nWarn} warnings</span>, `;
  h += `<span style="color:#6b7280;">${nInfo} info</span>`;
  h += `</div>`;

  // Gap list grouped by layer pair
  const groups = {};
  for (const g of gaps) {
    const key = `${g.layers[0]} vs ${g.layers[1]}`;
    if (!groups[key]) groups[key] = [];
    groups[key].push(g);
  }

  for (const [key, gapList] of Object.entries(groups)) {
    h += `<div style="margin-top:8px;"><div style="font-size:10px;font-weight:600;color:var(--text-dim);text-transform:uppercase;margin-bottom:4px;">${_pcEsc(key)}</div>`;
    for (const g of gapList) {
      const gc = PC_STYLES.gap[g.severity] || '#6b7280';
      h += `<div style="padding:4px 8px;border-left:3px solid ${gc};margin-bottom:4px;font-size:10px;line-height:1.5;background:rgba(0,0,0,0.15);border-radius:0 4px 4px 0;">`;
      h += `<span style="color:${gc};font-weight:600;">${g.severity}</span> `;
      h += `<span style="color:var(--text-mid);">${_pcEsc(g.gap_type)}</span>: ${_pcEsc(g.description)}`;
      if (g.suggestion) h += `<br><span style="color:var(--text-dim);">&rarr; ${_pcEsc(g.suggestion)}</span>`;
      h += `</div>`;
    }
    h += `</div>`;
  }

  container.innerHTML = h;
}

// ---- Main: render full comparison ----
function pcRenderComparison(data) {
  pcData = data;
  const comparison = data.comparison;
  if (!comparison) return;

  // Destroy old instances
  for (const cy of Object.values(pcInstances)) { if (cy) cy.destroy(); }
  pcInstances = {};

  // Collect gap step IDs per layer
  const gapSteps = { ideal: new Set(), predicted: new Set(), actual: new Set() };
  for (const g of (comparison.gaps || [])) {
    if (g.step_id) {
      for (const layer of g.layers) {
        if (gapSteps[layer]) gapSteps[layer].add(g.step_id);
      }
    }
  }

  // Render three lanes
  pcInstances.ideal = pcRenderLane('pc-lane-ideal', comparison.ideal, gapSteps.ideal);
  pcInstances.predicted = pcRenderLane('pc-lane-predicted', comparison.predicted, gapSteps.predicted);
  pcInstances.actual = pcRenderLane('pc-lane-actual', comparison.actual, gapSteps.actual);

  // Render gap summary
  pcRenderGapSummary(document.getElementById('pc-gaps'), comparison);

  // Task description
  const taskEl = document.getElementById('pc-task');
  if (taskEl && comparison.task_description) {
    const desc = comparison.task_description.length > 120
      ? comparison.task_description.slice(0, 120) + '...'
      : comparison.task_description;
    taskEl.textContent = desc;
    taskEl.title = comparison.task_description;
  }
}

// ---- Show/hide panel content ----
function pcShowContent() {
  const empty = document.getElementById('pc-empty');
  const lanes = document.getElementById('pc-lanes');
  const bottom = document.getElementById('pc-bottom');
  if (empty) empty.style.display = 'none';
  if (lanes) lanes.style.display = 'flex';
  if (bottom) bottom.style.display = 'flex';
}

// ---- Fit all lanes ----
function pcFitAll() {
  for (const cy of Object.values(pcInstances)) {
    if (cy) cy.fit(undefined, 20);
  }
}

// ---- Load from display block data ----
function pcLoadFromDisplayBlock(blockData) {
  pcShowContent();
  pcRenderComparison(blockData);
}

// ---- Show Plan Compare in optimizer sidebar ----
function pcShowPanel() {
  // Switch to Plan Compare tab and open sidebar
  if (typeof optSbSwitchTab === 'function') optSbSwitchTab('plancompare', null);
  if (typeof optSidebarShow === 'function') optSidebarShow();
  // Show Fit button
  const fitBtn = document.getElementById('pc-fit-btn');
  if (fitBtn) fitBtn.style.display = '';
  setTimeout(() => pcOnPanelVisible(), 50);
}

// ---- Called when plan compare tab becomes visible to resize cytoscape ----
function pcOnPanelVisible() {
  for (const cy of Object.values(pcInstances)) {
    if (cy) { cy.resize(); cy.fit(undefined, 20); }
  }
}

// ---- Resize drag handler for optimizer sidebar ----
document.addEventListener('DOMContentLoaded', () => {
  const handle = document.getElementById('opt-resize-handle');
  const sidebar = document.getElementById('opt-sidebar');
  if (!handle || !sidebar) return;
  let dragging = false, startX, startW;
  handle.addEventListener('mousedown', e => {
    e.preventDefault();
    dragging = true;
    startX = e.clientX;
    startW = sidebar.offsetWidth;
    document.body.style.cursor = 'col-resize';
    document.body.style.userSelect = 'none';
  });
  document.addEventListener('mousemove', e => {
    if (!dragging) return;
    const newW = Math.max(250, Math.min(startW + startX - e.clientX, window.innerWidth * 0.7));
    sidebar.style.width = newW + 'px';
  });
  document.addEventListener('mouseup', () => {
    if (!dragging) return;
    dragging = false;
    document.body.style.cursor = '';
    document.body.style.userSelect = '';
    pcOnPanelVisible();
  });
});
