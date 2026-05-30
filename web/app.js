/* Ukraine Drone Map — frontend
   Directional SVG icons · Physics-accurate speeds · Trajectory extrapolation */

// ── Threat definitions ────────────────────────────────────────────────────
// speed_kmh used for extrapolation after last waypoint
const THREATS = {
  shahed:    { label: 'Shahed',     color: '#f97316', glow: '#f97316', speed: 150,  cat: 'drone'      },
  geran:     { label: 'Geranium',   color: '#f97316', glow: '#f97316', speed: 150,  cat: 'drone'      },
  drone:     { label: 'UAV',        color: '#60a5fa', glow: '#3b82f6', speed: 150,  cat: 'drone'      },
  kar:       { label: 'KAR',        color: '#fb923c', glow: '#ea580c', speed: 200,  cat: 'drone'      },
  glidebomb: { label: 'Glide Bomb', color: '#f59e0b', glow: '#d97706', speed: 500,  cat: 'glidebomb'  },
  kalibr:    { label: 'Kalibr',     color: '#ef4444', glow: '#dc2626', speed: 700,  cat: 'missile'    },
  x101:      { label: 'X-101',      color: '#f87171', glow: '#ef4444', speed: 780,  cat: 'missile'    },
  x59:       { label: 'X-59',       color: '#fb923c', glow: '#ea580c', speed: 900,  cat: 'missile'    },
  x22:       { label: 'X-22',       color: '#f43f5e', glow: '#e11d48', speed: 1000, cat: 'missile'    },
  oniks:     { label: 'Oniks',      color: '#e879f9', glow: '#c026d3', speed: 2500, cat: 'missile'    },
  kinzhal:   { label: 'Kinzhal',    color: '#c084fc', glow: '#a855f7', speed: 3000, cat: 'missile'    },
  iskander:  { label: 'Iskander',   color: '#fbbf24', glow: '#d97706', speed: 1500, cat: 'missile'    },
  ballistic: { label: 'Ballistic',  color: '#eab308', glow: '#ca8a04', speed: 1200, cat: 'missile'    },
  missile:   { label: 'Missile',    color: '#ef4444', glow: '#dc2626', speed: 700,  cat: 'missile'    },
  unknown:   { label: 'Unknown',    color: '#94a3b8', glow: '#64748b', speed: 300,  cat: 'unknown'    },
  aviation:  { label: 'Aviation',   color: '#38bdf8', glow: '#0ea5e9', speed: 800,  cat: 'aviation'   },
};

const STATUS_CLASS = {
  moving: 's-moving', destroyed: 's-destroyed',
  alert:  's-alert',  launch:    's-launch', unknown: 's-unknown',
};

// 1 degree latitude ≈ 111 km — used to convert km/h to deg/ms
const DEG_PER_KM = 1 / 111;

// Threat expires after this long (disappears from map)
const EXPIRE_MS = 30 * 60 * 1000;
// How far back in time to extrapolate position on initial load.
// Matches the 20-min history window so a drone reported 20 min ago
// appears at its current estimated position, not its original reported spot.
const MAX_EXTRAP_MS = 20 * 60 * 1000;

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
  // drones: swept-wing delta shape
  drone:     'M8,1 L15,13 L11,11 L8,14 L5,11 L1,13 Z',
  shahed:    'M8,1 L15,13 L11,11 L8,14 L5,11 L1,13 Z',
  geran:     'M8,1 L15,13 L11,11 L8,14 L5,11 L1,13 Z',
  kar:       'M8,1 L15,13 L11,11 L8,14 L5,11 L1,13 Z',
  // cruise missiles: slim sleek dart with notched tail
  missile:   'M8,0 L12,12 L10,11 L8,15 L6,11 L4,12 Z',
  kalibr:    'M8,0 L12,12 L10,11 L8,15 L6,11 L4,12 Z',
  x101:      'M8,0 L12,12 L10,11 L8,15 L6,11 L4,12 Z',
  x59:       'M8,0 L12,12 L10,11 L8,15 L6,11 L4,12 Z',
  x22:       'M8,0 L12,12 L10,11 L8,15 L6,11 L4,12 Z',
  oniks:     'M8,0 L12,12 L10,11 L8,15 L6,11 L4,12 Z',
  // kinzhal: ultra-slim needle with double notch
  kinzhal:   'M8,0 L10,14 L8,11 L6,14 Z',
  // ballistic / iskander: rounded warhead silhouette
  iskander:  'M8,1 C11,1 13,5 13,10 C13,14 11,15 8,15 C5,15 3,14 3,10 C3,5 5,1 8,1 Z',
  ballistic: 'M8,1 C11,1 13,5 13,10 C13,14 11,15 8,15 C5,15 3,14 3,10 C3,5 5,1 8,1 Z',
  // glide bomb: swept diamond — short broad wing
  glidebomb: 'M8,2 L15,7 L12,8 L8,15 L4,8 L1,7 Z',
  unknown:   'M8,2 L14,13 L8,10 L2,13 Z',
  // top-down aircraft silhouette
  aviation:  'M8,0 L10,5 L16,6 L16,8 L10,8 L11,16 L8,14 L5,16 L6,8 L0,8 L0,6 L6,5 Z',
};

const RING_COLORS = {
  moving: '#f97316', launch: '#ef4444',
  alert:  '#facc15', destroyed: '#22c55e', unknown: '#64748b',
};

function makeIcon(type, status, bearingDeg, count) {
  const def   = THREATS[type] || THREATS.unknown;
  const shape = SHAPES[type]  || SHAPES.unknown;
  const ring  = RING_COLORS[status] || RING_COLORS.unknown;
  const isActive = status === 'moving' || status === 'launch' || status === 'alert';
  const pulse = isActive ? 'style="animation:iconPulse 1.8s infinite"' : '';
  const size  = type === 'kinzhal' ? 50 : (def.cat === 'glidebomb' ? 54 : def.cat === 'missile' ? 46 : 54);
  const n = count > 1 ? count : 0;
  const uid = Math.random().toString(36).slice(2, 7);

  // Lighter tint of the fill color for the gradient highlight
  const svg = `
    <svg width="${size}" height="${size}" viewBox="0 0 20 22"
         style="transform:rotate(${bearingDeg}deg)" ${pulse}>
      <defs>
        <radialGradient id="g${uid}" cx="40%" cy="30%" r="65%">
          <stop offset="0%"   stop-color="#ffffff" stop-opacity="0.35"/>
          <stop offset="100%" stop-color="${def.color}" stop-opacity="0"/>
        </radialGradient>
        <filter id="f${uid}" x="-40%" y="-40%" width="180%" height="180%">
          <feGaussianBlur in="SourceGraphic" stdDeviation="1.8" result="blur"/>
          <feColorMatrix in="blur" type="matrix"
            values="1 0 0 0 0  0 1 0 0 0  0 0 1 0 0  0 0 0 14 -5" result="glow"/>
          <feMerge><feMergeNode in="glow"/><feMergeNode in="SourceGraphic"/></feMerge>
        </filter>
      </defs>
      <g transform="scale(1.25) translate(0,-1)" filter="url(#f${uid})">
        <path d="${shape}" fill="${def.color}" opacity="0.95"
              stroke="${def.glow}" stroke-width="0.4" stroke-opacity="0.6"/>
        <path d="${shape}" fill="url(#g${uid})"/>
        <circle cx="8" cy="8" r="7" fill="none" stroke="${ring}"
                stroke-width="1.5" opacity="0.9"
                stroke-dasharray="${status === 'destroyed' ? '3 2' : 'none'}"/>
      </g>
      ${n ? `<text x="10" y="21" text-anchor="middle" font-family="monospace"
               font-size="5.5" font-weight="bold" fill="white"
               stroke="#080c10" stroke-width="1">×${n}</text>` : ''}
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

  // Normalise then scale to animation speed (deg-lat per ms)
  const speedKmh    = (THREATS[type] || THREATS.unknown).speed;
  const speedDegMs  = speedKmh * DEG_PER_KM / 3_600_000;

  return { dLat: (dlat / mag) * speedDegMs, dLon: (dlon / mag) * speedDegMs };
}

// ── Popup ─────────────────────────────────────────────────────────────────
function popup(evt) {
  const def  = THREATS[evt.type] || THREATS.unknown;
  const time = new Date(evt.ts).toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', hour12: false });
  const DIRS = {0:'N',45:'NE',90:'E',135:'SE',180:'S',225:'SW',270:'W',315:'NW'};
  const dirLabel = evt.direction != null ? (DIRS[evt.direction] || `${evt.direction}°`) : null;
  const count = evt.count || 1;
  return `
    <div style="min-width:200px;font-family:monospace">
      <b style="color:${def.color};font-size:13px">${def.label}${count > 1 ? ` ×${count}` : ''}</b>
      <span style="margin-left:8px;padding:1px 5px;background:${def.color}22;color:${def.color};
                   border-radius:3px;font-size:10px">${(evt.status||'unknown').toUpperCase()}</span>
      <div style="color:#64748b;font-size:10px;margin:4px 0 6px">${time} UTC · ${evt.channel || ''}</div>
      ${evt.location ? `<div style="margin-bottom:3px">📍 <b>${evt.location}</b></div>` : ''}
      ${dirLabel     ? `<div style="color:#94a3b8;font-size:11px">🧭 Heading: <b style="color:#e2e8f0">${dirLabel}</b></div>` : ''}
      ${evt.from     ? `<div style="color:#94a3b8;font-size:11px">↗ From: ${evt.from}</div>` : ''}
      ${evt.to       ? `<div style="color:#94a3b8;font-size:11px">🎯 Toward: ${evt.to}</div>` : ''}
      ${evt.waypoints && evt.waypoints.length > 1
        ? `<div style="color:#64748b;font-size:10px;margin-top:3px">📌 ${evt.waypoints.map(w=>w.name).join(' → ')}</div>`
        : ''}
      <div style="margin-top:7px;padding-top:6px;border-top:1px solid #1a2332;
                  font-size:10px;color:#64748b;line-height:1.45">
        ${(evt.text || '').substring(0, 200)}${(evt.text||'').length > 200 ? '…' : ''}
      </div>
    </div>`;
}

// ── Threat state ──────────────────────────────────────────────────────────
const threats = new Map();
// seenIds: Map<id, timestamp> — expires after 35 min so server-restart history reloads correctly
const seenIds = new Map();
function hasSeen(id) { return seenIds.has(id); }
function markSeen(id) { seenIds.set(id, Date.now()); }
setInterval(() => {
  const cutoff = Date.now() - 35 * 60 * 1000;
  for (const [id, ts] of seenIds) if (ts < cutoff) seenIds.delete(id);
}, 5 * 60 * 1000);
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

// Arrange N markers in a line perpendicular to direction of travel
function _formationOffsets(count, bearingDeg) {
  if (count <= 1) return [[0, 0]];
  const SPACING = 0.055;  // ~6 km between each unit
  const perpRad = (bearingDeg + 90) * Math.PI / 180;
  const half = (count - 1) / 2;
  const offsets = [];
  for (let i = 0; i < count; i++) {
    const t = i - half;
    offsets.push([Math.sin(perpRad) * SPACING * t, Math.cos(perpRad) * SPACING * t]);
  }
  return offsets;
}

function addThreat(evt) {
  if (!evt.lat || !evt.lon) return;
  if (threats.has(evt.id)) removeThreat(evt.id);

  const wps  = (evt.waypoints || []).filter(w => w.lat && w.lon);
  const def  = THREATS[evt.type] || THREATS.unknown;
  const count = Math.min(evt.count || 1, 6);

  // Initial bearing from text direction, or last waypoint segment
  let brg = evt.direction != null ? evt.direction : 0;
  if (brg === 0 && wps.length >= 2) {
    const a = wps[wps.length - 2], b = wps[wps.length - 1];
    brg = bearing(a.lat, a.lon, b.lat, b.lon);
  }

  const offsets = _formationOffsets(count, brg);
  const markers = [];
  const trailLines = [];

  offsets.forEach((off) => {
    const lat = evt.lat + off[0], lon = evt.lon + off[1];
    let m;
    try {
      m = L.marker([lat, lon], {
        icon: makeIcon(evt.type, evt.status, brg, count),
        zIndexOffset: def.cat === 'missile' ? 1000 : 500,
      });
    } catch(e) {
      m = L.circleMarker([lat, lon], {
        radius: 10, color: def.color, fillColor: def.color, fillOpacity: 0.85,
      });
    }
    m.bindPopup(popup(evt), { maxWidth: 300 });
    m.addTo(layers.markers);
    markers.push(m);
  });

  // Waypoint trail only (no forward-projection line — it caused cross-Ukraine artifacts)
  if (wps.length >= 2) {
    trailLines.push(L.polyline(wps.map(w => [w.lat, w.lon]), {
      color: def.color, weight: 2, opacity: 0.5, dashArray: '5 9',
    }).addTo(layers.paths));
  }

  const obj = { evt, markers, marker: markers[0], trailLines, cancelled: false };
  threats.set(evt.id, obj);

  if (evt.status !== 'destroyed') {
    if (evt.type === 'aviation') {
      _animatePatrol(obj);
    } else {
      offsets.forEach((off, i) => {
        const offsetWps = wps.map(w => ({ lat: w.lat + off[0], lon: w.lon + off[1], name: w.name }));
        _animateMarker(obj, markers[i], offsetWps, evt);
      });
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
  (obj.markers || (obj.marker ? [obj.marker] : [])).forEach(m => layers.markers.removeLayer(m));
  obj.trailLines.forEach(l => {
    layers.paths.removeLayer(l);
    layers.trails.removeLayer(l);
  });
  threats.delete(id);
  updateStats();
}

// ── Patrol animation (aviation — loops forever) ───────────────────────────
function _animatePatrol(obj) {
  const { evt } = obj;
  const marker = (obj.markers && obj.markers[0]) || obj.marker;
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
// Compute current real-world position from elapsed time since the report,
// then hand off to _extrapolateMarker which runs indefinitely at physics speed
// until the marker is removed or a new update arrives for this threat.
// MAX_EXTRAP_MS only limits the initial position jump on startup load.
function _animateMarker(obj, marker, wps, evt) {
  const def = THREATS[evt.type] || THREATS.unknown;
  const speedDegMs = def.speed * DEG_PER_KM / 3_600_000;

  // Cap initial jump to MAX_EXTRAP_MS so old events don't teleport far on load
  const elapsedMs = Math.min(
    Math.max(0, Date.now() - new Date(evt.ts).getTime()),
    MAX_EXTRAP_MS
  );

  const cardinalBrg = evt.direction != null ? evt.direction : null;

  // Determine extrapolation velocity:
  // Priority: (1) parsed cardinal direction, (2) waypoint trajectory,
  // (3) fallback south — every marker keeps moving, just "guessing"
  let extrapVel, guessedBrg;
  if (cardinalBrg != null) {
    const rad = cardinalBrg * Math.PI / 180;
    extrapVel  = { dLat: Math.cos(rad) * speedDegMs, dLon: Math.sin(rad) * speedDegMs };
    guessedBrg = cardinalBrg;
  } else if (wps.length >= 2) {
    extrapVel  = computeVelocity(wps, evt.type);
    guessedBrg = null;  // will be set from waypoints below
  } else {
    // No direction known — default heading for Russian assets entering Ukraine:
    // most attacks come from north/east, so default bearing is south (180°)
    const rad  = Math.PI;  // 180°
    extrapVel  = { dLat: Math.cos(rad) * speedDegMs, dLon: Math.sin(rad) * speedDegMs };
    guessedBrg = 180;
  }

  // Walk the waypoints to find the current interpolated position
  let curLat, curLon, curBrg;
  if (wps.length >= 2) {
    let distLeft = speedDegMs * elapsedMs;
    curLat = wps[0].lat; curLon = wps[0].lon;
    curBrg = bearing(wps[0].lat, wps[0].lon, wps[1].lat, wps[1].lon);
    let pastEnd = true;
    for (let i = 0; i < wps.length - 1; i++) {
      const a = wps[i], b = wps[i + 1];
      const segDist = Math.hypot(b.lat - a.lat, b.lon - a.lon);
      curBrg = bearing(a.lat, a.lon, b.lat, b.lon);
      if (distLeft <= segDist) {
        const t = distLeft / segDist;
        curLat = a.lat + (b.lat - a.lat) * t;
        curLon = a.lon + (b.lon - a.lon) * t;
        distLeft = 0; pastEnd = false; break;
      }
      distLeft -= segDist;
      curLat = b.lat; curLon = b.lon;
    }
    if (pastEnd && distLeft > 0) {
      curLat += extrapVel.dLat * (distLeft / speedDegMs);
      curLon += extrapVel.dLon * (distLeft / speedDegMs);
    }
  } else {
    const origin = wps[0] || { lat: evt.lat, lon: evt.lon };
    curLat = origin.lat + extrapVel.dLat * elapsedMs;
    curLon = origin.lon + extrapVel.dLon * elapsedMs;
    curBrg = guessedBrg ?? 0;
  }

  // Cardinal direction always wins for icon heading
  if (cardinalBrg != null) curBrg = cardinalBrg;
  if (guessedBrg != null && cardinalBrg == null && wps.length < 2) curBrg = guessedBrg;

  marker.setLatLng([curLat, curLon]);
  marker.setIcon(makeIcon(evt.type, evt.status, curBrg, evt.count || 1));

  // Always extrapolate — every marker keeps dead-reckoning until removed
  _extrapolateMarker(obj, marker, { lat: curLat, lon: curLon }, extrapVel, curBrg, evt);
}

// Continue moving at animation speed until marker is cancelled by a new update or expiry.
// This runs forever — it's the "guessing" phase between Telegram updates.
// Icon is set once here; only position is updated per frame.
function _extrapolateMarker(obj, marker, origin, vel, brg, evt) {
  if (obj.cancelled || !threats.has(obj.evt.id)) return;
  const count = (evt || obj.evt).count || 1;
  // Set icon once — heading doesn't change during extrapolation
  if (brg != null) marker.setIcon(makeIcon(obj.evt.type, obj.evt.status, brg, count));
  const t0 = performance.now();
  function step() {
    if (obj.cancelled || !threats.has(obj.evt.id)) return;
    const el = performance.now() - t0;
    marker.setLatLng([origin.lat + vel.dLat * el, origin.lon + vel.dLon * el]);
    requestAnimationFrame(step);
  }
  requestAnimationFrame(step);
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
  const nt = document.getElementById('no-threats');
  if (nt) nt.style.display = threats.size === 0 ? 'flex' : 'none';
}

// Age-based opacity fading — runs every 30 s
setInterval(() => {
  const now = Date.now();
  for (const [, obj] of threats) {
    const age = now - new Date(obj.evt.ts).getTime();
    const op  = age < 5 * 60_000 ? 1 : age < 15 * 60_000 ? 0.65 : 0.35;
    (obj.markers || (obj.marker ? [obj.marker] : [])).forEach(m => {
      const el = m.getElement();
      if (el) el.style.opacity = op;
    });
  }
}, 30_000);

// ── Feed ──────────────────────────────────────────────────────────────────
function addFeedItem(evt) {
  const def  = THREATS[evt.type] || THREATS.unknown;
  const time = new Date(evt.ts).toLocaleTimeString('en-US', { hour:'2-digit', minute:'2-digit' });
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

// ── Update status display ─────────────────────────────────────────────────
function _setUpdateTxt(text) {
  const el = document.getElementById('update-txt');
  if (el) el.textContent = text;
}

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
      _setUpdateTxt(m.at === 'live' ? 'Live — instant updates' : 'Loading history…');
    }
  };
}

function handleEvent(evt) {
  if (!evt || !evt.id || hasSeen(evt.id)) return;
  markSeen(evt.id);
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

// ── RAW message feed tab ──────────────────────────────────────────────────
let rawTab = false;

document.querySelectorAll('.tab-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    rawTab = btn.dataset.tab === 'raw';
    document.getElementById('feed').style.display    = rawTab ? 'none' : '';
    document.getElementById('feed-raw').style.display = rawTab ? '' : 'none';
  });
});

function pollRawMessages() {
  const xhr = new XMLHttpRequest();
  xhr.onreadystatechange = function() {
    if (xhr.readyState !== 4 || xhr.status !== 200) return;
    try {
      const msgs = JSON.parse(xhr.responseText).messages || [];
      const el = document.getElementById('feed-raw');
      if (!el) return;
      el.innerHTML = '';
      msgs.forEach(msg => {
        const time = new Date(msg.ts).toLocaleTimeString('en-US',
          { hour: '2-digit', minute: '2-digit', hour12: false });
        const div = document.createElement('div');
        div.className = 'raw-item ' + (msg.plotted ? 'r-plotted' : 'r-unplotted');
        div.innerHTML = `<div class="raw-header">
          <span class="raw-ch">${msg.channel}</span>
          <span class="raw-time">${time}</span>
          ${msg.plotted ? '<span class="raw-badge">PLOTTED</span>' : ''}
        </div>
        <div class="raw-text">${(msg.text || '').substring(0, 300)}</div>`;
        el.appendChild(div);
      });
    } catch(e) {}
  };
  xhr.open('GET', window.location.origin + '/api/messages', true);
  xhr.send();
}

// ── Boot ──────────────────────────────────────────────────────────────────
connect();
pollEvents();
pollRawMessages();
setInterval(pollRawMessages, 30_000);
setInterval(() => {
  const now = Date.now();
  for (const [id, o] of threats)
    if (now - new Date(o.evt.ts).getTime() > EXPIRE_MS + 5000) removeThreat(id);
}, 60_000);
