/* ── Config ──────────────────────────────────────────────────────────────── */
const API = "http://localhost:8000";

/* ── State ───────────────────────────────────────────────────────────────── */
let map, pinMarker;
let merchants      = [];
let geofenceCircles = [];
let selectedMerchant = null;

/* ── Map init ────────────────────────────────────────────────────────────── */
function initMap() {
  // Centre on downtown Champaign
  map = L.map("map", { zoomControl: false }).setView([40.1130, -88.2350], 15);

  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    attribution: "© OpenStreetMap contributors",
    maxZoom: 19,
  }).addTo(map);

  L.control.zoom({ position: "bottomright" }).addTo(map);

  map.on("click", (e) => {
    const { lat, lng } = e.latlng;
    document.getElementById("sim-lat").value = lat.toFixed(6);
    document.getElementById("sim-lng").value = lng.toFixed(6);
    placePinMarker(lat, lng);
  });
}

function placePinMarker(lat, lng) {
  if (pinMarker) pinMarker.remove();
  pinMarker = L.circleMarker([lat, lng], {
    radius: 6,
    color: "#a78bfa",
    fillColor: "#7c3aed",
    fillOpacity: 1,
    weight: 2,
  }).addTo(map).bindPopup(`📍 ${lat.toFixed(5)}, ${lng.toFixed(5)}`).openPopup();
}

/* ── Geofence circles ────────────────────────────────────────────────────── */
function clearGeofenceCircles() {
  geofenceCircles.forEach((c) => c.remove());
  geofenceCircles = [];
}

function drawGeofences(geofences, merchantName) {
  clearGeofenceCircles();
  geofences.forEach((g) => {
    const circle = L.circle([g.lat, g.lng], {
      radius: g.radius_meters,
      color: "#7c3aed",
      fillColor: "#7c3aed",
      fillOpacity: g.is_active ? 0.15 : 0.04,
      weight: g.is_active ? 2 : 1,
      dashArray: g.is_active ? null : "4 4",
      className: "geofence-circle",
    })
      .addTo(map)
      .bindPopup(buildGeofencePopup(g, merchantName));

    // Small label at centre
    L.marker([g.lat, g.lng], {
      icon: L.divIcon({
        className: "",
        html: `<div style="color:#a78bfa;font-size:11px;font-family:monospace;
                    background:#1a1a2e;border:1px solid #4c1d95;border-radius:4px;
                    padding:1px 5px;white-space:nowrap;">${merchantName}</div>`,
        iconAnchor: [0, -12],
      }),
    }).addTo(map);

    geofenceCircles.push(circle);
  });

  if (geofences.length > 0) {
    map.setView([geofences[0].lat, geofences[0].lng], 17);
  }

  buildJumpButtons(geofences);
}

function buildGeofencePopup(g, merchantName) {
  const tiers = g.discount_tiers
    .map((t) => `<li>${t.tier_type}: <b>${t.percent}%</b> off</li>`)
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
  geofences.forEach((g) => {
    const btn = document.createElement("button");
    btn.textContent = `⌖ ${g.name.split(" ")[0]}`;
    btn.className =
      "text-[10px] bg-surface border border-border rounded px-2 py-0.5 text-brand-light hover:border-brand transition-colors";
    btn.onclick = () => {
      document.getElementById("sim-lat").value = g.lat.toFixed(6);
      document.getElementById("sim-lng").value = g.lng.toFixed(6);
      placePinMarker(g.lat, g.lng);
      map.setView([g.lat, g.lng], 18);
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
    merchants.forEach((m) => {
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
    document.getElementById("analytics-panel").classList.add("hidden");
    return;
  }

  selectedMerchant = merchants.find((m) => m.id === merchantId);

  document.getElementById("info-id").textContent  = selectedMerchant.id;
  document.getElementById("info-key").textContent = selectedMerchant.api_key;
  document.getElementById("merchant-info").classList.remove("hidden");
  document.getElementById("checkin-btn").disabled = false;

  // Load and draw geofences
  try {
    const res = await fetch(`${API}/v1/merchants/${merchantId}/geofences`);
    const geofences = await res.json();
    drawGeofences(geofences, selectedMerchant.name);
  } catch (e) {
    console.error("Failed to load geofences:", e);
  }

  loadAnalytics(merchantId);
}

/* ── Checkin ─────────────────────────────────────────────────────────────── */
async function triggerCheckin() {
  if (!selectedMerchant) return;

  const lat     = parseFloat(document.getElementById("sim-lat").value);
  const lng     = parseFloat(document.getElementById("sim-lng").value);
  const userId  = document.getElementById("user-id").value.trim() || "user_demo_01";

  if (isNaN(lat) || isNaN(lng)) {
    alert("Click the map or enter coordinates first.");
    return;
  }

  const btn = document.getElementById("checkin-btn");
  btn.disabled = true;
  btn.textContent = "Processing…";

  try {
    const res = await fetch(`${API}/v1/checkins`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        user_id: userId,
        lat,
        lng,
        merchant_id: selectedMerchant.id,
      }),
    });

    const data = await res.json();
    renderOfferResult(data, userId, lat, lng);
    appendFeedItem(data, userId);
    loadAnalytics(selectedMerchant.id);

  } catch (e) {
    renderError(e.message);
  } finally {
    btn.disabled = false;
    btn.textContent = "Trigger Checkin";
  }
}

/* ── Render ──────────────────────────────────────────────────────────────── */
function renderOfferResult(data, userId, lat, lng) {
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
        <div class="text-gray-600 text-[10px] mt-1">${lat.toFixed(5)}, ${lng.toFixed(5)}</div>
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

  // Keep feed at max 30 items
  while (feed.children.length > 30) feed.removeChild(feed.lastChild);
}

/* ── Analytics ───────────────────────────────────────────────────────────── */
async function loadAnalytics(merchantId) {
  try {
    const res  = await fetch(`${API}/v1/merchants/${merchantId}/analytics`);
    const data = await res.json();
    document.getElementById("a-total").textContent   = data.total_offers;
    document.getElementById("a-redeemed").textContent = data.redeemed_offers;
    document.getElementById("a-rate").textContent    = `${data.redemption_rate}%`;
    document.getElementById("analytics-panel").classList.remove("hidden");
  } catch (_) { /* silent */ }
}

/* ── Status indicator ────────────────────────────────────────────────────── */
function setStatus(state) {
  const el  = document.getElementById("api-status");
  const dot = el.querySelector("span");
  if (state === "online") {
    dot.className = "w-2 h-2 rounded-full bg-green-400 inline-block";
    el.innerHTML  = `<span class="w-2 h-2 rounded-full bg-green-400 inline-block"></span> API online`;
  } else {
    dot.className = "w-2 h-2 rounded-full bg-red-500 inline-block";
    el.innerHTML  = `<span class="w-2 h-2 rounded-full bg-red-500 inline-block"></span> API offline`;
  }
}

/* ── Bootstrap ───────────────────────────────────────────────────────────── */
document.addEventListener("DOMContentLoaded", async () => {
  initMap();
  await loadMerchants();

  document.getElementById("merchant-select").addEventListener("change", (e) =>
    onMerchantChange(e.target.value)
  );

  document.getElementById("checkin-btn").addEventListener("click", triggerCheckin);

  document.getElementById("clear-feed").addEventListener("click", () => {
    document.getElementById("checkin-feed").innerHTML = "";
  });
});
