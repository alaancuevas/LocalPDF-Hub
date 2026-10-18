// "system" leaves data-theme unset so the CSS follows prefers-color-scheme.
const STORAGE_KEY = "theme";

export function readTheme() {
  try {
    return localStorage.getItem(STORAGE_KEY) || "system";
  } catch {
    return "system";
  }
}

export function setTheme(value) {
  try {
    localStorage.setItem(STORAGE_KEY, value);
  } catch {
    // Private windows can refuse storage; the choice then lasts until reload.
  }
  applyTheme(value);
}

export function applyTheme(value) {
  if (value === "light" || value === "dark") document.documentElement.dataset.theme = value;
  else delete document.documentElement.dataset.theme;
}
