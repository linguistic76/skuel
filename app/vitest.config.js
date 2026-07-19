import { defineConfig } from 'vitest/config';

// JS test infrastructure for static/js/ (testing-gap roadmap item 6, tranche 3).
// skuel.js is a browser IIFE (no modules), so tests load it via
// tests/js/helpers/load-skuel.js into the jsdom environment with a recording
// Alpine stub. Run with `npm run test:js` (or `./dev test-js`).
export default defineConfig({
  test: {
    environment: 'jsdom',
    include: ['tests/js/**/*.test.js'],
    // Each file gets a fresh jsdom document — skuel.js registers document-level
    // listeners at parse time, so cross-file isolation matters.
    isolate: true,
  },
});
