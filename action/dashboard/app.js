const state = {
  alerts: [],
  episodes: [],
  selectedId: null,
  hideAck: false,
  metrics: null,
  view: "alerts",
};

const listEl = document.getElementById("alertList");
const detailEl = document.getElementById("detail");
const detailEmpty = document.getElementById("detailEmpty");
const metricsEl = document.getElementById("metrics");
const episodesEl = document.getElementById("episodes");
const claimsEl = document.getElementById("claims");
const investorEl = document.getElementById("investor");
const hideAckEl = document.getElementById("hideAck");
const hideAckChip = document.getElementById("hideAckChip");
const pageTitle = document.getElementById("pageTitle");
const viewAlerts = document.getElementById("view-alerts");
const viewExplain = document.getElementById("view-explain");
const workflowListEl = document.getElementById("workflowList");
const episodePick = document.getElementById("episodePick");
const episodeExplainBtn = document.getElementById("episodeExplainBtn");
const episodeExplainOut = document.getElementById("episodeExplainOut");
const stewardText = document.getElementById("stewardText");
const stewardClassifyBtn = document.getElementById("stewardClassifyBtn");
const stewardOut = document.getElementById("stewardOut");
const viewBenchmarks = document.getElementById("view-benchmarks");
const benchmarkListEl = document.getElementById("benchmarkList");
const benchDisclaimer = document.getElementById("benchDisclaimer");
const benchHowto = document.getElementById("benchHowto");
const c4DiagramEl = document.getElementById("c4Diagram");
const c4CaptionEl = document.getElementById("c4Caption");
const c4LegendEl = document.getElementById("c4Legend");
const flowNarrationEl = document.getElementById("flowNarration");
const flowTokenEl = document.getElementById("flowToken");
const flowStepMetaEl = document.getElementById("flowStepMeta");
const flowPlayBtn = document.getElementById("flowPlay");
const flowStepBtn = document.getElementById("flowStep");
const flowResetBtn = document.getElementById("flowReset");
const flowScenarioTabsEl = document.getElementById("flowScenarioTabs");
const flowNodesEl = document.getElementById("flowNodes");
const flowEdgeGroupEl = document.getElementById("flowEdgeGroup");

const WORKFLOWS = [
  {
    id: "WF-01",
    title: "Hospital interface onboarding copilot",
    blurb: "Propose HL7/FHIR mappings; compile to deterministic transforms.",
    detail:
      "Lives in Curie Connect (curie-fhir). Production traffic uses the approved mapping only — no LLM after go-live.",
    where: "connect",
    status: "planned",
    statusLabel: "Connect · planned",
  },
  {
    id: "WF-02",
    title: "Deterministic-first conversion + LLM exceptions",
    blurb: "Fast path for known traffic; model only on novel or failed inputs.",
    detail:
      "Router order: approved mapping → validation → LLM repair proposal → revalidate → human review.",
    where: "connect",
    status: "planned",
    statusLabel: "Connect · planned",
  },
  {
    id: "WF-03",
    title: "Provenance-preserving note extraction",
    blurb: "Candidate facts with spans; promote only after validation.",
    detail:
      "Bridge contract rejects candidate / failed provenance. Pipeline consumes trusted facts only (CURIE-022).",
    where: "connect",
    status: "live",
    statusLabel: "Bridge · demo",
  },
  {
    id: "WF-06",
    title: "Grounded multi-condition episode copilot",
    blurb: "One narrative for the episode; every claim cites evidence IDs.",
    detail:
      "Immutable episode snapshot → GRP narrative. Quarantine unsupported text; alert still ships. Try below.",
    where: "copilot",
    status: "live",
    statusLabel: "Live in demo",
  },
  {
    id: "WF-07",
    title: "Uncertainty-band context assistant",
    blurb: "Passive context only when deterministic evidence is borderline.",
    detail:
      "Frozen eligibility policy. Must not suppress or escalate. Offline study path (CURIE-025).",
    where: "copilot",
    status: "live",
    statusLabel: "Eval · passive",
  },
  {
    id: "WF-09",
    title: "Alert feedback & stewardship copilot",
    blurb: "Classify dismissals into a governance taxonomy; propose offline experiments.",
    detail:
      "Never mutates live rules or thresholds. Proposals need frozen replay before approval. Try below.",
    where: "copilot",
    status: "live",
    statusLabel: "Live in demo",
  },
  {
    id: "WF-08",
    title: "Site-approved protocol retrieval",
    blurb: "Cite curated institutional protocols only — no free-form prescribing.",
    detail: "Requires a curated knowledge base and citation QA before clinical surface.",
    where: "copilot",
    status: "planned",
    statusLabel: "Planned",
  },
  {
    id: "WF-10",
    title: "Research cohort & adjudication copilot",
    blurb: "Draft packets and phenotypes; LLM labels are proposals, not truth.",
    detail: "Locked test sets, dual review, and inter-rater agreement remain mandatory.",
    where: "copilot",
    status: "planned",
    statusLabel: "Planned",
  },
];




function flowLayout(nodes, llmNode) {
  const main = nodes.filter((n) => !llmNode || n.id !== llmNode.id);
  const startX = 70;
  const endX = 850;
  const y = 150;
  const positions = {};
  main.forEach((n, i) => {
    const x =
      main.length === 1 ? 460 : startX + (i * (endX - startX)) / Math.max(main.length - 1, 1);
    positions[n.id] = [x, y];
  });
  const edges = [];
  for (let i = 0; i < main.length - 1; i += 1) {
    const a = positions[main[i].id];
    const b = positions[main[i + 1].id];
    edges.push({
      d: `M${a[0] + 48} ${a[1]} H${b[0] - 48}`,
      llm: false,
    });
  }
  if (llmNode) {
    const anchorId = llmNode.above || main[Math.floor(main.length / 2)]?.id;
    const anchor = positions[anchorId] || [460, y];
    positions[llmNode.id] = [anchor[0], 48];
    const prev = main[Math.max(0, main.findIndex((n) => n.id === anchorId) - 1)];
    const next = main[Math.min(main.length - 1, main.findIndex((n) => n.id === anchorId) + 1)];
    if (prev && next) {
      const p = positions[prev.id];
      const q = positions[llmNode.id];
      const r = positions[next.id];
      edges.push({
        d: `M${p[0] + 20} ${p[1] - 24} C${p[0] + 40} 70, ${q[0] - 40} 70, ${q[0]} ${q[1] + 18}`,
        llm: true,
      });
      edges.push({
        d: `M${q[0]} ${q[1] + 18} C${q[0] + 40} 70, ${r[0] - 40} 70, ${r[0] - 20} ${r[1] - 24}`,
        llm: true,
      });
    }
  }
  return { positions, edges, main, all: llmNode ? [...main, llmNode] : main };
}

function flowScenario(cfg) {
  const layout = flowLayout(cfg.nodes, cfg.llm || null);
  const steps = (cfg.steps || []).map((s) => {
    const focus = s.focus || (s.nodes && s.nodes[s.nodes.length - 1]);
    const token = layout.positions[focus] || [70, 150];
    return {
      nodes: s.nodes || [],
      edges: s.edges || [],
      token: [token[0], token[1]],
      text: s.text,
    };
  });
  return {
    id: cfg.id,
    tab: cfg.tab,
    label: cfg.label,
    group: cfg.group,
    llm: cfg.llm || null,
    layout,
    steps,
  };
}

const FLOW_SCENARIO_LIST = [
  flowScenario({
    id: "wf01",
    tab: "WF-01 Mapping",
    label: "WF-01 · Hospital interface onboarding",
    group: "connect",
    nodes: [
      { id: "spec", kicker: "In", title: "Sample HL7 / specs" },
      { id: "propose", kicker: "LLM", title: "Mapping proposal" },
      { id: "review", kicker: "Human", title: "Reviewer approve" },
      { id: "compile", kicker: "Out", title: "Compiled mapping" },
      { id: "prod", kicker: "Prod", title: "No LLM in prod" },
    ],
    steps: [
      { nodes: ["spec"], focus: "spec", text: "Informaticists bring sample messages, dictionaries, and target FHIR profiles." },
      { nodes: ["spec", "propose"], focus: "propose", edges: [0], text: "LLM proposes field maps, terminology, FHIRPath, golden tests, and open questions." },
      { nodes: ["propose", "review"], focus: "review", edges: [0, 1], text: "Humans accept, correct, or reject. Production never auto-activates the proposal." },
      { nodes: ["review", "compile"], focus: "compile", edges: [1, 2], text: "Approved proposal compiles into a deterministic site mapping + regression fixtures." },
      { nodes: ["compile", "prod"], focus: "prod", edges: [2, 3], text: "After go-live, traffic uses the compiled mapping only — LLM stays offline for that interface." },
    ],
  }),
  flowScenario({
    id: "fast",
    tab: "WF-02 Fast",
    label: "WF-02 · Deterministic fast path",
    group: "connect",
    nodes: [
      { id: "ingest", kicker: "In", title: "HL7 / notes" },
      { id: "map", kicker: "Map", title: "Approved mapping" },
      { id: "validate", kicker: "Gate", title: "Validate" },
      { id: "trusted", kicker: "Trust", title: "Trusted fact" },
      { id: "signal", kicker: "Signal", title: "Score · episode" },
    ],
    steps: [
      { nodes: ["ingest"], focus: "ingest", text: "Known message types arrive at Connect’s front door." },
      { nodes: ["ingest", "map"], focus: "map", edges: [0], text: "Approved site mapping runs first. No LLM on the happy path." },
      { nodes: ["map", "validate"], focus: "validate", edges: [0, 1], text: "Schema, terminology, and provenance checks must pass." },
      { nodes: ["validate", "trusted"], focus: "trusted", edges: [1, 2], text: "Only then is the envelope trusted for scoring." },
      { nodes: ["trusted", "signal"], focus: "signal", edges: [2, 3], text: "Signal scores and governs deterministically — alert can ship without any model call." },
    ],
  }),
  flowScenario({
    id: "exception",
    tab: "WF-02 Exception",
    label: "WF-02 · LLM exception path",
    group: "connect",
    nodes: [
      { id: "ingest", kicker: "In", title: "Novel / broken msg" },
      { id: "map", kicker: "Map", title: "Approved mapping" },
      { id: "validate", kicker: "Gate", title: "Validate" },
      { id: "trusted", kicker: "Trust", title: "Trusted fact" },
      { id: "signal", kicker: "Signal", title: "Score · episode" },
    ],
    llm: { id: "llm", kicker: "LLM", title: "Repair / extract", above: "validate" },
    steps: [
      { nodes: ["ingest"], focus: "ingest", text: "Malformed or unmapped input cannot finish the deterministic path." },
      { nodes: ["ingest", "map", "validate"], focus: "validate", edges: [0, 1], text: "Mapping still runs first; validation fails or fields are unknown." },
      { nodes: ["map", "validate", "llm"], focus: "llm", edges: [1, 4], text: "Only now the LLM proposes a repair or extraction — with model/prompt provenance." },
      { nodes: ["llm", "validate", "trusted"], focus: "validate", edges: [4, 5], text: "Re-validate. High-risk or unresolved → human review, never silent trust." },
      { nodes: ["validate", "trusted", "signal"], focus: "signal", edges: [2, 3], text: "After validation, Signal proceeds. Model failure must not block deterministic delivery." },
    ],
  }),
  flowScenario({
    id: "wf03",
    tab: "WF-03 Extract",
    label: "WF-03 · Provenance-preserving note extraction",
    group: "connect",
    nodes: [
      { id: "note", kicker: "In", title: "Clinical note" },
      { id: "extract", kicker: "LLM", title: "Span extraction" },
      { id: "candidate", kicker: "Cand", title: "Candidate fact" },
      { id: "validate", kicker: "Gate", title: "Validate / review" },
      { id: "trusted", kicker: "Trust", title: "Trusted only" },
    ],
    steps: [
      { nodes: ["note"], focus: "note", text: "Notes carry infection suspicion, baselines, goals of care — ambiguous semantic content." },
      { nodes: ["note", "extract"], focus: "extract", edges: [0], text: "LLM extracts concepts with exact text spans, negation, temporality, and confidence." },
      { nodes: ["extract", "candidate"], focus: "candidate", edges: [0, 1], text: "Output stays candidate. Pipeline scoring must not consume it yet." },
      { nodes: ["candidate", "validate"], focus: "validate", edges: [1, 2], text: "Deterministic validation or human approval required to promote." },
      { nodes: ["validate", "trusted"], focus: "trusted", edges: [2, 3], text: "Trusted facts cross the bridge; candidates remain quarantined." },
    ],
  }),
  flowScenario({
    id: "wf04",
    tab: "WF-04 Fidelity",
    label: "WF-04 · FHIR semantic fidelity reviewer",
    group: "connect",
    nodes: [
      { id: "source", kicker: "Src", title: "Source note" },
      { id: "fhir", kicker: "FHIR", title: "Valid resource" },
      { id: "judge", kicker: "LLM", title: "Field-level claims" },
      { id: "result", kicker: "Out", title: "supported / review" },
    ],
    steps: [
      { nodes: ["source", "fhir"], focus: "fhir", edges: [0], text: "Resource may be structurally valid FHIR but still misrepresent the source." },
      { nodes: ["fhir", "judge"], focus: "judge", edges: [0, 1], text: "LLM emits field-level claims: supported, unsupported, or omitted — never one boolean." },
      { nodes: ["judge", "result"], focus: "result", edges: [1, 2], text: "Judge failure returns unknown/review_required — never defaults to safe." },
    ],
  }),
  flowScenario({
    id: "wf05",
    tab: "WF-05 Review",
    label: "WF-05 · Human-review workbench",
    group: "connect",
    nodes: [
      { id: "queue", kicker: "In", title: "Exception queue" },
      { id: "side", kicker: "UI", title: "Source ↔ target" },
      { id: "suggest", kicker: "LLM", title: "Suggested patch" },
      { id: "disp", kicker: "Human", title: "Disposition" },
      { id: "fix", kicker: "Out", title: "Regression fixture" },
    ],
    steps: [
      { nodes: ["queue"], focus: "queue", text: "Failed validation and high-risk LLM repairs land in the review workbench." },
      { nodes: ["queue", "side"], focus: "side", edges: [0], text: "Reviewer sees source and target side by side with validation history." },
      { nodes: ["side", "suggest"], focus: "suggest", edges: [0, 1], text: "Copilot suggests a minimal patch — still advisory." },
      { nodes: ["suggest", "disp"], focus: "disp", edges: [1, 2], text: "Disposition: accepted, mapping fix, terminology, insufficient, unsafe, …" },
      { nodes: ["disp", "fix"], focus: "fix", edges: [2, 3], text: "Accept/correct writes a regression fixture so the same defect does not recur." },
    ],
  }),
  flowScenario({
    id: "wf06",
    tab: "WF-06 Narrative",
    label: "WF-06 · Grounded episode narrative",
    group: "copilot",
    nodes: [
      { id: "episode", kicker: "Signal", title: "Immutable episode" },
      { id: "snap", kicker: "Ctx", title: "Evidence snapshot" },
      { id: "narr", kicker: "LLM", title: "Grounded narrative" },
      { id: "gate", kicker: "GRP", title: "Quarantine gate" },
      { id: "ui", kicker: "UI", title: "Additive display" },
    ],
    steps: [
      { nodes: ["episode"], focus: "episode", text: "Episode arbiter already chose dominant signal and routing — frozen for explanation." },
      { nodes: ["episode", "snap"], focus: "snap", edges: [0], text: "Copilot receives only allowed evidence IDs, missing inputs, and rule versions." },
      { nodes: ["snap", "narr"], focus: "narr", edges: [0, 1], text: "LLM drafts what changed, supporting signals, and why passive vs interruptive." },
      { nodes: ["narr", "gate"], focus: "gate", edges: [1, 2], text: "Every claim must cite evidence. Unsupported text is quarantined; score unchanged." },
      { nodes: ["gate", "ui"], focus: "ui", edges: [2, 3], text: "Narrative is additive on the dashboard. Alert delivery never waits on the model." },
    ],
  }),
  flowScenario({
    id: "wf07",
    tab: "WF-07 Uncertainty",
    label: "WF-07 · Uncertainty-band assistant",
    group: "copilot",
    nodes: [
      { id: "policy", kicker: "Policy", title: "Frozen eligibility" },
      { id: "case", kicker: "Case", title: "Borderline evidence" },
      { id: "assist", kicker: "LLM", title: "Context / mimics" },
      { id: "pass", kicker: "Mode", title: "Passive only" },
      { id: "detect", kicker: "Signal", title: "Detection unchanged" },
    ],
    steps: [
      { nodes: ["policy"], focus: "policy", text: "Invoke only under a frozen uncertainty policy — not for every patient." },
      { nodes: ["policy", "case"], focus: "case", edges: [0], text: "Borderline or conflicting deterministic evidence selects the case." },
      { nodes: ["case", "assist"], focus: "assist", edges: [0, 1], text: "Assistant may surface grounded context, mimics, conflicts, and missing data." },
      { nodes: ["assist", "pass"], focus: "pass", edges: [1, 2], text: "Retrospective / passive mode only — must not suppress or escalate." },
      { nodes: ["pass", "detect"], focus: "detect", edges: [2, 3], text: "Detection metrics stay unchanged; quality is judged by unsupported-claim rate." },
    ],
  }),
  flowScenario({
    id: "wf08",
    tab: "WF-08 Protocol",
    label: "WF-08 · Site-approved protocol retrieval",
    group: "copilot",
    nodes: [
      { id: "alert", kicker: "Alert", title: "Governed alert" },
      { id: "kb", kicker: "KB", title: "Curated protocols" },
      { id: "retr", kicker: "LLM", title: "Retrieve + cite" },
      { id: "sum", kicker: "Out", title: "Workflow summary" },
    ],
    steps: [
      { nodes: ["alert"], focus: "alert", text: "Clinician needs actionable next steps after a governed alert." },
      { nodes: ["alert", "kb"], focus: "kb", edges: [0], text: "Retrieval is limited to a curated institutional knowledge base." },
      { nodes: ["kb", "retr"], focus: "retr", edges: [0, 1], text: "Every result cites title, version, section, dates, and authoritative link." },
      { nodes: ["retr", "sum"], focus: "sum", edges: [1, 2], text: "Summarize approved workflow / order-set availability — do not independently prescribe." },
    ],
  }),
  flowScenario({
    id: "wf09",
    tab: "WF-09 Steward",
    label: "WF-09 · Alert stewardship",
    group: "copilot",
    nodes: [
      { id: "fb", kicker: "In", title: "Ack / dismiss text" },
      { id: "class", kicker: "LLM", title: "Taxonomy classify" },
      { id: "agg", kicker: "Analytics", title: "Aggregate themes" },
      { id: "prop", kicker: "Offline", title: "Experiment proposal" },
      { id: "human", kicker: "Human", title: "Approve + replay" },
    ],
    steps: [
      { nodes: ["fb"], focus: "fb", text: "Clinician acknowledgement text becomes stewardship signal — not a live knob." },
      { nodes: ["fb", "class"], focus: "class", edges: [0], text: "Classify into taxonomy: already treated, baseline, wrong recipient, true escalation, …" },
      { nodes: ["class", "agg"], focus: "agg", edges: [0, 1], text: "Aggregate by site, service, indicator, rule version, and routing lane." },
      { nodes: ["agg", "prop"], focus: "prop", edges: [1, 2], text: "Propose offline experiments only. Never mutate active rules from the classifier." },
      { nodes: ["prop", "human"], focus: "human", edges: [2, 3], text: "Human approval + frozen replay required before any production change." },
    ],
  }),
  flowScenario({
    id: "wf10",
    tab: "WF-10 Research",
    label: "WF-10 · Research cohort & adjudication",
    group: "copilot",
    nodes: [
      { id: "cohort", kicker: "Study", title: "Cohort / phenotype" },
      { id: "packet", kicker: "LLM", title: "Case packet draft" },
      { id: "dual", kicker: "Human", title: "Dual review" },
      { id: "lock", kicker: "Lock", title: "Locked test set" },
    ],
    steps: [
      { nodes: ["cohort"], focus: "cohort", text: "Researchers need reproducible phenotype review and error analysis." },
      { nodes: ["cohort", "packet"], focus: "packet", edges: [0], text: "LLM may draft cohort queries and source-grounded case packets — as proposals." },
      { nodes: ["packet", "dual"], focus: "dual", edges: [0, 1], text: "Independent dual review + adjudication; LLM labels are not ground truth." },
      { nodes: ["dual", "lock"], focus: "lock", edges: [1, 2], text: "Studies keep a locked test set and inter-rater agreement — no silent retuning." },
    ],
  }),
];

const FLOW_SCENARIOS = Object.fromEntries(FLOW_SCENARIO_LIST.map((s) => [s.id, s]));

const flowState = {
  scenario: "fast",
  step: 0,
  playing: false,
  timer: null,
};

const FLOW_LLM_NODE_IDS = new Set([
  "llm",
  "narr",
  "assist",
  "class",
  "retr",
  "propose",
  "extract",
  "judge",
  "suggest",
  "packet",
]);

function mountFlowScenario(scenarioId) {
  const sc = FLOW_SCENARIOS[scenarioId];
  if (!sc || !flowNodesEl || !flowEdgeGroupEl) return;
  flowEdgeGroupEl.innerHTML = sc.layout.edges
    .map(
      (e, idx) =>
        `<path class="flow-edge${e.llm ? " flow-edge-llm" : ""}" data-edge="${idx}" d="${e.d}" marker-end="url(#flowArrow)"></path>`
    )
    .join("");
  const floatId = sc.llm?.id || null;
  flowNodesEl.innerHTML = sc.layout.all
    .map((n) => {
      const [x, y] = sc.layout.positions[n.id];
      const isLlm = FLOW_LLM_NODE_IDS.has(n.id) || n.kicker === "LLM";
      const isFloat = floatId === n.id;
      const kind = [isLlm ? "flow-node-llm" : "", isFloat ? "flow-node-llm-float" : ""]
        .filter(Boolean)
        .join(" ");
      return `<div class="flow-node ${kind}" data-node="${n.id}" style="--fx:${x};--fy:${y}">
        <span class="flow-node-kicker">${esc(n.kicker)}</span>
        <strong>${esc(n.title)}</strong>
      </div>`;
    })
    .join("");
  flowNodesEl.querySelectorAll(".flow-node-llm-float").forEach((el) => {
    const id = el.dataset.node;
    const [x] = sc.layout.positions[id] || [460, 48];
    el.style.left = `${(x / 920) * 100}%`;
  });
}

function clearFlowVisuals() {
  document.querySelectorAll(".flow-node").forEach((n) => n.classList.remove("active"));
  document.querySelectorAll(".flow-edge").forEach((e) => e.classList.remove("active"));
}

function applyFlowStep(step) {
  clearFlowVisuals();
  (step.nodes || []).forEach((id) => {
    document.querySelector(`.flow-node[data-node="${id}"]`)?.classList.add("active");
  });
  (step.edges || []).forEach((idx) => {
    document.querySelector(`.flow-edge[data-edge="${idx}"]`)?.classList.add("active");
  });
  if (flowTokenEl && step.token) {
    flowTokenEl.setAttribute("cx", String(step.token[0]));
    flowTokenEl.setAttribute("cy", String(step.token[1]));
    flowTokenEl.classList.remove("pulse");
    void flowTokenEl.getBoundingClientRect();
    flowTokenEl.classList.add("pulse");
  }
  if (flowNarrationEl) flowNarrationEl.textContent = step.text;
  const total = (FLOW_SCENARIOS[flowState.scenario]?.steps || []).length;
  if (flowStepMetaEl) {
    flowStepMetaEl.textContent = `Step ${flowState.step + 1} / ${total} · ${
      FLOW_SCENARIOS[flowState.scenario]?.label || ""
    }`;
  }
}

function stopFlowPlay() {
  flowState.playing = false;
  if (flowState.timer) {
    clearInterval(flowState.timer);
    flowState.timer = null;
  }
  if (flowPlayBtn) {
    flowPlayBtn.textContent = "Play";
    flowPlayBtn.classList.remove("playing");
  }
}

function resetFlow(scenario) {
  stopFlowPlay();
  if (scenario) flowState.scenario = scenario;
  flowState.step = 0;
  mountFlowScenario(flowState.scenario);
  document.querySelectorAll(".flow-scenario").forEach((btn) => {
    const on = btn.dataset.flow === flowState.scenario;
    btn.classList.toggle("active", on);
    btn.setAttribute("aria-selected", on ? "true" : "false");
  });
  const steps = FLOW_SCENARIOS[flowState.scenario]?.steps || [];
  if (steps[0]) applyFlowStep(steps[0]);
}

function stepFlow() {
  const steps = FLOW_SCENARIOS[flowState.scenario]?.steps || [];
  if (!steps.length) return false;
  if (flowState.step >= steps.length - 1) {
    stopFlowPlay();
    return false;
  }
  flowState.step += 1;
  applyFlowStep(steps[flowState.step]);
  return flowState.step < steps.length - 1;
}

function playFlow() {
  const reduce = window.matchMedia?.("(prefers-reduced-motion: reduce)")?.matches;
  if (reduce) {
    stepFlow();
    return;
  }
  if (flowState.playing) {
    stopFlowPlay();
    return;
  }
  const steps = FLOW_SCENARIOS[flowState.scenario]?.steps || [];
  if (flowState.step >= steps.length - 1) {
    flowState.step = 0;
    applyFlowStep(steps[0]);
  }
  flowState.playing = true;
  if (flowPlayBtn) {
    flowPlayBtn.textContent = "Pause";
    flowPlayBtn.classList.add("playing");
  }
  flowState.timer = setInterval(() => {
    const more = stepFlow();
    if (!more) stopFlowPlay();
  }, 1600);
}

function initFlowAnim() {
  if (!flowNarrationEl || !flowScenarioTabsEl) return;
  flowScenarioTabsEl.innerHTML = FLOW_SCENARIO_LIST.map(
    (s, i) =>
      `<button type="button" class="flow-scenario${i === 1 ? " active" : ""}" role="tab" aria-selected="${
        i === 1 ? "true" : "false"
      }" data-flow="${s.id}" data-group="${s.group}">${esc(s.tab)}</button>`
  ).join("");
  flowScenarioTabsEl.querySelectorAll(".flow-scenario").forEach((btn) => {
    btn.addEventListener("click", () => resetFlow(btn.dataset.flow));
  });
  flowPlayBtn?.addEventListener("click", playFlow);
  flowStepBtn?.addEventListener("click", () => {
    stopFlowPlay();
    const steps = FLOW_SCENARIOS[flowState.scenario]?.steps || [];
    if (flowState.step >= steps.length - 1) resetFlow(flowState.scenario);
    else stepFlow();
  });
  flowResetBtn?.addEventListener("click", () => resetFlow(flowState.scenario));
  resetFlow("fast");
}

const C4_VIEWS = {
  context: {
    caption:
      "C4 Level 1 — System context. Hospitals send clinical data into Curie; clinicians receive governed alerts and additive explanations. LLMs never sit on the direct path from score to page.",
    legend: [
      "People interact with alerts and review workbenches — not raw model output as truth.",
      "External EHR / interface engines remain the system of record.",
      "Curie is one platform with three product layers: Connect, Signal, Copilot.",
    ],
    diagram: `flowchart LR
  personClinician["Clinician / surveillance"]
  personInformatics["Informaticist / CDS governance"]
  ehr["Hospital EHR and interfaces\nHL7 v2 · FHIR · notes"]
  curie["Curie platform\nConnect · Signal · Copilot"]
  ehr -->|"Clinical data"| curie
  curie -->|"Governed alerts + evidence"| personClinician
  curie -->|"Mappings, review, stewardship"| personInformatics
  personClinician -->|"Ack / dismiss feedback"| curie`,
  },
  container: {
    caption:
      "C4 Level 2 — Containers. curie-fhir publishes trusted facts; this prediction pipeline scores, governs, and explains. The dashboard is one action surface on a single port.",
    legend: [
      "curie-fhir = Connect container (deterministic-first + LLM exceptions).",
      "prediction-pipeline = Signal + Copilot containers.",
      "Trusted-fact bridge is the only cross-project clinical contract.",
    ],
    diagram: `flowchart TB
  subgraph connect ["curie-fhir · Connect"]
    ingest["Ingest API / Mirth"]
    router["Deterministic-first router"]
    review["Human review workbench"]
    outbox["Trusted-fact publisher"]
  end
  subgraph signal ["curie-prediction-pipeline · Signal"]
    bridge["Trusted-fact admit gate"]
    indicators["Deterministic indicators"]
    episodes["Episode arbiter + governance"]
  end
  subgraph copilot ["curie-prediction-pipeline · Copilot"]
    grp["Grounded episode narrative"]
    steward["Stewardship classify"]
    dash["Dashboard :8000"]
  end
  ingest --> router
  router -->|"fast path"| outbox
  router -->|"exception"| review
  review --> outbox
  outbox -->|"trusted envelopes only"| bridge
  bridge --> indicators --> episodes
  episodes -->|"immutable snapshot"| grp
  episodes --> dash
  grp --> dash
  steward --> dash
  dash -.->|"feedback text"| steward`,
  },
  component: {
    caption:
      "C4 Level 3 — Components on the LLM workflow path. Models assist at semantic and human-workflow edges; scoring and routing components stay deterministic.",
    legend: [
      "Green path = deterministic / versioned.",
      "Teal assist = LLM with quarantine and provenance.",
      "Candidate facts cannot mutate scoring until validated or human-approved.",
    ],
    diagram: `flowchart LR
  subgraph wf02 ["WF-02 Connect router"]
    map["Approved mapping"]
    validate["Schema · terminology · provenance"]
    llmFix["LLM repair / extract"]
    map --> validate
    validate -->|"fail / novel"| llmFix --> validate
  end
  subgraph trust ["Trust boundary"]
    candidate["candidate envelope"]
    trusted["trusted envelope"]
    llmFix --> candidate
    validate -->|"pass"| trusted
    candidate -->|"human / validation"| trusted
  end
  subgraph signalComp ["Signal · no LLM"]
    score["SOFA / KDIGO / phenotypes"]
    gov["Governance + page gate"]
    arb["Episode arbitration"]
    trusted --> score --> gov --> arb
  end
  subgraph copil ["Copilot · additive"]
    narr["WF-06 episode narrative"]
    stews["WF-09 stewardship"]
    unc["WF-07 uncertainty band"]
    arb -.-> narr
    arb -.-> stews
    arb -.-> unc
  end`,
  },
  boundary: {
    caption:
      "LLM hard boundary — what Copilot may touch vs what remains forbidden. Model failure must not delay deterministic delivery.",
    legend: [
      "Allowed: grounded narrative, mapping proposals, feedback classification, borderline context.",
      "Forbidden: scores, episode open/resolve/suppress/escalate, live thresholds, uncited facts.",
      "Every LLM claim needs model/prompt version, evidence IDs, and audit.",
    ],
    diagram: `flowchart TB
  subgraph allowed ["LLM may assist"]
    a1["Mapping proposals WF-01"]
    a2["Exception repair WF-02"]
    a3["Note extraction candidates WF-03"]
    a4["Episode narrative WF-06"]
    a5["Uncertainty context WF-07"]
    a6["Stewardship classify WF-09"]
  end
  subgraph forbidden ["LLM must not"]
    f1["Calculate or change scores"]
    f2["Open / route / suppress episodes"]
    f3["Activate thresholds or rule bundles"]
    f4["Promote candidates to trusted alone"]
    f5["Invent uncited clinical facts"]
  end
  allowed -->|"validated · audited · additive"| surface["Clinician / operator surfaces"]
  forbidden -.->|"blocked by product + admit gate"| wall["Hard safety boundary"]`,
  },
};

let c4Ready = false;
let c4Active = "context";
let c4Rendered = false;

/** CSP-safe static C4 layout — no CDN / Mermaid dependency (CURIE-031). */
function renderC4Static(level, view) {
  const nodes = {
    context: [
      ["Clinicians / ops", "Consumers of pages + narratives"],
      ["Curie Signal", "Deterministic scores · governance · episodes"],
      ["Curie Connect", "FHIR / mapping · trust boundary"],
      ["EHR / labs / devices", "Source systems"],
      ["Copilot (LLM)", "Additive explain · never scores"],
    ],
    container: [
      ["Dashboard / API", "Review · ack · benchmarks"],
      ["Flink SOFA / AKI / Resp", "Event-time scoring"],
      ["Governance + arbiter", "Page gate · episodes"],
      ["Connect validation", "Trusted vs candidate"],
      ["LLM workflows", "WF-01…WF-10 edges only"],
    ],
    component: [
      ["Kafka clinical events", "Ingress"],
      ["Score → gov → episode", "Signal core"],
      ["Durable store", "Restart-safe IDs"],
      ["CDS Hooks / FHIR", "Evidence surface"],
      ["Narrative / stewardship", "Copilot add-ons"],
    ],
    boundary: [
      ["LLM may assist", "Mapping · repair · narrative · classify"],
      ["Hard boundary", "No scores · no routing · no live thresholds"],
      ["Audit + versions", "Model/prompt · evidence IDs"],
      ["Fail closed", "Model failure must not delay delivery"],
    ],
  };
  const boxes = (nodes[level] || nodes.context)
    .map(
      ([title, sub]) =>
        `<div class="c4-box"><strong>${esc(title)}</strong><span>${esc(sub)}</span></div>`
    )
    .join("");
  return `<div class="c4-static" role="img" aria-label="${esc(view.caption)}">${boxes}</div>
    <p class="c4-fallback">Static C4 view (CSP-safe). Caption and legend describe this level.</p>`;
}

async function renderC4(level) {
  if (!c4DiagramEl) return;
  const view = C4_VIEWS[level] || C4_VIEWS.context;
  c4Active = level;
  document.querySelectorAll(".c4-tab").forEach((tab) => {
    const on = tab.dataset.c4 === level;
    tab.classList.toggle("active", on);
    tab.setAttribute("aria-selected", on ? "true" : "false");
  });
  if (c4CaptionEl) c4CaptionEl.textContent = view.caption;
  if (c4LegendEl) {
    c4LegendEl.innerHTML = (view.legend || []).map((item) => `<li>${esc(item)}</li>`).join("");
  }
  c4DiagramEl.innerHTML = renderC4Static(level, view);
  c4Rendered = true;
  c4Ready = true;
}

function initC4Tabs() {
  document.querySelectorAll(".c4-tab").forEach((tab) => {
    tab.addEventListener("click", () => {
      renderC4(tab.dataset.c4);
    });
  });
}

function setView(view) {
  state.view = view;
  const panes = {
    alerts: viewAlerts,
    explain: viewExplain,
    benchmarks: viewBenchmarks,
  };
  Object.entries(panes).forEach(([key, el]) => {
    if (!el) return;
    const on = key === view;
    el.classList.toggle("hidden", !on);
    el.hidden = !on;
  });
  if (hideAckChip) hideAckChip.classList.toggle("hidden", view !== "alerts");
  if (pageTitle) {
    pageTitle.textContent =
      view === "alerts" ? "Curie" : view === "benchmarks" ? "Benchmarks" : "How Curie works";
  }
  if (view === "explain") {
    renderC4(c4Active || "context");
    const steps = FLOW_SCENARIOS[flowState.scenario]?.steps || [];
    if (steps[flowState.step]) applyFlowStep(steps[flowState.step]);
  } else {
    stopFlowPlay();
  }
  document.querySelectorAll(".rail-btn[data-view]").forEach((btn) => {
    const on = btn.dataset.view === view;
    btn.classList.toggle("active", on);
    if (on) btn.setAttribute("aria-current", "page");
    else btn.removeAttribute("aria-current");
  });
}

function esc(s) {
  return String(s ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function renderMetricList(metrics) {
  return `<ul class="bench-metrics">${(metrics || [])
    .map(
      (m) => `<li>
        <div class="bm-top"><span>${esc(m.label)}</span><strong>${esc(m.value)}</strong></div>
        <p class="bm-explain">${esc(m.explain)}</p>
      </li>`
    )
    .join("")}</ul>`;
}

async function loadBenchmarks() {
  if (!benchmarkListEl) return;
  try {
    const summary = await fetchJson("/benchmarks");
    if (benchDisclaimer) benchDisclaimer.textContent = summary.disclaimer || "";
    if (benchHowto) {
      const steps = summary.how_to_use_this_page || [];
      benchHowto.innerHTML = steps.length
        ? `<h3 class="section-label" style="margin:0">How to use this page</h3><ol>${steps
            .map((s) => `<li>${esc(s)}</li>`)
            .join("")}</ol>`
        : "";
    }
    benchmarkListEl.innerHTML = (summary.benchmarks || [])
      .map((b) => {
        const holdout = b.published_holdout
          ? `<h4>Published holdout</h4>
             <p class="meta">${esc(b.published_holdout.source)}</p>
             <p class="meta">${esc(b.published_holdout.window_note || "")}</p>
             ${renderMetricList(b.published_holdout.metrics)}`
          : "";
        const caveats = (b.caveats || []).map((c) => `<li>${esc(c)}</li>`).join("");
        return `<article class="bench-card" aria-expanded="false" data-bench="${esc(b.id)}">
          <button type="button" class="bench-card-toggle">
            <div>
              <p class="meta" style="margin:0 0 0.2rem">${esc(b.status_label || "")}</p>
              <h3 class="bench-card-title">${esc(b.title)}</h3>
              <p class="bench-card-what">${esc(b.what)}</p>
            </div>
            <span class="bench-tier ${esc(b.tier)}">${esc((b.tier || "").replaceAll("_", " "))}</span>
          </button>
          <div class="bench-body">
            <h4>How to read</h4>
            <p>${esc(b.how_to_read)}</p>
            <h4>Metrics</h4>
            ${renderMetricList(b.metrics)}
            ${holdout}
            <h4>Caveats</h4>
            <ul>${caveats}</ul>
            <div class="bench-meta-row">
              Docs: <code>${esc(b.docs || "—")}</code><br />
              Reproduce: <code>${esc(b.reproduce || "—")}</code>
            </div>
          </div>
        </article>`;
      })
      .join("");
    benchmarkListEl.querySelectorAll(".bench-card").forEach((card) => {
      card.querySelector(".bench-card-toggle")?.addEventListener("click", () => {
        const open = card.getAttribute("aria-expanded") === "true";
        benchmarkListEl
          .querySelectorAll(".bench-card")
          .forEach((c) => c.setAttribute("aria-expanded", "false"));
        card.setAttribute("aria-expanded", open ? "false" : "true");
      });
    });
  } catch (err) {
    console.warn("benchmarks unavailable", err);
    if (benchDisclaimer) {
      benchDisclaimer.textContent = "Benchmarks unavailable — is /benchmarks served by this API?";
    }
    if (benchmarkListEl) benchmarkListEl.innerHTML = "";
  }
}

function renderWorkflows() {
  if (!workflowListEl) return;
  workflowListEl.innerHTML = WORKFLOWS.map((wf) => {
    const idClass = wf.status === "live" ? "" : wf.where === "connect" ? "connect" : "planned";
    return `<button type="button" class="wf-row" aria-expanded="false" data-wf="${esc(wf.id)}">
      <span class="wf-id ${idClass}">${esc(wf.id)}</span>
      <div class="wf-body">
        <h4>${esc(wf.title)}</h4>
        <p>${esc(wf.blurb)}</p>
        <div class="wf-detail">${esc(wf.detail)}</div>
      </div>
      <span class="wf-status ${wf.status === "live" ? "live" : ""}">${esc(wf.statusLabel)}</span>
    </button>`;
  }).join("");
  workflowListEl.querySelectorAll(".wf-row").forEach((row) => {
    row.addEventListener("click", () => {
      const open = row.getAttribute("aria-expanded") === "true";
      workflowListEl.querySelectorAll(".wf-row").forEach((r) => r.setAttribute("aria-expanded", "false"));
      row.setAttribute("aria-expanded", open ? "false" : "true");
    });
  });
}

function fillEpisodePicker() {
  if (!episodePick) return;
  const opts = state.episodes || [];
  episodePick.innerHTML = opts.length
    ? opts
        .map((ep) => {
          const label = `${esc(ep.episode_id)} · ${esc(ep.dominant_signal_type || "—")} · ${esc(ep.dominant_severity)}`;
          return `<option value="${esc(ep.episode_id)}">${label}</option>`;
        })
        .join("")
    : `<option value="">No episodes loaded</option>`;
  if (episodeExplainBtn) episodeExplainBtn.disabled = !opts.length;
}

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
      <strong class="stat-value">${esc(m.open_alerts)}</strong>
      <span class="stat-sub">Needs review</span>
    </article>
    <article class="stat-card critical">
      <span class="stat-label">Critical</span>
      <strong class="stat-value">${esc(m.by_tier.critical || 0)}</strong>
      <span class="stat-sub">Highest acuity</span>
    </article>
    <article class="stat-card urgent">
      <span class="stat-label">Urgent</span>
      <strong class="stat-value">${esc(m.by_tier.urgent || 0)}</strong>
      <span class="stat-sub">Interruptive</span>
    </article>
    <article class="stat-card watch">
      <span class="stat-label">Watch</span>
      <strong class="stat-value">${esc(m.by_tier.watch || 0)}</strong>
      <span class="stat-sub">Passive flag</span>
    </article>
    <article class="stat-card ok">
      <span class="stat-label">Acknowledged</span>
      <strong class="stat-value">${esc(m.acknowledged_alerts)}</strong>
      <span class="stat-sub">of ${esc(m.total_alerts)} total</span>
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
              <strong>${esc(name)}</strong>
              <span class="tier-chip ${esc(ep.dominant_severity)}">${esc(ep.status)}</span>
            </div>
            <div class="episode-dom">${esc(ep.dominant_signal_type || "—")} · ${esc(ep.dominant_severity)}</div>
            <div class="meta">support: ${esc(support)}</div>
            <div class="meta">pages ${esc(ep.page_count)} · passive ${esc(ep.passive_update_count)}</div>
          </article>`;
        })
        .join("")}
    </div>
  `;
  fillEpisodePicker();
}

async function loadClaims() {
  if (!claimsEl) return;
  try {
    const matrix = await fetchJson("/claims-matrix");
    const groups = [
      ["demonstrated", "Demonstrated"],
      ["under_evaluation", "Under evaluation"],
      ["not_claimed", "Not claimed"],
    ];
    claimsEl.innerHTML = `
      <div class="section-title-row">
        <h2>Claims matrix</h2>
        <p class="hint">Investor posture · not regulatory · see docs/research/claims-matrix.md</p>
      </div>
      <div class="claims-grid">
        ${groups
          .map(([key, label]) => {
            const rows = (matrix.claims || []).filter((c) => c.status === key);
            return `<article class="claims-col ${key}">
              <h3>${label}</h3>
              <ul>${rows
                .map((c) => `<li><code>${esc(c.id)}</code> ${esc(c.claim)}</li>`)
                .join("")}</ul>
            </article>`;
          })
          .join("")}
      </div>
    `;
  } catch (err) {
    console.warn("claims matrix unavailable", err);
    claimsEl.innerHTML = "";
  }
}

async function loadInvestorDemo() {
  if (!investorEl) return;
  try {
    const report = await fetchJson("/investor-demo");
    const vol = report.timeline?.volume || {};
    const chaos = report.chaos_all_passed ? "passed" : "failed";
    investorEl.innerHTML = `
      <div class="section-title-row">
        <h2>Investor demo snapshot</h2>
        <p class="hint">Multi-signal → one episode · chaos ${esc(chaos)}</p>
      </div>
      <div class="investor-row">
        <article class="investor-card">
          <span class="stat-label">Signals → episode</span>
          <strong class="stat-value">${esc(report.timeline?.signals_merged ?? "—")} → 1</strong>
          <span class="stat-sub">${esc(report.timeline?.final_episode?.dominant_signal_type || "dominant")}</span>
        </article>
        <article class="investor-card">
          <span class="stat-label">Naive pages</span>
          <strong class="stat-value">${esc(vol.naive_alert_count ?? "—")}</strong>
          <span class="stat-sub">Every emission</span>
        </article>
        <article class="investor-card">
          <span class="stat-label">Episode pages</span>
          <strong class="stat-value">${esc(vol.episode_interruptive_pages ?? "—")}</strong>
          <span class="stat-sub">vs ${vol.governed_passive_count ?? 0} passive</span>
        </article>
        <article class="investor-card">
          <span class="stat-label">Evidence + hashes</span>
          <strong class="stat-value">${(report.evidence_and_hashes || []).length}</strong>
          <span class="stat-sub">alerts with rule digests</span>
        </article>
      </div>
    `;
  } catch (err) {
    console.warn("investor demo unavailable", err);
    investorEl.innerHTML = "";
  }
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
        <div class="icon-pill ${esc(tier)}" aria-hidden="true">${indicatorGlyph(indicator)}</div>
        <span class="tier-chip ${esc(tier)}">${esc(tier)}</span>
      </div>
      <div class="card-patient">${esc(displayName(alert))}</div>
      <div class="card-score-row">
        <div class="card-score">
          <span>${view.kind === "phenotype" ? "Met" : "Score"}</span>
          ${esc(view.score ?? "—")}
        </div>
        <div class="card-meta">${esc(fmtTime(alert.event_time))}</div>
      </div>
      <div class="meter ${esc(tier)}" aria-hidden="true"><i style="width:${esc(scoreWidth(alert.score))}"></i></div>
      <div class="card-footer">
        <span class="indicator-tag">${esc(indicator)}</span>
        <span>${esc(view.kind)} · ${alert.routing ? `${esc(alert.routing)} · ` : ""}${esc(view.completeness)}${
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
  const copilot = `<div class="copilot-label">Copilot <span>additive · WF-06</span></div>`;
  if (status === "pass" && alert.narrative) {
    const claims = (alert.narrative_claims || [])
      .map(
        (c) =>
          `<li>${esc(c.text)} <span class="meta">[${esc((c.evidence_ids || []).join(", "))}]</span></li>`
      )
      .join("");
    return `
      <div class="narrative pass">
        ${copilot}
        <p>${esc(alert.narrative)}</p>
        <ul class="evidence">${claims}</ul>
        <div class="meta">model ${esc(alert.grp_model_name || "—")} · prompt ${esc(
          alert.prompt_version || alert.grp_prompt_version || "—"
        )} · score unchanged</div>
      </div>`;
  }
  if (status === "quarantine" || status === "abstain" || status === "error") {
    return `
      <div class="narrative ${status}">
        ${copilot}
        <strong>${esc(status)}</strong>
        <p>${esc(alert.quarantine_reason || "No narrative attached.")}</p>
        <div class="meta">Deterministic alert still valid · score unchanged</div>
        <button type="button" id="explainBtn" class="secondary">Retry explanation</button>
      </div>`;
  }
  return `
    <div class="narrative none">
      ${copilot}
      <p class="meta">No narrative yet. Copilot cannot change the score or routing.</p>
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
        return `<li class="comp-item missing"><div class="comp-head"><strong>${esc(c.name)}</strong><span>missing</span></div></li>`;
      }
      return `
        <li class="comp-item">
          <div class="comp-head">
            <strong>${esc(c.name)}</strong>
            <span>${esc(c.points ?? 0)} pts</span>
          </div>
          <div class="comp-bar" aria-hidden="true"><i style="width:${esc(componentWidth(c.points))}"></i></div>
          <div class="meta">${esc((c.evidence_ids || []).join(", ") || "no evidence ids")}</div>
        </li>`;
    })
    .join("");

  const evidence = (view.evidence || [])
    .map((e) => `<li><code>${esc(e)}</code></li>`)
    .join("");
  const missing = (view.missing || [])
    .map((m) => `<li><code>${esc(m)}</code></li>`)
    .join("");
  const criteria = (view.criteria || [])
    .map((c) => `<li><code>${esc(c)}</code></li>`)
    .join("");
  const exclusions = (view.exclusions || [])
    .map((e) => `<li><code>${esc(e)}</code></li>`)
    .join("");

  detailEl.innerHTML = `
    <div class="detail-hero">
      <div class="detail-score"><small>${view.kind === "phenotype" ? "Met" : "Score"}</small>${esc(view.score ?? "—")}</div>
      <div>
        <h3>${esc(displayName(alert))}</h3>
        <p class="meta">${esc(alert.alert_id)} · ${esc(patientIdLabel(alert.patient_id))}</p>
        <div class="badges">
          <span class="badge tier-chip ${esc(view.severity)}">${esc(view.severity)}</span>
          <span class="badge">${esc(view.type)}</span>
          <span class="badge">${esc(view.kind)}</span>
          <span class="badge">${esc(view.completeness)}</span>
          <span class="badge">${esc(view.resolution)}</span>
          <span class="badge">${esc(alert.governance_path)}</span>
          ${
            alert.routing
              ? `<span class="badge routing-chip ${esc(alert.routing)}">${esc(alert.routing)}</span>`
              : ""
          }
          ${
            alert.page_deferred_reason
              ? `<span class="badge">deferred: ${esc(alert.page_deferred_reason)}</span>`
              : ""
          }
          ${view.stage != null ? `<span class="badge">stage ${esc(view.stage)}</span>` : ""}
          <span class="badge">${esc(view.ruleId)}@${esc(view.ruleVersion)}</span>
        </div>
      </div>
    </div>
    <p class="meta">Event ${esc(fmtTime(alert.event_time))} · Encounter ${esc(alert.encounter_id || "—")}
      ${view.onset ? ` · Onset ${esc(fmtTime(view.onset))}` : ""}</p>
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
        ? `<div class="ack-note">Acknowledged ${esc(fmtTime(alert.acknowledged_at))}${
            alert.acknowledge_note ? ` — ${esc(alert.acknowledge_note)}` : ""
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

hideAckEl?.addEventListener("change", async () => {
  state.hideAck = hideAckEl.checked;
  await loadAlerts();
});

document.querySelectorAll(".rail-btn[data-view]").forEach((btn) => {
  btn.addEventListener("click", () => setView(btn.dataset.view));
});

if (episodeExplainBtn) {
  episodeExplainBtn.addEventListener("click", async () => {
    const id = episodePick?.value;
    if (!id) return;
    episodeExplainBtn.disabled = true;
    episodeExplainOut.textContent = "Generating…";
    try {
      const updated = await fetchJson(`/episodes/${encodeURIComponent(id)}/explain`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ force: true }),
      });
      const claims = (updated.narrative_claims || [])
        .map((c) => `• ${esc(c.text)} [${esc((c.evidence_ids || []).join(", "))}]`)
        .join("\n");
      episodeExplainOut.innerHTML = `
        <div class="copilot-label">Status <span>${esc(updated.narrative_status || "—")}</span></div>
        <p>${esc(updated.narrative || updated.quarantine_reason || "No narrative.")}</p>
        <pre class="meta" style="white-space:pre-wrap;margin:0.4rem 0 0">${claims || "No claims"}</pre>
        <div class="meta">model ${esc(updated.grp_model_name || "—")} · routing unchanged</div>`;
      state.episodes = state.episodes.map((e) =>
        e.episode_id === updated.episode_id ? updated : e
      );
    } catch (err) {
      episodeExplainOut.textContent = `Failed: ${err.message}`;
    } finally {
      episodeExplainBtn.disabled = false;
    }
  });
}

if (stewardClassifyBtn) {
  stewardClassifyBtn.addEventListener("click", async () => {
    const textVal = (stewardText?.value || "").trim();
    if (!textVal) return;
    stewardClassifyBtn.disabled = true;
    stewardOut.textContent = "Classifying…";
    try {
      const result = await fetchJson("/stewardship/classify", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text: textVal }),
      });
      stewardOut.innerHTML = `
        <div class="copilot-label">Category <span>${esc(result.category || "—")}</span></div>
        <p>confidence ${esc((result.confidence ?? 0).toFixed(2))} · method ${esc(result.method || "—")}</p>
        <p class="meta">hints: ${esc((result.matched_hints || []).join(", ") || "none")}</p>
        <div class="meta">mutates_active_rules=${esc(result.mutates_active_rules)} · never changes live rules</div>`;
    } catch (err) {
      stewardOut.textContent = `Failed: ${err.message}`;
    } finally {
      stewardClassifyBtn.disabled = false;
    }
  });
}

(async function init() {
  renderWorkflows();
  initC4Tabs();
  initFlowAnim();
  setView("alerts");
  await loadMetrics();
  await loadClaims();
  await loadInvestorDemo();
  await loadBenchmarks();
  await loadAlerts();
  await loadEpisodes();
  if (state.alerts[0]) {
    state.selectedId = state.alerts[0].alert_id;
    renderList();
    renderDetail(state.alerts[0]);
  }
})();
