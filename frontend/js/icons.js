// Icons come from one SVG sprite built by scripts/vendor.mjs (Phosphor plus
// our own glyphs), so the page never loads an icon it does not use.
const SPRITE = "libs/icons.svg";
const SVG = "http://www.w3.org/2000/svg";

export function icon(name, size = 20) {
  const svg = document.createElementNS(SVG, "svg");
  const sizes = { 16: "icon icon-sm", 32: "icon icon-lg" };
  svg.setAttribute("class", sizes[size] ?? "icon");
  svg.setAttribute("aria-hidden", "true");
  const use = document.createElementNS(SVG, "use");
  use.setAttribute("href", `${SPRITE}#${name}`);
  svg.append(use);
  return svg;
}
