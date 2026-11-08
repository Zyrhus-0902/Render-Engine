// Run: node --test visual-brief/tests/scoring.test.js
"use strict";
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const S = require("../app/js/scoring.js");

const base = path.join(__dirname, "..", "datasets", "erode-hacienda-kerala");
const D = JSON.parse(fs.readFileSync(path.join(base, "dataset.json"), "utf8"));
const P = JSON.parse(fs.readFileSync(path.join(base, "pairs.json"), "utf8")).pairs;
const I = JSON.parse(fs.readFileSync(path.join(base, "assets", "manifest.json"), "utf8")).images;
const imgs = Object.fromEntries(I.map(i => [i.id, i]));

// A respondent who always picks a fixed option per dimension when it is shown.
function respond(likes, opts = {}) {
  const steps = S.buildSequence(D, P, I, opts.seed || "t");
  const responses = steps.filter(s => s.type === "pair").map((s, n) => {
    const p = P.find(x => x.id === s.pair_id), a = imgs[p.image_a].option_id, b = imgs[p.image_b].option_id;
    let choice = opts.default || "a";
    if (opts.rejects && opts.rejects[p.dimension_id] === a) choice = "reject_a";
    else if (opts.rejects && opts.rejects[p.dimension_id] === b) choice = "reject_b";
    else if (likes[p.dimension_id] === a) choice = "a";
    else if (likes[p.dimension_id] === b) choice = "b";
    if (opts.flip && opts.flip(p, n)) choice = choice === "a" ? "b" : choice === "b" ? "a" : choice;
    return { pair_id: p.id, choice, swapped: s.swapped, chips: choice === "a" || choice === "b" ? ["shape"] : [], ms: opts.ms ? opts.ms(p, n) : 3000 };
  });
  return { id: "x", respondent: { name: "T" }, responses, brief: {} };
}

test("sequence: every pair once, grouped by dimension, deterministic per seed", () => {
  const a = S.buildSequence(D, P, I, "seed-1"), b = S.buildSequence(D, P, I, "seed-1"), c = S.buildSequence(D, P, I, "seed-2");
  const ids = a.filter(s => s.type === "pair").map(s => s.pair_id);
  assert.equal(new Set(ids).size, P.length);
  assert.deepEqual(a, b);
  assert.notDeepEqual(a.map(s => s.pair_id), c.map(s => s.pair_id));
  assert.equal(a.filter(s => s.type === "round").length, D.dimensions.length);
  assert.equal(a.at(-1).type, "done");
  // Pairs of one round are contiguous, right after that round's intro.
  let cur = null;
  for (const s of a) { if (s.type === "round") cur = s.dimension_id; else if (s.type === "pair") assert.equal(s.dimension_id, cur); }
});

test("sequence: climate-excluded images drop their pairs", () => {
  const I2 = I.map(i => i.id === P[0].image_a ? Object.assign({}, i, { climate: { status: "exclude" } }) : i);
  const ids = S.buildSequence(D, P, I2, "s").filter(s => s.type === "pair").map(s => s.pair_id);
  assert.ok(!ids.includes(P[0].id));
});

test("profile: consistent respondent gets strong winners and the matching blend", () => {
  const likes = { roof: "kerala_steep_tile", courtyard: "nalukettu_enclosed", facade_material: "laterite", columns: "timber_columns",
    openings: "timber_slat_rect", palette: "wood_whitewash", landscape: "courtyard_planting", abstraction: "ornate" };
  const prof = S.computeProfile(D, P, I, respond(likes));
  for (const d of prof.dimensions) {
    assert.equal(d.winner.id, likes[d.id], d.id);
    assert.ok(["strong", "moderate"].includes(d.strength_label), `${d.id}: ${d.strength_label}`);
  }
  assert.ok(prof.blend.overall.kerala > 0.5, JSON.stringify(prof.blend.overall));
  assert.equal(prof.answered, P.length);
  assert.ok(prof.questions.filter(q => q.recommended).length <= 5);
  assert.ok(prof.questions.some(q => q.kind === "lopsided"));
  // The fake respondent answers "a" on pairs without its liked option, so only
  // contrasts involving the liked option are guaranteed consistent.
  for (const d of prof.dimensions) assert.ok(!d.inconsistencies.some(x => x.options.includes(likes[d.id])), d.id);
  assert.ok(prof.palette.colours_lean.some(c => c.name === "Dark teak"));
});

test("profile: a repeated contrast that flips is flagged inconsistent with a why? question", () => {
  let flipped = 0;
  const prof = S.computeProfile(D, P, I, respond({ roof: "kerala_steep_tile" }, {
    flip: p => p.dimension_id === "roof" && imgs[p.image_a].option_id === "hacienda_low_hip" && imgs[p.image_b].option_id === "kerala_steep_tile" && !flipped++,
  }));
  const roof = prof.dimensions.find(d => d.id === "roof");
  assert.equal(roof.inconsistencies.length, 1);
  assert.ok(prof.flags.some(f => f.type === "inconsistent" && f.dimension_id === "roof"));
  assert.ok(prof.questions.some(q => q.kind === "inconsistent" && q.dimension_id === "roof"));
});

test("profile: never-this lowers the option and is counted by origin", () => {
  const prof = S.computeProfile(D, P, I, respond({}, { rejects: { roof: "modern_flat_slab" } }));
  const flat = prof.dimensions.find(d => d.id === "roof").options.find(o => o.id === "modern_flat_slab");
  assert.equal(flat.rejects, 2);
  assert.ok(flat.score <= -1.5);
  assert.equal(prof.blend.rejections.modern, 2);
  assert.ok(prof.questions.some(q => q.kind === "reject" && q.dimension_id === "roof"));
});

test("profile: tensions fire when all their winners match", () => {
  const prof = S.computeProfile(D, P, I, respond({ courtyard: "nalukettu_enclosed", roof: "hacienda_low_hip" }));
  assert.ok(prof.questions.some(q => q.tension_id === "nalukettu_low_roof"));
});

test("profile: always-left picking is flagged as side bias", () => {
  const steps = S.buildSequence(D, P, I, "t");
  const responses = steps.filter(s => s.type === "pair").map(s => ({ pair_id: s.pair_id, choice: s.swapped ? "b" : "a", swapped: s.swapped, ms: 2000 }));
  const prof = S.computeProfile(D, P, I, { responses });
  assert.ok(prof.flags.some(f => f.type === "side_bias"));
});

test("profile: slow decisions surface as hesitation", () => {
  const prof = S.computeProfile(D, P, I, respond({}, { ms: (p) => p.id === "palette-03" ? 40000 : 3000 }));
  assert.ok(prof.flags.some(f => f.type === "hesitation" && f.pair_id === "palette-03"));
});

test("profile: mostly neither is flagged as no fit; empty session is safe", () => {
  const prof = S.computeProfile(D, P, I, respond({}, { default: "neither" }));
  assert.ok(prof.flags.some(f => f.type === "no_fit"));
  assert.ok(prof.dimensions.every(d => d.winner === null));
  const empty = S.computeProfile(D, P, I, { responses: [] });
  assert.equal(empty.answered, 0);
  assert.equal(empty.questions.length, 0);
});

test("latest answer wins when a pair is answered twice", () => {
  const r = S.latestResponses({ responses: [{ pair_id: "roof-01", choice: "a" }, { pair_id: "roof-01", choice: "b" }, { pair_id: "roof-02", choice: "bogus" }] });
  assert.equal(r["roof-01"].choice, "b");
  assert.ok(!r["roof-02"]);
});

test("compare: two respondents who disagree on roof", () => {
  const s1 = respond({ roof: "kerala_steep_tile", palette: "wood_whitewash" }), s2 = respond({ roof: "hacienda_low_hip", palette: "wood_whitewash" });
  const p1 = S.computeProfile(D, P, I, s1), p2 = S.computeProfile(D, P, I, s2);
  const cmp = S.compareProfiles(D, P, [p1, p2], [s1, s2]);
  assert.ok(cmp.dimensions.find(d => d.id === "roof").disagree);
  assert.ok(cmp.dimensions.find(d => d.id === "palette").agree);
  assert.ok(cmp.opposite_pairs.length > 0);
});
