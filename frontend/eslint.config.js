import js from "@eslint/js";
import globals from "globals";
import reactHooks from "eslint-plugin-react-hooks";
import reactRefresh from "eslint-plugin-react-refresh";

export default [
  { ignores: ["dist", "playwright-report", "test-results"] },
  {
    files: ["**/*.{js,jsx}"],
    languageOptions: { ecmaVersion: "latest", globals: globals.browser, parserOptions: { ecmaFeatures: { jsx: true }, sourceType: "module" } },
    plugins: { "react-hooks": reactHooks, "react-refresh": reactRefresh },
    rules: {
      ...js.configs.recommended.rules,
      ...reactHooks.configs.recommended.rules,
      "no-unused-vars": ["warn", { varsIgnorePattern: "^[A-Z_]" }],
      "react-refresh/only-export-components": "off",
    },
  },
  // Config files and Playwright tests run in Node (process.env, etc.).
  { files: ["*.config.js", "e2e/**/*.js"], languageOptions: { globals: { ...globals.node } } },
];
