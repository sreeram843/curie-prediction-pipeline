const state = {
  alerts: [],
  selectedId: null,
  hideAck: false,
};

const listEl = document.getElementById("alertList");
const detailEl = document.getElementById("detail");
const detailEmpty = document.getElementById("detailEmpty");
const metricsEl = document.getElementById("metrics");
const hideAckEl = document.getElementById("hideAck");

function fmtTime(iso) {
  if (!iso) return "—";
  const d = new Date(iso);
  return d.toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

async function fetchJson(url, options) {
  const res = await fetch(url, options);
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || res.statusText);
  }
  return res.json();
}

async function loadMetrics() {
  const m = await fetchJson("/metrics");
  metricsEl.innerHTML = `
    <div class="metric"><strong>${m.open_alerts}</strong><span>Open</span></div>
    <div class="metric"><strong>${m.acknowledged_alerts}</strong><span>Acked</span></div>
    <div class="metric"><strong>${m.by_tier.critical || 0}</strong><span>Critical</span></div>
  `;
}

async function loadAlerts() {
  const params = new URLSearchParams({
    include_acknowledged: String(!state.hideAck),
    limit: "100",
  });
  state.alerts = await fetchJson(`/alerts?${params}`);
  renderList();
  if (state.selectedId) {
    const still = state.alerts.find((a) => a.alert_id === state.selectedId);
    if (still) renderDetail(still);
    else {
      state.selectedId = state.alerts[0]?.alert_id || null;
      if (state.selectedId) {
        renderDetail(state.alerts[0]);
      } else {
        detailEl.classList.add("hidden");
        detailEmpty.classList.remove("hidden");
      }
    }
  }
}

function renderList() {
  listEl.innerHTML = "";
  if (!state.alerts.length) {
    listEl.innerHTML = `<li class="empty">No alerts match this filter.</li>`;
    return;
  }
  for (const alert of state.alerts) {
    const li = document.createElement("li");
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = `alert-item${alert.acknowledged ? " acked" : ""}${
      alert.alert_id === state.selectedId ? " active" : ""
    }`;
    btn.innerHTML = `
      <div class="row">
        <span class="patient">${alert.patient_id}</span>
        <span class="tier ${alert.tier}">${alert.tier}</span>
      </div>
      <div class="meta">Score ${alert.score ?? "—"} · ${fmtTime(alert.event_time)}${
        alert.acknowledged ? " · acknowledged" : ""
      }</div>
    `;
    btn.addEventListener("click", () => {
      state.selectedId = alert.alert_id;
      renderList();
      renderDetail(alert);
    });
    li.appendChild(btn);
    listEl.appendChild(li);
  }
}

function renderDetail(alert) {
  detailEmpty.classList.add("hidden");
  detailEl.classList.remove("hidden");
  const components = (alert.component_breakdown || [])
    .map((c) => {
      if (c.missing) {
        return `<li class="missing">${c.name} — missing</li>`;
      }
      return `<li><strong>${c.name}</strong>: ${c.points} pts · ${(c.evidence_ids || []).join(", ") || "no evidence ids"}</li>`;
    })
    .join("");
  const evidence = (alert.evidence_ids || [])
    .map((e) => `<li><code>${e}</code></li>`)
    .join("");

  detailEl.innerHTML = `
    <h3>${alert.patient_id}</h3>
    <div class="meta">${alert.alert_id}</div>
    <div class="badges">
      <span class="badge tier ${alert.tier}">${alert.tier}</span>
      <span class="badge">score ${alert.score ?? "—"}</span>
      <span class="badge">${alert.completeness}</span>
      <span class="badge">${alert.governance_path}</span>
      <span class="badge">rule ${alert.rule_bundle_id}@${alert.rule_version}</span>
    </div>
    <p class="meta">Event ${fmtTime(alert.event_time)} · Encounter ${alert.encounter_id || "—"}</p>
    <div class="section-label">Component breakdown</div>
    <ul class="breakdown">${components || "<li class='missing'>No components</li>"}</ul>
    <div class="section-label">Evidence IDs</div>
    <ul class="evidence">${evidence || "<li class='missing'>None</li>"}</ul>
    ${
      alert.acknowledged
        ? `<div class="ack-note">Acknowledged ${fmtTime(alert.acknowledged_at)}${
            alert.acknowledge_note ? ` — ${alert.acknowledge_note}` : ""
          }</div>`
        : `<div class="actions">
            <label class="section-label" for="ackNote">Acknowledge note</label>
            <textarea id="ackNote" placeholder="Optional note (dismiss / accept signal)"></textarea>
            <button type="button" id="ackBtn">Acknowledge</button>
          </div>`
    }
  `;

  const ackBtn = document.getElementById("ackBtn");
  if (ackBtn) {
    ackBtn.addEventListener("click", async () => {
      const note = document.getElementById("ackNote")?.value || null;
      ackBtn.disabled = true;
      try {
        await fetchJson(`/alerts/${alert.alert_id}/acknowledge`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ note }),
        });
        await Promise.all([loadMetrics(), loadAlerts()]);
      } catch (err) {
        ackBtn.disabled = false;
        console.error(err);
        window.alert(`Acknowledge failed: ${err.message}`);
      }
    });
  }
}

hideAckEl.addEventListener("change", async () => {
  state.hideAck = hideAckEl.checked;
  await loadAlerts();
});

(async function init() {
  await loadMetrics();
  await loadAlerts();
  if (state.alerts[0]) {
    state.selectedId = state.alerts[0].alert_id;
    renderList();
    renderDetail(state.alerts[0]);
  }
})();
