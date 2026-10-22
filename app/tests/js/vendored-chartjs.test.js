/**
 * The Chart.js the browser runs is static/vendor/chart.js/chart.umd.js, a copy
 * `npm run vendor:copy` makes from node_modules. Its URL carries no version, so
 * the precache pin (tests/unit/ui/test_vendored_asset_pins.py) cannot see it: a
 * lockfile bump that skips the re-copy leaves the browser on the old library
 * while package-lock.json names the new one. This test holds the two together.
 *
 * Fix a failure with `npm run vendor:copy`, commit the vendored file, and bump
 * CACHE_VERSION in static/service-worker.js (cacheFirst serves the stale copy to
 * every installed client until the cache key changes).
 */
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { expect, it } from 'vitest';

const APP_ROOT = join(dirname(fileURLToPath(import.meta.url)), '..', '..');

function read(relativePath) {
  return readFileSync(join(APP_ROOT, relativePath), 'utf8');
}

it('the vendored chart.umd.js is the Chart.js package-lock.json locks', () => {
  const lock = JSON.parse(read('package-lock.json'));
  const locked = lock.packages['node_modules/chart.js']?.version;
  expect(locked, 'chart.js missing from package-lock.json').toMatch(/^\d+\.\d+\.\d+$/);

  const banner = read('static/vendor/chart.js/chart.umd.js').slice(0, 200);
  const vendored = banner.match(/Chart\.js v(\d+\.\d+\.\d+)/)?.[1];
  expect(vendored, 'no "Chart.js vX.Y.Z" banner in the vendored file').toBeDefined();

  expect(vendored).toBe(locked);
});
