(() => {
  const API = (window.API_BASE || "").replace(/\/$/, "");
  const chat = document.getElementById("chat");
  const form = document.getElementById("composer");
  const input = document.getElementById("question");
  const send = document.getElementById("send");
  const hint = document.querySelector(".hint");
  const hintText = hint.textContent;
  let lastScheme = null;

  // Same PII rules as the server: block before anything leaves the browser.
  const PII = [
    [/\b[A-Za-z]{5}[0-9]{4}[A-Za-z]\b/, "PAN"],
    [/(?<!\d)\d{4}[\s-]?\d{4}[\s-]?\d{4}(?!\d)/, "Aadhaar"],
    [/(?:\+?91[\s-]?)?(?<!\d)[6-9]\d{9}(?!\d)/, "phone number"],
    [/[\w.+-]+@[\w-]+\.[\w.-]+/, "email"],
    [/\b(?:otp|cvv|m?pin|upi pin|password|passcode)\b\D{0,20}\d{3,8}/i, "OTP/PIN"],
    [/\b(?:account|a\/c|acct|acc|folio|bank|demat)\b\D{0,25}\d{6,18}/i, "account/folio number"],
    [/(?<!\d)\d{11,18}(?!\d)/, "ID number"],
  ];
  const findPII = (t) => (PII.find(([re]) => re.test(t)) || [])[1];

  const LABEL = { answer: "Answer", refusal: "Facts-only", pii_blocked: "Privacy", clarify: "Need one detail",
                  not_found: "Not in my sources", greeting: "Hello", error: "Error" };

  function el(tag, cls, text) {
    const n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text !== undefined) n.textContent = text;
    return n;
  }

  function addUser(text) {
    chat.appendChild(el("div", "msg user", text));
    scroll();
  }

  function addBot(r) {
    const box = el("div", `msg bot ${r.type || ""}`);
    box.appendChild(el("div", "badge", LABEL[r.type] || "Answer"));
    box.appendChild(el("div", "", r.answer));
    if (r.source_url) {
      const a = el("a", "source");
      a.href = r.source_url;
      a.target = "_blank";
      a.rel = "noopener";
      const isEdu = r.type === "refusal" || r.type === "pii_blocked";
      a.textContent = `${isEdu ? "Learn more" : "Source"} ↗ ${r.source_url.replace(/^https?:\/\//, "")}`;
      box.appendChild(a);
    }
    if (r.last_updated) box.appendChild(el("div", "updated", `Last updated from sources: ${r.last_updated}`));
    chat.appendChild(box);
    scroll();
  }

  function scroll() { window.scrollTo({ top: document.body.scrollHeight, behavior: "smooth" }); }

  async function ask(question) {
    question = question.trim();
    if (!question) return;
    const pii = findPII(question);
    if (pii) {
      hint.textContent = `⚠️ That looks like a ${pii}. Please remove personal details — nothing was sent.`;
      hint.classList.add("warn");
      return;
    }
    hint.textContent = hintText;
    hint.classList.remove("warn");

    addUser(question);
    input.value = "";
    send.disabled = true;
    const typing = el("div", "msg bot typing", "Looking it up in the sources…");
    chat.appendChild(typing);
    scroll();
    const slow = setTimeout(() => {
      typing.textContent = "Waking up the server (free hosting) — the first answer can take up to a minute…";
    }, 5000);

    try {
      const res = await fetch(`${API}/api/ask`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question, scheme_hint: lastScheme }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || `HTTP ${res.status}`);
      if (data.scheme && data.scheme !== "hdfc-amc") lastScheme = data.scheme;
      typing.remove();
      addBot(data);
    } catch (err) {
      typing.remove();
      addBot({ type: "error", answer: `Sorry, I couldn't reach the server (${err.message}). Please try again in a few seconds.` });
    } finally {
      clearTimeout(slow);
      send.disabled = false;
      input.focus();
    }
  }

  form.addEventListener("submit", (e) => { e.preventDefault(); ask(input.value); });
  document.querySelectorAll(".example").forEach((b) => b.addEventListener("click", () => ask(b.textContent)));

  // Load the corpus date (also wakes the server early).
  fetch(`${API}/api/meta`).then((r) => r.json()).then((m) => {
    document.getElementById("last-updated").textContent = m.last_updated || "—";
  }).catch(() => {});
})();
