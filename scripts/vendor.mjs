// Builds frontend/libs/ from npm packages: pdf.js, the IBM Plex Sans font
// files, and one SVG sprite with the icons the UI uses. The app is served
// offline from disk, so nothing can come from a CDN, and generated files
// stay out of git.
import { copyFileSync, existsSync, mkdirSync, readdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const libs = join(root, "frontend", "libs");
const modules = join(root, "node_modules");

// Phosphor icons in use (regular weight). Our own glyphs live in
// frontend/icons/ and are added under their file name.
export const PHOSPHOR_ICONS = [
  "arrow-clockwise",
  "arrows-in",
  "caret-down",
  "caret-up",
  "drop-half",
  "file-doc",
  "file-pdf",
  "files",
  "gear-six",
  "image",
  "images",
  "lock-simple",
  "lock-simple-open",
  "scissors",
  "upload-simple",
  "x",
];

function copy(source, target) {
  mkdirSync(dirname(target), { recursive: true });
  copyFileSync(source, target);
  console.log(target.slice(root.length + 1));
}

function symbol(id, svg) {
  const viewBox = svg.match(/viewBox="([^"]+)"/)[1];
  const inner = svg.replace(/^[\s\S]*?<svg[^>]*>/, "").replace(/<\/svg>\s*$/, "");
  return `<symbol id="${id}" viewBox="${viewBox}">${inner.trim()}</symbol>`;
}

function buildSprite() {
  const symbols = PHOSPHOR_ICONS.map((name) =>
    symbol(name, readFileSync(join(modules, "@phosphor-icons/core/assets/regular", `${name}.svg`), "utf8")),
  );
  const own = join(root, "frontend", "icons");
  if (existsSync(own)) {
    for (const file of readdirSync(own).filter((name) => name.endsWith(".svg")).sort()) {
      symbols.push(symbol(file.slice(0, -4), readFileSync(join(own, file), "utf8")));
    }
  }
  const sprite = `<svg xmlns="http://www.w3.org/2000/svg">\n${symbols.join("\n")}\n</svg>\n`;
  mkdirSync(libs, { recursive: true });
  writeFileSync(join(libs, "icons.svg"), sprite);
  console.log(`frontend/libs/icons.svg (${symbols.length} icons)`);
}

copy(join(modules, "pdfjs-dist/build/pdf.min.mjs"), join(libs, "pdf.min.mjs"));
copy(join(modules, "pdfjs-dist/build/pdf.worker.min.mjs"), join(libs, "pdf.worker.min.mjs"));
for (const weight of [400, 500, 600]) {
  const file = `ibm-plex-sans-latin-${weight}-normal.woff2`;
  copy(join(modules, "@fontsource/ibm-plex-sans/files", file), join(libs, "fonts", file));
}
buildSprite();
