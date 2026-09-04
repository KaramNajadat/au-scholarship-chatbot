// Admin log browser. Reads the read-only /admin/api endpoints and renders them.
// All values go in via textContent (never innerHTML) so logged text can't inject HTML.

const sessionsList = document.getElementById("sessions-list");
const turnsList = document.getElementById("turns-list");
const turnsTitle = document.getElementById("turns-title");
const refreshBtn = document.getElementById("refresh-btn");

const ARABIC_RE = /[؀-ۿ]/;

function el(tag, className, text) {
  const e = document.createElement(tag);
  if (className) e.className = className;
  if (text !== undefined) e.textContent = text;
  return e;
}

function fmtTime(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  return isNaN(d.getTime()) ? iso : d.toLocaleString();
}

function shortId(id) {
  return String(id).slice(0, 8) + "…";
}

async function loadSessions() {
  sessionsList.textContent = "";
  sessionsList.appendChild(el("div", "empty", "Loading…"));
  try {
    const resp = await fetch("/admin/api/sessions");
    if (!resp.ok) throw new Error("HTTP " + resp.status);
    const sessions = await resp.json();

    sessionsList.textContent = "";
    if (sessions.length === 0) {
      sessionsList.appendChild(el("div", "empty", "No sessions logged yet."));
      return;
    }

    for (const s of sessions) {
      const row = el("button", "session-row");
      row.appendChild(el("span", "sess-id", shortId(s.id)));
      row.appendChild(el("span", "sess-meta", `${s.turn_count} turns · ${fmtTime(s.started_at)}`));
      if (s.escalated) row.appendChild(el("span", "badge escalated", "escalated"));
      row.addEventListener("click", () => {
        document.querySelectorAll(".session-row.active").forEach((r) => r.classList.remove("active"));
        row.classList.add("active");
        loadTurns(s);
      });
      sessionsList.appendChild(row);
    }
  } catch (err) {
    sessionsList.textContent = "";
    sessionsList.appendChild(el("div", "error", "Failed to load sessions: " + err.message));
  }
}

async function loadTurns(session) {
  turnsTitle.textContent = "Session " + shortId(session.id) + (session.escalated ? "  (escalated)" : "");
  turnsList.textContent = "";
  turnsList.appendChild(el("div", "empty", "Loading…"));
  try {
    const resp = await fetch("/admin/api/sessions/" + encodeURIComponent(session.id));
    if (!resp.ok) throw new Error("HTTP " + resp.status);
    const data = await resp.json();

    turnsList.textContent = "";
    if (!data.turns || data.turns.length === 0) {
      turnsList.appendChild(el("div", "empty", "No turns in this session."));
      return;
    }

    for (const t of data.turns) {
      const card = el("div", "turn-card");

      const q = el("div", "turn-q", "Q:  " + t.question);
      q.dir = ARABIC_RE.test(t.question) ? "rtl" : "ltr";
      card.appendChild(q);

      const a = el("div", "turn-a", "A:  " + t.answer);
      a.dir = ARABIC_RE.test(t.answer) ? "rtl" : "ltr";
      card.appendChild(a);

      if (Array.isArray(t.sources) && t.sources.length) {
        const text = t.sources
          .map((x) => (typeof x === "string" ? x : x.title || x.url || JSON.stringify(x)))
          .join(",  ");
        card.appendChild(el("div", "turn-sources", "sources:  " + text));
      }

      card.appendChild(
        el("div", "turn-meta", `${t.language} · score ${t.retrieval_score} · ${fmtTime(t.created_at)}`)
      );
      turnsList.appendChild(card);
    }
  } catch (err) {
    turnsList.textContent = "";
    turnsList.appendChild(el("div", "error", "Failed to load turns: " + err.message));
  }
}

refreshBtn.addEventListener("click", loadSessions);
loadSessions();
