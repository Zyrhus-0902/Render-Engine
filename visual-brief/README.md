# Visual brief

**Pull a client's design vision out of them with image pairs instead of a questionnaire.**

A style label like "hacienda + Kerala, modern" means something different to every
client, and a single saved image mixes 6-8 design variables at once. This tool
splits the style into **dimensions** (roof, courtyard, walls, columns, openings,
colour, landscape, abstraction) and shows A/B pairs **within one dimension at a
time**, so only one thing changes per pair. The client just taps. The architect
gets a preference profile and a short list of sharp "why?" questions for the next
meeting.

It's a static web app with no backend, it works on a phone or tablet, and you
can run it in a meeting or send it as a link or a single file.

## Try it

```bash
cd visual-brief
python -m http.server 8000
```

- Client: <http://localhost:8000/app/> (add `?project=<id>` for another dataset)
- Architect: <http://localhost:8000/app/architect.html>. Use **Load a simulated
  respondent** to see a full profile without doing the run yourself.

Single files that open offline, even from `file://`, for sending over WhatsApp or email,
or putting on a USB stick or a static host:

```bash
python visual-brief/tools/build_bundle.py erode-hacienda-kerala
# -> visual-brief/dist/erode-hacienda-kerala/brief.html      (send this to the client)
#    visual-brief/dist/erode-hacienda-kerala/architect.html  (keep this one)
```

## The client flow

1. Intro: the project name, a short instruction and an optional name field. An unfinished run can be resumed.
2. Per round: a one-line prompt ("Look only at the roof"), then 6-8 pairs.
   - Tap a picture, or choose **Both equally**, **Neither** or **✕ Never this** under either picture.
   - Optional "what caught your eye?" chips: shape, colour, material, light, mood, detail.
   - Progress shows per round and overall. Back is always available, and an answer can be changed.
   - Pair order and left/right sides are shuffled per respondent, with a fixed seed so a resumed run keeps the same order.
3. An optional functional brief: household, must-have spaces, cars, wants and don't-wants, plot status.
4. A thank-you screen with **Download my answers** (for remote clients) and **Another person's turn** (for a couple filling it in separately).

Progress saves to the browser as they go. The client never sees the analysis.

## The architect view

Load sessions saved on this device, or import the JSON files clients send. If you load two or more, you get a side-by-side comparison.

- **Ask "why?"**: the top 5 questions, ranked. They are built from the most lopsided dimensions (using each option's `why_prompt` and the chips they tapped), repeated contrasts that went both ways, cross-dimension tensions defined in the dataset, firm "never this" choices, rounds where nothing fit, and the pairs that took longest.
- **At a glance**: the winner, its strength (strong / moderate / slight / split) and the runner-up for each dimension.
- **Style blend**: Kerala / hacienda / modern / hybrid share, overall and per dimension, taken from the origin tags on the chosen images. It also counts "never this" by origin.
- **By dimension**: a score per option (+1 win, −1 loss, +½ both, −½ neither, −2 never, averaged over the times it was shown), plus chip counts.
- **Materials & colour**: what to lean towards and what to avoid, weighted from the materials and palette tags on each image.
- **Consistency checks**: flip-flops on repeated contrasts, preference cycles, side bias, slow decisions, and options rejected once but chosen elsewhere.
- **Compare**: the dimensions where two respondents disagree, and the pairs where they picked opposite images.
- **Export**: JSON (session + profile), or Print → Save as PDF.

## Data: a new project means a new dataset, not new code

```
datasets/<project>/
  dataset.json          project, branding, copy (per language), origins, dimensions + options,
                        chips, brief fields, tensions, settings
  pairs.json            pairs[]: id, dimension_id, image_a, image_b, origin_a, origin_b, tags, note
  assets/manifest.json  images[]: id, file, dimension_id, option_id, origin (or origin_weights),
                        subject, materials[], palette[{name,hex}], scale,
                        climate{status: ok|review|exclude, note}, source, credit, placeholder
  assets/*              the images
```

Responses (the downloaded file): `{type: "visual-brief-session", id, project_id,
respondent, seed, started_at, completed_at, responses: [{pair_id, choice, swapped,
chips, ms, timestamp}], brief}`. The `choice` value is one of `a | b | both | neither | reject_a |
reject_b`, always relative to the pair's `image_a`/`image_b`, whichever side the image was shown on.

Tools:

| Command | What it does |
|---|---|
| `python visual-brief/tools/validate.py <project>` | Checks references, one-dimension-per-pair, no same-option pairs, no climate-excluded images in pairs, 6-10 pairs per round, scale mismatches, missing credit, leftover placeholders |
| `python visual-brief/tools/build_bundle.py <project>` | Builds the single-file client and architect pages (validates first) |
| `python visual-brief/tools/make_placeholder_dataset.py` | Scaffolds the Erode starter dataset with labelled placeholder cards (`--force` overwrites curated JSON, so be careful) |
| `node --test visual-brief/tests/scoring.test.js` | Scoring tests (also run by `pytest`) |

## Curating the real image set (Erode)

The starter set has 8 dimensions, 55 pairs and 66 placeholder images. Each placeholder card
shows what the real photo should be. To replace one, drop the photo into
`assets/`, then in `manifest.json` set `file`, `source` and `credit` and remove
`"placeholder": true`. Rules from the brief that the data supports:

1. **Source pure, don't pre-blend.** Tag every image `kerala`, `hacienda`,
   `modern` or `hybrid`. The blend ratio comes from the client's choices. For a
   genuinely mixed image, use `origin_weights: {"kerala": 0.5, "modern": 0.5}`.
2. **Climate and buildability filter.** Set `climate.status` to `exclude`
   (the image is never shown, and the validator errors if a pair uses it) or `review`
   (the image is shown, and the validator lists it). Four images start as `review`: flat roof heat
   gain, laterite transport cost, unshaded full-height glass, and the irrigation demand of a lush garden.
   `dataset.json` → `project.climate_note` records the assumption that Erode is hot and semi-arid,
   with rain mostly from the northeast monsoon. **Check this against IMD normals before
   locking the filter.**
3. **Scale.** Every image has a `scale`. Keep pairs at the same scale, and the validator will flag a mismatch.
   Run the brief after basic massing and FSI are known, if possible.
4. **Isolate the variable.** Match the light, the framing and everything else within a pair.
   Each dimension's `isolate_note` says what should stay constant. If the
   profile shows a preference *cycle*, it usually means a badly matched pair.
5. **Repeats measure consistency.** The main Kerala-vs-hacienda contrast in each
   round appears 2-3 times with different images and sides swapped. Keep that pattern when curating.

The render engine in this repo can produce matched pairs: render one massing in
two material or roof variants with the same preset and camera.

## Open decisions (from the handoff), and what v1 does

| Decision | v1 |
|---|---|
| Hosting vs local file | Both. Serve the folder from any static host, or send the single-file bundle |
| Automatic return of results | Manual: the client downloads a JSON file and sends it. A form endpoint can be added later without changing the data format |
| Who fills it | Any number of people, each with their own saved session. The architect view compares them |
| Language | English. Tamil is ready to add: every client-facing string can be `{ "en": ..., "ta": ... }`. Add `"ta"` to `languages` and a `copy.ta` block, and a language picker appears |
| Branding | `branding.studio_name` and `branding.accent` in `dataset.json` |

The architect page is only unlisted, not protected: the client page never links to it. Don't send `architect.html` to clients.
