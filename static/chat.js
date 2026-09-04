// Chat page behavior: language switching, sending questions to /chat, and
// rendering replies. Karam owns this file.

const form = document.getElementById("chat-form");
const input = document.getElementById("question");
const messages = document.getElementById("messages");
const sendBtn = document.getElementById("send-btn");
const langToggle = document.getElementById("lang-toggle");
const appTitle = document.getElementById("app-title");
const appSubtitle = document.getElementById("app-subtitle");

// One session per page load. The server logs and escalates per session_id.
const sessionId = crypto.randomUUID();

// Any character in the Arabic Unicode block -> lay that text out right-to-left.
const ARABIC_RE = /[؀-ۿ]/;

// --- Website language (chrome only; chat bubbles keep their own per-message direction) ---
const I18N = {
  en: {
    title: "Scholarship Assistant",
    subtitle: "Scholarships & financial aid",
    placeholder: "Ask about AU scholarships…",
    send: "Send",
    toggle: "العربية",                    // label shows the language you switch TO
    networkError: "Could not reach the server. Is it running?",
    escalated: "This conversation has been flagged for a human advisor. Someone will follow up.",
    sources: "Sources",
  },
  ar: {
    title: "مساعد المنح الدراسية",
    subtitle: "المنح والمساعدات المالية",
    placeholder: "اسأل عن منح جامعة عجمان…",
    send: "إرسال",
    toggle: "English",
    networkError: "تعذّر الوصول إلى الخادم. تأكد من أنه قيد التشغيل.",
    escalated: "تمت إحالة هذه المحادثة إلى مستشار بشري. سيتم التواصل معك قريباً.",
    sources: "المصادر",
  },
};

let currentLang = "en";

function applyLanguage(lang) {
  currentLang = lang;
  const t = I18N[lang];
  document.documentElement.lang = lang;
  document.documentElement.dir = lang === "ar" ? "rtl" : "ltr";
  appTitle.textContent = t.title;
  appSubtitle.textContent = t.subtitle;
  input.placeholder = t.placeholder;
  sendBtn.textContent = t.send;
  langToggle.textContent = t.toggle;
}

langToggle.addEventListener("click", () => {
  applyLanguage(currentLang === "en" ? "ar" : "en");
  input.focus();
});

// --- Rendering ---
function addBubble(text, who) {
  const div = document.createElement("div");
  div.className = `bubble ${who}`;
  div.textContent = text;                 // textContent (not innerHTML) => no HTML injection
  div.dir = ARABIC_RE.test(text) ? "rtl" : "ltr";
  messages.appendChild(div);
  messages.scrollTop = messages.scrollHeight;   // keep the newest message in view
  return div;
}

// Render the RAG's sources as small chips under an answer. Display-only for now:
// a source is clickable only when it is (or contains) a URL. Deep linking to the
// exact PDF line depends on the source format Ayham's RAG returns — a later extra.
function addSources(sources) {
  if (!Array.isArray(sources) || sources.length === 0) return;

  const row = document.createElement("div");
  row.className = "sources";

  const label = document.createElement("span");
  label.className = "sources-label";
  label.textContent = I18N[currentLang].sources + ":";
  row.appendChild(label);

  for (const s of sources) {
    let text;
    let url = null;
    if (typeof s === "string") {
      text = s;
      if (/^https?:\/\//i.test(s)) url = s;
    } else if (s && typeof s === "object") {
      text = s.title || s.name || s.url || JSON.stringify(s);
      url = s.url || null;
    } else {
      text = String(s);
    }

    let chip;
    if (url) {
      chip = document.createElement("a");
      chip.href = url;
      chip.target = "_blank";
      chip.rel = "noopener noreferrer";
    } else {
      chip = document.createElement("span");
    }
    chip.className = "source-chip";
    chip.textContent = text;
    row.appendChild(chip);
  }

  messages.appendChild(row);
  messages.scrollTop = messages.scrollHeight;
}

// Fixed bilingual welcome bubble (Arabic first, then English), shown once on load.
function addWelcome() {
  const div = document.createElement("div");
  div.className = "bubble bot";
  const ar = document.createElement("div");
  ar.dir = "rtl";
  ar.textContent = "أهلاً بك! اسألني عن منح جامعة عجمان الدراسية.";
  const en = document.createElement("div");
  en.dir = "ltr";
  en.className = "welcome-en";
  en.textContent = "Welcome! Ask me anything about Ajman University scholarships.";
  div.appendChild(ar);
  div.appendChild(en);
  messages.appendChild(div);
  messages.scrollTop = messages.scrollHeight;
}

// --- Startup ---
applyLanguage("en");
addWelcome();

form.addEventListener("submit", async (event) => {
  event.preventDefault();                 // stop the browser's default page reload on submit
  const question = input.value.trim();
  if (!question) return;

  addBubble(question, "user");
  input.value = "";
  input.disabled = true;
  sendBtn.disabled = true;

  try {
    const resp = await fetch("/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question: question, session_id: sessionId }),
    });
    const data = await resp.json();

    if (!resp.ok) {
      // Server returned 4xx/5xx — show its detail message, never fail silently.
      addBubble(`Error: ${data.detail || resp.status}`, "error");
    } else {
      addBubble(data.answer, "bot");
      addSources(data.sources);
      if (data.escalated) {
        addBubble(I18N[currentLang].escalated, "system");
      }
    }
  } catch (err) {
    // Network failure (server down, no connection) — fetch itself threw.
    addBubble(I18N[currentLang].networkError, "error");
  } finally {
    input.disabled = false;
    sendBtn.disabled = false;
    input.focus();
  }
});
