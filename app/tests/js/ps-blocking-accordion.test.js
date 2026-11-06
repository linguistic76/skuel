/**
 * The PathStep page's "Blocking dependencies" accordion, mounted by the real vendored Alpine
 * on the markup the Python renders (tests/js/fixtures/ps-blocking-accordion.html, drift-pinned
 * by tests/unit/ui/test_ps_blocking_seed.py), with static/js/ps-detail.js as its component.
 *
 * Pins what the server-side pins cannot see: the status word in the Python seed, the same word
 * in the x-show expressions, and the same word in the page bundle's getters must agree. They
 * live in three places and nothing but a run joins them. A mismatch shows every prerequisite
 * as Blocked and fails no Python test.
 */
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { afterEach, beforeAll, describe, expect, it } from 'vitest';
import { fixture, loadAlpine, settle } from './helpers/load-alpine.js';

const PS_DETAIL_JS = readFileSync(
  join(dirname(fileURLToPath(import.meta.url)), '..', '..', 'static', 'js', 'ps-detail.js'),
  'utf8',
);

let Alpine;

function mount() {
  const host = document.createElement('div');
  host.innerHTML = fixture('ps-blocking-accordion.html');
  document.body.appendChild(host);
  return host;
}

function shown(element) {
  return element.style.display !== 'none';
}

function rowFor(host, title) {
  return [...host.querySelectorAll('li')].find((row) => row.textContent.includes(title));
}

function summary(host) {
  return host.querySelector('#deps-h').nextElementSibling.textContent;
}

beforeAll(async () => {
  new Function(PS_DETAIL_JS)();
  Alpine = await loadAlpine();
});

afterEach(() => {
  document.body.replaceChildren();
});

describe('Blocking dependencies', () => {
  it('reads each row by the status the Python seed sent', async () => {
    const host = mount();
    await settle();

    expect(rowFor(host, 'Done first').textContent).toContain('Completed');
    expect(rowFor(host, 'Still open').textContent).toContain('Blocked');
  });

  it('shows the tick on a completed row and the lock on a blocked one', async () => {
    const host = mount();
    await settle();

    const [doneTick, doneLock] = rowFor(host, 'Done first').querySelectorAll(':scope > span');
    const [openTick, openLock] = rowFor(host, 'Still open').querySelectorAll(':scope > span');
    expect([shown(doneTick), shown(doneLock)]).toEqual([true, false]);
    expect([shown(openTick), shown(openLock)]).toEqual([false, true]);
  });

  it('counts what is left to clear', async () => {
    const host = mount();
    await settle();

    expect(summary(host)).toBe('1 prerequisite to clear');
  });

  it('says nothing blocks the step once every row is completed', async () => {
    const host = mount();
    await settle();

    const component = Alpine.$data(host.querySelector('[x-data]'));
    component.blocking = component.blocking.map((row) => ({ ...row, status: 'completed' }));
    await settle();

    expect(summary(host)).toBe('Ready — nothing blocks this step.');
  });
});
