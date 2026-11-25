/**
 * The PathStep page's hero card, mounted by the real vendored Alpine on the markup the Python
 * renders (tests/js/fixtures/ps-hero-states.html, drift-pinned by
 * tests/unit/ui/test_ps_hero_states.py), with static/js/ps-detail.js as its component.
 *
 * Completed is mastered. A step marked as read is its own state, short of completion: its
 * label is Read and the progress track stops short of full. The state word lives in the
 * Python seed, the x-show expressions and the bundle's progressPct getter, and only a run
 * joins them. A step not yet started waits on its prerequisite chain: while a row of the
 * seed's `blocking` is not completed, Start learning is disabled and counts what is left.
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
  host.innerHTML = fixture('ps-hero-states.html');
  document.body.appendChild(host);
  return host;
}

function shown(element) {
  return element.style.display !== 'none';
}

/** The visible status labels, by their text. */
function visibleLabels(host) {
  const labels = host.querySelector('.flex.items-center.gap-2').children;
  return [...labels].filter(shown).map((label) => label.textContent.trim());
}

function track(host) {
  return host.querySelector('[role="progressbar"]').firstElementChild.style.width;
}

function button(host, text) {
  return [...host.querySelectorAll('button')].find((b) => b.textContent.includes(text));
}

function buttonShown(host, text) {
  const found = button(host, text);
  return found !== undefined && shown(found);
}

/** The primary action, whatever its label reads. */
function primary(host) {
  return host.querySelector('[\\@click="advance()"]');
}

async function inState(host, status) {
  await settle();
  Alpine.$data(host.querySelector('[x-data]')).status = status;
  // x-show applies a change on the next animation frame.
  await new Promise((resolve) => requestAnimationFrame(() => setTimeout(resolve, 0)));
}

beforeAll(async () => {
  new Function(PS_DETAIL_JS)();
  Alpine = await loadAlpine();
});

afterEach(() => {
  document.body.replaceChildren();
});

describe('PathStep hero card', () => {
  it('shows a mastered step as Completed with a full track', async () => {
    const host = mount();
    await settle();

    expect(visibleLabels(host)).toEqual(['Completed']);
    expect(track(host)).toBe('100%');
    // Mastery retired the in-progress hold Review again returns to.
    expect(buttonShown(host, 'Review again')).toBe(false);
    expect(shown(primary(host))).toBe(false);
  });

  it('shows a step marked as read as Read, short of a full track', async () => {
    const host = mount();
    await inState(host, 'read');

    expect(visibleLabels(host)).toEqual(['Read']);
    expect(track(host)).toBe('80%');
    expect(buttonShown(host, 'Review again')).toBe(true);
    expect(buttonShown(host, 'Start learning')).toBe(false);
  });

  it('offers Mark as read while learning and Start learning before', async () => {
    const host = mount();

    await inState(host, 'learning');
    expect(visibleLabels(host)).toEqual(['Learning']);
    expect(track(host)).toBe('55%');
    expect(buttonShown(host, 'Mark as read')).toBe(true);
    expect(buttonShown(host, 'Review again')).toBe(false);

    await inState(host, 'not_started');
    Alpine.$data(host.querySelector('[x-data]')).blocking = [];
    await inState(host, 'not_started');
    expect(visibleLabels(host)).toEqual(['Not started']);
    expect(track(host)).toBe('0%');
    expect(buttonShown(host, 'Start learning')).toBe(true);
    expect(primary(host).disabled).toBe(false);
  });

  it('disables Start learning while a prerequisite is unmastered, counting what is left', async () => {
    const host = mount();
    await inState(host, 'not_started');

    expect(shown(primary(host))).toBe(true);
    expect(primary(host).disabled).toBe(true);
    expect(primary(host).textContent.trim()).toBe('1 prerequisite to clear');
  });

  it('lets a step already in progress be marked as read, whatever blocks a new start', async () => {
    const host = mount();
    await inState(host, 'learning');

    expect(primary(host).disabled).toBe(false);
    expect(primary(host).textContent.trim()).toBe('Mark as read');
  });
});
