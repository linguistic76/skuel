/**
 * Test loader for static/js/today.js (browser IIFE, no modules).
 *
 * today.js registers one Alpine.data('today', factory) inside an
 * 'alpine:init' listener and reads window.SEED at instantiation. This helper
 * evaluates the real file against jsdom with a recording Alpine stub, seeds
 * window.SEED, and returns the instantiated component as a plain object with
 * a synchronous $nextTick stub so tests can drive methods directly.
 *
 * Usage:
 *   const c = loadToday(seed());
 *   c.deferTask('ribbon', 't-1', '1d');
 */
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const TODAY_JS_PATH = join(
  dirname(fileURLToPath(import.meta.url)),
  '..', '..', '..', 'static', 'js', 'today.js',
);

const source = readFileSync(TODAY_JS_PATH, 'utf8');

export function loadToday(seed) {
  const registry = new Map();
  window.Alpine = {
    data(name, factory) {
      registry.set(name, factory);
    },
  };
  window.SEED = seed;

  // Evaluate the IIFE against jsdom's window/document globals, then fire the
  // registration lifecycle event it listens for.
  new Function(source)();
  document.dispatchEvent(new Event('alpine:init'));

  const factory = registry.get('today');
  if (!factory) {
    throw new Error('today component was not registered on alpine:init');
  }
  const component = factory();
  // Alpine magic stub: run the callback synchronously — these tests assert
  // state, not DOM scheduling.
  component.$nextTick = (fn) => fn();
  return component;
}
