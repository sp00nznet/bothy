// Catalog multi-select, live resource summing, and the sticky selection bar.
(function () {
  "use strict";

  const KEY = "bothy.selection";
  const sel = new Set(JSON.parse(sessionStorage.getItem(KEY) || "[]"));

  const bar = document.getElementById("selbar");
  const countEl = document.getElementById("sel-count");
  const summaryEl = document.getElementById("sel-summary");
  const keysEl = document.getElementById("sel-keys");

  function persist() {
    sessionStorage.setItem(KEY, JSON.stringify([...sel]));
  }

  function summarise() {
    let cpu = 0, mem = 0, disk = 0;
    const names = [];
    for (const key of sel) {
      const card = document.querySelector(`.app[data-key="${CSS.escape(key)}"]`);
      if (!card) continue;
      cpu += +card.dataset.cores || 0;
      mem += +card.dataset.memory || 0;   // MB
      disk += +card.dataset.disk || 0;    // GB
      names.push(card.dataset.name);
    }
    const memLabel = mem >= 1024 ? `${(mem / 1024).toFixed(mem % 1024 ? 1 : 0)} GB` : `${mem} MB`;
    const shown = names.slice(0, 3).join(" · ");
    const more = names.length > 3 ? ` +${names.length - 3} more` : "";
    return `${shown}${more} — ${cpu} vCPU · ${memLabel} · ${disk} GB total`;
  }

  function render() {
    document.querySelectorAll(".app").forEach((card) => {
      card.classList.toggle("sel", sel.has(card.dataset.key));
    });
    if (!bar) return;
    if (sel.size === 0) {
      bar.hidden = true;
      return;
    }
    bar.hidden = false;
    countEl.textContent = `${sel.size} selected`;
    summaryEl.textContent = summarise();
    // the collection form and the batch form both need the selected keys
    for (const host of [keysEl, document.getElementById("sel-keys-2")]) {
      if (!host) continue;
      host.innerHTML = "";
      for (const k of sel) {
        const i = document.createElement("input");
        i.type = "hidden"; i.name = "keys"; i.value = k;
        host.appendChild(i);
      }
    }
  }

  // clicking the checkbox toggles selection; clicking the card still navigates
  document.addEventListener("click", (e) => {
    const box = e.target.closest(".checkbox-sel");
    if (box) {
      e.preventDefault();
      e.stopPropagation();
      const key = box.closest(".app").dataset.key;
      sel.has(key) ? sel.delete(key) : sel.add(key);
      persist();
      render();
    }
  });

  const clear = document.getElementById("sel-clear");
  if (clear) clear.addEventListener("click", () => { sel.clear(); persist(); render(); });

  // "Save as collection" needs a name
  const saveForm = document.getElementById("collection-form");
  if (saveForm) {
    saveForm.addEventListener("submit", (e) => {
      const input = saveForm.querySelector('input[name="name"]');
      if (!input.value.trim()) {
        e.preventDefault();
        const name = prompt("Collection name:");
        if (!name) return;
        input.value = name;
        saveForm.submit();
      }
    });
  }

  // Ctrl/Cmd-K focuses search
  document.addEventListener("keydown", (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
      e.preventDefault();
      const f = document.querySelector("input[name=q]") || document.querySelector(".search input");
      if (f) { f.focus(); f.select(); }
    }
  });

  // buttons that POST and then reload, with a pending state so a slow probe
  // does not look like a dead button
  document.querySelectorAll("form[data-busy]").forEach((form) => {
    form.addEventListener("submit", () => {
      const btn = form.querySelector("button");
      if (btn) { btn.disabled = true; btn.textContent = form.dataset.busy; }
    });
  });

  render();
})();

// ---- queue: poll job state and tail the active log --------------------------
(function () {
  "use strict";
  const root = document.querySelector(".queue[data-batch]");
  if (!root) return;

  const jobsEl = document.getElementById("q-jobs");
  const barEl = document.getElementById("q-bar");
  const progEl = document.getElementById("q-progress");
  const logEl = document.getElementById("log-body");
  const nameEl = document.getElementById("log-name");
  const stepEl = document.getElementById("log-step");
  const follow = document.getElementById("follow");

  const CLASS = {
    complete: "ok", installing: "accent", blocked: "danger",
    failed: "danger", cancelled: "muted", queued: "muted",
  };
  const esc = (s) => String(s).replace(/[&<>]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c]));

  function renderJobs(jobs) {
    jobsEl.innerHTML = jobs.map((j) => {
      const c = CLASS[j.status] || "muted";
      const fill = j.status === "complete" ? "var(--ok)" : "var(--accent)";
      return `<div class="job ${j.status}">
        <div class="job-top">
          <span class="dot ${c}"></span>
          <span class="job-name">${esc(j.name)}</span>
          <span class="job-target">${esc(j.target)}</span>
          <span class="job-status t-${c}">${esc(j.status[0].toUpperCase() + j.status.slice(1))}</span>
        </div>
        <div style="display:flex;align-items:center;gap:10px">
          <div class="job-bar" style="flex:1"><i style="width:${j.pct}%;background:${fill}"></i></div>
          <span class="pct">${j.pct}%</span>
        </div>
        <div class="job-meta"><span>${esc(j.reason || j.step)}</span>
          <span class="el">${esc(j.elapsed)}</span></div>
      </div>`;
    }).join("");
  }

  function renderLog(job) {
    if (!job) return;
    nameEl.textContent = job.name;
    stepEl.textContent = job.step || "";
    const atBottom = logEl.scrollHeight - logEl.scrollTop - logEl.clientHeight < 40;
    logEl.innerHTML = (job.log || []).map(
      (l) => `<div class="log-line ${l.kind}"><span class="t">${esc(l.t)}</span><span>${esc(l.text)}</span></div>`
    ).join("");
    // follow the tail unless the user has scrolled up, per the design
    if (follow.checked && atBottom) logEl.scrollTop = logEl.scrollHeight;
  }

  async function tick() {
    let b;
    try {
      b = await (await fetch("/api/queue", { headers: { Accept: "application/json" } })).json();
    } catch { return; }
    if (!b.jobs) return;
    renderJobs(b.jobs);
    const pctDone = b.total ? Math.round((b.done / b.total) * 100) : 0;
    barEl.innerHTML = `<i style="width:${pctDone}%;background:var(--ok)"></i>`;
    progEl.textContent = `${b.done} of ${b.total} complete`;
    renderLog(b.jobs.find((j) => j.status === "installing") || b.jobs[0]);
    if (!b.finished) setTimeout(tick, 900);
  }
  tick();
})();

// ---- provider wizard: test before save -------------------------------------
(function () {
  "use strict";
  const btn = document.getElementById("wz-test");
  if (!btn) return;
  const form = document.getElementById("wz-form");
  const out = document.getElementById("wz-result");

  btn.addEventListener("click", async () => {
    btn.disabled = true;
    const original = btn.textContent;
    btn.textContent = "Testing…";
    out.innerHTML = "";
    try {
      const r = await fetch("/actions/provider-try", { method: "POST", body: new FormData(form) });
      const d = await r.json();
      out.innerHTML = `<div class="${d.ok ? "callout-ok" : "banner danger"} wz-result">${
        d.ok ? "Connected — " : "Failed — "}${String(d.detail).replace(/[<>&]/g, "")}</div>`;
    } catch (e) {
      out.innerHTML = `<div class="banner danger wz-result">Test request failed: ${e}</div>`;
    } finally {
      btn.disabled = false;
      btn.textContent = original;
    }
  });
})();
