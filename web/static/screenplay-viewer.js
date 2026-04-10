// ==== Screenplay Viewer — rendering logic for the sidebar ====
// Loaded by index.html. Depends on sidebar DOM + toggle/detect functions defined inline in index.html.

// --- State ---
let currentScreenplayPath = null;
let spMeta = null, spEntities = null, spOutline = null;
let spActCache = {};
let spAllScenes = []; // flat list of {actIdx, sceneIdx, scene}
let spEntityMap = {}; // id -> entity object (characters, locations, props)
let spCurrentView = 'outline'; // 'outline' | 'scene'
let spCurrentSceneIdx = -1;
let spActiveSubTab = 'story'; // 'story' | 'entities'

// --- Helpers ---
function spTimeLabel(t) {
  const map = { morning: '早晨', midday: '正午', afternoon: '下午', evening: '傍晚', night: '夜晚', dawn: '黎明', dusk: '黄昏' };
  return map[t] || t || '';
}

function spEsc(s) {
  if (!s) return '';
  const d = document.createElement('div');
  d.textContent = s;
  return d.innerHTML;
}

// --- Data Loading ---
async function spLoadData() {
  if (!currentScreenplayPath) return;
  const base = currentScreenplayPath;

  try {
    // Use /read-json/ endpoint — strip leading slash for URL path segment
    const jsonBase = base.startsWith('/') ? base.substring(1) : base;
    const [metaRes, entRes, outRes] = await Promise.all([
      fetch(`/read-json/${jsonBase}/meta.json`),
      fetch(`/read-json/${jsonBase}/entities.json`),
      fetch(`/read-json/${jsonBase}/outline.json`)
    ]);

    if (metaRes.ok) spMeta = await metaRes.json();
    if (entRes.ok) spEntities = await entRes.json();
    if (outRes.ok) spOutline = await outRes.json();
  } catch (e) {
    console.warn('spLoadData fetch error:', e);
  }

  // Build entity map
  spEntityMap = {};
  if (spEntities) {
    for (const c of (spEntities.characters || [])) spEntityMap[c.id] = { ...c, _type: 'character' };
    for (const l of (spEntities.locations || [])) spEntityMap[l.id] = { ...l, _type: 'location' };
    for (const p of (spEntities.props || [])) spEntityMap[p.id] = { ...p, _type: 'prop' };
  }

  // Build flat scene list
  spAllScenes = [];
  if (spOutline && spOutline.acts) {
    spOutline.acts.forEach((act, ai) => {
      (act.scenes || []).forEach((sc, si) => {
        spAllScenes.push({ actIdx: ai, sceneIdx: si, scene: sc });
      });
    });
  }

  // Clear act cache
  spActCache = {};

  // Update header
  if (spMeta) {
    const titleEl = document.getElementById('sp-sidebar-title');
    const metaEl = document.getElementById('sp-sidebar-meta');
    if (titleEl) titleEl.textContent = spMeta.title || 'Screenplay';
    if (metaEl) {
      const vi = spMeta.video_info || {};
      const parts = [vi.aspect_ratio, vi.duration, vi.language].filter(Boolean);
      metaEl.textContent = parts.join(' · ');
    }
  }

  spShowOutline();
}

// --- Outline View ---
function spShowOutline() {
  spCurrentView = 'outline';
  spCurrentSceneIdx = -1;
  const panel = document.getElementById('sp-story-panel');
  if (!panel) return;

  // Hide scene nav buttons, show nothing for back
  _spNavVisibility(false);

  if (!spOutline || !spOutline.acts) {
    panel.innerHTML = '<div style="color:var(--text-dim);font-size:12px;padding:16px;">No screenplay data loaded yet.</div>';
    return;
  }

  // Count entities
  const charCount = spEntities && spEntities.characters ? spEntities.characters.length : 0;
  const locCount = spEntities && spEntities.locations ? spEntities.locations.length : 0;
  const propCount = spEntities && spEntities.props ? spEntities.props.length : 0;
  const entityTotal = charCount + locCount + propCount;

  let html = '';
  // Sub-tabs
  html += `<div class="sp-sub-tabs">`;
  html += `<button class="sp-sub-tab ${spActiveSubTab === 'story' ? 'active' : ''}" data-subtab="story">Story</button>`;
  html += `<button class="sp-sub-tab ${spActiveSubTab === 'entities' ? 'active' : ''}" data-subtab="entities">Entities<span class="sp-sub-tab-count">${entityTotal}</span></button>`;
  html += `</div>`;
  // Story sub-panel
  html += `<div class="sp-sub-panel ${spActiveSubTab === 'story' ? 'active' : ''}" id="sp-sub-story">`;
  html += spRenderOutlineActs();
  html += `</div>`;
  // Entities sub-panel
  html += `<div class="sp-sub-panel ${spActiveSubTab === 'entities' ? 'active' : ''}" id="sp-sub-entities">`;
  html += spRenderEntitiesPanel();
  html += `</div>`;

  panel.innerHTML = html;

  // Bind sub-tab switching
  panel.querySelectorAll('.sp-sub-tab').forEach(btn => {
    btn.addEventListener('click', () => {
      spActiveSubTab = btn.dataset.subtab;
      panel.querySelectorAll('.sp-sub-tab').forEach(b => b.classList.toggle('active', b.dataset.subtab === spActiveSubTab));
      panel.querySelectorAll('.sp-sub-panel').forEach(p => p.classList.toggle('active', p.id === `sp-sub-${spActiveSubTab}`));
    });
  });

  // Bind act toggle
  panel.querySelectorAll('.sp-act-header').forEach(hdr => {
    hdr.addEventListener('click', () => {
      const toggle = hdr.querySelector('.sp-act-toggle');
      const scenes = hdr.nextElementSibling;
      if (toggle) toggle.classList.toggle('open');
      if (scenes) scenes.classList.toggle('open');
    });
  });

  // Bind scene click
  panel.querySelectorAll('.sp-scene-card').forEach(card => {
    card.addEventListener('click', () => {
      const idx = parseInt(card.dataset.flatIdx);
      if (!isNaN(idx)) spOpenScene(idx);
    });
  });

  // Bind entity card toggle
  spBindEntityToggle(panel);

  // Bind entity scene-appearance clicks
  panel.querySelectorAll('.sp-entity-appear-item').forEach(item => {
    item.addEventListener('click', () => {
      const idx = parseInt(item.dataset.flatIdx);
      if (!isNaN(idx)) spOpenScene(idx);
    });
  });
}

function spRenderOutlineActs() {
  let html = '';
  let flatIdx = 0;

  spOutline.acts.forEach((act, ai) => {
    const actId = act.id || `act_${ai + 1}`;
    const actTitle = act.title || act.name || `Act ${ai + 1}`;
    const actSummary = act.summary || '';

    html += `<div class="sp-act-block">`;
    html += `<div class="sp-act-header">`;
    html += `<span class="sp-act-toggle open">&#9654;</span>`;
    html += `<span class="sp-act-title">${spEsc(actTitle)}</span>`;
    if (actSummary) html += `<span class="sp-act-summary" title="${spEsc(actSummary)}">${spEsc(actSummary)}</span>`;
    html += `</div>`;
    html += `<div class="sp-act-scenes open">`;

    (act.scenes || []).forEach((sc, si) => {
      const scTitle = sc.title || sc.name || sc.id;
      const scSummary = sc.summary || sc.logline || '';
      const loc = spEntityMap[sc.location] || spEntityMap[sc.location_id];
      const locName = loc ? loc.name : (sc.location || sc.location_id || '');
      const charCount = (sc.characters || []).length;
      const time = sc.time_of_day || '';
      const mood = sc.mood || '';

      html += `<div class="sp-scene-card" data-flat-idx="${flatIdx}">`;
      html += `<div class="sp-scene-num">${flatIdx + 1}</div>`;
      html += `<div class="sp-scene-body">`;
      html += `<div class="sp-scene-title">${spEsc(scTitle)}</div>`;
      if (scSummary) html += `<div class="sp-scene-summary" title="${spEsc(scSummary)}">${spEsc(scSummary)}</div>`;
      html += `<div class="sp-scene-tags">`;
      if (locName) html += `<span class="sp-tag loc">${spEsc(locName)}</span>`;
      if (charCount) html += `<span class="sp-tag chr">${charCount} chars</span>`;
      if (time) html += `<span class="sp-tag time">${spEsc(spTimeLabel(time))}</span>`;
      if (mood) html += `<span class="sp-tag mood">${spEsc(mood)}</span>`;
      html += `</div></div></div>`;
      flatIdx++;
    });

    html += `</div></div>`;
  });

  return html;
}

function spRenderEntitiesPanel() {
  if (!spEntities) return '<div style="color:var(--text-dim);font-size:12px;">No entity data.</div>';

  // Build entity -> scene appearances map
  const appearMap = {}; // entityId -> [{flatIdx, sceneTitle}]
  spAllScenes.forEach((item, flatIdx) => {
    const sc = item.scene;
    const ids = [...(sc.characters || []), ...(sc.props || [])];
    // location
    if (sc.location) ids.push(sc.location);
    if (sc.location_id) ids.push(sc.location_id);
    for (const id of ids) {
      if (!appearMap[id]) appearMap[id] = [];
      appearMap[id].push({ flatIdx, title: sc.title || sc.name || sc.id });
    }
  });

  let html = '';
  const sections = [
    { key: 'characters', label: 'Characters', icon: 'character' },
    { key: 'locations', label: 'Locations', icon: 'location' },
    { key: 'props', label: 'Props', icon: 'prop' }
  ];

  for (const sec of sections) {
    const items = spEntities[sec.key];
    if (!items || !items.length) continue;
    html += `<div class="sp-entity-section-bar">${sec.label} (${items.length})</div>`;
    for (const item of items) {
      html += spRenderEntityCardWithAppearances(item.id, spEntityMap[item.id], appearMap[item.id] || []);
    }
  }

  return html;
}

function spRenderEntityCardWithAppearances(id, entity, appearances) {
  // Render the standard entity card but inject scene appearances into the body
  const type = entity ? entity._type : 'character';
  const name = entity ? entity.name : id;
  const iconLetter = name.charAt(0);
  const tags = entity ? (entity.tags || entity.visual_distinctions || []) : [];

  let html = `<div class="sp-entity-card">`;
  html += `<div class="sp-entity-hdr" data-entity-id="${spEsc(id)}">`;
  if (entity && entity.reference_image) {
    const imgUrl = '/files/' + entity.reference_image.replace(/^\//, '');
    html += `<img src="${imgUrl}" class="ref-img-thumb" style="width:36px;height:36px;" data-full-src="${imgUrl}">`;
  } else {
    html += `<div class="sp-entity-icon ${type}">${spEsc(iconLetter)}</div>`;
  }
  html += `<span class="sp-entity-name">${spEsc(name)}</span>`;
  if (tags.length > 0) html += `<span class="sp-entity-tags">${tags.map(t => spEsc(t)).join(', ')}</span>`;
  if (appearances.length > 0) html += `<span class="sp-entity-tags" style="margin-left:auto;">${appearances.length} scenes</span>`;
  html += `</div>`;

  html += `<div class="sp-entity-body">`;

  // Fixed traits
  if (entity && entity.fixed_traits) {
    for (const [k, v] of Object.entries(entity.fixed_traits)) {
      html += `<div class="sp-entity-trait"><span class="sp-entity-trait-k">${spEsc(k)}</span><span class="sp-entity-trait-v">${spEsc(String(v))}</span></div>`;
    }
  }
  if (entity && !entity.fixed_traits) {
    if (entity.appearance) html += `<div class="sp-entity-trait"><span class="sp-entity-trait-k">appearance</span><span class="sp-entity-trait-v">${spEsc(entity.appearance)}</span></div>`;
    if (entity.wardrobe) html += `<div class="sp-entity-trait"><span class="sp-entity-trait-k">wardrobe</span><span class="sp-entity-trait-v">${spEsc(entity.wardrobe)}</span></div>`;
    if (entity.traits) html += `<div class="sp-entity-trait"><span class="sp-entity-trait-k">traits</span><span class="sp-entity-trait-v">${spEsc(entity.traits.join(', '))}</span></div>`;
  }
  if (entity && entity.description && type !== 'character') {
    html += `<div class="sp-entity-trait"><span class="sp-entity-trait-k">desc</span><span class="sp-entity-trait-v">${spEsc(entity.description)}</span></div>`;
  }

  // Relationships
  if (entity && entity.relationships && Object.keys(entity.relationships).length > 0) {
    html += `<div class="sp-entity-section">Relationships</div>`;
    for (const [targetId, rels] of Object.entries(entity.relationships)) {
      const target = spEntityMap[targetId];
      const targetName = target ? target.name : targetId;
      const relArr = Array.isArray(rels) ? rels : [rels];
      for (const rel of relArr) {
        const kind = typeof rel === 'string' ? rel : rel.kind;
        let scope = '';
        if (rel.from || rel.until) {
          const parts = [];
          if (rel.from) parts.push(`from ${rel.from}`);
          if (rel.until) parts.push(`until ${rel.until}`);
          scope = ` (${parts.join(', ')})`;
        }
        html += `<div class="sp-entity-rel">`;
        html += `<span class="sp-entity-rel-target">${spEsc(targetName)}</span>`;
        html += `<span style="color:var(--text-dim)">— ${spEsc(kind)}${spEsc(scope)}</span>`;
        html += `</div>`;
      }
    }
  }

  // Scene appearances
  if (appearances.length > 0) {
    html += `<div class="sp-entity-appearances">`;
    html += `<div class="sp-entity-section">Appears in</div>`;
    for (const ap of appearances) {
      html += `<div class="sp-entity-appear-item" data-flat-idx="${ap.flatIdx}">`;
      html += `<span class="sp-entity-appear-num">${ap.flatIdx + 1}</span>`;
      html += `<span>${spEsc(ap.title)}</span>`;
      html += `</div>`;
    }
    html += `</div>`;
  }

  html += `</div></div>`;
  return html;
}

// --- Scene Detail View ---
async function spOpenScene(flatIdx) {
  if (flatIdx < 0 || flatIdx >= spAllScenes.length) return;
  spCurrentView = 'scene';
  spCurrentSceneIdx = flatIdx;

  const { actIdx, scene } = spAllScenes[flatIdx];
  const act = spOutline.acts[actIdx];
  const actId = act.id || `act_${actIdx + 1}`;

  // Load act detail if not cached
  if (!spActCache[actId]) {
    try {
      // Try act-{N}.json (1-based)
      const jsonBase = currentScreenplayPath.startsWith('/') ? currentScreenplayPath.substring(1) : currentScreenplayPath;
      const res = await fetch(`/read-json/${jsonBase}/act-${actIdx + 1}.json`);
      if (res.ok) spActCache[actId] = await res.json();
    } catch (e) {
      console.warn('Failed to load act file:', e);
    }
  }

  // Find detailed scene data from act file
  let detailedScene = null;
  const actData = spActCache[actId];
  if (actData && actData.scenes) {
    const sceneId = scene.id;
    detailedScene = actData.scenes.find(s => s.id === sceneId);
  }

  _spNavVisibility(true);
  _spUpdateNavButtons();

  const panel = document.getElementById('sp-story-panel');
  if (!panel) return;
  panel.innerHTML = spRenderScene(scene, detailedScene, flatIdx);
  spBindEntityToggle(panel);
  panel.scrollTop = 0;
}

function spRenderScene(outlineScene, detailedScene, flatIdx) {
  const sc = detailedScene || outlineScene;
  const title = sc.title || sc.name || sc.id;
  const desc = sc.description || outlineScene.summary || outlineScene.logline || '';
  const loc = spEntityMap[sc.location] || spEntityMap[sc.location_id] || spEntityMap[outlineScene.location] || spEntityMap[outlineScene.location_id];
  const locName = loc ? loc.name : (sc.location || sc.location_id || outlineScene.location || outlineScene.location_id || '');
  const time = sc.time_of_day || outlineScene.time_of_day || '';
  const mood = sc.mood || outlineScene.mood || '';
  const area = sc.area || outlineScene.area || '';

  let html = `<div class="sp-detail">`;
  html += `<div class="sp-detail-title">${flatIdx + 1}. ${spEsc(title)}</div>`;
  if (desc) html += `<div class="sp-detail-desc">${spEsc(desc)}</div>`;

  // Meta tags
  html += `<div class="sp-detail-meta">`;
  if (locName) html += `<span class="sp-tag loc">${spEsc(locName)}</span>`;
  if (area) {
    const areaObj = loc && loc.areas ? loc.areas.find(a => a.id === area) : null;
    html += `<span class="sp-tag loc">${spEsc(areaObj ? areaObj.name : area)}</span>`;
  }
  if (time) html += `<span class="sp-tag time">${spEsc(spTimeLabel(time))}</span>`;
  if (mood) html += `<span class="sp-tag mood">${spEsc(mood)}</span>`;
  html += `</div>`;

  // Location state
  if (detailedScene && detailedScene.location_state) {
    const ls = detailedScene.location_state;
    html += `<div class="sp-entity-section-bar">Location State</div>`;
    html += `<div style="font-size:11px;color:var(--text-mid);margin-bottom:8px;">`;
    for (const [k, v] of Object.entries(ls)) {
      if (v) html += `<div><span style="color:var(--text-dim)">${spEsc(k)}:</span> ${spEsc(v)}</div>`;
    }
    html += `</div>`;
  }

  // Beats
  if (detailedScene && detailedScene.beats && detailedScene.beats.length > 0) {
    html += `<div class="sp-entity-section-bar">Beats</div>`;
    for (const beat of detailedScene.beats) {
      html += spRenderBeat(beat);
    }
  }

  // Character states
  if (detailedScene && detailedScene.character_states) {
    html += `<div class="sp-entity-section-bar">Characters in Scene</div>`;
    const charIds = detailedScene.characters_present || outlineScene.characters || [];
    for (const cid of charIds) {
      const entity = spEntityMap[cid];
      const state = detailedScene.character_states[cid];
      html += spRenderEntityCard(cid, entity, state);
    }
  } else if (outlineScene.characters && outlineScene.characters.length > 0) {
    html += `<div class="sp-entity-section-bar">Characters</div>`;
    for (const cid of outlineScene.characters) {
      const entity = spEntityMap[cid];
      html += spRenderEntityCard(cid, entity, null);
    }
  }

  // Props
  if (detailedScene && detailedScene.props_in_scene && detailedScene.props_in_scene.length > 0) {
    html += `<div class="sp-entity-section-bar">Props</div>`;
    for (const pid of detailedScene.props_in_scene) {
      const entity = spEntityMap[pid];
      const state = detailedScene.prop_states ? detailedScene.prop_states[pid] : null;
      html += spRenderEntityCard(pid, entity, state);
    }
  } else if (outlineScene.props && outlineScene.props.length > 0) {
    html += `<div class="sp-entity-section-bar">Props</div>`;
    for (const pid of outlineScene.props) {
      const entity = spEntityMap[pid];
      html += spRenderEntityCard(pid, entity, null);
    }
  }

  html += `</div>`;
  return html;
}

function spRenderBeat(beat) {
  let html = `<div class="sp-beat">`;
  if (beat.type === 'action') {
    html += `<div class="sp-beat-action">${spEsc(beat.text)}</div>`;
  } else if (beat.type === 'dialogue') {
    if (beat.speaker === 'narrator') {
      html += `<div class="sp-beat-narrator">${spEsc(beat.text)}</div>`;
    } else {
      const entity = spEntityMap[beat.speaker];
      const name = entity ? entity.name : beat.speaker;
      html += `<div class="sp-beat-dialogue">`;
      html += `<div class="sp-beat-speaker">${spEsc(name)}`;
      if (beat.tone) html += `<span class="sp-tone">(${spEsc(beat.tone)})</span>`;
      html += `</div>`;
      html += `<div class="sp-beat-text">${spEsc(beat.text)}</div>`;
      html += `</div>`;
    }
  }
  html += `</div>`;
  return html;
}

// --- Entity Cards ---
function spRenderEntityCard(id, entity, state) {
  const type = entity ? entity._type : 'character';
  const name = entity ? entity.name : id;
  const iconLetter = name.charAt(0);
  const tags = entity ? (entity.tags || entity.visual_distinctions || []) : [];

  let html = `<div class="sp-entity-card">`;
  html += `<div class="sp-entity-hdr" data-entity-id="${spEsc(id)}">`;
  if (entity && entity.reference_image) {
    const imgUrl = '/files/' + entity.reference_image.replace(/^\//, '');
    html += `<img src="${imgUrl}" class="ref-img-thumb" style="width:36px;height:36px;" data-full-src="${imgUrl}">`;
  } else {
    html += `<div class="sp-entity-icon ${type}">${spEsc(iconLetter)}</div>`;
  }
  html += `<span class="sp-entity-name">${spEsc(name)}</span>`;
  if (tags.length > 0) html += `<span class="sp-entity-tags">${tags.map(t => spEsc(t)).join(', ')}</span>`;
  html += `</div>`;

  html += `<div class="sp-entity-body">`;

  // Fixed traits
  if (entity && entity.fixed_traits) {
    for (const [k, v] of Object.entries(entity.fixed_traits)) {
      html += `<div class="sp-entity-trait"><span class="sp-entity-trait-k">${spEsc(k)}</span><span class="sp-entity-trait-v">${spEsc(String(v))}</span></div>`;
    }
  }

  // Legacy fields (for old schema compatibility: wardrobe, appearance, traits)
  if (entity && !entity.fixed_traits) {
    if (entity.appearance) html += `<div class="sp-entity-trait"><span class="sp-entity-trait-k">appearance</span><span class="sp-entity-trait-v">${spEsc(entity.appearance)}</span></div>`;
    if (entity.wardrobe) html += `<div class="sp-entity-trait"><span class="sp-entity-trait-k">wardrobe</span><span class="sp-entity-trait-v">${spEsc(entity.wardrobe)}</span></div>`;
    if (entity.traits) html += `<div class="sp-entity-trait"><span class="sp-entity-trait-k">traits</span><span class="sp-entity-trait-v">${spEsc(entity.traits.join(', '))}</span></div>`;
  }

  // Description (for locations, props)
  if (entity && entity.description && type !== 'character') {
    html += `<div class="sp-entity-trait"><span class="sp-entity-trait-k">desc</span><span class="sp-entity-trait-v">${spEsc(entity.description)}</span></div>`;
  }

  // State
  if (state) {
    html += `<div class="sp-entity-section">State</div>`;
    if (typeof state === 'object') {
      for (const [k, v] of Object.entries(state)) {
        if (v !== null && v !== undefined) {
          html += `<div class="sp-entity-state"><span style="color:var(--text-dim)">${spEsc(k)}:</span> ${spEsc(String(v))}</div>`;
        }
      }
    } else {
      html += `<div class="sp-entity-state">${spEsc(String(state))}</div>`;
    }
  }

  // Relationships
  if (entity && entity.relationships && Object.keys(entity.relationships).length > 0) {
    html += `<div class="sp-entity-section">Relationships</div>`;
    for (const [targetId, rels] of Object.entries(entity.relationships)) {
      const target = spEntityMap[targetId];
      const targetName = target ? target.name : targetId;
      const relArr = Array.isArray(rels) ? rels : [rels];
      for (const rel of relArr) {
        const kind = typeof rel === 'string' ? rel : rel.kind;
        let scope = '';
        if (rel.from || rel.until) {
          const parts = [];
          if (rel.from) parts.push(`from ${rel.from}`);
          if (rel.until) parts.push(`until ${rel.until}`);
          scope = ` (${parts.join(', ')})`;
        }
        html += `<div class="sp-entity-rel">`;
        html += `<span class="sp-entity-rel-target">${spEsc(targetName)}</span>`;
        html += `<span style="color:var(--text-dim)">— ${spEsc(kind)}${spEsc(scope)}</span>`;
        html += `</div>`;
      }
    }
  }

  html += `</div></div>`;
  return html;
}

function spBindEntityToggle(container) {
  container.querySelectorAll('.sp-entity-hdr').forEach(hdr => {
    hdr.addEventListener('click', (e) => {
      // If clicking a ref image thumbnail, open lightbox instead of toggling
      if (e.target.classList.contains('ref-img-thumb')) {
        e.stopPropagation();
        openLightbox(e.target.dataset.fullSrc || e.target.src);
        return;
      }
      const body = hdr.nextElementSibling;
      if (body) body.classList.toggle('open');
    });
  });
}

// --- Navigation ---
function spNavigateScene(delta) {
  const newIdx = spCurrentSceneIdx + delta;
  if (newIdx >= 0 && newIdx < spAllScenes.length) {
    spOpenScene(newIdx);
  }
}

function _spNavVisibility(showSceneNav) {
  // Delegate to shared nav updater which also binds onclick handlers
  if (typeof _sidebarUpdateNav === 'function') {
    _sidebarUpdateNav();
  } else {
    // Fallback if index.html hasn't loaded yet
    const back = document.getElementById('sp-btn-back');
    const prev = document.getElementById('sp-btn-prev');
    const next = document.getElementById('sp-btn-next');
    if (back) back.style.display = showSceneNav ? '' : 'none';
    if (prev) prev.style.display = showSceneNav ? '' : 'none';
    if (next) next.style.display = showSceneNav ? '' : 'none';
  }
}

function _spUpdateNavButtons() {
  const prev = document.getElementById('sp-btn-prev');
  const next = document.getElementById('sp-btn-next');
  if (prev) prev.disabled = spCurrentSceneIdx <= 0;
  if (next) next.disabled = spCurrentSceneIdx >= spAllScenes.length - 1;
}
