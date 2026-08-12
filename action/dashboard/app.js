const state = {
  alerts: [],
  episodes: [],
  selectedId: null,
  hideAck: false,
  metrics: null,
};

const listEl = document.getElementById("alertList");
const detailEl = document.getElementById("detail");
const detailEmpty = document.getElementById("detailEmpty");
const metricsEl = document.getElementById("metrics");
const episodesEl = document.getElementById("episodes");
const hideAckEl = document.getElementById("hideAck");

const SCORE_CEILING = 24;

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

const FIRST_NAMES = [
  "Amelia",
  "Noah",
  "Sofia",
  "Liam",
  "Ava",
  "Ethan",
  "Mia",
  "Lucas",
  "Harper",
  "Owen",
  "Isla",
  "Caleb",
  "Chloe",
  "Julian",
  "Zoe",
  "Adrian",
];

const LAST_NAMES = [
  "Brooks",
  "Nguyen",
  "Patel",
  "Garcia",
  "Kim",
  "Andersen",
  "Hassan",
  "Murphy",
  "Silva",
  "Cohen",
  "Walsh",
  "Ibrahim",
  "Foster",
  "Reyes",
  "Bennett",
  "Sato",
];

function hashString(value) {
  let h = 0;
  const s = String(value || "");
  for (let i = 0; i < s.length; i += 1) {
    h = (h * 31 + s.charCodeAt(i)) >>> 0;
  }
  return h;
}

function displayName(alert) {
  if (alert.patient_name && String(alert.patient_name).trim()) {
    return String(alert.patient_name).trim();
  }
  const h = hashString(alert.patient_id);
  const first = FIRST_NAMES[h % FIRST_NAMES.length];
  const last = LAST_NAMES[Math.floor(h / FIRST_NAMES.length) % LAST_NAMES.length];
  return `${first} ${last}`;
}

function patientIdLabel(id) {
  if (!id) return "";
  return String(id).replace(/^Patient\//, "");
}

function indicatorGlyph(indicator) {
  const known = { aki: "◇", "sofa-deterioration": "◈", "sepsis-3": "▣", sepsis: "◈" };
  return known[indicator] || "○";
}

function signalView(alert) {
  const s = alert.signal || {};
  return {
    type: s.signal_type || alert.indicator || "unknown",
    kind: s.signal_kind || alert.signal_kind || "risk",
    severity: s.severity || alert.tier || "none",
    completeness: s.completeness || alert.completeness || "partial",
    score: s.score ?? alert.score,
    stage: s.stage ?? alert.stage,
    onset: s.onset_time || alert.onset_time,
    missing: s.missing_inputs || alert.missing_components || [],
    required: s.required_inputs || alert.required_inputs || [],
    evidence: s.evidence_ids || alert.evidence_ids || [],
    exclusions: s.exclusions || alert.exclusions || [],
    criteria: s.criteria_met || alert.criteria_met || [],
    resolution: s.resolution_state || alert.resolution_state || (alert.acknowledged ? "acknowledged" : "open"),
    components: s.components || alert.component_breakdown || [],
    ruleId: s.rule_bundle_id || alert.rule_bundle_id,
    ruleVersion: s.rule_version || alert.rule_version,
    ruleHash: s.rule_bundle_hash || alert.rule_bundle_hash,
  };
}

function scoreWidth(score) {
  const n = Number(score) || 0;
  return `${Math.max(6, Math.min(100, (n / SCORE_CEILING) * 100))}%`;
}

function componentWidth(points) {
  if (points == null) return "0%";
  return `${Math.max(8, Math.min(100, (Number(points) / 4) * 100))}%`;
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
  state.metrics = m;
  metricsEl.innerHTML = `
    <article class="stat-card">
      <span class="stat-label">Open</span>
      <strong class="stat-value">${m.open_alerts}</strong>
      <span class="stat-sub">Needs review</span>
    </article>
    <article class="stat-card critical">
      <span class="stat-label">Critical</span>
      <strong class="stat-value">${m.by_tier.critical || 0}</strong>
      <span class="stat-sub">Highest acuity</span>
    </article>
    <article class="stat-card urgent">
      <span class="stat-label">Urgent</span>
      <strong class="stat-value">${m.by_tier.urgent || 0}</strong>
      <span class="stat-sub">Interruptive</span>
    </article>
    <article class="stat-card watch">
      <span class="stat-label">Watch</span>
      <strong class="stat-value">${m.by_tier.watch || 0}</strong>
      <span class="stat-sub">Passive flag</span>
    </article>
    <article class="stat-card ok">
      <span class="stat-label">Acknowledged</span>
      <strong class="stat-value">${m.acknowledged_alerts}</strong>
      <span class="stat-sub">of ${m.total_alerts} total</span>
    </article>
  `;
}

async function loadEpisodes() {
  if (!episodesEl) return;
  state.episodes = await fetchJson("/episodes?limit=50");
  if (!state.episodes.length) {
    episodesEl.innerHTML = "";
    return;
  }
  episodesEl.innerHTML = `
    <div class="section-title-row">
      <h2>Episodes</h2>
      <p class="hint">One interruptive page per patient episode · supporting signals retained</p>
    </div>
    <div class="episode-row">
      ${state.episodes
        .map((ep) => {
          const support = (ep.supporting_signal_types || []).join(", ") || "—";
          const name =
            state.alerts.find((a) => a.patient_id === ep.patient_id)?.patient_name ||
            ep.patient_id.replace(/^Patient\//, "");
          return `<article class="episode-card">
            <div class="episode-top">
              <strong>${name}</strong>
              <span class="tier-chip ${ep.dominant_severity}">${ep.status}</span>
            </div>
            <div class="episode-dom">${ep.dominant_signal_type || "—"} · ${ep.dominant_severity}</div>
            <div class="meta">support: ${support}</div>
            <div class="meta">pages ${ep.page_count} · passive ${ep.passive_update_count}</div>
          </article>`;
        })
        .join("")}
    </div>
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
    else if (state.alerts[0]) {
      state.selectedId = state.alerts[0].alert_id;
      renderDetail(state.alerts[0]);
    } else {
      state.selectedId = null;
      detailEl.classList.add("hidden");
      detailEmpty.classList.remove("hidden");
    }
  }
}

function renderList() {
  listEl.innerHTML = "";
  if (!state.alerts.length) {
    listEl.innerHTML = `<p class="empty">No alerts match this filter.</p>`;
    return;
  }

  for (const alert of state.alerts) {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = `alert-card${alert.acknowledged ? " acked" : ""}${
      alert.alert_id === state.selectedId ? " active" : ""
    }`;
    const tier = alert.tier || "none";
    const view = signalView(alert);
    const indicator = view.type;
    btn.innerHTML = `
      <div class="card-top">
        <div class="icon-pill ${tier}" aria-hidden="true">${indicatorGlyph(indicator)}</div>
        <span class="tier-chip ${tier}">${tier}</span>
      </div>
      <div class="card-patient">${displayName(alert)}</div>
      <div class="card-score-row">
        <div class="card-score">
          <span>${view.kind === "phenotype" ? "Met" : "Score"}</span>
          ${view.score ?? "—"}
        </div>
        <div class="card-meta">${fmtTime(alert.event_time)}</div>
      </div>
      <div class="meter ${tier}" aria-hidden="true"><i style="width:${scoreWidth(alert.score)}"></i></div>
      <div class="card-footer">
        <span class="indicator-tag">${indicator}</span>
        <span>${view.kind} · ${alert.routing ? `${alert.routing} · ` : ""}${view.completeness}${
          alert.acknowledged ? " · acked" : ""
        }</span>
      </div>
    `;
    btn.addEventListener("click", () => {
      state.selectedId = alert.alert_id;
      renderList();
      renderDetail(alert);
    });
    listEl.appendChild(btn);
  }
}

function renderNarrative(alert) {
  const status = alert.narrative_status || "none";
  if (status === "pass" && alert.narrative) {
    const claims = (alert.narrative_claims || [])
      .map(
        (c) =>
          `<li>${c.text} <span class="meta">[${(c.evidence_ids || []).join(", ")}]</span></li>`
      )
      .join("");
    return `
      <div class="narrative pass">
        <p>${alert.narrative}</p>
        <ul class="evidence">${claims}</ul>
        <div class="meta">model ${alert.grp_model_name || "—"} · score unchanged</div>
      </div>`;
  }
  if (status === "quarantine" || status === "abstain" || status === "error") {
    return `
      <div class="narrative ${status}">
        <strong>${status}</strong>
        <p>${alert.quarantine_reason || "No narrative attached."}</p>
        <div class="meta">Deterministic alert still valid · score unchanged</div>
        <button type="button" id="explainBtn" class="secondary">Retry explanation</button>
      </div>`;
  }
  return `
    <div class="narrative none">
      <p class="meta">No LLM narrative yet. GRP is additive and cannot change the score.</p>
      <button type="button" id="explainBtn">Generate explanation</button>
    </div>`;
}

function renderDetail(alert) {
  detailEmpty.classList.add("hidden");
  detailEl.classList.remove("hidden");

  const view = signalView(alert);
  const components = (view.components || [])
    .map((c) => {
      if (c.missing) {
        return `<li class="comp-item missing"><div class="comp-head"><strong>${c.name}</strong><span>missing</span></div></li>`;
      }
      return `
        <li class="comp-item">
          <div class="comp-head">
            <strong>${c.name}</strong>
            <span>${c.points ?? 0} pts</span>
          </div>
          <div class="comp-bar" aria-hidden="true"><i style="width:${componentWidth(c.points)}"></i></div>
          <div class="meta">${(c.evidence_ids || []).join(", ") || "no evidence ids"}</div>
        </li>`;
    })
    .join("");

  const evidence = (view.evidence || [])
    .map((e) => `<li><code>${e}</code></li>`)
    .join("");
  const missing = (view.missing || [])
    .map((m) => `<li><code>${m}</code></li>`)
    .join("");
  const criteria = (view.criteria || [])
    .map((c) => `<li><code>${c}</code></li>`)
    .join("");
  const exclusions = (view.exclusions || [])
    .map((e) => `<li><code>${e}</code></li>`)
    .join("");

  detailEl.innerHTML = `
    <div class="detail-hero">
      <div class="detail-score"><small>${view.kind === "phenotype" ? "Met" : "Score"}</small>${view.score ?? "—"}</div>
      <div>
        <h3>${displayName(alert)}</h3>
        <p class="meta">${alert.alert_id} · ${patientIdLabel(alert.patient_id)}</p>
        <div class="badges">
          <span class="badge tier-chip ${view.severity}">${view.severity}</span>
          <span class="badge">${view.type}</span>
          <span class="badge">${view.kind}</span>
          <span class="badge">${view.completeness}</span>
          <span class="badge">${view.resolution}</span>
          <span class="badge">${alert.governance_path}</span>
          ${
            alert.routing
              ? `<span class="badge routing-chip ${alert.routing}">${alert.routing}</span>`
              : ""
          }
          ${
            alert.page_deferred_reason
              ? `<span class="badge">deferred: ${alert.page_deferred_reason}</span>`
              : ""
          }
          ${view.stage != null ? `<span class="badge">stage ${view.stage}</span>` : ""}
          <span class="badge">${view.ruleId}@${view.ruleVersion}</span>
        </div>
      </div>
    </div>
    <p class="meta">Event ${fmtTime(alert.event_time)} · Encounter ${alert.encounter_id || "—"}
      ${view.onset ? ` · Onset ${fmtTime(view.onset)}` : ""}</p>
    <div class="section-label">Components</div>
    <ul class="comp-list">${components || '<li class="comp-item missing">No components</li>'}</ul>
    <div class="section-label">Missing inputs</div>
    <ul class="evidence">${missing || '<li class="missing">None</li>'}</ul>
    <div class="section-label">Criteria met</div>
    <ul class="evidence">${criteria || '<li class="missing">None</li>'}</ul>
    <div class="section-label">Exclusions</div>
    <ul class="evidence">${exclusions || '<li class="missing">None</li>'}</ul>
    <div class="section-label">Evidence IDs</div>
    <ul class="evidence">${evidence || '<li class="missing">None</li>'}</ul>
    <div class="section-label">Guarded explanation</div>
    ${renderNarrative(alert)}
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

  const explainBtn = document.getElementById("explainBtn");
  if (explainBtn) {
    explainBtn.addEventListener("click", async () => {
      explainBtn.disabled = true;
      try {
        const updated = await fetchJson(`/alerts/${alert.alert_id}/explain`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ force: true }),
        });
        state.alerts = state.alerts.map((a) =>
          a.alert_id === updated.alert_id ? updated : a
        );
        renderList();
        renderDetail(updated);
      } catch (err) {
        explainBtn.disabled = false;
        console.error(err);
        window.alert(`Explain failed: ${err.message}`);
      }
    });
  }

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
  await loadEpisodes();
  if (state.alerts[0]) {
    state.selectedId = state.alerts[0].alert_id;
    renderList();
    renderDetail(state.alerts[0]);
  }
})();
