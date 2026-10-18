import en from "./locales/en.js";
import es from "./locales/es.js";

const LOCALES = { en, es };
const STORAGE_KEY = "language";

let current = resolve(readPreference());

export function readPreference() {
  try {
    return localStorage.getItem(STORAGE_KEY) || "auto";
  } catch {
    return "auto";
  }
}

export function setPreference(value) {
  try {
    localStorage.setItem(STORAGE_KEY, value);
  } catch {
    // Private windows can refuse storage; the choice then lasts until reload.
  }
  current = resolve(value);
  document.documentElement.lang = current;
}

export function language() {
  return current;
}

export function t(key, vars = {}) {
  const text = LOCALES[current][key] ?? LOCALES.en[key] ?? key;
  return text.replace(/\{(\w+)\}/g, (_, name) => String(vars[name] ?? ""));
}

function resolve(preference) {
  if (preference in LOCALES) return preference;
  return navigator.language?.toLowerCase().startsWith("es") ? "es" : "en";
}

document.documentElement.lang = current;
