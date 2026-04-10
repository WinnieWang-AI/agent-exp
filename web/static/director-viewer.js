// ==== Director Viewer — rendering logic for director output in sidebar ====
// Loaded by index.html. Depends on sidebar DOM + toggle/detect functions defined inline in index.html.

// --- State ---
let currentDirectorPath = null;
let drEvents = null, drStates = null, drShots = null;
let drEntities = null;
let drEntityMap = {}; // id -> entity object (characters, locations, props)
let drMeta = null; // meta.json data
let drOutline = null; // outline.json data (act/scene structure)
let drGenStatus = null; // generation-status.json data
let drMusicStatus = null; // music-status.json data
let drMusicSegments = []; // parsed music segments for timeline display
let drCurrentView = 'overview'; // 'overview' | 'detail'
let drCurrentEventIdx = -1;
let drEventList = []; // flat list of events
let drEventNumMap = {}; // idx -> display number (1-based, consistent with act grouping)

// --- Helpers ---
function drEsc(s) {
  if (!s) return '';
  const d = document.createElement('div');
  d.textContent = s;
  return d.innerHTML;
}

function drName(id) {
  const e = drEntityMap[id];
  return e ? e.name : id;
}

function drGetMeta() {
  if (!drEvents && !drShots) return '';
  const parts = [];
  // Show video_info first (same format as screenplay tab)
  if (drMeta && drMeta.video_info) {
    const vi = drMeta.video_info;
    if (vi.aspect_ratio) parts.push(vi.aspect_ratio);
    if (vi.duration) parts.push(vi.duration);
    if (vi.language) parts.push(vi.language);
  }
  // Then director-specific stats
  if (drEventList.length) parts.push(drEventList.length + ' events');
  if (drShots && drShots.shots) parts.push(drShots.shots.length + ' shots');
  if (drShots && drShots.total_duration_seconds) parts.push(drShots.total_duration_seconds + 's');
  return parts.join(' \u00b7 ');
}

// --- Data Loading ---
async function drLoadData() {
  if (!currentDirectorPath) return;
  const base = currentDirectorPath;
  const jsonBase = base.startsWith('/') ? base.substring(1) : base;

  try {
    const [evtRes, stRes, shRes, entRes, musRes, metaRes, outRes, genRes] = await Promise.all([
      fetch(`/read-json/${jsonBase}/events.json`),
      fetch(`/read-json/${jsonBase}/states.json`),
      fetch(`/read-json/${jsonBase}/shots.json`),
      fetch(`/read-json/${jsonBase}/entities.json`),
      fetch(`/read-json/${jsonBase}/music-status.json`),
      fetch(`/read-json/${jsonBase}/meta.json`),
      fetch(`/read-json/${jsonBase}/outline.json`),
      fetch(`/read-json/${jsonBase}/generation-status.json`)
    ]);
    if (evtRes.ok) drEvents = await evtRes.json();
    if (stRes.ok) drStates = await stRes.json();
    if (shRes.ok) drShots = await shRes.json();
    if (entRes.ok) drEntities = await entRes.json();
    if (musRes.ok) drMusicStatus = await musRes.json(); else drMusicStatus = null;
    if (metaRes.ok) drMeta = await metaRes.json(); else drMeta = null;
    if (outRes.ok) drOutline = await outRes.json(); else drOutline = null;
    if (genRes.ok) drGenStatus = await genRes.json(); else drGenStatus = null;
  } catch (e) {
    console.warn('drLoadData fetch error:', e);
  }

  // Normalize generation-status: flatten plan/steps into top-level fields
  // so rendering code can use genInfo.mode, genInfo.reference_images, etc.
  if (drGenStatus && drGenStatus.shots) {
    const shotOrder = drShots?.shot_order || [];
    for (const [shotId, info] of Object.entries(drGenStatus.shots)) {
      const plan = info.plan || {};
      const steps = info.steps || {};
      info.mode = plan.video_mode;
      info.provider = plan.provider;
      info.reference_images = (plan.reference_images || []).map(refPath => {
        if (refPath === '__COMPOSITION__') {
          return steps.composition_image?.output_path || refPath;
        }
        if (refPath === '__TAIL_FRAME__') {
          const idx = shotOrder.indexOf(shotId);
          if (idx > 0) {
            const prevShot = drGenStatus.shots[shotOrder[idx - 1]];
            return prevShot?.steps?.tail_frame?.output_path || refPath;
          }
        }
        return refPath;
      });
      info.first_frame = steps.first_frame?.output_path;
      info.first_frame_prompt = steps.first_frame?.prompt;
    }
  }

  // Build music segments list for timeline display
  drMusicSegments = [];
  if (drMusicStatus && drMusicStatus.segments) {
    const pathBase = base.startsWith('/') ? base.substring(1) : base;
    for (const [segId, seg] of Object.entries(drMusicStatus.segments)) {
      drMusicSegments.push({
        id: segId,
        description: seg.description || '',
        status: seg.status,
        duration_seconds: seg.duration_seconds || 0,
        start_offset: seg.start_offset || 0,
        audioUrl: (seg.status === 'done' && seg.output_path) ? '/files/' + pathBase + '/' + seg.output_path : null
      });
    }
    drMusicSegments.sort((a, b) => a.start_offset - b.start_offset);
  }

  // Build entity map
  drEntityMap = {};
  if (drEntities) {
    for (const c of (drEntities.characters || [])) drEntityMap[c.id] = c;
    for (const l of (drEntities.locations || [])) drEntityMap[l.id] = l;
    for (const p of (drEntities.props || [])) drEntityMap[p.id] = p;
  }

  // Build flat event list
  drEventList = (drEvents && drEvents.events) ? drEvents.events : [];

  // Update meta in header if director tab is active
  if (typeof _activeSidebarTab !== 'undefined' && _activeSidebarTab === 'director') {
    const metaEl = document.getElementById('sp-sidebar-meta');
    if (metaEl) metaEl.textContent = drGetMeta();
  }

  // Mark director tab as having data
  const tabBtn = document.getElementById('sidebar-tab-dr');
  if (tabBtn) tabBtn.classList.add('has-data');

  drShowOverview();
}

// --- Overview (Event List) ---
function drShowOverview() {
  drCurrentView = 'overview';
  drCurrentEventIdx = -1;
  const panel = document.getElementById('dr-story-panel');
  if (!panel) return;

  if (typeof _sidebarUpdateNav === 'function') _sidebarUpdateNav();

  if (!drEventList.length) {
    panel.innerHTML = '<div style="color:var(--text-dim);font-size:12px;padding:16px;">No director data loaded yet.</div>';
    return;
  }

  let html = '';

  // Summary bar
  html += '<div class="dr-summary-bar">';
  html += `<div class="dr-summary-stat"><span class="dr-num">${drEventList.length}</span> events</div>`;
  if (drShots && drShots.shots) {
    html += `<div class="dr-summary-stat"><span class="dr-num">${drShots.shots.length}</span> shots</div>`;
  }
  if (drShots && drShots.total_duration_seconds) {
    html += `<div class="dr-summary-stat"><span class="dr-num">${drShots.total_duration_seconds}s</span> total</div>`;
  }
  html += '</div>';

  // BGM timeline
  if (drMusicSegments.length) {
    html += '<div class="dr-bgm-timeline">';
    html += '<div class="dr-section-label">BGM</div>';
    const totalDur = drShots && drShots.total_duration_seconds ? drShots.total_duration_seconds : 0;
    drMusicSegments.forEach(seg => {
      const startMin = Math.floor(seg.start_offset / 60);
      const startSec = seg.start_offset % 60;
      const endOffset = seg.start_offset + seg.duration_seconds;
      const endMin = Math.floor(endOffset / 60);
      const endSec = endOffset % 60;
      const timeRange = `${startMin}:${String(startSec).padStart(2,'0')} – ${endMin}:${String(endSec).padStart(2,'0')}`;
      const statusClass = seg.status === 'done' ? 'done' : 'failed';
      html += `<div class="dr-bgm-segment ${statusClass}">`;
      html += `<div class="dr-bgm-seg-header">`;
      html += `<span class="dr-bgm-seg-time">${timeRange}</span>`;
      html += `<span class="dr-bgm-seg-dur">${seg.duration_seconds}s</span>`;
      html += `</div>`;
      if (seg.description) html += `<div class="dr-bgm-seg-desc">${drEsc(seg.description)}</div>`;
      if (seg.audioUrl) {
        html += `<div class="dr-shot-audio-player"><audio controls preload="none" src="${seg.audioUrl}"></audio></div>`;
      }
      html += '</div>';
    });
    html += '</div>';
  }

  // State matrix (entity × event overview)
  // Build event numbering first (needed by matrix header)
  drEventNumMap = {};
  if (drOutline && drOutline.acts) {
    const sceneToEvts = {};
    drEventList.forEach((evt, idx) => {
      (evt.source_scenes || []).forEach(scId => {
        if (!sceneToEvts[scId]) sceneToEvts[scId] = [];
        sceneToEvts[scId].push({ evt, idx });
      });
    });
    let fi = 0;
    const seen = new Set();
    drOutline.acts.forEach(act => {
      (act.scenes || []).forEach(sc => {
        (sceneToEvts[sc.id] || []).forEach(({ evt, idx }) => {
          if (seen.has(evt.id)) return;
          seen.add(evt.id);
          fi++;
          drEventNumMap[idx] = fi;
        });
      });
    });
    drEventList.forEach((evt, idx) => {
      if (!seen.has(evt.id)) { fi++; drEventNumMap[idx] = fi; }
    });
  } else {
    drEventList.forEach((evt, idx) => { drEventNumMap[idx] = idx + 1; });
  }
  // Event blocks — grouped by act if outline available (reuse drEventNumMap computed above)
  if (drOutline && drOutline.acts) {
    const sceneToEvents = {};
    drEventList.forEach((evt, idx) => {
      (evt.source_scenes || []).forEach(scId => {
        if (!sceneToEvents[scId]) sceneToEvents[scId] = [];
        sceneToEvents[scId].push({ evt, idx });
      });
    });

    const renderedEventIds = new Set();
    drOutline.acts.forEach((act, ai) => {
      const actTitle = act.title || act.name || `Act ${ai + 1}`;
      html += '<div class="dr-act-block">';
      html += '<div class="dr-act-header">';
      html += '<span class="dr-act-toggle open">&#9654;</span>';
      html += `<span class="dr-act-title">${drEsc(actTitle)}</span>`;
      html += '</div>';
      html += '<div class="dr-act-events open">';

      (act.scenes || []).forEach(sc => {
        (sceneToEvents[sc.id] || []).forEach(({ evt, idx }) => {
          if (renderedEventIds.has(evt.id)) return;
          renderedEventIds.add(evt.id);
          html += drRenderEventBlock(evt, idx, drEventNumMap[idx]);
        });
      });

      html += '</div></div>';
    });

    drEventList.forEach((evt, idx) => {
      if (!renderedEventIds.has(evt.id)) {
        html += drRenderEventBlock(evt, idx, drEventNumMap[idx]);
      }
    });
  } else {
    drEventList.forEach((evt, idx) => {
      html += drRenderEventBlock(evt, idx, drEventNumMap[idx]);
    });
  }

  panel.innerHTML = html;

  // Bind toggles
  panel.querySelectorAll('.dr-evt-header').forEach(hdr => {
    hdr.addEventListener('click', (e) => {
      // Don't toggle if clicking the detail button
      if (e.target.closest('.dr-evt-detail-btn')) return;
      const toggle = hdr.querySelector('.dr-evt-toggle');
      const body = hdr.nextElementSibling;
      if (toggle) toggle.classList.toggle('open');
      if (body) body.classList.toggle('open');
    });
  });

  // Bind act toggles
  panel.querySelectorAll('.dr-act-header').forEach(hdr => {
    hdr.addEventListener('click', () => {
      const toggle = hdr.querySelector('.dr-act-toggle');
      const body = hdr.nextElementSibling;
      if (toggle) toggle.classList.toggle('open');
      if (body) body.classList.toggle('open');
    });
  });

  // Bind detail buttons
  panel.querySelectorAll('.dr-evt-detail-btn').forEach(btn => {
    btn.addEventListener('click', (e) => {
      e.stopPropagation();
      const idx = parseInt(btn.dataset.idx);
      if (!isNaN(idx)) drShowEvent(idx);
    });
  });

  // Bind ref image clicks (state matrix thumbnails)
  panel.querySelectorAll('.ref-img-thumb').forEach(img => {
    img.addEventListener('click', (e) => {
      e.stopPropagation();
      if (typeof openLightbox === 'function') openLightbox(img.dataset.fullSrc || img.src);
    });
  });
}

function drRenderEventBlock(evt, idx, num) {
  const shotsForEvt = drShots && drShots.shots ? drShots.shots.filter(s => s.event_id === evt.id) : [];
  const shotCount = shotsForEvt.length;
  const totalDur = shotsForEvt.reduce((sum, s) => sum + (s.duration_seconds || 0), 0);

  let html = '<div class="dr-evt-block">';
  // Header
  html += '<div class="dr-evt-header">';
  html += `<span class="dr-evt-num">${num}</span>`;
  html += '<span class="dr-evt-toggle">\u25b6</span>';
  html += `<span class="dr-evt-title">${drEsc(evt.title || evt.id)}</span>`;
  html += '<div class="dr-evt-tags">';
  if (evt.location) html += `<span class="sp-tag loc">${drEsc(drName(evt.location))}</span>`;
  if (evt.time_of_day) html += `<span class="sp-tag time">${drEsc(evt.time_of_day)}</span>`;
  if (shotCount) html += `<span class="sp-tag chr">${shotCount} shots \u00b7 ${totalDur}s</span>`;
  html += '</div>';
  html += `<button class="sp-nav-btn dr-evt-detail-btn" data-idx="${idx}" title="View detail">\u2192</button>`;
  html += '</div>';

  // Body (collapsed by default)
  html += '<div class="dr-evt-body">';

  // Description
  if (evt.description) {
    html += `<div class="dr-evt-desc">${drEsc(evt.description)}</div>`;
  }

  // Characters & Props
  if (evt.characters && evt.characters.length) {
    html += '<div style="margin-bottom:4px;">';
    evt.characters.forEach(c => { html += `<span class="dr-chip char">${drEsc(drName(c))}</span>`; });
    html += '</div>';
  }
  if (evt.props && evt.props.length) {
    html += '<div style="margin-bottom:4px;">';
    evt.props.forEach(p => { html += `<span class="dr-chip prop">${drEsc(drName(p))}</span>`; });
    html += '</div>';
  }

  // Interactions
  if (evt.interactions && evt.interactions.length) {
    html += '<div class="dr-section-label">Interactions</div>';
    evt.interactions.forEach(inter => {
      const between = (inter.between || []).map(drName).join(' \u2194 ');
      html += `<div class="dr-interaction"><strong>${drEsc(between)}</strong>: ${drEsc(inter.style)}</div>`;
    });
  }

  // State changes
  if (evt.state_changes && evt.state_changes.length) {
    html += '<div class="dr-section-label">State Changes</div>';
    evt.state_changes.forEach(sc => {
      html += '<div class="dr-state-change">';
      html += `<span class="entity">${drEsc(drName(sc.entity))}</span>`;
      html += `<span class="aspect">${drEsc(sc.aspect)}</span>`;
      html += `<span class="detail">${drEsc(sc.detail)}</span>`;
      html += '</div>';
    });
  }

  // Dialogues
  if (evt.dialogues && evt.dialogues.length) {
    html += '<div class="dr-section-label">Dialogues</div>';
    evt.dialogues.forEach(d => {
      html += '<div class="dr-dialogue">';
      html += `<div class="speaker">${drEsc(drName(d.speaker))}`;
      if (d.tone) html += `<span class="tone">(${drEsc(d.tone)})</span>`;
      html += '</div>';
      html += `<div class="text">${drEsc(d.text)}</div>`;
      html += '</div>';
    });
  }

  // Shots preview (compact)
  if (shotsForEvt.length) {
    html += '<div class="dr-section-label">Shots</div>';
    shotsForEvt.forEach(shot => {
      html += drRenderShotCard(shot);
    });
  }

  html += '</div>'; // dr-evt-body
  html += '</div>'; // dr-evt-block
  return html;
}

function drRenderShotCard(shot) {
  let html = '<div class="dr-shot-card">';
  // Header line
  html += '<div class="dr-shot-header">';
  html += `<span class="dr-shot-id">#${drEsc(shot.order || '')}</span>`;
  const camParts = [shot.framing, shot.angle, shot.movement].filter(Boolean);
  html += `<span class="dr-shot-cam">${drEsc(camParts.join(' / '))}</span>`;
  if (shot.duration_seconds) html += `<span class="dr-shot-dur">${shot.duration_seconds}s</span>`;
  html += '</div>';
  // Content
  if (shot.content) {
    html += `<div class="dr-shot-content">${drEsc(shot.content)}</div>`;
  }
  // Narration
  if (shot.narration) {
    html += `<div class="dr-shot-audio"><span>\ud83c\udfa4 ${drEsc(shot.narration)}</span></div>`;
  }
  html += '</div>';
  return html;
}

// --- Event Detail View ---
function drShowEvent(idx) {
  if (idx < 0 || idx >= drEventList.length) return;
  drCurrentView = 'detail';
  drCurrentEventIdx = idx;

  if (typeof _sidebarUpdateNav === 'function') _sidebarUpdateNav();
  _drUpdateNavButtons();

  const evt = drEventList[idx];
  const panel = document.getElementById('dr-story-panel');
  if (!panel) return;

  const shotsForEvt = drShots && drShots.shots ? drShots.shots.filter(s => s.event_id === evt.id) : [];

  let html = '<div class="sp-detail">';
  const displayNum = drEventNumMap[idx] || (idx + 1);
  html += `<div class="dr-detail-title">${displayNum}. ${drEsc(evt.title || evt.id)}</div>`;
  if (evt.description) html += `<div class="dr-detail-desc">${drEsc(evt.description)}</div>`;

  // Meta
  html += '<div class="dr-detail-meta">';
  if (evt.location) {
    html += `<span class="sp-tag loc">${drEsc(drName(evt.location))}</span>`;
  }
  if (evt.area) {
    const loc = drEntityMap[evt.location];
    const areaObj = loc && loc.areas ? loc.areas.find(a => a.id === evt.area) : null;
    html += `<span class="sp-tag loc">${drEsc(areaObj ? areaObj.name : evt.area)}</span>`;
  }
  if (evt.time_of_day) html += `<span class="sp-tag time">${drEsc(evt.time_of_day)}</span>`;
  if (evt.mood) html += `<span class="sp-tag mood">${drEsc(evt.mood)}</span>`;
  html += '</div>';

  // Characters
  if (evt.characters && evt.characters.length) {
    html += '<div class="sp-entity-section-bar">Characters</div>';
    html += '<div class="dr-entity-list">';
    evt.characters.forEach(cid => {
      html += _drRenderEntityCard(cid, evt.id, 'char');
    });
    html += '</div>';
  }

  // Props
  if (evt.props && evt.props.length) {
    html += '<div class="sp-entity-section-bar">Props</div>';
    html += '<div class="dr-entity-list">';
    evt.props.forEach(pid => {
      html += _drRenderEntityCard(pid, evt.id, 'prop');
    });
    html += '</div>';
  }

  // Location
  if (evt.location) {
    const locId = evt.location;
    const locStates = _drGetActiveStates(locId, evt.id);
    if (locStates.length || (drEntityMap[locId] && drEntityMap[locId].reference_image)) {
      html += '<div class="sp-entity-section-bar">Location</div>';
      html += '<div class="dr-entity-list">';
      html += _drRenderEntityCard(locId, evt.id, 'loc');
      html += '</div>';
    }
  }

  // Interactions
  if (evt.interactions && evt.interactions.length) {
    html += '<div class="sp-entity-section-bar">Interactions</div>';
    evt.interactions.forEach(inter => {
      const between = (inter.between || []).map(drName).join(' \u2194 ');
      html += `<div class="dr-interaction"><strong>${drEsc(between)}</strong>: ${drEsc(inter.style)}</div>`;
    });
  }

  // State Changes
  if (evt.state_changes && evt.state_changes.length) {
    html += '<div class="sp-entity-section-bar">State Changes</div>';
    evt.state_changes.forEach(sc => {
      html += '<div class="dr-state-change">';
      html += `<span class="entity">${drEsc(drName(sc.entity))}</span>`;
      html += `<span class="aspect">${drEsc(sc.aspect)}</span>`;
      html += `<span class="detail">${drEsc(sc.detail)}</span>`;
      html += '</div>';
    });
  }

  // Dialogues
  if (evt.dialogues && evt.dialogues.length) {
    html += '<div class="sp-entity-section-bar">Dialogues</div>';
    evt.dialogues.forEach(d => {
      html += '<div class="dr-dialogue">';
      html += `<div class="speaker">${drEsc(drName(d.speaker))}`;
      if (d.tone) html += `<span class="tone">(${drEsc(d.tone)})</span>`;
      html += '</div>';
      html += `<div class="text">${drEsc(d.text)}</div>`;
      html += '</div>';
    });
  }

  // Shots (full detail)
  if (shotsForEvt.length) {
    html += '<div class="sp-entity-section-bar">Shots</div>';
    shotsForEvt.forEach(shot => {
      html += drRenderShotCardFull(shot);
    });
  }

  html += '</div>';
  panel.innerHTML = html;
  panel.scrollTop = 0;

  // Bind ref image clicks via delegation
  panel.querySelectorAll('.ref-img-thumb').forEach(img => {
    img.addEventListener('click', (e) => {
      e.stopPropagation();
      openLightbox(img.dataset.fullSrc || img.src);
    });
  });

  // Hide video elements that fail to load (file not yet generated)
  panel.querySelectorAll('.dr-shot-video').forEach(vid => {
    vid.addEventListener('error', () => { vid.style.display = 'none'; });
  });
}

function drRenderShotCardFull(shot) {
  let html = '<div class="dr-shot-card">';
  html += '<div class="dr-shot-header">';
  html += `<span class="dr-shot-id">${drEsc(shot.id)}</span>`;
  if (shot.duration_seconds) html += `<span class="dr-shot-dur">${shot.duration_seconds}s</span>`;
  html += '</div>';

  // Camera info
  const camParts = [];
  if (shot.framing) camParts.push(shot.framing);
  if (shot.angle) camParts.push(shot.angle);
  if (shot.movement) camParts.push(shot.movement);
  if (camParts.length) {
    html += `<div style="font-size:10px;color:var(--accent-blue);margin-bottom:4px;">\ud83c\udfa5 ${drEsc(camParts.join(' \u00b7 '))}</div>`;
  }

  // Transitions
  const transParts = [];
  if (shot.transition_in) transParts.push('in: ' + shot.transition_in);
  if (shot.transition_out) transParts.push('out: ' + shot.transition_out);
  if (transParts.length) {
    html += `<div style="font-size:10px;color:var(--text-dim);margin-bottom:4px;">\u21c4 ${drEsc(transParts.join(' | '))}</div>`;
  }

  // Focus
  if (shot.focus_on && shot.focus_on.length) {
    html += `<div style="font-size:10px;color:var(--text-dim);margin-bottom:4px;">\ud83c\udfaf ${drEsc(shot.focus_on.map(drName).join(', '))}</div>`;
  }

  // Content
  if (shot.content) {
    html += `<div class="dr-shot-content">${drEsc(shot.content)}</div>`;
  }

  // Generation info from generation-status.json
  const genInfo = drGenStatus && drGenStatus.shots ? drGenStatus.shots[shot.id] : null;
  if (genInfo) {
    // Mode badge
    if (genInfo.mode) {
      const modeLabels = {
        'reference_to_video': 'Ref\u2192Video',
        'image_to_video': 'Img\u2192Video',
        'text_to_video': 'Text\u2192Video'
      };
      const modeLabel = modeLabels[genInfo.mode] || genInfo.mode;
      html += `<div class="dr-shot-gen-mode"><span class="dr-gen-mode-badge">${drEsc(modeLabel)}</span>`;
      if (genInfo.model) html += `<span class="dr-gen-model">${drEsc(genInfo.model)}</span>`;
      if (genInfo.provider) html += `<span class="dr-gen-model">${drEsc(genInfo.provider)}</span>`;
      html += '</div>';
    }

    // Reference images used for generation
    if (genInfo.reference_images && genInfo.reference_images.length) {
      html += '<div class="dr-shot-ref-images"><span class="dr-shot-ref-label">Ref:</span>';
      genInfo.reference_images.forEach(refPath => {
        const url = _drFileUrl(refPath);
        html += `<img src="${url}" class="ref-img-thumb dr-shot-ref-thumb" data-full-src="${url}">`;
      });
      html += '</div>';
    }

    // First frame image
    if (genInfo.first_frame) {
      const ffUrl = _drFileUrl(genInfo.first_frame);
      html += '<div class="dr-shot-ref-images"><span class="dr-shot-ref-label">First frame:</span>';
      html += `<img src="${ffUrl}" class="ref-img-thumb dr-shot-ref-thumb" data-full-src="${ffUrl}">`;
      html += '</div>';
      // First frame prompt (collapsible)
      if (genInfo.first_frame_prompt) {
        html += `<div class="dr-shot-prompt-wrap"><span class="dr-shot-prompt-toggle" onclick="this.parentElement.classList.toggle('open')">First frame prompt &#9654;</span>`;
        html += `<div class="dr-shot-prompt-text">${drEsc(genInfo.first_frame_prompt)}</div></div>`;
      }
    }

    // Reasoning (collapsible)
    if (genInfo.reasoning) {
      html += `<div class="dr-shot-prompt-wrap"><span class="dr-shot-prompt-toggle" onclick="this.parentElement.classList.toggle('open')">Reasoning &#9654;</span>`;
      html += `<div class="dr-shot-prompt-text">${drEsc(genInfo.reasoning)}</div></div>`;
    }

    // Video generation prompt (collapsible)
    if (genInfo.prompt) {
      html += `<div class="dr-shot-prompt-wrap"><span class="dr-shot-prompt-toggle" onclick="this.parentElement.classList.toggle('open')">Video prompt &#9654;</span>`;
      html += `<div class="dr-shot-prompt-text">${drEsc(genInfo.prompt)}</div></div>`;
    }
  }

  // Video preview (output_path may be at top level or in steps.video)
  const genOutputPath = genInfo ? (genInfo.output_path || (genInfo.steps && genInfo.steps.video && genInfo.steps.video.output_path)) : null;
  const videoPath = genOutputPath ? _drFileUrl(genOutputPath) : null;
  if (videoPath) {
    html += `<video src="${videoPath}" class="dr-shot-video" controls preload="metadata"></video>`;
  } else if (currentDirectorPath) {
    const vidBase = (currentDirectorPath + '/assets/shots/' + shot.id + '.mp4').replace(/^\//, '');
    html += `<video src="/files/${vidBase}" class="dr-shot-video" controls preload="metadata"></video>`;
  }

  // Narration
  if (shot.narration) {
    html += `<div class="dr-shot-audio"><span>\ud83c\udfa4 ${drEsc(shot.narration)}</span></div>`;
  }

  html += '</div>';
  return html;
}

// --- Entity Card (consolidated ref image + states) ---
function _drFileUrl(path) {
  if (!path) return '';
  if (path.startsWith('http')) return path;
  const clean = path.replace(/^\//, '');
  // If path is relative (no project base prefix), prepend project base
  if (currentDirectorPath && !clean.startsWith(currentDirectorPath.replace(/^\//, ''))) {
    const base = currentDirectorPath.replace(/^\//, '');
    return `/files/${base}/${clean}`;
  }
  return `/files/${clean}`;
}

function _drRenderEntityCard(entityId, eventId, type) {
  const ent = drEntityMap[entityId];
  const name = ent ? ent.name : entityId;
  const states = _drGetActiveStates(entityId, eventId);

  let html = '<div class="dr-entity-card">';
  // Row: ref image + name + state chips
  html += '<div class="dr-entity-card-row">';
  if (ent && ent.reference_image) {
    const imgUrl = _drFileUrl(ent.reference_image);
    html += `<img src="${imgUrl}" class="ref-img-thumb dr-entity-card-img" data-full-src="${imgUrl}" alt="${drEsc(name)}">`;
  }
  html += `<div class="dr-entity-card-info">`;
  html += `<span class="dr-chip ${type}">${drEsc(name)}</span>`;
  // Compact state summary
  if (states.length) {
    const skipKeys = new Set(['id', 'entity', 'phase', 'reference_image']);
    states.forEach(st => {
      const label = st.phase || st.id;
      html += `<div class="dr-entity-state-row">`;
      if (st.reference_image) {
        const stImgUrl = _drFileUrl(st.reference_image);
        html += `<img src="${stImgUrl}" class="ref-img-thumb dr-entity-state-img" data-full-src="${stImgUrl}">`;
      }
      html += `<span class="dr-entity-state-label">${drEsc(label)}</span>`;
      // Show key state details inline
      const details = [];
      for (const [k, v] of Object.entries(st)) {
        if (skipKeys.has(k) || v === null || v === undefined || v === '') continue;
        details.push(`${k}: ${v}`);
      }
      if (details.length) {
        html += `<span class="dr-entity-state-detail">${drEsc(details.join(' | '))}</span>`;
      }
      html += '</div>';
    });
  }
  html += '</div></div>';
  html += '</div>';
  return html;
}

// --- State Helpers ---
function _drGetActiveStates(entityId, eventId) {
  if (!drStates || !drStates.active_during) return [];
  const results = [];
  const ad = drStates.active_during;

  // Check character_appearance
  if (ad.character_appearance) {
    for (const [stateId, evtIds] of Object.entries(ad.character_appearance)) {
      if (evtIds.includes(eventId)) {
        const state = (drStates.character_appearances || []).find(s => s.id === stateId && s.entity === entityId);
        if (state) results.push(state);
      }
    }
  }
  // Check character_mind
  if (ad.character_mind) {
    for (const [stateId, evtIds] of Object.entries(ad.character_mind)) {
      if (evtIds.includes(eventId)) {
        const state = (drStates.character_minds || []).find(s => s.id === stateId && s.entity === entityId);
        if (state) results.push(state);
      }
    }
  }
  // Check prop_state
  if (ad.prop_state) {
    for (const [stateId, evtIds] of Object.entries(ad.prop_state)) {
      if (evtIds.includes(eventId)) {
        const state = (drStates.prop_states || []).find(s => s.id === stateId && s.entity === entityId);
        if (state) results.push(state);
      }
    }
  }
  // Check location_state
  if (ad.location_state) {
    for (const [stateId, evtIds] of Object.entries(ad.location_state)) {
      if (evtIds.includes(eventId)) {
        const state = (drStates.location_states || []).find(s => s.id === stateId && s.entity === entityId);
        if (state) results.push(state);
      }
    }
  }
  return results;
}

// --- Navigation ---
function drNavigateEvent(delta) {
  const newIdx = drCurrentEventIdx + delta;
  if (newIdx >= 0 && newIdx < drEventList.length) {
    drShowEvent(newIdx);
  }
}

function _drUpdateNavButtons() {
  const prev = document.getElementById('sp-btn-prev');
  const next = document.getElementById('sp-btn-next');
  if (prev) prev.disabled = drCurrentEventIdx <= 0;
  if (next) next.disabled = drCurrentEventIdx >= drEventList.length - 1;
}
