"""
The page you look at during the draft.

Kept in its own file purely so draft_assistant.py stays readable -- this
is just one big chunk of HTML with the styling and the click handling
built in. Nothing in here talks to ESPN; it only draws whatever the
assistant sends it.
"""

PAGE_HTML = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Draft Assistant</title>
<style>
  :root {
    --bg:#0e1117; --panel:#161b26; --line:#252c3b; --ink:#e8ecf3;
    --dim:#8b97ad; --good:#3ddc84; --warn:#ffb020; --bad:#ff5f56; --accent:#5b9dff;
  }
  * { box-sizing:border-box; }
  body {
    margin:0; background:var(--bg); color:var(--ink);
    font:15px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Helvetica,Arial,sans-serif;
  }
  header {
    padding:14px 20px; border-bottom:1px solid var(--line);
    display:flex; align-items:center; gap:18px; flex-wrap:wrap;
    background:var(--panel); position:sticky; top:0; z-index:10;
  }
  header h1 { font-size:16px; margin:0; font-weight:650; }
  .rules { color:var(--dim); font-size:13px; }
  .spacer { flex:1; }
  .sync { font-size:12px; color:var(--dim); }
  .sync.live { color:var(--good); }
  .sync.dead { color:var(--bad); font-weight:700; }
  select, button {
    font:inherit; background:#202836; color:var(--ink);
    border:1px solid var(--line); border-radius:7px; padding:6px 11px; cursor:pointer;
  }
  button:hover { border-color:var(--accent); }

  .wrap { display:grid; grid-template-columns: 1fr 330px; gap:18px; padding:18px 20px; }
  @media (max-width:900px){ .wrap { grid-template-columns:1fr; } }

  .card { background:var(--panel); border:1px solid var(--line); border-radius:12px; }

  /* --- the big recommendation --- */
  .pick { padding:18px 20px; margin-bottom:16px; border-left:4px solid var(--accent); }
  .pick .status { font-size:12px; letter-spacing:.09em; text-transform:uppercase; color:var(--dim); }
  .pick .status.now { color:var(--good); font-weight:700; }
  .pick .who { font-size:30px; font-weight:700; margin:6px 0 2px; letter-spacing:-.4px; }
  .pick .meta { color:var(--dim); font-size:14px; margin-bottom:10px; }
  .pick ul { margin:0; padding-left:18px; }
  .pick li { margin:3px 0; }
  .pick .cta { margin-top:14px; display:flex; gap:8px; }
  .cta button.mine { background:var(--good); color:#06240f; border-color:transparent; font-weight:650; }

  /* --- setup nudge --- */
  .setup { padding:16px 20px; margin-bottom:16px; border-left:4px solid var(--warn); }

  /* --- player table --- */
  .toolbar { display:flex; gap:8px; padding:12px 14px; border-bottom:1px solid var(--line); flex-wrap:wrap; }
  .toolbar input {
    flex:1; min-width:180px; background:#0f141d; border:1px solid var(--line);
    color:var(--ink); border-radius:7px; padding:7px 11px; font:inherit;
  }
  .chip { padding:5px 11px; font-size:13px; border-radius:20px; }
  .chip.on { background:var(--accent); color:#04162f; border-color:transparent; font-weight:650; }

  table { width:100%; border-collapse:collapse; }
  th {
    text-align:left; font-size:11px; text-transform:uppercase; letter-spacing:.07em;
    color:var(--dim); font-weight:600; padding:9px 10px; border-bottom:1px solid var(--line);
  }
  td { padding:8px 10px; border-bottom:1px solid #1c2331; vertical-align:middle; }
  tr:hover td { background:#1a2130; }
  .nm { font-weight:600; }
  .why { font-size:12px; color:var(--dim); }
  .num { text-align:right; font-variant-numeric:tabular-nums; }
  .pos { font-weight:700; font-size:12px; padding:2px 7px; border-radius:5px; }
  .QB{background:#4a2b5e;color:#e3b8ff} .RB{background:#123f2c;color:#6ee7a8}
  .WR{background:#123a52;color:#7dc9ff} .TE{background:#5a3a12;color:#ffc46b}
  .K{background:#333a48;color:#b8c2d4} .DST{background:#333a48;color:#b8c2d4}
  .hurt { color:var(--warn); font-size:11px; }
  .acts { display:flex; gap:5px; justify-content:flex-end; }
  .acts button { padding:4px 9px; font-size:12px; }
  .acts .mine { border-color:var(--good); color:var(--good); }

  /* --- roster --- */
  .roster h2, .card h2 { font-size:13px; text-transform:uppercase; letter-spacing:.07em;
    color:var(--dim); margin:0; padding:13px 15px; border-bottom:1px solid var(--line); }
  .slot { display:flex; justify-content:space-between; gap:10px; padding:7px 15px;
    border-bottom:1px solid #1c2331; font-size:14px; }
  .slot .lbl { color:var(--dim); font-size:12px; width:46px; flex:none; }
  .slot.empty .val { color:#5a6478; font-style:italic; }
  .foot { padding:11px 15px; color:var(--dim); font-size:12px; }
</style>
</head>
<body>

<header>
  <h1 id="lg">Loading…</h1>
  <span class="rules" id="rules"></span>
  <span class="spacer"></span>
  <label class="rules">Your seat
    <select id="slot"><option value="">— pick —</option></select>
  </label>
  <button id="undo">Undo</button>
  <span class="sync" id="sync"></span>
</header>

<div class="wrap">
  <div>
    <div id="setup" class="card setup" style="display:none">
      <b>Set your draft seat above.</b>
      <div class="rules" style="margin-top:5px">
        Which pick you have in round one. The tool needs it to work out how
        long until your next turn — that is what decides whether you can wait
        on someone or have to take him now.
      </div>
    </div>

    <div id="pick" class="card pick"></div>

    <div class="card">
      <div class="toolbar">
        <input id="q" placeholder="Search a player…" autocomplete="off">
        <button class="chip on" data-pos="ALL">All</button>
        <button class="chip" data-pos="QB">QB</button>
        <button class="chip" data-pos="RB">RB</button>
        <button class="chip" data-pos="WR">WR</button>
        <button class="chip" data-pos="TE">TE</button>
        <button class="chip" data-pos="K">K</button>
        <button class="chip" data-pos="D/ST">DST</button>
      </div>
      <table>
        <thead><tr>
          <th>Player</th><th>Pos</th><th>Tm</th>
          <th class="num">VOR</th><th>Tier</th><th class="num">Own</th><th></th>
        </tr></thead>
        <tbody id="rows"></tbody>
      </table>
    </div>
  </div>

  <div>
    <div class="card roster" style="margin-bottom:16px">
      <h2>Your team</h2>
      <div id="roster"></div>
      <div class="foot" id="rosterFoot"></div>
    </div>
    <div class="card">
      <h2>Reminder</h2>
      <div class="foot">
        This tool only reads ESPN. It cannot draft for you — make every pick
        yourself in the ESPN app, then it shows up here.
      </div>
    </div>
  </div>
</div>

<script>
let posFilter = "ALL", search = "", latest = null;

// If the assistant stops answering -- the terminal window got closed, the
// laptop went to sleep -- say so loudly. Silently showing a board that
// stopped updating twenty picks ago is the worst thing this page could do.
function offline() {
  const sync = document.getElementById("sync");
  sync.textContent = "LOST CONNECTION -- restart the tool in your terminal";
  sync.className = "sync dead";
}

const api = (path, body) => fetch(path, body ? {
  method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify(body)
} : {}).then(r => r.json()).then(render).catch(offline);

const esc = s => String(s).replace(/[&<>"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
const posClass = p => p === "D/ST" ? "DST" : p;

function render(state) {
  latest = state;
  document.getElementById("lg").textContent = state.league.name;
  document.getElementById("rules").textContent = state.league.rules;

  const sync = document.getElementById("sync");
  sync.textContent = state.sync.status;
  sync.className = "sync" + (state.sync.live ? " live" : "");

  const slotSel = document.getElementById("slot");
  if (slotSel.options.length <= 1) {
    for (let i = 1; i <= state.league.teams; i++) {
      slotSel.add(new Option(i, i));
    }
  }
  if (state.draft_slot) slotSel.value = state.draft_slot;
  document.getElementById("setup").style.display = state.draft_slot ? "none" : "block";
  document.getElementById("undo").disabled = !state.can_undo;

  renderPick(state);
  renderRows(state);
  renderRoster(state);
}

function renderPick(state) {
  const box = document.getElementById("pick");
  const top = state.recommendations[0];
  const t = state.turn;

  if (!top || t.draft_over) {
    box.innerHTML = "<div class='status'>Draft complete</div>" +
      "<div class='who'>You're done.</div>";
    return;
  }

  const onClock = t.on_the_clock && state.draft_slot;
  const status = !state.draft_slot
    ? "Best available"
    : onClock
      ? `Your pick — round ${t.round}`
      : `Round ${t.round} · ${t.picks_until_turn} pick${t.picks_until_turn === 1 ? "" : "s"} until your turn`;

  box.innerHTML = `
    <div class="status ${onClock ? "now" : ""}">${esc(status)}</div>
    <div class="who">${esc(top.name)}</div>
    <div class="meta">
      <span class="pos ${posClass(top.position)}">${esc(top.position_rank)}</span>
      &nbsp;${esc(top.pro_team)} · ${top.projection.toFixed(0)} proj · ${top.vor.toFixed(0)} VOR · ${esc(top.tier)}
    </div>
    <ul>${top.reasons.map(r => `<li>${esc(r)}</li>`).join("") || "<li>Best value on the board.</li>"}</ul>
    <div class="cta">
      <button class="mine" onclick="pick(${top.player_id}, true)">I drafted him</button>
      <button onclick="pick(${top.player_id}, false)">Someone else took him</button>
    </div>`;
}

// The page refreshes itself every couple of seconds. Rebuilding the table
// every time would mean that if a refresh landed in the split second between
// you pressing a button and the click registering, the button would vanish
// underneath you and the click would be lost. So the table is only rebuilt
// when something about it actually changed.
let lastRowsKey = "";

function renderRows(state, force) {
  const key = [state.picks_made, state.draft_slot, posFilter, search].join("|");
  if (!force && key === lastRowsKey) return;
  lastRowsKey = key;

  const q = search.toLowerCase();
  const rows = state.recommendations.filter(p =>
    (posFilter === "ALL" || p.position === posFilter) &&
    (!q || p.name.toLowerCase().includes(q))
  );

  document.getElementById("rows").innerHTML = rows.map(p => `
    <tr>
      <td>
        <div class="nm">${esc(p.name)}
          ${p.injury_status !== "ACTIVE" && p.injury_status !== "NORMAL"
            ? `<span class="hurt">${esc(p.injury_status)}</span>` : ""}
        </div>
        ${p.reasons.length ? `<div class="why">${esc(p.reasons[0])}</div>` : ""}
      </td>
      <td><span class="pos ${posClass(p.position)}">${esc(p.position_rank)}</span></td>
      <td class="why">${esc(p.pro_team)}</td>
      <td class="num">${p.vor.toFixed(0)}</td>
      <td class="why">${esc(p.tier)}${p.left_in_tier <= 2 ? ` · ${p.left_in_tier} left` : ""}</td>
      <td class="num why">${p.percent_owned.toFixed(0)}%</td>
      <td><div class="acts">
        <button class="mine" onclick="pick(${p.player_id}, true)">Mine</button>
        <button onclick="pick(${p.player_id}, false)">Taken</button>
      </div></td>
    </tr>`).join("") || `<tr><td colspan="7" class="foot">No players match.</td></tr>`;
}

function renderRoster(state) {
  const plan = state.roster_plan;
  const order = [["QB", plan.starters.QB], ["RB", plan.starters.RB], ["WR", plan.starters.WR],
                 ["TE", plan.starters.TE], ["FLEX", plan.flex],
                 ["K", plan.starters.K], ["D/ST", plan.starters["D/ST"]]];

  const pool = state.my_roster.slice();
  const take = pos => {
    const i = pool.findIndex(p => p.position === pos);
    return i === -1 ? null : pool.splice(i, 1)[0];
  };

  let html = "";
  for (const [label, count] of order) {
    for (let i = 0; i < count; i++) {
      const p = label === "FLEX"
        ? (take("RB") || take("WR") || take("TE"))
        : take(label);
      html += `<div class="slot ${p ? "" : "empty"}">
        <span class="lbl">${esc(label)}</span>
        <span class="val">${p ? esc(p.name) : "—"}</span>
      </div>`;
    }
  }
  for (const p of pool) {
    html += `<div class="slot"><span class="lbl">BE</span><span class="val">${esc(p.name)}</span></div>`;
  }
  document.getElementById("roster").innerHTML = html;

  const byes = {};
  state.my_roster.forEach(p => { if (p.bye_week) byes[p.bye_week] = (byes[p.bye_week] || 0) + 1; });
  const heavy = Object.entries(byes).filter(([, n]) => n >= 3).map(([w, n]) => `wk ${w}: ${n}`);
  document.getElementById("rosterFoot").textContent =
    `${state.my_roster.length} of ${plan.total_rounds} picks made` +
    (heavy.length ? ` · bye stack — ${heavy.join(", ")}` : "");
}

function pick(id, mine) { api("/api/pick", {player_id:id, mine}); }

document.getElementById("undo").onclick = () => api("/api/undo", {});
document.getElementById("slot").onchange = e => api("/api/slot", {slot:e.target.value});
document.getElementById("q").oninput = e => { search = e.target.value; if (latest) renderRows(latest, true); };
document.querySelectorAll(".chip").forEach(chip => chip.onclick = () => {
  document.querySelectorAll(".chip").forEach(c => c.classList.remove("on"));
  chip.classList.add("on");
  posFilter = chip.dataset.pos;
  if (latest) renderRows(latest, true);
});

api("/api/state");
setInterval(() => api("/api/state"), 2500);
</script>
</body>
</html>
"""
