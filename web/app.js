/* Ukraine Drone Map — frontend
   Directional SVG icons · Physics-accurate speeds · Trajectory extrapolation */

// ── Threat definitions ────────────────────────────────────────────────────
// speed_kmh used for extrapolation after last waypoint
const THREATS = {
  shahed:    { label: 'Shahed',    color: '#f97316', glow: '#f97316', speed: 150,  cat: 'drone'   },
  geran:     { label: 'Geranium',  color: '#f97316', glow: '#f97316', speed: 150,  cat: 'drone'   },
  drone:     { label: 'БПЛА',      color: '#60a5fa', glow: '#3b82f6', speed: 150,  cat: 'drone'   },
  kalibr:    { label: 'Kalibr',    color: '#ef4444', glow: '#dc2626', speed: 700,  cat: 'missile' },
  x101:      { label: 'X-101',     color: '#f87171', glow: '#ef4444', speed: 780,  cat: 'missile' },
  x59:       { label: 'X-59',      color: '#fb923c', glow: '#ea580c', speed: 900,  cat: 'missile' },
  x22:       { label: 'X-22',      color: '#f43f5e', glow: '#e11d48', speed: 1000, cat: 'missile' },
  oniks:     { label: 'Oniks',     color: '#e879f9', glow: '#c026d3', speed: 2500, cat: 'missile' },
  kinzhal:   { label: 'Kinzhal',   color: '#c084fc', glow: '#a855f7', speed: 3000, cat: 'missile' },
  iskander:  { label: 'Iskander',  color: '#fbbf24', glow: '#d97706', speed: 1500, cat: 'missile' },
  ballistic: { label: 'Ballistic', color: '#eab308', glow: '#ca8a04', speed: 1200, cat: 'missile' },
  missile:   { label: 'Missile',   color: '#ef4444', glow: '#dc2626', speed: 700,  cat: 'missile' },
  unknown:   { label: 'Unknown',   color: '#94a3b8', glow: '#64748b', speed: 300,  cat: 'unknown' },
  aviation:  { label: 'Aviation',  color: '#38bdf8', glow: '#0ea5e9', speed: 800,  cat: 'aviation' },
};

const STATUS_CLASS = {
  moving: 's-moving', destroyed: 's-destroyed',
  alert:  's-alert',  launch:    's-launch', unknown: 's-unknown',
};

// 1 degree latitude ≈ 111 km — used to convert km/h to deg/ms
const DEG_PER_KM = 1 / 111;

// Animation: time to traverse all known waypoints before extrapolating
const WAYPOINT_TRAVERSE_MS = 22_000;  // 22 seconds

// Threat expires after this long (disappears from map)
const EXPIRE_MS = 30 * 60 * 1000;

// ── Map ───────────────────────────────────────────────────────────────────
const map = L.map('map', {
  center: [49.0, 31.5], zoom: 6,
  zoomControl: false, attributionControl: false,
});
L.control.zoom({ position: 'topright' }).addTo(map);

// Tiles are proxied through localhost so they load inside pywebview without
// any CORS/CSP issues. The server fetches from CartoDB/OSM and caches them.
L.tileLayer('/tiles/{z}/{x}/{y}.png', {
  maxZoom: 18,
  crossOrigin: true,
  keepBuffer: 4,
}).addTo(map);

// Ukraine border outline
L.rectangle([[44.3, 22.1], [52.4, 40.2]], {
  color: '#2563eb', weight: 1.5, fill: false,
  dashArray: '6 5', opacity: 0.3,
}).addTo(map);

const layers = {
  trails:  L.layerGroup().addTo(map),
  paths:   L.layerGroup().addTo(map),
  markers: L.layerGroup().addTo(map),
};

// ── SVG icon factory ──────────────────────────────────────────────────────
// All icons are arrow shapes pointing "up" (north=0°), rotated via CSS.
// The outer ring color shows status; the inner fill shows threat type.

const SHAPES = {
  // drones: wide triangle
  drone:   'M8,1 L15,14 L8,11 L1,14 Z',
  shahed:  'M8,1 L15,14 L8,11 L1,14 Z',
  geran:   'M8,1 L15,14 L8,11 L1,14 Z',
  // cruise missiles: slim dart
  missile: 'M8,1 L13,15 L8,12 L3,15 Z',
  kalibr:  'M8,1 L13,15 L8,12 L3,15 Z',
  x101:    'M8,1 L13,15 L8,12 L3,15 Z',
  x59:     'M8,1 L13,15 L8,12 L3,15 Z',
  x22:     'M8,1 L13,15 L8,12 L3,15 Z',
  oniks:   'M8,1 L13,15 L8,12 L3,15 Z',
  // kinzhal: ultra-slim needle
  kinzhal: 'M8,0 L11,16 L8,13 L5,16 Z',
  // ballistic / iskander: teardrop
  iskander:  'M8,1 C12,1 14,7 14,12 C14,15 11,16 8,16 C5,16 2,15 2,12 C2,7 4,1 8,1 Z',
  ballistic: 'M8,1 C12,1 14,7 14,12 C14,15 11,16 8,16 C5,16 2,15 2,12 C2,7 4,1 8,1 Z',
  unknown:  'M8,2 L14,14 L8,11 L2,14 Z',
  // top-down aircraft silhouette
  aviation: 'M8,0 L10,5 L16,6 L16,8 L10,8 L11,16 L8,14 L5,16 L6,8 L0,8 L0,6 L6,5 Z',
};

const RING_COLORS = {
  moving: '#f97316', launch: '#ef4444',
  alert:  '#facc15', destroyed: '#22c55e', unknown: '#64748b',
};

function makeIcon(type, status, bearingDeg) {
  const def    = THREATS[type] || THREATS.unknown;
  const shape  = SHAPES[type]  || SHAPES.unknown;
  const ring   = RING_COLORS[status] || RING_COLORS.unknown;
  const isActive = status === 'moving' || status === 'launch' || status === 'alert';
  const pulse  = isActive ? 'style="animation:iconPulse 1.8s infinite"' : '';
  const size   = type === 'kinzhal' ? 40 : (def.cat === 'missile' ? 34 : 36);

  const svg = `
    <svg width="${size}" height="${size}" viewBox="0 0 16 16"
         style="transform:rotate(${bearingDeg}deg);filter:drop-shadow(0 0 4px ${def.glow}88)"
         ${pulse}>
      <path d="${shape}" fill="${def.color}" opacity=".92"/>
      <circle cx="8" cy="8" r="7" fill="none" stroke="${ring}" stroke-width="1.2" opacity=".7"/>
    </svg>`;

  return L.divIcon({
    html: svg,
    className: '',
    iconSize: [size, size],
    iconAnchor: [size / 2, size / 2],
    popupAnchor: [0, -size / 2],
  });
}

// ── Bearing calculation ───────────────────────────────────────────────────
function bearing(lat1, lon1, lat2, lon2) {
  const φ1 = lat1 * Math.PI / 180, φ2 = lat2 * Math.PI / 180;
  const Δλ = (lon2 - lon1) * Math.PI / 180;
  const y  = Math.sin(Δλ) * Math.cos(φ2);
  const x  = Math.cos(φ1) * Math.sin(φ2) - Math.sin(φ1) * Math.cos(φ2) * Math.cos(Δλ);
  return (Math.atan2(y, x) * 180 / Math.PI + 360) % 360;
}

// ── Velocity from last segment, scaled to real threat speed ───────────────
function computeVelocity(waypoints, type) {
  if (waypoints.length < 2) return { dLat: 0, dLon: 0 };
  const a   = waypoints[waypoints.length - 2];
  const b   = waypoints[waypoints.length - 1];
  const dlat = b.lat - a.lat;
  const dlon = b.lon - a.lon;
  const mag  = Math.hypot(dlat, dlon);
  if (mag < 1e-9) return { dLat: 0, dLon: 0 };

  // Normalise then scale to real speed (deg-lat per ms)
  const speedKmh    = (THREATS[type] || THREATS.unknown).speed;
  const speedDegMs  = speedKmh * DEG_PER_KM / 3_600_000;

  return { dLat: (dlat / mag) * speedDegMs, dLon: (dlon / mag) * speedDegMs };
}

// ── Popup ─────────────────────────────────────────────────────────────────
function popup(evt) {
  const def  = THREATS[evt.type] || THREATS.unknown;
  const time = new Date(evt.ts).toLocaleTimeString('uk-UA', { hour: '2-digit', minute: '2-digit' });
  const from = evt.from ? `↗ From: ${evt.from}` : '';
  const to   = evt.to   ? `🎯 To: ${evt.to}` : '';
  return `
    <div style="min-width:190px">
      <b style="color:${def.color};font-size:13px">${def.label} × ${evt.count || 1}</b>
      <div style="color:#64748b;font-size:10px;margin:3px 0 6px">${time} · ${evt.channel || ''}</div>
      ${evt.location ? `<div>📍 ${evt.location}</div>` : ''}
      ${from ? `<div style="color:#64748b;font-size:11px">${from}</div>` : ''}
      ${to   ? `<div style="color:#64748b;font-size:11px">${to}</div>` : ''}
      <div style="margin-top:7px;padding-top:6px;border-top:1px solid #1a2332;
                  font-size:10px;color:#64748b;line-height:1.45">
        ${(evt.text || '').substring(0, 160)}${(evt.text||'').length > 160 ? '…' : ''}
      </div>
    </div>`;
}

// ── Threat state ──────────────────────────────────────────────────────────
const threats = new Map();
const seenIds = new Set();
let totalCount = 0;

// Build a racetrack patrol loop centred on (lat,lon) for aviation threats
function _patrolRoute(lat, lon) {
  const w = 1.4, h = 0.35;   // ~155 km wide, ~40 km tall
  return [
    [lat + h,  lon - w],
    [lat,      lon - w * 0.5],
    [lat - h,  lon],
    [lat,      lon + w * 0.5],
    [lat + h,  lon + w],
    [lat,      lon + w * 0.5],
    [lat - h,  lon],
    [lat,      lon - w * 0.5],
  ];
}

function addThreat(evt) {
  if (!evt.lat || !evt.lon) return;
  if (threats.has(evt.id)) removeThreat(evt.id);

  const wps = (evt.waypoints || []).filter(w => w.lat && w.lon);
  const def  = THREATS[evt.type] || THREATS.unknown;

  let brg = 0;
  if (wps.length >= 2) {
    const a = wps[wps.length - 2], b = wps[wps.length - 1];
    brg = bearing(a.lat, a.lon, b.lat, b.lon);
  }

  let marker;
  try {
    marker = L.marker([evt.lat, evt.lon], {
      icon: makeIcon(evt.type, evt.status, brg),
      zIndexOffset: def.cat === 'missile' ? 1000 : 500,
    });
  } catch(e) {
    marker = L.circleMarker([evt.lat, evt.lon], {
      radius: 10, color: def.color, fillColor: def.color, fillOpacity: 0.85,
    });
  }
  marker.bindPopup(popup(evt), { maxWidth: 280 });
  marker.addTo(layers.markers);

  // Trajectory trail (no ant-path dependency)
  const trailLines = [];
  if (wps.length >= 2) {
    const lls = wps.map(w => [w.lat, w.lon]);
    trailLines.push(L.polyline(lls, {
      color: def.color, weight: 2, opacity: 0.55,
      dashArray: '6 10',
    }).addTo(layers.paths));

    const vel = computeVelocity(wps, evt.type);
    const msLeft = EXPIRE_MS - (Date.now() - new Date(evt.ts).getTime());
    const last = wps[wps.length - 1];
    const projEnd = {
      lat: last.lat + vel.dLat * Math.max(msLeft, 10_000),
      lon: last.lon + vel.dLon * Math.max(msLeft, 10_000),
    };
    trailLines.push(L.polyline([[last.lat, last.lon], [projEnd.lat, projEnd.lon]], {
      color: def.color, weight: 1, opacity: 0.18, dashArray: '2 14',
    }).addTo(layers.trails));
  }

  const obj = { evt, marker, trailLines, animFrame: null, cancelled: false };
  threats.set(evt.id, obj);

  if (evt.status !== 'destroyed') {
    if (evt.type === 'aviation') {
      _animatePatrol(obj);
    } else {
      _animate(obj, wps);
    }
  }

  const ttl = EXPIRE_MS - (Date.now() - new Date(evt.ts).getTime());
  setTimeout(() => removeThreat(evt.id), Math.max(ttl, 5000));
  updateStats();
}

function removeThreat(id) {
  const obj = threats.get(id);
  if (!obj) return;
  obj.cancelled = true;
  if (obj.animFrame) cancelAnimationFrame(obj.animFrame);
  layers.markers.removeLayer(obj.marker);
  obj.trailLines.forEach(l => {
    layers.paths.removeLayer(l);
    layers.trails.removeLayer(l);
  });
  threats.delete(id);
  updateStats();
}

// ── Patrol animation (aviation — loops forever) ───────────────────────────
function _animatePatrol(obj) {
  const { evt, marker } = obj;
  const route   = _patrolRoute(evt.lat, evt.lon);
  const speedMs = (THREATS[evt.type] || THREATS.aviation).speed * DEG_PER_KM / 3_600_000;

  function step(si, t0) {
    if (obj.cancelled || !threats.has(evt.id)) return;
    const fi   = si % route.length;
    const ti   = (si + 1) % route.length;
    const from = route[fi], to = route[ti];
    const dist = Math.hypot(to[0] - from[0], to[1] - from[1]);
    const segMs = dist / speedMs;
    const t = Math.min((performance.now() - t0) / segMs, 1);

    marker.setLatLng([
      from[0] + (to[0] - from[0]) * t,
      from[1] + (to[1] - from[1]) * t,
    ]);
    marker.setIcon(makeIcon(evt.type, evt.status, bearing(from[0], from[1], to[0], to[1])));

    if (t >= 1) {
      step(si + 1, performance.now());
    } else {
      obj.animFrame = requestAnimationFrame(() => step(si, t0));
    }
  }
  step(0, performance.now());
}

// ── Animation ─────────────────────────────────────────────────────────────
function _animate(obj, wps) {
  if (wps.length < 2) return;

  const { evt, marker } = obj;
  const segs      = wps.length - 1;
  const segMs     = WAYPOINT_TRAVERSE_MS / segs;
  const vel       = computeVelocity(wps, evt.type);

  // Phase 1: traverse waypoints
  function animSeg(si, t0) {
    if (obj.cancelled || !threats.has(evt.id)) return;
    const from = wps[si], to = wps[si + 1];
    const t    = Math.min((performance.now() - t0) / segMs, 1);
    const ease = t < .5 ? 2*t*t : -1 + (4 - 2*t)*t;

    const lat = from.lat + (to.lat - from.lat) * ease;
    const lon = from.lon + (to.lon - from.lon) * ease;
    marker.setLatLng([lat, lon]);

    // Update icon bearing at segment boundaries
    const brg = bearing(from.lat, from.lon, to.lat, to.lon);
    if (t >= 0.98) marker.setIcon(makeIcon(evt.type, evt.status, brg));

    if (t < 1) {
      obj.animFrame = requestAnimationFrame(() => animSeg(si, t0));
    } else if (si < segs - 1) {
      animSeg(si + 1, performance.now());
    } else {
      // Phase 2: extrapolate at real weapon speed
      const finalBrg = bearing(wps[segs-1].lat, wps[segs-1].lon, wps[segs].lat, wps[segs].lon);
      marker.setIcon(makeIcon(evt.type, evt.status, finalBrg));
      _extrapolate(obj, wps[segs], vel);
    }
  }

  animSeg(0, performance.now());
}

// Phase 2: continue in same direction at physics speed indefinitely
function _extrapolate(obj, origin, vel) {
  if (obj.cancelled || !threats.has(obj.evt.id)) return;
  const t0 = performance.now();

  function step() {
    if (obj.cancelled || !threats.has(obj.evt.id)) return;
    const el  = performance.now() - t0;
    obj.marker.setLatLng([origin.lat + vel.dLat * el, origin.lon + vel.dLon * el]);
    obj.animFrame = requestAnimationFrame(step);
  }
  step();
}

// ── Stats ─────────────────────────────────────────────────────────────────
function updateStats() {
  let active = 0, destroyed = 0;
  for (const [, o] of threats) {
    if (o.evt.status === 'destroyed') destroyed++;
    else active++;
  }
  document.getElementById('c-total').textContent     = totalCount;
  document.getElementById('c-active').textContent    = active;
  document.getElementById('c-destroyed').textContent = destroyed;
}

// ── Feed ──────────────────────────────────────────────────────────────────
function addFeedItem(evt) {
  const def  = THREATS[evt.type] || THREATS.unknown;
  const time = new Date(evt.ts).toLocaleTimeString('uk-UA', { hour:'2-digit', minute:'2-digit' });
  const sCls = STATUS_CLASS[evt.status] || 's-unknown';

  const el = document.createElement('div');
  el.className  = 'item';
  el.dataset.cat    = def.cat;
  el.dataset.status = evt.status || 'unknown';

  el.innerHTML = `
    <div class="item-top">
      <span class="item-icon">
        <svg width="14" height="14" viewBox="0 0 16 16">
          <path d="${SHAPES[evt.type] || SHAPES.unknown}" fill="${def.color}"/>
        </svg>
      </span>
      <span class="item-type" style="color:${def.color}">${def.label} × ${evt.count||1}</span>
      <span class="badge ${sCls}">${evt.status||'?'}</span>
      <span class="item-time">${time}</span>
    </div>
    ${evt.location ? `<div class="item-loc">📍 ${evt.location}</div>` : ''}
    <div class="item-text">${evt.text || ''}</div>
    <div class="item-ch">${evt.channel || ''}</div>`;

  el.addEventListener('click', () => {
    if (evt.lat && evt.lon) map.setView([evt.lat, evt.lon], 9, { animate: true });
    const o = threats.get(evt.id);
    if (o) o.marker.openPopup();
  });

  applyFilter(el);
  const feed = document.getElementById('feed');
  feed.insertBefore(el, feed.firstChild);
  while (feed.children.length > 150) feed.removeChild(feed.lastChild);
}

// ── Filters ───────────────────────────────────────────────────────────────
let activeFilter = 'all';

document.querySelectorAll('.f').forEach(b => {
  b.addEventListener('click', () => {
    document.querySelectorAll('.f').forEach(x => x.classList.remove('active'));
    b.classList.add('active');
    activeFilter = b.dataset.f;
    document.querySelectorAll('.item').forEach(applyFilter);
  });
});

function applyFilter(el) {
  const show = activeFilter === 'all'
    || activeFilter === el.dataset.cat
    || activeFilter === el.dataset.status;
  el.classList.toggle('hidden', !show);
}

// ── Update countdown ──────────────────────────────────────────────────────
let nextUpdateAt = null;
setInterval(() => {
  const el = document.getElementById('update-txt');
  if (!nextUpdateAt) return;
  const s = Math.round((nextUpdateAt - Date.now()) / 1000);
  if (s <= 0) { el.textContent = 'Fetching…'; return; }
  const m = Math.floor(s / 60), ss = String(s % 60).padStart(2, '0');
  el.textContent = `Next update ${m}:${ss}`;
}, 1000);

// ── CSS pulse animation injection ────────────────────────────────────────
document.head.insertAdjacentHTML('beforeend', `
  <style>
    @keyframes iconPulse {
      0%,100%{opacity:1;filter:drop-shadow(0 0 4px currentColor)}
      50%{opacity:.65;filter:drop-shadow(0 0 10px currentColor)}
    }
  </style>`);

// ── WebSocket ─────────────────────────────────────────────────────────────
let ws, wsRetries = 0;

function connect() {
  const url = `${location.protocol==='https:'?'wss':'ws'}://${location.host}/ws`;
  setConn('connecting');
  ws = new WebSocket(url);

  ws.onopen  = () => { wsRetries = 0; setConn('live'); };
  ws.onclose = () => {
    setConn('error');
    setTimeout(connect, Math.min(3000 * (wsRetries + 1), 15_000));
    wsRetries++;
  };
  ws.onerror = () => ws.close();

  ws.onmessage = ({ data }) => {
    let m;
    try { m = JSON.parse(data); } catch { return; }
    if (m.type === 'event') {
      handleEvent(m.data);
    } else if (m.type === 'history') {
      [...m.data].reverse().forEach(handleEvent);
    } else if (m.type === 'next_update') {
      nextUpdateAt = new Date(m.at).getTime();
    }
  };
}

function handleEvent(evt) {
  if (!evt || !evt.id || seenIds.has(evt.id)) return;
  seenIds.add(evt.id);
  totalCount++;
  try { addThreat(evt); } catch(e) { console.error('addThreat', e, evt); }
  try { addFeedItem(evt); } catch(e) { console.error('addFeedItem', e, evt); }
  updateStats();
}

function setConn(state) {
  const dot = document.getElementById('conn-dot');
  const txt = document.getElementById('conn-txt');
  dot.className = `dot${state === 'live' ? ' live' : state === 'error' ? ' error' : ''}`;
  txt.textContent = { connecting: 'Connecting…', live: 'Connected', error: 'Reconnecting…' }[state];
}

// ── HTTP polling — XMLHttpRequest instead of fetch() for pywebview compat ──
function pollEvents() {
  const xhr = new XMLHttpRequest();
  xhr.onreadystatechange = function() {
    if (xhr.readyState !== 4) return;
    if (xhr.status === 200) {
      try {
        const data = JSON.parse(xhr.responseText);
        const evts = data.events || [];
        if (evts.length > 0) {
          document.getElementById('conn-txt').textContent = 'Live · ' + evts.length + ' event' + (evts.length === 1 ? '' : 's');
          document.getElementById('conn-dot').className = 'dot live';
        }
        evts.forEach(handleEvent);
      } catch(e) {
        document.getElementById('conn-txt').textContent = 'Parse error';
      }
    } else if (xhr.status !== 0) {
      document.getElementById('conn-txt').textContent = 'Poll error ' + xhr.status;
    }
    setTimeout(pollEvents, 3000);
  };
  xhr.onerror = function() {
    document.getElementById('conn-txt').textContent = 'XHR error – retrying';
    setTimeout(pollEvents, 3000);
  };
  xhr.open('GET', window.location.origin + '/api/events', true);
  xhr.send();
}

// ── Boot ──────────────────────────────────────────────────────────────────
connect();
pollEvents();
setInterval(() => {
  const now = Date.now();
  for (const [id, o] of threats)
    if (now - new Date(o.evt.ts).getTime() > EXPIRE_MS + 5000) removeThreat(id);
}, 60_000);
