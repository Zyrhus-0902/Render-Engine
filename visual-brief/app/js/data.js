/*
 * Visual brief: dataset loading, image URLs and local storage.
 *
 * A dataset lives in datasets/<project>/ as dataset.json, pairs.json and
 * assets/manifest.json. Served over http(s) the pages fetch those files.
 * The single-file bundle (tools/build_bundle.py) instead embeds them as
 * window.VB_BUNDLE, which also makes the page work from file://.
 */
(function () {
  "use strict";
  const DEFAULT_PROJECT = "erode-hacienda-kerala";
  const DATA_ROOT = "../datasets/";

  function projectId() {
    if (window.VB_BUNDLE) return window.VB_BUNDLE.dataset.project.id;
    const q = new URLSearchParams(location.search).get("project");
    return (q && /^[a-z0-9._-]+$/i.test(q)) ? q : DEFAULT_PROJECT;
  }

  async function fetchJSON(url) {
    const r = await fetch(url, { cache: "no-cache" });
    if (!r.ok) throw new Error(`${url}: HTTP ${r.status}`);
    return r.json();
  }

  async function loadProject() {
    if (window.VB_BUNDLE) {
      const b = window.VB_BUNDLE;
      return { dataset: b.dataset, pairs: b.pairs, images: b.images, assetBase: "" };
    }
    const id = projectId(), base = DATA_ROOT + id + "/";
    try {
      const [dataset, pairs, manifest] = await Promise.all([
        fetchJSON(base + "dataset.json"), fetchJSON(base + "pairs.json"), fetchJSON(base + "assets/manifest.json"),
      ]);
      return { dataset, pairs: pairs.pairs, images: manifest.images, assetBase: base + "assets/" };
    } catch (e) {
      const hint = location.protocol === "file:"
        ? "Opened as a local file: browsers block loading the dataset this way. Serve the folder (python -m http.server, from visual-brief/) or use the single-file bundle from tools/build_bundle.py."
        : `Could not load project "${id}". Check datasets/${id}/.`;
      throw new Error(hint + "\n\n" + e.message);
    }
  }

  function imageUrl(project, img) {
    if (!img) return "";
    if (img.data_uri) return img.data_uri;
    if (/^(https?:|data:)/.test(img.file)) return img.file;
    return project.assetBase + img.file;
  }

  // ---------- storage (best effort: private windows may block it) ----------
  function key(pid, name) { return `vb:v1:${pid}:${name}`; }
  function read(pid, name, fallback) {
    try { const v = localStorage.getItem(key(pid, name)); return v ? JSON.parse(v) : fallback; } catch (e) { return fallback; }
  }
  function write(pid, name, value) {
    try { localStorage.setItem(key(pid, name), JSON.stringify(value)); return true; } catch (e) { return false; }
  }
  const store = {
    sessions(pid) { return read(pid, "sessions", {}); },
    saveSession(pid, s) { const all = store.sessions(pid); all[s.id] = s; return write(pid, "sessions", all); },
    deleteSession(pid, id) { const all = store.sessions(pid); delete all[id]; write(pid, "sessions", all); },
    current(pid) { return read(pid, "current", null); },
    setCurrent(pid, id) { write(pid, "current", id); },
    lang(pid) { return read(pid, "lang", null); },
    setLang(pid, l) { write(pid, "lang", l); },
  };

  function download(filename, obj) {
    const blob = new Blob([JSON.stringify(obj, null, 2)], { type: "application/json" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob); a.download = filename;
    document.body.appendChild(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(a.href), 2000);
  }

  function slug(s) { return String(s || "").toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "") || "respondent"; }

  function el(tag, attrs, ...children) {
    const n = document.createElement(tag);
    for (const k in (attrs || {})) {
      const v = attrs[k];
      if (v == null || v === false) continue;
      if (k === "class") n.className = v;
      else if (k.startsWith("on")) n.addEventListener(k.slice(2), v);
      else if (k === "html") n.innerHTML = v;
      else n.setAttribute(k, v === true ? "" : v);
    }
    for (const c of children.flat(Infinity)) if (c != null && c !== false) n.append(c.nodeType ? c : document.createTextNode(String(c)));
    return n;
  }

  function showError(err) {
    document.body.innerHTML = "";
    document.body.append(el("main", { class: "wrap error" }, el("h1", null, "Couldn't start"), el("pre", null, String(err.message || err))));
  }

  window.VBData = { loadProject, imageUrl, store, download, slug, el, showError, projectId };
})();
