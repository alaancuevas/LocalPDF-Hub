// The work area of one tool: files in, options, run, result out.

import { ApiError, runTool } from "./api.js";
import { t } from "./i18n.js";
import { icon } from "./icons.js";
import { fadeIn, measure, slide } from "./motion.js";
import { pageGrid } from "./pagegrid.js";
import { openPages, probe, thumbnail } from "./pages.js";
import { askPasswords } from "./passwords.js";
import { formatRanges, parseRanges } from "./ranges.js";
import { accepts, TOOLS } from "./tools.js";

const MAX_BYTES = 500 * 1024 * 1024;
// pdf.js makes its own copy of the result to draw the thumbnail.
const THUMBNAIL_MAX_BYTES = 50 * 1024 * 1024;

// options.files: files to start with; options.onContinue(toolId, file) opens another tool with the result.
export function renderTool(root, id, tool, announce, options = {}) {
  const state = { files: [], values: defaults(tool), status: "idle", result: null, message: "" };
  // Split and Rotate: the open PDF, its thumbnails, and the pages picked or turned.
  Object.assign(state, { doc: null, grid: null, selected: new Set(), anchor: null, angles: [] });
  const form = document.createElement("form");
  form.className = "work";
  form.noValidate = true;
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    run();
  });
  // Option values live in the state so a redraw never loses what was typed.
  form.addEventListener("input", (event) => {
    if (event.target.name) state.values[event.target.name] = event.target.value;
    // Typing pages marks them in the thumbnails, without a redraw that would move the caret.
    if (event.target.name === "pages" && state.grid) {
      state.selected = parseRanges(event.target.value, state.doc.count);
      state.grid.sync();
      updateFoot();
    }
  });
  root.replaceChildren(form);
  draw();
  if (options.files?.length) addFiles(options.files);
  return {
    // Lets a language change redraw the texts without dropping the files.
    redraw: () => {
      state.grid?.sync();
      draw();
    },
    // Leaving the tool drops the open PDF and any password typed for it.
    destroy: () => {
      releaseResult();
      closePages();
      for (const entry of state.files) entry.password = null;
    },
  };

  function draw(focusSelector) {
    form.replaceChildren(header(), body(), footer());
    if (focusSelector) form.querySelector(focusSelector)?.focus();
  }

  function header() {
    const head = el("header", "work-head");
    head.append(el("h1", "", t(`${id}.title`)), el("p", "lede", t(`${id}.lede`)));
    if (state.status === "working") head.append(el("div", "progress"));
    return head;
  }

  function body() {
    const box = el("div", "work-body");
    if (state.status === "done") {
      box.append(resultPanel());
      return box;
    }
    box.append(dropZone());
    if (state.message) {
      const message = el("p", state.status === "error" ? "message is-error" : "message", state.message);
      if (state.status === "error") message.setAttribute("role", "alert");
      box.append(message);
    }
    if (state.files.length) box.append(el("p", "section-label", t(tool.multiple ? "filesLabel" : "fileLabel")), fileList());
    if (tool.fields.length) box.append(optionFields());
    if (state.grid) box.append(state.grid.element);
    return box;
  }

  function dropZone() {
    const zone = el("div", "drop");
    const input = document.createElement("input");
    input.type = "file";
    input.hidden = true;
    input.multiple = Boolean(tool.multiple);
    input.accept = tool.accepts.extensions.join(",");
    input.addEventListener("change", () => addFiles([...input.files]));

    const pick = el("button", "link", t(tool.multiple ? "dropPick" : "dropPickOne"));
    pick.type = "button";
    pick.addEventListener("click", () => input.click());

    const text = el("span", "", `${t(tool.multiple ? "dropHint" : "dropHintOne")} `);
    text.append(pick);
    zone.append(icon("upload-simple"), text, el("small", "", t("dropLimits", { types: tool.accepts.label })), input);

    zone.addEventListener("dragover", (event) => {
      event.preventDefault();
      zone.classList.add("is-over");
    });
    zone.addEventListener("dragleave", () => zone.classList.remove("is-over"));
    zone.addEventListener("drop", (event) => {
      event.preventDefault();
      zone.classList.remove("is-over");
      addFiles([...event.dataTransfer.files]);
    });
    return zone;
  }

  function fileList() {
    const list = el("ul", "files");
    state.files.forEach((entry, index) => {
      const row = el("li", entry.isNew ? "file is-new" : "file");
      entry.isNew = false;
      entry.row = row;
      entry.meta = el("span", "meta", fileMeta(entry));
      row.classList.toggle("is-locked", Boolean(entry.locked));
      row.append(icon(entry.locked ? "lock-simple" : kindIcon(entry.file)), el("span", "file-name", entry.file.name), entry.meta);

      const actions = el("span", "row-actions");
      if (tool.multiple && state.files.length > 1) {
        actions.append(
          iconButton("caret-up", t("moveUp"), () => move(index, -1), index === 0, "up"),
          iconButton("caret-down", t("moveDown"), () => move(index, 1), index === state.files.length - 1, "down"),
        );
      }
      if (tool.rotatable) {
        actions.append(iconButton("arrow-clockwise", t("rotateFile"), () => rotateFile(index), false, "rotate"));
      }
      actions.append(iconButton("x", t("remove"), () => removeFile(index), false, "remove"));
      row.append(actions);
      list.append(row);
    });
    return list;
  }

  function optionFields() {
    const box = el("div", "options");
    for (const field of tool.fields) {
      const label = el("label", "field");
      label.append(el("span", "field-label", t(field.label)));
      const control = field.type === "select" ? selectFor(field) : document.createElement("input");
      if (field.type !== "select") control.type = field.type;
      // A PDF's password is not a login for this app: no saved passwords here.
      if (field.type === "password") control.autocomplete = "off";
      control.name = field.name;
      control.required = Boolean(field.required);
      if (field.hint) control.placeholder = t(field.hint);
      if (field.type === "range") Object.assign(control, { min: field.min, max: field.max, step: field.step });
      control.value = state.values[field.name] ?? "";
      label.append(control);
      if (field.type === "range") {
        const output = el("output", "range-value", percent(control.value));
        control.addEventListener("input", () => {
          output.textContent = percent(control.value);
        });
        label.append(output);
      }
      box.append(label);
    }
    return box;
  }

  function footer() {
    const foot = el("footer", "work-foot");
    // The result panel has its own buttons; an empty bar would only add a line.
    foot.hidden = state.status === "done";
    if (state.status === "done") return foot;
    state.summary = el("span", "summary", summary());
    foot.append(state.summary);
    if (state.files.length) {
      const clear = el("button", "secondary", t("clear"));
      clear.type = "button";
      clear.addEventListener("click", reset);
      foot.append(clear);
    }
    const working = state.status === "working";
    state.primary = el("button", "primary", working ? t("working") : t(`${id}.action`));
    if (working) state.primary.prepend(el("span", "spinner"));
    state.primary.type = "submit";
    state.primary.disabled = !canRun();
    foot.append(state.primary);
    return foot;
  }

  function canRun() {
    if (!state.files.length || state.status === "working") return false;
    // The action asks for the passwords first.
    if (state.files.some((entry) => entry.locked)) return true;
    if (tool.pagePicker === "rotate") return state.angles.some((angle) => angle !== 0);
    if (tool.pagePicker === "select" && state.grid) return state.selected.size > 0;
    return true;
  }

  function updateFoot() {
    state.summary.textContent = summary();
    state.primary.disabled = !canRun();
  }

  function pagesChanged() {
    if (tool.pagePicker === "select") {
      state.values.pages = formatRanges(state.selected);
      if (form.elements.pages) form.elements.pages.value = state.values.pages;
    }
    updateFoot();
  }

  async function loadPages(entry) {
    closePages();
    const { state: kind } = await probe(entry.file);
    if (state.files[0] !== entry || kind === "aborted") return;
    if (kind === "damaged") return rejectDamaged(entry);
    if (kind === "locked") {
      entry.locked = true;
      draw();
      // The thumbnails need the password, so it is asked for right away.
      if (!(await askPasswords([entry], tooBig)) || state.files[0] !== entry) return;
    }
    openPages(entry.file).then((doc) => {
      // A newer file may have replaced this one while it was opening.
      if (state.files[0] !== entry) {
        doc?.close();
        return;
      }
      entry.pages = doc ? doc.count : null;
      if (doc) {
        state.doc = doc;
        state.selected = parseRanges(state.values.pages ?? "", doc.count);
        state.angles = Array(doc.count).fill(0);
        state.grid = pageGrid({ mode: tool.pagePicker, doc, state, onChange: pagesChanged });
      } else {
        state.message = t("pagesUnreadable");
      }
      draw();
    });
  }

  function closePages() {
    state.grid?.destroy();
    state.doc?.close();
    Object.assign(state, { doc: null, grid: null, selected: new Set(), anchor: null, angles: [] });
  }

  function resultPanel() {
    const result = state.result;
    const panel = el("div", "result");
    // The entrance plays once, when the result arrives; a language change or
    // protecting it again redraws the card without moving it.
    if (state.justFinished) panel.classList.add("is-entering");
    state.justFinished = false;

    const preview = el("div", "result-preview");
    if (result.thumb) preview.append(result.thumb);
    else preview.append(icon(previewIcon(result), 32));
    panel.append(preview);

    const info = el("div", "result-info");
    const title = el("p", "result-title");
    title.append(checkMark(), document.createTextNode(t("doneTitle")));
    info.append(title, el("p", "result-name", result.name), el("p", "result-meta", resultMeta(result)));
    if (id === "compress" && result.blob.size >= result.inputBytes) info.append(el("p", "result-note", t("notReduced")));
    if (result.locked) info.append(el("p", "result-note", t("resultLocked")));

    const link = el("a", "primary", t("downloadShort"));
    link.href = result.url;
    link.download = result.name;
    link.setAttribute("aria-label", `${t("downloadShort")} ${result.name}`);
    const again = el("button", "secondary", t("again"));
    again.type = "button";
    again.addEventListener("click", reset);
    const actions = el("div", "result-actions");
    actions.append(link, again);
    info.append(actions, ...passwordNotice());
    panel.append(info);

    const next = continueTargets();
    if (next.length) {
      const box = el("div", "result-next");
      box.append(el("p", "section-label", t("continueWith")));
      const list = el("div", "result-next-list");
      for (const target of next) {
        const button = el("button", "chip");
        button.type = "button";
        button.append(icon(TOOLS[target].icon, 16), document.createTextNode(t(`short.${target}`)));
        button.addEventListener("click", () => options.onContinue?.(target, resultFile()));
        list.append(button);
      }
      box.append(list);
      panel.append(box);
    }
    queueMicrotask(() => link.focus());
    return panel;
  }

  // Tools that take the result as it is, except this one. A copy made from a
  // file opened with its password stays here, next to "Protect again".
  function continueTargets() {
    if (!options.onContinue || state.files.some((entry) => entry.password)) return [];
    const file = resultFile();
    // Unlock only makes sense for a protected result, and Protect for one that is not.
    const skip = new Set([id, state.result.locked ? "protect" : "unlock"]);
    return Object.keys(TOOLS).filter((other) => !skip.has(other) && accepts(TOOLS[other], file));
  }

  function resultFile() {
    return new File([state.result.blob], state.result.name, { type: state.result.blob.type });
  }

  // First page and page count of a PDF result, drawn once and kept for redraws.
  function drawThumbnail() {
    const result = state.result;
    if (!result.name.toLowerCase().endsWith(".pdf") || result.blob.size > THUMBNAIL_MAX_BYTES) return;
    state.thumbJob?.abort();
    state.thumbJob = new AbortController();
    thumbnail(result.blob, 96, state.thumbJob.signal).then((drawn) => {
      if (!drawn || state.result !== result) return;
      if (drawn.locked) result.locked = true;
      else Object.assign(result, { thumb: drawn.canvas, pages: drawn.pages });
      // The card on screen now, which a language change may have replaced.
      const preview = form.querySelector(".result-preview");
      if (preview && result.thumb) {
        preview.replaceChildren(result.thumb);
        fadeIn(result.thumb, 200);
      }
      const meta = form.querySelector(".result-meta");
      if (meta) meta.textContent = resultMeta(result);
      if (result.locked) draw();
    });
  }

  function releaseResult() {
    state.thumbJob?.abort();
    state.thumbJob = null;
    if (state.result) URL.revokeObjectURL(state.result.url);
  }

  // What the result panel says when a file was opened with its password.
  function passwordNotice() {
    if (state.result.protected) return [el("p", "result-note", t("protectedAgain"))];
    const opened = state.files.filter((entry) => entry.password);
    if (!opened.length) return [];
    // /protect takes PDFs only; a ZIP or DOCX just gets an honest note.
    if (!state.result.name.toLowerCase().endsWith(".pdf")) return [el("p", "result-note", t("resultUnlockedOther"))];
    const several = new Set(opened.map((entry) => entry.password)).size > 1;
    const label = several ? t("protectAgainFrom", { name: opened[0].file.name }) : t("protectAgain");
    const button = el("button", "secondary", label);
    button.type = "button";
    button.addEventListener("click", () => protectResult(button, opened[0].password));
    const nodes = [el("p", "result-note", t("resultUnlockedPdf")), button, el("p", "result-hint", t("protectAgainHint"))];
    if (state.result.error) nodes.push(el("p", "message is-error", state.result.error));
    return nodes;
  }

  async function protectResult(button, password) {
    button.disabled = true;
    const body = new FormData();
    body.append("file", state.result.blob, state.result.name);
    body.append("password", password);
    try {
      const { blob } = await runTool("protect", body);
      URL.revokeObjectURL(state.result.url);
      // Same pages as before; pdf.js cannot draw the encrypted copy.
      state.result = { ...state.result, url: URL.createObjectURL(blob), blob, protected: true, locked: true, thumb: null, error: undefined };
      for (const entry of state.files) entry.password = null;
      announce(t("protectedAgain"));
    } catch (error) {
      state.result.error = t(`error.${error instanceof ApiError ? error.code : "ERR_INTERNAL"}`);
    }
    draw();
  }

  // Limits for the unlocked copy, which can be larger than the locked file.
  function tooBig(entry, size) {
    if (size > MAX_BYTES) return t("unlockedTooBig", { name: entry.file.name });
    if (tool.multiple && totalBytes() - entry.file.size + size > MAX_BYTES) return t("unlockedTooBigTotal");
    return "";
  }

  function rejectDamaged(entry) {
    state.files.splice(state.files.indexOf(entry), 1);
    state.message = t("rejectedDamaged", { name: entry.file.name });
    draw();
  }

  // Applies what opening the file showed, in place, so a field being typed keeps its focus.
  function settle(entry, kind, pages) {
    if (!state.files.includes(entry) || kind === "aborted") return;
    if (kind === "damaged") return rejectDamaged(entry);
    // Protect and Unlock take the password in their own field.
    entry.locked = kind === "locked" && !tool.takesPassword;
    entry.pages = pages;
    if (entry.locked && entry.row) {
      entry.row.classList.add("is-locked");
      entry.row.firstElementChild.replaceWith(icon("lock-simple"));
    }
    if (entry.meta) entry.meta.textContent = fileMeta(entry);
    if (state.summary) updateFoot();
  }

  function addFiles(files) {
    state.message = "";
    state.status = "idle";
    for (const file of files) {
      if (!accepts(tool, file)) {
        state.message = t("rejectedType", { name: file.name });
        continue;
      }
      if (file.size > MAX_BYTES) {
        state.message = t("rejectedSize", { name: file.name });
        continue;
      }
      // The server limits the whole request, not each file.
      if (tool.multiple && totalBytes() + file.size > MAX_BYTES) {
        state.message = t("rejectedTotal", { name: file.name });
        continue;
      }
      const entry = { file, pages: undefined, rotation: 0, meta: null, isNew: true };
      if (tool.multiple) {
        state.files.push(entry);
      } else {
        if (state.files.length) state.message = t("onlyOne");
        state.files = [entry];
      }
      if (tool.pagePicker) {
        loadPages(entry);
        continue;
      }
      // Opening the file can take a moment; only the affected row is updated.
      probe(file).then(({ state: kind, pages }) => settle(entry, kind, pages));
    }
    draw();
  }

  function totalBytes() {
    return state.files.reduce((sum, entry) => sum + entry.file.size, 0);
  }

  // The rows below a removed one, or around a moved one, slide to their new place.
  function rows() {
    return state.files.map((entry) => [entry, entry.row]);
  }

  function removeFile(index) {
    const before = measure(rows());
    state.files.splice(index, 1);
    if (tool.pagePicker) closePages();
    draw();
    slide(before, rows());
  }

  function move(index, step) {
    const [entry] = state.files.splice(index, 1);
    const target = index + step;
    state.files.splice(target, 0, entry);
    const edge = target === 0 || target === state.files.length - 1;
    // Keep focus on the moved row so the keyboard user can keep moving it.
    const action = step < 0 ? (edge ? "down" : "up") : edge ? "up" : "down";
    const before = measure(rows());
    draw(`.file:nth-child(${target + 1}) [data-action="${action}"]`);
    slide(before, rows());
  }

  function rotateFile(index) {
    const entry = state.files[index];
    entry.rotation = (entry.rotation + 90) % 360;
    draw(`.file:nth-child(${index + 1}) [data-action="rotate"]`);
    announce(t("rotatedTo", { name: entry.file.name, angle: entry.rotation }));
  }

  function reset() {
    releaseResult();
    closePages();
    Object.assign(state, { files: [], status: "idle", result: null, message: "" });
    if (tool.pagePicker === "select") state.values.pages = "";
    draw();
  }

  async function run() {
    if (!form.reportValidity()) return;
    const locked = state.files.filter((entry) => entry.locked);
    if (locked.length) {
      const opened = await askPasswords(locked, tooBig);
      draw();
      if (!opened) return;
      // Split and Rotate need the pages of the opened file before they can run.
      if (tool.pagePicker) return loadPages(state.files[0]);
    }
    const body = new FormData();
    const fileField = tool.multiple ? "files" : "file";
    for (const entry of state.files) body.append(fileField, entry.file, entry.file.name);
    // The API takes one angle per file, in the same order.
    if (tool.rotatable) body.append("rotations", state.files.map((entry) => entry.rotation).join(","));
    // Rotate takes one angle per page.
    if (tool.pagePicker === "rotate") body.append("rotations", state.angles.join(","));
    for (const field of tool.fields) body.append(field.name, state.values[field.name] ?? "");
    state.status = "working";
    state.message = "";
    draw();
    announce(t("working"));
    try {
      const { blob, name } = await runTool(tool.endpoint, body);
      state.result = { url: URL.createObjectURL(blob), name, blob, inputBytes: totalBytes(), pages: null, thumb: null };
      state.status = "done";
      state.justFinished = true;
      drawThumbnail();
      announce(t("doneTitle"));
    } catch (error) {
      state.status = "error";
      state.message = t(`error.${error instanceof ApiError ? error.code : "ERR_INTERNAL"}`);
    }
    draw();
  }

  function summary() {
    if (!state.files.length) return "";
    if (state.grid) return pageSummary();
    const files = state.files.length === 1 ? t("summaryFile") : t("summaryFiles", { count: state.files.length });
    if (!state.files.every((entry) => typeof entry.pages === "number")) return files;
    const pages = state.files.reduce((sum, entry) => sum + entry.pages, 0);
    return `${files} · ${t("summaryPages", { count: pages })}`;
  }

  function pageSummary() {
    const total = state.doc.count;
    if (tool.pagePicker === "select") {
      const count = state.selected.size;
      return count ? t("pagesPicked", { count, total }) : t("pagesNone");
    }
    const count = state.angles.filter((angle) => angle !== 0).length;
    if (!count) return t("pagesUnchanged");
    return count === 1 ? t("pageTurned", { total }) : t("pagesTurned", { count, total });
  }
}

function defaults(tool) {
  const values = {};
  for (const field of tool.fields) {
    if (field.value !== undefined) values[field.name] = String(field.value);
    else if (field.type === "select") values[field.name] = field.options[0][0];
  }
  return values;
}

function selectFor(field) {
  const select = document.createElement("select");
  for (const [value, text] of field.options) select.append(new Option(t(text), value));
  return select;
}

function previewIcon(result) {
  const name = result.name.toLowerCase();
  if (result.locked) return "lock-simple";
  if (name.endsWith(".zip")) return "file-zip";
  if (name.endsWith(".docx")) return "file-doc";
  return "file-pdf";
}

function resultMeta(result) {
  const parts = [];
  if (typeof result.pages === "number") parts.push(result.pages === 1 ? t("page") : t("pages", { count: result.pages }));
  parts.push(`${formatSize(result.inputBytes)} → ${formatSize(result.blob.size)}`);
  const saved = Math.round((1 - result.blob.size / result.inputBytes) * 100);
  if (saved > 0) parts.push(t("smaller", { percent: saved }));
  return parts.join(" · ");
}

// A check drawn as one stroke (frontend/icons/check-draw.svg); CSS draws it in.
function checkMark() {
  const mark = icon("check-draw", 16);
  mark.classList.add("check-draw");
  return mark;
}

function kindIcon(file) {
  const name = file.name.toLowerCase();
  if (name.endsWith(".pdf")) return "file-pdf";
  if (name.endsWith(".docx")) return "file-doc";
  return "image";
}

function fileMeta(entry) {
  const parts = [formatSize(entry.file.size)];
  if (entry.locked) parts.unshift(t("lockedMeta"));
  if (typeof entry.pages === "number") parts.unshift(entry.pages === 1 ? t("page") : t("pages", { count: entry.pages }));
  if (entry.rotation) parts.push(t("rotated", { angle: entry.rotation }));
  return parts.join(" · ");
}

function formatSize(bytes) {
  const format = (value) => value.toLocaleString(document.documentElement.lang, { maximumFractionDigits: 1 });
  if (bytes < 1024 * 1024) return `${format(bytes / 1024)} KB`;
  return `${format(bytes / 1024 / 1024)} MB`;
}

function percent(value) {
  return `${Math.round(Number(value) * 100)} %`;
}

function iconButton(name, label, onClick, disabled, action) {
  const button = el("button", "icon-button");
  button.type = "button";
  button.dataset.action = action;
  button.setAttribute("aria-label", label);
  button.title = label;
  button.disabled = disabled;
  button.append(icon(name, 16));
  button.addEventListener("click", onClick);
  return button;
}

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}
