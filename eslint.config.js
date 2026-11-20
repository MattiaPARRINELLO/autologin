import js from "@eslint/js";
import globals from "globals";

export default [
  {
    ignores: ["eslint.config.js", "node_modules/**", "ui/**", "watcher/**", "emulator/**"],
  },
  js.configs.recommended,
  {
    files: ["*.js"],
    languageOptions: {
      ecmaVersion: 2022,
      sourceType: "module",
      globals: {
        ...globals.browser,
        ...globals.webextensions,
        chrome: "readonly",
        browser: "readonly",
      },
    },
    rules: {
      "no-unused-vars": [
        "warn",
        {
          argsIgnorePattern: "^_",
          caughtErrors: "none",
          ignoreRestSiblings: true,
        },
      ],
      "no-empty": ["error", { allowEmptyCatch: true }],
    },
  },
];
