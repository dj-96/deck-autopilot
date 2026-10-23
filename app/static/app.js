"use strict";
// Deck Autopilot front end: start a run, poll its trace, render the checked deck.
// All model-written text goes through esc() before it touches the DOM.

const $ = (id) => document.getElementById(id);
const state = { source: "sample", files: { prev: null, curr: null }, jobId: null, result: null, slide: 0, poll: null };

const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const fmtInt = (n) => Math.round(n || 0).toLocaleString("en-US");
const fmtUsd = (n, d = 4) => "$" + (n || 0).toFixed(d);

// ---------- tabs ----------
document.querySelectorAll(".tab").forEach((t) => t.addEventListener("click", () => {
  document.querySelectorAll(".tab").forEach((x) => x.classList.toggle("active", x === t));
  ["build", "safety", "usage"].forEach((v) => ($("view-" + v).hidden = v !== t.dataset.tab));
  if (t.dataset.tab === "usage") loadUsage();
}));

// ---------- status pills ----------
async function loadStatus() {
  try {
    const s = await (await fetch("/api/status")).json();
    // Until a call fails over, we only know the order we'll try, not which gateway will answer.
    const via = s.gateways_disabled.includes("portkey") || !s.keys_present.portkey ? "via OpenAI"
      : (s.keys_present.openai ? "Portkey → OpenAI fallback" : "via Portkey");
    $("model-pill").textContent = `${s.model} · ${via}`;
    $("spend-pill").textContent = `Today ${fmtUsd(s.spent_today_usd, 3)} / $${s.daily_budget_usd.toFixed(2)}`;
    if (!s.keys_present.portkey && !s.keys_present.openai) {
      $("model-pill").textContent = "No API key found";
      $("model-pill").style.color = "var(--red)";
    }
    renderLimits(s);
    return s;
  } catch { /* server restarting; ignore */ }
}

// ---------- data inputs ----------
function setSource(src) {
  state.source = src;
  $("use-sample").classList.toggle("selected", src === "sample");
  const p = state.files.prev?.name, c = state.files.curr?.name;
  $("source-line").textContent = src === "sample" ? "Source: sample client data (Northwind Outdoor Co.)"
    : `Source: ${p || "?"} → ${c || "?"}`;
  $("poisoned").disabled = src !== "sample";
}
["prev", "curr"].forEach((k) => {
  const input = $("file-" + k), drop = $("drop-" + k);
  input.addEventListener("change", () => {
    state.files[k] = input.files[0] || null;
    $("name-" + k).textContent = state.files[k]?.name || "Drop CSV or Excel";
    drop.classList.toggle("has-file", !!state.files[k]);
    setSource(state.files.prev || state.files.curr ? "upload" : "sample");
    $("form-error").textContent = "";
  });
  drop.addEventListener("dragover", (e) => { e.preventDefault(); drop.classList.add("over"); });
  drop.addEventListener("dragleave", () => drop.classList.remove("over"));
  drop.addEventListener("drop", () => drop.classList.remove("over"));
});
$("use-sample").addEventListener("click", () => {
  state.files = { prev: null, curr: null };
  ["prev", "curr"].forEach((k) => { $("file-" + k).value = ""; $("name-" + k).textContent = "Drop CSV or Excel"; $("drop-" + k).classList.remove("has-file"); });
  setSource("sample");
  $("form-error").textContent = "";
});

// ---------- run ----------
$("run").addEventListener("click", async () => {
  $("form-error").textContent = "";
  const fd = new FormData();
  if (state.source === "upload") {
    if (!state.files.prev || !state.files.curr) { $("form-error").textContent = "Add both files, or use the sample client."; return; }
    fd.append("mode", "upload"); fd.append("prev", state.files.prev); fd.append("curr", state.files.curr);
  } else {
    fd.append("mode", $("poisoned").checked ? "poisoned" : "sample");
  }
  fd.append("tamper", $("tamper").checked ? "true" : "false");
  $("run").disabled = true; $("run").textContent = "Building…";
  try {
    const res = await fetch("/api/run", { method: "POST", body: fd });
    const body = await res.json();
    if (!res.ok) throw new Error(body.detail || "Couldn't start the run.");
    state.jobId = body.job_id;
    startRunUI();
    state.poll = setInterval(pollJob, 900);
    pollJob();
  } catch (err) {
    $("form-error").textContent = err.message;
    resetRunButton();
  }
});

function resetRunButton() { $("run").disabled = false; $("run").textContent = "Refresh my deck"; }

function startRunUI() {
  $("empty").hidden = true; $("result").hidden = true; $("error-box").hidden = true; $("running").hidden = false;
  document.querySelectorAll("#steps li").forEach((li) => { li.className = ""; li.querySelector("em").textContent = ""; });
}

async function pollJob() {
  let job;
  try { job = await (await fetch(`/api/jobs/${state.jobId}`)).json(); } catch { return; }
  updateSteps(job);
  updateMeter(job.usage, job.elapsed_s);
  if (job.status === "done") {
    clearInterval(state.poll);
    state.result = job.result;
    $("running").hidden = true;
    renderResult(job.result);
    renderSafety(job.result);
    resetRunButton(); loadStatus();
  } else if (job.status === "error") {
    clearInterval(state.poll);
    $("running").hidden = true;
    $("error-box").hidden = false;
    $("error-box").textContent = job.error?.message || "The run failed.";
    if (!state.result) $("empty").hidden = false;
    resetRunButton(); loadStatus();
  }
}

// ---------- agent steps (derived from the live trace) ----------
function updateSteps(job) {
  stepStates(job);
  const active = document.querySelector("#steps li.active b");
  $("running-detail").textContent = active ? `${active.textContent} working…` : "Finishing…";
}

function stepStates(job) {
  const t = job.trace, by = (a, k) => t.filter((e) => e.agent === a && (!k || e.kind === k));
  const li = (s) => document.querySelector(`#steps li[data-step="${s}"]`);
  const set = (s, cls, text) => { li(s).className = cls; if (text !== undefined) li(s).querySelector("em").textContent = text; };
  const failed = job.status === "error";

  const guardDone = by("guard", "done")[0], quarantined = by("guard", "safety").length;
  if (guardDone) set("guard", quarantined ? "warn" : "done", quarantined ? `${quarantined} cell(s) quarantined` : "Clean: no instructions found in the data");
  else set("guard", failed ? "failed" : "active", failed ? "Upload rejected" : "Checking files…");
  if (!guardDone) { ["analyst", "storyliner", "factchecker", "renderer"].forEach((s) => set(s, "", "")); return; }

  const aDone = by("analyst", "done")[0], tools = by("analyst", "tool_call");
  if (aDone) set("analyst", "done", `${tools.length} tool calls · ${job.result?.stats?.facts ?? ""} facts`.replace(" ·  facts", ""));
  else { const last = tools[tools.length - 1]; set("analyst", failed ? "failed" : "active", last ? `${tools.length} · ${last.detail.split("(")[0]}…` : "Planning the analysis…"); }
  if (!aDone) { ["storyliner", "factchecker", "renderer"].forEach((s) => set(s, "", "")); return; }

  const drafts = by("storyliner", "model_call"), checks = by("factchecker", "check");
  const lastCheck = checks[checks.length - 1];
  const fixing = lastCheck && /[1-9]\d* violation/.test(lastCheck.detail) && drafts.length <= checks.length && !job.result;
  if (!drafts.length) set("storyliner", failed ? "failed" : "active", "Writing slides…");
  else set("storyliner", fixing ? "active" : "done", fixing ? `Fixing draft ${drafts.length}…` : `${drafts.length} draft(s)`);

  if (!drafts.length) { set("factchecker", "", ""); set("renderer", "", ""); return; }
  const caught = checks.reduce((n, c) => n + (+((c.detail.match(/(\d+) violation/) || [])[1] || 0)), 0);
  if (!checks.length || fixing) set("factchecker", "active", fixing ? `Caught ${caught}, sent back` : "Checking every number…");
  else {
    const m = lastCheck.detail.match(/(\d+)\/(\d+) numbers verified/);
    const passed = /0 violation/.test(lastCheck.detail);
    set("factchecker", passed ? (caught ? "warn" : "done") : "failed",
      `${m ? m[1] + "/" + m[2] + " verified" : ""}${caught ? ` · caught ${caught}, fixed` : ""}${passed ? "" : " · flagged"}`);
  }
  const rDone = by("renderer", "done")[0];
  if (rDone) set("renderer", "done", rDone.detail.replace("Built ", ""));
  else if (checks.length && !fixing) set("renderer", failed ? "failed" : "active", "Building .pptx…");

}

function updateMeter(u, elapsed) {
  if (!u) return;
  $("m-in").textContent = fmtInt(u.input_tokens);
  $("m-cached").textContent = fmtInt(u.cached_tokens);
  $("m-out").textContent = fmtInt(u.output_tokens);
  $("m-calls").textContent = fmtInt(u.calls);
  $("m-cost").textContent = fmtUsd(u.cost_usd);
  $("m-time").textContent = `${Math.round(elapsed || 0)}s`;
}

// ---------- result ----------
function slidesOf(r) {
  return [{ kind: "title" }, { kind: "summary" }, ...r.deck.slides.map((s, i) => ({ kind: "content", i }))];
}

function renderResult(r) {
  $("result").hidden = false;
  const c = r.check, rounds = r.check_rounds;
  const caught = rounds.reduce((n, x) => n + x.violations.length, 0);
  const b = [];
  b.push(c.passed ? `<span class="badge good">✓ ${c.verified}/${c.numbers_checked} numbers traced to data</span>`
    : `<span class="badge bad">${c.violations.length} number(s) unverified, flagged on slides</span>`);
  if (r.quarantined.length) b.push(`<span class="badge alert">${r.quarantined.length} injected instruction(s) blocked</span>`);
  if (caught) b.push(`<span class="badge alert">${caught} made-up number(s) caught${c.passed ? `, fixed in draft ${rounds.length}` : ""}</span>`);
  if (c.auto_cited.length) b.push(`<span class="badge info">${c.auto_cited.length} citation(s) auto-added</span>`);
  b.push(`<span class="badge info">${r.stats.facts} facts from ${r.stats.tool_calls} tool calls</span>`);
  $("badges").innerHTML = b.join("");
  $("download").href = `/api/jobs/${state.jobId}/deck.pptx`;
  $("n-findings").textContent = r.findings.length;
  renderChanges(r);
  $("changes").hidden = true; $("trace-panel").hidden = true;
  state.slide = 0;
  renderSlide();
}

function badSet(r) { return new Set(r.check.violations.map((v) => v.where)); }

function bulletsHTML(items, prefix, bad) {
  return "<ul>" + items.map((b, i) => {
    const where = `${prefix} bullet ${i + 1}`, isBad = bad.has(where);
    const chk = isBad ? "⚠ unverified" : (b.fact_ids.length ? `✓ ${b.fact_ids.length}` : "");
    return `<li class="${isBad ? "bad" : ""}" data-facts="${esc(b.fact_ids.join(","))}" data-where="${esc(where)}">${esc(b.text)}<span class="chk">${chk}</span></li>`;
  }).join("") + "</ul>";
}

function renderSlide() {
  const r = state.result, list = slidesOf(r), cur = list[state.slide], bad = badSet(r), el = $("slide");
  const total = list.length;
  const foot = `<div class="foot"><span>Source: client data files. ${r.check.passed ? "All numbers fact-checked." : "Unverified numbers flagged."}</span><span>${state.slide + 1} / ${total}</span></div>`;
  el.className = "slide";
  let notes = "";
  if (cur.kind === "title") {
    el.className = "slide title-slide";
    el.innerHTML = `<div class="accent"></div><h2>${esc(r.deck.deck_title)}</h2><div class="sub">${esc(r.deck.subtitle)}</div>
      <div class="stamp">${r.check.passed ? "All numbers fact-checked against the source data" : "Some numbers could not be verified"}</div>`;
    notes = `${r.periods.previous} → ${r.periods.current} · ${r.stats.rows} rows · metrics: ${r.stats.metrics.join(", ")}`;
  } else if (cur.kind === "summary") {
    el.innerHTML = `<h3>Executive summary</h3>${bulletsHTML(r.deck.executive_summary, "executive summary", bad)}${foot}`;
    notes = "Click any bullet to see the facts behind its numbers.";
  } else {
    const s = r.deck.slides[cur.i], chart = r.charts[cur.i], n = cur.i + 1;
    el.innerHTML = `<h3 class="${bad.has(`slide ${n} title`) ? "bad" : ""}" data-facts="${esc(s.title_fact_ids.join(","))}">${esc(s.title)}</h3>
      <div class="slide-body ${chart ? "with-chart" : ""}"><div>${bulletsHTML(s.bullets, `slide ${n}`, bad)}</div>
      ${chart ? `<div class="chart"><div class="chart-title">${esc(chart.title)}</div>${chartSVG(chart)}</div>` : ""}</div>${foot}`;
    notes = s.speaker_notes;
  }
  $("notes").textContent = notes;
  $("slide-count").textContent = `Slide ${state.slide + 1} of ${total}`;
  $("dots").innerHTML = list.map((_, i) => `<button class="${i === state.slide ? "on" : ""}" data-i="${i}" aria-label="Slide ${i + 1}"></button>`).join("");
  $("dots").querySelectorAll("button").forEach((d) => d.addEventListener("click", () => { state.slide = +d.dataset.i; renderSlide(); }));
  el.querySelectorAll("li[data-facts]").forEach((li) => li.addEventListener("click", () => showFacts(li)));
  $("trace-panel").hidden = true;
}

function showFacts(li) {
  const r = state.result, ids = li.dataset.facts ? li.dataset.facts.split(",") : [];
  document.querySelectorAll(".slide li.selected").forEach((x) => x.classList.remove("selected"));
  li.classList.add("selected");
  const v = r.check.violations.filter((x) => x.where === li.dataset.where);
  let html = `<h4>Facts behind this bullet${ids.length ? "" : " (none cited)"}</h4>`;
  html += ids.map((id) => {
    const f = r.facts[id];
    return f ? `<div class="fact-row"><code>${esc(id)}</code><span class="val">${esc(f.display)}</span><span>${esc(f.label)}<span class="src">${esc(f.source)}</span></span></div>` : "";
  }).join("");
  if (v.length) html += `<p style="color:var(--red)">Unverified: ${v.map((x) => esc(`"${x.number}" (${x.reason})`)).join("; ")}</p>`;
  $("trace-panel").innerHTML = html;
  $("trace-panel").hidden = false;
}

function renderChanges(r) {
  const items = [...r.findings].sort((a, b) => b.importance - a.importance);
  $("changes").innerHTML = "<h4>What changed: the Analyst's findings, most important first</h4>" + items.map((f) =>
    `<div class="finding"><span class="imp">${f.importance}</span>${esc(f.finding)}${f.explanation ? `<small>Why: ${esc(f.explanation)}</small>` : ""}</div>`).join("");
}
$("show-changes").addEventListener("click", () => { $("changes").hidden = !$("changes").hidden; });
$("prev-slide").addEventListener("click", () => step(-1));
$("next-slide").addEventListener("click", () => step(1));
document.addEventListener("keydown", (e) => {
  if (!state.result || $("view-build").hidden || e.target.tagName === "INPUT") return;
  if (e.key === "ArrowRight") step(1);
  if (e.key === "ArrowLeft") step(-1);
});
function step(d) {
  if (!state.result) return;
  const n = slidesOf(state.result).length;
  state.slide = (state.slide + d + n) % n;
  renderSlide();
}

// ---------- chart (values come from the fact table, same as the .pptx) ----------
function chartSVG(c) {
  const pts = c.points, vals = pts.map((p) => p.value);
  const max = Math.max(0, ...vals), min = Math.min(0, ...vals), span = (max - min) || 1;
  if (c.type === "bar") {
    // Leave room for value labels on whichever side has bars, so the longest bar's label isn't clipped.
    const W = 520, rowH = 44, H = pts.length * rowH + 8, labelW = 150;
    const leftPad = min < 0 ? 64 : 8, rightPad = max > 0 ? 64 : 8;
    const area = W - labelW - leftPad - rightPad, x0 = labelW + leftPad + area * (-min / span);
    let svg = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(c.title)}">`;
    pts.forEach((p, i) => {
      const y = i * rowH + 6, w = Math.abs(p.value) / span * area, x = p.value >= 0 ? x0 : x0 - w;
      svg += `<text x="${labelW - 6}" y="${y + rowH / 2}" text-anchor="end" dominant-baseline="central" font-size="15" fill="#3f3f46">${esc(p.label)}</text>`;
      svg += `<rect x="${x}" y="${y + 4}" width="${Math.max(w, 1)}" height="${rowH - 12}" rx="2" fill="${p.value >= 0 ? "#ff2e93" : "#0b0b0d"}"><title>${esc(p.fact_id)}: ${esc(p.display)}</title></rect>`;
      const tx = p.value >= 0 ? x + w + 5 : x - 5;
      svg += `<text x="${tx}" y="${y + rowH / 2}" text-anchor="${p.value >= 0 ? "start" : "end"}" dominant-baseline="central" font-size="15" font-weight="700" fill="#18181b">${esc(p.display)}</text>`;
    });
    return svg + `<line x1="${x0}" x2="${x0}" y1="2" y2="${H - 2}" stroke="#a1a1aa"/></svg>`;
  }
  const W = 520, H = 260, top = 24, bottom = 36, area = H - top - bottom, colW = W / pts.length, y0 = top + area * (max / span);
  let svg = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(c.title)}">`;
  pts.forEach((p, i) => {
    const h = Math.abs(p.value) / span * area, x = i * colW + colW * 0.2, w = colW * 0.6, y = p.value >= 0 ? y0 - h : y0;
    svg += `<rect x="${x}" y="${y}" width="${w}" height="${Math.max(h, 1)}" rx="2" fill="${p.value >= 0 ? "#ff2e93" : "#0b0b0d"}"><title>${esc(p.fact_id)}: ${esc(p.display)}</title></rect>`;
    svg += `<text x="${x + w / 2}" y="${p.value >= 0 ? y - 6 : y + h + 14}" text-anchor="middle" font-size="15" font-weight="700" fill="#18181b">${esc(p.display)}</text>`;
    svg += `<text x="${x + w / 2}" y="${H - 12}" text-anchor="middle" font-size="14" fill="#3f3f46">${esc(p.label)}</text>`;
  });
  return svg + `<line x1="0" x2="${W}" y1="${y0}" y2="${y0}" stroke="#a1a1aa"/></svg>`;
}

// ---------- safety tab ----------
function renderSafety(r) {
  const caught = r.check_rounds.reduce((n, x) => n + x.violations.length, 0);
  const events = r.safety.length;
  $("safety-count").hidden = !events; $("safety-count").textContent = events;
  $("safety-cards").innerHTML = [
    ["Injected instructions blocked", r.quarantined.length, "Quarantined before any model call"],
    ["Numbers verified", `${r.check.verified}/${r.check.numbers_checked}`, r.check.passed ? "Every number traced to a fact" : "Unverified numbers flagged"],
    ["Made-up numbers caught", caught, caught ? `Sent back, ${r.check.passed ? "fixed" : "still flagged"} after ${r.check_rounds.length} draft(s)` : "None this run"],
    ["Run cost", fmtUsd(r.usage.cost_usd), `${fmtInt(r.usage.input_tokens + r.usage.output_tokens)} tokens of ${fmtInt(120000)} cap`],
  ].map(([k, v, s]) => `<div class="stat"><small>${k}</small><b>${esc(v)}</b><span>${esc(s)}</span></div>`).join("");
  $("events").innerHTML = r.safety.length ? r.safety.map((e) => {
    const inj = e.defense === "guard_injection";
    return `<li><span class="tag ${inj ? "inj" : "fc"}">${inj ? "Prompt injection" : "Fact-check"}</span>${esc(e.detail)}
      ${e.excerpt ? `<blockquote>${esc(e.excerpt)}</blockquote>` : ""}${e.text ? `<blockquote>${esc(e.text)}</blockquote>` : ""}</li>`;
  }).join("") : `<li class="muted">No attacks or bad numbers this run. Try the safety demos under "Data" to see the defenses fire.</li>`;
  $("rounds").innerHTML = r.check_rounds.map((x) => `<div class="round"><b>Draft ${x.draft}</b>: ${x.verified}/${x.numbers_checked} numbers verified,
    ${x.auto_cited.length} citation(s) auto-added, ${x.violations.length} violation(s)
    ${x.violations.map((v) => `<div class="v">✗ ${esc(v.where)}: "${esc(v.number)}" (${esc(v.reason)})</div>`).join("")}</div>`).join("");
}

function renderLimits(s) {
  $("limits").innerHTML = [
    `<b>Prompt-injection scan</b> on every text cell before any model sees the data`,
    `<b>Fact-checker</b>: every number on a slide must match the data, up to 2 fix rounds, then flagged`,
    `<b>${fmtInt(s.max_tokens_per_run)} tokens</b> per run, then the run stops`,
    `<b>10 Analyst turns, 30 tool calls</b> per run, so an agent can't loop forever`,
    `<b>$${s.daily_budget_usd.toFixed(2)} daily budget</b> across all runs (spent today: ${fmtUsd(s.spent_today_usd, 4)})`,
    `<b>2 MB / 5,000 rows</b> per file; <b>2 runs</b> at a time`,
  ].map((x) => `<li>${x}</li>`).join("");
}

// ---------- usage tab ----------
async function loadUsage() {
  const s = await loadStatus();
  if (s) {
    const pct = Math.min(100, s.spent_today_usd / s.daily_budget_usd * 100);
    $("budget-fill").style.width = pct + "%";
    $("budget-text").textContent = `${fmtUsd(s.spent_today_usd)} of $${s.daily_budget_usd.toFixed(2)} (${pct.toFixed(1)}%)`;
  }
  if (state.result) {
    const agg = {};
    state.result.usage.by_agent.forEach((c) => {
      const a = agg[c.agent] ||= { calls: 0, in: 0, cached: 0, out: 0, cost: 0 };
      a.calls++; a.in += c.input_tokens; a.cached += c.cached_tokens; a.out += c.output_tokens; a.cost += c.cost_usd;
    });
    const u = state.result.usage;
    $("agent-table").innerHTML = `<thead><tr><th>Agent</th><th class="num">Calls</th><th class="num">Input</th><th class="num">Cached</th><th class="num">Output</th><th class="num">Cost</th></tr></thead><tbody>` +
      Object.entries(agg).map(([k, a]) => `<tr><td>${esc(k)}</td><td class="num">${a.calls}</td><td class="num">${fmtInt(a.in)}</td><td class="num">${fmtInt(a.cached)}</td><td class="num">${fmtInt(a.out)}</td><td class="num">${fmtUsd(a.cost, 5)}</td></tr>`).join("") +
      `<tr class="total"><td>Total</td><td class="num">${u.calls}</td><td class="num">${fmtInt(u.input_tokens)}</td><td class="num">${fmtInt(u.cached_tokens)}</td><td class="num">${fmtInt(u.output_tokens)}</td><td class="num">${fmtUsd(u.cost_usd, 5)}</td></tr></tbody>`;
  }
  const h = await (await fetch("/api/usage")).json();
  if (h.runs.length) {
    $("history-table").innerHTML = `<thead><tr><th>When</th><th>Files</th><th class="num">Drafts</th><th class="num">Input (cached)</th><th class="num">Output</th><th class="num">Cost</th><th class="num">Time</th><th>Checks</th></tr></thead><tbody>` +
      h.runs.map((x) => `<tr><td>${esc(x.date)} ${esc(x.time)}</td><td>${esc(x.curr)}${x.tamper ? " (tamper test)" : ""}</td><td class="num">${x.drafts}</td>
        <td class="num">${fmtInt(x.usage.input_tokens)} (${fmtInt(x.usage.cached_tokens)})</td><td class="num">${fmtInt(x.usage.output_tokens)}</td>
        <td class="num">${fmtUsd(x.usage.cost_usd)}</td><td class="num">${Math.round(x.elapsed_s)}s</td>
        <td>${x.verified ? "✓ verified" : "⚠ flagged"}${x.quarantined ? ` · ${x.quarantined} blocked` : ""}</td></tr>`).join("") + "</tbody>";
  }
}

// ---------- replay a saved run: /?replay=<job id>&tab=safety&slide=3&open=changes|facts ----------
async function replayFromURL() {
  const q = new URLSearchParams(location.search), id = q.get("replay");
  if (!id) return;
  const res = await fetch(`/api/replay/${encodeURIComponent(id)}`);
  if (!res.ok) { $("error-box").hidden = false; $("error-box").textContent = "Saved run not found."; return; }
  const job = await res.json();
  $("empty").hidden = true;
  if (q.get("upto")) {  // show the run as it looked mid-way: first N trace events, no result yet
    const partial = { ...job, status: "running", result: null, trace: job.trace.slice(0, +q.get("upto")) };
    $("running").hidden = false;
    updateSteps(partial);
    const calls = partial.trace.filter((e) => e.kind === "model_call" && e.tokens);
    const u = calls.reduce((a, e) => ({ input_tokens: a.input_tokens + e.tokens.input, cached_tokens: a.cached_tokens + e.tokens.cached,
      output_tokens: a.output_tokens + e.tokens.output, calls: a.calls + 1 }), { input_tokens: 0, cached_tokens: 0, output_tokens: 0, calls: 0 });
    u.cost_usd = ((u.input_tokens - u.cached_tokens) * 0.10 + u.cached_tokens * 0.01 + u.output_tokens * 0.50) / 1e6;
    updateMeter(u, partial.trace.length ? partial.trace[partial.trace.length - 1].t - job.trace[0].t : 0);
    $("run").disabled = true; $("run").textContent = "Building…";
    return;
  }
  state.result = job.result;
  updateSteps(job); updateMeter(job.usage, job.elapsed_s);
  renderResult(job.result); renderSafety(job.result);
  $("download").removeAttribute("href");
  if (q.get("demo")) {  // tick the boxes that produced this run, for screenshots
    document.querySelector(".test-modes").open = true;
    q.get("demo").split(",").forEach((id) => { const el = $(id); if (el) el.checked = true; });
  }
  if (q.get("slide")) { state.slide = +q.get("slide"); renderSlide(); }
  if (q.get("open") === "changes") $("changes").hidden = false;
  if (q.get("open") === "facts") { const li = document.querySelectorAll("#slide li")[+(q.get("bullet") || 0)]; if (li) showFacts(li); }
  if (q.get("tab")) document.querySelector(`.tab[data-tab="${q.get("tab")}"]`)?.click();
}

setSource("sample");
loadStatus();
replayFromURL();
