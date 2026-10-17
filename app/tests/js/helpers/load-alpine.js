/**
 * Test loader for skuel.js under the REAL vendored Alpine.
 *
 * load-skuel.js records Alpine.data() factories on a stub, which tests a
 * component's methods but cannot see its markup: which element holds x-data,
 * what an extra x-init does, whether a directive outside the scope binds.
 * This helper evaluates skuel.js and then the vendored Alpine build into the
 * current jsdom document. Alpine starts on a microtask, dispatches
 * 'alpine:init' (skuel.js registers its components there) and from then on
 * mounts any x-data tree inserted into the document through its
 * MutationObserver, the way an HTMX swap reaches it. Call it once per test
 * file: Alpine cannot be started twice in one document.
 *
 * Usage:
 *   const Alpine = await loadAlpine();
 *   document.body.insertAdjacentHTML('beforeend', fixture('relationship-graph.html'));
 *   await settle();
 */
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const APP_ROOT = join(dirname(fileURLToPath(import.meta.url)), '..', '..', '..');
const SKUEL_JS = readFileSync(join(APP_ROOT, 'static', 'js', 'skuel.js'), 'utf8');
const ALPINE_JS = readFileSync(
  join(APP_ROOT, 'static', 'vendor', 'alpinejs', 'alpine.3.14.8.min.js'),
  'utf8',
);

/** The Python-rendered markup under tests/js/fixtures/ (drift-pinned by pytest). */
export function fixture(name) {
  return readFileSync(join(APP_ROOT, 'tests', 'js', 'fixtures', name), 'utf8');
}

/** Let Alpine's MutationObserver, effects and pending fetch promises run. */
export function settle() {
  return new Promise((resolve) => setTimeout(resolve, 0));
}

export async function loadAlpine() {
  new Function(SKUEL_JS)();
  document.dispatchEvent(new Event('DOMContentLoaded', { bubbles: true }));
  new Function(ALPINE_JS)();
  await settle();
  return window.Alpine;
}
