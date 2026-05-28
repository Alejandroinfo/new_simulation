let data = null;
let _ws = null;
let _lastDataHash = null;
let _wsRetries = 0;

// ── Bidirectional WS commands ────────────────────────────────
function sendCmd(obj) {
  if (_ws && _ws.readyState === 1) {
    _ws.send(JSON.stringify(obj));
  } else {
    setStatus("not connected — start cli.py", "var(--accent)");
  }
}

function cmdGo(district) {
  sendCmd({action: "go", district: district});
}

function cmdTalkCat(cat, charId) {
  sendCmd({action: "talk_cat", cat: cat, char_id: charId});
}

function cmdLeave() {
  sendCmd({action: "leave"});
}

function renderCommandPanel(d) {
  const el = document.getElementById("cmd-panel");
  if (!el) return;

  const active = d.active_char_id;
  const CATS = ["location","time","victim","strangers","motive","alibi"];

  if (active) {
    // In conversation — show category buttons
    const char = (d.characters || []).find(c => c.id === active);
    const cname = char ? char.name : "?";
    el.innerHTML = `
      <div style="font-size:10px;color:var(--dim);margin-bottom:6px">
        Speaking with <strong style="color:var(--cyan)">${escH(cname)}</strong>
      </div>
      <div style="display:flex;flex-wrap:wrap;gap:5px;margin-bottom:6px">
        ${CATS.map(cat => `
          <button class="cmd-btn cmd-cat" onclick="cmdTalkCat('${cat}','${escH(active)}')">
            ${cat}
          </button>`).join("")}
      </div>
      <button class="cmd-btn cmd-leave" onclick="cmdLeave()">✕ Leave</button>
    `;
  } else {
    // Not in conversation — show movement + action buttons
    const locs = [...new Set((d.characters || [])
      .filter(c => c.alive)
      .map(c => c.district))].sort();
    const current = d.player_location || "";
    el.innerHTML = `
      <div style="font-size:10px;color:var(--dim);margin-bottom:6px">
        You are in <strong style="color:var(--cyan)">${escH(current)}</strong>
      </div>
      <div style="font-size:10px;color:var(--dim);margin-bottom:4px">Move to:</div>
      <div style="display:flex;flex-wrap:wrap;gap:4px;margin-bottom:8px">
        ${locs.filter(l => l !== current).map(l => `
          <button class="cmd-btn cmd-go" onclick="cmdGo('${escH(l)}')">
            → ${escH(l)}
          </button>`).join("")}
      </div>
      <div style="display:flex;gap:5px">
        <button class="cmd-btn" onclick="sendCmd({action:'clues'})">clues</button>
        <button class="cmd-btn" onclick="sendCmd({action:'status'})">status</button>
      </div>
    `;
  }
}

// ── Resizable panels ─────────────────────────────────────────
const _savedSizes = {};   // id → height in px, persists across re-renders

function applyStoredSize(el) {
  if (!el || !el.id) return;
  if (_savedSizes[el.id]) {
    el.style.maxHeight = _savedSizes[el.id] + "px";
    el.style.height    = _savedSizes[el.id] + "px";
  }
}

function makeResizable(el) {
  if (!el || el.dataset.resizable) return;
  el.dataset.resizable = "1";
  applyStoredSize(el);   // restore size from before re-render

  const handle = document.createElement("div");
  handle.className = "resize-handle";
  el.parentNode.insertBefore(handle, el.nextSibling);

  let startY = 0, startH = 0, dragging = false;

  handle.addEventListener("mousedown", e => {
    e.preventDefault();
    dragging = true;
    startY = e.clientY;
    startH = el.offsetHeight;
    handle.classList.add("dragging");
    document.body.style.cursor = "ns-resize";
    document.body.style.userSelect = "none";
  });

  document.addEventListener("mousemove", e => {
    if (!dragging) return;
    const delta = e.clientY - startY;
    const newH = Math.max(60, Math.min(700, startH + delta));
    el.style.maxHeight = newH + "px";
    el.style.height    = newH + "px";
    if (el.id) _savedSizes[el.id] = newH;   // persist
  });

  document.addEventListener("mouseup", () => {
    if (!dragging) return;
    dragging = false;
    handle.classList.remove("dragging");
    document.body.style.cursor = "";
    document.body.style.userSelect = "";
  });
}

// Apply to resizable panels after each render
function applyResizable() {
  ["conv-panel", "inv-board", "inv-board", "deduction-grid",
   "suspects-panel", "events-panel"].forEach(id => {
    const el = document.getElementById(id);
    if (el) makeResizable(el);
  });
}

function setStatus(msg, color) {
  const el = document.getElementById("ws-status");
  if (el) { el.textContent = msg; el.style.color = color || "var(--dim)"; }
}

function connectWS() {
  try {
    _ws = new WebSocket("ws://localhost:8765");
  } catch(e) {
    setStatus("WS error — retrying", "var(--warn)");
    setTimeout(connectWS, 3000);
    return;
  }
  setStatus("connecting...", "var(--dim)");
  _ws.onopen = () => {
    setStatus("connected — waiting for game", "var(--warn)");
    _wsRetries = 0;
  };
  _ws.onmessage = (evt) => {
    try {
      const parsed = JSON.parse(evt.data);
      if (parsed && parsed.scenario_type) {
        const _h = evt.data.length + evt.data.slice(0,64);
        if (_h === _lastDataHash) return;
        _lastDataHash = _h;
        data = parsed;
        render();
        setStatus("live ✓", "var(--good)");
      if (data && data.active_char_id) { const a=document.getElementById("inv_"+data.active_char_id); if(a){a.classList.add("inv-active"); const n=document.getElementById("invnote_"+data.active_char_id); if(n)n.style.display="block";}}
      }
    } catch(e) {
      console.error("[ws] parse error:", e);
    }
  };
  _ws.onclose = () => {
    _ws = null;
    setStatus("reconnecting...", "var(--dim)");
    const delay = Math.min(1000 * Math.pow(1.5, _wsRetries++), 8000);
    setTimeout(connectWS, delay);
  };
  _ws.onerror = () => { _ws && _ws.close(); };
}

function load() {
  // WebSocket handles updates — this is just a keepalive check
  if (!_ws || _ws.readyState > 1) {
    setStatus("waiting — run cli.py in terminal", "var(--dim)");
  }
}

function escH(s) {
  return String(s).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;");
}

function render() {
  console.log("[render] called, data=", data ? "present" : "null");
  if (!data) {
    document.getElementById("main").innerHTML =
      '<div style="padding:40px 20px;color:var(--dim);font-size:13px;line-height:2">' +
      '<div style="font-size:18px;margin-bottom:12px">⏳ Waiting for game</div>' +
      '<div>1. Run <code style="color:var(--accent)">uv run cli.py</code> in a terminal</div>' +
      '<div>2. This dashboard will update automatically</div>' +
      '</div>';
    return;
  }
  console.log("[render] scenario_type=", data.scenario_type,
              "town=", data.town_name, "victims=", data.victims);
  const t = data.scenario_type || "unknown";
  document.body.className = t;

  try {
    renderTopbar(data);
    console.log("[render] topbar OK");
    renderCommandPanel(data);
    setTimeout(applyResizable, 50);
  } catch(e) { console.error("[render] topbar FAILED:", e); }

  try {
    if      (t === "murderer")  renderMurderer(data);
    else if (t === "trial")     renderTrial(data);
    else if (t === "labyrinth") renderLabyrinth(data);
    else {
      document.getElementById("main").innerHTML =
        '<div style="padding:40px;color:var(--dim)">Unknown scenario type: ' + t + '</div>';
      document.getElementById("sidebar").innerHTML = "";
    }
    console.log("[render] scenario render OK");
  } catch(e) { console.error("[render] scenario render FAILED:", e); }
}

function renderTopbar(d) {
  const titles = { murderer:"⚔ THE MURDERER", trial:"⚖ THE TRIAL", labyrinth:"🌀 THE LABYRINTH" };
  const _st=document.getElementById("scenario-title"); if(_st) _st.textContent = titles[d.scenario_type] || "DASHBOARD";
  const _ts=document.getElementById("top-sub"); if(_ts) _ts.textContent = d.town_name || "";

  const pct = d.pressure_pct || 0;
  const pcolor = pct > 70 ? "var(--accent)" : pct > 40 ? "var(--warn)" : "var(--good)";
  document.getElementById("pressure-fill").style.width = pct + "%";
  document.getElementById("pressure-fill").style.background = pcolor;
  document.getElementById("pressure-pct").textContent = pct + "%";

  const labels = {
    murderer:  d.time_str ? `${d.time_str} · Victims ${d.victims}/${d.max_victims}` : `Day ${d.day} · Victims ${d.victims}/${d.max_victims}`,
    trial:     `${d.hours_remaining}h remaining`,
    labyrinth: `Stamina ${d.stamina}/${d.stamina_max}`,
  };
  const _pl=document.getElementById("pressure-label"); if(_pl) _pl.textContent =
    labels[d.scenario_type] || "";
}

/* ════════════════════════════════════════
   MURDERER
════════════════════════════════════════ */
// Notes stored in memory (per session) keyed by suspect name
const _suspectNotes = {};

function renderMurderer(d) {
  const main = document.getElementById("main");
  const side = document.getElementById("sidebar");

  const hoursLeft = d.hours_to_strike ?? (d.next_strike * 24);
  const nextStrike = hoursLeft <= 4
    ? '<span style="color:var(--accent);font-weight:700">IMMINENT</span>'
    : hoursLeft <= 12
    ? `<span style="color:var(--accent)">~${Math.round(hoursLeft)}h</span>`
    : `<span style="color:var(--warn)">~${Math.round(hoursLeft)}h</span>`;

  const ctBadge = {
    serial:      '<span style="color:var(--accent);font-weight:700">[SERIAL]</span>',
    passion:     '<span style="color:var(--warn);font-weight:700">[PASSION]</span>',
    conspiracy:  '<span style="color:var(--cyan);font-weight:700">[CONSPIRACY]</span>',
    frame:       '<span style="color:var(--warn);font-weight:700">[FRAME]</span>',
  }[d.case_type] || "";

  main.innerHTML = `
    <div class="card">
      <div class="card-title">💬 Conversation Log</div>
      <div class="card-body" id="conv-panel" style="max-height:280px;overflow-y:auto"></div>
    </div>

    <div class="card">
      <div class="card-title">🔢 Deduction Grid <span style="font-size:9px;color:var(--dim);font-weight:400">— click cells to mark</span></div>
      <div class="card-body" id="deduction-grid" style="overflow-x:auto"></div>
    </div>
  `;

  // events-panel is in sidebar, built by side.innerHTML above - update it after
  const evEl = document.getElementById("events-panel");
  if (evEl) evEl.innerHTML =
    (d.events || []).slice().reverse().map(ev => {
      const cls = ev.includes("body") || ev.includes("killed") ? "danger" : "info";
      return `<div class="event-row ${cls}">${escH(ev)}</div>`;
    }).join("") || '<div class="empty">No events yet.</div>';

  renderConvLog("conv-panel", d.conversation_log);

  // Sidebar
  const foundClues = (d.clues || []).filter(c => c.found);
  const hiddenCount = (d.clues || []).length - foundClues.length;
  const suspects = d.suspects || [];

  const closedDistricts = Object.keys(d.district_closed || {});
  const agendaItems = (d.killer_agenda_visible || []);

  let sidePrefix = "";
  if (agendaItems.length > 0) {
    sidePrefix += `<div class="card" style="border-color:var(--warn)">
      <div class="card-title" style="color:var(--warn)">⚠ Signals — Something may happen soon</div>
      <div class="card-body">
        ${agendaItems.map(a => `<div style="font-size:11px;color:var(--warn);padding:3px 0">${escH(a)}</div>`).join("")}
      </div>
    </div>`;
  }
  if (closedDistricts.length > 0) {
    sidePrefix += `<div class="card" style="border-color:var(--dim)">
      <div class="card-title" style="color:var(--dim)">🔇 People aren't talking</div>
      <div class="card-body">
        ${closedDistricts.map(dist => `<div style="font-size:11px;color:var(--dim);padding:2px 0">${escH(dist)} district — guarded</div>`).join("")}
      </div>
    </div>`;
  }
  if ((d.world_reactions || []).length > 0) {
    sidePrefix += `<div class="card" style="border-color:var(--accent2)">
      <div class="card-title" style="color:var(--accent2)">👁 World reactions</div>
      <div class="card-body">
        ${d.world_reactions.slice(-3).map(r => `<div style="font-size:11px;color:var(--text);padding:3px 0">${escH(r)}</div>`).join("")}
      </div>
    </div>`;
  }

  side.innerHTML = sidePrefix + `
    <div class="card">
      <div class="card-title">📊 Status ${ctBadge}</div>
      <div class="card-body" style="font-size:11px">
        <div class="stat-row"><span class="stat-label">Time</span><span class="stat-val">${escH(d.time_str || ("Day " + d.day))}</span></div>
        <div class="stat-row"><span class="stat-label">Victims</span><span class="stat-val" style="color:var(--accent)">${d.victims} / ${d.max_victims}</span></div>
        <div class="stat-row"><span class="stat-label">Next strike</span><span class="stat-val">${nextStrike}</span></div>
        <div class="stat-row"><span class="stat-label">Clues</span><span class="stat-val">${d.clues_found} / ${d.total_clues}</span></div>
        <div class="stat-row"><span class="stat-label">Location</span><span class="stat-val" style="color:var(--cyan)">${escH(d.player_location)}</span></div>
        <div class="stat-row"><span class="stat-label">Money</span><span class="stat-val" style="color:var(--accent2)">${d.money ?? "—"}g</span></div>
        <div class="stat-row"><span class="stat-label">Difficulty</span><span class="stat-val">${d.difficulty ?? "—"}/20</span></div>
        <div class="stat-row">
          <span class="stat-label">Murder weapon</span>
          <span class="stat-val" style="color:${d.weapon_found ? 'var(--good)' : 'var(--accent)'}">
            ${d.weapon_found || "not found"}
          </span>
        </div>
      </div>
    </div>

    <div class="card">
      <div class="card-title">📰 Events</div>
      <div class="card-body" id="events-panel" style="max-height:160px;overflow-y:auto"></div>
    </div>

    <div class="card">
      <div class="card-title collapsible" onclick="toggleCard('clues-body')">
        🔍 Clues (${foundClues.length}/${d.total_clues})
        <span id="clues-chevron" style="float:right;font-size:10px">${_cardOpen['clues-body']===false ? '▸' : '▾'}</span>
      </div>
      <div class="card-body" id="clues-body" style="max-height:200px;overflow-y:auto;display:${_cardOpen['clues-body']===false?'none':'block'}">
        ${foundClues.map(c => {
          const lieTag = c.is_lie ? '<span style="color:var(--accent);font-size:9px"> ⚠ REVISED</span>' : '';
          const clr = c.is_lie ? "var(--accent)" : (c.narrows_suspects ? "var(--good)" : "var(--dim)");
          return '<div class="clue-row found" style="border-left-color:' + clr + '">' +
            '<div class="clue-attr">' + escH(c.attribute) + lieTag + '</div>' +
            escH(c.text) + '</div>';
        }).join("")}
        ${hiddenCount > 0 ? `<div class="clue-row hidden">${hiddenCount} still undiscovered.</div>` : ""}
        ${foundClues.length === 0 ? '<div class="empty">No clues yet.</div>' : ""}
      </div>
    </div>

    <div class="card">
      <div class="card-title">🗂 Investigation Board</div>
      <div class="card-body" id="inv-board" style="max-height:300px;overflow-y:auto"></div>
    </div>
  `;

  renderDeductionGrid(d);
  renderInvBoard(d);
}
function renderSuspects(suspects, victims, acSuspects) {
  const el = document.getElementById("suspects-panel");
  if (!el) return;

  let html = "";
  if (suspects.length === 0) {
    html += '<div class="empty">No suspects narrowed yet.</div>';
  } else if (suspects.length === 1) {
    html += '<div style="color:var(--good);font-size:11px;padding:4px 0">One suspect — ready to confront.</div>';
  }

  el.innerHTML = html + suspects.map(s => {
    const key   = s.name;
    const saved = _suspectNotes[key] || "";
    const isVictim = victims.includes(s.name);
    return `
      <div class="suspect-block" id="sb_${escH(key.replace(/\s/g,'_'))}">
        <div class="suspect-header">
          <div>
            <div class="suspect-name">${escH(s.name)}</div>
            <div class="suspect-meta">${escH(s.occupation)} · ${escH(s.district)}</div>
          </div>
          <button class="note-toggle" onclick="toggleNote('${escH(key)}')">📝</button>
        </div>
        <div class="note-area" id="note_${escH(key.replace(/\s/g,'_'))}" style="display:${saved ? 'block' : 'none'}">
          <textarea
            class="note-input"
            placeholder="Your suspicions, inconsistencies, notes..."
            onchange="_suspectNotes['${escH(key)}'] = this.value"
            oninput="_suspectNotes['${escH(key)}'] = this.value"
          >${escH(saved)}</textarea>
        </div>
      </div>`;
  }).join("");

  // Accomplice suspects (conspiracy only)
  if (acSuspects && acSuspects.length > 0) {
    el.innerHTML += `<div style="margin-top:10px;font-size:10px;color:var(--warn);font-weight:700">
      ACCOMPLICE SUSPECTS (${acSuspects.length})</div>`;
    el.innerHTML += acSuspects.map(s => `
      <div class="suspect-block" style="border-left-color:var(--warn)">
        <div class="suspect-header">
          <div>
            <div class="suspect-name">${escH(s.name)}</div>
            <div class="suspect-meta">${escH(s.occupation)} · ${escH(s.district)}</div>
          </div>
        </div>
      </div>`).join("");
  }
}


const _charMarks = {};
const _cardOpen  = {};   // id -> true/false, undefined = open by default

function toggleCard(id) {
  _cardOpen[id] = _cardOpen[id] === false ? true : false;
  const body = document.getElementById(id);
  const chev = document.getElementById(id.replace('-body','-chevron'));
  if (body) body.style.display = _cardOpen[id] === false ? 'none' : 'block';
  if (chev) chev.textContent  = _cardOpen[id] === false ? '▸' : '▾';
}

// Deduction grid state: {charId}_{attr} -> "" | "?" | "✓" | "✗"
const _gridCells = {};
const GRID_ATTRS = ["district","occupation","trait"];
const GRID_STATES = ["", "?", "✓", "✗"];
const GRID_COLORS = {
  "":  "transparent",
  "?": "rgba(255,200,0,.15)",
  "✓": "rgba(100,200,100,.2)",
  "✗": "rgba(200,80,80,.15)",
};
const GRID_LABELS = {"district":"district","occupation":"occupation","trait":"trait"};

function cycleCell(key) {
  const states = GRID_STATES;
  const cur = _gridCells[key] || "";
  const idx = states.indexOf(cur);
  _gridCells[key] = states[(idx + 1) % states.length];
  const el = document.getElementById("gc_" + key);
  if (el) {
    el.textContent = _gridCells[key];
    el.style.background = GRID_COLORS[_gridCells[key]];
  }
}

function renderDeductionGrid(d) {
  const el = document.getElementById('deduction-grid');
  if (!el) return;
  const chars = (d.characters || []).filter(c => c.alive);
  if (!chars.length) { el.innerHTML = ''; return; }

  // Clue-highlighted values: attribute -> [values that are relevant]
  const clueHighlight = {};
  (d.clues || []).filter(c => c.found && c.narrows_suspects).forEach(clue => {
    if (!clueHighlight[clue.attribute]) clueHighlight[clue.attribute] = [];
    if (clue.value) clueHighlight[clue.attribute].push(clue.value);
  });

  // All district values always shown (visible from start)
  // Occupation/trait only shown for chars the player has met
  const districtVals = [...new Set(chars.map(c => c.district))].sort();
  const occVals      = [...new Set(chars.filter(c=>c.known).map(c=>c.occupation).filter(Boolean))].sort();
  const traitVals    = [...new Set(chars.filter(c=>c.known).map(c=>c.trait).filter(Boolean))].sort();

  const sections = [
    {label:'District',   vals:districtVals, attr:'district',   alwaysKnown:true},
    {label:'Occupation', vals:occVals,       attr:'occupation', alwaysKnown:false},
    {label:'Trait',      vals:traitVals,     attr:'trait',      alwaysKnown:false},
  ];

  function colBg(attr, val) {
    return (clueHighlight[attr] || []).includes(val) ? 'rgba(255,210,0,.14)' : '';
  }

  // Header
  let html = '<table class="ded-table"><thead><tr><th class="ded-name">Person</th>';
  for (const sec of sections) {
    if (!sec.vals.length) continue;
    const hasClue = !!clueHighlight[sec.attr];
    html += '<th class="ded-section' + (hasClue?' ded-section-clue':'') + '" colspan="' + sec.vals.length + '">' + sec.label + (hasClue?' ★':'') + '</th>';
  }
  html += '</tr><tr><th></th>';
  for (const sec of sections) {
    for (const v of sec.vals) {
      const bg = colBg(sec.attr, v);
      html += '<th class="ded-val"' + (bg?(' style="background:'+bg+';color:var(--warn)"'):'') + '>' + escH(v) + '</th>';
    }
  }
  html += '</tr></thead><tbody>';

  // Rows
  for (const c of chars) {
    html += '<tr class="' + (!c.known?'ded-row-unknown':'') + '">';
    html += '<td class="ded-name-cell">' + escH(c.portrait) + ' ' + escH(c.name.split(' ')[0]) + '</td>';
    for (const sec of sections) {
      if (!sec.vals.length) continue;
      for (const v of sec.vals) {
        if (!c.known && !sec.alwaysKnown) {
          html += '<td class="ded-cell ded-unknown" title="Talk to them first">—</td>';
          continue;
        }
        const key   = c.id + '_' + sec.attr + '_' + v;
        const state = _gridCells[key] || '';
        const isTrue = c[sec.attr] === v;
        const colHi  = colBg(sec.attr, v);

        // Auto-eliminate: if another cell in same char+attr row is ✓, this is implicitly ✗
        const hasConfirmed = sec.vals.some(ov => ov!==v && (_gridCells[c.id+'_'+sec.attr+'_'+ov]==='✓'));
        const autoElim = hasConfirmed && !state;

        const bg = state ? GRID_COLORS[state] : (colHi || 'transparent');
        html += '<td id="gc_' + escH(key) + '" class="ded-cell'
          + (isTrue?' ded-actual':'') + (autoElim?' ded-auto-elim':'')
          + '" style="background:' + bg + '"'
          + ' onclick="cycleCell(' + "'" + escH(key) + "'" + ')"'
          + ' title="' + escH(c.name) + ': ' + sec.attr + '=' + escH(v) + '">'
          + (state || (autoElim?'·':'')) + '</td>';
      }
    }
    html += '</tr>';
  }
  html += '</tbody></table>';
  el.innerHTML = html;
}

function renderInvBoard(d) {
  const el = document.getElementById("inv-board");
  if (!el) return;
  const chars = (d.characters || []).filter(c => c.alive);
  if (!chars.length) { el.innerHTML = '<div class="empty">No data yet.</div>'; return; }
  el.innerHTML = chars.map(c => {
    const saved  = _suspectNotes[c.id] || "";
    const mark   = _charMarks[c.id] || "";
    const active = d.active_char_id === c.id;
    const mc = mark==="suspect"?"inv-suspect":mark==="innocent"?"inv-innocent":"";
    const occStr = c.known ? escH(c.occupation) + " &middot; " + escH(c.district) : escH(c.district);
    const noteDisp = (saved||active) ? "block" : "none";
    return `<div class="inv-row ${mc} ${active?"inv-active":""}" id="inv_${escH(c.id)}">
      <div class="inv-header" onclick="toggleInvNote('${escH(c.id)}')">
        <span>${escH(c.portrait)}</span>
        <span class="inv-name">${escH(c.name)}</span>
        <span class="inv-meta">${occStr}</span>
        <span style="margin-left:auto;font-size:10px;color:var(--dim)">&#128221;</span>
      </div>
      <div class="inv-note" id="invnote_${escH(c.id)}" style="display:${noteDisp}">
        <textarea class="note-input" placeholder="suspicions, confirmed, ruled out..."
          onchange="_suspectNotes['${escH(c.id)}'] = this.value"
          oninput="_suspectNotes['${escH(c.id)}'] = this.value"
        >${escH(saved)}</textarea>
        <div style="display:flex;gap:4px;margin-top:3px">
          <button class="mark-btn" onclick="markChar('${escH(c.id)}','')">&#8212;</button>
          <button class="mark-btn" style="color:var(--warn)" onclick="markChar('${escH(c.id)}','suspect')">&#127919; suspect</button>
          <button class="mark-btn" style="color:var(--good)" onclick="markChar('${escH(c.id)}','innocent')">&#10003; clear</button>
        </div>
      </div>
    </div>`;
  }).join("");
}

function markChar(id, mark) {
  _charMarks[id] = mark;
  const el = document.getElementById("inv_" + id);
  if (!el) return;
  el.classList.remove("inv-suspect","inv-innocent");
  if (mark==="suspect")  el.classList.add("inv-suspect");
  if (mark==="innocent") el.classList.add("inv-innocent");
}

function toggleInvNote(id) {
  const el = document.getElementById("invnote_" + id);
  if (el) el.style.display = el.style.display==="none" ? "block" : "none";
}

function toggleNote(name) {
  const key  = name.replace(/\s/g, "_");
  const area = document.getElementById("note_" + key);
  if (!area) return;
  area.style.display = area.style.display === "none" ? "block" : "none";
  if (area.style.display === "block") {
    const ta = area.querySelector("textarea");
    if (ta) ta.focus();
  }
}

/* ════════════════════════════════════════
   TRIAL
════════════════════════════════════════ */
function renderTrial(d) {
  const main = document.getElementById("main");
  const side = document.getElementById("sidebar");

  const hRemain = d.hours_remaining;
  const urgency = hRemain <= 6
    ? "color:var(--accent)"
    : hRemain <= 12 ? "color:var(--warn)" : "color:var(--good)";

  main.innerHTML = `
    <div class="card">
      <div class="card-title">⏰ Time</div>
      <div class="card-body">
        <div id="countdown-display" style="${urgency}">${hRemain}h</div>
        <div id="countdown-label">${hRemain <= 0 ? "EXECUTION TIME" : "remaining until dawn"}</div>
        <div style="height:8px;background:var(--bg4);border-radius:4px;overflow:hidden;margin-top:8px">
          <div style="height:100%;border-radius:4px;background:${urgency.split(':')[1]};width:${d.pressure_pct}%;transition:width .5s"></div>
        </div>
      </div>
    </div>

    <div class="card">
      <div class="card-title">👤 The Accused</div>
      <div class="card-body">
        <div class="stat-row"><span class="stat-label">Name</span><span class="stat-val">${escH(d.accused_name)}</span></div>
        <div class="stat-row"><span class="stat-label">Occupation</span><span class="stat-val">${escH(d.accused_occupation)}</span></div>
        <div class="stat-row"><span class="stat-label">Charge</span><span class="stat-val" style="color:var(--warn)">${escH(d.crime)}</span></div>
        <div class="stat-row"><span class="stat-label">Status</span><span class="stat-val">${d.presented ? "Case presented" : "Awaiting verdict"}</span></div>
      </div>
    </div>

    <div class="card">
      <div class="card-title">🗂 Evidence (${d.evidence_examined}/${d.total_evidence} examined)</div>
      <div class="card-body" id="evidence-panel"></div>
    </div>

    <div class="card">
      <div class="card-title">📰 Events</div>
      <div class="card-body" id="events-panel"></div>
    </div>

    <div class="card">
      <div class="card-title">💬 Conversation Log</div>
      <div class="card-body" id="conv-panel" style="max-height:220px;overflow-y:auto"></div>
    </div>

    <div class="card">
      <div class="card-title">🔢 Deduction Grid <span style="font-size:9px;color:var(--dim);font-weight:400">— click cells to mark</span></div>
      <div class="card-body" id="deduction-grid" style="overflow-x:auto"></div>
    </div>
  `;

  const evPan = document.getElementById("evidence-panel"); if (evPan) evPan.innerHTML =
    (d.evidence || []).map(ev => {
      let cls = "unexamined", tag = "";
      if (ev.examined && ev.is_genuine === true) {
        cls = "examined-genuine";
        tag = '<span class="ev-tag genuine">genuine</span>';
      } else if (ev.examined && ev.is_genuine === false) {
        cls = "examined-false";
        tag = '<span class="ev-tag false">questionable</span>';
      } else if (!ev.examined) {
        tag = '<span class="ev-tag unknown">not examined</span>';
      }
      return `<div class="ev-row ${cls}">
        <div><span class="ev-name">${escH(ev.name)}</span>${tag}</div>
        ${ev.examined ? `<div style="color:var(--dim);font-size:10px;margin-top:2px">${escH(ev.description)}</div>` : ""}
      </div>`;
    }).join("");

  const evPan3 = document.getElementById("events-panel"); if (evPan3) evPan3.innerHTML =
    (d.events || []).slice().reverse().map(ev =>
      `<div class="event-row info">${escH(ev)}</div>`
    ).join("") || '<div class="empty">No events yet.</div>';

  renderConvLog("conv-panel", d.conversation_log);

  // Sidebar: witnesses
  side.innerHTML = `
    <div class="card">
      <div class="card-title">🧑‍⚖️ People to Interview</div>
      <div id="char-grid" style="flex-direction:column;gap:6px;padding:10px 12px;display:flex"></div>
    </div>
    <div class="card">
      <div class="card-title">💡 Tips</div>
      <div class="card-body" style="font-size:11px;color:var(--dim)">
        <div style="margin:4px 0">→ <span style="color:var(--text)">examine</span> evidence to see if it's genuine</div>
        <div style="margin:4px 0">→ <span style="color:var(--text)">talk</span> to witnesses for testimony</div>
        <div style="margin:4px 0">→ <span style="color:var(--text)">present guilty/innocent</span> to conclude</div>
        <div style="margin:4px 0">→ Build bond to unlock hidden information</div>
      </div>
    </div>
  `;

  const charGrid = document.getElementById("char-grid");
  charGrid.innerHTML = (d.characters || []).map(c => `
    <div style="background:var(--bg3);border:1px solid var(--border);border-radius:4px;padding:7px 10px;display:flex;align-items:center;gap:10px">
      <div style="font-size:16px">${escH(c.portrait)}</div>
      <div>
        <div style="font-size:11px;font-weight:700;color:var(--bright)">${escH(c.name)}</div>
        <div style="font-size:10px;color:var(--dim)">${escH(c.occupation)}</div>
      </div>

    </div>
  `).join("");
}

/* ════════════════════════════════════════
   LABYRINTH
════════════════════════════════════════ */
function renderLabyrinth(d) {
  const main = document.getElementById("main");
  const side = document.getElementById("sidebar");

  const staminaColor = d.stamina_pct > 50 ? "var(--good)" : d.stamina_pct > 25 ? "var(--warn)" : "var(--accent)";

  main.innerHTML = `
    <div class="card">
      <div class="card-title">📍 Current Location</div>
      <div class="card-body">
        <div style="font-size:20px;font-weight:700;color:var(--bright);margin-bottom:8px">${escH(d.current_room)}</div>
        <div style="font-size:11px;color:var(--dim);margin-bottom:10px">Exits:</div>
        <div>${(d.exits||[]).map(e => `<span class="exit-chip">${escH(e)}</span>`).join(" ")}</div>
      </div>
    </div>

    <div class="card">
      <div class="card-title">⚡ Stamina</div>
      <div class="card-body">
        <div style="display:flex;justify-content:space-between;margin-bottom:6px">
          <span style="font-size:12px;color:var(--dim)">Energy remaining</span>
          <span style="font-size:14px;font-weight:700;color:${staminaColor}">${d.stamina} / ${d.stamina_max}</span>
        </div>
        <div class="stamina-bar">
          <div class="stamina-fill" style="width:${d.stamina_pct}%;background:${staminaColor}"></div>
        </div>
        ${d.stamina <= 5 ? '<div style="color:var(--accent);font-size:11px;margin-top:6px">⚠ Low stamina — use rest</div>' : ""}
      </div>
    </div>

    <div class="card">
      <div class="card-title">🗺 Explored Map (${d.rooms_visited} / ${d.total_rooms} rooms)</div>
      <svg id="maze-canvas" class="card-body"></svg>
    </div>

    <div class="card">
      <div class="card-title">📰 Events</div>
      <div class="card-body" id="events-panel"></div>
    </div>

    <div class="card">
      <div class="card-title">💬 Conversation Log</div>
      <div class="card-body" id="conv-panel" style="max-height:220px;overflow-y:auto"></div>
    </div>

    <div class="card">
      <div class="card-title">🔢 Deduction Grid <span style="font-size:9px;color:var(--dim);font-weight:400">— click cells to mark</span></div>
      <div class="card-body" id="deduction-grid" style="overflow-x:auto"></div>
    </div>
  `;

  const evPan3 = document.getElementById("events-panel"); if (evPan3) evPan3.innerHTML =
    (d.events || []).slice().reverse().map(ev =>
      `<div class="event-row info">${escH(ev)}</div>`
    ).join("") || '<div class="empty">No events yet.</div>';

  renderConvLog("conv-panel", d.conversation_log);
  renderMazeMap(d);

  side.innerHTML = `
    <div class="card">
      <div class="card-title">🎒 Items</div>
      <div class="card-body">
        ${(d.items||[]).length === 0
          ? '<div class="empty">No items yet.</div>'
          : (d.items||[]).map(i => `<span class="item-chip">${escH(i)}</span>`).join(" ")}
      </div>
    </div>

    <div class="card">
      <div class="card-title">📝 Notes</div>
      <div class="card-body">
        ${(d.notes||[]).length === 0
          ? '<div class="empty">Talk to others to gather directions.</div>'
          : (d.notes||[]).map(n => `<div class="note-row">${escH(n)}</div>`).join("")}
      </div>
    </div>

    <div class="card">
      <div class="card-title">👥 Others Trapped</div>
      <div class="card-body">
        ${(d.characters||[]).map(c => `
          <div style="display:flex;align-items:center;gap:8px;padding:5px 0;border-bottom:1px solid var(--bg3)">
            <span style="font-size:14px">${escH(c.portrait)}</span>
            <div>
              <div style="font-size:11px;font-weight:700;color:var(--bright)">${escH(c.name)}</div>
              <div style="font-size:10px;color:var(--dim)">${escH(c.occupation)}</div>
            </div>

          </div>
        `).join("")}
      </div>
    </div>
  `;
}

function renderMazeMap(d) {
  const svg = document.getElementById("maze-canvas");
  if (!svg || !d.rooms) return;
  const visited = d.rooms.filter(r => r.visited);
  if (visited.length === 0) return;

  const W = svg.clientWidth || 500;
  const H = 280;
  svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
  svg.setAttribute("style", `width:100%;height:${H}px`);

  // Position rooms in a grid-ish layout
  const cols = Math.ceil(Math.sqrt(visited.length));
  const padX = 60, padY = 40;
  const cellW = (W - padX*2) / Math.max(cols-1, 1);
  const cellH = (H - padY*2) / Math.max(Math.ceil(visited.length/cols)-1, 1);

  const pos = {};
  visited.forEach((r, i) => {
    const col = i % cols;
    const row = Math.floor(i / cols);
    pos[r.id] = { x: padX + col*cellW, y: padY + row*cellH };
  });

  let lines = "";
  const drawn = new Set();
  visited.forEach(r => {
    Object.values(r.connections).forEach(tid => {
      if (!pos[tid]) return;
      const key = [r.id, tid].sort().join("_");
      if (drawn.has(key)) return;
      drawn.add(key);
      const p = pos[r.id], q = pos[tid];
      lines += `<line x1="${p.x}" y1="${p.y}" x2="${q.x}" y2="${q.y}" stroke="var(--border)" stroke-width="1.5"/>`;
    });
  });

  let nodes = "";
  visited.forEach(r => {
    const p = pos[r.id];
    const isCurrent = r.is_current;
    const isExit = r.is_exit;
    const fill = isExit ? "var(--good)" : isCurrent ? "var(--accent)" : "var(--bg4)";
    const stroke = isExit ? "var(--good)" : isCurrent ? "var(--accent)" : "var(--border)";
    const radius = isCurrent ? 10 : 7;
    const label = r.name.split(" ").slice(0,2).join(" ");
    const labelClass = isCurrent ? "current" : isExit ? "exit" : "";
    nodes += `<circle cx="${p.x}" cy="${p.y}" r="${radius}" fill="${fill}" stroke="${stroke}" stroke-width="1.5"/>`;
    nodes += `<text x="${p.x}" y="${p.y + radius + 10}" text-anchor="middle" class="room-label ${labelClass}">${escH(label)}</text>`;
    if (isExit) nodes += `<text x="${p.x}" y="${p.y - radius - 4}" text-anchor="middle" style="font-size:9px;fill:var(--good)">EXIT</text>`;
  });

  svg.innerHTML = lines + nodes;
}

let _convFilter = { person: "", category: "" };

function renderConvLog(elementId, log) {
  const el = document.getElementById(elementId);
  if (!el) return;
  const all = (log || []).slice().reverse();
  if (!all.length) {
    el.innerHTML = '<div class="empty">No conversations yet.</div>';
    return;
  }

  // Build unique people and categories for filter dropdowns
  const people = [...new Set(all.map(e => e.who))].sort();
  const categories = [...new Set(
    all.map(e => {
      const m = e.q.match(/\[([^\]]+)\]/);
      return m ? m[1] : null;
    }).filter(Boolean)
  )].sort();

  // Filter controls
  const filterHtml = `<div class="conv-filter">
    <input id="conv-search" class="conv-search-input" type="text"
      placeholder="Search text..."
      value="${escH(_convFilter.person)}"
      oninput="_convFilter.person = this.value; _refreshConvLog('${elementId}', window._convLog || [])">
    <select class="conv-filter-sel" onchange="_convFilter.category = this.value; _refreshConvLog('${elementId}', window._convLog || [])">
      <option value="">All types</option>
      ${categories.map(c => `<option value="${escH(c)}" ${_convFilter.category===c?'selected':''}>${escH(c)}</option>`).join("")}
    </select>
    <select class="conv-filter-sel" onchange="_convFilter.person = this.value; _refreshConvLog('${elementId}', window._convLog || [])">
      <option value="">All people</option>
      ${people.map(p => `<option value="${escH(p)}" ${_convFilter.person===p?'selected':''}>${escH(p)}</option>`).join("")}
    </select>
  </div>`;

  window._convLog = all;  // store for filter refresh
  el.innerHTML = filterHtml + '<div id="conv-entries"></div>';
  _refreshConvLog(elementId, all);
}

function _refreshConvLog(elementId, entries) {
  const entriesEl = document.getElementById("conv-entries");
  if (!entriesEl) return;

  const search  = (_convFilter.person || "").toLowerCase();
  const catF    = _convFilter.category || "";
  const personF = _convFilter.person || "";

  // If person filter is exact match to a name, filter by name; else search text
  const filtered = entries.filter(e => {
    const catMatch = e.q.match(/\[([^\]]+)\]/);
    const cat = catMatch ? catMatch[1] : "";
    if (catF && cat !== catF) return false;
    if (personF && personF !== e.who && !e.who.toLowerCase().includes(search)
        && !e.q.toLowerCase().includes(search) && !e.a.toLowerCase().includes(search)) return false;
    return true;
  });

  if (!filtered.length) {
    entriesEl.innerHTML = '<div class="empty">No matches.</div>';
    return;
  }

  entriesEl.innerHTML = filtered.map(e => {
    const clueTag = e.clue ? '<div class="conv-clue-tag">★ revealed a clue</div>' : '';
    const catM = e.q.match(/\[([^\]]+)\]/);
    const cat  = catM ? catM[1] : "";
    const qText = e.q.replace(/\[[^\]]+\]/, "").trim();
    return `<div class="conv-entry ${e.clue ? "has-clue" : ""}">
      <div class="conv-who">${escH(e.who)} ${cat ? `<span class="conv-cat-tag">[${escH(cat)}]</span>` : ""}</div>
      ${qText ? `<div class="conv-q">${escH(qText)}</div>` : ""}
      <div class="conv-a">${escH(e.a)}</div>
      ${clueTag}
    </div>`;
  }).join("");
}

connectWS();
setInterval(load, 5000);
