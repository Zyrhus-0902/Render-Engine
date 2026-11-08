/*
 * Visual brief: sequencing and scoring. Pure functions, no DOM.
 * Loaded by both pages as a browser global (window.VBScoring) and by the
 * Node tests through module.exports.
 *
 * Choice values (always relative to the pair's canonical image_a / image_b,
 * whatever side the image was shown on):
 *   "a" | "b"            preferred that image
 *   "both"               liked both equally
 *   "neither"            liked neither
 *   "reject_a" | "reject_b"   "never this" on that image
 */
(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  else root.VBScoring = api;
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";

  // Points an option earns per appearance. Score = mean points, range [-2, 1].
  const POINTS = { win: 1, loss: -1, both: 0.5, neither: -0.5, rejected: -2, other_rejected: 0 };
  const CHOICES = ["a", "b", "both", "neither", "reject_a", "reject_b"];

  // ---------- helpers ----------
  function hashString(s) {
    let h = 2166136261 >>> 0;
    for (let i = 0; i < s.length; i++) { h ^= s.charCodeAt(i); h = Math.imul(h, 16777619); }
    return h >>> 0;
  }
  function rng(seed) { // mulberry32
    let a = typeof seed === "number" ? seed : hashString(String(seed));
    return function () {
      a |= 0; a = (a + 0x6d2b79f5) | 0;
      let t = Math.imul(a ^ (a >>> 15), 1 | a);
      t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
  }
  function shuffle(list, rand) {
    const a = list.slice();
    for (let i = a.length - 1; i > 0; i--) { const j = Math.floor(rand() * (i + 1)); [a[i], a[j]] = [a[j], a[i]]; }
    return a;
  }
  function median(xs) {
    if (!xs.length) return 0;
    const s = xs.slice().sort((x, y) => x - y), m = s.length >> 1;
    return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2;
  }
  function text(v, lang) {
    if (v == null) return "";
    if (typeof v === "string") return v;
    return v[lang] || v.en || Object.values(v)[0] || "";
  }
  function indexBy(list, key) { const m = {}; for (const x of list) m[x[key]] = x; return m; }
  function originWeights(img) {
    if (img.origin_weights) return img.origin_weights;
    const w = {}; w[img.origin] = 1; return w;
  }

  /** Images the climate/buildability filter keeps out of the client run. */
  function isExcluded(img) { return !img || (img.climate && img.climate.status === "exclude"); }

  /**
   * The ordered steps the client walks through: a round intro per dimension,
   * then that dimension's pairs (shuffled), then the brief, then done.
   * Deterministic for a given seed so a resumed session sees the same order.
   */
  function buildSequence(dataset, pairs, images, seed) {
    const settings = dataset.settings || {};
    const imgs = indexBy(images, "id");
    const rand = rng(seed || "fixed");
    const steps = [];
    dataset.dimensions.forEach(function (dim, di) {
      let ps = pairs.filter(p => p.dimension_id === dim.id && !isExcluded(imgs[p.image_a]) && !isExcluded(imgs[p.image_b]));
      if (!ps.length) return;
      if (settings.shuffle_pairs !== false) ps = shuffle(ps, rand);
      steps.push({ type: "round", dimension_id: dim.id, round_index: di, hidden: settings.round_intros === false });
      ps.forEach(function (p, pi) {
        steps.push({
          type: "pair", pair_id: p.id, dimension_id: dim.id, index_in_round: pi, round_size: ps.length,
          swapped: settings.randomise_sides !== false ? rand() < 0.5 : false,
        });
      });
    });
    const rounds = steps.filter(s => s.type === "round");
    rounds.forEach((r, i) => { r.round_number = i + 1; r.round_count = rounds.length; });
    steps.forEach(s => { if (s.type === "pair") { const r = rounds.find(x => x.dimension_id === s.dimension_id); s.round_number = r.round_number; s.round_count = r.round_count; } });
    // Round intro screens can be switched off: the client then sees only pictures.
    if (dataset.brief && dataset.brief.fields && dataset.brief.fields.length) steps.push({ type: "brief" });
    steps.push({ type: "done" });
    // Round intro screens can be switched off: the client then sees only pictures.
    return steps.filter(s => !(s.type === "round" && s.hidden));
  }

  /** Latest response per pair (a respondent may go back and change an answer). */
  function latestResponses(session) {
    const by = {};
    for (const r of (session.responses || [])) {
      if (CHOICES.indexOf(r.choice) < 0) continue;
      by[r.pair_id] = r;
    }
    return by;
  }

  function strengthLabel(s, decisive) {
    if (decisive === 0) return "no preference";
    if (s >= 0.6) return "strong";
    if (s >= 0.3) return "moderate";
    if (s >= 0.1) return "slight";
    return "split";
  }

  /**
   * The architect's preference profile for one session.
   * Returns per-dimension winners and strength, origin blend, consistency
   * flags, ranked "why?" questions, palette and material summary, brief.
   */
  function computeProfile(dataset, pairs, images, session, opts) {
    opts = opts || {};
    const lang = opts.lang || "en";
    const imgs = indexBy(images, "id");
    const pairById = indexBy(pairs, "id");
    const dimById = indexBy(dataset.dimensions, "id");
    const latest = latestResponses(session);
    const originIds = (dataset.origins || []).map(o => o.id);

    const attrStats = {}; // "key=value" -> {key, value, wins, losses, rejects, dims:Set}
    function attrHit(img, key, kind, dimId) {
      const v = (img.attributes || {})[key], k = key + "=" + v;
      attrStats[k] = attrStats[k] || { key, value: v, wins: 0, losses: 0, rejects: 0, dims: {} };
      attrStats[k][kind]++; attrStats[k].dims[dimId] = true;
    }
    function attrCompare(A, B, outcome, dimId) {
      // Only attributes that differ between the two pictures carry information.
      const keys = new Set(Object.keys(A.attributes || {}).concat(Object.keys(B.attributes || {})));
      for (const key of keys) {
        const va = (A.attributes || {})[key], vb = (B.attributes || {})[key];
        if (va == null || vb == null || va === vb) continue;
        if (outcome === "a") { attrHit(A, key, "wins", dimId); attrHit(B, key, "losses", dimId); }
        else if (outcome === "b") { attrHit(B, key, "wins", dimId); attrHit(A, key, "losses", dimId); }
        else if (outcome === "reject_a") attrHit(A, key, "rejects", dimId);
        else if (outcome === "reject_b") attrHit(B, key, "rejects", dimId);
      }
    }
    const blankBlend = () => { const b = {}; originIds.forEach(o => b[o] = 0); return b; };
    const blendOverall = blankBlend(), rejectByOrigin = blankBlend();
    const blendByDim = {};
    const colours = {}, materials = {};
    const flags = [], questions = [];
    const durations = [];
    let leftPicks = 0, rightPicks = 0;

    function credit(target, img, amount) {
      const w = originWeights(img);
      for (const o in w) target[o] = (target[o] || 0) + amount * w[o];
    }
    function tally(img, amount) {
      for (const c of (img.palette || [])) {
        const k = c.hex.toLowerCase();
        colours[k] = colours[k] || { name: c.name, hex: c.hex, score: 0, seen: 0 };
        colours[k].score += amount; colours[k].seen++;
      }
      for (const m of (img.materials || [])) {
        materials[m] = materials[m] || { name: m, score: 0, seen: 0 };
        materials[m].score += amount; materials[m].seen++;
      }
    }

    const dims = dataset.dimensions.map(function (dim) {
      const optStats = {};
      dim.options.forEach(o => optStats[o.id] = {
        id: o.id, label: text(o.label, lang), origin: o.origin, points: 0, appearances: 0,
        wins: 0, losses: 0, both: 0, neither: 0, rejects: 0, chips: {},
      });
      const h2h = {}; // "x|y" (sorted) -> {x: wins, y: wins}
      const dimPairs = pairs.filter(p => p.dimension_id === dim.id && !isExcluded(imgs[p.image_a]) && !isExcluded(imgs[p.image_b]));
      let answered = 0, decisive = 0, neitherCount = 0;
      blendByDim[dim.id] = blankBlend();

      for (const p of dimPairs) {
        const r = latest[p.id];
        if (!r) continue;
        answered++;
        const A = imgs[p.image_a], B = imgs[p.image_b];
        const sa = optStats[A.option_id], sb = optStats[B.option_id];
        if (!sa || !sb) continue;
        sa.appearances++; sb.appearances++;
        if (typeof r.ms === "number" && r.ms > 0) durations.push({ pair_id: p.id, ms: r.ms });
        const chips = r.chips || [];

        attrCompare(A, B, r.choice, dim.id);
        let winner = null, loser = null;
        switch (r.choice) {
          case "a": winner = sa; loser = sb; break;
          case "b": winner = sb; loser = sa; break;
          case "both":
            sa.points += POINTS.both; sb.points += POINTS.both; sa.both++; sb.both++;
            credit(blendOverall, A, 0.5); credit(blendOverall, B, 0.5);
            credit(blendByDim[dim.id], A, 0.5); credit(blendByDim[dim.id], B, 0.5);
            tally(A, 0.5); tally(B, 0.5);
            chips.forEach(c => { sa.chips[c] = (sa.chips[c] || 0) + 1; sb.chips[c] = (sb.chips[c] || 0) + 1; });
            break;
          case "neither":
            sa.points += POINTS.neither; sb.points += POINTS.neither; sa.neither++; sb.neither++;
            tally(A, -0.5); tally(B, -0.5); neitherCount++;
            break;
          case "reject_a": case "reject_b": {
            const rej = r.choice === "reject_a" ? sa : sb, other = rej === sa ? sb : sa;
            const rejImg = r.choice === "reject_a" ? A : B;
            rej.points += POINTS.rejected; rej.rejects++;
            other.points += POINTS.other_rejected;
            credit(rejectByOrigin, rejImg, 1);
            tally(rejImg, -2);
            break;
          }
        }
        if (winner) {
          decisive++;
          winner.points += POINTS.win; loser.points += POINTS.loss;
          winner.wins++; loser.losses++;
          const wImg = winner === sa ? A : B;
          credit(blendOverall, wImg, 1); credit(blendByDim[dim.id], wImg, 1);
          tally(wImg, 1);
          chips.forEach(c => winner.chips[c] = (winner.chips[c] || 0) + 1);
          if (winner.id !== loser.id) {
            const key = [winner.id, loser.id].sort().join("|");
            h2h[key] = h2h[key] || {}; h2h[key][winner.id] = (h2h[key][winner.id] || 0) + 1;
          }
          // Screen side, for a side-bias check: a shown on the left unless swapped.
          const choseA = r.choice === "a";
          if (choseA !== !!r.swapped) leftPicks++; else rightPicks++;
        }
      }

      const options = Object.values(optStats).map(function (s) {
        s.score = s.appearances ? s.points / s.appearances : null;
        return s;
      });
      const ranked = options.filter(o => o.score !== null).sort((x, y) => y.score - x.score || y.wins - x.wins);
      const top = ranked[0], second = ranked[1];
      const margin = top && second ? top.score - second.score : (top ? Math.max(top.score, 0) : 0);
      const strength = Math.max(0, Math.min(1, margin / 1.5));
      const hasWinner = !!top && top.score > 0 && decisive > 0 && strength >= 0.1;

      // Consistency: repeated contrasts that went both ways.
      const inconsistencies = [];
      for (const key in h2h) {
        const [x, y] = key.split("|"), wx = h2h[key][x] || 0, wy = h2h[key][y] || 0;
        if (wx > 0 && wy > 0) inconsistencies.push({
          options: [x, y], labels: [optStats[x].label, optStats[y].label], counts: [wx, wy],
          severity: Math.min(wx, wy) / (wx + wy),
        });
      }
      // Consistency: preference cycles (x beat y, y beat z, z beat x on net).
      const beats = {};
      for (const key in h2h) {
        const [x, y] = key.split("|"), wx = h2h[key][x] || 0, wy = h2h[key][y] || 0, net = wx - wy;
        // One vote is too thin to call a cycle; require two decisive votes per edge.
        if (wx + wy < 2) continue;
        if (net > 0) (beats[x] = beats[x] || {})[y] = true;
        if (net < 0) (beats[y] = beats[y] || {})[x] = true;
      }
      const cycles = [], ids = Object.keys(optStats);
      for (let i = 0; i < ids.length; i++) for (let j = 0; j < ids.length; j++) for (let k = 0; k < ids.length; k++) {
        const x = ids[i], y = ids[j], z = ids[k];
        if (i < j && i < k && j !== k && beats[x] && beats[x][y] && beats[y] && beats[y][z] && beats[z] && beats[z][x])
          cycles.push([x, y, z].map(o => optStats[o].label));
      }

      return {
        id: dim.id, name: text(dim.name, lang), answered, total: dimPairs.length, decisive,
        neither_share: answered ? neitherCount / answered : 0,
        options: ranked.concat(options.filter(o => o.score === null)),
        winner: hasWinner ? { id: top.id, label: top.label, origin: top.origin, score: top.score } : null,
        runner_up: second ? { id: second.id, label: second.label, score: second.score } : null,
        strength, strength_label: hasWinner ? strengthLabel(strength, decisive) : (decisive ? "split" : "no preference"),
        inconsistencies, cycles,
      };
    });

    // ---------- flags and questions ----------
    const optLookup = {};
    dataset.dimensions.forEach(d => d.options.forEach(o => optLookup[d.id + "/" + o.id] = o));
    const chipLabels = indexBy(dataset.chips || [], "id");
    function topChips(o) {
      return Object.entries(o.chips).sort((a, b) => b[1] - a[1]).slice(0, 2)
        .map(([c]) => text((chipLabels[c] || { label: c }).label, lang).toLowerCase());
    }

    for (const d of dims) {
      if (d.winner && d.strength >= 0.3) {
        const o = d.options[0], opt = optLookup[d.id + "/" + o.id];
        const chips = topChips(o);
        questions.push({
          kind: "lopsided", dimension_id: d.id, priority: 1 + d.strength,
          context: `${d.name}: chose "${o.label}" in ${o.wins} of ${o.appearances} pairs (${d.strength_label}).` +
            (chips.length ? ` Most tagged: ${chips.join(", ")}.` : ""),
          text: text(opt.why_prompt, lang) || `What is it about "${o.label}" that you like?`,
        });
      }
      for (const inc of d.inconsistencies) {
        flags.push({ type: "inconsistent", dimension_id: d.id, severity: inc.severity,
          message: `${d.name}: "${inc.labels[0]}" vs "${inc.labels[1]}" went both ways (${inc.counts[0]}-${inc.counts[1]}).` });
        questions.push({
          kind: "inconsistent", dimension_id: d.id, priority: 0.8 + inc.severity,
          context: `${d.name}: picked "${inc.labels[0]}" ${inc.counts[0]}x and "${inc.labels[1]}" ${inc.counts[1]}x when shown together.`,
          text: `Sometimes you chose ${inc.labels[0].toLowerCase()}, sometimes ${inc.labels[1].toLowerCase()}. What was different about the ones you picked? (Show both images side by side.)`,
        });
      }
      for (const c of d.cycles) flags.push({ type: "cycle", dimension_id: d.id, severity: 0.5,
        message: `${d.name}: circular preference ${c.join(" > ")} > ${c[0]}. Likely reacting to something other than the tested variable; check pair matching.` });
      if (d.answered >= 3 && d.neither_share >= 0.5) {
        flags.push({ type: "no_fit", dimension_id: d.id, severity: d.neither_share,
          message: `${d.name}: "neither" on ${Math.round(d.neither_share * 100)}% of pairs. None of the options fit.` });
        questions.push({ kind: "no_fit", dimension_id: d.id, priority: 0.9,
          context: `${d.name}: mostly "neither".`,
          text: `None of the ${d.name.toLowerCase()} options seemed right. Can you describe or show one you'd like?` });
      }
      for (const o of d.options) {
        if (o.rejects >= 2 || (o.rejects >= 1 && o.wins === 0 && o.appearances >= 2)) {
          questions.push({ kind: "reject", dimension_id: d.id, priority: 0.7 + 0.1 * o.rejects,
            context: `${d.name}: "never this" on "${o.label}" ${o.rejects}x.`,
            text: `You ruled out ${o.label.toLowerCase()} firmly. What about it puts you off?` });
        }
        if (o.rejects >= 1 && o.wins >= 1) {
          flags.push({ type: "reject_then_chose", dimension_id: d.id, severity: 0.4,
            message: `${d.name}: "${o.label}" was rejected once but also chosen ${o.wins}x. The rejected image may carry something else they dislike.` });
        }
      }
    }

    // Cross-dimension tensions defined in the dataset.
    const winners = {}; dims.forEach(d => { if (d.winner) winners[d.id] = d.winner.id; });
    for (const t of (dataset.tensions || [])) {
      if (t.when.every(c => winners[c.dimension] === c.option)) {
        questions.push({ kind: "tension", dimension_id: t.when[0].dimension, priority: 1.2,
          context: t.when.map(c => `${text(dimById[c.dimension].name, lang)}: ${text(optLookup[c.dimension + "/" + c.option].label, lang)}`).join(" + "),
          text: text(t.prompt, lang), tension_id: t.id });
      }
    }

    // Side bias and hesitation.
    const decisiveTotal = leftPicks + rightPicks;
    if (decisiveTotal >= 10) {
      const left = leftPicks / decisiveTotal;
      if (left >= 0.8 || left <= 0.2) flags.push({ type: "side_bias", severity: Math.abs(left - 0.5) * 2,
        message: `${Math.round(Math.max(left, 1 - left) * 100)}% of picks were on the ${left >= 0.5 ? "left/top" : "right/bottom"} side. Treat weak preferences with caution.` });
    }
    const med = median(durations.map(d => d.ms));
    const slow = durations.filter(d => d.ms > Math.max(2.5 * med, 8000)).sort((a, b) => b.ms - a.ms).slice(0, 3);
    for (const s of slow) {
      const p = pairById[s.pair_id], A = imgs[p.image_a], B = imgs[p.image_b];
      const la = text(optLookup[p.dimension_id + "/" + A.option_id].label, lang), lb = text(optLookup[p.dimension_id + "/" + B.option_id].label, lang);
      flags.push({ type: "hesitation", dimension_id: p.dimension_id, pair_id: p.id, severity: 0.3,
        message: `Took ${Math.round(s.ms / 1000)}s on ${p.id} (${la} vs ${lb}); median is ${Math.round(med / 1000)}s.` });
      questions.push({ kind: "ambivalent", dimension_id: p.dimension_id, priority: 0.5, pair_id: p.id,
        context: `Longest decision: ${la} vs ${lb}.`,
        text: `This pair took you the longest (${la} vs ${lb}). What was pulling you each way?` });
    }

    // ---------- attribute signals (across rounds) ----------
    const attrCat = indexBy(dataset.attributes || [], "id");
    const attrLabel = (key, v) => { const c = attrCat[key]; return c && c.values && c.values[v] ? text(c.values[v], lang) : `${key}: ${v}`; };
    const signals = Object.values(attrStats).map(a => {
      const n = a.wins + a.losses;
      const rate = n ? a.wins / n : 0;
      // Confidence-weighted lean: distance from a coin flip, scaled by sample size.
      const lean = n ? (rate - 0.5) * 2 * Math.min(1, Math.sqrt(n / 6)) : 0;
      return { key: a.key, value: a.value, label: attrLabel(a.key, a.value), group: attrCat[a.key] ? text(attrCat[a.key].label, lang) : a.key,
        wins: a.wins, losses: a.losses, rejects: a.rejects, n, rate, lean: a.rejects ? lean - 0.15 * a.rejects : lean,
        rounds: Object.keys(a.dims).length };
    }).filter(a => a.n >= 2 || a.rejects);
    // Ties are common (a steep roof always comes with deep eaves in the roof set); break
    // them by breadth: a feature that wins in more different sets is better evidence.
    const drawn = signals.filter(a => a.lean >= 0.3).sort((x, y) => y.lean - x.lean || y.rounds - x.rounds || y.n - x.n);
    const repelled = signals.filter(a => a.lean <= -0.3).sort((x, y) => x.lean - y.lean || y.rounds - x.rounds || y.n - x.n);
    for (const a of drawn.slice(0, 2)) {
      if (a.rounds < 2) continue; // only cross-round patterns say something the dimension view doesn't
      questions.push({ kind: "pattern", priority: 1 + a.lean / 2, context: `Across ${a.rounds} different sets they chose pictures with ${a.label} ${a.wins} of ${a.n} times.`,
        text: `You were drawn to ${a.label} again and again, even when we were showing something else. What does it give you?` });
    }

    questions.sort((a, b) => b.priority - a.priority);
    questions.forEach((q, i) => q.recommended = i < 5);
    flags.sort((a, b) => b.severity - a.severity);

    // ---------- blend ----------
    function normalise(b) {
      const sum = Object.values(b).reduce((x, y) => x + y, 0), out = {};
      for (const k in b) out[k] = sum ? b[k] / sum : 0;
      return out;
    }
    const byDim = {}; for (const k in blendByDim) byDim[k] = normalise(blendByDim[k]);

    // ---------- palette ----------
    const cl = Object.values(colours), ml = Object.values(materials);
    const lean = xs => xs.filter(x => x.score > 0).sort((a, b) => b.score - a.score).slice(0, 8);
    const avoid = xs => xs.filter(x => x.score < 0).sort((a, b) => a.score - b.score).slice(0, 6);

    const answered = Object.keys(latest).filter(id => pairById[id]).length;
    return {
      schema_version: 1,
      project_id: dataset.project.id,
      respondent: session.respondent || {},
      generated_at: new Date().toISOString(),
      answered, total_pairs: dims.reduce((s, d) => s + d.total, 0),
      dimensions: dims,
      blend: { overall: normalise(blendOverall), raw: blendOverall, by_dimension: byDim, rejections: rejectByOrigin },
      flags, questions,
      attributes: { drawn, repelled, all: signals },
      palette: { colours_lean: lean(cl), colours_avoid: avoid(cl), materials_lean: lean(ml), materials_avoid: avoid(ml) },
      brief: session.brief || {},
      timing: { median_ms: med, pairs_timed: durations.length },
    };
  }

  /** Where two or more respondents agree and disagree. */
  function compareProfiles(dataset, pairs, profiles, sessions) {
    const dims = dataset.dimensions.map(function (dim) {
      const per = profiles.map(p => p.dimensions.find(d => d.id === dim.id));
      const winners = per.map(d => d && d.winner ? d.winner.id : null);
      const named = winners.filter(Boolean);
      return {
        id: dim.id, name: text(dim.name), winners: per.map(d => d && d.winner ? d.winner.label : "no clear preference"),
        strengths: per.map(d => d ? d.strength_label : ""),
        agree: named.length === winners.length && new Set(named).size === 1,
        disagree: new Set(named).size > 1,
      };
    });
    const opposite = [];
    if (sessions && sessions.length >= 2) {
      const L = sessions.map(latestResponses);
      for (const p of pairs) {
        const cs = L.map(l => l[p.id] && l[p.id].choice).filter(Boolean);
        const sides = cs.map(c => (c === "a" || c === "reject_b") ? "a" : (c === "b" || c === "reject_a") ? "b" : null).filter(Boolean);
        if (sides.length >= 2 && new Set(sides).size > 1) opposite.push({ pair_id: p.id, dimension_id: p.dimension_id, choices: cs });
      }
    }
    return { dimensions: dims, opposite_pairs: opposite };
  }

  return { POINTS, CHOICES, buildSequence, computeProfile, compareProfiles, latestResponses, isExcluded, rng, shuffle, hashString, text };
});
