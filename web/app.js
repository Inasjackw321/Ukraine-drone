/* ─────────────────────────────────────────────────────────────────────────────
   Ukraine Drone Map — frontend
   Connects via WebSocket, renders Leaflet map, animates trajectories.
───────────────────────────────────────────────────────────────────────────── */

// ── Config ─────────────────────────────────────────────────────────────────
const EXPIRE_MS       = 45 * 60 * 1000;   // 45 min threat lifetime
const ANIM_STEP_MS    = 60;               // trajectory animation tick
const ANIM_DURATION   = 18_000;          // ms to traverse full trajectory
const MAX_TRAIL_PTS   = 80;
const WS_RECONNECT_MS = 3000;

// ── Threat meta ────────────────────────────────────────────────────────────
const THREAT_META = {
  shahed:    { icon: '🔺', color: '#ff6600', label: 'Shahed' },
  geran:     { icon: '🔺', color: '#ff4400', label: 'Geranium' },
  drone:     { icon: '🚁', color: '#ffaa00', label: 'Drone' },
  kalibr:    { icon: '🚀', color: '#ff2200', label: 'Kalibr' },
  kinzhal:   { icon: '⚡', color: '#cc00ff', label: 'Kinzhal' },
  iskander:  { icon: '💥', color: '#ff0066', label: 'Iskander' },
  x101:      { icon: '🚀', color: '#ff3300', label: 'X-101' },
  x22:       { icon: '🚀', color: '#dd2200', label: 'X-22' },
  x59:       { icon: '🚀', color: '#ee1100', label: 'X-59' },
  oniks:     { icon: '🚀', color: '#ff0044', label: 'Oniks' },
  ballistic: { icon: '☄️', color: '#ff00aa', label: 'Ballistic' },
  missile:   { icon: '🚀', color: '#ff2200', label: 'Missile' },
  unknown:   { icon: '❓', color: '#888888', label: 'Unknown' },
};

const STATUS_ICON = {
  moving:    '🔴',
  alert:     '🟡',
  destroyed: '✅',
  launch:    '🔴',
  unknown:   '⚪',
};

// ── State ──────────────────────────────────────────────────────────────────
const threats    = new Map();   // id → { event, marker, path, antPath, animState }
let activeFilter = 'all';
let totalEvents  = 0;
let statsActive  = 0;
let statsDestroyed = 0;

// ── Map init ───────────────────────────────────────────────────────────────
const map = L.map('map', {
  center: [49.0, 31.5],
  zoom: 6,
  zoomControl: false,
  attributionControl: false,
});

L.control.zoom({ position: 'topright' }).addTo(map);

// Dark tile layer (CartoDB Dark Matter)
L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
  maxZoom: 18,
  subdomains: 'abcd',
}).addTo(map);

// Ukraine border highlight (simple GeoJSON rectangle approximation)
L.rectangle([[44.0, 22.0], [52.5, 40.5]], {
  color: '#1a8cff',
  weight: 1.5,
  fill: false,
  dashArray: '4 4',
  opacity: 0.35,
}).addTo(map);

// ── Layer groups ───────────────────────────────────────────────────────────
const markerLayer  = L.layerGroup().addTo(map);
const pathLayer    = L.layerGroup().addTo(map);
const trailLayer   = L.layerGroup().addTo(map);

// ── Helper: build Leaflet DivIcon ──────────────────────────────────────────
function makeIcon(threat, status) {
  const meta  = THREAT_META[threat] || THREAT_META.unknown;
  const pulse = (status === 'moving' || status === 'launch') ? 'marker-pulse' : '';
  const size  = status === 'kinzhal' ? 36 : 28;

  return L.divIcon({
    className: '',
    html: `
      <div class="threat-marker ${pulse}"
           style="width:${size}px;height:${size}px;
                  background:${meta.color}22;
                  color:${meta.color};
                  border-color:${meta.color}88;
                  font-size:${size * 0.6}px;
                  box-shadow:0 0 8px ${meta.color}66">
        ${meta.icon}
      </div>`,
    iconSize: [size, size],
    iconAnchor: [size / 2, size / 2],
    popupAnchor: [0, -size / 2],
  });
}

// ── Build popup HTML ───────────────────────────────────────────────────────
function buildPopup(evt) {
  const meta   = THREAT_META[evt.threat_type] || THREAT_META.unknown;
  const time   = new Date(evt.timestamp).toLocaleTimeString('uk-UA');
  const dirs   = evt.directions || {};
  const dirStr = [dirs.from && `From: ${dirs.from}`, dirs.to && `To: ${dirs.to}`]
    .filter(Boolean).join('  →  ');

  return `
    <div style="min-width:180px">
      <div style="font-weight:700;font-size:13px;color:${meta.color};margin-bottom:4px">
        ${meta.icon} ${meta.label} × ${evt.count}
      </div>
      <div style="color:#8b949e;font-size:10px;margin-bottom:6px">${time} · ${evt.channel}</div>
      ${evt.location_name ? `<div>📍 ${evt.location_name}</div>` : ''}
      ${dirStr ? `<div style="color:#8b949e;margin-top:4px">↗ ${dirStr}</div>` : ''}
      <div style="margin-top:6px;padding-top:6px;border-top:1px solid #1e2a38;font-size:10px;color:#8b949e">
        ${evt.text ? evt.text.substring(0, 140) + (evt.text.length > 140 ? '…' : '') : ''}
      </div>
    </div>`;
}

// ── Draw ant-path trajectory ───────────────────────────────────────────────
function drawTrajectory(evt) {
  const waypoints = (evt.waypoints || []).filter(w => w.lat && w.lon);
  if (waypoints.length < 2) return null;

  const meta  = THREAT_META[evt.threat_type] || THREAT_META.unknown;
  const latlngs = waypoints.map(w => [w.lat, w.lon]);

  // Animated ant-path
  const antPath = L.polyline.antPath(latlngs, {
    delay: 800,
    dashArray: [10, 20],
    weight: 2.5,
    color: meta.color,
    pulseColor: '#fff',
    paused: false,
    reverse: false,
    hardwareAccelerated: true,
  });
  antPath.addTo(pathLayer);

  // Static faint trail
  const trail = L.polyline(latlngs, {
    color: meta.color,
    weight: 1,
    opacity: 0.25,
    dashArray: '3 6',
  });
  trail.addTo(trailLayer);

  return { antPath, trail };
}

// ── Animate marker along waypoints ────────────────────────────────────────
function startAnimation(threatObj) {
  const { event: evt, marker } = threatObj;
  const waypoints = (evt.waypoints || []).filter(w => w.lat && w.lon);
  if (waypoints.length < 2 || evt.status === 'destroyed') return;

  const totalSegments = waypoints.length - 1;
  const segDuration   = ANIM_DURATION / totalSegments;

  function animateSegment(segIdx, startTime) {
    if (!threats.has(evt.id)) return; // threat removed
    const current = threats.get(evt.id);
    if (!current || current.animCancelled) return;

    const from = waypoints[segIdx];
    const to   = waypoints[segIdx + 1];
    const now  = performance.now();
    const t    = Math.min((now - startTime) / segDuration, 1);

    const lat = from.lat + (to.lat - from.lat) * easeInOut(t);
    const lon = from.lon + (to.lon - from.lon) * easeInOut(t);
    marker.setLatLng([lat, lon]);

    if (t < 1) {
      current.animFrame = requestAnimationFrame(() => animateSegment(segIdx, startTime));
    } else if (segIdx < totalSegments - 1) {
      animateSegment(segIdx + 1, performance.now());
    } else {
      // Loop back to start after pause
      setTimeout(() => {
        if (threats.has(evt.id)) {
          marker.setLatLng([waypoints[0].lat, waypoints[0].lon]);
          animateSegment(0, performance.now());
        }
      }, 4000);
    }
  }

  // Start from penultimate waypoint if status is "destroyed"
  if (evt.status === 'moving' || evt.status === 'launch') {
    animateSegment(0, performance.now());
  }
}

function easeInOut(t) {
  return t < 0.5 ? 2 * t * t : -1 + (4 - 2 * t) * t;
}

// ── Add / update a threat on the map ──────────────────────────────────────
function addThreat(evt) {
  if (!evt.lat || !evt.lon) return;

  // Already exists → update
  if (threats.has(evt.id)) {
    removeThreat(evt.id);
  }

  const marker = L.marker([evt.lat, evt.lon], {
    icon: makeIcon(evt.threat_type, evt.status),
    zIndexOffset: evt.status === 'moving' ? 1000 : 0,
  });

  marker.bindPopup(buildPopup(evt), { maxWidth: 280 });
  marker.on('click', () => showDetail(evt));
  marker.addTo(markerLayer);

  // Trajectory
  const pathObjs = drawTrajectory(evt);

  const threatObj = { event: evt, marker, ...pathObjs, animCancelled: false };
  threats.set(evt.id, threatObj);
  startAnimation(threatObj);

  // Auto-expire
  const ttl = EXPIRE_MS - (Date.now() - new Date(evt.timestamp).getTime());
  if (ttl > 0) {
    setTimeout(() => removeThreat(evt.id), ttl);
  } else {
    setTimeout(() => removeThreat(evt.id), 5000);
  }

  updateStats();
}

function removeThreat(id) {
  const t = threats.get(id);
  if (!t) return;
  t.animCancelled = true;
  if (t.animFrame) cancelAnimationFrame(t.animFrame);
  if (t.marker) markerLayer.removeLayer(t.marker);
  if (t.antPath) pathLayer.removeLayer(t.antPath);
  if (t.trail) trailLayer.removeLayer(t.trail);
  threats.delete(id);
  updateStats();
}

// ── Stats & feed ──────────────────────────────────────────────────────────
function updateStats() {
  let active = 0, destroyed = 0;
  for (const [, t] of threats) {
    if (t.event.status === 'destroyed') destroyed++;
    else active++;
  }
  document.getElementById('stat-total').textContent     = totalEvents;
  document.getElementById('stat-active').textContent    = active;
  document.getElementById('stat-destroyed').textContent = destroyed;
}

function addFeedItem(evt) {
  const meta     = THREAT_META[evt.threat_type] || THREAT_META.unknown;
  const time     = new Date(evt.timestamp).toLocaleTimeString('uk-UA', { hour: '2-digit', minute: '2-digit' });
  const statusCls = `status-${evt.status || 'unknown'}`;

  const item = document.createElement('div');
  item.className = 'feed-item';
  item.dataset.category = evt.threat_category || 'unknown';
  item.dataset.status   = evt.status || 'unknown';
  item.dataset.id       = evt.id;

  item.innerHTML = `
    <div class="feed-top">
      <span class="feed-icon">${meta.icon}</span>
      <span class="feed-threat" style="color:${meta.color}">${meta.label} × ${evt.count || 1}</span>
      <span class="status-badge ${statusCls}">${evt.status || '?'}</span>
      <span class="feed-time">${time}</span>
    </div>
    ${evt.location_name ? `<div class="feed-location">📍 ${evt.location_name}</div>` : ''}
    <div class="feed-text">${evt.text || ''}</div>
    <div class="feed-channel">${evt.channel || ''}</div>
  `;

  item.addEventListener('click', () => {
    if (evt.lat && evt.lon) {
      map.setView([evt.lat, evt.lon], 9, { animate: true });
      const t = threats.get(evt.id);
      if (t) t.marker.openPopup();
    }
    showDetail(evt);
  });

  applyFilter(item);

  const feed = document.getElementById('feed');
  feed.insertBefore(item, feed.firstChild);

  // Limit feed length
  while (feed.children.length > 120) {
    feed.removeChild(feed.lastChild);
  }
}

// ── Filters ────────────────────────────────────────────────────────────────
document.querySelectorAll('.filter-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    activeFilter = btn.dataset.filter;
    document.querySelectorAll('.feed-item').forEach(applyFilter);
  });
});

function applyFilter(item) {
  const cat    = item.dataset.category;
  const status = item.dataset.status;
  const show   =
    activeFilter === 'all' ||
    activeFilter === cat ||
    activeFilter === status;
  item.classList.toggle('filtered-out', !show);
}

// ── Detail panel ───────────────────────────────────────────────────────────
function showDetail(evt) {
  const meta = THREAT_META[evt.threat_type] || THREAT_META.unknown;
  const dirs = evt.directions || {};
  const locs = (evt.locations || []).map(l => l.name).join(', ');

  document.getElementById('detail-content').innerHTML = `
    <div style="font-size:16px;font-weight:700;color:${meta.color};margin-bottom:10px">
      ${meta.icon} ${meta.label}
    </div>
    <div class="detail-label">Status</div>
    <div class="detail-value">${STATUS_ICON[evt.status] || '⚪'} ${evt.status || 'unknown'}</div>

    <div class="detail-label">Count</div>
    <div class="detail-value">${evt.count || 1}</div>

    ${evt.location_name ? `<div class="detail-label">Location</div>
    <div class="detail-value">📍 ${evt.location_name}</div>` : ''}

    ${locs ? `<div class="detail-label">All Locations</div>
    <div class="detail-value">${locs}</div>` : ''}

    ${dirs.from ? `<div class="detail-label">Origin</div>
    <div class="detail-value">↗ ${dirs.from}</div>` : ''}

    ${dirs.to ? `<div class="detail-label">Heading</div>
    <div class="detail-value">🎯 ${dirs.to}</div>` : ''}

    <div class="detail-label">Channel</div>
    <div class="detail-value">${evt.channel || '—'}</div>

    <div class="detail-label">Time</div>
    <div class="detail-value">${new Date(evt.timestamp).toLocaleString('uk-UA')}</div>

    <div class="detail-text">${evt.text || ''}</div>
  `;
  document.getElementById('detail-panel').classList.remove('hidden');
}

function closeDetail() {
  document.getElementById('detail-panel').classList.add('hidden');
}

// ── WebSocket ──────────────────────────────────────────────────────────────
let ws = null;
let wsRetries = 0;

function connectWS() {
  const protocol = location.protocol === 'https:' ? 'wss' : 'ws';
  const wsUrl    = `${protocol}://${location.host}/ws`;

  setConnectionStatus('connecting');

  ws = new WebSocket(wsUrl);

  ws.onopen = () => {
    wsRetries = 0;
    setConnectionStatus('live');
  };

  ws.onmessage = ({ data }) => {
    let msg;
    try { msg = JSON.parse(data); } catch { return; }

    if (msg.type === 'event') {
      handleEvent(msg.data);
    } else if (msg.type === 'history') {
      // Reverse so newest ends up on top of feed
      const events = [...msg.data].reverse();
      events.forEach(handleEvent);
    }
  };

  ws.onclose = () => {
    setConnectionStatus('error');
    const delay = Math.min(WS_RECONNECT_MS * (wsRetries + 1), 15_000);
    wsRetries++;
    setTimeout(connectWS, delay);
  };

  ws.onerror = () => {
    ws.close();
  };
}

function handleEvent(evt) {
  totalEvents++;
  addThreat(evt);
  addFeedItem(evt);
  updateStats();
}

function setConnectionStatus(state) {
  const dot   = document.getElementById('ws-dot');
  const label = document.getElementById('ws-label');
  dot.className   = `dot dot-${state}`;
  label.textContent = { connecting: 'Connecting…', live: 'Live', error: 'Reconnecting…' }[state] || state;
}

// ── Boot ───────────────────────────────────────────────────────────────────
connectWS();

// Periodically clean up expired threats
setInterval(() => {
  const now = Date.now();
  for (const [id, t] of threats) {
    const age = now - new Date(t.event.timestamp).getTime();
    if (age > EXPIRE_MS + 5000) removeThreat(id);
  }
}, 60_000);
