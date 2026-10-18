// Thumbnails of one PDF's pages: pick pages (Split) or turn each one (Rotate).
// The grid outlives redraws of the work area, so drawn thumbnails are kept.

import { t } from "./i18n.js";
import { icon } from "./icons.js";
import { fadeIn } from "./motion.js";

export function pageGrid({ mode, doc, state, onChange }) {
  const section = el("section", "pages");
  const head = el("div", "pages-head");
  const label = el("p", "pages-label");
  head.append(label);

  let hint;
  let reset;
  let turnAll;
  if (mode === "select") {
    hint = el("p", "pages-hint");
    head.append(hint);
  } else {
    reset = el("button", "link pages-reset");
    reset.type = "button";
    reset.addEventListener("click", () => {
      state.angles.fill(0);
      changed();
    });
    turnAll = el("button", "secondary pages-turn-all");
    turnAll.type = "button";
    turnAll.addEventListener("click", () => {
      state.angles.forEach((angle, index) => {
        state.angles[index] = (angle + 90) % 360;
      });
      changed();
    });
    head.append(reset, turnAll);
  }

  const grid = el("ul", "page-grid");
  const cards = [];
  for (let number = 1; number <= doc.count; number++) cards.push(card(number));
  grid.append(...cards.map((entry) => entry.item));
  section.append(head, grid);

  // Pages are drawn only when they scroll near the screen.
  const observer = new IntersectionObserver(
    (entries) => {
      for (const entry of entries) {
        if (!entry.isIntersecting) continue;
        observer.unobserve(entry.target);
        drawThumbnail(cards[Number(entry.target.dataset.page) - 1]);
      }
    },
    { rootMargin: "200px" },
  );
  for (const entry of cards) observer.observe(entry.cell);
  sync();

  return { element: section, sync, destroy: () => observer.disconnect() };

  function card(number) {
    const item = el("li", "");
    const cell = el("span", "page-cell");
    cell.dataset.page = String(number);
    const sheet = el("span", "sheet-wrap");
    sheet.append(el("span", "sheet sheet-placeholder"));
    cell.append(sheet);
    const entry = { number, item, cell, sheet };

    if (mode === "select") {
      const button = el("button", "page");
      button.type = "button";
      const check = el("span", "page-check");
      check.append(icon("check", 16));
      sheet.append(check);
      button.append(cell, el("span", "page-number", String(number)));
      button.addEventListener("click", (event) => pick(number, event.shiftKey));
      item.append(button);
      entry.button = button;
    } else {
      const page = el("div", "page");
      const turn = el("button", "icon-button page-turn");
      turn.type = "button";
      const angle = el("span", "page-angle");
      turn.append(icon("arrow-clockwise", 16), angle);
      turn.addEventListener("click", () => {
        state.angles[number - 1] = (state.angles[number - 1] + 90) % 360;
        changed();
      });
      const foot = el("span", "page-foot");
      foot.append(el("span", "page-number", String(number)), turn);
      page.append(cell, foot);
      item.append(page);
      Object.assign(entry, { button: turn, angle });
    }
    return entry;
  }

  function drawThumbnail(entry) {
    const box = entry.cell.clientWidth;
    const canvas = document.createElement("canvas");
    canvas.className = "sheet";
    canvas.setAttribute("aria-hidden", "true");
    doc.draw(entry.number, canvas, box).then(() => {
      const placeholder = entry.sheet.querySelector(".sheet-placeholder");
      if (canvas.width && placeholder) {
        placeholder.replaceWith(canvas);
        fadeIn(canvas, 200);
      }
    });
  }

  function pick(number, range) {
    if (range && state.anchor) {
      const [first, last] = [Math.min(state.anchor, number), Math.max(state.anchor, number)];
      for (let page = first; page <= last; page++) state.selected.add(page);
    } else if (state.selected.has(number)) {
      state.selected.delete(number);
    } else {
      state.selected.add(number);
    }
    state.anchor = number;
    changed();
  }

  function changed() {
    sync();
    onChange();
  }

  /** Brings every card and text in line with the state (also after a language change). */
  function sync() {
    label.textContent = t("pagesLabel");
    if (mode === "select") {
      hint.textContent = t("pagesHint");
      for (const entry of cards) {
        const on = state.selected.has(entry.number);
        entry.button.setAttribute("aria-pressed", String(on));
        entry.button.setAttribute("aria-label", t("pageLabel", { number: entry.number }));
      }
      return;
    }
    reset.textContent = t("resetRotation");
    reset.hidden = state.angles.every((angle) => angle === 0);
    turnAll.replaceChildren(icon("arrow-clockwise", 16), document.createTextNode(t("rotateAll")));
    for (const entry of cards) {
      const angle = state.angles[entry.number - 1];
      entry.sheet.style.transform = angle ? `rotate(${angle}deg)` : "";
      entry.sheet.classList.toggle("is-turned", angle !== 0);
      entry.button.classList.toggle("is-turned", angle !== 0);
      entry.angle.textContent = angle ? `${angle}°` : "";
      const name = angle ? "rotatePageNow" : "rotatePage";
      const text = t(name, { number: entry.number, angle });
      entry.button.setAttribute("aria-label", text);
      entry.button.title = text;
    }
  }
}

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}
