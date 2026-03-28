/**
 * Story Graph visualization using Cytoscape.js
 *
 * Custom layout: events sorted by time on the left, entities grouped on the right.
 */

// ---- Node colors ----
const NODE_STYLES = {
  event:                { bg: '#3b82f6', border: '#1d4ed8', text: '#fff',    shape: 'round-rectangle' },
  character:            { bg: '#10b981', border: '#059669', text: '#fff',    shape: 'ellipse' },
  character_appearance: { bg: '#a7f3d0', border: '#6ee7b7', text: '#064e3b', shape: 'round-rectangle' },
  prop:                 { bg: '#f59e0b', border: '#d97706', text: '#fff',    shape: 'diamond' },
  prop_state:           { bg: '#fde68a', border: '#fcd34d', text: '#78350f', shape: 'round-rectangle' },
  location:             { bg: '#8b5cf6', border: '#7c3aed', text: '#fff',    shape: 'hexagon' },
  location_state:       { bg: '#ddd6fe', border: '#c4b5fd', text: '#4c1d95', shape: 'round-rectangle' },
  timeline:             { bg: '#6b7280', border: '#4b5563', text: '#fff',    shape: 'ellipse' },
  shot:                 { bg: '#f472b6', border: '#ec4899', text: '#fff',    shape: 'round-rectangle' },
  audio_bgm:            { bg: '#eab308', border: '#ca8a04', text: '#422006', shape: 'round-rectangle' },
  audio_dialogue:       { bg: '#8b5cf6', border: '#7c3aed', text: '#fff',    shape: 'round-rectangle' },
  production_style:     { bg: '#e11d48', border: '#be123c', text: '#fff',    shape: 'round-rectangle' },
  production_ratio:     { bg: '#7c3aed', border: '#6d28d9', text: '#fff',    shape: 'round-rectangle' },
  production_duration:  { bg: '#0891b2', border: '#0e7490', text: '#fff',    shape: 'round-rectangle' },
  production_language:  { bg: '#059669', border: '#047857', text: '#fff',    shape: 'round-rectangle' },
  story_detail:        { bg: '#334155', border: '#1e293b', text: '#f1f5f9', shape: 'round-rectangle' },
  asset_ref_image:     { bg: '#6366f1', border: '#4f46e5', text: '#fff',    shape: 'round-rectangle' },
  asset_first_frame:   { bg: '#f97316', border: '#ea580c', text: '#fff',    shape: 'round-rectangle' },
  asset_tail_frame:    { bg: '#14b8a6', border: '#0d9488', text: '#fff',    shape: 'round-rectangle' },
  // asset_shot merged into shot — no longer a separate node type
  asset_output:        { bg: '#22c55e', border: '#15803d', text: '#fff',    shape: 'round-rectangle' },
};

// ---- Edge styles ----
const EDGE_STYLES = {
  THEN:           { color: '#3b82f6', style: 'solid',  width: 2.5, arrow: 'triangle' },
  THEN_CONTINUOUS: { color: '#10b981', style: 'solid',  width: 3.5, arrow: 'triangle' },
  PARALLEL:       { color: '#f59e0b', style: 'dashed', width: 2,   arrow: 'diamond' },
  HAS_STATE:      { color: '#6b7280', style: 'dotted', width: 1.5, arrow: 'none' },
  ACTIVE_DURING:  { color: '#374151', style: 'dotted', width: 1,   arrow: 'triangle' },
  TRANSITIONS_TO: { color: '#ef4444', style: 'solid',  width: 2,   arrow: 'triangle' },
  CAMERA_FOR:     { color: '#ec4899', style: 'dotted', width: 1.5, arrow: 'triangle' },
  FOCUS_ON:       { color: '#f9a8d4', style: 'dotted', width: 1,   arrow: 'triangle' },
  HAPPENS_AT:     { color: '#8b5cf6', style: 'dotted', width: 1,   arrow: 'triangle' },
  HAPPENS_DURING: { color: '#6b7280', style: 'dotted', width: 1,   arrow: 'triangle' },
  BASED_ON:       { color: '#a78bfa', style: 'dashed', width: 1.5, arrow: 'triangle' },
  RELATIONSHIP:   { color: '#f97316', style: 'solid',  width: 2.5, arrow: 'none' },
  USES_REF:       { color: '#6366f1', style: 'dotted', width: 1,   arrow: 'triangle' },
  USES_FRAME:     { color: '#f97316', style: 'solid',  width: 1.5, arrow: 'triangle' },
  PRODUCES:       { color: '#ef4444', style: 'solid',  width: 2,   arrow: 'triangle' },
  EXTRACTS:       { color: '#14b8a6', style: 'dashed', width: 1.5, arrow: 'triangle' },
  SEQUENCE_CONTINUITY: { color: '#14b8a6', style: 'dashed', width: 2, arrow: 'triangle' },
  ASSEMBLES:      { color: '#22c55e', style: 'solid',  width: 2,   arrow: 'triangle' },
  MIXES_INTO:     { color: '#eab308', style: 'solid',  width: 2,   arrow: 'triangle' },
};

// ---- State ----
let cy = null;
let storyData = null;
let storyGraphDir = '';  // directory prefix for resolving relative paths (e.g. "output/session/project/")
let eventOrder = {};  // event_id -> topological index (lower = earlier)
let graphElements = null;  // cached { nodes, edges } for the unified view
const visibleTypes = new Set([
  'story_detail',
  'event', 'character', 'character_appearance',
  'prop', 'prop_state', 'location', 'location_state', 'timeline',
  'shot', 'production_style', 'production_ratio', 'production_duration', 'production_language',
  'asset_first_frame', 'asset_tail_frame', 'asset_output',
  'audio_bgm', 'audio_dialogue',
]);

// ---- Compute event topological order (for numbering) ----
function _computeEventOrder(data) {
  const order = {};
  const eventIds = (data.events || []).map(e => e.id);
  const adj = {};
  const inDeg = {};
  for (const id of eventIds) { adj[id] = []; inDeg[id] = 0; }
  for (const seq of (data.event_sequence || [])) {
    if (seq.type !== 'PARALLEL' && adj[seq.from]) {
      adj[seq.from].push(seq.to);
      inDeg[seq.to] = (inDeg[seq.to] || 0) + 1;
    }
  }
  const queue = eventIds.filter(id => (inDeg[id] || 0) === 0);
  let idx = 0;
  while (queue.length > 0) {
    const node = queue.shift();
    order[node] = idx++;
    for (const next of (adj[node] || [])) {
      inDeg[next]--;
      if (inDeg[next] === 0) queue.push(next);
    }
  }
  for (const id of eventIds) {
    if (order[id] === undefined) order[id] = idx++;
  }
  return order;
}

// ---- Convert StoryGraph JSON to Cytoscape elements ----
function convertToElements(data) {
  const nodes = [];
  const edges = [];
  let edgeId = 0;
  const eid = () => `e${edgeId++}`;

  // Story detail node — title + synopsis
  if (data.synopsis || data.title) {
    const label = data.title || (data.synopsis.length > 30 ? data.synopsis.slice(0, 30) + '…' : data.synopsis);
    nodes.push({
      data: {
        id: '_story_detail', label,
        fullLabel: data.title || '故事详情',
        nodeType: 'story_detail',
        raw: { title: data.title, synopsis: data.synopsis },
      },
    });
  }

  // Events — compute topological order first for numbering
  const evtOrder = _computeEventOrder(data);

  if (data.events) {
    for (const evt of data.events) {
      const idx = evtOrder[evt.id];
      const num = idx !== undefined ? idx + 1 : '?';
      nodes.push({
        data: {
          id: evt.id, label: `#${num} ${evt.name}`,
          fullLabel: `#${num} ${evt.name}`,
          nodeType: 'event', raw: evt,
        },
      });
      if (evt.happens_at) {
        edges.push({ data: { id: eid(), source: evt.id, target: evt.happens_at, edgeType: 'HAPPENS_AT' } });
      }
      if (evt.happens_during) {
        edges.push({ data: { id: eid(), source: evt.id, target: evt.happens_during, edgeType: 'HAPPENS_DURING' } });
      }
    }
  }

  // Event sequence
  if (data.event_sequence) {
    for (const seq of data.event_sequence) {
      let edgeType = seq.type || 'THEN';
      if (edgeType === 'THEN' && seq.continuous) {
        edgeType = 'THEN_CONTINUOUS';
      }
      edges.push({
        data: { id: eid(), source: seq.from, target: seq.to, edgeType },
      });
    }
  }

  // TimeLines
  if (data.timelines) {
    for (const tp of data.timelines) {
      nodes.push({
        data: { id: tp.id, label: tp.label, fullLabel: tp.label, nodeType: 'timeline', raw: tp },
      });
    }
  }

  // Characters
  if (data.characters) {
    for (const ch of data.characters) {
      const nd = {
        data: {
          id: ch.id, label: ch.name, fullLabel: ch.name,
          nodeType: 'character', raw: ch,
        },
      };
      if (ch.reference_image) {
        nd.data.imagePath = ch.reference_image;
      }
      nodes.push(nd);
    }
  }

  // Props
  if (data.props) {
    for (const p of data.props) {
      const nd = {
        data: {
          id: p.id, label: p.name, fullLabel: p.name,
          nodeType: 'prop', raw: p,
        },
      };
      if (p.reference_image) {
        nd.data.imagePath = p.reference_image;
      }
      nodes.push(nd);
    }
  }

  // Locations
  if (data.locations) {
    for (const loc of data.locations) {
      const nd = {
        data: {
          id: loc.id, label: loc.name, fullLabel: loc.name,
          nodeType: 'location', raw: loc,
        },
      };
      if (loc.reference_image) {
        nd.data.imagePath = loc.reference_image;
      }
      nodes.push(nd);
    }
  }

  // Character appearances (visual states)
  if (data.character_appearances) {
    for (const ca of data.character_appearances) {
      const nd = {
        data: {
          id: ca.id, label: ca.phase || ca.id, fullLabel: `${ca.entity}: ${ca.phase}`,
          nodeType: 'character_appearance', raw: ca,
        },
      };
      if (ca.reference_image) {
        nd.data.imagePath = ca.reference_image;
      }
      nodes.push(nd);
      if (ca.entity) {
        edges.push({ data: { id: eid(), source: ca.entity, target: ca.id, edgeType: 'HAS_STATE' } });
      }
    }
  }

  const appearActiveMap = data.appearance_active_during || {};

  // Prop states
  if (data.prop_states) {
    for (const ps of data.prop_states) {
      const nd = {
        data: {
          id: ps.id, label: ps.phase || ps.id, fullLabel: `${ps.entity}: ${ps.phase}`,
          nodeType: 'prop_state', raw: ps,
        },
      };
      if (ps.reference_image) {
        nd.data.imagePath = ps.reference_image;
      }
      nodes.push(nd);
      if (ps.entity) {
        edges.push({ data: { id: eid(), source: ps.entity, target: ps.id, edgeType: 'HAS_STATE' } });
      }
    }
  }

  // Location states
  if (data.location_states) {
    for (const ls of data.location_states) {
      const nd = {
        data: {
          id: ls.id, label: ls.phase || ls.id, fullLabel: `${ls.entity}: ${ls.phase}`,
          nodeType: 'location_state', raw: ls,
        },
      };
      if (ls.reference_image) {
        nd.data.imagePath = ls.reference_image;
      }
      nodes.push(nd);
      if (ls.entity) {
        edges.push({ data: { id: eid(), source: ls.entity, target: ls.id, edgeType: 'HAS_STATE' } });
      }
    }
  }

  // ACTIVE_DURING edges
  const activeMaps = [
    data.appearance_active_during,
    data.state_active_during,
    data.prop_active_during,
    data.location_active_during,
    data.audio_active_during,
  ];
  for (const map of activeMaps) {
    if (!map) continue;
    for (const [stateId, eventIds] of Object.entries(map)) {
      for (const evtId of eventIds) {
        edges.push({ data: { id: eid(), source: stateId, target: evtId, edgeType: 'ACTIVE_DURING' } });
      }
    }
  }

  // Appearance transitions
  if (data.appearance_transitions) {
    for (const tr of data.appearance_transitions) {
      edges.push({
        data: {
          id: eid(), source: tr.from, target: tr.to, edgeType: 'TRANSITIONS_TO',
          trigger: tr.trigger, delta: tr.delta,
        },
      });
    }
  }


  // Legacy: character_transitions (backward compat)
  if (data.character_transitions) {
    for (const tr of data.character_transitions) {
      edges.push({
        data: {
          id: eid(), source: tr.from, target: tr.to, edgeType: 'TRANSITIONS_TO',
          trigger: tr.trigger, delta: tr.delta,
        },
      });
    }
  }

  // Camera directives — each shot becomes its own node
  if (data.camera_directives) {
    for (const cam of data.camera_directives) {
      const camId = cam.id;
      const evts = Array.isArray(cam.for_event) ? cam.for_event : [cam.for_event];
      const shots = cam.shots || [];

      // Create individual shot nodes directly (no camera_directive parent node)
      for (const shot of shots) {
        const order = shot.order || 0;
        const eventId = evts[0] || '';
        // Use event-based ID to match shot-plan format (evt_xxx_shot_N)
        const shotId = eventId ? `${eventId}_shot_${order}` : `${camId}_shot_${order}`;
        const shotType = shot.shot_type || '';
        const intent = shot.content || shot.intent || '';
        // Resolve clipPath: prefer shot-plan output_path, fallback to convention
        let clipPath = '';
        if (window._shotPlanData && window._shotPlanData.shots) {
          const spShot = window._shotPlanData.shots.find(s => s.shot_id === shotId);
          if (spShot && spShot.output_path) clipPath = spShot.output_path;
        }
        if (!clipPath) {
          clipPath = `assets/shots/${shotId}.mp4`;
        }

        nodes.push({
          data: {
            id: shotId,
            label: `S${order} ${(intent || shotType).slice(0, 12)}`,
            fullLabel: `Shot ${order}: ${intent || shotType}`,
            nodeType: 'shot',
            clipPath: clipPath,
            raw: { ...shot, _cam_id: camId, _for_event: evts, _clip_path: clipPath },
          },
        });

        // Edge: shot → event
        for (const evtId of evts) {
          edges.push({ data: { id: eid(), source: shotId, target: evtId, edgeType: 'CAMERA_FOR' } });
        }

        // Edge: shot → focus_on states
        if (shot.focus_on) {
          for (const stateId of shot.focus_on) {
            edges.push({ data: { id: eid(), source: shotId, target: stateId, edgeType: 'FOCUS_ON' } });
          }
        }
      }
    }
  }

  // Video info → ratio, duration, language nodes (from top-level video_info,
  // falling back to production_styles[0] for old-format graphs)
  const vi = data.video_info || {};
  const ps0 = (data.production_styles || [])[0] || {};
  const viRatio = vi.aspect_ratio || ps0.aspect_ratio || '';
  const viDuration = vi.duration || ps0.duration || '';
  const viLanguage = vi.language || ps0.language || '';

  if (viRatio) {
    nodes.push({
      data: {
        id: 'video_info__ratio',
        label: `📐 ${viRatio}`,
        fullLabel: `画面比例: ${viRatio}`,
        nodeType: 'production_ratio',
        raw: { aspect_ratio: viRatio, _display: 'ratio' },
      },
    });
  }
  if (viDuration) {
    nodes.push({
      data: {
        id: 'video_info__duration',
        label: `⏱ ${viDuration}`,
        fullLabel: `视频时长: ${viDuration}`,
        nodeType: 'production_duration',
        raw: { duration: viDuration, _display: 'duration' },
      },
    });
  }
  if (viLanguage) {
    const langNames = { zh: '中文', 'zh-CN': '中文', en: 'English', ja: '日本語', ko: '한국어' };
    const langDisplay = langNames[viLanguage] || viLanguage;
    nodes.push({
      data: {
        id: 'video_info__language',
        label: `🌐 ${langDisplay}`,
        fullLabel: `视频语言: ${langDisplay}`,
        nodeType: 'production_language',
        raw: { language: viLanguage, _display: 'language' },
      },
    });
  }

  // Production styles → visual style nodes only (style_prefix, negative_prefix)
  if (data.production_styles) {
    for (const ps of data.production_styles) {
      const styleLabel = ps.description || ps.style_prefix || ps.id;
      nodes.push({
        data: {
          id: `${ps.id}__style`,
          label: `🎨 ${styleLabel.slice(0, 30)}`,
          fullLabel: `视觉风格: ${styleLabel}`,
          nodeType: 'production_style',
          raw: { id: ps.id, description: ps.description, style_prefix: ps.style_prefix, negative_prefix: ps.negative_prefix, _display: 'style' },
        },
      });
    }
  }

  // style_active_during edges (link style nodes to events)
  if (data.style_active_during) {
    for (const [stateId, eventIds] of Object.entries(data.style_active_during)) {
      for (const evtId of eventIds) {
        edges.push({ data: { id: eid(), source: `${stateId}__style`, target: evtId, edgeType: 'ACTIVE_DURING' } });
      }
    }
  }

  // Audio states
  if (data.audio_states) {
    for (const as of data.audio_states) {
      nodes.push({
        data: {
          id: as.id, label: as.phase || as.id,
          fullLabel: `${as.layer}: ${as.phase}`,
          nodeType: as.layer === 'audio_dialogue' ? 'audio_dialogue' : 'audio_bgm', raw: as,
          audioPath: `assets/audio/${as.id}.mp3`,
        },
      });
    }
  }

  // Audio transitions
  if (data.audio_transitions) {
    for (const tr of data.audio_transitions) {
      edges.push({
        data: {
          id: eid(), source: tr.from, target: tr.to, edgeType: 'TRANSITIONS_TO',
          trigger: tr.trigger, method: tr.method,
        },
      });
    }
  }

  // BASED_ON edges (scan all nodes for based_on field)
  for (const n of nodes) {
    const basedOn = n.data.raw?.based_on;
    if (basedOn) {
      edges.push({ data: { id: eid(), source: n.data.id, target: basedOn, edgeType: 'BASED_ON' } });
    }
  }

  // Filter out edges referencing nonexistent nodes (robustness for incomplete graphs)
  const nodeIds = new Set(nodes.map(n => n.data.id));
  const validEdges = edges.filter(e => nodeIds.has(e.data.source) && nodeIds.has(e.data.target));

  return { nodes, edges: validEdges };
}

// ---- Build Cytoscape stylesheet ----
function buildStylesheet() {
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
        'text-max-width': '100px',
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
        'border-width': 3,
        'border-color': '#fff',
        'overlay-color': '#fff',
        'overlay-opacity': 0.1,
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
        'opacity': 0.6,
      },
    },
    { selector: '.hidden', style: { 'display': 'none' } },
    { selector: '.highlighted', style: { 'opacity': 1 } },
    { selector: '.dimmed', style: { 'opacity': 0.15 } },
  ];

  for (const [type, s] of Object.entries(NODE_STYLES)) {
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

  // Asset generation status — distinguished by border style + badge label:
  // - img-pending: gray dashed border
  // - img-generating: thick orange border + pulsing glow
  // - node[imageUrl]/[clipUrl]: ✓ badge only (no extra border)
  styles.push({
    selector: 'node.img-pending',
    style: {
      'border-width': 2.5,
      'border-style': 'dashed',
      'border-color': '#6b7280',
    },
  });
  styles.push({
    selector: 'node.img-generating',
    style: {
      'border-width': 4,
      'border-style': 'solid',
      'border-color': '#f59e0b',
      'overlay-color': '#f59e0b',
      'overlay-opacity': 0.2,
      'overlay-padding': 5,
    },
  });
  // node[imageUrl]/[clipUrl]: ✓ badge is sufficient, no extra border

  // Execution graph: asset nodes with thumbnail images
  styles.push({
    selector: 'node[nodeType="asset_ref_image"][imageUrl], node[nodeType="asset_first_frame"][imageUrl], node[nodeType="asset_tail_frame"][imageUrl]',
    style: {
      'background-image': 'data(imageUrl)',
      'background-fit': 'cover',
      'background-image-opacity': 0.85,
      'width': 50,
      'height': 50,
      'text-valign': 'bottom',
      'text-margin-y': 4,
      'text-outline-color': '#000',
      'text-outline-width': 1,
      'text-outline-opacity': 0.7,
    },
  });

  for (const [type, s] of Object.entries(EDGE_STYLES)) {
    const edgeStyle = {
      'width': s.width,
      'line-color': s.color,
      'line-style': s.style,
      'target-arrow-color': s.color,
      'target-arrow-shape': s.arrow,
    };
    // RELATIONSHIP edges show labels
    if (type === 'RELATIONSHIP') {
      edgeStyle['label'] = 'data(label)';
      edgeStyle['font-size'] = '10px';
      edgeStyle['font-family'] = '-apple-system, BlinkMacSystemFont, sans-serif';
      edgeStyle['text-background-color'] = '#1a1a2e';
      edgeStyle['text-background-opacity'] = 0.85;
      edgeStyle['text-background-padding'] = '3px';
      edgeStyle['text-border-opacity'] = 0;
      edgeStyle['color'] = '#f97316';
      edgeStyle['text-rotation'] = 'autorotate';
      edgeStyle['opacity'] = 1;
      edgeStyle['z-index'] = 999;
    }
    styles.push({
      selector: `edge[edgeType="${type}"]`,
      style: edgeStyle,
    });
  }

  return styles;
}

// ---- Semantic Layout ----
function computePositions(data) {
  const pos = {}; // id -> { x, y }

  // Layout constants
  const EVENT_X = 400;          // events column X
  const EVENT_Y_START = 60;
  const EVENT_Y_GAP = 100;
  const PARALLEL_X_OFFSET = 180; // offset for parallel events

  const TIMELINE_X = -80;       // timelines far left, away from camera column
  const CAMERA_X = 180;         // camera column, left of events
  const AUDIO_X = 620;          // audio column, right of events

  const ENTITY_X_START = 900;   // entities start X (right side)
  const ENTITY_GROUP_GAP = 280; // gap between entity groups
  const ENTITY_Y_START = 60;
  const ENTITY_Y_GAP = 80;
  const STATE_Y_OFFSET = 50;    // state chain starts below entity
  const STATE_Y_GAP = 60;       // gap between states in chain
  const SHOT_Y_GAP = 50;        // gap between shots within same camera
  const SHOT_MIN_Y_GAP = 50;    // minimum gap between shots of different cameras

  // Step 0: Video info + production style nodes — top row, well above events
  const PRODUCTION_Y = -80;
  // Story detail + video info nodes (ratio, duration, language)
  pos['_story_detail']        = { x: EVENT_X - 400,       y: PRODUCTION_Y };
  pos['video_info__ratio']    = { x: EVENT_X - 200,       y: PRODUCTION_Y };
  pos['video_info__duration'] = { x: EVENT_X,              y: PRODUCTION_Y };
  pos['video_info__language'] = { x: EVENT_X + 200,        y: PRODUCTION_Y };
  // Production style nodes
  if (data.production_styles) {
    for (let i = 0; i < data.production_styles.length; i++) {
      const ps = data.production_styles[i];
      pos[`${ps.id}__style`] = { x: EVENT_X + 400 + i * 300, y: PRODUCTION_Y };
    }
  }

  // Step 1: Topological sort of events using THEN edges
  const eventIds = (data.events || []).map(e => e.id);
  const eventSet = new Set(eventIds);

  // Build adjacency from THEN edges
  const thenAdj = {};   // from -> [to]
  const inDegree = {};
  const parallelPairs = []; // [{a, b}]

  for (const id of eventIds) {
    thenAdj[id] = [];
    inDegree[id] = 0;
  }

  if (data.event_sequence) {
    for (const seq of data.event_sequence) {
      if (seq.type === 'PARALLEL') {
        parallelPairs.push({ a: seq.from, b: seq.to });
      } else {
        // THEN
        if (thenAdj[seq.from]) {
          thenAdj[seq.from].push(seq.to);
          inDegree[seq.to] = (inDegree[seq.to] || 0) + 1;
        }
      }
    }
  }

  // Kahn's algorithm for topological sort with level assignment
  const eventLevel = {};
  const queue = [];
  for (const id of eventIds) {
    if ((inDegree[id] || 0) === 0) {
      queue.push(id);
      eventLevel[id] = 0;
    }
  }

  const topoOrder = [];
  while (queue.length > 0) {
    const node = queue.shift();
    topoOrder.push(node);
    for (const next of (thenAdj[node] || [])) {
      inDegree[next]--;
      eventLevel[next] = Math.max(eventLevel[next] || 0, eventLevel[node] + 1);
      if (inDegree[next] === 0) {
        queue.push(next);
      }
    }
  }

  // Any events not in topo order (disconnected) get appended
  for (const id of eventIds) {
    if (eventLevel[id] === undefined) {
      eventLevel[id] = topoOrder.length;
      topoOrder.push(id);
    }
  }

  // Find parallel events - they should share the same level
  const parallelWith = {}; // id -> partner id
  for (const { a, b } of parallelPairs) {
    parallelWith[a] = b;
    parallelWith[b] = a;
    // Ensure they have the same level (use the max)
    const lvl = Math.max(eventLevel[a] || 0, eventLevel[b] || 0);
    eventLevel[a] = lvl;
    eventLevel[b] = lvl;
  }

  // Group events by level
  const levelEvents = {};
  for (const id of topoOrder) {
    const lvl = eventLevel[id];
    if (!levelEvents[lvl]) levelEvents[lvl] = [];
    if (!levelEvents[lvl].includes(id)) levelEvents[lvl].push(id);
  }

  // Pre-compute shot count per event for dynamic spacing
  const shotCountByEvent = {};
  if (data.camera_directives) {
    for (const cam of data.camera_directives) {
      const evts = Array.isArray(cam.for_event) ? cam.for_event : [cam.for_event];
      const nShots = (cam.shots || []).length;
      for (const eid of evts) {
        shotCountByEvent[eid] = Math.max(shotCountByEvent[eid] || 0, nShots);
      }
    }
  }

  // Assign Y positions per level, X offset for parallel
  const sortedLevels = Object.keys(levelEvents).map(Number).sort((a, b) => a - b);
  let currentY = EVENT_Y_START;

  // Map event -> timeline for grouping
  const eventTimeline = {};
  if (data.events) {
    for (const evt of data.events) {
      if (evt.happens_during) eventTimeline[evt.id] = evt.happens_during;
    }
  }

  // Track timeline Y ranges for positioning
  const timelineYRange = {}; // tp_id -> { min, max }

  for (const lvl of sortedLevels) {
    const evts = levelEvents[lvl];
    if (evts.length === 1) {
      pos[evts[0]] = { x: EVENT_X, y: currentY };
    } else if (evts.length === 2 && parallelWith[evts[0]] === evts[1]) {
      // Parallel pair: side by side
      pos[evts[0]] = { x: EVENT_X - PARALLEL_X_OFFSET / 2, y: currentY };
      pos[evts[1]] = { x: EVENT_X + PARALLEL_X_OFFSET / 2, y: currentY };
    } else {
      // Multiple events at same level, spread them
      for (let i = 0; i < evts.length; i++) {
        pos[evts[i]] = { x: EVENT_X + (i - (evts.length - 1) / 2) * 160, y: currentY };
      }
    }

    // Track timeline ranges
    for (const eid of evts) {
      const tp = eventTimeline[eid];
      if (tp) {
        if (!timelineYRange[tp]) timelineYRange[tp] = { min: currentY, max: currentY };
        timelineYRange[tp].min = Math.min(timelineYRange[tp].min, currentY);
        timelineYRange[tp].max = Math.max(timelineYRange[tp].max, currentY);
      }
    }

    // Dynamic gap: expand based on max shot count at this level
    const maxShots = Math.max(...evts.map(eid => shotCountByEvent[eid] || 0), 0);
    const dynamicGap = Math.max(EVENT_Y_GAP, maxShots * SHOT_Y_GAP + 20);
    currentY += dynamicGap;
  }

  // Step 2: Position timelines on far left, centered on their event range
  if (data.timelines) {
    for (const tp of data.timelines) {
      const range = timelineYRange[tp.id];
      if (range) {
        pos[tp.id] = { x: TIMELINE_X, y: (range.min + range.max) / 2 };
      } else {
        pos[tp.id] = { x: TIMELINE_X, y: EVENT_Y_START };
      }
    }
  }

  // Step 3: Position entities on the right side in groups
  // Build state chains per entity using TRANSITIONS_TO edges
  const entityStates = {}; // entity_id -> { appearances: [], states: [] }
  const stateEntity = {};  // state_id -> entity_id

  // Collect all state-like nodes per entity
  for (const ca of (data.character_appearances || [])) {
    if (!entityStates[ca.entity]) entityStates[ca.entity] = { appearances: [], states: [] };
    entityStates[ca.entity].appearances.push(ca.id);
    stateEntity[ca.id] = ca.entity;
  }
  for (const ps of (data.prop_states || [])) {
    if (!entityStates[ps.entity]) entityStates[ps.entity] = { appearances: [], states: [] };
    entityStates[ps.entity].states.push(ps.id);
    stateEntity[ps.id] = ps.entity;
  }
  for (const ls of (data.location_states || [])) {
    if (!entityStates[ls.entity]) entityStates[ls.entity] = { appearances: [], states: [] };
    entityStates[ls.entity].states.push(ls.id);
    stateEntity[ls.id] = ls.entity;
  }
  // Legacy support
  for (const cs of (data.character_states || [])) {
    if (!entityStates[cs.entity]) entityStates[cs.entity] = { appearances: [], states: [] };
    entityStates[cs.entity].states.push(cs.id);
    stateEntity[cs.id] = cs.entity;
  }

  // Order states by transition chain
  const transitionNext = {};
  const transitionPrev = {};
  const allTransitions = [
    ...(data.appearance_transitions || []),
    ...(data.character_transitions || []),
  ];
  for (const tr of allTransitions) {
    transitionNext[tr.from] = tr.to;
    transitionPrev[tr.to] = tr.from;
  }

  function orderStateChain(stateIds) {
    if (stateIds.length <= 1) return stateIds;
    // Find head (no prev in this set)
    const idSet = new Set(stateIds);
    let head = null;
    for (const id of stateIds) {
      if (!transitionPrev[id] || !idSet.has(transitionPrev[id])) {
        head = id;
        break;
      }
    }
    if (!head) head = stateIds[0];

    const ordered = [head];
    const visited = new Set([head]);
    let current = head;
    while (transitionNext[current] && idSet.has(transitionNext[current]) && !visited.has(transitionNext[current])) {
      current = transitionNext[current];
      ordered.push(current);
      visited.add(current);
    }
    // Add any remaining states not in chain
    for (const id of stateIds) {
      if (!visited.has(id)) ordered.push(id);
    }
    return ordered;
  }

  // Group entities by type
  const entityGroups = [
    { type: 'character', items: data.characters || [] },
    { type: 'prop', items: data.props || [] },
    { type: 'location', items: data.locations || [] },
  ];

  let groupX = ENTITY_X_START;
  for (const group of entityGroups) {
    let entityY = ENTITY_Y_START;
    for (const entity of group.items) {
      // Position entity node
      pos[entity.id] = { x: groupX, y: entityY };

      const es = entityStates[entity.id] || { appearances: [], states: [] };

      // For characters: appearance chain
      if (group.type === 'character') {
        const orderedAppear = orderStateChain(es.appearances);
        let stateY = entityY + STATE_Y_OFFSET;
        for (const appearId of orderedAppear) {
          pos[appearId] = { x: groupX, y: stateY };
          stateY += STATE_Y_GAP;
        }
        entityY = stateY + ENTITY_Y_GAP;
      } else {
        // Props / Locations: single column
        const orderedStates = orderStateChain(es.states);
        let stateY = entityY + STATE_Y_OFFSET;
        for (const stateId of orderedStates) {
          pos[stateId] = { x: groupX, y: stateY };
          stateY += STATE_Y_GAP;
        }
        entityY = stateY + ENTITY_Y_GAP;
      }
    }
    groupX += ENTITY_GROUP_GAP;
  }

  // Step 4: Shot nodes - positioned to the left of their events
  // Collect all shot groups, then resolve Y overlaps between adjacent cameras
  if (data.camera_directives) {
    // First pass: compute ideal Y positions for each camera's shots
    const camGroups = []; // { camId, baseY, shots: [{ shotId, idealY }] }
    for (const cam of data.camera_directives) {
      const evts = Array.isArray(cam.for_event) ? cam.for_event : [cam.for_event];
      const shots = cam.shots || [];

      let avgY = 0;
      let count = 0;
      for (const evtId of evts) {
        if (pos[evtId]) { avgY += pos[evtId].y; count++; }
      }
      const baseY = count > 0 ? avgY / count : EVENT_Y_START;

      if (shots.length === 0) continue;
      const group = { camId: cam.id, baseY, shots: [] };
      const startY = baseY - ((shots.length - 1) * SHOT_Y_GAP) / 2;
      for (let i = 0; i < shots.length; i++) {
        const order = shots[i].order || 0;
        // Match convertToElements: use event-based ID when available
        const eventId = evts[0] || '';
        const shotId = eventId ? `${eventId}_shot_${order}` : `${cam.id}_shot_${order}`;
        group.shots.push({ shotId, idealY: startY + i * SHOT_Y_GAP });
      }
      camGroups.push(group);
    }

    // Sort camera groups by their baseY (event order)
    camGroups.sort((a, b) => a.baseY - b.baseY);

    // Second pass: resolve overlaps — push groups down if they collide with previous
    let prevBottomY = -Infinity;
    for (const group of camGroups) {
      if (group.shots.length === 0) continue;
      const topY = group.shots[0].idealY;
      if (topY < prevBottomY + SHOT_MIN_Y_GAP) {
        // Shift this entire group down
        const shift = (prevBottomY + SHOT_MIN_Y_GAP) - topY;
        for (const s of group.shots) {
          s.idealY += shift;
        }
        group.baseY += shift;
      }
      prevBottomY = group.shots[group.shots.length - 1].idealY;
    }

    // Third pass: assign final positions
    for (const group of camGroups) {
      for (const s of group.shots) {
        pos[s.shotId] = { x: CAMERA_X, y: s.idealY };
      }
    }
  }

  // Step 5: Audio states - positioned to the right of their events
  // Group by layer (bgm, ambience, dialogue) into separate columns, then
  // resolve Y overlaps within each column.
  if (data.audio_states) {
    const audioActive = data.audio_active_during || {};
    const AUDIO_LAYER_GAP = 140; // horizontal gap between layers
    const AUDIO_MIN_Y_GAP = 45;  // minimum vertical gap to avoid overlap
    const layerOrder = ['audio_bgm', 'audio_dialogue'];
    const layerNodes = {}; // layer -> [{id, y}]

    for (const as of data.audio_states) {
      const evts = audioActive[as.id] || [];
      let avgY = 0;
      let count = 0;
      for (const evtId of evts) {
        if (pos[evtId]) { avgY += pos[evtId].y; count++; }
      }
      const y = count > 0 ? avgY / count : EVENT_Y_START;
      const layer = as.layer || 'audio_bgm';
      if (!layerNodes[layer]) layerNodes[layer] = [];
      layerNodes[layer].push({ id: as.id, y });
    }

    let layerIdx = 0;
    for (const layer of layerOrder) {
      const nodes = layerNodes[layer];
      if (!nodes) continue;
      const x = AUDIO_X + layerIdx * AUDIO_LAYER_GAP;
      // Sort by Y and push apart overlapping nodes
      nodes.sort((a, b) => a.y - b.y);
      for (let i = 1; i < nodes.length; i++) {
        if (nodes[i].y - nodes[i - 1].y < AUDIO_MIN_Y_GAP) {
          nodes[i].y = nodes[i - 1].y + AUDIO_MIN_Y_GAP;
        }
      }
      for (const n of nodes) {
        pos[n.id] = { x, y: n.y };
      }
      layerIdx++;
    }
    // Handle any layers not in layerOrder
    for (const [layer, nodes] of Object.entries(layerNodes)) {
      if (layerOrder.includes(layer)) continue;
      const x = AUDIO_X + layerIdx * AUDIO_LAYER_GAP;
      nodes.sort((a, b) => a.y - b.y);
      for (let i = 1; i < nodes.length; i++) {
        if (nodes[i].y - nodes[i - 1].y < AUDIO_MIN_Y_GAP) {
          nodes[i].y = nodes[i - 1].y + AUDIO_MIN_Y_GAP;
        }
      }
      for (const n of nodes) {
        pos[n.id] = { x, y: n.y };
      }
      layerIdx++;
    }
  }

  return pos;
}

function runLayout() {
  if (!cy || !storyData) return;

  const outFiles = window._outputFiles || [];
  const positions = window._shotPlanData
    ? computeAssetsViewPositions(storyData, window._shotPlanData, outFiles)
    : computePositions(storyData);

  cy.batch(() => {
    cy.nodes().forEach(n => {
      const p = positions[n.id()];
      if (p) {
        n.position(p);
      }
    });
  });

  cy.fit(undefined, 50);
}

// ---- Filter visibility ----
function applyFilters() {
  if (!cy) return;
  cy.batch(() => {
    cy.nodes().forEach(n => {
      const t = n.data('nodeType');
      if (visibleTypes.has(t)) {
        n.removeClass('hidden');
      } else {
        n.addClass('hidden');
      }
    });
    cy.edges().forEach(e => {
      if (e.source().hasClass('hidden') || e.target().hasClass('hidden')) {
        e.addClass('hidden');
      } else {
        e.removeClass('hidden');
      }
    });
  });
}

// ---- Detail panel ----
function showDetail(nodeData) {
  const panel = document.getElementById('sg-detail');
  const body = document.getElementById('sg-detail-body');
  const title = document.getElementById('sg-detail-title');
  if (!panel || !body) return;

  const raw = nodeData.raw || {};
  const type = nodeData.nodeType;
  title.textContent = nodeData.fullLabel || nodeData.id;

  let html = `<div class="sg-detail-section">
    <span class="sg-detail-badge sg-type-${type}">${type}</span>
    <span style="font-size:11px;color:var(--text-dim);font-family:var(--font-mono)">${nodeData.id}</span>
  </div>`;

  html += renderRawFields(raw, type, nodeData);
  body.innerHTML = html;
  panel.classList.add('open');
}

function hideDetail() {
  const panel = document.getElementById('sg-detail');
  if (panel) panel.classList.remove('open');
  if (cy) {
    cy.nodes().removeClass('highlighted dimmed');
    cy.edges().removeClass('highlighted dimmed');
  }
}

function renderRawFields(raw, type, nodeData) {
  nodeData = nodeData || {};
  let html = '';
  const skip = new Set(['id', 'type']);

  // Show reference_image at the top if present
  if (raw.reference_image) {
    const imgUrl = resolveRefImageUrl(raw.reference_image);
    const imgUrlBusted = imgUrl + (imgUrl.includes('?') ? '&' : '?') + 't=' + Date.now();
    html += `<div class="sg-detail-field">
      <div class="sg-detail-field-label">reference_image</div>
      <div class="sg-detail-field-value sg-ref-img-container">
        <img src="${escHtml(imgUrlBusted)}" class="sg-ref-img" alt="reference image"
             onclick="openImageLightbox('${escHtml(imgUrlBusted)}')"
             onerror="this.style.display='none';this.nextElementSibling.style.display='block'"
        /><span class="sg-ref-img-fallback" style="display:none;font-size:11px;color:var(--text-dim)">Image not found</span>
      </div>
    </div>`;
    if (raw.generation_prompt) {
      html += `<div class="sg-detail-field">
        <div class="sg-detail-field-label">生成 Prompt</div>
        <div class="sg-detail-field-value" style="font-size:11px;line-height:1.5;white-space:pre-wrap;word-break:break-word;color:var(--text-mid)">${escHtml(raw.generation_prompt)}</div>
      </div>`;
    }
  }

  // Show video clip and production info for shot nodes
  if (type === 'shot') {
    // Enrich with shot-plan data if not already present
    let shotPlanEntry = raw._shotPlanEntry || nodeData._shotPlanEntry || null;
    if (!shotPlanEntry && window._shotPlanData && window._shotPlanData.shots) {
      shotPlanEntry = window._shotPlanData.shots.find(s => s.shot_id === nodeData.id);
    }
    if (shotPlanEntry) {
      if (!raw.execution && shotPlanEntry.execution) raw.execution = shotPlanEntry.execution;
      if (!raw.path && shotPlanEntry.output_path) raw.path = shotPlanEntry.output_path;
      if (!raw.duration_seconds && shotPlanEntry.duration_seconds) raw.duration_seconds = shotPlanEntry.duration_seconds;
    }
    // Enrich audio states from story data if not already present
    const audioStatesFromSP = nodeData._audioStates || [];
    if (audioStatesFromSP.length === 0 && shotPlanEntry && storyData) {
      const evtId = shotPlanEntry.event_id || (raw._for_event && raw._for_event[0]) || '';
      if (evtId) {
        const aaDuring = storyData.audio_active_during || {};
        for (const [audioId, eventIds] of Object.entries(aaDuring)) {
          if (eventIds.includes(evtId)) {
            const audioState = (storyData.audio_states || []).find(a => a.id === audioId);
            if (audioState) audioStatesFromSP.push(audioState);
          }
        }
      }
    }

    // Video player: prefer merged (video+audio), fallback to raw video, fallback to output_path
    const mergedPath = raw._merged_path || nodeData.mergedPath || '';
    const rawVideoPath = raw._raw_video_path || nodeData.rawVideoPath || '';
    const clipPath = mergedPath || rawVideoPath || raw._clip_path || raw.path || '';
    if (clipPath) {
      const clipUrl = resolveRefImageUrl(clipPath);
      const label = mergedPath ? '合成片段 (video + audio)' : '视频片段 (raw video)';
      html += `<div class="sg-detail-field">
        <div class="sg-detail-field-label">${label}</div>
        <div class="sg-detail-field-value sg-clip-container">
          <video src="${escHtml(clipUrl)}" class="sg-clip-video" controls preload="metadata"
                 onerror="this.style.display='none';this.nextElementSibling.style.display='block'"
          ></video>
          <span class="sg-clip-fallback" style="display:none;font-size:11px;color:var(--text-dim)">Clip not generated yet</span>
        </div>
      </div>`;
    }

    // Show audio composition info
    const audioStates = audioStatesFromSP;
    if (audioStates.length > 0) {
      html += `<div class="sg-detail-field">
        <div class="sg-detail-field-label">音频合成 (Audio Mix)</div>
        <div class="sg-detail-field-value" style="font-size:11px;line-height:1.6">`;
      for (const as of audioStates) {
        const icon = as.layer === 'audio_dialogue' ? '🎤' : '🎵';
        const layerLabel = as.layer === 'audio_dialogue' ? '对白' : 'BGM';
        const detail = as.layer === 'audio_dialogue'
          ? (as.text ? `"${as.text.slice(0, 40)}${as.text.length > 40 ? '...' : ''}"` : '')
          : (as.music_prompt ? as.music_prompt.slice(0, 40) : '');
        html += `<div style="margin-bottom:4px;padding:3px 6px;background:rgba(139,92,246,0.1);border-radius:4px">
          ${icon} <strong>${escHtml(layerLabel)}</strong>: ${escHtml(as.id)}${detail ? ' — ' + escHtml(detail) : ''}
        </div>`;
      }
      html += `</div></div>`;
    }

    // Production pipeline info (from execution writeback in shot-plan)
    const shotExec = raw.execution || {};
    if (shotExec.mode) {
      html += `<div class="sg-detail-field">
        <div class="sg-detail-field-label">制作流程 (Production Pipeline)</div>
        <div class="sg-detail-field-value" style="font-size:11px;line-height:1.6">`;

      const mode = shotExec.mode || '?';
      const modeLabel = mode === 'image_to_video' ? '图生视频 (image→video)' : mode === 'reference_to_video' ? '参考图生视频 (ref→video)' : mode === 'text_to_video' ? '文生视频 (text→video)' : mode;
      html += `<div style="margin-bottom:6px;padding:4px 8px;background:rgba(59,130,246,0.15);border-radius:4px">
        <strong>生成模式:</strong> ${escHtml(modeLabel)}
        ${raw.duration_seconds ? ` · <strong>${raw.duration_seconds}s</strong>` : ''}
      </div>`;

      // Reference images
      const execRefImages = shotExec.reference_images || [];
      if (execRefImages.length) {
        html += `<div style="margin-bottom:6px">
          <div><strong>参考图 (Reference Images)</strong> — ${execRefImages.length} 张</div>
          <div style="display:flex;flex-wrap:wrap;gap:4px;margin-top:4px">`;
        for (const imgPath of execRefImages) {
          const imgUrl = resolveRefImageUrl(imgPath);
          const imgName = imgPath.split('/').pop();
          html += `<div style="text-align:center;width:64px">
            <img src="${escHtml(imgUrl)}" style="width:60px;height:60px;object-fit:cover;border-radius:4px;border:1px solid rgba(255,255,255,0.2);cursor:pointer"
                 onclick="openImageLightbox('${escHtml(imgUrl)}')"
                 onerror="this.style.display='none'"
                 title="${escHtml(imgName)}" />
            <div style="font-size:9px;color:var(--text-dim);overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${escHtml(imgName)}</div>
          </div>`;
        }
        html += `</div></div>`;
      }

      // First frame
      if (shotExec.first_frame_path) {
        const ffUrl = resolveRefImageUrl(shotExec.first_frame_path);
        html += `<div style="margin-bottom:6px">
          <div><strong>首帧图 (First Frame)</strong></div>
          <div style="margin-top:4px">
            <img src="${escHtml(ffUrl)}" style="max-width:120px;max-height:120px;border-radius:4px;border:1px solid rgba(255,255,255,0.2);cursor:pointer"
                 onclick="openImageLightbox('${escHtml(ffUrl)}')"
                 onerror="this.parentElement.innerHTML='<span style=color:var(--text-dim)>首帧未生成</span>'" />
          </div>
        </div>`;
        if (shotExec.first_frame_prompt) {
          html += `<div style="margin-bottom:6px"><strong>首帧 Prompt:</strong> <span style="color:var(--text-mid);font-size:11px">${escHtml(shotExec.first_frame_prompt)}</span></div>`;
        }
      }

      // Tail frame (duration-split)
      if (shotExec.tail_frame_path) {
        const tfUrl = resolveRefImageUrl(shotExec.tail_frame_path);
        html += `<div style="margin-bottom:6px">
          <div><strong>尾帧衔接 (Tail Frame)</strong></div>
          <div style="margin-top:4px">
            <img src="${escHtml(tfUrl)}" style="max-width:120px;max-height:120px;border-radius:4px;border:1px solid rgba(255,255,255,0.2);cursor:pointer"
                 onclick="openImageLightbox('${escHtml(tfUrl)}')"
                 onerror="this.parentElement.innerHTML='<span style=color:var(--text-dim)>尾帧未提取</span>'" />
          </div>
        </div>`;
      }

      // Sequence tail frame (cross-shot continuity)
      if (shotExec.sequence_tail_frame_path) {
        const stfUrl = resolveRefImageUrl(shotExec.sequence_tail_frame_path);
        html += `<div style="margin-bottom:6px">
          <div><strong>序列尾帧接续 (Sequence Tail Frame)</strong>
            <span style="font-size:10px;color:var(--text-dim);margin-left:4px">← 来自前一事件</span>
          </div>
          <div style="margin-top:4px">
            <img src="${escHtml(stfUrl)}" style="max-width:120px;max-height:120px;border-radius:4px;border:1px solid rgba(20,184,166,0.5);cursor:pointer"
                 onclick="openImageLightbox('${escHtml(stfUrl)}')"
                 onerror="this.parentElement.innerHTML='<span style=color:var(--text-dim)>序列尾帧未提取</span>'" />
          </div>
        </div>`;
      }

      html += `</div></div>`;
    }

    // ---- Video Generation Prompt (full) ----
    if (shotExec.prompt) {
      html += `<div class="sg-detail-field">
        <div class="sg-detail-field-label">视频生成 Prompt</div>
        <div class="sg-detail-field-value" style="font-size:11px;line-height:1.5;white-space:pre-wrap;word-break:break-word;color:var(--text-mid)">${escHtml(shotExec.prompt)}</div>
      </div>`;
    }
    if (shotExec.negative_prompt) {
      html += `<div class="sg-detail-field">
        <div class="sg-detail-field-label">Negative Prompt</div>
        <div class="sg-detail-field-value" style="font-size:11px;line-height:1.5;white-space:pre-wrap;word-break:break-word;color:var(--text-dim)">${escHtml(shotExec.negative_prompt)}</div>
      </div>`;
    }
    if (shotExec.reasoning) {
      html += `<div class="sg-detail-field">
        <div class="sg-detail-field-label">决策推理 (Reasoning)</div>
        <div class="sg-detail-field-value" style="font-size:11px;line-height:1.6;white-space:pre-wrap;word-break:break-word;color:var(--text-mid);padding:6px 8px;background:rgba(139,92,246,0.1);border-radius:4px;border-left:3px solid rgba(139,92,246,0.4)">${escHtml(shotExec.reasoning)}</div>
      </div>`;
    }
  }

  // Show image preview for asset frame nodes
  if ((type === 'asset_first_frame' || type === 'asset_tail_frame' || type === 'asset_ref_image') && raw.path) {
    const imgUrl = resolveRefImageUrl(raw.path);
    const imgUrlBusted = imgUrl + (imgUrl.includes('?') ? '&' : '?') + 't=' + Date.now();
    html += `<div class="sg-detail-field">
      <div class="sg-detail-field-label">${type === 'asset_ref_image' ? 'reference image' : type === 'asset_first_frame' ? 'first frame' : 'tail frame'}</div>
      <div class="sg-detail-field-value sg-ref-img-container">
        <img src="${escHtml(imgUrlBusted)}" class="sg-ref-img" alt="${escHtml(type)}"
             onclick="openImageLightbox('${escHtml(imgUrlBusted)}')"
             onerror="this.style.display='none';this.nextElementSibling.style.display='block'"
        /><span class="sg-ref-img-fallback" style="display:none;font-size:11px;color:var(--text-dim)">Not generated yet</span>
      </div>
    </div>`;
    // Show generation prompt if available
    if (raw.generation_prompt) {
      html += `<div class="sg-detail-field">
        <div class="sg-detail-field-label">生成 Prompt</div>
        <div class="sg-detail-field-value" style="font-size:11px;line-height:1.5;white-space:pre-wrap;word-break:break-word;color:var(--text-mid)">${escHtml(raw.generation_prompt)}</div>
      </div>`;
    }
  }

  // Show audio player for narrative audio nodes (audio file at assets/audio/{id}.mp3)
  if ((type === 'audio_bgm' || type === 'audio_dialogue') && raw.id) {
    const audioPath = `assets/audio/${raw.id}.mp3`;
    const audioUrl = resolveRefImageUrl(audioPath);
    html += `<div class="sg-detail-field">
      <div class="sg-detail-field-label">audio file</div>
      <div class="sg-detail-field-value">
        <audio src="${escHtml(audioUrl)}" controls preload="metadata" style="width:100%"
               onerror="this.style.display='none';this.nextElementSibling.style.display='block'"
        ></audio>
        <span style="display:none;font-size:11px;color:var(--text-dim)">Not generated yet</span>
      </div>
    </div>`;
  }


  // Show video player for asset_output nodes
  if (type === 'asset_output' && raw.path) {
    const videoUrl = resolveRefImageUrl(raw.path);
    html += `<div class="sg-detail-field">
      <div class="sg-detail-field-label">output video</div>
      <div class="sg-detail-field-value sg-clip-container">
        <video src="${escHtml(videoUrl)}" class="sg-clip-video" controls preload="metadata"
               onerror="this.style.display='none';this.nextElementSibling.style.display='block'"
        ></video>
        <span class="sg-clip-fallback" style="display:none;font-size:11px;color:var(--text-dim)">Not generated yet</span>
      </div>
    </div>`;
  }

  // Show composition summary for shot nodes (brief info about the assembled clip)
  if (type === 'shot') {
    // Prefer attached shot-plan entry (Assets view), fallback to lookup from global data (Narrative view)
    let plan = nodeData._shotPlanEntry || null;
    if (!plan && window._shotPlanData) {
      const forEvents = raw._for_event || [];
      const eventId = forEvents[0] || '';
      const shotId = eventId ? `${eventId}_shot_${raw.order || 0}` : '';
      plan = (window._shotPlanData.shots || []).find(s => s.shot_id === shotId || s.event_id === eventId) || null;
    }
    if (plan) {
      const exec = plan.execution || {};

      // ---- Brief shot info ----
      html += `<div class="sg-detail-field">
        <div class="sg-detail-field-label">片段信息 (Clip Info)</div>
        <div class="sg-detail-field-value" style="font-size:11px;line-height:1.6">`;

      const infoItems = [
        plan.shot_type ? `类型: ${plan.shot_type}` : '',
        plan.angle ? `角度: ${plan.angle}` : '',
        plan.movement ? `运动: ${plan.movement}` : '',
        plan.duration_seconds ? `时长: ${plan.duration_seconds}s` : '',
        plan.is_continuation ? '(延续镜头)' : '',
      ].filter(Boolean);
      if (infoItems.length) {
        html += `<div style="margin-bottom:6px;padding:4px 8px;background:rgba(59,130,246,0.1);border-radius:4px">${escHtml(infoItems.join(' · '))}</div>`;
      }
      const planContent = plan.content || plan.intent;
      if (planContent) {
        html += `<div style="margin-bottom:6px"><strong>内容:</strong> ${escHtml(planContent)}</div>`;
      }
      if (plan.transition_in || plan.transition_out) {
        const transItems = [plan.transition_in ? `入: ${plan.transition_in}` : '', plan.transition_out ? `出: ${plan.transition_out}` : ''].filter(Boolean);
        html += `<div style="margin-bottom:6px"><strong>转场:</strong> ${escHtml(transItems.join(' · '))}</div>`;
      }
      html += `</div></div>`;
    }
  }

  // Blocking (spatial staging) — dedicated section for event nodes
  if (type === 'event' && raw.blocking && typeof raw.blocking === 'object' && Object.keys(raw.blocking).length > 0) {
    html += `<div class="sg-detail-field">
      <div class="sg-detail-field-label">调度 (Blocking)</div>
      <div class="sg-detail-field-value" style="font-size:11px;line-height:1.6">`;
    for (const [charId, bdata] of Object.entries(raw.blocking)) {
      if (!bdata || typeof bdata !== 'object') continue;
      const charName = ((typeof storyData !== 'undefined' && storyData ? storyData.characters : null) || []).find(c => c.id === charId);
      const displayName = charName ? charName.name : charId;
      html += `<div style="margin-bottom:8px;padding:6px 8px;background:rgba(59,130,246,0.08);border-radius:4px;border-left:3px solid rgba(59,130,246,0.4)">
        <div style="font-weight:600;margin-bottom:4px;color:var(--text-bright)">${escHtml(displayName)}</div>`;
      if (bdata.region) html += `<div><span style="color:var(--text-dim)">区域:</span> ${escHtml(bdata.region)}</div>`;
      if (bdata.start) html += `<div><span style="color:var(--text-dim)">起始:</span> ${escHtml(bdata.start)}</div>`;
      if (bdata.action) html += `<div><span style="color:var(--text-dim)">动作:</span> ${escHtml(bdata.action)}</div>`;
      if (bdata.end) html += `<div><span style="color:var(--text-dim)">终了:</span> ${escHtml(bdata.end)}</div>`;
      html += `</div>`;
    }
    html += `</div></div>`;
  }

  // Fields already shown in structured sections above
  const skipFields = new Set(['id', 'type', 'reference_image', 'generation_prompt',
    'shot_type', 'angle', 'movement', 'duration', 'content', 'intent', 'focus_on', 'order',
    'composition', 'lens', 'focus_depth', 'transition_in', 'transition_out',
    'continuity_notes', 'prompt_materials', 'execution', 'output_path',
    'shot_id', 'event_id', 'camera_directive_id', 'is_continuation',
    'prev_shot', 'prev_shot_in_sequence', 'duration_seconds', 'blocking']);

  for (const [key, val] of Object.entries(raw)) {
    if (skipFields.has(key)) continue;
    if (key.startsWith('_')) continue; // skip internal fields (_cam_id, _for_event, _clip_path)
    if (val === null || val === undefined || val === '') continue;

    html += '<div class="sg-detail-field">';
    html += `<div class="sg-detail-field-label">${key}</div>`;

    if (typeof val === 'object' && !Array.isArray(val)) {
      html += '<div class="sg-detail-field-value">';
      for (const [k, v] of Object.entries(val)) {
        if (typeof v === 'object') {
          html += `<div><strong>${k}:</strong></div>`;
          html += `<div style="margin-left:8px;font-size:11px;color:var(--text-mid)">${JSON.stringify(v, null, 1)}</div>`;
        } else {
          html += `<div><strong>${k}:</strong> ${escHtml(String(v))}</div>`;
        }
      }
      html += '</div>';
    } else if (Array.isArray(val)) {
      html += `<div class="sg-detail-field-value">${val.map(v =>
        typeof v === 'object' ? `<div style="margin-bottom:4px">${JSON.stringify(v, null, 1)}</div>` : escHtml(String(v))
      ).join(', ')}</div>`;
    } else {
      html += `<div class="sg-detail-field-value">${escHtml(String(val))}</div>`;
    }

    html += '</div>';
  }

  return html;
}

function escHtml(s) {
  return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

/** Resolve a reference_image path to a /files/ URL.
 *  Backend returns absolute paths for all resolved assets.
 *  For paths that are already absolute (start with /), strip the leading slash
 *  and use directly.  For relative paths (e.g. "assets/..."), prepend storyGraphDir. */
function resolveRefImageUrl(refImage) {
  if (!refImage) return null;
  // Skip placeholder IDs (e.g. "ref_char_pony_main") that are not real file paths
  if (!refImage.includes('/') && !refImage.includes('.')) return null;

  // Absolute path from backend (e.g. "/home/user/project/assets/images/x.png")
  if (refImage.startsWith('/')) {
    return '/files/' + refImage.replace(/^\/+/, '');
  }

  // Relative path — prepend project directory
  let dir = storyGraphDir;
  if (!dir && typeof currentStoryGraphPath !== 'undefined' && currentStoryGraphPath) {
    dir = extractStoryGraphDir(currentStoryGraphPath);
    storyGraphDir = dir;
  }
  let path = refImage;
  if (dir && !path.startsWith(dir)) {
    path = dir + path;
  }
  return '/files/' + path;
}

/** Fetch list of .mp4 output files from the project's output/ directory. */
async function fetchOutputFiles() {
  let dir = storyGraphDir;
  if (!dir && typeof currentStoryGraphPath !== 'undefined' && currentStoryGraphPath) {
    dir = extractStoryGraphDir(currentStoryGraphPath);
  }
  if (!dir) return [];
  const outputDir = dir + 'output';
  try {
    const r = await fetch('/list-dir/' + encodeURI(outputDir) + '?suffix=.mp4');
    if (!r.ok) return [];
    const data = await r.json();
    // Filter out temporary intermediate files (tmp_*)
    return (data.files || []).filter(f => !f.stem.startsWith('tmp_'));
  } catch (e) {
    return [];
  }
}

// ---- Highlight neighbors on select ----
function highlightNeighbors(node) {
  cy.batch(() => {
    cy.elements().addClass('dimmed').removeClass('highlighted');
    let neighborhood = node.neighborhood().add(node);

    // Build a set of neighbor node IDs for fast lookup
    const neighborIds = new Set();
    neighborhood.nodes().forEach(n => neighborIds.add(n.id()));

    console.log('[highlightNeighbors] clicked:', node.id(), 'nodeType:', node.data('nodeType'));
    console.log('[highlightNeighbors] neighbor count:', neighborhood.nodes().length);
    const types = {};
    neighborhood.nodes().forEach(n => {
      const t = n.data('nodeType') || 'unknown';
      types[t] = (types[t] || 0) + 1;
    });
    console.log('[highlightNeighbors] neighbor types:', JSON.stringify(types));
    console.log('[highlightNeighbors] neighborIds:', Array.from(neighborIds));

    // Extend: if a state node is in the neighborhood, also include its parent entity
    // (follow HAS_STATE edges upward)
    const extra = cy.collection();
    neighborhood.nodes().forEach(n => {
      const type = n.data('nodeType');
      if (type === 'character_appearance' ||
          type === 'prop_state' || type === 'location_state' || type === 'audio_bgm' || type === 'audio_dialogue') {
        n.connectedEdges().forEach(e => {
          const et = e.data('edgeType');
          if (et === 'HAS_STATE' && e.target().id() === n.id()) {
            extra.merge(e.source());
            extra.merge(e);
          }
        });
      }
    });

    neighborhood = neighborhood.add(extra);
    neighborhood.removeClass('dimmed').addClass('highlighted');
  });
}

// ---- Compute event topological order ----
function buildEventOrder(data) {
  eventOrder = {};
  const eventIds = (data.events || []).map(e => e.id);
  const adj = {};
  const inDeg = {};
  for (const id of eventIds) { adj[id] = []; inDeg[id] = 0; }
  for (const seq of (data.event_sequence || [])) {
    if (seq.type !== 'PARALLEL' && adj[seq.from]) {
      adj[seq.from].push(seq.to);
      inDeg[seq.to] = (inDeg[seq.to] || 0) + 1;
    }
  }
  const queue = eventIds.filter(id => (inDeg[id] || 0) === 0);
  let idx = 0;
  while (queue.length > 0) {
    const node = queue.shift();
    eventOrder[node] = idx++;
    for (const next of (adj[node] || [])) {
      inDeg[next]--;
      if (inDeg[next] === 0) queue.push(next);
    }
  }
  // Assign remaining disconnected events
  for (const id of eventIds) {
    if (eventOrder[id] === undefined) eventOrder[id] = idx++;
  }
}

// ---- Relationship edges for a given event ----
function getRelationshipsAtEvent(eventId) {
  if (!storyData) return [];
  const currentIdx = eventOrder[eventId];
  if (currentIdx === undefined) return [];

  const rels = [];
  for (const ch of (storyData.characters || [])) {
    if (!ch.relationships) continue;
    for (const [targetId, history] of Object.entries(ch.relationships)) {
      // Find the latest entry where since <= current event
      let active = null;
      for (const entry of history) {
        if (entry.since === null) {
          active = entry; // before story, always applies
        } else {
          const sinceIdx = eventOrder[entry.since];
          if (sinceIdx !== undefined && sinceIdx <= currentIdx) {
            active = entry;
          }
        }
      }
      if (active) {
        // Avoid duplicate edges (A→B and B→A for same relationship)
        const key = [ch.id, targetId].sort().join('|');
        if (!rels.find(r => r.key === key)) {
          rels.push({ key, source: ch.id, target: targetId, kind: active.kind });
        }
      }
    }
  }
  // Also check prop relationships
  for (const p of (storyData.props || [])) {
    if (!p.relationships) continue;
    for (const [targetId, history] of Object.entries(p.relationships)) {
      let active = null;
      for (const entry of history) {
        if (entry.since === null) {
          active = entry;
        } else {
          const sinceIdx = eventOrder[entry.since];
          if (sinceIdx !== undefined && sinceIdx <= currentIdx) {
            active = entry;
          }
        }
      }
      if (active) {
        const key = [p.id, targetId].sort().join('|');
        if (!rels.find(r => r.key === key)) {
          rels.push({ key, source: p.id, target: targetId, kind: active.kind });
        }
      }
    }
  }
  return rels;
}

let relationshipEdgeIds = []; // track temporary edges

function showRelationships(eventId) {
  clearRelationships();
  const rels = getRelationshipsAtEvent(eventId);
  if (rels.length === 0) return;

  cy.batch(() => {
    for (const rel of rels) {
      const edgeId = `rel_${rel.source}_${rel.target}`;
      const srcNode = cy.getElementById(rel.source);
      const tgtNode = cy.getElementById(rel.target);
      if (srcNode.length && tgtNode.length) {
        cy.add({
          data: {
            id: edgeId,
            source: rel.source,
            target: rel.target,
            edgeType: 'RELATIONSHIP',
            label: rel.kind,
          },
        });
        relationshipEdgeIds.push(edgeId);
        // Ensure connected nodes are visible
        srcNode.removeClass('dimmed').addClass('highlighted');
        tgtNode.removeClass('dimmed').addClass('highlighted');
      }
    }
  });
}

function clearRelationships() {
  if (relationshipEdgeIds.length === 0) return;
  cy.batch(() => {
    for (const id of relationshipEdgeIds) {
      const el = cy.getElementById(id);
      if (el.length) cy.remove(el);
    }
  });
  relationshipEdgeIds = [];
}

// ---- Init Cytoscape ----
function initGraph(data) {
  // Clear stale generating state from previous session/connection
  generatingNodes.clear();
  storyData = data;

  // Build unified graph: narrative + assets (if shot-plan available)
  const narrativeElements = convertToElements(data);
  if (window._shotPlanData) {
    graphElements = buildAssetsViewElements(data, window._shotPlanData, []);
    // Async: fetch output files and rebuild with them
    fetchOutputFiles().then(outFiles => {
      window._outputFiles = outFiles;
      graphElements = buildAssetsViewElements(data, window._shotPlanData, outFiles);
      // Refresh: add any new output nodes
      if (cy) {
        cy.batch(() => {
          cy.elements().remove();
          cy.add(graphElements.nodes);
          cy.add(graphElements.edges);
        });
        _layoutAndCheck();
      }
    });
  } else {
    graphElements = narrativeElements;
  }

  const { nodes, edges } = graphElements;

  if (cy) cy.destroy();

  // Make container visible BEFORE creating Cytoscape (it needs non-zero dimensions)
  document.getElementById('sg-empty').style.display = 'none';
  document.getElementById('sg-toolbar').style.display = 'flex';
  document.getElementById('sg-body').style.display = 'flex';

  cy = cytoscape({
    container: document.getElementById('sg-cy'),
    elements: { nodes, edges },
    style: buildStylesheet(),
    layout: { name: 'preset' },
    minZoom: 0.1,
    maxZoom: 4,
    wheelSensitivity: 0.3,
  });

  // Precompute event ordering for relationship queries
  buildEventOrder(data);

  cy.on('tap', 'node', function (evt) {
    const node = evt.target;
    showDetail(node.data());
    highlightNeighbors(node);

    // Show relationships at this event's point in time
    if (node.data('nodeType') === 'event') {
      showRelationships(node.id());
    } else {
      clearRelationships();
    }
  });

  cy.on('tap', function (evt) {
    if (evt.target === cy) {
      hideDetail();
      clearRelationships();
    }
  });

  _layoutAndCheck();
}

/** Apply layout, filters, and asset status checks. */
function _layoutAndCheck() {
  applyFilters();
  runLayout();
  applyImageStatusClasses(cy);
  checkRefImageStatus(cy);
  checkShotClipStatus(cy);
  checkExecutionClipStatus(cy);
}

// ---- Load JSON file ----
function loadStoryGraphFile(file) {
  const reader = new FileReader();
  reader.onload = function (e) {
    try {
      const data = JSON.parse(e.target.result);
      initGraph(data);
    } catch (err) {
      alert('Failed to parse JSON: ' + err.message);
    }
  };
  reader.readAsText(file);
}

// ---- Toggle filter ----
function toggleType(type, btn) {
  if (visibleTypes.has(type)) {
    visibleTypes.delete(type);
    btn.classList.remove('active');
  } else {
    visibleTypes.add(type);
    btn.classList.add('active');
  }
  applyFilters();
}

function toggleProductionTypes(btn) {
  const types = ['production_style', 'production_ratio', 'production_duration', 'production_language'];
  const allVisible = types.every(t => visibleTypes.has(t));
  for (const t of types) {
    if (allVisible) visibleTypes.delete(t);
    else visibleTypes.add(t);
  }
  if (allVisible) btn.classList.remove('active');
  else btn.classList.add('active');
  applyFilters();
}

// ---- Load sample data ----
function loadSampleData() {
  fetch('/static/story-graph-sample.json')
    .then(r => r.json())
    .then(data => initGraph(data))
    .catch(err => alert('Failed to load sample: ' + err.message));
}

/** Extract the directory prefix from a story-graph.json file path.
 *  This is used to resolve relative reference_image paths. */
function extractStoryGraphDir(filePath) {
  const cleaned = filePath.replace(/^\.\//, '').replace(/^\/+/, '');
  const lastSlash = cleaned.lastIndexOf('/');
  return lastSlash >= 0 ? cleaned.substring(0, lastSlash + 1) : '';
}

// ---- Fetch story graph from server (called when agent writes story-graph.json) ----
function fetchAndLoadStoryGraph(filePath) {
  // Normalize: strip leading ./ or leading / to avoid double slashes in URL
  let cleaned = filePath.replace(/^\.\//, '').replace(/^\/+/, '');
  // Extract directory prefix for resolving relative reference_image paths
  storyGraphDir = extractStoryGraphDir(filePath);
  const url = '/read-json/' + encodeURI(cleaned);
  console.log('[SG] fetchAndLoadStoryGraph:', filePath, '-> dir:', storyGraphDir);
  // Also try to load shot-plan.json from the same directory
  const shotPlanPath = cleaned.replace(/story-graph\.json$/, 'shot-plan.json');
  const shotPlanUrl = '/read-json/' + encodeURI(shotPlanPath);

  const sgPromise = fetch(url).then(r => { if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); });
  const spPromise = fetch(shotPlanUrl).then(r => r.ok ? r.json() : null).catch(() => null);

  Promise.all([sgPromise, spPromise])
    .then(([data, shotPlan]) => {
      if (shotPlan) window._shotPlanData = shotPlan;
      initGraph(data);
    })
    .catch(err => console.warn('Failed to auto-load story graph:', err.message));
}

// ---- Export ----
function exportGraphJSON() {
  if (!storyData) return;
  const blob = new Blob([JSON.stringify(storyData, null, 2)], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = 'story-graph.json';
  a.click();
  URL.revokeObjectURL(url);
}

// ===========================================================================
// Execution Graph — visualizes the production pipeline (assets & shots)
// ===========================================================================

/**
 * Build execution graph elements from story-graph + shot-plan data.
 * Returns { nodes, edges } in Cytoscape format.
 */
function buildExecutionElements(sgData, spData) {
  const nodes = [];
  const edges = [];
  let _eid = 0;
  const eid = () => `exec_e_${++_eid}`;

  if (!spData || !spData.shots || !sgData) return { nodes, edges };

  const shots = spData.shots;

  // --- Build lookup: reference_image path -> generation_prompt ---
  const refImagePromptMap = {};
  for (const list of [sgData.characters, sgData.props, sgData.locations,
                       sgData.character_appearances, sgData.character_minds,
                       sgData.prop_states, sgData.location_states]) {
    for (const item of (list || [])) {
      if (item.reference_image && item.generation_prompt) {
        refImagePromptMap[item.reference_image] = item.generation_prompt;
      }
    }
  }

  // --- Deduplicated reference image nodes ---
  const refImageNodes = new Map();

  function getRefImageNodeId(imgPath) {
    if (refImageNodes.has(imgPath)) return refImageNodes.get(imgPath).id;
    const imgName = imgPath.split('/').pop().replace(/\.[^.]+$/, '');
    const nodeId = `ref_${imgName}`;
    refImageNodes.set(imgPath, { id: nodeId });
    nodes.push({
      data: {
        id: nodeId,
        label: imgName.replace(/^(appear_|char_|loc_|lstate_|pstate_|prop_)/, '').slice(0, 15),
        fullLabel: `参考图: ${imgName}`,
        nodeType: 'asset_ref_image',
        imagePath: imgPath,
        raw: { id: imgName, path: imgPath, generation_prompt: refImagePromptMap[imgPath] || '' },
      },
    });
    return nodeId;
  }

  // --- Iterate shots ---
  for (const shot of shots) {
    const shotId = shot.shot_id;
    const exec = shot.execution || {};

    // Shot node (merged: includes design info + video output)
    const intent = shot.content || shot.intent || '';
    const mode = exec.mode === 'image_to_video' ? '图→视频' : exec.mode === 'reference_to_video' ? '参考→视频' : exec.mode === 'text_to_video' ? '文→视频' : (exec.mode || '?');
    const dur = shot.duration_seconds || '?';
    nodes.push({
      data: {
        id: shotId,
        label: `${intent.slice(0, 20)} (${mode} ${dur}s)`,
        fullLabel: `Shot: ${intent}`,
        nodeType: 'shot',
        clipPath: shot.output_path,
        raw: { ...shot, _for_event: [shot.event_id], _clip_path: shot.output_path, path: shot.output_path },
      },
    });

    // --- Reference images (from execution writeback) ---
    const execRefImages = exec.reference_images || [];
    for (const imgPath of execRefImages) {
      const refNodeId = getRefImageNodeId(imgPath);
      edges.push({ data: { id: eid(), source: refNodeId, target: shotId, edgeType: 'USES_REF' } });
    }

    // --- First frame (from execution writeback) ---
    if (exec.first_frame_path) {
      const ffId = `ff_${shotId}`;
      nodes.push({
        data: {
          id: ffId,
          label: '首帧',
          fullLabel: `首帧图: ${shotId}`,
          nodeType: 'asset_first_frame',
          imagePath: exec.first_frame_path,
          raw: { path: exec.first_frame_path, generation_prompt: exec.first_frame_prompt || '' },
        },
      });
      edges.push({ data: { id: eid(), source: ffId, target: shotId, edgeType: 'USES_FRAME' } });
    }

    // --- Tail frame (from execution writeback) ---
    if (exec.tail_frame_path) {
      const tfId = `tf_${shotId}`;
      nodes.push({
        data: {
          id: tfId,
          label: '尾帧',
          fullLabel: `尾帧: ${shotId}`,
          nodeType: 'asset_tail_frame',
          imagePath: exec.tail_frame_path,
          raw: { path: exec.tail_frame_path },
        },
      });
      edges.push({ data: { id: eid(), source: tfId, target: shotId, edgeType: 'USES_FRAME' } });

      // Edge from previous shot to this tail frame (EXTRACTS)
      if (shot.prev_shot && shot.prev_shot.output_path) {
        const sourceShot = shots.find(s => s.output_path === shot.prev_shot.output_path);
        if (sourceShot) {
          edges.push({ data: { id: eid(), source: sourceShot.shot_id, target: tfId, edgeType: 'EXTRACTS' } });
        }
      }
    }

    // --- Sequence tail frame (cross-shot continuity) ---
    if (exec.sequence_tail_frame_path) {
      const stfId = `stf_${shotId}`;
      nodes.push({
        data: {
          id: stfId,
          label: '序列尾帧',
          fullLabel: `序列尾帧接续: ${shotId}`,
          nodeType: 'asset_tail_frame',
          imagePath: exec.sequence_tail_frame_path,
          raw: { path: exec.sequence_tail_frame_path },
        },
      });
      edges.push({ data: { id: eid(), source: stfId, target: shotId, edgeType: 'USES_FRAME' } });

      // Edge from predecessor shot to this sequence tail frame (EXTRACTS)
      if (shot.prev_shot_in_sequence && shot.prev_shot_in_sequence.output_path) {
        const sourceShot = shots.find(s => s.output_path === shot.prev_shot_in_sequence.output_path);
        if (sourceShot) {
          edges.push({ data: { id: eid(), source: sourceShot.shot_id, target: stfId, edgeType: 'EXTRACTS' } });
        }
      }
    } else if (shot.prev_shot_in_sequence && !exec.mode) {
      // Not yet executed but eligible for sequence continuity — show a placeholder edge
      const prevShotId = shot.prev_shot_in_sequence.shot_id;
      // Dashed edge directly between shots to indicate planned sequence continuity
      edges.push({ data: { id: eid(), source: prevShotId, target: shotId, edgeType: 'SEQUENCE_CONTINUITY' } });
    }
  }

  return { nodes, edges };
}

/**
 * Compute positions for execution graph.
 * Left-to-right pipeline: ref_images → frames → shot (with video)
 * Shots ordered top-to-bottom by event sequence.
 */
function computeExecutionPositions(sgData, spData) {
  const pos = {};
  if (!spData || !spData.shots) return pos;

  const shots = spData.shots;
  const COL_REF = 0;          // reference images column
  const COL_FRAME = 250;      // first/tail frame column
  const COL_SHOT = 500;       // shot column (includes video output)
  const ROW_GAP = 120;        // gap between shot rows
  const REF_Y_OFFSET = 25;    // vertical spread for multiple ref images

  const refImagePositioned = new Map();

  // First pass: assign Y to each shot row
  const shotYMap = {};
  let currentY = 60;
  for (const shot of shots) {
    shotYMap[shot.shot_id] = currentY;
    currentY += ROW_GAP;
  }

  // Second pass: position all nodes
  for (const shot of shots) {
    const shotId = shot.shot_id;
    const y = shotYMap[shotId];
    const exec = shot.execution || {};

    // Shot node (includes video output)
    pos[shotId] = { x: COL_SHOT, y };

    // First frame
    if (exec.first_frame_path) {
      pos[`ff_${shotId}`] = { x: COL_FRAME, y: y - 20 };
    }

    // Tail frame
    if (exec.tail_frame_path) {
      pos[`tf_${shotId}`] = { x: COL_FRAME, y: y + 20 };
    }

    // Sequence tail frame
    if (exec.sequence_tail_frame_path) {
      pos[`stf_${shotId}`] = { x: COL_FRAME, y: y + 40 };
    }

    // Reference images
    const execRefImages = exec.reference_images || [];
    for (let i = 0; i < execRefImages.length; i++) {
      const imgPath = execRefImages[i];
      const imgName = imgPath.split('/').pop().replace(/\.[^.]+$/, '');
      const refNodeId = `ref_${imgName}`;
      if (!refImagePositioned.has(refNodeId)) {
        const refY = y + (i - (execRefImages.length - 1) / 2) * REF_Y_OFFSET;
        pos[refNodeId] = { x: COL_REF, y: refY };
        refImagePositioned.set(refNodeId, true);
      }
    }
  }

  return pos;
}

/**
 * Build elements for the "Assets" overlay view:
 * narrative story graph + asset nodes (ref images, frames, clips) from shot-plan.
 */
function buildAssetsViewElements(sgData, spData, outputFiles) {
  const narrative = convertToElements(sgData);
  const nodes = [...narrative.nodes];
  const edges = [...narrative.edges];
  let _eid = 50000;
  const eid = () => `asset_e_${++_eid}`;

  if (!spData || !spData.shots) return { nodes, edges };

  const shots = spData.shots;
  const nodeIdSet = new Set(nodes.map(n => n.data.id));
  const addedRefEdges = new Set();

  // Build a map: event_id -> list of narrative shot node IDs (from camera_directives)
  const shotNodesByEvent = {};
  for (const n of nodes) {
    if (n.data.nodeType === 'shot' && n.data.raw && n.data.raw._for_event) {
      for (const evtId of n.data.raw._for_event) {
        if (!shotNodesByEvent[evtId]) shotNodesByEvent[evtId] = [];
        shotNodesByEvent[evtId].push(n.data.id);
      }
    }
  }

  // Build reverse map: audio_state_id -> [event_ids]
  const audioActiveDuring = sgData.audio_active_during || {};
  // Invert to: event_id -> [audio_state objects]
  const audioByEvent = {};
  for (const [audioId, eventIds] of Object.entries(audioActiveDuring)) {
    const audioState = (sgData.audio_states || []).find(a => a.id === audioId);
    if (!audioState) continue;
    for (const evtId of eventIds) {
      if (!audioByEvent[evtId]) audioByEvent[evtId] = [];
      audioByEvent[evtId].push(audioState);
    }
  }

  // Build a node map for quick lookup to attach merged info to narrative shot nodes
  const nodeById = {};
  for (const n of nodes) { nodeById[n.data.id] = n; }

  for (const shot of shots) {
    const shotId = shot.shot_id;
    const eventId = shot.event_id;
    const exec = shot.execution || {};

    // Find narrative shot nodes belonging to this event
    const eventShotIds = shotNodesByEvent[eventId] || [];

    // Attach merged video path and audio info to narrative shot nodes
    for (const sid of eventShotIds) {
      const sNode = nodeById[sid];
      if (!sNode) continue;
      const mergedPath = exec.merged_path || '';
      const rawVideoPath = shot.output_path || '';
      // Prefer merged (video+audio), fallback to raw video
      sNode.data.mergedPath = mergedPath;
      sNode.data.rawVideoPath = rawVideoPath;
      sNode.data.clipPath = mergedPath || rawVideoPath || sNode.data.clipPath;
      // Attach audio info for this shot's event
      sNode.data._audioStates = audioByEvent[eventId] || [];
      sNode.data._shotPlanEntry = shot;
    }

    // Reference images — add USES_REF edges from entity/state nodes to event's shot nodes
    const pm = shot.prompt_materials || {};
    const refEntityIds = [];
    for (const ap of (pm.appearances || [])) { if (ap.id) refEntityIds.push(ap.id); }
    for (const m of (pm.minds || [])) { if (m.id) refEntityIds.push(m.id); }
    if (pm.location_state && pm.location_state.id) refEntityIds.push(pm.location_state.id);
    for (const entityId of refEntityIds) {
      if (!nodeIdSet.has(entityId)) continue;
      for (const sid of eventShotIds) {
        const edgeKey = `${entityId}->${sid}`;
        if (!addedRefEdges.has(edgeKey)) {
          addedRefEdges.add(edgeKey);
          edges.push({ data: { id: eid(), source: entityId, target: sid, edgeType: 'USES_REF' } });
        }
      }
    }

    // First frame (from execution writeback)
    if (exec.first_frame_path) {
      const ffId = `ff_${shotId}`;
      nodes.push({
        data: {
          id: ffId, label: '\u9996\u5e27', fullLabel: `\u9996\u5e27\u56fe: ${shotId}`,
          nodeType: 'asset_first_frame', imagePath: exec.first_frame_path,
          raw: { path: exec.first_frame_path, generation_prompt: exec.first_frame_prompt || '' },
        },
      });
      nodeIdSet.add(ffId);
      const targetShotId = eventShotIds[0] || shotId;
      edges.push({ data: { id: eid(), source: ffId, target: targetShotId, edgeType: 'USES_FRAME' } });
    }

    // Tail frame (from execution writeback)
    if (exec.tail_frame_path) {
      const tfId = `tf_${shotId}`;
      nodes.push({
        data: {
          id: tfId, label: '\u5c3e\u5e27', fullLabel: `\u5c3e\u5e27: ${shotId}`,
          nodeType: 'asset_tail_frame', imagePath: exec.tail_frame_path,
          raw: { path: exec.tail_frame_path },
        },
      });
      nodeIdSet.add(tfId);
      const targetShotId = eventShotIds[0] || shotId;
      edges.push({ data: { id: eid(), source: tfId, target: targetShotId, edgeType: 'USES_FRAME' } });

      // EXTRACTS edge from previous shot node
      if (shot.prev_shot && shot.prev_shot.output_path) {
        const sourceShot = shots.find(s => s.output_path === shot.prev_shot.output_path);
        if (sourceShot) {
          // Find the narrative shot node for the source
          const sourceShotNodes = shotNodesByEvent[sourceShot.event_id] || [];
          for (const srcId of sourceShotNodes) {
            if (nodeIdSet.has(srcId)) {
              edges.push({ data: { id: eid(), source: srcId, target: tfId, edgeType: 'EXTRACTS' } });
              break;
            }
          }
        }
      }
    }

    // Sequence tail frame (cross-shot continuity, from execution writeback)
    if (exec.sequence_tail_frame_path) {
      const stfId = `stf_${shotId}`;
      nodes.push({
        data: {
          id: stfId, label: '序列尾帧', fullLabel: `序列尾帧接续: ${shotId}`,
          nodeType: 'asset_tail_frame', imagePath: exec.sequence_tail_frame_path,
          raw: { path: exec.sequence_tail_frame_path },
        },
      });
      nodeIdSet.add(stfId);
      const targetShotId = eventShotIds[0] || shotId;
      edges.push({ data: { id: eid(), source: stfId, target: targetShotId, edgeType: 'USES_FRAME' } });

      if (shot.prev_shot_in_sequence && shot.prev_shot_in_sequence.output_path) {
        const sourceShot = shots.find(s => s.output_path === shot.prev_shot_in_sequence.output_path);
        if (sourceShot) {
          const sourceShotNodes = shotNodesByEvent[sourceShot.event_id] || [];
          for (const srcId of sourceShotNodes) {
            if (nodeIdSet.has(srcId)) {
              edges.push({ data: { id: eid(), source: srcId, target: stfId, edgeType: 'EXTRACTS' } });
              break;
            }
          }
        }
      }
    } else if (shot.prev_shot_in_sequence && !exec.mode) {
      const prevShotId = shot.prev_shot_in_sequence.shot_id;
      // Find narrative shot node for predecessor
      const prevShotEntry = shots.find(s => s.shot_id === prevShotId);
      if (prevShotEntry) {
        const prevNarrativeNodes = shotNodesByEvent[prevShotEntry.event_id] || [];
        const targetShotId = eventShotIds[0] || shotId;
        for (const srcId of prevNarrativeNodes) {
          if (nodeIdSet.has(srcId)) {
            edges.push({ data: { id: eid(), source: srcId, target: targetShotId, edgeType: 'SEQUENCE_CONTINUITY' } });
            break;
          }
        }
      }
    }

    // Enrich narrative shot nodes with raw shot-plan data
    for (const sid of eventShotIds) {
      const sNode = nodeById[sid];
      if (sNode) {
        sNode.data.raw = { ...sNode.data.raw, ...shot, path: shot.output_path };
      }
    }
  }

  // --- Audio MIXES_INTO edges (dialogue → shots, BGM → output handled below) ---
  for (const as of (sgData.audio_states || [])) {
    const isDialogue = as.layer === 'audio_dialogue';
    if (isDialogue && nodeIdSet.has(as.id)) {
      const activeEvents = audioActiveDuring[as.id] || [];
      for (const evtId of activeEvents) {
        const shotIds = shotNodesByEvent[evtId] || [];
        for (const sid of shotIds) {
          edges.push({ data: { id: eid(), source: as.id, target: sid, edgeType: 'MIXES_INTO' } });
        }
      }
    }
  }

  // --- Final output nodes (dynamically from outputFiles) ---
  const outputList = outputFiles || [];
  const outputNodeIds = [];
  let prevOutputId = null;
  for (const of_ of outputList) {
    const outId = `output_${of_.stem}`;
    const outPath = `output/${of_.name}`;
    nodes.push({
      data: {
        id: outId, label: of_.stem, fullLabel: of_.name,
        nodeType: 'asset_output', clipPath: outPath,
        raw: { path: outPath, stage: of_.stem },
      },
    });
    nodeIdSet.add(outId);
    outputNodeIds.push(outId);
    if (prevOutputId) {
      edges.push({ data: { id: eid(), source: prevOutputId, target: outId, edgeType: 'ASSEMBLES' } });
    }
    prevOutputId = outId;
  }
  // Connect narrative shot nodes to first output (shot → output, ASSEMBLES)
  if (outputNodeIds.length > 0) {
    const firstOutputId = outputNodeIds[0];
    const connectedShots = new Set();
    for (const shot of shots) {
      const eventShotIds = shotNodesByEvent[shot.event_id] || [];
      for (const sid of eventShotIds) {
        if (!connectedShots.has(sid)) {
          connectedShots.add(sid);
          edges.push({ data: { id: eid(), source: sid, target: firstOutputId, edgeType: 'ASSEMBLES' } });
        }
      }
    }
  }
  // Connect BGM audio nodes to last output (MIXES_INTO)
  if (outputNodeIds.length > 0) {
    const lastOutputId = outputNodeIds[outputNodeIds.length - 1];
    for (const as of (sgData.audio_states || [])) {
      if (as.layer === 'audio_bgm' && nodeIdSet.has(as.id)) {
        edges.push({ data: { id: eid(), source: as.id, target: lastOutputId, edgeType: 'MIXES_INTO' } });
      }
    }
  }

  const validEdges = edges.filter(e => nodeIdSet.has(e.data.source) && nodeIdSet.has(e.data.target));
  return { nodes, edges: validEdges };
}

/**
 * Compute positions for Assets overlay view:
 * narrative positions + asset nodes positioned relative to their shots.
 */
function computeAssetsViewPositions(sgData, spData, outputFiles) {
  const pos = computePositions(sgData);
  if (!spData || !spData.shots) return pos;

  const FRAME_X_OFFSET = -100;
  // VIDEO_X_OFFSET removed — video merged into shot node
  // AUDIO_ASSET_X_OFFSET removed — audio merged into narrative nodes

  // Group shots by event so we can offset multiple shots vertically
  const shotsByEvent = {};
  for (const shot of spData.shots) {
    const eid = shot.event_id;
    if (!shotsByEvent[eid]) shotsByEvent[eid] = [];
    shotsByEvent[eid].push(shot);
  }

  const SHOT_ROW_GAP = 70; // vertical gap between shots of same event
  const SHOT_GROUP_MIN_GAP = 40; // minimum vertical gap between shot groups of different events

  // Build shot groups with ideal Y positions centered on their event
  const shotGroups = []; // { eventId, eventPos, shots: [{shot, idealY}] }
  for (const [eventId, eventShots] of Object.entries(shotsByEvent)) {
    const eventPos = pos[eventId];
    if (!eventPos) continue;
    const totalHeight = (eventShots.length - 1) * SHOT_ROW_GAP;
    const startY = eventPos.y - totalHeight / 2;
    const group = { eventId, eventPos, shots: [] };
    for (let si = 0; si < eventShots.length; si++) {
      group.shots.push({ shot: eventShots[si], idealY: startY + si * SHOT_ROW_GAP });
    }
    shotGroups.push(group);
  }

  // Sort groups by event Y so we can resolve vertical overlaps
  shotGroups.sort((a, b) => a.eventPos.y - b.eventPos.y);

  // Resolve overlaps: push groups down if they collide with the previous group
  let prevBottomY = -Infinity;
  for (const group of shotGroups) {
    if (group.shots.length === 0) continue;
    const topY = group.shots[0].idealY;
    if (topY < prevBottomY + SHOT_GROUP_MIN_GAP) {
      const shift = (prevBottomY + SHOT_GROUP_MIN_GAP) - topY;
      for (const s of group.shots) s.idealY += shift;
    }
    prevBottomY = group.shots[group.shots.length - 1].idealY;
  }

  // Assign final positions
  for (const group of shotGroups) {
    for (const { shot, idealY: shotY } of group.shots) {
      const shotId = shot.shot_id;
      const exec = shot.execution || {};
      const ex = group.eventPos.x;

      // Frames: left of event (from execution writeback)
      if (exec.first_frame_path) {
        pos[`ff_${shotId}`] = { x: ex + FRAME_X_OFFSET, y: shotY - 18 };
      }
      if (exec.tail_frame_path) {
        pos[`tf_${shotId}`] = { x: ex + FRAME_X_OFFSET, y: shotY + 18 };
      }
      if (exec.sequence_tail_frame_path) {
        pos[`stf_${shotId}`] = { x: ex + FRAME_X_OFFSET, y: shotY + 36 };
      }
    }
  }

  // Audio nodes reuse narrative positions (no separate asset nodes)

  // Output nodes: below all content, spaced horizontally
  const outList = outputFiles || [];
  if (outList.length > 0) {
    let maxY = 0;
    for (const key of Object.keys(pos)) {
      if (pos[key].y > maxY) maxY = pos[key].y;
    }
    const OUTPUT_Y = maxY + 150;
    const OUTPUT_X = 400;
    const spacing = 160;
    const totalWidth = (outList.length - 1) * spacing;
    const startX = OUTPUT_X - totalWidth / 2;
    for (let i = 0; i < outList.length; i++) {
      pos[`output_${outList[i].stem}`] = { x: startX + i * spacing, y: OUTPUT_Y };
    }
  }

  return pos;
}

// switchGraphView and _applyGraphView removed — views merged into unified graph

/**
 * Check clip existence for execution view clip nodes via HEAD requests.
 */
function checkExecutionClipStatus(cyInstance) {
  if (!cyInstance) return;
  const tasks = [];
  cyInstance.nodes().forEach(n => {
    const nodeType = n.data('nodeType');
    if (nodeType === 'shot') {
      // Shot nodes handled by checkShotClipStatus — skip here
      return;
    } else if (nodeType === 'asset_first_frame' || nodeType === 'asset_tail_frame') {
      // Frame nodes: verify via imagePath
      const imagePath = n.data('imagePath') || '';
      // Default: show as tiny placeholder dot
      n.style({ width: 12, height: 12, opacity: 0.35, 'font-size': 0, 'border-width': 1, 'border-style': 'dashed', 'border-color': '#9ca3af' });
      n.data('label', '');
      if (!imagePath) return;
      const imgUrl = n.data('imageUrl') || resolveRefImageUrl(imagePath);
      if (!imgUrl) return;
      tasks.push(() => fetch(imgUrl, { method: 'HEAD' }).then(r => {
        if (r.ok) {
          n.data('imageUrl', imgUrl);
          if (!n.data('_origLabel')) n.data('_origLabel', nodeType === 'asset_first_frame' ? '首帧' : '尾帧');
          n.data('label', '✓ ' + n.data('_origLabel'));
          n.style({ width: 50, height: 50, opacity: 1, 'font-size': 10, 'border-width': 3, 'border-style': 'solid', 'border-color': '#22c55e' });
        }
      }).catch(() => {}));
    } else if (nodeType === 'audio_bgm' || nodeType === 'audio_dialogue') {
      if (n.data('audioUrl')) return;  // already verified
      const audioPath = n.data('audioPath') || '';
      const raw = n.data('raw');
      const audioUrl = audioPath ? resolveRefImageUrl(audioPath)
        : (raw && raw.id ? resolveRefImageUrl(`assets/audio/${raw.id}.mp3`) : null);
      if (!audioUrl) return;
      tasks.push(() => fetch(audioUrl, { method: 'HEAD' }).then(r => {
        if (r.ok) {
          n.data('audioUrl', audioUrl);
          n.removeClass('img-pending img-generating');
          n.style('border-color', '#22c55e');
          n.style('border-width', 3);
          if (!n.data('_origLabel')) n.data('_origLabel', n.data('label'));
          n.data('label', '✓ ' + n.data('_origLabel'));
        } else {
          n.style('border-style', 'dashed');
          n.style('border-color', '#6b7280');
        }
      }).catch(() => {}));
    } else if (nodeType === 'asset_output') {
      // Output nodes: verify via clipPath
      const clipPath = n.data('clipPath') || '';
      if (!clipPath) return;
      const clipUrl = n.data('clipUrl') || resolveRefImageUrl(clipPath);
      if (!clipUrl) return;
      tasks.push(() => fetch(clipUrl, { method: 'HEAD' }).then(r => {
        if (!n.data('_origLabel')) n.data('_origLabel', n.data('label'));
        const origLabel = n.data('_origLabel');
        if (r.ok) {
          n.data('clipUrl', clipUrl);
          n.data('label', '\u2713 ' + origLabel);
          n.style('border-color', '#22c55e');
          n.style('border-width', 3);
        } else {
          n.removeData('clipUrl');
          n.data('label', '\u25cb ' + origLabel);
          n.style('border-style', 'dashed');
          n.style('border-color', '#6b7280');
        }
      }).catch(() => {}));
    }
  });
  _runWithConcurrency(tasks, 3);
}

// ---- Image Lightbox ----
function openImageLightbox(imgUrl) {
  let lb = document.getElementById('sg-lightbox');
  if (!lb) {
    lb = document.createElement('div');
    lb.id = 'sg-lightbox';
    lb.className = 'sg-lightbox';
    lb.innerHTML = `
      <div class="sg-lightbox-backdrop"></div>
      <img class="sg-lightbox-img" />
      <button class="sg-lightbox-close">&times;</button>
    `;
    document.body.appendChild(lb);
    lb.querySelector('.sg-lightbox-backdrop').addEventListener('click', closeImageLightbox);
    lb.querySelector('.sg-lightbox-close').addEventListener('click', closeImageLightbox);
    lb.addEventListener('keydown', e => { if (e.key === 'Escape') closeImageLightbox(); });
  }
  lb.querySelector('.sg-lightbox-img').src = imgUrl;
  lb.style.display = 'flex';
  lb.focus();
}

function closeImageLightbox() {
  const lb = document.getElementById('sg-lightbox');
  if (lb) lb.style.display = 'none';
}

// ---- Asset generation status tracking ----
// Node types that should have reference images or video clips
const ASSET_NODE_TYPES = new Set([
  'character', 'prop', 'location',
  'character_appearance', 'prop_state', 'location_state',
  'shot',
  'asset_ref_image', 'asset_first_frame', 'asset_tail_frame', 'asset_output',
]);

const generatingNodes = new Set(); // node IDs currently being generated

/** Mark nodes that should have assets but don't yet as "pending". */
function applyImageStatusClasses(cyInstance) {
  if (!cyInstance) return;
  cyInstance.batch(() => {
    cyInstance.nodes().forEach(n => {
      const nodeType = n.data('nodeType');
      if (!ASSET_NODE_TYPES.has(nodeType)) return;
      // Save original label once
      if (!n.data('_origLabel')) n.data('_origLabel', n.data('label'));
      const orig = n.data('_origLabel');
      // Already has asset
      const hasAsset = n.data('imageUrl') || n.data('clipUrl');
      if (hasAsset) {
        n.removeClass('img-pending img-generating img-generating-dim');
        n.data('label', '✓ ' + orig);
        return;
      }
      // Currently generating
      if (generatingNodes.has(n.id())) {
        n.removeClass('img-pending');
        n.addClass('img-generating');
        n.data('label', '⟳ ' + orig);
        return;
      }
      // No asset yet → pending
      n.removeClass('img-generating img-generating-dim');
      n.addClass('img-pending');
      n.data('label', '○ ' + orig);
    });
  });
}

/**
 * Run an array of async functions with limited concurrency.
 * Each task is a () => Promise. Returns when all are done.
 */
function _runWithConcurrency(tasks, limit) {
  if (!tasks.length) return Promise.resolve();
  limit = Math.min(limit, tasks.length);
  let idx = 0;
  let running = 0;
  return new Promise(resolve => {
    function next() {
      while (running < limit && idx < tasks.length) {
        const task = tasks[idx++];
        running++;
        task().finally(() => { running--; next(); });
      }
      if (running === 0) resolve();
    }
    next();
  });
}

/**
 * Check reference image file existence for entity/state nodes that have no imageUrl.
 * Uses the convention path "assets/images/{node_id}.png" to probe via HEAD request.
 * If the file exists on disk, set imageUrl so the node gets ✓ status.
 */
function checkRefImageStatus(cyInstance) {
  if (!cyInstance) return;
  const VERIFIABLE_TYPES = new Set([
    'character', 'prop', 'location',
    'character_appearance', 'prop_state', 'location_state',
    'asset_ref_image', 'asset_first_frame', 'asset_tail_frame',
  ]);
  const tasks = [];
  cyInstance.nodes().forEach(n => {
    const nodeType = n.data('nodeType');
    if (!VERIFIABLE_TYPES.has(nodeType)) return;
    if (n.data('imageUrl')) return;  // already verified

    // Determine URL to probe: prefer explicit imagePath, fallback to convention
    const imagePath = n.data('imagePath') || '';
    let imgUrl = imagePath ? resolveRefImageUrl(imagePath) : null;
    if (!imgUrl) {
      // Convention path only for entity/state types
      const nodeId = n.id();
      const conventionPath = 'assets/images/' + nodeId + '.png';
      imgUrl = resolveRefImageUrl(conventionPath);
    }
    if (!imgUrl) return;
    tasks.push(() => fetch(imgUrl, { method: 'HEAD' }).then(r => {
      if (r.ok) {
        n.data('imageUrl', imgUrl);
        n.removeClass('img-pending img-generating img-generating-dim');
        if (!n.data('_origLabel')) n.data('_origLabel', n.data('label'));
        n.data('label', '✓ ' + n.data('_origLabel'));
      }
    }).catch(() => {}));
  });
  _runWithConcurrency(tasks, 3);
}

/**
 * Check clip file existence for all shot nodes via HEAD requests.
 * If the clip file exists on disk, set clipUrl so the node gets ✓ status.
 * Limits concurrent requests to avoid browser freezing.
 */
function checkShotClipStatus(cyInstance) {
  if (!cyInstance) return;
  const tasks = [];
  cyInstance.nodes().forEach(n => {
    if (n.data('nodeType') !== 'shot') return;
    if (n.data('clipUrl')) return;  // already verified by HEAD

    // Prefer merged path (video+audio composite), fallback to raw video
    const mergedPath = n.data('mergedPath') || '';
    const rawVideoPath = n.data('rawVideoPath') || '';
    const clipPath = mergedPath || rawVideoPath || n.data('clipPath') || '';
    if (!clipPath) return;
    const clipUrl = resolveRefImageUrl(clipPath);
    if (!clipUrl) return;

    tasks.push(() => fetch(clipUrl, { method: 'HEAD' }).then(r => {
      if (r.ok) {
        n.data('clipUrl', clipUrl);
        if (n.data('raw')) {
          n.data('raw')._clip_url = clipUrl;
          n.data('raw')._merged_path = mergedPath;
          n.data('raw')._raw_video_path = rawVideoPath;
        }
        n.removeClass('img-pending img-generating');
        if (!n.data('_origLabel')) n.data('_origLabel', n.data('label'));
        const suffix = mergedPath ? '✓ ' : '◇ ';
        n.data('label', suffix + n.data('_origLabel'));
      }
    }).catch(() => {}));
  });
  _runWithConcurrency(tasks, 3);
}


/** Mark a node as "generating" — skip if the node already has a resolved asset. */
function markNodeGenerating(nodeId) {
  // Check if any cy instance already has this node with a resolved imageUrl/clipUrl.
  // If so, this is a duplicate generation call — don't regress the status.
  let alreadyResolved = false;
  _applyToAllCyInstances(inst => {
    const n = inst.getElementById(nodeId);
    if (n.length && (n.data('imageUrl') || n.data('clipUrl'))) {
      alreadyResolved = true;
    }
  });
  if (alreadyResolved) {
    console.log('[SG-img] markNodeGenerating: SKIPPED (already resolved):', nodeId);
    return;
  }
  generatingNodes.add(nodeId);
  console.log('[SG-img] markNodeGenerating:', nodeId, 'total:', generatingNodes.size);
  _applyToAllCyInstances(inst => {
    const n = inst.getElementById(nodeId);
    if (n.length) {
      n.removeClass('img-pending');
      n.addClass('img-generating');
      if (!n.data('_origLabel')) n.data('_origLabel', n.data('label'));
      n.data('label', '⟳ ' + n.data('_origLabel'));
    }
  });
}

/** Mark a node as "generated" (done). Also refresh imageUrl to bust browser cache. */
function markNodeGenerated(nodeId, outputPath) {
  generatingNodes.delete(nodeId);
  console.log('[SG-img] markNodeGenerated:', nodeId, 'remaining:', generatingNodes.size);
  // Resolve the new image URL and verify file existence before marking ✓
  const base = outputPath ? resolveRefImageUrl(outputPath) : null;
  if (!base) {
    // No output path — just clear generating state, mark pending
    _applyToAllCyInstances(inst => {
      const n = inst.getElementById(nodeId);
      if (n.length) {
        n.removeClass('img-generating');
        n.addClass('img-pending');
        if (!n.data('_origLabel')) n.data('_origLabel', n.data('label'));
        n.data('label', '○ ' + n.data('_origLabel'));
      }
    });
    return;
  }
  const verifyUrl = base + '?t=' + Date.now();
  fetch(base, { method: 'HEAD' }).then(r => {
    _applyToAllCyInstances(inst => {
      const n = inst.getElementById(nodeId);
      if (!n.length) return;
      n.removeClass('img-pending img-generating');
      if (!n.data('_origLabel')) n.data('_origLabel', n.data('label'));
      if (r.ok) {
        n.data('label', '✓ ' + n.data('_origLabel'));
        n.data('imageUrl', verifyUrl);
      } else {
        n.addClass('img-pending');
        n.data('label', '○ ' + n.data('_origLabel'));
      }
    });
  }).catch(() => {
    _applyToAllCyInstances(inst => {
      const n = inst.getElementById(nodeId);
      if (n.length) {
        n.removeClass('img-generating');
        n.addClass('img-pending');
        if (!n.data('_origLabel')) n.data('_origLabel', n.data('label'));
        n.data('label', '○ ' + n.data('_origLabel'));
      }
    });
  });
}

/** Clear all generating states. */
function clearGeneratingState() {
  generatingNodes.clear();
  _applyToAllCyInstances(inst => {
    inst.nodes('.img-generating').removeClass('img-generating');
  });
}

/** Extract node ID from GenerateImage output_path (e.g. "assets/images/char_red.png" → "char_red"). */
function extractNodeIdFromImagePath(outputPath) {
  if (!outputPath) return null;
  const filename = outputPath.split('/').pop() || '';
  return filename.replace(/\.[^.]+$/, '') || null;
}

function _applyToAllCyInstances(fn) {
  if (cy) fn(cy);
  if (typeof sgOverlayCy !== 'undefined' && sgOverlayCy) fn(sgOverlayCy);
}

