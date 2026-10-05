// Applies the saved (or system) colour theme before the first paint, so the page never flashes the wrong theme.
// Kept as a same-origin file rather than an inline <script>, so the Content-Security-Policy can forbid inline scripts.
try {
  var t = localStorage.getItem("ek-theme");
  if (t === "dark" || (!t && window.matchMedia("(prefers-color-scheme: dark)").matches)) {
    document.documentElement.classList.add("dark");
  }
} catch (e) {
  /* storage blocked: keep the light theme */
}
