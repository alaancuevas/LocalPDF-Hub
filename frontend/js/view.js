// The work area of one tool: files in, options, run, result out.

import { ApiError, runTool } from "./api.js";
import { t } from "./i18n.js";
import { icon } from "./icons.js";
import { pageCount } from "./pages.js";
import { accepts } from "./tools.js";

const MAX_BYTES = 500 * 1024 * 1024;

export function renderTool(root, id, tool, announce) {
  const state = { files: [], values: defaults(tool), status: "idle", result: null, message: "" };
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
  });
  root.replaceChildren(form);
  draw();
  // Lets a language change redraw the texts without dropping the files.
  return { redraw: () => draw() };

  function draw(focusSelector) {
    form.replaceChildren(header(), body(), footer());
    if (focusSelector) form.querySelector(focusSelector)?.focus();
  }

  function header() {
    const head = el("header", "work-head");
    head.append(el("h1", "", t(`${id}.title`)), el("p", "lede", t(`${id}.lede`)));
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
      const row = el("li", "file");
      entry.meta = el("span", "meta", fileMeta(entry));
      row.append(icon(kindIcon(entry.file)), el("span", "file-name", entry.file.name), entry.meta);

      const actions = el("span", "row-actions");
      if (tool.multiple && state.files.length > 1) {
        actions.append(
          iconButton("caret-up", t("moveUp"), () => move(index, -1), index === 0, "up"),
          iconButton("caret-down", t("moveDown"), () => move(index, 1), index === state.files.length - 1, "down"),
        );
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
    const primary = el("button", "primary", working ? t("working") : t(`${id}.action`));
    primary.type = "submit";
    primary.disabled = !state.files.length || working;
    foot.append(primary);
    return foot;
  }

  function resultPanel() {
    const panel = el("div", "result");
    panel.append(el("p", "result-title", t("doneTitle")));
    const link = el("a", "primary", t("download", { name: state.result.name }));
    link.href = state.result.url;
    link.download = state.result.name;
    const again = el("button", "secondary", t("again"));
    again.type = "button";
    again.addEventListener("click", reset);
    const actions = el("div", "result-actions");
    actions.append(link, again);
    panel.append(actions);
    queueMicrotask(() => link.focus());
    return panel;
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
      const entry = { file, pages: undefined, meta: null };
      if (tool.multiple) {
        state.files.push(entry);
      } else {
        if (state.files.length) state.message = t("onlyOne");
        state.files = [entry];
      }
      // Counting pages can take a moment; only the affected texts are updated.
      pageCount(file).then((pages) => {
        entry.pages = pages;
        if (entry.meta) entry.meta.textContent = fileMeta(entry);
        if (state.summary) state.summary.textContent = summary();
      });
    }
    draw();
  }

  function removeFile(index) {
    state.files.splice(index, 1);
    draw();
  }

  function move(index, step) {
    const [entry] = state.files.splice(index, 1);
    const target = index + step;
    state.files.splice(target, 0, entry);
    const edge = target === 0 || target === state.files.length - 1;
    // Keep focus on the moved row so the keyboard user can keep moving it.
    const action = step < 0 ? (edge ? "down" : "up") : edge ? "up" : "down";
    draw(`.file:nth-child(${target + 1}) [data-action="${action}"]`);
  }

  function reset() {
    if (state.result) URL.revokeObjectURL(state.result.url);
    Object.assign(state, { files: [], status: "idle", result: null, message: "" });
    draw();
  }

  async function run() {
    if (!form.reportValidity()) return;
    const body = new FormData();
    const fileField = tool.multiple ? "files" : "file";
    for (const entry of state.files) body.append(fileField, entry.file, entry.file.name);
    for (const field of tool.fields) {
      const value = state.values[field.name] ?? "";
      if (field.name === "angle") {
        // The API takes one angle per page.
        const pages = state.files[0].pages ?? 1;
        body.append("rotations", Array(pages).fill(value).join(","));
      } else {
        body.append(field.name, value);
      }
    }
    state.status = "working";
    state.message = "";
    draw();
    announce(t("working"));
    try {
      const { blob, name } = await runTool(tool.endpoint, body);
      state.result = { url: URL.createObjectURL(blob), name };
      state.status = "done";
      announce(t("doneTitle"));
    } catch (error) {
      state.status = "error";
      state.message = t(`error.${error instanceof ApiError ? error.code : "ERR_INTERNAL"}`);
    }
    draw();
  }

  function summary() {
    if (!state.files.length) return "";
    const files = state.files.length === 1 ? t("summaryFile") : t("summaryFiles", { count: state.files.length });
    if (!state.files.every((entry) => typeof entry.pages === "number")) return files;
    const pages = state.files.reduce((sum, entry) => sum + entry.pages, 0);
    return `${files} · ${t("summaryPages", { count: pages })}`;
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

function kindIcon(file) {
  const name = file.name.toLowerCase();
  if (name.endsWith(".pdf")) return "file-pdf";
  if (name.endsWith(".docx")) return "file-doc";
  return "image";
}

function fileMeta(entry) {
  const size = formatSize(entry.file.size);
  if (typeof entry.pages !== "number") return size;
  const pages = entry.pages === 1 ? t("page") : t("pages", { count: entry.pages });
  return `${pages} · ${size}`;
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
