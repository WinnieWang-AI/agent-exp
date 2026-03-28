/**
 * Agent Graph visualization using Cytoscape.js
 *
 * Renders agent topology, workflow steps, and deviation highlights.
 * Data is loaded from the AgentGraphViewDisplayBlock JSON.
 */

// ---- Node styles ----
const AG_NODE_STYLES = {
  agent:        { bg: '#3b82f6', border: '#1d4ed8', text: '#fff',    shape: 'round-rectangle' },
  tool:         { bg: '#10b981', border: '#059669', text: '#fff',    shape: 'ellipse' },
  task:         { bg: '#f59e0b', border: '#d97706', text: '#fff',    shape: 'round-rectangle' },
  decision:     { bg: '#8b5cf6', border: '#7c3aed', text: '#fff',    shape: 'diamond' },
  user_confirm: { bg: '#f472b6', border: '#ec4899', text: '#fff',    shape: 'hexagon' },
  begin:        { bg: '#6b7280', border: '#4b5563', text: '#fff',    shape: 'ellipse' },
  end:          { bg: '#6b7280', border: '#4b5563', text: '#fff',    shape: 'ellipse' },
};

// ---- Edge styles ----
const AG_EDGE_STYLES = {
  SUBAGENT:  { color: '#3b82f6', style: 'solid',  width: 2.5, arrow: 'triangle' },
  CHAT_WITH: { color: '#8b5cf6', style: 'dashed', width: 2,   arrow: 'triangle' },
  TOOL:      { color: '#6b7280', style: 'dotted', width: 1.5, arrow: 'none' },
  FLOW:      { color: '#f59e0b', style: 'solid',  width: 2,   arrow: 'triangle' },
  LOOP:      { color: '#ef4444', style: 'dashed', width: 2,   arrow: 'triangle' },
  DEVIATION: { color: '#ef4444', style: 'solid',  width: 3,   arrow: 'triangle' },
};

// ---- State ----
let agCy = null;
let agData = null;
let agViewMode = 'topology'; // 'topology' | 'workflow' | 'merged'
const agVisibleTypes = new Set([
  'agent', 'tool', 'task', 'decision', 'user_confirm', 'begin', 'end',
]);
let agDeviationHighlight = false;

// ---- Convert data to Cytoscape elements ----
function agConvertToElements(data, mode) {
  const nodes = [];
  const edges = [];
  let edgeId = 0;
  const eid = () => `ag_e${edgeId++}`;

  const topology = data.topology || { nodes: [], edges: [] };
  const workflow = data.workflow || null;
  const deviationReport = data.deviation_report || null;
  const traces = data.traces || {};

  // Collect step IDs with deviations for highlighting
  const deviatedSteps = new Set();
  if (deviationReport && deviationReport.step_deviations) {
    for (const d of deviationReport.step_deviations) {
      deviatedSteps.add(d.step_id);
    }
  }
  // Also check trace-level deviations
  for (const [stepId, stepTraces] of Object.entries(traces)) {
    for (const trace of stepTraces) {
      for (const call of (trace.calls || [])) {
        if (call.deviations && call.deviations.length > 0) {
          deviatedSteps.add(stepId);
        }
      }
    }
  }

  if (mode === 'topology' || mode === 'merged') {
    // Agent nodes
    for (const n of topology.nodes) {
      nodes.push({
        data: {
          id: n.id,
          label: n.name,
          fullLabel: `${n.name} (${n.tool_count} tools)`,
          nodeType: 'agent',
          raw: n,
          toolCount: n.tool_count,
          subagentCount: n.subagent_count,
        },
      });
    }

    // Agent edges
    for (const e of topology.edges) {
      edges.push({
        data: {
          id: eid(),
          source: e.source,
          target: e.target,
          edgeType: e.edge_type,
          label: e.description || '',
        },
      });
    }
  }

  if ((mode === 'workflow' || mode === 'merged') && workflow) {
    const prefix = mode === 'merged' ? 'wf_' : '';

    // Workflow step nodes
    for (const step of workflow.steps) {
      const hasDeviation = deviatedSteps.has(step.id);
      nodes.push({
        data: {
          id: prefix + step.id,
          label: step.label,
          fullLabel: `${step.label}${step.agent_call ? ' [' + step.agent_call + ']' : ''}`,
          nodeType: step.kind,
          raw: step,
          agentCall: step.agent_call || null,
          hasDeviation,
        },
      });
    }

    // Workflow edges
    for (const e of workflow.edges) {
      edges.push({
        data: {
          id: eid(),
          source: prefix + e.source,
          target: prefix + e.target,
          edgeType: e.is_loop ? 'LOOP' : 'FLOW',
          label: e.label || '',
        },
      });
    }

    // In merged mode, connect agent nodes to their workflow steps
    if (mode === 'merged') {
      for (const step of workflow.steps) {
        if (step.agent_call) {
          const agentNode = topology.nodes.find(n => n.name === step.agent_call || n.id === step.agent_call);
          if (agentNode) {
            edges.push({
              data: {
                id: eid(),
                source: prefix + step.id,
                target: agentNode.id,
                edgeType: 'TOOL',
                label: 'calls',
              },
            });
          }
        }
      }
    }
  }

  return { nodes, edges };
}

// ---- Build Cytoscape stylesheet ----
function agBuildStylesheet() {
  const styles = [
    // Base node
    {
      selector: 'node',
      style: {
        'label': 'data(label)',
        'text-valign': 'center',
        'text-halign': 'center',
        'font-size': 11,
        'font-weight': 500,
        'text-wrap': 'ellipsis',
        'text-max-width': 120,
        'width': 'label',
        'height': 30,
        'padding': '8px',
        'border-width': 2,
        'text-outline-width': 0,
      },
    },
    // Base edge
    {
      selector: 'edge',
      style: {
        'curve-style': 'bezier',
        'target-arrow-shape': 'triangle',
        'arrow-scale': 0.8,
        'font-size': 9,
        'text-rotation': 'autorotate',
        'text-margin-y': -8,
        'text-outline-width': 2,
        'text-outline-color': '#1a1a2e',
      },
    },
    // Edge labels
    {
      selector: 'edge[label]',
      style: {
        'label': 'data(label)',
      },
    },
  ];

  // Node type styles
  for (const [type, s] of Object.entries(AG_NODE_STYLES)) {
    styles.push({
      selector: `node[nodeType="${type}"]`,
      style: {
        'background-color': s.bg,
        'border-color': s.border,
        'color': s.text,
        'shape': s.shape,
      },
    });
  }

  // Edge type styles
  for (const [type, s] of Object.entries(AG_EDGE_STYLES)) {
    styles.push({
      selector: `edge[edgeType="${type}"]`,
      style: {
        'line-color': s.color,
        'target-arrow-color': s.color,
        'line-style': s.style,
        'width': s.width,
        'target-arrow-shape': s.arrow,
        'color': s.color,
      },
    });
  }

  // Deviation highlight
  styles.push({
    selector: 'node[?hasDeviation]',
    style: {
      'border-color': '#ef4444',
      'border-width': 3,
    },
  });

  // Deviation highlight when enabled
  styles.push({
    selector: '.deviation-glow',
    style: {
      'border-color': '#ef4444',
      'border-width': 4,
      'shadow-blur': 10,
      'shadow-color': '#ef4444',
      'shadow-opacity': 0.5,
    },
  });

  // Dimmed (filtered out)
  styles.push({
    selector: '.ag-hidden',
    style: {
      'display': 'none',
    },
  });

  // Highlighted
  styles.push({
    selector: '.ag-highlight',
    style: {
      'border-width': 4,
      'border-color': '#fff',
      'z-index': 999,
    },
  });

  // Dimmed neighbors
  styles.push({
    selector: '.ag-dimmed',
    style: {
      'opacity': 0.2,
    },
  });

  return styles;
}

// ---- Layout ----
function agRunLayout() {
  if (!agCy) return;
  const layout = agCy.layout({
    name: 'cose-bilkent',
    animate: false,
    nodeDimensionsIncludeLabels: true,
    idealEdgeLength: 100,
    nodeRepulsion: 8000,
    gravity: 0.25,
    gravityRange: 1.5,
    numIter: 2500,
    tile: true,
    tilingPaddingVertical: 20,
    tilingPaddingHorizontal: 20,
  });
  layout.run();
}

// ---- Filter ----
function agApplyFilters() {
  if (!agCy) return;
  agCy.batch(() => {
    agCy.nodes().forEach(n => {
      const type = n.data('nodeType');
      if (agVisibleTypes.has(type)) {
        n.removeClass('ag-hidden');
      } else {
        n.addClass('ag-hidden');
      }
    });

    // Show/hide deviation glow
    if (agDeviationHighlight) {
      agCy.nodes('[?hasDeviation]').addClass('deviation-glow');
    } else {
      agCy.nodes().removeClass('deviation-glow');
    }
  });
}

function agToggleType(type, btn) {
  if (agVisibleTypes.has(type)) {
    agVisibleTypes.delete(type);
    btn.classList.remove('active');
  } else {
    agVisibleTypes.add(type);
    btn.classList.add('active');
  }
  agApplyFilters();
}

function agToggleDeviations(btn) {
  agDeviationHighlight = !agDeviationHighlight;
  btn.classList.toggle('active', agDeviationHighlight);
  agApplyFilters();
}

function agSetView(mode, btn) {
  agViewMode = mode;
  document.querySelectorAll('.ag-view-toggle').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  if (agData) agInitGraph(agData);
}

// ---- Highlight neighbors on click ----
function agHighlightNeighbors(node) {
  if (!agCy) return;
  agCy.elements().removeClass('ag-highlight ag-dimmed');
  const neighborhood = node.closedNeighborhood();
  agCy.elements().not(neighborhood).addClass('ag-dimmed');
  node.addClass('ag-highlight');
}

// ---- Detail panel ----
function agShowDetail(nodeData) {
  const panel = document.getElementById('ag-detail');
  const body = document.getElementById('ag-detail-body');
  const title = document.getElementById('ag-detail-title');
  if (!panel || !body) return;

  title.textContent = nodeData.fullLabel || nodeData.label;
  let html = '';

  const type = nodeData.nodeType;
  html += `<span class="ag-detail-badge ag-type-${type}">${type}</span>`;

  if (type === 'agent') {
    const raw = nodeData.raw || {};
    html += `<div class="ag-detail-section">`;
    html += `<div class="ag-detail-section-title">Info</div>`;
    html += `<div class="ag-detail-field"><div class="ag-detail-field-label">Tools</div>`;
    html += `<div class="ag-detail-field-value">${raw.tool_count || 0} tools`;
    if (raw.tools && raw.tools.length) {
      html += '<br>' + raw.tools.map(t => `<span style="color:#6ee7b7;font-size:10px">${t}</span>`).join(', ');
    }
    html += `</div></div>`;
    html += `<div class="ag-detail-field"><div class="ag-detail-field-label">Subagents</div>`;
    html += `<div class="ag-detail-field-value">${raw.subagent_count || 0}</div></div>`;
    html += `</div>`;
  } else if (['task', 'decision', 'user_confirm', 'begin', 'end'].includes(type)) {
    const raw = nodeData.raw || {};
    html += `<div class="ag-detail-section">`;
    html += `<div class="ag-detail-section-title">Step Details</div>`;
    if (raw.description) {
      html += `<div class="ag-detail-field"><div class="ag-detail-field-label">Description</div>`;
      html += `<div class="ag-detail-field-value">${escapeHtml(raw.description)}</div></div>`;
    }
    if (raw.agent_call) {
      html += `<div class="ag-detail-field"><div class="ag-detail-field-label">Calls Agent</div>`;
      html += `<div class="ag-detail-field-value" style="color:#93c5fd">${raw.agent_call}</div></div>`;
    }
    html += `</div>`;

    // Show trace if available
    const stepId = raw.id;
    if (stepId && agData && agData.traces && agData.traces[stepId]) {
      html += agRenderTraceDetail(stepId, agData.traces[stepId]);
    }

    // Show deviations for this step
    if (stepId && agData && agData.deviation_report) {
      const stepDevs = (agData.deviation_report.step_deviations || []).filter(d => d.step_id === stepId);
      if (stepDevs.length > 0) {
        html += `<div class="ag-detail-section">`;
        html += `<div class="ag-detail-section-title">Deviations</div>`;
        for (const d of stepDevs) {
          html += `<div class="ag-deviation ${d.severity}">`;
          html += `<span class="ag-deviation-label">${d.severity}</span> `;
          html += `<strong>${d.deviation_type}</strong><br>`;
          html += escapeHtml(d.description);
          if (d.expected) {
            html += `<br><span style="font-size:10px;opacity:0.7">expected: ${escapeHtml(d.expected)} | actual: ${escapeHtml(d.actual || '')}</span>`;
          }
          html += `</div>`;
        }
        html += `</div>`;
      }
    }
  }

  body.innerHTML = html;
  panel.classList.add('open');
}

function agRenderTraceDetail(stepId, stepTraces) {
  if (!stepTraces || stepTraces.length === 0) return '';

  let html = `<div class="ag-detail-section">`;
  html += `<div class="ag-detail-section-title">Execution Trace</div>`;

  // Iteration tabs (if multiple)
  if (stepTraces.length > 1) {
    html += `<div class="ag-iter-tabs">`;
    for (let i = 0; i < stepTraces.length; i++) {
      const t = stepTraces[i];
      const hasDevs = t.calls.some(c => c.deviations && c.deviations.length > 0);
      html += `<button class="ag-iter-tab${i === 0 ? ' active' : ''}${hasDevs ? ' has-deviation' : ''}" `
            + `onclick="agSelectIteration('${stepId}', ${i}, this)">`
            + `#${t.iteration}${hasDevs ? '!' : ''}</button>`;
    }
    html += `</div>`;
  }

  // Render first iteration by default
  html += `<div id="ag-trace-calls-${stepId}">`;
  html += agRenderTraceCalls(stepTraces[0]);
  html += `</div>`;

  // Stats
  const trace = stepTraces[0];
  html += `<div style="font-size:10px;color:var(--text-dim);margin-top:4px">`;
  html += `${trace.total_tool_calls || 0} calls, ${(trace.total_tokens || 0).toLocaleString()} tokens`;
  html += `</div>`;

  html += `</div>`;
  return html;
}

function agRenderTraceCalls(trace) {
  if (!trace || !trace.calls) return '';
  let html = '';
  for (const call of trace.calls) {
    const hasDevs = call.deviations && call.deviations.length > 0;
    html += `<div class="ag-trace-call${hasDevs ? ' has-deviation' : ''}">`;
    html += `<span style="color:var(--text-dim);font-size:9px">#${call.seq}</span> `;
    html += `<span style="color:${call.role === 'assistant' ? '#93c5fd' : '#6ee7b7'};font-weight:600">${call.role}</span>`;
    if (call.tool_name) {
      html += ` <span style="color:var(--text-mid)">${call.tool_name}`;
      if (call.tool_args && call.tool_args.subagent_name) {
        html += ` &rarr; ${call.tool_args.subagent_name}`;
      }
      html += `</span>`;
    }
    if (call.token_usage) {
      html += ` <span style="font-size:9px;color:var(--text-dim);float:right">${call.token_usage.toLocaleString()} tok</span>`;
    }
    if (call.tool_args && call.tool_args.prompt) {
      const prompt = String(call.tool_args.prompt);
      html += `<div style="font-size:9px;color:var(--text-dim);margin-top:2px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${escapeHtml(prompt.slice(0, 200))}</div>`;
    }
    if (call.tool_result) {
      html += `<div style="font-size:9px;color:var(--text-dim);opacity:0.6;margin-top:2px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${escapeHtml(call.tool_result.slice(0, 200))}</div>`;
    }
    // Inline deviations
    if (hasDevs) {
      for (const dev of call.deviations) {
        html += `<div class="ag-deviation ${dev.severity}" style="margin-top:4px">`;
        html += `<span class="ag-deviation-label">${dev.severity}</span> ${escapeHtml(dev.rule)}`;
        if (dev.evidence) {
          html += `<br><span style="font-size:9px;opacity:0.7">${escapeHtml(dev.evidence)}</span>`;
        }
        html += `</div>`;
      }
    }
    html += `</div>`;
  }
  return html;
}

function agSelectIteration(stepId, idx, btn) {
  if (!agData || !agData.traces || !agData.traces[stepId]) return;
  const trace = agData.traces[stepId][idx];
  if (!trace) return;
  // Update active tab
  btn.parentElement.querySelectorAll('.ag-iter-tab').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  // Re-render calls
  const container = document.getElementById(`ag-trace-calls-${stepId}`);
  if (container) {
    container.innerHTML = agRenderTraceCalls(trace);
  }
}

function agHideDetail() {
  const panel = document.getElementById('ag-detail');
  if (panel) panel.classList.remove('open');
  if (agCy) agCy.elements().removeClass('ag-highlight ag-dimmed');
}

function escapeHtml(str) {
  const div = document.createElement('div');
  div.textContent = str;
  return div.innerHTML;
}

// ---- Init graph ----
function agInitGraph(data) {
  agData = data;
  const { nodes, edges } = agConvertToElements(data, agViewMode);

  if (agCy) agCy.destroy();

  // Show UI
  const emptyEl = document.getElementById('ag-empty');
  const toolbarEl = document.getElementById('ag-toolbar');
  const bodyEl = document.getElementById('ag-body');
  if (emptyEl) emptyEl.style.display = 'none';
  if (toolbarEl) toolbarEl.style.display = 'flex';
  if (bodyEl) bodyEl.style.display = 'flex';

  agCy = cytoscape({
    container: document.getElementById('ag-cy'),
    elements: { nodes, edges },
    style: agBuildStylesheet(),
    layout: { name: 'preset' },
    minZoom: 0.1,
    maxZoom: 4,
    wheelSensitivity: 0.3,
  });

  agCy.on('tap', 'node', function (evt) {
    const node = evt.target;
    agShowDetail(node.data());
    agHighlightNeighbors(node);
  });

  agCy.on('tap', function (evt) {
    if (evt.target === agCy) {
      agHideDetail();
    }
  });

  // Double-click on workflow node to expand trace
  agCy.on('dbltap', 'node', function (evt) {
    const node = evt.target;
    const raw = node.data('raw');
    if (raw && raw.id && agData.traces && agData.traces[raw.id]) {
      agShowDetail(node.data());
    }
  });

  agApplyFilters();
  agRunLayout();
}

// ---- Load data from JSON ----
function agLoadData(jsonData) {
  agInitGraph(jsonData);
}

// ---- Fit view ----
function agFitView() {
  if (agCy) agCy.fit(undefined, 40);
}

// ---- Re-layout ----
function agRelayout() {
  agRunLayout();
}
