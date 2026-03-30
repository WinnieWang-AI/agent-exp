/**
 * Session-based Agent Operation Graph — Right sidebar panel
 *
 * Views:
 *   overview — vertical step chain with inputs/outputs in labels
 *   grouped  — steps expanded showing inner tool calls (dagre)
 *   full     — all nodes flat (dagre)
 */

// ---- Palette ----
const SOG_STYLES = {
  // Cool tones for flow, warm tones for resources — no overlap
  node: {
    goal:       { bg: '#2a1f4e', border: '#7c3aed', text: '#c4b5fd' },  // purple
    delegation: { bg: '#1e2a4a', border: '#3b82f6', text: '#93c5fd' },  // blue
    tool_call:  { bg: '#1a2e28', border: '#10b981', text: '#6ee7b7' },  // green
    resource:   { bg: '#332820', border: '#b45309', text: '#fbbf24' },  // amber (default)
    fork:       { bg: '#374151', border: '#6b7280', text: 'transparent' },  // gray
    join:       { bg: '#374151', border: '#6b7280', text: 'transparent' },  // gray
  },
  resType: {
    json:  { bg: '#332820', border: '#b45309', text: '#fbbf24' },  // amber — data files
    image: { bg: '#3b1c2e', border: '#be185d', text: '#f9a8d4' },  // pink — images
    video: { bg: '#3b2014', border: '#c2410c', text: '#fdba74' },  // orange — video
    audio: { bg: '#3d3220', border: '#a16207', text: '#fde68a' },  // gold — audio
  },
  edge: {
    requires:    { color: '#7c3aed', style: 'solid',  width: 2 },
    followed_by: { color: '#6b7280', style: 'solid',  width: 2 },
    executes:    { color: '#3b82f6', style: 'solid',  width: 1.5 },
    produces:    { color: '#b45309', style: 'dashed', width: 1.5 },  // amber, matches resource
    consumed_by: { color: '#b45309', style: 'dashed', width: 1.5 },  // amber
    parallel:    { color: '#6b7280', style: 'dashed', width: 2 },    // gray, matches fork/join
  },
  agent: { screenwriter: '#a78bfa', 'video-creator': '#60a5fa', 'video-evaluator': '#ef4444' },
};

// ---- State ----
let sogCy = null, sogData = null, sogViewMode = 'overview';
let sogLiveTimer = null, sogLiveSessionId = null, sogLastHash = '';

// ---- Helpers ----
function _sogEsc(s) {
  if (typeof s !== 'string') s = String(s ?? '');
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}
function _sogField(label, value) {
  return `<div class="sg-detail-field"><div class="sg-detail-field-label">${label}</div><div class="sg-detail-field-value">${value}</div></div>`;
}
function _sogShortName(path) { return (path || '').split('/').pop(); }
function _sogFmtResources(resMap, max) {
  if (!resMap || resMap.size === 0) return '';
  const names = [...resMap.values()].map(r => _sogShortName(r.path || r.label));
  return names.length <= max ? names.join(', ') : names.slice(0, max).join(', ') + ` +${names.length - max}`;
}

// ---- Pre-compute resource maps ----
function _sogBuildResourceMaps(dataNodes, dataEdges) {
  const nodeMap = {};
  for (const n of dataNodes) nodeMap[n.id] = n;

  const produces = {};  // delegation_id -> Map(resId, resNode)
  const consumes = {};  // delegation_id -> Map(resId, resNode)
  const toolProduces = {}; // tool_call_id -> [resId]

  for (const n of dataNodes) {
    if (n.type !== 'tool_call' || !n.parent_delegation) continue;
    for (const e of dataEdges) {
      if (e.type === 'produces' && e.source === n.id) {
        const res = nodeMap[e.target]; if (!res) continue;
        if (!produces[n.parent_delegation]) produces[n.parent_delegation] = new Map();
        produces[n.parent_delegation].set(res.id, res);
        if (!toolProduces[n.id]) toolProduces[n.id] = [];
        toolProduces[n.id].push(res.id);
      }
      if (e.type === 'consumed_by' && e.target === n.id) {
        const res = nodeMap[e.source]; if (!res) continue;
        if (!consumes[n.parent_delegation]) consumes[n.parent_delegation] = new Map();
        consumes[n.parent_delegation].set(res.id, res);
      }
    }
  }
  return { nodeMap, produces, consumes, toolProduces };
}

// ==== Element Conversion ====
function sogConvertToElements(data, mode) {
  const nodes = [], edges = [];
  const dataNodes = data.nodes || [], dataEdges = data.edges || [];
  const { nodeMap, produces, consumes, toolProduces } = _sogBuildResourceMaps(dataNodes, dataEdges);

  function eid() { return `sog_e_${edges.length}`; }

  if (mode === 'overview') {
    _sogOverview(data, nodes, edges, dataNodes, nodeMap, produces, consumes, eid);
  } else {
    _sogGrouped(data, nodes, edges, dataNodes, dataEdges, nodeMap, toolProduces, eid);
  }
  return { nodes, edges };
}

// ---- Overview: vertical step chain, inputs/outputs in label ----
function _sogOverview(data, nodes, edges, dataNodes, nodeMap, produces, consumes, eid) {
  const steps = data.steps || [];
  const BASE_GAP = 60;       // minimum gap between nodes
  const LINE_H = 16;         // approx height per line of text
  const PAR_SPREAD = 300;
  const positions = {};
  let curY = 0;

  // Goals
  const goalNodes = dataNodes.filter(n => n.type === 'goal');
  for (const n of goalNodes) {
    nodes.push({ data: { id: n.id, label: n.label, fullLabel: n.label, nodeType: 'goal', raw: n } });
    positions[n.id] = { x: 0, y: curY };
    curY += BASE_GAP + LINE_H * 2;
  }

  let prev = goalNodes[0]?.id || null;

  // Build label and estimate line count for dynamic spacing
  function mkLabel(stepIdx, n) {
    const tools = dataNodes.filter(c => c.type === 'tool_call' && c.parent_delegation === n.id).length;
    const agent = n.agent ? `[${n.agent}]` : '';
    const lines = [];
    lines.push(`Step ${stepIdx} ${agent}  \u00b7 ${tools} tools`);
    if (n.goal) {
      lines.push(`\ud83c\udfaf ${n.goal}`);
    } else {
      lines.push(n.label);
    }
    const inp = _sogFmtResources(consumes[n.id], 3);
    const out = _sogFmtResources(produces[n.id], 3);
    if (inp) lines.push(`\u2190 ${inp}`);
    if (out) lines.push(`\u2192 ${out}`);
    // If no file outputs, show a short result summary from the last tool call
    if (!out) {
      const kids = dataNodes.filter(c => c.type === 'tool_call' && c.parent_delegation === n.id);
      const last = kids[kids.length - 1];
      if (last && last.result) {
        const short = last.result.length > 60 ? last.result.slice(0, 58) + '..' : last.result;
        lines.push(`\u2192 ${short}`);
      }
    }
    return { text: lines.join('\n'), lineCount: lines.length };
  }

  let stepIdx = 0;
  for (const step of steps) {
    stepIdx++;

    // Handle tool_call_ids steps (no delegation, flat tool calls)
    const tcIds = step.tool_call_ids || [];
    if (tcIds.length) {
      for (const tcId of tcIds) {
        const tc = nodeMap[tcId]; if (!tc) continue;
        const icon = tc.is_error ? '\u274c' : '\u2705';
        let lbl = `Step ${stepIdx}  ${icon} ${tc.tool || tc.label}`;
        if (tc.result) {
          const short = tc.result.length > 60 ? tc.result.slice(0, 58) + '..' : tc.result;
          lbl += `\n\u2192 ${short}`;
        }
        const lineCount = lbl.split('\n').length;
        nodes.push({ data: { id: tc.id, label: lbl, fullLabel: tc.label, nodeType: 'tool_call', raw: tc } });
        positions[tc.id] = { x: 0, y: curY };
        if (prev) edges.push({ data: { id: eid(), source: prev, target: tc.id, edgeType: 'followed_by' } });
        prev = tc.id;
        curY += BASE_GAP + lineCount * LINE_H + 30;
      }
      continue;
    }

    const dIds = step.delegation_ids || [];
    if (!dIds.length) continue;

    if (dIds.length === 1) {
      const n = nodeMap[dIds[0]]; if (!n) continue;
      const { text, lineCount } = mkLabel(stepIdx, n);
      nodes.push({ data: { id: n.id, label: text, fullLabel: n.label, nodeType: 'delegation', agent: n.agent || '', raw: n } });
      positions[n.id] = { x: 0, y: curY };
      if (prev) edges.push({ data: { id: eid(), source: prev, target: n.id, edgeType: 'followed_by' } });
      prev = n.id;
      curY += BASE_GAP + lineCount * LINE_H + 30;
    } else {
      // Parallel
      const forkId = `fork_${stepIdx}`, joinId = `join_${stepIdx}`;
      nodes.push({ data: { id: forkId, label: '', nodeType: 'fork', raw: {} } });
      positions[forkId] = { x: 0, y: curY };
      if (prev) edges.push({ data: { id: eid(), source: prev, target: forkId, edgeType: 'followed_by' } });
      curY += BASE_GAP * 0.6;

      const startX = -(dIds.length - 1) * PAR_SPREAD / 2;
      let maxLineCount = 0;
      dIds.forEach((did, bi) => {
        const n = nodeMap[did]; if (!n) return;
        const { text, lineCount } = mkLabel(stepIdx, n);
        if (lineCount > maxLineCount) maxLineCount = lineCount;
        nodes.push({ data: { id: n.id, label: text, fullLabel: n.label, nodeType: 'delegation', agent: n.agent || '', isParallel: true, raw: n } });
        positions[n.id] = { x: startX + bi * PAR_SPREAD, y: curY };
        edges.push({ data: { id: eid(), source: forkId, target: n.id, edgeType: 'parallel' } });
        edges.push({ data: { id: eid(), source: n.id, target: joinId, edgeType: 'parallel' } });
      });
      curY += BASE_GAP + maxLineCount * LINE_H + 30;

      nodes.push({ data: { id: joinId, label: '', nodeType: 'join', raw: {} } });
      positions[joinId] = { x: 0, y: curY };
      prev = joinId;
      curY += BASE_GAP * 0.5;
    }
  }
  nodes.forEach(n => { n.position = positions[n.data.id] || { x: 0, y: 0 }; });
}

// ---- Grouped: delegations LR, tool_calls TB inside each compound (preset layout) ----
function _sogGrouped(data, nodes, edges, dataNodes, dataEdges, nodeMap, toolProduces, eid) {
  const steps = data.steps || [];
  const COL_GAP = 580;    // horizontal gap between delegations (tool 300 + resource ~180 + margins)
  const ROW_H = 50;       // vertical gap between tool_calls inside a delegation
  const RES_OFFSET_X = 280; // resource node offset to the right of its tool_call center
  const positions = {};
  const addedRes = new Set();

  // Goal node at the left
  const goalNode = dataNodes.find(n => n.type === 'goal');
  let prevDel = null;
  let curX = 0;

  if (goalNode) {
    nodes.push({ data: { id: goalNode.id, label: goalNode.label, fullLabel: goalNode.label, nodeType: 'goal', raw: goalNode } });
    positions[goalNode.id] = { x: curX, y: 0 };
    prevDel = goalNode.id;
    curX += COL_GAP;
  }

  let stepIdx = 0;
  for (const step of steps) {
    stepIdx++;

    // Handle tool_call_ids steps (no delegation, flat tool calls)
    const tcIds = step.tool_call_ids || [];
    if (tcIds.length) {
      tcIds.forEach((tcId, i) => {
        const tc = nodeMap[tcId]; if (!tc) return;
        const icon = tc.is_error ? '\u274c' : '\u2705';
        let lbl = `${icon} ${tc.tool || tc.label}`;
        if (tc.result) {
          const short = tc.result.length > 60 ? tc.result.slice(0, 58) + '..' : tc.result;
          lbl += `\n\u2192 ${short}`;
        }
        nodes.push({ data: { id: tc.id, label: lbl, fullLabel: tc.label, nodeType: 'tool_call', isError: !!tc.is_error, raw: tc } });
        positions[tc.id] = { x: curX, y: 0 };
        if (prevDel) edges.push({ data: { id: eid(), source: prevDel, target: tc.id, edgeType: 'followed_by' } });
        prevDel = tc.id;
        curX += COL_GAP * 0.6;
      });
      continue;
    }

    for (const did of (step.delegation_ids || [])) {
      const dn = nodeMap[did]; if (!dn) continue;
      const agentTag = dn.agent ? ` [${dn.agent}]` : '';
      const stepLabel = `Step ${stepIdx}${agentTag}\n${dn.label}`;
      nodes.push({ data: { id: did, label: stepLabel, fullLabel: dn.label, nodeType: 'delegation', agent: dn.agent || '', raw: dn } });
      if (prevDel) edges.push({ data: { id: eid(), source: prevDel, target: did, edgeType: 'followed_by' } });

      // Inner tool calls: top to bottom within this column
      const children = dataNodes.filter(c => c.type === 'tool_call' && c.parent_delegation === did);
      let prevTool = null;
      children.forEach((tc, i) => {
        const icon = tc.is_error ? '\u274c' : '\u2705';
        let lbl = `${i + 1}. ${icon} ${tc.tool || tc.label}`;
        if (tc.result) {
          const short = tc.result.length > 60 ? tc.result.slice(0, 58) + '..' : tc.result;
          lbl += `\n\u2192 ${short}`;
        }
        nodes.push({ data: { id: tc.id, label: lbl, fullLabel: tc.label, nodeType: 'tool_call', isError: !!tc.is_error, parent: did, raw: tc } });
        positions[tc.id] = { x: curX, y: i * ROW_H };

        if (prevTool) edges.push({ data: { id: eid(), source: prevTool, target: tc.id, edgeType: 'executes' } });
        prevTool = tc.id;

        // Produced resources: offset to the right
        for (const resId of (toolProduces[tc.id] || [])) {
          const res = nodeMap[resId]; if (!res) continue;
          if (!addedRes.has(resId)) {
            addedRes.add(resId);
            nodes.push({ data: { id: resId, label: _sogShortName(res.path || res.label), fullLabel: res.label, nodeType: 'resource', resourceType: res.resource_type || '', raw: res } });
            positions[resId] = { x: curX + RES_OFFSET_X, y: i * ROW_H };
          }
          edges.push({ data: { id: eid(), source: tc.id, target: resId, edgeType: 'produces' } });
        }
      });

      prevDel = did;
      curX += COL_GAP;
    }
  }

  // Apply positions
  nodes.forEach(n => { n.position = positions[n.data.id] || { x: 0, y: 0 }; });
}


// ==== Stylesheet ====
function sogBuildStylesheet(mode) {
  const s = [
    { selector: 'node', style: {
      'label': 'data(label)', 'text-valign': 'center', 'text-halign': 'center',
      'font-size': 11, 'font-family': '-apple-system, BlinkMacSystemFont, sans-serif',
      'color': '#e1e4ed', 'text-wrap': 'wrap', 'text-max-width': 200,
      'width': 'label', 'height': 'label', 'padding': '10px',
      'border-width': 2, 'shape': 'round-rectangle',
    }},
    { selector: 'edge', style: {
      'width': 1.5, 'line-color': '#4b5563', 'target-arrow-color': '#4b5563',
      'target-arrow-shape': 'triangle', 'arrow-scale': 0.8, 'curve-style': 'bezier', 'opacity': 0.8,
    }},
    { selector: '.sog-dimmed', style: { 'opacity': 0.12 } },
    { selector: '.sog-highlight', style: { 'border-width': 4, 'border-color': '#fff', 'z-index': 999 } },
  ];

  // Node type colors
  for (const [type, c] of Object.entries(SOG_STYLES.node)) {
    s.push({ selector: `node[nodeType="${type}"]`, style: { 'background-color': c.bg, 'border-color': c.border, 'color': c.text } });
  }
  // Resource sub-type colors
  for (const [rt, c] of Object.entries(SOG_STYLES.resType)) {
    s.push({ selector: `node[resourceType="${rt}"]`, style: { 'background-color': c.bg, 'border-color': c.border, 'color': c.text } });
  }
  // Edge type styles
  for (const [type, c] of Object.entries(SOG_STYLES.edge)) {
    s.push({ selector: `edge[edgeType="${type}"]`, style: { 'width': c.width, 'line-color': c.color, 'line-style': c.style, 'target-arrow-color': c.color } });
  }
  // Goal
  s.push({ selector: 'node[nodeType="goal"]', style: { 'font-size': 13, 'font-weight': 600, 'padding': '14px', 'text-max-width': 260 } });
  // Error
  s.push({ selector: 'node[?isError]', style: { 'border-color': '#ef4444', 'border-width': 3, 'color': '#fca5a5' } });
  // Fork/Join
  s.push({ selector: 'node[nodeType="fork"], node[nodeType="join"]', style: { 'shape': 'diamond', 'width': 20, 'height': 20, 'padding': 0, 'label': '', 'font-size': 1 } });

  if (mode === 'overview') {
    s.push({ selector: 'node[nodeType="delegation"]', style: {
      'font-size': 11, 'padding': '14px',
      'width': 340, 'text-max-width': 310,
      'text-halign': 'center', 'text-valign': 'center',
    } });
    s.push({ selector: 'node[nodeType="goal"]', style: { 'width': 340, 'text-max-width': 310 } });
    s.push({ selector: 'node[?isParallel]', style: { 'border-color': '#f59e0b', 'border-width': 3, 'border-style': 'double' } });
  }
  if (mode === 'grouped') {
    // Compound parent (delegation) — box container
    s.push({ selector: '$node > node', style: {
      'text-valign': 'top', 'text-halign': 'center', 'padding': '28px 16px 12px',
      'background-color': '#141828', 'border-color': '#3b82f6', 'border-width': 2, 'border-opacity': 0.7,
      'font-size': 12, 'font-weight': 600, 'color': '#93c5fd', 'text-max-width': 360,
    }});
    // Tool call children — numbered, centered in fixed-width box
    s.push({ selector: 'node[nodeType="tool_call"]', style: {
      'font-size': 10, 'padding': '8px 10px', 'text-max-width': 280,
      'text-halign': 'center', 'text-valign': 'center',
      'width': 300,
    }});
    // Resource nodes
    s.push({ selector: 'node[nodeType="resource"]', style: {
      'font-size': 10, 'padding': '5px 8px', 'opacity': 0.9, 'shape': 'round-rectangle', 'text-max-width': 160,
    }});
  }
  return s;
}

// ==== Layout ====
function sogGetLayout(mode) {
  return { name: 'preset', animate: false, padding: 40 };
}

// ==== Detail Panel ====
function sogShowDetail(nodeData, targetPrefix) {
  const prefix = targetPrefix || 'og';
  const panel = document.getElementById(prefix + '-detail');
  const body = document.getElementById(prefix + '-detail-body');
  const title = document.getElementById(prefix + '-detail-title');
  if (!panel || !body) return;

  const raw = nodeData.raw || {};
  title.textContent = nodeData.fullLabel || nodeData.label;
  const bc = (SOG_STYLES.node[nodeData.nodeType] || {}).border || '#666';
  let h = `<div style="margin-bottom:8px;"><span class="sg-detail-badge" style="background:${bc};color:#fff">${nodeData.nodeType}</span>`;
  if (nodeData.agent) h += ` <span class="sg-detail-badge" style="background:#1e40af;color:#93c5fd">${nodeData.agent}</span>`;
  h += `</div>`;

  if (nodeData.nodeType === 'goal') {
    h += `<div style="font-size:12px;color:var(--text);line-height:1.6;white-space:pre-wrap">${_sogEsc(raw.text || '')}</div>`;
  } else if (nodeData.nodeType === 'delegation') {
    // Step declaration: goal + check_criteria
    if (raw.goal) h += _sogField('\ud83c\udfaf Goal', `<div style="font-size:12px;font-weight:600;color:#c4b5fd;white-space:pre-wrap">${_sogEsc(raw.goal)}</div>`);
    if (raw.check_criteria) h += _sogField('\u2705 Verify', `<div style="font-size:11px;color:#6ee7b7;white-space:pre-wrap">${_sogEsc(raw.check_criteria)}</div>`);
    if (raw.seq) h += _sogField('Sequence', `#${raw.seq}` + (raw.parallel_group ? ' <span style="color:#f59e0b">parallel</span>' : ''));
    if (raw.agent) h += _sogField('Agent', _sogEsc(raw.agent));
    if (raw.session_id) h += _sogField('Session', `<span style="font-family:var(--font-mono);font-size:11px">${_sogEsc(raw.session_id)}</span>`);
    if (sogData) {
      const kids = (sogData.nodes || []).filter(n => n.type === 'tool_call' && n.parent_delegation === raw.id);
      if (kids.length) h += _sogField(`Tools (${kids.length})`, kids.map(c => `<span style="color:#6ee7b7">${_sogEsc(c.tool || c.label)}</span>`).join(', '));
    }
    if (raw.prompt_preview) h += _sogField('Prompt', `<div style="font-size:11px;white-space:pre-wrap;max-height:300px;overflow-y:auto">${_sogEsc(raw.prompt_preview)}</div>`);
    if (raw.subagent_report) h += _sogField('\ud83d\udcdd Subagent Report', `<div style="font-size:11px;white-space:pre-wrap;max-height:300px;overflow-y:auto;color:#93c5fd">${_sogEsc(raw.subagent_report)}</div>`);
    if (raw.maker_summary) h += _sogField('\ud83d\udce3 Maker Summary', `<div style="font-size:11px;white-space:pre-wrap;max-height:300px;overflow-y:auto;color:#fbbf24">${_sogEsc(raw.maker_summary)}</div>`);
  } else if (nodeData.nodeType === 'tool_call') {
    if (raw.goal) h += _sogField('\ud83c\udfaf Goal', `<div style="font-size:12px;font-weight:600;color:#c4b5fd;white-space:pre-wrap">${_sogEsc(raw.goal)}</div>`);
    if (raw.check_criteria) h += _sogField('\u2705 Verify', `<div style="font-size:11px;color:#6ee7b7;white-space:pre-wrap">${_sogEsc(raw.check_criteria)}</div>`);
    h += _sogField('Tool', `<span style="color:#6ee7b7;font-weight:600">${_sogEsc(raw.tool || '')}</span>`);
    if (raw.agent) h += _sogField('Called by', _sogEsc(raw.agent));
    if (raw.args_preview) h += _sogField('Args', `<div style="font-family:var(--font-mono);font-size:10px;white-space:pre-wrap;max-height:200px;overflow-y:auto">${_sogEsc(raw.args_preview)}</div>`);
    if (raw.result != null) {
      const rc = raw.is_error ? '#ef4444' : '#6ee7b7';
      h += _sogField(raw.is_error ? 'Error' : 'Result', `<div style="color:${rc};font-size:11px;white-space:pre-wrap;max-height:200px;overflow-y:auto">${_sogEsc(raw.result || '(empty)')}</div>`);
    }
  } else if (nodeData.nodeType === 'resource') {
    h += _sogField('Type', _sogEsc(raw.resource_type || 'file'));
    if (raw.path) h += _sogField('Path', `<span style="font-family:var(--font-mono);font-size:11px;word-break:break-all">${_sogEsc(raw.path)}</span>`);
    if (raw.resource_type === 'image' && raw.path) h += _sogField('Preview', `<img src="/files/${encodeURIComponent(raw.path)}" style="max-width:100%;max-height:200px;border-radius:4px" onerror="this.style.display='none'" />`);
  }
  body.innerHTML = h;
  panel.style.transform = 'translateX(0)';
}

// ==== Highlight ====
function _sogHighlight(cy, target, mode) {
  cy.elements().removeClass('sog-highlight sog-dimmed');
  let keep;
  if (mode === 'grouped') {
    // In grouped mode: keep the parent compound, all siblings, and direct neighbors visible
    const parent = target.parent();
    const siblings = parent.nonempty() ? parent.children() : cy.collection();
    const hood = target.closedNeighborhood();
    keep = hood.union(parent).union(siblings).union(siblings.connectedEdges());
  } else {
    keep = target.closedNeighborhood();
  }
  cy.elements().not(keep).addClass('sog-dimmed');
  target.addClass('sog-highlight');
}

// ==== Render ====
function sogRender(data, mode) {
  sogData = data;
  sogViewMode = mode || 'overview';
  const container = document.getElementById('og-cy');
  if (sogCy) { sogCy.destroy(); sogCy = null; }
  const { nodes, edges } = sogConvertToElements(data, sogViewMode);

  sogCy = cytoscape({
    container, elements: { nodes, edges },
    style: sogBuildStylesheet(sogViewMode),
    layout: sogGetLayout(sogViewMode),
    minZoom: 0.1, maxZoom: 4, wheelSensitivity: 0.3,
  });
  sogCy.on('tap', 'node', evt => {
    sogShowDetail(evt.target.data());
    _sogHighlight(sogCy, evt.target, sogViewMode);
  });
  sogCy.on('tap', evt => {
    if (evt.target === sogCy) {
      document.getElementById('og-detail').style.transform = 'translateX(100%)';
      sogCy.elements().removeClass('sog-highlight sog-dimmed');
    }
  });
  setTimeout(() => sogCy.fit(undefined, 40), 100);
}

// ==== Summary ====
function sogBuildSummary(data) {
  const st = data.stats || {};
  let h = `<div style="font-size:11px;color:var(--text-mid);line-height:1.8;">`;
  h += `Goals: <strong>${st.goals||0}</strong> &middot; Delegations: <strong>${st.delegations||0}</strong> &middot; Tools: <strong>${st.tool_calls||0}</strong> &middot; Resources: <strong>${st.resources||0}</strong>`;
  h += `</div>`;
  if (data.goal) {
    h += `<div style="margin-top:6px;padding:6px 8px;background:var(--surface2);border-radius:4px;border-left:3px solid #7c3aed;font-size:11px;color:var(--text);">${_sogEsc(data.goal)}</div>`;
  }
  return h;
}

// ==== Sidebar control ====
function sogTogglePanel() {
  const sidebar = document.getElementById('sog-sidebar');
  const handle = document.getElementById('sog-resize-handle');
  const tab = document.getElementById('sog-reopen-tab');
  if (!sidebar) return;
  const isHidden = sidebar.style.display === 'none' || !sidebar.style.display;
  sidebar.style.display = isHidden ? 'flex' : 'none';
  if (handle) handle.style.display = isHidden ? '' : 'none';
  if (tab) tab.style.display = isHidden ? 'none' : 'flex';
  if (isHidden && sogCy) setTimeout(() => sogCy.resize(), 50);
  if (!isHidden) sogStopLive();
}

function sogShowPanel() {
  const sidebar = document.getElementById('sog-sidebar');
  const handle = document.getElementById('sog-resize-handle');
  const tab = document.getElementById('sog-reopen-tab');
  if (sidebar) sidebar.style.display = 'flex';
  if (handle) handle.style.display = '';
  if (tab) tab.style.display = 'none';
}

// ==== Load / Live ====
function sogLoadFromSession(sessionId) {
  if (!sessionId) return;
  sogStopLive();
  sogLiveSessionId = sessionId;
  sogShowPanel();
  document.getElementById('og-empty').style.display = 'none';
  document.getElementById('og-toolbar').style.display = '';
  document.getElementById('og-body').style.display = 'flex';
  document.getElementById('og-summary').innerHTML = '<div style="color:var(--text-dim)">Loading...</div>';
  sogFetchAndRender(sessionId);
}

function sogFetchAndRender(sessionId, live) {
  fetch(`/api/sessions/${encodeURIComponent(sessionId)}/op-graph`)
    .then(r => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json(); })
    .then(data => {
      const hash = `${(data.nodes||[]).length}_${(data.edges||[]).length}`;
      if (live && hash === sogLastHash) return;
      sogLastHash = hash;
      let zoom, pan;
      if (live && sogCy) { zoom = sogCy.zoom(); pan = { ...sogCy.pan() }; }
      sogRender(data, sogViewMode);
      document.getElementById('og-summary').innerHTML = sogBuildSummary(data);
      if (live && zoom !== undefined) { sogCy.zoom(zoom); sogCy.pan(pan); }
    })
    .catch(err => {
      if (!live) document.getElementById('og-summary').innerHTML = `<div style="color:var(--accent-red)">${_sogEsc(err.message)}</div>`;
    });
}

function sogToggleLive() { sogLiveTimer ? sogStopLive() : sogStartLive(); }
function sogStartLive() {
  if (!sogLiveSessionId || sogLiveTimer) return;
  sogLiveTimer = setInterval(() => sogFetchAndRender(sogLiveSessionId, true), 2000);
  const btn = document.getElementById('sog-live-btn');
  if (btn) { btn.classList.add('active'); btn.textContent = '\u25cf Live'; }
}
function sogStopLive() {
  if (sogLiveTimer) { clearInterval(sogLiveTimer); sogLiveTimer = null; }
  sogLastHash = '';
  const btn = document.getElementById('sog-live-btn');
  if (btn) { btn.classList.remove('active'); btn.textContent = '\u25cb Live'; }
}

function sogSwitchView(mode, btn) {
  sogViewMode = mode;
  document.querySelectorAll('.sog-view-btn').forEach(b => b.classList.remove('active'));
  if (btn) btn.classList.add('active');
  else document.getElementById('sog-view-' + mode)?.classList.add('active');
  if (sogData) sogRender(sogData, mode);
}

// ==== Tab panel (standalone, separate from sidebar) ====
let opgraphCy = null, opgraphData = null, opgraphViewMode = 'overview';

function opgraphLoad() {
  const input = document.getElementById('opgraph-session-input');
  const sid = (input?.value || '').trim();
  if (!sid) return;
  document.getElementById('opgraph-empty').style.display = 'none';
  document.getElementById('opgraph-toolbar').style.display = '';
  document.getElementById('opgraph-summary').innerHTML = '<div style="color:var(--text-dim)">Loading...</div>';
  fetch(`/api/sessions/${encodeURIComponent(sid)}/op-graph`)
    .then(r => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json(); })
    .then(data => {
      opgraphData = data;
      opgraphRenderGraph(data, opgraphViewMode);
      document.getElementById('opgraph-summary').innerHTML = sogBuildSummary(data);
    })
    .catch(err => {
      document.getElementById('opgraph-summary').innerHTML = `<div style="color:var(--accent-red)">${_sogEsc(err.message)}</div>`;
    });
}

function opgraphRenderGraph(data, mode) {
  const container = document.getElementById('opgraph-cy');
  if (opgraphCy) { opgraphCy.destroy(); opgraphCy = null; }
  const { nodes, edges } = sogConvertToElements(data, mode);
  opgraphCy = cytoscape({
    container, elements: { nodes, edges },
    style: sogBuildStylesheet(mode),
    layout: sogGetLayout(mode),
    minZoom: 0.1, maxZoom: 4, wheelSensitivity: 0.3,
  });
  opgraphCy.on('tap', 'node', evt => {
    const nd = evt.target.data();
    sogShowDetail(nd, 'opgraph');
    _sogHighlight(opgraphCy, evt.target, opgraphViewMode);
  });
  opgraphCy.on('tap', evt => {
    if (evt.target === opgraphCy) {
      document.getElementById('opgraph-detail').style.transform = 'translateX(100%)';
      opgraphCy.elements().removeClass('sog-highlight sog-dimmed');
    }
  });
  setTimeout(() => opgraphCy.fit(undefined, 40), 100);
}

function opgraphSwitchView(mode, btn) {
  opgraphViewMode = mode;
  document.querySelectorAll('.sog-view-btn-tab').forEach(b => b.classList.remove('active'));
  if (btn) btn.classList.add('active');
  if (opgraphData) opgraphRenderGraph(opgraphData, mode);
}

// ==== Resize drag ====
document.addEventListener('DOMContentLoaded', () => {
  const handle = document.getElementById('sog-resize-handle');
  const sidebar = document.getElementById('sog-sidebar');
  if (!handle || !sidebar) return;
  let dragging = false, startX, startW;
  handle.addEventListener('mousedown', e => {
    e.preventDefault(); dragging = true; startX = e.clientX; startW = sidebar.offsetWidth;
    document.body.style.cursor = 'col-resize'; document.body.style.userSelect = 'none';
  });
  document.addEventListener('mousemove', e => {
    if (!dragging) return;
    sidebar.style.width = Math.max(250, Math.min(startW + startX - e.clientX, window.innerWidth * 0.6)) + 'px';
  });
  document.addEventListener('mouseup', () => {
    if (!dragging) return;
    dragging = false; document.body.style.cursor = ''; document.body.style.userSelect = '';
    if (sogCy) sogCy.resize();
  });
});
