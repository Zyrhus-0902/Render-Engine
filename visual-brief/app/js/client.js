/*
 * Visual brief: client-facing flow.
 * intro -> (round intro -> pairs) x dimensions -> optional brief -> thank you.
 * The client never sees the analysis; that lives in architect.html.
 */
(function () {
  "use strict";
  const { el, store, imageUrl, download, slug } = window.VBData;
  const S = window.VBScoring;

  let P, D, pid, imgs, pairsById, dimsById, session, steps, lang, shownAt = 0;
  const app = () => document.getElementById("app");

  const t = k => S.text((D.copy[lang] || D.copy.en)[k] ?? D.copy.en[k], lang);
  const tx = v => S.text(v, lang);

  function newSession(name) {
    const id = Date.now().toString(36) + Math.random().toString(36).slice(2, 7);
    return {
      type: "visual-brief-session", schema_version: 1, id, project_id: pid,
      respondent: { name: name || "" }, seed: id, lang,
      started_at: new Date().toISOString(), updated_at: null, completed_at: null,
      position: 0, responses: [], brief: {},
    };
  }
  function save() { session.updated_at = new Date().toISOString(); store.saveSession(pid, session); store.setCurrent(pid, session.id); }
  function go(i) { session.position = Math.max(0, Math.min(steps.length - 1, i)); save(); render(); window.scrollTo(0, 0); }
  function responseFor(pairId) { return session.responses.find(r => r.pair_id === pairId); }

  function setResponse(pairId, patch) {
    let r = responseFor(pairId);
    if (!r) { r = { pair_id: pairId, chips: [] }; session.responses.push(r); }
    else if (patch.choice && r.choice && patch.choice !== r.choice) r.revisions = (r.revisions || 0) + 1;
    Object.assign(r, patch, { timestamp: new Date().toISOString() });
    save();
    return r;
  }

  // ---------- screens ----------
  function header() {
    const langs = D.languages || ["en"];
    return el("header", { class: "top" },
      el("div", { class: "brand" }, D.branding && D.branding.studio_name ? D.branding.studio_name : "", el("span", { class: "proj" }, tx(D.project.name))),
      langs.length > 1 ? el("select", { class: "lang", "aria-label": "Language", onchange: e => { lang = e.target.value; session && (session.lang = lang); store.setLang(pid, lang); render(); } },
        langs.map(l => el("option", { value: l, selected: l === lang }, l.toUpperCase()))) : null);
  }

  function intro() {
    const cur = store.current(pid), existing = cur && store.sessions(pid)[cur];
    const resumable = existing && !existing.completed_at && existing.responses.length;
    const name = el("input", { id: "name", type: "text", autocomplete: "given-name", placeholder: t("name_placeholder") });
    const begin = () => { session = newSession(name.value.trim()); steps = S.buildSequence(D, P.pairs, P.images, session.seed); go(0); };
    return el("main", { class: "wrap intro" },
      el("p", { class: "eyebrow" }, tx(D.project.subtitle)),
      el("h1", null, t("intro_title")),
      el("p", { class: "lead" }, t("intro_body")),
      el("p", { class: "muted" }, t("intro_time")),
      el("label", { for: "name", class: "field" }, t("name_label"), name),
      el("div", { class: "actions" },
        resumable ? el("button", { class: "btn primary", onclick: () => { session = existing; steps = S.buildSequence(D, P.pairs, P.images, session.seed); render(); } },
          t("resume") + (existing.respondent.name ? ` (${existing.respondent.name})` : "")) : null,
        el("button", { class: resumable ? "btn" : "btn primary", onclick: begin }, resumable ? t("start_over") : t("start"))),
      creditsLink());
  }

  function progress(step) {
    const num = step.round_number, count = step.round_count;
    const done = step.type === "pair" ? step.index_in_round + 1 : 0;
    // Category names ("Roof form") are architect vocabulary; hidden from clients unless the dataset asks.
    const showName = D.settings && D.settings.show_dimension_names;
    return el("div", { class: "progress" },
      el("div", { class: "rounds", "aria-hidden": "true" }, Array.from({ length: count }, (_, i) => el("span", { class: "dot" + (i + 1 < num ? " done" : i + 1 === num ? " now" : "") }))),
      el("div", { class: "progress-label" }, `${t("round")} ${num} ${t("of")} ${count}` + (showName ? ` · ${tx(dimsById[step.dimension_id].name)}` : ""),
        step.type === "pair" ? el("span", { class: "count" }, `${done} / ${step.round_size}`) : null),
      step.type === "pair" ? el("div", { class: "bar", role: "progressbar", "aria-valuemin": 0, "aria-valuemax": step.round_size, "aria-valuenow": done },
        el("span", { style: `width:${(done / step.round_size) * 100}%` })) : null);
  }

  function roundIntro(step) {
    const dim = dimsById[step.dimension_id];
    return el("main", { class: "wrap round-intro" }, progress(step),
      el("h1", null, D.settings && D.settings.show_dimension_names ? tx(dim.name) : `${t("round")} ${step.round_number}`),
      el("p", { class: "lead" }, tx(dim.client_prompt)),
      el("div", { class: "actions" },
        session.position > 0 ? el("button", { class: "btn ghost", onclick: () => go(session.position - 1) }, t("back")) : null,
        el("button", { class: "btn primary", onclick: () => go(session.position + 1), autofocus: true }, t("begin_round"))));
  }

  function pairScreen(step) {
    const pair = pairsById[step.pair_id], dim = dimsById[step.dimension_id];
    const sides = step.swapped ? ["b", "a"] : ["a", "b"];
    const resp = responseFor(pair.id);
    const choice = resp && resp.choice;
    shownAt = performance.now();
    const showChips = D.settings && D.settings.show_chips !== false && (D.chips || []).length;

    function choose(c) {
      const ms = Math.round(performance.now() - shownAt);
      const prev = responseFor(pair.id);
      setResponse(pair.id, { choice: c, swapped: step.swapped, ms: prev && prev.ms ? prev.ms : ms });
      const keepsChips = c === "a" || c === "b" || c === "both";
      if (!showChips || !keepsChips) { if (prev && prev.chips && !keepsChips) prev.chips = []; return go(session.position + 1); }
      render();
    }

    const card = side => {
      const img = imgs[pair["image_" + side]];
      const selected = choice === side, rejected = choice === "reject_" + side;
      return el("figure", { class: "choice" + (selected ? " selected" : "") + (rejected ? " rejected" : "") },
        el("button", { class: "pick", "aria-pressed": selected ? "true" : "false", "aria-label": `Choose ${side === sides[0] ? "first" : "second"} picture`, onclick: () => choose(side) },
          el("img", { src: imageUrl(P, img), alt: img.alt ? tx(img.alt) : "", loading: "eager", draggable: "false" })),
        el("button", { class: "never", "aria-pressed": rejected ? "true" : "false", onclick: () => choose("reject_" + side) }, "✕ " + t("never")));
    };

    const chipRow = showChips && (choice === "a" || choice === "b" || choice === "both")
      ? el("div", { class: "chips-wrap" },
          el("p", { class: "muted small" }, t("chips_prompt")),
          el("div", { class: "chips" }, D.chips.map(c => {
            const on = resp.chips && resp.chips.includes(c.id);
            return el("button", { class: "chip" + (on ? " on" : ""), "aria-pressed": on ? "true" : "false", onclick: () => {
              const cs = new Set(resp.chips || []); on ? cs.delete(c.id) : cs.add(c.id);
              setResponse(pair.id, { chips: [...cs] }); render();
            } }, tx(c.label));
          })))
      : null;

    return el("main", { class: "wrap pair" }, progress(step),
      el("p", { class: "prompt" }, tx(dim.client_prompt)),
      el("div", { class: "pair-grid" }, card(sides[0]), card(sides[1])),
      el("div", { class: "alt" },
        el("button", { class: "btn" + (choice === "both" ? " on" : ""), onclick: () => choose("both") }, t("both")),
        el("button", { class: "btn" + (choice === "neither" ? " on" : ""), onclick: () => choose("neither") }, t("neither"))),
      chipRow,
      el("div", { class: "nav" },
        el("button", { class: "btn ghost", onclick: () => go(session.position - 1) }, "← " + t("back")),
        choice ? el("button", { class: "btn primary", onclick: () => go(session.position + 1) }, t("next") + " →") : null));
  }

  function briefScreen() {
    const B = D.brief, val = session.brief;
    const set = (id, v) => { val[id] = v; save(); };
    const field = f => {
      const label = tx(f.label);
      if (f.type === "multi" || f.type === "single") {
        const cur = val[f.id] || (f.type === "multi" ? [] : "");
        return el("fieldset", { class: "field" }, el("legend", null, label),
          el("div", { class: "chips" }, f.options.map(o => {
            const ov = tx(o), on = f.type === "multi" ? cur.includes(ov) : cur === ov;
            return el("button", { type: "button", class: "chip" + (on ? " on" : ""), "aria-pressed": on ? "true" : "false", onclick: () => {
              if (f.type === "multi") { const s = new Set(cur); on ? s.delete(ov) : s.add(ov); set(f.id, [...s]); }
              else set(f.id, on ? "" : ov);
              render();
            } }, ov);
          })));
      }
      const attrs = { id: "f-" + f.id, placeholder: tx(f.placeholder) || null, oninput: e => set(f.id, e.target.value) };
      const input = f.type === "textarea" ? el("textarea", Object.assign({ rows: 3 }, attrs))
        : el("input", Object.assign({ type: f.type === "number" ? "number" : "text", inputmode: f.type === "number" ? "numeric" : null, min: f.min, max: f.max }, attrs));
      input.value = val[f.id] ?? "";
      return el("label", { class: "field", for: "f-" + f.id }, label, input);
    };
    return el("main", { class: "wrap brief" },
      el("h1", null, tx(B.title)), el("p", { class: "lead" }, tx(B.intro)),
      el("form", { onsubmit: e => e.preventDefault() }, B.fields.map(field)),
      el("div", { class: "nav" },
        el("button", { class: "btn ghost", onclick: () => go(session.position - 1) }, "← " + t("back")),
        el("button", { class: "btn primary", onclick: () => go(session.position + 1) }, t("brief_continue"))));
  }

  function done() {
    if (!session.completed_at) { session.completed_at = new Date().toISOString(); save(); }
    const file = `visual-brief_${pid}_${slug(session.respondent.name)}_${session.completed_at.slice(0, 10)}.json`;
    return el("main", { class: "wrap done" },
      el("h1", null, t("done_title")), el("p", { class: "lead" }, t("done_body")),
      el("p", { class: "muted" }, t("remote_hint")),
      el("div", { class: "actions" },
        el("button", { class: "btn primary", onclick: () => download(file, session) }, t("download")),
        el("button", { class: "btn", onclick: () => { session = null; store.setCurrent(pid, null); render(); } }, t("another"))),
      creditsLink());
  }

  // Licences (CC BY / BY-SA) require visible credit; kept off the pairs themselves.
  function creditsLink() {
    const credited = P.images.filter(i => !i.placeholder && i.credit);
    if (!credited.length) return null;
    return el("p", { class: "credits-link" }, el("button", { class: "link", onclick: () => showCredits(credited) }, `Photo credits (${credited.length})`));
  }
  function showCredits(list) {
    const close = () => dlg.remove();
    const dlg = el("div", { class: "credits", role: "dialog", "aria-modal": "true", "aria-label": "Photo credits", onclick: e => { if (e.target === dlg) close(); } },
      el("div", { class: "credits-panel" },
        el("div", { class: "credits-head" }, el("h2", null, "Photo credits"), el("button", { class: "btn ghost", onclick: close }, "Close")),
        el("ul", null, list.map(i => el("li", null,
          el("span", { class: "muted" }, (i.code || "") + " "), i.title || "Untitled", " · ", i.credit, " · ",
          i.license_url ? el("a", { href: i.license_url, target: "_blank", rel: "noopener" }, i.license || "licence") : (i.license || ""),
          i.source ? [" · ", el("a", { href: i.source, target: "_blank", rel: "noopener" }, "source")] : null)))));
    document.body.append(dlg);
  }

  function render() {
    const root = app(); root.innerHTML = "";
    root.append(header());
    if (!session) return root.append(intro());
    const step = steps[session.position];
    root.append(step.type === "round" ? roundIntro(step) : step.type === "pair" ? pairScreen(step) : step.type === "brief" ? briefScreen() : done());
    const af = root.querySelector("[autofocus]"); if (af) af.focus();
  }

  // Keyboard: 1/← first picture, 2/→ second, Enter next, Backspace back (not while typing).
  document.addEventListener("keydown", e => {
    if (!session || /INPUT|TEXTAREA|SELECT/.test(document.activeElement.tagName)) return;
    const step = steps[session.position];
    if (step.type !== "pair") return;
    const btns = app().querySelectorAll(".pick");
    if (e.key === "1" || e.key === "ArrowLeft") btns[0] && btns[0].click();
    else if (e.key === "2" || e.key === "ArrowRight") btns[1] && btns[1].click();
    else if (e.key === "Enter" && responseFor(step.pair_id)) go(session.position + 1);
    else return;
    e.preventDefault();
  });

  window.VBData.loadProject().then(function (project) {
    P = project; D = project.dataset; pid = D.project.id;
    imgs = Object.fromEntries(P.images.map(i => [i.id, i]));
    pairsById = Object.fromEntries(P.pairs.map(p => [p.id, p]));
    dimsById = Object.fromEntries(D.dimensions.map(d => [d.id, d]));
    lang = store.lang(pid) || (D.languages || ["en"])[0];
    document.title = S.text(D.project.name, lang);
    if (D.branding && D.branding.accent) document.documentElement.style.setProperty("--accent", D.branding.accent);
    // Warm the cache so pairs appear instantly on slow connections.
    P.images.forEach(i => { if (!S.isExcluded(i)) { const im = new Image(); im.src = imageUrl(P, i); } });
    render();
  }).catch(window.VBData.showError);
})();
