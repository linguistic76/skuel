/**
 * Test loader for static/js/skuel.js (browser IIFE, no modules).
 *
 * skuel.js expects a browser: it installs window.SKUEL helpers and
 * document-level listeners at parse time, then registers 26 Alpine.data()
 * components inside an 'alpine:init' listener. This helper evaluates the real
 * file inside the jsdom environment with a minimal recording Alpine stub, so
 * tests can instantiate component factories as plain objects and drive their
 * methods directly.
 *
 * Usage:
 *   const skuel = loadSkuel();
 *   const component = skuel.make('collapsible', true);
 *   component.toggle();
 */
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const SKUEL_JS_PATH = join(
  dirname(fileURLToPath(import.meta.url)),
  '..', '..', '..', 'static', 'js', 'skuel.js',
);

const source = readFileSync(SKUEL_JS_PATH, 'utf8');

/**
 * Minimal Alpine stand-in: records Alpine.data() factories and provides a
 * real enough Alpine.store() for components that share state through stores.
 */
function makeAlpineStub() {
  const registry = new Map();
  const stores = new Map();
  return {
    data(name, factory) {
      registry.set(name, factory);
    },
    store(name, value) {
      if (arguments.length === 2) {
        stores.set(name, value);
        return value;
      }
      return stores.get(name);
    },
    _registry: registry,
    _stores: stores,
  };
}

/**
 * Evaluate skuel.js against the current jsdom globals and fire the lifecycle
 * events it listens for. Returns accessors for the recorded components.
 */
export function loadSkuel() {
  const alpine = makeAlpineStub();
  window.Alpine = alpine;

  // Evaluate the IIFE against jsdom's window/document globals.
  new Function(source)();

  // Trigger the Alpine.data() registrations and the DOMContentLoaded wiring.
  document.dispatchEvent(new Event('alpine:init'));
  document.dispatchEvent(new Event('DOMContentLoaded', { bubbles: true }));

  return {
    alpine,
    /** Instantiate a registered Alpine.data component as a plain object. */
    make(name, ...args) {
      const factory = alpine._registry.get(name);
      if (!factory) {
        throw new Error(`Alpine component not registered: ${name}`);
      }
      return factory(...args);
    },
    /** True when the component name was registered on alpine:init. */
    has(name) {
      return alpine._registry.has(name);
    },
  };
}
