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
let session           = null;   // { id, username, role, merchant_id }
let userLat           = null;
let userLng           = null;

/* ── Session management ──────────────────────────────────────────────────── */
function saveSession(user) {
  session = user;
  localStorage.setItem("goe_session", JSON.stringify(user));
}

function loadSession() {
  try {
    const raw = localStorage.getItem("goe_session");
    return raw ? JSON.parse(raw) : null;
  } catch (_) { return null; }
}

function clearSession() {
  session = null;
  localStorage.removeItem("goe_session");
}

/* ── Auth screen ─────────────────────────────────────────────────────────── */
let authMode = "login"; // "login" | "register"

function showAuthTab(mode) {
  authMode = mode;
  const isLogin = mode === "login";

  document.getElementById("tab-login").className =
    `flex-1 pb-2 text-sm font-semibold transition-colors border-b-2 ${
      isLogin ? "text-white border-brand" : "text-gray-500 border-transparent hover:text-white"
    }`;
  document.getElementById("tab-register").className =
    `flex-1 pb-2 text-sm font-semibold transition-colors border-b-2 ${
      !isLogin ? "text-white border-brand" : "text-gray-500 border-transparent hover:text-white"
    }`;
  document.getElementById("auth-submit").textContent = isLogin ? "Log In" : "Register";
  document.getElementById("auth-error").classList.add("hidden");
}

async function submitAuth() {
  const username = document.getElementById("auth-username").value.trim();
  const password = document.getElementById("auth-password").value;
  const errorEl  = document.getElementById("auth-error");
  errorEl.classList.add("hidden");

  if (!username || !password) {
    errorEl.textContent = "Username and password are required.";
    errorEl.classList.remove("hidden");
    return;
  }

  const btn = document.getElementById("auth-submit");
  btn.disabled = true;
  btn.textContent = "…";

  try {
    const endpoint = authMode === "register" ? "/v1/auth/register" : "/v1/auth/login";
    const res = await fetch(`${API}${endpoint}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, password }),
    });

    if (!res.ok) {
      const data = await res.json();
      throw new Error(data.detail ?? "Authentication failed.");
    }

    const user = await res.json();
    saveSession(user);
    showPostLogin(user);
  } catch (e) {
    errorEl.textContent = e.message;
    errorEl.classList.remove("hidden");
  } finally {
    btn.disabled = false;
    btn.textContent = authMode === "register" ? "Register" : "Log In";
  }
}

function showPostLogin(user) {
  document.getElementById("screen-login").classList.add("hidden");
  document.getElementById("screen-landing").classList.remove("hidden");
  document.getElementById("logged-in-label").textContent = `@${user.username}`;
  document.getElementById("logged-in-label").classList.remove("hidden");
  document.getElementById("logout-btn").classList.remove("hidden");
}

function logout() {
  clearSession();
  // Reset UI
  document.getElementById("screen-landing").classList.add("hidden");
  document.getElementById("screen-merchant").classList.add("hidden");
  document.getElementById("main-content").classList.add("hidden");
  document.getElementById("back-btn").classList.add("hidden");
  document.getElementById("logged-in-label").classList.add("hidden");
  document.getElementById("logout-btn").classList.add("hidden");
  document.getElementById("auth-username").value = "";
  document.getElementById("auth-password").value = "";
  document.getElementById("auth-error").classList.add("hidden");
  showAuthTab("login");
  document.getElementById("screen-login").classList.remove("hidden");
}

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

    // ── Map click → place pin + optionally auto-trigger checkin ───────────
    map.on("click", (e) => {
      const { lng, lat } = e.lngLat;
      document.getElementById("sim-lat").value = lat.toFixed(6);
      document.getElementById("sim-lng").value = lng.toFixed(6);
      placePinMarker(lat, lng);

      // Auto-trigger checkin if clicking inside a geofence while merchant selected
      const hit = map.queryRenderedFeatures(e.point, { layers: ["geofences-fill"] });
      if (hit.length && selectedMerchant) {
        triggerCheckin();
      }
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

/* ── Location / radius ───────────────────────────────────────────────────── */
function requestLocation() {
  const statusEl = document.getElementById("location-status");
  const btn      = document.getElementById("locate-btn");
  if (!navigator.geolocation) {
    statusEl.textContent = "Geolocation not supported by your browser.";
    return;
  }
  btn.textContent = "Locating…";
  btn.disabled    = true;
  navigator.geolocation.getCurrentPosition(
    (pos) => {
      userLat = pos.coords.latitude;
      userLng = pos.coords.longitude;
      statusEl.textContent = `📍 ${userLat.toFixed(5)}, ${userLng.toFixed(5)}`;
      btn.textContent = "📍 Location Set";
      btn.disabled    = false;
      // Pan map to user location
      if (map) map.flyTo({ center: [userLng, userLat], zoom: 15, duration: 800 });
    },
    (err) => {
      statusEl.textContent = "Could not get location: " + err.message;
      btn.textContent = "📍 Use My Location";
      btn.disabled    = false;
    }
  );
}

async function applyRadius() {
  if (userLat === null || userLng === null) {
    document.getElementById("location-status").textContent =
      'Click "Use My Location" first.';
    return;
  }
  const radius = parseFloat(document.getElementById("radius-input").value) || 1000;
  try {
    const res  = await fetch(`${API}/v1/merchants/nearby?lat=${userLat}&lng=${userLng}&radius_meters=${radius}`);
    const list = await res.json();
    populateMerchantSelect(list);
  } catch (e) {
    console.error("Nearby fetch failed:", e);
  }
}

/* ── Merchants ───────────────────────────────────────────────────────────── */
function populateMerchantSelect(list) {
  merchants = list;
  const sel = document.getElementById("merchant-select");
  sel.innerHTML = '<option value="">— select a merchant —</option>';

  list.forEach(m => {
    const opt = document.createElement("option");
    opt.value = m.id;
    opt.textContent = m.name;
    sel.appendChild(opt);
  });

  // Switch to scrollable listbox mode when there are many merchants
  if (list.length > 10) {
    sel.size = 8;
  } else {
    sel.size = 1;
  }
}

async function loadMerchants() {
  try {
    const res  = await fetch(`${API}/v1/merchants/`);
    if (!res.ok) throw new Error(res.statusText);
    const list = await res.json();
    populateMerchantSelect(list);
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
    document.getElementById("checkin-btn").disabled = true;
    document.getElementById("analytics-panel").classList.add("hidden");
    return;
  }

  selectedMerchant = merchants.find(m => m.id === merchantId);
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
  const userId = (session && session.id) ? session.id : "user_demo_01";

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
    appendFeedItem(data, session ? session.username : userId);
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

function appendFeedItem(data, displayName) {
  const feed = document.getElementById("checkin-feed");
  const li   = document.createElement("li");
  const time = new Date().toLocaleTimeString();

  li.className = `feed-item ${data.enabled ? "triggered" : "no-trigger"}`;
  li.innerHTML = data.enabled
    ? `<span class="text-brand-light">${displayName}</span>
       → <b class="text-green-400">${data.discount_percent}% off</b>
       <span class="text-gray-500 float-right">${time}</span>`
    : `<span class="text-gray-400">${displayName}</span>
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
    document.getElementById("a-total").textContent    = data.total_offers;
    document.getElementById("a-redeemed").textContent = data.redeemed_offers;
    document.getElementById("a-rate").textContent     = `${data.redemption_rate}%`;
    document.getElementById("analytics-panel").classList.remove("hidden");
  } catch (_) { /* silent */ }
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
  document.getElementById("main-content").classList.add("hidden");
  document.getElementById("back-btn").classList.add("hidden");
}

function selectRole(role) {
  document.getElementById("screen-landing").classList.add("hidden");
  document.getElementById("screen-merchant").classList.add("hidden");
  document.getElementById("back-btn").classList.remove("hidden");

  if (role === "merchant") {
    // Check if this user already registered a merchant
    if (session && session.merchant_id) {
      const alreadyEl  = document.getElementById("m-already-registered");
      const detailEl   = document.getElementById("m-already-detail");
      detailEl.textContent = `Company ID: ${session.merchant_id} · You have already registered a merchant with this account.`;
      alreadyEl.classList.remove("hidden");
      document.getElementById("m-submit").disabled = true;
    }
    document.getElementById("screen-merchant").classList.remove("hidden");
    setTimeout(initMerchantMap, 80);
  } else {
    document.getElementById("main-content").classList.remove("hidden");
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
  clearGeofenceCircles();
  selectedMerchant = null;
  document.getElementById("checkin-btn").disabled = true;
  document.getElementById("analytics-panel").classList.add("hidden");
  await loadMerchants();
}

/* ── Merchant registration form ──────────────────────────────────────────── */
async function submitMerchantForm() {
  // Block re-registration if already linked
  if (session && session.merchant_id) {
    document.getElementById("m-error").textContent =
      "Your account is already linked to a merchant.";
    document.getElementById("m-error").classList.remove("hidden");
    return;
  }

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
    // POST 1 — create merchant
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

    // POST 2 — create geofence
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

    // POST 3 — save promotion description
    const pRes = await fetch(`${API}/v1/promotions/`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ company_id: merchant.id, description, timeline }),
    });
    if (!pRes.ok) throw new Error((await pRes.json()).detail ?? "Failed to save promotion.");

    // PATCH — link merchant to logged-in user account
    if (session) {
      await fetch(`${API}/v1/auth/me/${session.id}/link-merchant?merchant_id=${merchant.id}`, {
        method: "PATCH",
      });
      session.merchant_id = merchant.id;
      saveSession(session);
    }

    document.getElementById("m-success-detail").textContent =
      `Company ID: ${merchant.id} · Now visible on the customer map.`;
    successEl.classList.remove("hidden");
    submitBtn.disabled = true; // prevent double-submit

    if (mapInitialized) reloadMerchants();

    // Reset form fields
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
    if (submitBtn.textContent === "Submitting…") {
      submitBtn.disabled = false;
      submitBtn.textContent = "Submit";
    }
  }
}

/* ── Bootstrap ───────────────────────────────────────────────────────────── */
document.addEventListener("DOMContentLoaded", async () => {
  document.getElementById("merchant-select").addEventListener("change", e =>
    onMerchantChange(e.target.value)
  );
  document.getElementById("checkin-btn").addEventListener("click", triggerCheckin);
  document.getElementById("clear-feed").addEventListener("click", () => {
    document.getElementById("checkin-feed").innerHTML = "";
  });

  // Allow Enter key to submit auth form
  ["auth-username", "auth-password"].forEach(id => {
    document.getElementById(id).addEventListener("keydown", e => {
      if (e.key === "Enter") submitAuth();
    });
  });

  // Restore session from localStorage
  const saved = loadSession();
  if (saved) {
    try {
      // Verify session is still valid
      const res = await fetch(`${API}/v1/auth/me/${saved.id}`);
      if (res.ok) {
        const user = await res.json();
        saveSession(user);
        showPostLogin(user);
        return;
      }
    } catch (_) { /* network error — fall through to login */ }
    clearSession();
  }
  // Show login screen (already visible by default from HTML)
});
