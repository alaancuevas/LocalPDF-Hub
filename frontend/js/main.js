import { language, readPreference, setPreference, t } from "./i18n.js";
import { icon } from "./icons.js";
import { fadeIn, measure, slide } from "./motion.js";
import { readTheme, setTheme } from "./theme.js";
import { GROUPS, TOOLS } from "./tools.js";
import { renderTool } from "./view.js";

const sidebarList = document.querySelector("#tool-list");
const picker = document.querySelector("#tool-picker");
const work = document.querySelector("#work");
const announcer = document.querySelector("#announcer");
const settings = document.querySelector("#settings");

function currentTool() {
  const id = location.hash.slice(1);
  return id in TOOLS ? id : "merge";
}

function announce(text) {
  // Clearing first makes screen readers repeat an identical message.
  announcer.textContent = "";
  requestAnimationFrame(() => {
    announcer.textContent = text;
  });
}

function renderChrome() {
  document.title = t("appName");
  document.querySelectorAll("[data-i18n]").forEach((node) => {
    node.textContent = t(node.dataset.i18n);
  });
  document.querySelectorAll("[data-i18n-label]").forEach((node) => {
    node.setAttribute("aria-label", t(node.dataset.i18nLabel));
  });

  const active = currentTool();
  sidebarList.replaceChildren();
  picker.replaceChildren();
  for (const group of GROUPS) {
    const heading = document.createElement("li");
    heading.className = "group-label";
    heading.textContent = t(group.label);
    sidebarList.append(heading);
    const optgroup = document.createElement("optgroup");
    optgroup.label = t(group.label);
    for (const id of group.tools) {
      const link = document.createElement("a");
      link.className = "tool";
      link.href = `#${id}`;
      link.append(icon(TOOLS[id].icon), document.createTextNode(t(`short.${id}`)));
      if (id === active) {
        link.setAttribute("aria-current", "page");
        const bar = document.createElement("span");
        bar.className = "tool-bar";
        bar.setAttribute("aria-hidden", "true");
        link.prepend(bar);
      }
      const item = document.createElement("li");
      item.append(link);
      sidebarList.append(item);
      optgroup.append(new Option(t(`short.${id}`), id, false, id === active));
    }
    picker.append(optgroup);
  }
}

let view;
// A result passed on with "Continue with…", picked up by the next tool once.
let handover = null;

function show({ initial = false } = {}) {
  const id = currentTool();
  // The selection bar slides from the old tool to the new one; nothing moves on page load.
  const before = measure([["bar", sidebarList.querySelector(".tool-bar")]]);
  renderChrome();
  if (!initial) slide(before, [["bar", sidebarList.querySelector(".tool-bar")]]);
  // Frees the open PDF and the result of the tool being left.
  view?.destroy();
  const files = handover?.id === id ? [handover.file] : [];
  handover = null;
  view = renderTool(work, id, TOOLS[id], announce, { files, onContinue });
  if (!initial) fadeIn(work);
}

function onContinue(id, file) {
  handover = { id, file };
  location.hash = id;
}

picker.addEventListener("change", () => {
  location.hash = picker.value;
});
window.addEventListener("hashchange", () => show());

for (const button of document.querySelectorAll("[data-open-settings]")) {
  button.addEventListener("click", () => {
    settings.querySelector("#setting-language").value = readPreference();
    settings.querySelector("#setting-theme").value = readTheme();
    settings.showModal();
  });
}
settings.querySelector("#setting-language").addEventListener("change", (event) => {
  setPreference(event.target.value);
  renderChrome();
  view.redraw();
});
settings.querySelector("#setting-theme").addEventListener("change", (event) => {
  setTheme(event.target.value);
});

document.documentElement.lang = language();
show({ initial: true });
