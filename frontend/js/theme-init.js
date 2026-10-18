// Loaded as a classic script in <head>, before the CSS paints, so a dark
// preference never flashes light. Not inline, so the CSP can forbid inline scripts.
try {
  const theme = localStorage.getItem("theme");
  if (theme === "light" || theme === "dark") document.documentElement.dataset.theme = theme;
} catch {}
