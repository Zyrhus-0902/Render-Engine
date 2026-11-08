/*
 * Visual brief: architect view. Loads sessions saved on this device or
 * imported JSON files, computes the preference profile, and exports it.
 */
(function () {
  "use strict";
  const { el, store, imageUrl, download, slug } = window.VBData;
  const S = window.VBScoring;
  let P, D, pid, imgs, dimsById, origins;
  let loaded = [];      // [{ session, source }]
  let active = 0;
  const app = () => document.getElementById("app");
  const pct = x => Math.round(x * 100) + "%";
  const tx = v => S.text(v);

  // ---------- tooltip ----------
  const tip = el("div", { class: "tip", role: "tooltip", hidden: true });
  document.addEventListener("pointerover", e => {
    const t = e.target.closest("[data-tip]");
    if (!t) { tip.hidden = true; return; }
    tip.textContent = t.getAttribute("data-tip"); tip.hidden = false;
  });
  document.addEventListener("pointermove", e => {
    if (tip.hidden) return;
    const x = Math.min(e.clientX + 14, window.innerWidth - tip.offsetWidth - 8);
    tip.style.left = x + "px"; tip.style.top = (e.clientY + 16) + "px";
  });

  // ---------- loading ----------
  function normaliseImport(obj) {
    if (obj && obj.type === "visual-brief-profile" && obj.session) return obj.session;
    if (obj && obj.type === "visual-brief-session") return obj;
    if (obj && Array.isArray(obj.responses)) return obj;
    throw new Error("Not a visual-brief session file");
  }
  function addSession(session, source) {
    const i = loaded.findIndex(l => l.session.id === session.id);
    if (i >= 0) loaded[i] = { session, source }; else loaded.push({ session, source });
  }
  async function importFiles(files) {
    const errors = [];
    for (const f of files) {
      try {
        const s = normaliseImport(JSON.parse(await f.text()));
        if (s.project_id && s.project_id !== pid) errors.push(`${f.name}: belongs to project "${s.project_id}", not "${pid}"`);
        else addSession(s, f.name);
      } catch (e) { errors.push(`${f.name}: ${e.message}`); }
    }
    render();
    if (errors.length) alert(errors.join("\n"));
  }

  // ---------- small charts ----------
  function originColour(o) { return `var(--origin-${o}, var(--muted))`; }
  function originLabel(o) { return (origins[o] && tx(origins[o].label)) || o; }

  function blendBar(blend, opts) {
    opts = opts || {};
    const segs = Object.entries(blend).filter(([, v]) => v > 0);
    if (!segs.length) return el("div", { class: "muted small" }, "No picks yet");
    return el("div", { class: "blend" + (opts.small ? " small" : "") },
      el("div", { class: "stack", role: "img", "aria-label": segs.map(([o, v]) => `${originLabel(o)} ${pct(v)}`).join(", ") },
        segs.map(([o, v]) => el("span", { class: "seg", style: `flex-grow:${v};background:${originColour(o)}`, "data-tip": `${originLabel(o)}: ${pct(v)}` }))),
      opts.small ? null : el("div", { class: "legend" }, segs.map(([o, v]) =>
        el("span", { class: "key" }, el("i", { style: `background:${originColour(o)}` }), `${originLabel(o)} `, el("b", null, pct(v))))));
  }

  // Option scores on a [-2, 1] axis with a zero baseline; bar colour = origin.
  function optionBars(d) {
    const MIN = -2, MAX = 1, span = MAX - MIN, zero = (-MIN / span) * 100;
    return el("div", { class: "opts" }, d.options.map(o => {
      const has = o.score !== null;
      const v = has ? o.score : 0, left = Math.min(zero, ((v - MIN) / span) * 100), width = Math.abs(((v - MIN) / span) * 100 - zero);
      const detail = has ? `${o.label}: score ${v.toFixed(2)} · ${o.wins} won, ${o.losses} lost, ${o.both} both, ${o.neither} neither, ${o.rejects} never · ${o.appearances} shown` : `${o.label}: not shown`;
      return el("div", { class: "opt" + (d.winner && d.winner.id === o.id ? " win" : ""), "data-tip": detail },
        el("span", { class: "opt-label" }, o.label, el("small", null, originLabel(o.origin))),
        el("span", { class: "track" },
          el("span", { class: "zero", style: `left:${zero}%` }),
          has ? el("span", { class: "fill" + (v < 0 ? " neg" : ""), style: `left:${left}%;width:${Math.max(width, 0.6)}%;background:${originColour(o.origin)}` }) : null),
        el("span", { class: "opt-val" }, has ? (v > 0 ? "+" : "") + v.toFixed(2) : "–", o.rejects ? el("em", { class: "rej" }, ` ✕${o.rejects}`) : null));
    }));
  }

  function meter(strength, label) {
    return el("span", { class: "meter", "data-tip": `Strength ${pct(strength)}` },
      el("span", { class: "meter-track" }, el("span", { style: `width:${pct(strength)}` })), el("span", null, label));
  }

  // ---------- sections ----------
  function sourcesPanel() {
    const local = Object.values(store.sessions(pid)).sort((a, b) => (b.updated_at || "").localeCompare(a.updated_at || ""));
    const fileInput = el("input", { type: "file", accept: "application/json,.json", multiple: true, onchange: e => importFiles(e.target.files) });
    return el("section", { class: "card sources no-print" },
      el("h2", null, "Responses"),
      el("p", { class: "muted small" }, "Load answers saved on this device, or import the JSON file a client sent you. Load two people to compare them."),
      local.length ? el("ul", { class: "list" }, local.map(s => {
        const isLoaded = loaded.some(l => l.session.id === s.id);
        return el("li", null,
          el("label", null, el("input", { type: "checkbox", checked: isLoaded, onchange: e => {
            if (e.target.checked) addSession(s, "this device"); else loaded = loaded.filter(l => l.session.id !== s.id);
            active = Math.min(active, Math.max(0, loaded.length - 1)); render();
          } }), " ", s.respondent.name || "Unnamed", " ",
          el("span", { class: "muted small" }, `${s.responses.length} answers · ${s.completed_at ? "complete" : "in progress"} · ${(s.updated_at || s.started_at || "").slice(0, 16).replace("T", " ")}`)),
          el("button", { class: "link danger", onclick: () => { if (confirm(`Delete ${s.respondent.name || "this"} session from this device?`)) { store.deleteSession(pid, s.id); loaded = loaded.filter(l => l.session.id !== s.id); render(); } } }, "delete"));
      })) : el("p", { class: "muted small" }, "No sessions saved on this device yet."),
      el("label", { class: "btn file" }, "Import JSON…", fileInput),
      el("button", { class: "btn ghost", onclick: () => loadDemo() }, "Load a simulated respondent"));
  }

  function headerCard(s, prof) {
    const mins = s.started_at && (s.completed_at || s.updated_at) ? Math.round((new Date(s.completed_at || s.updated_at) - new Date(s.started_at)) / 60000) : null;
    return el("section", { class: "card head" },
      el("p", { class: "eyebrow" }, `${tx(D.project.name)} · ${tx(D.project.location)}`),
      el("h1", null, s.respondent.name || "Unnamed respondent"),
      el("p", { class: "muted" }, `${prof.answered} of ${prof.total_pairs} pairs answered · ${s.completed_at ? "completed " + s.completed_at.slice(0, 10) : "in progress"}` + (mins != null ? ` · ${mins} min` : "") +
        (prof.timing.median_ms ? ` · median ${Math.round(prof.timing.median_ms / 100) / 10}s per pair` : "")));
  }

  function headline(prof) {
    const strong = prof.dimensions.filter(d => d.winner).sort((a, b) => b.strength - a.strength);
    return el("section", { class: "card" },
      el("h2", null, "At a glance"),
      el("table", { class: "glance" },
        el("thead", null, el("tr", null, el("th", null, "Dimension"), el("th", null, "Prefers"), el("th", null, "Strength"), el("th", null, "Runner-up"))),
        el("tbody", null, prof.dimensions.map(d => el("tr", null,
          el("td", null, d.name),
          el("td", null, d.winner ? [el("i", { class: "sw", style: `background:${originColour(d.winner.origin)}` }), d.winner.label] : el("span", { class: "muted" }, d.answered ? "No clear preference" : "Not answered")),
          el("td", null, meter(d.strength, d.strength_label)),
          el("td", { class: "muted" }, d.runner_up ? d.runner_up.label : ""))))),
      strong.length ? el("p", { class: "small muted" }, "Strongest: " + strong.slice(0, 3).map(d => `${d.name.toLowerCase()} (${d.winner.label.toLowerCase()})`).join("; ") + ".") : null);
  }

  function blendCard(prof) {
    const rej = Object.entries(prof.blend.rejections).filter(([, v]) => v > 0);
    return el("section", { class: "card" },
      el("h2", null, "Style blend"),
      el("p", { class: "muted small" }, "Share of picks by image origin (both-equally counts half to each). Images were sourced pure, so this is the client's blend, not ours."),
      blendBar(prof.blend.overall),
      el("table", { class: "blend-table" },
        el("thead", null, el("tr", null, el("th", null, "Dimension"), el("th", null, "Blend"), ...Object.keys(origins).map(o => el("th", { class: "num" }, originLabel(o))))),
        el("tbody", null, prof.dimensions.map(d => el("tr", null, el("td", null, d.name), el("td", { class: "bar-cell" }, blendBar(prof.blend.by_dimension[d.id], { small: true })),
          ...Object.keys(origins).map(o => el("td", { class: "num" }, prof.blend.by_dimension[d.id][o] ? pct(prof.blend.by_dimension[d.id][o]) : "–")))),
          el("tr", { class: "total" }, el("td", null, "Overall"), el("td"), ...Object.keys(origins).map(o => el("td", { class: "num" }, pct(prof.blend.overall[o] || 0)))))),
      rej.length ? el("p", { class: "small" }, el("b", null, "“Never this” by origin: "), rej.map(([o, v]) => `${originLabel(o)} ${v}`).join(", ")) : null);
  }

  function questionsCard(prof) {
    const rec = prof.questions.filter(q => q.recommended), rest = prof.questions.filter(q => !q.recommended);
    const item = q => el("li", { class: "q q-" + q.kind },
      el("span", { class: "tag" }, { lopsided: "strong pull", pattern: "pattern", inconsistent: "inconsistent", tension: "tension", reject: "dislike", no_fit: "no fit", ambivalent: "hesitated" }[q.kind] || q.kind),
      el("p", { class: "ask" }, q.text), el("p", { class: "ctx muted small" }, q.context));
    return el("section", { class: "card questions" },
      el("h2", null, "Ask “why?” at the next meeting"),
      rec.length ? el("ol", null, rec.map(item)) : el("p", { class: "muted" }, "Not enough answers to suggest questions yet."),
      rest.length ? el("details", null, el("summary", null, `${rest.length} more`), el("ol", { start: rec.length + 1 }, rest.map(item))) : null);
  }

  // What the pictures they picked have in common, read from the hidden image tags.
  function attributesCard(prof) {
    const row = a => el("li", { "data-tip": `${a.group}: picked ${a.wins} of ${a.n} times when it was one of the two options` + (a.rejects ? ` · “never this” ${a.rejects}x` : "") + ` · seen in ${a.rounds} set(s)` },
      el("span", { class: "attr-label" }, a.label),
      el("span", { class: "attr-bar" }, el("span", { style: `width:${pct(a.n ? a.rate : 0)}` })),
      el("span", { class: "attr-val" }, `${a.wins}/${a.n}` + (a.rejects ? ` ✕${a.rejects}` : "")));
    const A = prof.attributes;
    return el("section", { class: "card" },
      el("h2", null, "What they respond to"),
      el("p", { class: "muted small" }, "Every picture carries hidden tags (roof pitch, eaves, texture, arches, ornament, greenery…). Counted only when the two pictures in a pair differed on that tag, across all sets. The bar shows how often the picture with that feature was the one picked."),
      el("div", { class: "two" },
        el("div", null, el("h3", null, "Drawn to"), A.drawn.length ? el("ul", { class: "attrs" }, A.drawn.slice(0, 8).map(row)) : el("p", { class: "muted small" }, "No clear pattern yet.")),
        el("div", null, el("h3", null, "Pushed away by"), A.repelled.length ? el("ul", { class: "attrs" }, A.repelled.slice(0, 8).map(row)) : el("p", { class: "muted small" }, "No clear pattern yet."))));
  }

  function dimensionsCard(prof) {
    return el("section", { class: "card" },
      el("h2", null, "By dimension"),
      el("p", { class: "muted small" }, "Score per option: +1 per win, −1 per loss, +½ both, −½ neither, −2 “never this”, averaged over times shown. Bar colour is the option's origin."),
      el("div", { class: "dims" }, prof.dimensions.map(d => {
        const chips = {};
        d.options.forEach(o => Object.entries(o.chips).forEach(([c, n]) => chips[c] = (chips[c] || 0) + n));
        const chipText = Object.entries(chips).sort((a, b) => b[1] - a[1]).map(([c, n]) => `${tx((D.chips.find(x => x.id === c) || { label: c }).label)} ${n}`).join(" · ");
        return el("article", { class: "dim" },
          el("header", null, el("h3", null, d.name), meter(d.strength, d.strength_label)),
          el("p", { class: "small" }, d.winner ? ["Prefers ", el("b", null, d.winner.label)] : el("span", { class: "muted" }, "No clear preference"),
            el("span", { class: "muted" }, ` · ${d.answered}/${d.total} answered` + (d.neither_share ? ` · ${pct(d.neither_share)} neither` : ""))),
          optionBars(d),
          chipText ? el("p", { class: "small muted" }, "Caught their eye: " + chipText) : null);
      })));
  }

  function flagsCard(prof) {
    return el("section", { class: "card" },
      el("h2", null, "Consistency checks"),
      prof.flags.length ? el("ul", { class: "flags" }, prof.flags.map(f => el("li", null, el("span", { class: "tag" }, f.type.replace(/_/g, " ")), " ", f.message)))
        : el("p", { class: "muted" }, "No inconsistencies, cycles, side bias or long hesitations found."));
  }

  function paletteCard(prof) {
    const sw = (list, neg) => list.length ? el("div", { class: "swatches" }, list.map(c => el("figure", { class: "swatch" + (neg ? " neg" : "") },
      el("span", { style: `background:${c.hex}` }), el("figcaption", null, c.name, el("small", null, c.hex))))) : el("p", { class: "muted small" }, "–");
    const mats = (list) => list.length ? el("ul", { class: "mats" }, list.map(m => el("li", null, m.name, el("small", { class: "muted" }, ` ${m.score > 0 ? "+" : ""}${m.score.toFixed(1)}`)))) : el("p", { class: "muted small" }, "–");
    return el("section", { class: "card" },
      el("h2", null, "Materials & colour"),
      el("p", { class: "muted small" }, "Weighted from the tags on chosen (+), both (+½), neither (−½) and rejected (−2) images. A starting palette, not a specification."),
      el("div", { class: "two" },
        el("div", null, el("h3", null, "Lean towards"), sw(prof.palette.colours_lean), mats(prof.palette.materials_lean)),
        el("div", null, el("h3", null, "Avoid"), sw(prof.palette.colours_avoid, true), mats(prof.palette.materials_avoid))));
  }

  function briefCard(prof) {
    const entries = D.brief.fields.map(f => [tx(f.label), prof.brief[f.id]]).filter(([, v]) => v !== undefined && v !== "" && !(Array.isArray(v) && !v.length));
    return el("section", { class: "card" },
      el("h2", null, "Functional brief"),
      entries.length ? el("dl", { class: "brief-dl" }, entries.map(([k, v]) => [el("dt", null, k), el("dd", null, Array.isArray(v) ? v.join(", ") : String(v))]))
        : el("p", { class: "muted" }, "Skipped or not reached."));
  }

  function compareCard(cmp) {
    const names = loaded.map(l => l.session.respondent.name || "Unnamed");
    return el("section", { class: "card" },
      el("h2", null, `Compare: ${names.join(" vs ")}`),
      el("table", { class: "glance" },
        el("thead", null, el("tr", null, el("th", null, "Dimension"), ...names.map(n => el("th", null, n)), el("th", null, ""))),
        el("tbody", null, cmp.dimensions.map(d => el("tr", { class: d.disagree ? "disagree" : "" },
          el("td", null, d.name), ...d.winners.map((w, i) => el("td", null, w, el("small", { class: "muted" }, " " + d.strengths[i]))),
          el("td", null, d.disagree ? el("span", { class: "tag warn" }, "⚠ differ") : d.agree ? el("span", { class: "tag ok" }, "✓ agree") : ""))))),
      el("p", { class: "small muted" }, `${cmp.opposite_pairs.length} pairs where they picked opposite images.` +
        (cmp.dimensions.some(d => d.disagree) ? " Start the next meeting with the rows marked “differ”: those need a joint decision." : "")));
  }

  function responsesCard(s) {
    const latest = S.latestResponses(s);
    const rows = P.pairs.filter(p => latest[p.id]).map(p => {
      const r = latest[p.id], A = imgs[p.image_a], B = imgs[p.image_b];
      const thumb = (img, side) => el("img", { src: imageUrl(P, img), alt: "", class: "thumb" + (r.choice === side ? " picked" : r.choice === "reject_" + side ? " rejected" : "") });
      return el("tr", null, el("td", null, p.id), el("td", null, thumb(A, "a")), el("td", null, thumb(B, "b")),
        el("td", null, r.choice.replace("_", " ")), el("td", null, (r.chips || []).join(", ")), el("td", { class: "num" }, r.ms ? (r.ms / 1000).toFixed(1) + "s" : ""));
    });
    return el("section", { class: "card no-print-detail" },
      el("details", null, el("summary", null, `All responses (${rows.length})`),
        el("table", { class: "responses" }, el("thead", null, el("tr", null, ["Pair", "A", "B", "Choice", "Tags", "Time"].map(h => el("th", null, h)))), el("tbody", null, rows))));
  }

  // ---------- demo: a simulated respondent to see the view working ----------
  function loadDemo() {
    const rand = S.rng("demo-" + loaded.length);
    const like = { roof: "kerala_steep_tile", courtyard: "nalukettu_enclosed", facade_material: "lime_whitewash", columns: "timber_columns",
      openings: "arched_openings", palette: "ochre_terracotta", landscape: "fountain_patio", abstraction: "restrained" };
    const hate = { roof: "modern_flat_slab", landscape: "dry_native" };
    const steps = S.buildSequence(D, P.pairs, P.images, "demo");
    const responses = steps.filter(x => x.type === "pair").map(x => {
      const p = P.pairs.find(q => q.id === x.pair_id), A = imgs[p.image_a], B = imgs[p.image_b];
      let choice;
      if (hate[p.dimension_id] === A.option_id && rand() < 0.7) choice = "reject_a";
      else if (hate[p.dimension_id] === B.option_id && rand() < 0.7) choice = "reject_b";
      else if (A.option_id === like[p.dimension_id]) choice = rand() < 0.85 ? "a" : "b";
      else if (B.option_id === like[p.dimension_id]) choice = rand() < 0.85 ? "b" : "a";
      else { const u = rand(); choice = u < 0.4 ? "a" : u < 0.8 ? "b" : u < 0.9 ? "both" : "neither"; }
      const chips = (choice === "a" || choice === "b") && rand() < 0.6 ? [D.chips[Math.floor(rand() * D.chips.length)].id] : [];
      return { pair_id: p.id, choice, swapped: x.swapped, chips, ms: Math.round(2000 + rand() * 5000 + (rand() < 0.05 ? 20000 : 0)), timestamp: new Date().toISOString() };
    });
    const now = new Date();
    addSession({ type: "visual-brief-session", schema_version: 1, id: "demo-" + loaded.length, project_id: pid,
      respondent: { name: "Simulated client " + (loaded.length + 1) }, seed: "demo", started_at: new Date(now - 14 * 60000).toISOString(),
      updated_at: now.toISOString(), completed_at: now.toISOString(), responses,
      brief: { household: "Couple, two children, parents visiting often", spaces: ["Pooja room", "Ground-floor bedroom for elders", "Swing (oonjal) space"], cars: "2", plot: "Shortlisted" } }, "simulated");
    active = loaded.length - 1; render();
  }

  // ---------- render ----------
  function render() {
    const root = app(); root.innerHTML = "";
    const bar = el("header", { class: "top" }, el("div", { class: "brand" }, el("span", { class: "proj" }, tx(D.project.name)), el("span", { class: "muted small" }, " · Architect view")));
    root.append(bar);
    const main = el("main", { class: "wrap wide" });
    root.append(main);
    main.append(sourcesPanel());
    if (!loaded.length) { main.append(el("section", { class: "card" }, el("p", { class: "muted" }, "Select or import a response to see the preference profile."))); return; }

    const profiles = loaded.map(l => S.computeProfile(D, P.pairs, P.images, l.session));
    active = Math.min(active, loaded.length - 1);
    const s = loaded[active].session, prof = profiles[active];

    if (loaded.length > 1) main.append(el("nav", { class: "tabs no-print" }, loaded.map((l, i) => el("button", { class: "tab" + (i === active ? " on" : ""), onclick: () => { active = i; render(); } }, l.session.respondent.name || "Unnamed"))));
    main.append(el("div", { class: "toolbar no-print" },
      el("button", { class: "btn", onclick: () => download(`visual-brief-profile_${pid}_${slug(s.respondent.name)}.json`, { type: "visual-brief-profile", schema_version: 1, session: s, profile: prof }) }, "Export JSON"),
      el("button", { class: "btn", onclick: () => window.print() }, "Print / save PDF")));
    main.append(headerCard(s, prof), questionsCard(prof), headline(prof));
    if (loaded.length > 1) main.append(compareCard(S.compareProfiles(D, P.pairs, profiles, loaded.map(l => l.session))));
    main.append(attributesCard(prof), blendCard(prof), dimensionsCard(prof), paletteCard(prof), flagsCard(prof), briefCard(prof), responsesCard(s));
  }

  window.VBData.loadProject().then(function (project) {
    P = project; D = project.dataset; pid = D.project.id;
    imgs = Object.fromEntries(P.images.map(i => [i.id, i]));
    dimsById = Object.fromEntries(D.dimensions.map(d => [d.id, d]));
    origins = Object.fromEntries(D.origins.map(o => [o.id, o]));
    document.title = "Architect view · " + tx(D.project.name);
    document.body.append(tip);
    window.addEventListener("beforeprint", () => document.querySelectorAll(".questions details").forEach(d => d.open = true));
    const cur = store.current(pid), all = store.sessions(pid);
    if (cur && all[cur]) addSession(all[cur], "this device");
    render();
  }).catch(window.VBData.showError);
})();
