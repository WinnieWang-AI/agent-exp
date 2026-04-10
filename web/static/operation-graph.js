/**
 * Operation Graph visualization using Cytoscape.js
 *
 * Renders agent execution memory: resource nodes, operation edges, constraint nodes.
 * Supports error analysis, filtering, and real-time status updates.
 */

// ---- Node styles by resource type ----
// Muted, cohesive palette for dark background
const OP_NODE_STYLES = {
  input:      { bg: '#3d4455', border: '#5a6178', text: '#c8cdd8', shape: 'diamond' },
  json:       { bg: '#2b3a52', border: '#4a7ab5', text: '#a8c8e8', shape: 'round-rectangle' },
  image:      { bg: '#1e3a32', border: '#3d8b6e', text: '#8fd4b8', shape: 'ellipse' },
  video:      { bg: '#2a2850', border: '#6e6aaf', text: '#b5b2e0', shape: 'round-rectangle' },
  audio:      { bg: '#3d3220', border: '#a88a4a', text: '#dbc88e', shape: 'ellipse' },
  constraint: { bg: '#3d2020', border: '#b05050', text: '#e8a0a0', shape: 'round-rectangle' },
};

// ---- Edge styles by operation status ----
const OP_EDGE_STYLES = {
  planned: { color: '#4a5060', style: 'dashed', width: 1.5 },
  running: { color: '#c9962a', style: 'solid',  width: 2.5 },
  done:    { color: '#3d8b6e', style: 'solid',  width: 2 },
  failed:  { color: '#c05050', style: 'solid',  width: 2.5 },
  skipped: { color: '#4a5060', style: 'dotted', width: 1.5 },
};

// ---- Convert tasks → Cytoscape elements (Task Layer) ----
function convertTaskLayerToElements(data) {
  const nodes = [];
  const edges = [];
  let edgeIdx = 0;
  const eid = () => `te${edgeIdx++}`;

  for (const task of (data.tasks || [])) {
    // Compute progress: count operations by status
    const ops = (data.operations || []).filter(o => (task.operations || []).includes(o.id));
    const done = ops.filter(o => o.status === 'done').length;
    const failed = ops.filter(o => o.status === 'failed').length;
    const total = ops.length;
    const progress = total > 0 ? `${done}/${total}` : '';

    // Build rich multi-line label
    const statusIcon = { verified: '✓', rejected: '✗', failed: '✗', running: '⟳', planned: '○', done: '◎' }[task.status] || '';
    const statusWord = { verified: 'PASSED', rejected: 'REJECTED', failed: 'FAILED', running: 'RUNNING', planned: 'PLANNED', done: 'DONE' }[task.status] || '';

    // Line 1: status icon + task name
    let label = `${statusIcon} ${task.name}`;
    // Line 2: purpose (truncated)
    if (task.purpose) {
      const shortPurpose = task.purpose.length > 30 ? task.purpose.slice(0, 28) + '..' : task.purpose;
      label += `\n${shortPurpose}`;
    }
    // Line 3: progress + verification summary
    const parts = [];
    if (progress) parts.push(`ops: ${progress}`);
    if (task.verification && task.verification.summary) {
      const vs = task.verification.summary;
      parts.push(vs.length > 24 ? vs.slice(0, 22) + '..' : vs);
    } else if (statusWord) {
      parts.push(statusWord);
    }
    if (parts.length) label += `\n${parts.join(' | ')}`;

    nodes.push({
      data: {
        id: task.id,
        label: label,
        fullLabel: task.name,
        nodeType: '_task',
        status: task.status || 'planned',
        progress: progress,
        done: done, failed: failed, total: total,
        raw: task,
      },
    });

    // Dependency edges between tasks
    for (const depId of (task.depends_on || [])) {
      edges.push({
        data: { id: eid(), source: depId, target: task.id, edgeType: 'DEPENDS_ON', status: task.status },
      });
    }
  }

  return { nodes, edges };
}

// ---- Layout for task layer ----
function computeTaskLayerPositions(data) {
  const pos = {};
  const tasks = data.tasks || [];
  if (tasks.length === 0) return pos;

  // Topological sort by depends_on
  const taskMap = {};
  for (const t of tasks) taskMap[t.id] = t;
  const depth = {};
  const visited = new Set();

  function getDepth(id) {
    if (depth[id] !== undefined) return depth[id];
    if (visited.has(id)) return 0;
    visited.add(id);
    const t = taskMap[id];
    if (!t || !t.depends_on || t.depends_on.length === 0) { depth[id] = 0; return 0; }
    let maxD = 0;
    for (const dep of t.depends_on) {
      maxD = Math.max(maxD, getDepth(dep) + 1);
    }
    depth[id] = maxD;
    return maxD;
  }
  for (const t of tasks) getDepth(t.id);

  // Group by depth
  const groups = {};
  for (const t of tasks) {
    const d = depth[t.id] || 0;
    if (!groups[d]) groups[d] = [];
    groups[d].push(t.id);
  }

  const X_GAP = 340;
  const Y_GAP = 120;
  const X_START = 150;
  const Y_START = 80;
  const cols = Object.keys(groups).map(Number).sort((a, b) => a - b);
  const maxGroupSize = Math.max(...cols.map(c => groups[c].length));

  for (const c of cols) {
    const group = groups[c];
    const totalH = (group.length - 1) * Y_GAP;
    const yOff = Y_START + (maxGroupSize - 1) * Y_GAP / 2 - totalH / 2;
    for (let i = 0; i < group.length; i++) {
      pos[group[i]] = { x: X_START + c * X_GAP, y: yOff + i * Y_GAP };
    }
  }
  return pos;
}

// ---- Convert operations → Cytoscape elements (Execution Layer, for a single task) ----
function convertTaskDetailToElements(data, taskId) {
  const task = (data.tasks || []).find(t => t.id === taskId);
  if (!task) return { nodes: [], edges: [] };

  const opIds = new Set(task.operations || []);
  const resIds = new Set([...(task.inputs || []), ...(task.outputs || [])]);

  // Collect resources referenced by task operations
  const ops = (data.operations || []).filter(o => opIds.has(o.id));
  for (const op of ops) {
    for (const r of (op.inputs || [])) resIds.add(r);
    for (const r of (op.outputs || [])) resIds.add(r);
  }

  const nodes = [];
  const edges = [];
  let edgeIdx = 0;
  const eid = () => `de${edgeIdx++}`;

  // Resource nodes
  for (const res of (data.resources || [])) {
    if (!resIds.has(res.id)) continue;
    nodes.push({
      data: {
        id: res.id, label: res.plan?.description || res.id,
        fullLabel: res.plan?.description || res.id,
        nodeType: res.type || 'input', status: res.status || 'planned',
        raw: res,
      },
    });
  }

  // Operation nodes + edges
  for (const op of ops) {
    const opStatus = op.status || 'planned';
    const toolName = op.tool || '';
    const duration = op.actual?.duration_s;
    const attempts = (op.attempts || []).length;
    let label = toolName;
    if (opStatus === 'done' && duration) label += ` ${duration}s`;
    if (opStatus === 'failed') label += ' FAILED';
    if (attempts > 1) label += ` (x${attempts})`;

    nodes.push({
      data: {
        id: op.id, label: label, fullLabel: `${toolName}: ${op.plan?.description || op.id}`,
        nodeType: '_operation', status: opStatus, tool: toolName,
        agent: op.agent || '', attempts: attempts, raw: op,
      },
    });
    for (const inp of (op.inputs || [])) {
      edges.push({ data: { id: eid(), source: inp, target: op.id, edgeType: 'INPUT', status: opStatus } });
    }
    for (const out of (op.outputs || [])) {
      edges.push({ data: { id: eid(), source: op.id, target: out, edgeType: 'OUTPUT', status: opStatus } });
    }
  }

  // Constraints related to these operations
  for (const c of (data.constraints || [])) {
    const related = (c.related_ops || []).filter(id => opIds.has(id));
    if (related.length === 0) continue;
    nodes.push({
      data: {
        id: c.id, label: c.rule ? (c.rule.length > 25 ? c.rule.slice(0, 25) + '...' : c.rule) : c.id,
        fullLabel: c.rule || c.id, nodeType: 'constraint', status: 'done', raw: c,
      },
    });
    for (const opId of related) {
      edges.push({ data: { id: eid(), source: c.id, target: opId, edgeType: 'CONSTRAINT', status: 'done' } });
    }
  }

  // Filter edges to valid nodes
  const nodeIds = new Set(nodes.map(n => n.data.id));
  return { nodes, edges: edges.filter(e => nodeIds.has(e.data.source) && nodeIds.has(e.data.target)) };
}

// ---- Convert full graph → Cytoscape elements (flat view, backward compat) ----
function convertOpGraphToElements(data) {
  const nodes = [];
  const edges = [];
  let edgeIdx = 0;
  const eid = () => `ope${edgeIdx++}`;

  // Resource nodes
  for (const res of (data.resources || [])) {
    nodes.push({
      data: {
        id: res.id,
        label: res.plan?.description || res.id,
        fullLabel: res.plan?.description || res.id,
        nodeType: res.type || 'input',
        status: res.status || 'planned',
        path: res.path || '',
        raw: res,
      },
    });
  }

  // Constraint nodes
  for (const c of (data.constraints || [])) {
    nodes.push({
      data: {
        id: c.id,
        label: c.rule ? (c.rule.length > 30 ? c.rule.slice(0, 30) + '...' : c.rule) : c.id,
        fullLabel: c.rule || c.id,
        nodeType: 'constraint',
        status: 'done',
        raw: c,
      },
    });
    // Connect constraint to related operations
    for (const opId of (c.related_ops || [])) {
      edges.push({
        data: { id: eid(), source: c.id, target: opId, edgeType: 'CONSTRAINT', status: 'done' },
      });
    }
  }

  // Operation edges (they connect input resources → output resources)
  for (const op of (data.operations || [])) {
    const opStatus = op.status || 'planned';
    const toolName = op.tool || '';
    const duration = op.actual?.duration_s;
    const attempts = (op.attempts || []).length;
    let label = toolName;
    if (opStatus === 'done' && duration) label += ` ${duration}s`;
    if (opStatus === 'failed') label += ' FAILED';
    if (attempts > 1) label += ` (x${attempts})`;

    // Create a node for the operation (so we can show details on click)
    const opNodeId = op.id;
    nodes.push({
      data: {
        id: opNodeId,
        label: label,
        fullLabel: `${toolName}: ${op.plan?.description || op.id}`,
        nodeType: '_operation',
        status: opStatus,
        tool: toolName,
        agent: op.agent || '',
        attempts: attempts,
        raw: op,
      },
    });

    // Edges from inputs → operation node
    for (const inputId of (op.inputs || [])) {
      edges.push({
        data: {
          id: eid(), source: inputId, target: opNodeId,
          edgeType: 'INPUT', status: opStatus,
        },
      });
    }

    // Edges from operation node → outputs
    for (const outputId of (op.outputs || [])) {
      edges.push({
        data: {
          id: eid(), source: opNodeId, target: outputId,
          edgeType: 'OUTPUT', status: opStatus,
        },
      });
    }
  }

  // Filter out edges referencing nonexistent nodes
  const nodeIds = new Set(nodes.map(n => n.data.id));
  const validEdges = edges.filter(e => nodeIds.has(e.data.source) && nodeIds.has(e.data.target));

  return { nodes, edges: validEdges };
}

// ---- Build Cytoscape stylesheet for operation graph ----
function buildOpGraphStylesheet() {
  const styles = [
    {
      selector: 'node',
      style: {
        'label': 'data(label)',
        'text-valign': 'center',
        'text-halign': 'center',
        'font-size': '10px',
        'font-family': '-apple-system, BlinkMacSystemFont, sans-serif',
        'color': '#fff',
        'text-wrap': 'ellipsis',
        'text-max-width': '120px',
        'width': 'label',
        'height': 30,
        'padding': '8px',
        'border-width': 2,
        'text-outline-width': 0,
      },
    },
    {
      selector: 'node:selected',
      style: {
        'border-width': 3, 'border-color': '#fff',
        'overlay-color': '#fff', 'overlay-opacity': 0.1,
      },
    },
    {
      selector: 'edge',
      style: {
        'width': 1.5,
        'line-color': '#4b5563',
        'target-arrow-color': '#4b5563',
        'target-arrow-shape': 'triangle',
        'arrow-scale': 0.8,
        'curve-style': 'bezier',
        'opacity': 0.7,
      },
    },
    { selector: '.hidden', style: { 'display': 'none' } },
    { selector: '.highlighted', style: { 'opacity': 1 } },
    { selector: '.dimmed', style: { 'opacity': 0.15 } },
    { selector: '.error-dimmed', style: { 'opacity': 0.15 } },
  ];

  // Resource node type styles
  for (const [type, s] of Object.entries(OP_NODE_STYLES)) {
    styles.push({
      selector: `node[nodeType="${type}"]`,
      style: { 'background-color': s.bg, 'border-color': s.border, 'color': s.text, 'shape': s.shape },
    });
  }

  // Operation node (small pill shape, acts as edge label)
  styles.push({
    selector: 'node[nodeType="_operation"]',
    style: {
      'background-color': '#282c3a', 'border-color': '#3e4458', 'color': '#9ba3b8',
      'shape': 'round-rectangle', 'font-size': '9px', 'height': 24,
      'padding': '6px',
    },
  });

  // Task node (card-like, multi-line)
  styles.push({
    selector: 'node[nodeType="_task"]',
    style: {
      'background-color': '#1e2233', 'border-color': '#3e4458', 'color': '#c8cdd8',
      'shape': 'round-rectangle', 'font-size': '11px',
      'height': 68, 'padding': '14px',
      'text-wrap': 'wrap', 'text-max-width': '220px',
      'text-valign': 'center', 'text-halign': 'center',
      'line-height': 1.4,
    },
  });
  styles.push({
    selector: 'node[nodeType="_task"][status="verified"]',
    style: { 'background-color': '#1a2e28', 'border-color': '#3d8b6e', 'border-width': 3, 'color': '#8fd4b8' },
  });
  styles.push({
    selector: 'node[nodeType="_task"][status="rejected"]',
    style: { 'background-color': '#2e1a1a', 'border-color': '#c05050', 'border-width': 3, 'color': '#e8a0a0' },
  });
  styles.push({
    selector: 'node[nodeType="_task"][status="running"]',
    style: { 'background-color': '#2e2818', 'border-color': '#c9962a', 'border-width': 3, 'color': '#e8d5a0' },
  });
  styles.push({
    selector: 'node[nodeType="_task"][status="failed"]',
    style: { 'background-color': '#2e1a1a', 'border-color': '#c05050', 'border-width': 3, 'color': '#e8a0a0' },
  });

  // DEPENDS_ON edges
  styles.push({
    selector: 'edge[edgeType="DEPENDS_ON"]',
    style: { 'line-color': '#4a5a70', 'target-arrow-color': '#4a5a70', 'width': 2, 'line-style': 'solid', 'arrow-scale': 1 },
  });

  // Status-based border styles for resource nodes
  styles.push({
    selector: 'node[status="planned"]',
    style: { 'border-width': 2, 'border-style': 'dashed', 'border-color': '#4a5060' },
  });
  styles.push({
    selector: 'node[status="generating"], node[status="running"]',
    style: {
      'border-width': 3, 'border-style': 'solid', 'border-color': '#c9962a',
      'overlay-color': '#c9962a', 'overlay-opacity': 0.1, 'overlay-padding': 3,
    },
  });
  styles.push({
    selector: 'node[status="done"]',
    style: { 'border-width': 2.5, 'border-style': 'solid', 'border-color': '#3d8b6e' },
  });
  styles.push({
    selector: 'node[status="failed"]',
    style: {
      'border-width': 3, 'border-style': 'solid', 'border-color': '#c05050',
      'overlay-color': '#c05050', 'overlay-opacity': 0.12, 'overlay-padding': 4,
    },
  });
  styles.push({
    selector: 'node[status="skipped"]',
    style: { 'border-width': 2, 'border-style': 'solid', 'border-color': '#4a5060', 'opacity': 0.4 },
  });

  // Operation node status overrides
  styles.push({
    selector: 'node[nodeType="_operation"][status="running"]',
    style: { 'background-color': '#3a2e18', 'border-color': '#c9962a', 'color': '#e8d5a0' },
  });
  styles.push({
    selector: 'node[nodeType="_operation"][status="done"]',
    style: { 'background-color': '#1a3028', 'border-color': '#3d8b6e', 'color': '#8fd4b8' },
  });
  styles.push({
    selector: 'node[nodeType="_operation"][status="failed"]',
    style: { 'background-color': '#3a1a1a', 'border-color': '#c05050', 'color': '#e8a0a0' },
  });

  // Edge status styles
  for (const [status, s] of Object.entries(OP_EDGE_STYLES)) {
    styles.push({
      selector: `edge[status="${status}"]`,
      style: {
        'width': s.width, 'line-color': s.color, 'line-style': s.style,
        'target-arrow-color': s.color,
      },
    });
  }

  // Constraint edges: muted red dashed
  styles.push({
    selector: 'edge[edgeType="CONSTRAINT"]',
    style: {
      'line-color': '#b05050', 'line-style': 'dashed', 'width': 1.5,
      'target-arrow-color': '#b05050', 'target-arrow-shape': 'diamond',
    },
  });

  // Edge labels for done operations (show tool + duration)
  styles.push({
    selector: 'edge[edgeType="OUTPUT"]',
    style: {
      'label': '',  // labels are on the operation node itself
    },
  });

  return styles;
}

// ---- Layout: topological left-to-right ----
// Resources and operations are placed in alternating columns:
//   col 0: input resources (no producer)
//   col 1: operations consuming col-0 resources
//   col 2: output resources of col-1 operations
//   col 3: operations consuming col-2 resources
//   ...
function computeOpGraphPositions(data) {
  const pos = {};
  const resources = data.resources || [];
  const operations = data.operations || [];
  const constraints = data.constraints || [];

  // Build adjacency
  const opProducers = {};  // res_id → op that produces it
  const resConsumers = {}; // res_id → [op]
  for (const op of operations) {
    for (const inp of (op.inputs || [])) {
      if (!resConsumers[inp]) resConsumers[inp] = [];
      resConsumers[inp].push(op);
    }
    for (const out of (op.outputs || [])) {
      opProducers[out] = op;
    }
  }

  // Assign columns via BFS
  const resCol = {};
  const opCol = {};
  const visited = new Set();

  // Seed: resources with no producer → column 0
  const queue = [];
  for (const r of resources) {
    if (!opProducers[r.id]) {
      resCol[r.id] = 0;
      visited.add(r.id);
      queue.push(r.id);
    }
  }

  let maxCol = 0;
  while (queue.length > 0) {
    const resId = queue.shift();
    for (const op of (resConsumers[resId] || [])) {
      const col = (resCol[resId] || 0) + 1;
      opCol[op.id] = Math.max(opCol[op.id] || 0, col);
      maxCol = Math.max(maxCol, col);
      for (const outId of (op.outputs || [])) {
        const outCol = opCol[op.id] + 1;
        if (!resCol[outId] || outCol > resCol[outId]) {
          resCol[outId] = outCol;
          maxCol = Math.max(maxCol, outCol);
        }
        if (!visited.has(outId)) {
          visited.add(outId);
          queue.push(outId);
        }
      }
    }
  }

  // Handle unvisited resources (disconnected)
  for (const r of resources) {
    if (resCol[r.id] === undefined) resCol[r.id] = 0;
  }
  for (const op of operations) {
    if (opCol[op.id] === undefined) opCol[op.id] = 1;
  }

  // Group by column
  const colGroups = {};
  for (const r of resources) {
    const c = resCol[r.id];
    if (!colGroups[c]) colGroups[c] = [];
    colGroups[c].push(r.id);
  }
  for (const op of operations) {
    const c = opCol[op.id];
    if (!colGroups[c]) colGroups[c] = [];
    colGroups[c].push(op.id);
  }

  // Layout constants
  const X_GAP = 200;
  const Y_GAP = 75;
  const Y_START = 60;
  const X_START = 100;

  // Sort columns, center each group vertically
  const cols = Object.keys(colGroups).map(Number).sort((a, b) => a - b);
  const maxGroupSize = Math.max(...cols.map(c => colGroups[c].length));

  for (const c of cols) {
    const group = colGroups[c];
    const totalHeight = (group.length - 1) * Y_GAP;
    const yOffset = Y_START + (maxGroupSize - 1) * Y_GAP / 2 - totalHeight / 2;
    for (let i = 0; i < group.length; i++) {
      pos[group[i]] = {
        x: X_START + c * X_GAP,
        y: yOffset + i * Y_GAP,
      };
    }
  }

  // Constraints: place to the right of their related operation, offset up
  let constraintIdx = 0;
  for (const c of constraints) {
    const relOps = c.related_ops || [];
    if (relOps.length > 0 && pos[relOps[0]]) {
      const ref = pos[relOps[0]];
      // Place to the upper-right to avoid overlapping the column
      pos[c.id] = { x: ref.x + X_GAP * 0.55, y: ref.y - Y_GAP * 0.8 };
    } else {
      pos[c.id] = { x: X_START + (maxCol + 1) * X_GAP, y: Y_START + constraintIdx * Y_GAP };
    }
    constraintIdx++;
  }

  // Post-process: detect and fix remaining overlaps
  const allPosIds = Object.keys(pos);
  for (let i = 0; i < allPosIds.length; i++) {
    for (let j = i + 1; j < allPosIds.length; j++) {
      const a = pos[allPosIds[i]], b = pos[allPosIds[j]];
      if (Math.abs(a.x - b.x) < 60 && Math.abs(a.y - b.y) < 50) {
        // Nudge the second node down
        b.y = a.y + Y_GAP;
      }
    }
  }

  return pos;
}

// ---- Error highlight mode ----
function toggleOpErrorHighlight(cy, enabled) {
  if (!cy) return;
  cy.batch(() => {
    if (enabled) {
      // Dim everything first
      cy.nodes().addClass('error-dimmed');
      cy.edges().addClass('error-dimmed');
      // Un-dim failed nodes and their neighbors
      const failedNodes = cy.nodes('[status="failed"]');
      failedNodes.removeClass('error-dimmed');
      failedNodes.connectedEdges().removeClass('error-dimmed');
      failedNodes.neighborhood().nodes().removeClass('error-dimmed');
      // Also un-dim constraint nodes connected to failed ops
      cy.nodes('[nodeType="constraint"]').forEach(n => {
        const connected = n.connectedEdges().connectedNodes();
        if (connected.some(c => c.data('status') === 'failed')) {
          n.removeClass('error-dimmed');
          n.connectedEdges().removeClass('error-dimmed');
        }
      });
    } else {
      cy.nodes().removeClass('error-dimmed');
      cy.edges().removeClass('error-dimmed');
    }
  });
}

// ---- Failure pattern analysis ----
function analyzeFailurePatterns(data) {
  const patterns = {};
  for (const op of (data.operations || [])) {
    if (op.status !== 'failed') continue;
    for (const attempt of (op.attempts || [])) {
      if (attempt.status !== 'failed') continue;
      const errorType = attempt.error_type || attempt.error || 'unknown';
      const key = `${op.tool}::${errorType}`;
      if (!patterns[key]) {
        patterns[key] = {
          error_type: errorType,
          tool: op.tool,
          ops: [],
          total_attempts: 0,
          agents: new Set(),
        };
      }
      patterns[key].ops.push(op.id);
      patterns[key].total_attempts++;
      if (op.agent) patterns[key].agents.add(op.agent);
    }
  }

  return Object.values(patterns).map(p => ({
    error_type: p.error_type,
    tool: p.tool,
    op_count: [...new Set(p.ops)].length,
    total_attempts: p.total_attempts,
    agents: [...p.agents],
    op_ids: [...new Set(p.ops)],
  })).sort((a, b) => b.total_attempts - a.total_attempts);
}

// ---- Build detail panel HTML for operation graph nodes ----
function buildOpDetailHtml(nodeData) {
  const raw = nodeData.raw || {};
  const type = nodeData.nodeType;
  const status = nodeData.status || 'planned';

  let html = `<div class="sg-detail-section">
    <span class="sg-detail-badge op-type-${type}">${type}</span>
    <span class="sg-detail-badge op-status-${status}">${status}</span>
    <span style="font-size:11px;color:var(--text-dim);font-family:var(--font-mono)">${nodeData.id}</span>
  </div>`;

  if (type === '_task') {
    html += buildTaskDetail(raw);
  } else if (type === '_operation') {
    html += buildOperationDetail(raw);
  } else if (type === 'constraint') {
    html += buildConstraintDetail(raw);
  } else {
    html += buildResourceDetail(raw);
  }

  return html;
}

function buildTaskDetail(task) {
  let html = '';

  // Purpose
  if (task.purpose) {
    html += `<div class="sg-detail-section">
      <div class="sg-detail-section-title">Purpose</div>
      <div class="sg-detail-field-value">${escHtml(task.purpose)}</div>
    </div>`;
  }

  // Check criteria
  if (task.check_criteria && task.check_criteria.length) {
    html += `<div class="sg-detail-section">
      <div class="sg-detail-section-title">Check Criteria</div>
      <div class="sg-detail-field-value">
        ${task.check_criteria.map((c, i) => `<div style="margin-bottom:4px;">${i + 1}. ${escHtml(c)}</div>`).join('')}
      </div>
    </div>`;
  }

  // Verification
  if (task.verification) {
    const v = task.verification;
    const vColor = v.status === 'passed' ? '#8fd4b8' : v.status === 'failed' ? '#e8a0a0' : '#9ba3b8';
    html += `<div class="sg-detail-section">
      <div class="sg-detail-section-title">Verification</div>
      <div class="sg-detail-field">
        <div class="sg-detail-field-label">status</div>
        <div class="sg-detail-field-value" style="color:${vColor};font-weight:600">${escHtml(v.status || 'pending')}</div>
      </div>`;
    if (v.method) {
      html += `<div class="sg-detail-field">
        <div class="sg-detail-field-label">method</div>
        <div class="sg-detail-field-value">${escHtml(v.method)}</div>
      </div>`;
    }
    if (v.summary) {
      html += `<div class="sg-detail-field">
        <div class="sg-detail-field-label">summary</div>
        <div class="sg-detail-field-value">${escHtml(v.summary)}</div>
      </div>`;
    }
    if (v.issues && v.issues.length) {
      html += `<div class="sg-detail-field">
        <div class="sg-detail-field-label">issues</div>
        <div class="sg-detail-field-value">
          ${v.issues.map(iss => `<div style="margin-bottom:6px;padding:4px 6px;border-left:3px solid ${iss.severity === 'critical' ? '#c05050' : '#c9962a'};background:rgba(0,0,0,0.2);border-radius:2px;">
            <div style="font-size:10px;color:var(--text-dim)">${escHtml(iss.resource || '')}</div>
            <div>${escHtml(iss.issue)}</div>
          </div>`).join('')}
        </div>
      </div>`;
    }
    html += `</div>`;
  }

  // Operations list
  if (task.operations && task.operations.length) {
    html += `<div class="sg-detail-section">
      <div class="sg-detail-section-title">Operations (${task.operations.length})</div>
      <div class="sg-detail-field-value">${task.operations.map(o => `<div>• ${escHtml(o)}</div>`).join('')}</div>
    </div>`;
  }

  // Dependencies
  if (task.depends_on && task.depends_on.length) {
    html += `<div class="sg-detail-section">
      <div class="sg-detail-section-title">Depends On</div>
      <div class="sg-detail-field-value">${task.depends_on.map(d => `<div>• ${escHtml(d)}</div>`).join('')}</div>
    </div>`;
  }

  return html;
}

function buildOperationDetail(op) {
  let html = '';

  // Plan section
  if (op.plan) {
    html += `<div class="sg-detail-section">
      <div class="sg-detail-section-title">Plan</div>`;
    if (op.plan.description) {
      html += `<div class="sg-detail-field">
        <div class="sg-detail-field-label">description</div>
        <div class="sg-detail-field-value">${escHtml(op.plan.description)}</div>
      </div>`;
    }
    if (op.plan.params) {
      html += `<div class="sg-detail-field">
        <div class="sg-detail-field-label">planned params</div>
        <div class="sg-detail-field-value" style="font-size:11px;font-family:var(--font-mono);white-space:pre-wrap">${escHtml(JSON.stringify(op.plan.params, null, 2))}</div>
      </div>`;
    }
    html += `</div>`;
  }

  // Actual section
  if (op.actual) {
    html += `<div class="sg-detail-section">
      <div class="sg-detail-section-title">Actual</div>`;
    if (op.actual.duration_s !== undefined) {
      html += `<div class="sg-detail-field">
        <div class="sg-detail-field-label">duration</div>
        <div class="sg-detail-field-value">${op.actual.duration_s}s</div>
      </div>`;
    }
    if (op.actual.error) {
      html += `<div class="sg-detail-field">
        <div class="sg-detail-field-label">error</div>
        <div class="sg-detail-field-value" style="color:#fca5a5">${escHtml(op.actual.error)}</div>
      </div>`;
    }
    if (op.actual.params) {
      html += `<div class="sg-detail-field">
        <div class="sg-detail-field-label">actual params</div>
        <div class="sg-detail-field-value" style="font-size:11px;font-family:var(--font-mono);white-space:pre-wrap">${escHtml(JSON.stringify(op.actual.params, null, 2))}</div>
      </div>`;
    }
    html += `</div>`;
  }

  // Attempts section
  if (op.attempts && op.attempts.length > 0) {
    html += `<div class="sg-detail-section">
      <div class="sg-detail-section-title">Attempts (${op.attempts.length})</div>`;
    for (const att of op.attempts) {
      const icon = att.status === 'done' ? '✓' : '✗';
      const cls = att.status === 'done' ? 'op-attempt-ok' : 'op-attempt-fail';
      html += `<div class="op-attempt ${cls}">
        <div class="op-attempt-header">
          <span>${icon} #${att.attempt || '?'}</span>
          <span>${att.duration_s ? att.duration_s + 's' : ''}</span>
          <span class="op-attempt-error-type">${escHtml(att.error_type || att.error || att.status || '')}</span>
        </div>`;
      if (att.params?.prompt) {
        html += `<div class="op-attempt-detail">prompt: ${escHtml(att.params.prompt.slice(0, 150))}${att.params.prompt.length > 150 ? '...' : ''}</div>`;
      }
      if (att.error && att.status === 'failed') {
        html += `<div class="op-attempt-detail" style="color:#fca5a5">${escHtml(att.error)}</div>`;
      }
      html += `</div>`;
    }
    html += `</div>`;
  }

  // Inputs / Outputs
  if (op.inputs?.length) {
    html += `<div class="sg-detail-section">
      <div class="sg-detail-section-title">Inputs</div>
      <div class="sg-detail-field-value">${op.inputs.map(i => `<div>• ${escHtml(i)}</div>`).join('')}</div>
    </div>`;
  }
  if (op.outputs?.length) {
    html += `<div class="sg-detail-section">
      <div class="sg-detail-section-title">Outputs</div>
      <div class="sg-detail-field-value">${op.outputs.map(o => `<div>• ${escHtml(o)}</div>`).join('')}</div>
    </div>`;
  }

  return html;
}

function buildResourceDetail(res) {
  let html = '';

  if (res.path) {
    html += `<div class="sg-detail-field">
      <div class="sg-detail-field-label">path</div>
      <div class="sg-detail-field-value" style="font-family:var(--font-mono);font-size:11px">${escHtml(res.path)}</div>
    </div>`;
  }

  if (res.plan) {
    html += `<div class="sg-detail-section">
      <div class="sg-detail-section-title">Plan</div>`;
    if (res.plan.description) {
      html += `<div class="sg-detail-field">
        <div class="sg-detail-field-label">description</div>
        <div class="sg-detail-field-value">${escHtml(res.plan.description)}</div>
      </div>`;
    }
    if (res.plan.expected) {
      html += `<div class="sg-detail-field">
        <div class="sg-detail-field-label">expected</div>
        <div class="sg-detail-field-value" style="font-size:11px;font-family:var(--font-mono);white-space:pre-wrap">${escHtml(JSON.stringify(res.plan.expected, null, 2))}</div>
      </div>`;
    }
    html += `</div>`;
  }

  if (res.actual) {
    html += `<div class="sg-detail-section">
      <div class="sg-detail-section-title">Actual</div>
      <div class="sg-detail-field-value" style="font-size:11px;font-family:var(--font-mono);white-space:pre-wrap">${escHtml(JSON.stringify(res.actual, null, 2))}</div>
    </div>`;
  }

  // Show image preview if it's an image resource with a path
  if (res.type === 'image' && res.path && res.status === 'done') {
    const imgUrl = resolveRefImageUrl(res.path);
    if (imgUrl) {
      html += `<div class="sg-detail-field">
        <div class="sg-detail-field-label">preview</div>
        <div class="sg-detail-field-value sg-ref-img-container">
          <img src="${escHtml(imgUrl)}" class="sg-ref-img" alt="resource preview"
               onclick="openImageLightbox('${escHtml(imgUrl)}')"
               onerror="this.style.display='none'"
          />
        </div>
      </div>`;
    }
  }

  return html;
}

function buildConstraintDetail(c) {
  let html = '';
  if (c.rule) {
    html += `<div class="sg-detail-field">
      <div class="sg-detail-field-label">rule</div>
      <div class="sg-detail-field-value">${escHtml(c.rule)}</div>
    </div>`;
  }
  if (c.source) {
    html += `<div class="sg-detail-field">
      <div class="sg-detail-field-label">source</div>
      <div class="sg-detail-field-value">${escHtml(c.source)}</div>
    </div>`;
  }
  if (c.scope) {
    html += `<div class="sg-detail-field">
      <div class="sg-detail-field-label">scope</div>
      <div class="sg-detail-field-value">${escHtml(c.scope)}</div>
    </div>`;
  }
  if (c.related_ops?.length) {
    html += `<div class="sg-detail-field">
      <div class="sg-detail-field-label">related operations</div>
      <div class="sg-detail-field-value">${c.related_ops.map(o => `<div>• ${escHtml(o)}</div>`).join('')}</div>
    </div>`;
  }
  return html;
}

// ---- Build failure patterns panel HTML ----
function buildFailurePatternsHtml(data) {
  const patterns = analyzeFailurePatterns(data);
  if (patterns.length === 0) {
    return '<div style="padding:12px;color:var(--text-dim);font-size:12px;">No failures detected.</div>';
  }

  let html = '<div class="op-failure-patterns">';
  for (const p of patterns) {
    html += `<div class="op-failure-item" data-op-ids='${JSON.stringify(p.op_ids)}'>
      <div class="op-failure-header">
        <span class="op-failure-icon">◆</span>
        <span class="op-failure-type">${escHtml(p.error_type)}</span>
        <span class="op-failure-count">${p.op_count} ops, ${p.total_attempts} attempts</span>
      </div>
      <div class="op-failure-details">
        <div>tool: ${escHtml(p.tool)}</div>
        ${p.agents.length ? '<div>agents: ' + p.agents.map(escHtml).join(', ') + '</div>' : ''}
      </div>
    </div>`;
  }
  html += '</div>';
  return html;
}

// ---- Summary stats ----
function computeOpGraphSummary(data) {
  const ops = data.operations || [];
  const total = ops.length;
  const done = ops.filter(o => o.status === 'done').length;
  const failed = ops.filter(o => o.status === 'failed').length;
  const running = ops.filter(o => o.status === 'running').length;
  const planned = ops.filter(o => o.status === 'planned').length;
  const skipped = ops.filter(o => o.status === 'skipped').length;
  const totalDuration = ops.reduce((sum, o) => sum + (o.actual?.duration_s || 0), 0);

  return { total, done, failed, running, planned, skipped, totalDuration };
}

// ---- Utility: escape HTML ----
if (typeof escHtml === 'undefined') {
  function escHtml(s) {
    if (typeof s !== 'string') s = String(s ?? '');
    return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
  }
}
