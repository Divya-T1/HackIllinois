/* ── Config ──────────────────────────────────────────────────────────────── */
const API = "http://localhost:8001";

/* ── State ───────────────────────────────────────────────────────────────── */
let map, pinMarker;
let mapInitialized    = false;
let merchantMap, merchantMapMarker;
let merchants         = [];
let selectedMerchant  = null;
let currentGeofences  = [];
let currentMerchantName = "";
let drawerOpen = false;
let activeTab  = "overview";
let feedEvents = [];  // mirror of live feed for drawer

/* ── Main map — MapLibre GL (3D) ─────────────────────────────────────────── */
function initMap() {
  map = new maplibregl.Map({
    container: "map",
    style: "https://tiles.openfreemap.org/styles/liberty",
    center: [-88.2350, 40.1130],   // [lng, lat]
    zoom: 15,
    pitch: 45,
    bearing: -10,
    attributionControl: false,
  });

  map.addControl(new maplibregl.NavigationControl({ visualizePitch: true }), "bottom-right");
  map.addControl(new maplibregl.AttributionControl({ compact: true }));

  map.on("load", () => {
    // ── Geofence GeoJSON source + layers ──────────────────────────────────
    map.addSource("geofences", {
      type: "geojson",
      data: { type: "FeatureCollection", features: [] },
    });
    map.addLayer({
      id: "geofences-fill",
      type: "fill",
      source: "geofences",
      paint: { "fill-color": "#7c3aed", "fill-opacity": 0.18 },
    });
    map.addLayer({
      id: "geofences-border",
      type: "line",
      source: "geofences",
      paint: { "line-color": "#a78bfa", "line-width": 2 },
    });

    // ── 3D buildings ──────────────────────────────────────────────────────
    try {
      map.addLayer({
        id: "3d-buildings",
        source: "openmaptiles",
        "source-layer": "building",
        type: "fill-extrusion",
        minzoom: 14,
        paint: {
          "fill-extrusion-color": "#2a2a4a",
          "fill-extrusion-height": ["get", "render_height"],
          "fill-extrusion-base":   ["get", "render_min_height"],
          "fill-extrusion-opacity": 0.75,
        },
      }, "geofences-fill");
    } catch (_) { /* style may not expose building source */ }

    // ── Map click → place pin (skip if over a geofence) ───────────────────
    map.on("click", (e) => {
      const hit = map.queryRenderedFeatures(e.point, { layers: ["geofences-fill"] });
      if (hit.length) return;
      const { lng, lat } = e.lngLat;
      document.getElementById("sim-lat").value = lat.toFixed(6);
      document.getElementById("sim-lng").value = lng.toFixed(6);
      placePinMarker(lat, lng);
    });

    // ── Geofence click → popup ────────────────────────────────────────────
    map.on("click", "geofences-fill", (e) => {
      if (!e.features.length) return;
      const g = currentGeofences.find(x => x.id === e.features[0].properties.id);
      if (!g) return;
      new maplibregl.Popup({ closeButton: false, maxWidth: "240px" })
        .setLngLat(e.lngLat)
        .setHTML(buildGeofencePopup(g, currentMerchantName))
        .addTo(map);
    });

    map.on("mouseenter", "geofences-fill", () => { map.getCanvas().style.cursor = "pointer"; });
    map.on("mouseleave", "geofences-fill", () => { map.getCanvas().style.cursor = ""; });
  });
}

/* ── Helpers ─────────────────────────────────────────────────────────────── */
function makeCirclePolygon(lat, lng, radiusMeters, steps = 64) {
  const coords = [];
  for (let i = 0; i <= steps; i++) {
    const angle = (i / steps) * 2 * Math.PI;
    const dLat  = (radiusMeters * Math.cos(angle)) / 111320;
    const dLng  = (radiusMeters * Math.sin(angle)) / (111320 * Math.cos((lat * Math.PI) / 180));
    coords.push([lng + dLng, lat + dLat]);
  }
  return { type: "Feature", geometry: { type: "Polygon", coordinates: [coords] }, properties: {} };
}

function placePinMarker(lat, lng) {
  if (pinMarker) pinMarker.remove();
  const el = document.createElement("div");
  el.style.cssText = "width:12px;height:12px;background:#a78bfa;border:2px solid #fff;border-radius:50%;box-shadow:0 0 8px #7c3aed;";
  pinMarker = new maplibregl.Marker({ element: el })
    .setLngLat([lng, lat])
    .addTo(map);
}

/* ── Geofence circles ────────────────────────────────────────────────────── */
function clearGeofenceCircles() {
  currentGeofences    = [];
  currentMerchantName = "";
  if (!map) return;
  const src = map.getSource("geofences");
  if (src) src.setData({ type: "FeatureCollection", features: [] });
}

function drawGeofences(geofences, merchantName) {
  currentGeofences    = geofences;
  currentMerchantName = merchantName;

  const features = geofences.map(g => {
    const f = makeCirclePolygon(g.lat, g.lng, g.radius_meters);
    f.properties = { id: g.id };
    return f;
  });

  const update = () => {
    const src = map.getSource("geofences");
    if (src) src.setData({ type: "FeatureCollection", features });
    if (geofences.length) {
      map.flyTo({ center: [geofences[0].lng, geofences[0].lat], zoom: 17, pitch: 45, duration: 800 });
    }
  };

  if (map.loaded()) update();
  else map.once("load", update);

  buildJumpButtons(geofences);
}

function buildGeofencePopup(g, merchantName) {
  const tiers = g.discount_tiers
    .map(t => `<li>${t.tier_type}: <b>${t.percent}%</b> off</li>`)
    .join("");
  return `
    <div style="font-family:monospace;font-size:12px;min-width:180px">
      <b style="color:#a78bfa">${merchantName}</b><br/>
      <span style="color:#9ca3af">${g.name}</span><br/>
      <hr style="border-color:#2d2d4e;margin:4px 0"/>
      Radius: ${g.radius_meters}m &nbsp;|&nbsp; Cap: ${g.max_discount}%<br/>
      Hours: ${g.active_hours_start}–${g.active_hours_end}<br/>
      <ul style="margin:4px 0;padding-left:12px">${tiers}</ul>
    </div>`;
}

function buildJumpButtons(geofences) {
  const container = document.getElementById("jump-buttons");
  container.innerHTML = "";
  geofences.forEach(g => {
    const btn = document.createElement("button");
    btn.textContent = `⌖ ${g.name.split(" ")[0]}`;
    btn.className = "text-[10px] bg-surface border border-border rounded px-2 py-0.5 text-brand-light hover:border-brand transition-colors";
    btn.onclick = () => {
      document.getElementById("sim-lat").value = g.lat.toFixed(6);
      document.getElementById("sim-lng").value = g.lng.toFixed(6);
      placePinMarker(g.lat, g.lng);
      map.flyTo({ center: [g.lng, g.lat], zoom: 18, pitch: 45, duration: 600 });
    };
    container.appendChild(btn);
  });
}

/* ── Merchants ───────────────────────────────────────────────────────────── */
async function loadMerchants() {
  try {
    const res = await fetch(`${API}/v1/merchants/`);
    if (!res.ok) throw new Error(res.statusText);
    merchants = await res.json();

    const sel = document.getElementById("merchant-select");
    merchants.forEach(m => {
      const opt = document.createElement("option");
      opt.value = m.id;
      opt.textContent = m.name;
      sel.appendChild(opt);
    });

    setStatus("online");
  } catch (e) {
    setStatus("offline");
    console.error("Failed to load merchants:", e);
  }
}

async function onMerchantChange(merchantId) {
  if (!merchantId) {
    selectedMerchant = null;
    clearGeofenceCircles();
    document.getElementById("merchant-info").classList.add("hidden");
    document.getElementById("checkin-btn").disabled = true;
    document.getElementById("analytics-pill-wrap").classList.add("hidden");
    return;
  }

  selectedMerchant = merchants.find(m => m.id === merchantId);
  document.getElementById("info-id").textContent  = selectedMerchant.id;
  document.getElementById("info-key").textContent = selectedMerchant.api_key;
  document.getElementById("merchant-info").classList.remove("hidden");
  document.getElementById("checkin-btn").disabled = false;

  try {
    const res = await fetch(`${API}/v1/merchants/${merchantId}/geofences`);
    drawGeofences(await res.json(), selectedMerchant.name);
  } catch (e) {
    console.error("Failed to load geofences:", e);
  }

  loadAnalytics(merchantId);
}

/* ── Checkin ─────────────────────────────────────────────────────────────── */
async function triggerCheckin() {
  if (!selectedMerchant) return;

  const lat    = parseFloat(document.getElementById("sim-lat").value);
  const lng    = parseFloat(document.getElementById("sim-lng").value);
  const userId = document.getElementById("user-id").value.trim() || "user_demo_01";

  if (isNaN(lat) || isNaN(lng)) {
    alert("Click the map to set a location first.");
    return;
  }

  const btn = document.getElementById("checkin-btn");
  btn.disabled = true;
  btn.textContent = "Processing…";

  try {
    const res = await fetch(`${API}/v1/checkins`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ user_id: userId, lat, lng, merchant_id: selectedMerchant.id }),
    });
    const data = await res.json();
    renderOfferResult(data);
    appendFeedItem(data, userId);
    appendDrawerFeedItem(data, userId);
    loadAnalytics(selectedMerchant.id);
  } catch (e) {
    renderError(e.message);
  } finally {
    btn.disabled = false;
    btn.textContent = "Trigger Checkin";
  }
}

/* ── Render ──────────────────────────────────────────────────────────────── */
function renderOfferResult(data) {
  const el = document.getElementById("offer-result");
  if (data.enabled) {
    el.innerHTML = `
      <div class="offer-card success">
        <div class="flex items-center justify-between mb-2">
          <span class="text-green-400 font-bold">✓ Offer Generated</span>
          <span class="text-brand-light font-bold text-base">${data.discount_percent}% off</span>
        </div>
        <div class="text-gray-400 mb-1">${data.geofence_name ?? ""}</div>
        <div class="text-gray-300 mb-2 text-[11px]">${data.personalization?.explanation ?? ""}</div>
        <div class="text-gray-500 text-[10px] mb-2">
          Code: <span class="text-gray-300">${data.personalization?.reason_code ?? ""}</span>
          &nbsp;·&nbsp; ID: <span class="text-gray-300">${data.offer_id ?? ""}</span>
        </div>
        <a href="${data.stripe_payment_link}" target="_blank"
           class="block text-center bg-brand hover:bg-brand-dark text-white rounded px-3 py-1.5 text-xs font-semibold transition-colors">
          Open Stripe Checkout ↗
        </a>
      </div>`;
  } else {
    el.innerHTML = `
      <div class="offer-card fail">
        <div class="text-yellow-400 font-semibold mb-1">✗ No offer</div>
        <div class="text-gray-400">${data.message}</div>
      </div>`;
  }
}

function renderError(msg) {
  document.getElementById("offer-result").innerHTML = `
    <div class="offer-card fail">
      <div class="text-red-400 font-semibold mb-1">Error</div>
      <div class="text-gray-400 text-[11px]">${msg}</div>
    </div>`;
}

function appendFeedItem(data, userId) {
  const feed = document.getElementById("checkin-feed");
  const li   = document.createElement("li");
  const time = new Date().toLocaleTimeString();

  li.className = `feed-item ${data.enabled ? "triggered" : "no-trigger"}`;
  li.innerHTML = data.enabled
    ? `<span class="text-brand-light">${userId}</span>
       → <b class="text-green-400">${data.discount_percent}% off</b>
       <span class="text-gray-500 float-right">${time}</span>`
    : `<span class="text-gray-400">${userId}</span>
       — <span class="text-gray-600">${data.message.slice(0, 30)}…</span>
       <span class="text-gray-600 float-right">${time}</span>`;

  feed.prepend(li);
  while (feed.children.length > 30) feed.removeChild(feed.lastChild);
}

/* ── Analytics ───────────────────────────────────────────────────────────── */
async function loadAnalytics(merchantId) {
  try {
    const res  = await fetch(`${API}/v1/merchants/${merchantId}/analytics`);
    const data = await res.json();

    // Update pill stats + show it
    document.getElementById("a-total").textContent    = data.total_offers;
    document.getElementById("a-redeemed").textContent = data.redeemed_offers;
    document.getElementById("a-rate").textContent     = `${data.redemption_rate}%`;
    document.getElementById("analytics-pill-wrap").classList.remove("hidden");

    // Update drawer summary
    document.getElementById("d-total").textContent    = data.total_offers;
    document.getElementById("d-redeemed").textContent = data.redeemed_offers;
    document.getElementById("d-rate").textContent     = `${data.redemption_rate}%`;
    document.getElementById("drawer-merchant-name").textContent = selectedMerchant?.name ?? "";

    // Rate bar
    const barLabel = document.getElementById("d-rate-bar-label");
    barLabel.textContent = `${data.redemption_rate}%`;
    setTimeout(() => {
      document.getElementById("d-rate-bar").style.width = `${Math.min(data.redemption_rate, 100)}%`;
    }, 100);

    // Status breakdown
    renderStatusBreakdown(
      data.total_offers - data.redeemed_offers,
      data.redeemed_offers,
      data.total_offers
    );

    // Geofences + map dots
    renderDrawerGeofences(currentGeofences);
    renderDrawerMapDots(currentGeofences);

  } catch (_) { /* silent */ }
}

function renderStatusBreakdown(pending, redeemed, total) {
  const el = document.getElementById("status-breakdown");
  const items = [
    { label: "Pending",  value: pending,  color: "#f59e0b", pct: total ? pending/total*100 : 0 },
    { label: "Redeemed", value: redeemed, color: "#34d399", pct: total ? redeemed/total*100 : 0 },
  ];
  el.innerHTML = '<div style="font-size:10px;color:#475569;letter-spacing:2px;margin-bottom:12px;">OFFER STATUS BREAKDOWN</div>' +
    items.map((item, i) => `
      <div class="analytics-row" style="margin-bottom:14px;animation-delay:${i*0.07}s;">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:5px;">
          <span style="font-size:12px;color:#94a3b8;">${item.label}</span>
          <span style="font-size:12px;color:${item.color};font-weight:500;">${item.value}</span>
        </div>
        <div style="height:5px;border-radius:3px;background:#ffffff08;overflow:hidden;">
          <div class="spend-bar" style="height:100%;border-radius:3px;background:${item.color};box-shadow:0 0 8px ${item.color}60;transition-delay:${0.1+i*0.08}s;width:${item.pct}%"></div>
        </div>
      </div>`).join("");
}

function renderDrawerGeofences(geofences) {
  const el = document.getElementById("drawer-geofences");
  if (!geofences.length) {
    el.innerHTML = '<div style="font-size:12px;color:#334155;font-style:italic;">No geofences configured.</div>';
    return;
  }
  el.innerHTML = geofences.map((g, i) => `
    <div class="analytics-row" style="background:#ffffff04;border:1px solid #1e3a5f40;border-radius:10px;padding:12px 14px;animation-delay:${i*0.06}s;">
      <div style="display:flex;justify-content:space-between;align-items:center;">
        <div style="display:flex;align-items:center;gap:8px;">
          <div style="width:8px;height:8px;border-radius:50%;background:${g.is_active ? '#7c3aed' : '#374151'};box-shadow:${g.is_active ? '0 0 6px #7c3aedaa' : 'none'};flex-shrink:0;"></div>
          <div>
            <div style="font-size:12px;color:#e2e8f0;">${g.name}</div>
            <div style="font-size:10px;color:#475569;margin-top:2px;">${g.radius_meters}m radius · ${g.active_hours_start}–${g.active_hours_end}</div>
          </div>
        </div>
        <div style="text-align:right;">
          <div style="font-size:11px;color:#a78bfa;">Cap ${g.max_discount}%</div>
          <div style="font-size:9px;color:${g.is_active ? '#34d399' : '#475569'};margin-top:2px;letter-spacing:1px;">${g.is_active ? 'ACTIVE' : 'INACTIVE'}</div>
        </div>
      </div>
      ${g.discount_tiers?.length ? `
        <div style="display:flex;gap:6px;margin-top:10px;flex-wrap:wrap;">
          ${g.discount_tiers.map(t => `<span style="font-size:9px;background:#7c3aed18;border:1px solid #7c3aed30;border-radius:4px;padding:2px 7px;color:#a78bfa;letter-spacing:0.5px;">${t.tier_type} ${t.percent}%</span>`).join("")}
        </div>` : ""}
    </div>`).join("");
}

const DOT_POSITIONS = [
  {top:"42%",left:"48%"},{top:"60%",left:"30%"},{top:"25%",left:"58%"},
  {top:"70%",left:"55%"},{top:"35%",left:"22%"},{top:"55%",left:"68%"},
  {top:"20%",left:"42%"},{top:"78%",left:"38%"},
];
const DOT_COLORS = ["#7c3aed","#3b82f6","#10b981","#f59e0b","#ef4444","#ec4899","#06b6d4","#8b5cf6"];

function renderDrawerMapDots(geofences) {
  const wrap = document.getElementById("drawer-map-dots");
  wrap.innerHTML = "";
  geofences.forEach((g, i) => {
    const pos   = DOT_POSITIONS[i % DOT_POSITIONS.length];
    const color = DOT_COLORS[i % DOT_COLORS.length];
    const dot   = document.createElement("div");
    dot.style.cssText = `position:absolute;top:${pos.top};left:${pos.left};transform:translate(-50%,-50%);`;
    dot.innerHTML = `
      <div style="position:relative;width:10px;height:10px;">
        <div style="width:10px;height:10px;border-radius:50%;background:${color};box-shadow:0 0 8px ${color};"></div>
        <div class="map-dot-ring" style="position:absolute;width:24px;height:24px;border-radius:50%;border:1px solid ${color}60;top:50%;left:50%;"></div>
      </div>`;
    wrap.appendChild(dot);
  });

  const cards = document.getElementById("drawer-location-cards");
  cards.innerHTML = geofences.map((g, i) => {
    const color = DOT_COLORS[i % DOT_COLORS.length];
    return `
      <div class="analytics-row" style="display:flex;align-items:center;gap:12px;padding:12px 14px;
           background:#ffffff04;border:1px solid #1e3a5f30;border-radius:10px;animation-delay:${i*0.06}s;">
        <div style="width:36px;height:36px;border-radius:9px;background:${color}18;border:1px solid ${color}40;
             display:flex;align-items:center;justify-content:center;font-size:16px;flex-shrink:0;">📍</div>
        <div style="flex:1;min-width:0;">
          <div style="font-size:12px;color:#e2e8f0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">${g.name}</div>
          <div style="font-size:10px;color:#475569;margin-top:2px;">${g.lat.toFixed(4)}, ${g.lng.toFixed(4)} · ${g.radius_meters}m</div>
        </div>
        <div style="text-align:right;flex-shrink:0;">
          <div style="font-size:11px;color:${color};">up to ${g.max_discount}%</div>
          <div style="width:8px;height:8px;border-radius:50%;background:${g.is_active ? '#34d399' : '#374151'};margin-left:auto;margin-top:4px;"></div>
        </div>
      </div>`;
  }).join("");
}

/* ── Drawer feed ─────────────────────────────────────────────────────────── */
function appendDrawerFeedItem(data, userId) {
  feedEvents.unshift({ data, userId, time: new Date().toLocaleTimeString() });
  if (feedEvents.length > 50) feedEvents.pop();
  if (drawerOpen && activeTab === "feed") renderDrawerFeed();
}

function renderDrawerFeed() {
  const el = document.getElementById("drawer-live-feed");
  if (!feedEvents.length) {
    el.innerHTML = '<div style="font-size:12px;color:#334155;font-style:italic;">Trigger a checkin to see events here…</div>';
    return;
  }
  el.innerHTML = feedEvents.map((ev, i) => `
    <div class="analytics-row" style="display:flex;align-items:center;gap:10px;padding:10px 12px;
         background:#ffffff04;border-left:2px solid ${ev.data.enabled ? '#7c3aed' : '#374151'};border-radius:0 8px 8px 0;animation-delay:${i*0.04}s;">
      <div style="flex:1;">
        <div style="display:flex;justify-content:space-between;align-items:center;">
          <span style="font-size:11px;color:${ev.data.enabled ? '#a78bfa' : '#64748b'};">${ev.userId}</span>
          <span style="font-size:10px;color:#334155;">${ev.time}</span>
        </div>
        <div style="font-size:11px;margin-top:3px;color:${ev.data.enabled ? '#34d399' : '#475569'};">
          ${ev.data.enabled ? `✓ ${ev.data.discount_percent}% off · ${ev.data.geofence_name ?? ''}` : `✗ ${ev.data.message}`}
        </div>
      </div>
    </div>`).join("");
}

/* ── Tab switching ───────────────────────────────────────────────────────── */
function switchTab(tab) {
  activeTab = tab;
  ["overview","locations","feed"].forEach(t => {
    document.getElementById(`tab-${t}`).classList.toggle("active", t === tab);
    document.getElementById(`tab-content-${t}`).style.display = t === tab ? "block" : "none";
  });
  if (tab === "feed") renderDrawerFeed();
}

/* ── Drawer open / close ─────────────────────────────────────────────────── */
function openAnalyticsDrawer() {
  drawerOpen = true;
  document.getElementById("analytics-drawer").classList.add("open");
  if (selectedMerchant) loadAnalytics(selectedMerchant.id);
}

function closeAnalyticsDrawer() {
  drawerOpen = false;
  document.getElementById("analytics-drawer").classList.remove("open");
}

function handleDrawerBackdropClick(e) {
  if (e.target === document.getElementById("analytics-drawer")) closeAnalyticsDrawer();
}

/* ── Status indicator ────────────────────────────────────────────────────── */
function setStatus(state) {
  const el = document.getElementById("api-status");
  el.innerHTML = state === "online"
    ? `<span class="w-2 h-2 rounded-full bg-green-400 inline-block"></span> API online`
    : `<span class="w-2 h-2 rounded-full bg-red-500 inline-block"></span> API offline`;
}

/* ── Screen navigation ───────────────────────────────────────────────────── */
function goHome() {
  document.getElementById("screen-landing").classList.remove("hidden");
  document.getElementById("screen-merchant").classList.add("hidden");
  document.getElementById("back-btn").classList.add("hidden");
}

function selectRole(role) {
  document.getElementById("screen-landing").classList.add("hidden");
  document.getElementById("screen-merchant").classList.add("hidden");
  document.getElementById("back-btn").classList.remove("hidden");

  if (role === "merchant") {
    document.getElementById("screen-merchant").classList.remove("hidden");
    setTimeout(initMerchantMap, 80);
  } else {
    if (!mapInitialized) {
      initMap();
      loadMerchants();
      mapInitialized = true;
    } else {
      map.resize();
      reloadMerchants();
    }
  }
}

/* ── Merchant mini-map (Leaflet) ─────────────────────────────────────────── */
function initMerchantMap() {
  if (merchantMap) {
    merchantMap.invalidateSize();
    return;
  }
  merchantMap = L.map("m-map", { zoomControl: true }).setView([40.1130, -88.2350], 13);
  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    attribution: "© OpenStreetMap contributors",
    maxZoom: 19,
  }).addTo(merchantMap);

  merchantMap.on("click", (e) => {
    const { lat, lng } = e.latlng;
    document.getElementById("m-lat").value = lat.toFixed(6);
    document.getElementById("m-lng").value = lng.toFixed(6);
    if (merchantMapMarker) merchantMapMarker.remove();
    merchantMapMarker = L.circleMarker([lat, lng], {
      radius: 6, color: "#a78bfa", fillColor: "#7c3aed", fillOpacity: 1, weight: 2,
    }).addTo(merchantMap).bindPopup(`${lat.toFixed(5)}, ${lng.toFixed(5)}`).openPopup();
  });
}

/* ── Geocode address → pin on mini-map ───────────────────────────────────── */
async function geocodeAddress() {
  const address = document.getElementById("m-address").value.trim();
  const errorEl = document.getElementById("m-geo-error");
  const btn     = document.getElementById("m-geo-btn");
  errorEl.classList.add("hidden");
  if (!address) return;

  btn.textContent = "Finding…";
  btn.disabled    = true;

  try {
    const url  = `https://nominatim.openstreetmap.org/search?q=${encodeURIComponent(address)}&format=json&limit=1`;
    const data = await (await fetch(url, { headers: { "Accept-Language": "en" } })).json();

    if (!data.length) {
      errorEl.textContent = "Address not found. Try a more specific address.";
      errorEl.classList.remove("hidden");
      return;
    }

    const lat = parseFloat(data[0].lat);
    const lng = parseFloat(data[0].lon);

    document.getElementById("m-lat").value = lat;
    document.getElementById("m-lng").value = lng;

    merchantMap.setView([lat, lng], 17);
    if (merchantMapMarker) merchantMapMarker.remove();
    merchantMapMarker = L.circleMarker([lat, lng], {
      radius: 6, color: "#a78bfa", fillColor: "#7c3aed", fillOpacity: 1, weight: 2,
    }).addTo(merchantMap).bindPopup(data[0].display_name).openPopup();
  } catch (_) {
    errorEl.textContent = "Geocoding failed. Check your connection and try again.";
    errorEl.classList.remove("hidden");
  } finally {
    btn.textContent = "Find on Map";
    btn.disabled    = false;
  }
}

/* ── Reload merchant list (after new merchant added) ─────────────────────── */
async function reloadMerchants() {
  const sel = document.getElementById("merchant-select");
  sel.innerHTML = '<option value="">— select a merchant —</option>';
  merchants = [];
  clearGeofenceCircles();
  selectedMerchant = null;
  document.getElementById("merchant-info").classList.add("hidden");
  document.getElementById("checkin-btn").disabled = true;
  document.getElementById("analytics-pill-wrap").classList.add("hidden");
  feedEvents = [];
  await loadMerchants();
}

/* ── Merchant registration form ──────────────────────────────────────────── */
async function submitMerchantForm() {
  const name        = document.getElementById("m-name").value.trim();
  const lat         = parseFloat(document.getElementById("m-lat").value);
  const lng         = parseFloat(document.getElementById("m-lng").value);
  const radius      = parseFloat(document.getElementById("m-radius").value) || 75;
  const percent     = parseInt(document.getElementById("m-percent").value);
  const description = document.getElementById("m-description").value.trim();
  const timeline    = document.getElementById("m-timeline").value;
  const errorEl     = document.getElementById("m-error");
  const successEl   = document.getElementById("m-success");
  const submitBtn   = document.getElementById("m-submit");

  errorEl.classList.add("hidden");
  successEl.classList.add("hidden");

  if (!name || !description) {
    errorEl.textContent = "Company name and discount description are required.";
    errorEl.classList.remove("hidden");
    return;
  }
  if (isNaN(lat) || isNaN(lng)) {
    errorEl.textContent = 'Enter an address and click "Find on Map" to set your location.';
    errorEl.classList.remove("hidden");
    return;
  }
  if (isNaN(percent) || percent < 1 || percent > 100) {
    errorEl.textContent = "Enter a discount % between 1 and 100.";
    errorEl.classList.remove("hidden");
    return;
  }

  submitBtn.disabled = true;
  submitBtn.textContent = "Submitting…";

  try {
    // POST 1 — create merchant (name + id in merchants table)
    const email = `${name.toLowerCase().replace(/\s+/g, ".")}@demo.geooffer.com`;
    let merchant;

    const mRes = await fetch(`${API}/v1/merchants/`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name, email }),
    });

    if (mRes.status === 409) {
      const all = await (await fetch(`${API}/v1/merchants/`)).json();
      merchant  = all.find(m => m.name === name);
      if (!merchant) throw new Error("Merchant exists but could not be found.");
    } else if (!mRes.ok) {
      throw new Error((await mRes.json()).detail ?? "Failed to register merchant.");
    } else {
      merchant = await mRes.json();
    }

    // POST 2 — create geofence (shows on customer map)
    const gRes = await fetch(`${API}/v1/merchants/${merchant.id}/geofences`, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-API-Key": merchant.api_key },
      body: JSON.stringify({
        name: `${name} Entrance`,
        lat, lng,
        radius_meters: radius,
        max_discount: percent,
        discount_tiers: [
          { type: "new_customer",     percent },
          { type: "frequent_visitor", percent },
          { type: "lapsed_customer",  percent },
          { type: "regular", percent: Math.max(5, Math.floor(percent * 0.6)) },
        ],
        active_hours: { start: "06:00", end: "23:00" },
      }),
    });
    if (!gRes.ok) throw new Error((await gRes.json()).detail ?? "Failed to create geofence.");

    // POST 3 — store discount description (company_id + description in promotions table)
    const pRes = await fetch(`${API}/v1/promotions/`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ company_id: merchant.id, description, timeline }),
    });
    if (!pRes.ok) throw new Error((await pRes.json()).detail ?? "Failed to save promotion.");

    document.getElementById("m-success-detail").textContent =
      `Company ID: ${merchant.id} · Now visible on the customer map.`;
    successEl.classList.remove("hidden");

    if (mapInitialized) reloadMerchants();

    // Reset form
    ["m-name", "m-address", "m-percent", "m-description"].forEach(id => {
      document.getElementById(id).value = "";
    });
    document.getElementById("m-lat").value = "";
    document.getElementById("m-lng").value = "";
    if (merchantMapMarker) { merchantMapMarker.remove(); merchantMapMarker = null; }
  } catch (e) {
    errorEl.textContent = e.message;
    errorEl.classList.remove("hidden");
  } finally {
    submitBtn.disabled = false;
    submitBtn.textContent = "Submit";
  }
}

/* ── Bootstrap ───────────────────────────────────────────────────────────── */
document.addEventListener("DOMContentLoaded", () => {
  document.getElementById("merchant-select").addEventListener("change", e =>
    onMerchantChange(e.target.value)
  );
  document.getElementById("checkin-btn").addEventListener("click", triggerCheckin);
  document.getElementById("clear-feed").addEventListener("click", () => {
    document.getElementById("checkin-feed").innerHTML = "";
    feedEvents = [];
  });
});