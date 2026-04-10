// ==== Video Viewer: Final Video + Assets + Timeline ====

let vvProjectBase = null;   // project base path (no leading /)
let vvShots = null;         // shots.json
let vvGenStatus = null;     // generation-status.json
let vvMusicStatus = null;   // music-status.json
let vvFinalVideos = [];      // [{url, label, n}] all output/video_N.mp4
const VV_PX_PER_SEC = 12;

// --- Data Loading ---

async function vvLoadData() {
  if (!vvProjectBase) return;
  const base = vvProjectBase.startsWith('/') ? vvProjectBase.substring(1) : vvProjectBase;

  // Load JSON files in parallel
  const [shotsRes, genRes, musicRes] = await Promise.allSettled([
    fetch(`/read-json/${base}/shots.json`).then(r => r.ok ? r.json() : null),
    fetch(`/read-json/${base}/generation-status.json`).then(r => r.ok ? r.json() : null),
    fetch(`/read-json/${base}/music-status.json`).then(r => r.ok ? r.json() : null),
  ]);

  vvShots = shotsRes.status === 'fulfilled' ? shotsRes.value : null;
  vvGenStatus = genRes.status === 'fulfilled' ? genRes.value : null;
  vvMusicStatus = musicRes.status === 'fulfilled' ? musicRes.value : null;

  // Probe for all final videos
  vvFinalVideos = [];
  const pathBase = base;
  for (let n = 1; n <= 20; n++) {
    try {
      const r = await fetch(`/files/${pathBase}/output/video_${n}.mp4`, { method: 'HEAD' });
      if (r.ok) {
        vvFinalVideos.push({ url: `/files/${pathBase}/output/video_${n}.mp4`, filePath: `${pathBase}/output/video_${n}.mp4`, label: `video ${n}`, n });
      } else break;
    } catch { break; }
  }

  // Mark tab as having data
  const tabBtn = document.getElementById('sidebar-tab-vv');
  if (tabBtn) tabBtn.classList.add('has-data');

  vvRender();
}

// --- Helpers ---

function vvFmtTime(sec) {
  const m = Math.floor(sec / 60);
  const s = Math.floor(sec % 60);
  return `${m}:${s.toString().padStart(2, '0')}`;
}

function vvMediaUrl(relPath) {
  if (!relPath) return '';
  if (relPath.startsWith('http')) return relPath;
  const base = vvProjectBase.startsWith('/') ? vvProjectBase.substring(1) : vvProjectBase;
  const clean = relPath.startsWith('/') ? relPath.substring(1) : `${base}/${relPath}`;
  return `/files/${clean}`;
}

// --- Build shot map with timeline offsets ---

function vvBuildTimeline() {
  if (!vvShots || !vvShots.shot_order) return { shots: [], totalDur: 0 };
  const shotMap = {};
  (vvShots.shots || []).forEach(s => { shotMap[s.id] = s; });

  let offset = 0;
  const shots = vvShots.shot_order.map(id => {
    const s = shotMap[id] || {};
    const dur = s.duration_seconds || 0;
    const entry = {
      id,
      event_id: s.event_id || '',
      framing: s.framing || '',
      movement: s.movement || '',
      content: s.content || '',
      duration: dur,
      start: offset,
      end: offset + dur,
      transition_in: s.transition_in || 'cut',
      transition_out: s.transition_out || 'cut',
      narration: s.narration || '',
      genStatus: vvGenStatus && vvGenStatus.shots ? (() => {
        const gs = vvGenStatus.shots[id];
        if (gs && !gs.output_path && gs.steps && gs.steps.video) {
          gs.output_path = gs.steps.video.output_path;
        }
        return gs;
      })() : null,
    };
    offset += dur;
    return entry;
  });
  return { shots, totalDur: offset };
}

function vvBuildMusicSegments() {
  if (!vvMusicStatus) return [];
  // Support both "segments" and "themes + arrangement" formats
  if (vvMusicStatus.segments) {
    return Object.entries(vvMusicStatus.segments).map(([id, seg]) => ({
      id,
      description: seg.description || '',
      start: seg.start_offset || 0,
      end: (seg.start_offset || 0) + (seg.duration_seconds || 0),
      duration: seg.duration_seconds || 0,
      status: seg.status || 'unknown',
      output_path: seg.output_path || '',
      shot_ids: seg.shot_ids || [],
    }));
  }
  if (vvMusicStatus.arrangement && vvMusicStatus.themes) {
    return vvMusicStatus.arrangement.map((arr, i) => {
      const theme = vvMusicStatus.themes[arr.theme_id] || {};
      return {
        id: arr.theme_id + '_' + i,
        description: theme.description || arr.theme_id,
        start: arr.start || 0,
        end: arr.end || 0,
        duration: (arr.end || 0) - (arr.start || 0),
        status: theme.status || 'unknown',
        output_path: theme.output_path || '',
        shot_ids: [],
      };
    });
  }
  return [];
}

// --- Main Render ---

function vvRender() {
  const panel = document.getElementById('vv-story-panel');
  if (!panel) return;

  if (!vvShots && !vvFinalVideos.length) {
    panel.innerHTML = '<div style="color:var(--text-dim);font-size:12px;padding:16px;">No video data loaded yet.</div>';
    return;
  }

  const { shots, totalDur } = vvBuildTimeline();
  const musicSegs = vvBuildMusicSegments();

  let html = '';

  // === Section 1: Video Cards (each with player + timeline) ===
  if (vvFinalVideos.length) {
    for (let i = vvFinalVideos.length - 1; i >= 0; i--) {
      const v = vvFinalVideos[i];
      const isLatest = i === vvFinalVideos.length - 1;
      const cardId = `vv-card-${v.n}`;
      html += `<div class="vv-video-card ${isLatest ? 'vv-video-card-latest' : ''}" id="${cardId}">`;
      html += `<div class="vv-video-card-header">`;
      html += `<span class="vv-video-card-title">${v.label}${isLatest ? ' (latest)' : ''}</span>`;
      html += `<span class="vv-section-meta">${shots.length} shots &middot; ${vvFmtTime(totalDur)} &middot; ${musicSegs.length} audio segments</span>`;
      html += `<a class="vv-download-btn" href="/api/download/${v.filePath}?session_id=${typeof S !== 'undefined' ? S.sessionId || '' : ''}&user_id=${typeof currentUserId !== 'undefined' ? currentUserId || 'default' : 'default'}" title="Download">&#x2B07;</a>`;
      html += `</div>`;
      html += `<div class="vv-video-card-player">`;
      html += `<video src="${v.url}" controls preload="metadata" class="vv-final-video" data-card-id="${cardId}"></video>`;
      html += `</div>`;
      html += `<div class="vv-video-card-timeline">`;
      html += vvRenderTimeline(shots, musicSegs, totalDur, cardId);
      html += `</div>`;
      html += `</div>`;
    }
  } else {
    // No final videos yet — show timeline alone
    html += '<div class="vv-section">';
    html += `<div class="vv-section-title">Timeline <span class="vv-section-meta">${shots.length} shots &middot; ${vvFmtTime(totalDur)} &middot; ${musicSegs.length} audio segments</span></div>`;
    html += vvRenderTimeline(shots, musicSegs, totalDur, 'vv-card-none');
    html += '</div>';
  }

  // === Section 2: Assets Used ===
  html += '<div class="vv-section">';
  html += `<div class="vv-section-title">Assets</div>`;
  html += vvRenderAssets(shots, musicSegs);
  html += '</div>';

  panel.innerHTML = html;

  // Attach event handlers
  vvBindHandlers(panel, shots);
}

// --- Bind video + timeline interaction ---

function vvBindHandlers(panel, shots) {
  // Asset thumbnails → lightbox preview
  panel.querySelectorAll('.vv-shot-thumb[data-src]').forEach(el => {
    el.addEventListener('click', () => {
      if (el.dataset.src) vvPlayPreview(el.dataset.src);
    });
  });

  // Standalone timeline (no video card) → shot clip opens lightbox preview
  panel.querySelectorAll('.vv-section .vv-tl-clip[data-src]').forEach(el => {
    el.addEventListener('click', () => {
      if (el.dataset.src) vvPlayPreview(el.dataset.src);
    });
  });

  // For each video card: bind timeupdate → playhead, click timeline → seek
  panel.querySelectorAll('.vv-video-card').forEach(card => {
    const video = card.querySelector('video.vv-final-video');
    const playhead = card.querySelector('.vv-tl-playhead');
    if (!video || !playhead) return;

    // Compute playhead height dynamically based on actual track count
    const tracks = card.querySelectorAll('.vv-tl-track');
    // ruler height(20) + each track ~36px (32 min-height + 4 margin)
    const playheadHeight = 20 + tracks.length * 36;
    playhead.style.height = `${playheadHeight}px`;

    // Playhead follows video time
    video.addEventListener('timeupdate', () => {
      const px = video.currentTime * VV_PX_PER_SEC;
      playhead.style.left = `${px}px`;
      playhead.style.display = 'block';
    });

    // Click on timeline track bar → seek video
    card.querySelectorAll('.vv-tl-track-bar').forEach(bar => {
      bar.addEventListener('click', (e) => {
        const rect = bar.getBoundingClientRect();
        const x = e.clientX - rect.left;
        const time = x / VV_PX_PER_SEC;
        if (time >= 0 && time <= video.duration) {
          video.currentTime = time;
        }
      });
    });

    // Click on shot clip in card → seek video to shot start
    card.querySelectorAll('.vv-tl-clip[data-start]').forEach(clip => {
      clip.addEventListener('click', (e) => {
        e.stopPropagation(); // prevent track-bar click
        const start = parseFloat(clip.dataset.start);
        if (!isNaN(start) && start <= video.duration) {
          video.currentTime = start;
          if (video.paused) video.play();
        }
      });
    });
  });
}

// --- Timeline Visualization ---

function vvRenderTimeline(shots, musicSegs, totalDur, cardId) {
  if (!shots.length) return '<div class="vv-empty">No shots</div>';
  const pxPerSec = VV_PX_PER_SEC;

  let html = '<div class="vv-timeline-wrap">';

  // Time ruler
  html += `<div class="vv-tl-ruler" style="width:${totalDur * pxPerSec}px;">`;
  for (let t = 0; t <= totalDur; t += 5) {
    html += `<div class="vv-tl-tick" style="left:${t * pxPerSec}px;"><span>${vvFmtTime(t)}</span></div>`;
  }
  // Playhead (hidden by default, shown on video play)
  html += `<div class="vv-tl-playhead" style="display:none;left:0;"></div>`;
  html += '</div>';

  // Video track
  html += '<div class="vv-tl-track">';
  html += '<div class="vv-tl-track-label">Video</div>';
  html += `<div class="vv-tl-track-bar" style="width:${totalDur * pxPerSec}px;">`;
  // Group shots by event for coloring
  const eventColors = {};
  const palette = ['#4a7de0', '#e07a4a', '#4ae0a0', '#e04a7d', '#7d4ae0', '#e0c94a', '#4ac9e0', '#e04a4a'];
  let ci = 0;
  shots.forEach(s => {
    if (!eventColors[s.event_id]) {
      eventColors[s.event_id] = palette[ci % palette.length];
      ci++;
    }
  });

  shots.forEach((s, i) => {
    const left = s.start * pxPerSec;
    const width = Math.max(s.duration * pxPerSec - 1, 4);
    const color = eventColors[s.event_id];
    const statusCls = s.genStatus && s.genStatus.status === 'done' ? 'done' : s.genStatus && s.genStatus.status === 'failed' ? 'failed' : 'pending';
    // Transition indicator
    let transIcon = '';
    if (s.transition_in && s.transition_in !== 'cut') {
      transIcon = `<span class="vv-tl-trans vv-tl-trans-in" title="${s.transition_in}">&#9666;</span>`;
    }
    if (s.transition_out && s.transition_out !== 'cut') {
      transIcon += `<span class="vv-tl-trans vv-tl-trans-out" title="${s.transition_out}">&#9656;</span>`;
    }
    const shotFile = s.genStatus && s.genStatus.output_path ? vvMediaUrl(s.genStatus.output_path) : '';
    html += `<div class="vv-tl-clip ${statusCls}" style="left:${left}px;width:${width}px;background:${color};" title="${s.id}\n${s.content}\n${vvFmtTime(s.start)}–${vvFmtTime(s.end)} (${s.duration}s)\n${s.framing} / ${s.movement}" data-start="${s.start}"${shotFile ? ` data-src="${shotFile}"` : ''}>`;
    html += `<span class="vv-tl-clip-label">${s.id.replace(/^evt_/, '').replace(/_shot_/, ' #')}</span>`;
    html += transIcon;
    html += '</div>';
  });
  html += '</div></div>';

  // Audio/BGM track
  if (musicSegs.length) {
    html += '<div class="vv-tl-track">';
    html += '<div class="vv-tl-track-label">Audio</div>';
    html += `<div class="vv-tl-track-bar" style="width:${totalDur * pxPerSec}px;">`;
    musicSegs.forEach(seg => {
      const left = seg.start * pxPerSec;
      const width = Math.max(seg.duration * pxPerSec - 1, 4);
      const statusCls = seg.status === 'done' ? 'done' : seg.status === 'failed' ? 'failed' : 'pending';
      const audioUrl = seg.output_path ? vvMediaUrl(seg.output_path) : '';
      html += `<div class="vv-tl-clip vv-tl-audio ${statusCls}" style="left:${left}px;width:${width}px;" title="${seg.id}\n${seg.description}\n${vvFmtTime(seg.start)}–${vvFmtTime(seg.end)} (${seg.duration}s)" data-start="${seg.start}"${audioUrl ? ` data-audio="${audioUrl}"` : ''}>`;
      html += `<span class="vv-tl-clip-label">${seg.description || seg.id}</span>`;
      html += '</div>';
    });
    html += '</div></div>';
  }

  html += '</div>'; // .vv-timeline-wrap
  return html;
}

// --- Assets List ---

function vvRenderAssets(shots, musicSegs) {
  let html = '';

  // Video assets
  const videoAssets = shots.filter(s => s.genStatus && s.genStatus.status === 'done' && s.genStatus.output_path);
  const videoFailed = shots.filter(s => s.genStatus && s.genStatus.status === 'failed');

  html += '<div class="vv-asset-group">';
  html += `<div class="vv-asset-group-title">Video Clips <span class="vv-asset-count">${videoAssets.length} done${videoFailed.length ? ` / ${videoFailed.length} failed` : ''}</span></div>`;
  html += '<div class="vv-asset-grid">';
  videoAssets.forEach(s => {
    const url = vvMediaUrl(s.genStatus.output_path);
    html += `<div class="vv-asset-card vv-shot-thumb" data-src="${url}">`;
    html += `<div class="vv-asset-card-preview"><video src="${url}" preload="metadata" muted></video></div>`;
    html += `<div class="vv-asset-card-info">`;
    html += `<div class="vv-asset-card-name">${s.id}</div>`;
    html += `<div class="vv-asset-card-meta">${s.framing} &middot; ${s.duration}s &middot; ${s.movement}</div>`;
    html += `</div></div>`;
  });
  html += '</div></div>';

  // Audio assets
  const audioAssets = musicSegs.filter(s => s.status === 'done' && s.output_path);
  if (audioAssets.length) {
    html += '<div class="vv-asset-group">';
    html += `<div class="vv-asset-group-title">Audio Segments <span class="vv-asset-count">${audioAssets.length}</span></div>`;
    audioAssets.forEach(seg => {
      const url = vvMediaUrl(seg.output_path);
      html += `<div class="vv-asset-audio-row">`;
      html += `<div class="vv-asset-audio-info">`;
      html += `<span class="vv-asset-audio-name">${seg.id}</span>`;
      html += `<span class="vv-asset-audio-desc">${seg.description}</span>`;
      html += `<span class="vv-asset-audio-time">${vvFmtTime(seg.start)}–${vvFmtTime(seg.end)} (${seg.duration}s)</span>`;
      html += `</div>`;
      html += `<audio controls preload="none" src="${url}" style="height:28px;flex-shrink:0;"></audio>`;
      html += `</div>`;
    });
    html += '</div>';
  }

  return html;
}

// --- Video Preview Popup ---

function vvPlayPreview(src) {
  // Reuse lightbox if exists, else create
  let lb = document.getElementById('vv-lightbox');
  if (!lb) {
    lb = document.createElement('div');
    lb.id = 'vv-lightbox';
    lb.className = 'vv-lightbox';
    lb.innerHTML = '<video controls autoplay class="vv-lightbox-video"></video>';
    lb.addEventListener('click', e => {
      if (e.target === lb) { lb.style.display = 'none'; lb.querySelector('video').pause(); }
    });
    document.body.appendChild(lb);
  }
  const vid = lb.querySelector('video');
  vid.src = src;
  lb.style.display = 'flex';
}

// --- Auto-detect project path from other viewers ---

function vvDetectProject() {
  // Reuse path from director or screenplay viewer
  // Both currentDirectorPath and currentScreenplayPath are already directory paths (no filename)
  if (typeof currentDirectorPath !== 'undefined' && currentDirectorPath) {
    vvProjectBase = currentDirectorPath;
    return true;
  }
  if (typeof currentScreenplayPath !== 'undefined' && currentScreenplayPath) {
    vvProjectBase = currentScreenplayPath;
    return true;
  }
  return false;
}

// Called when sidebar switches to video tab
function vvOnTabActivate() {
  if (!vvProjectBase) vvDetectProject();
  if (vvProjectBase) vvLoadData();
  else {
    const panel = document.getElementById('vv-story-panel');
    if (panel) panel.innerHTML = '<div style="color:var(--text-dim);font-size:12px;padding:16px;">No project loaded. Open a project via Screenplay or Director tab first.</div>';
  }
}
