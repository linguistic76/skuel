/**
 * Rendered-refusal swap pins for static/js/skuel.js.
 *
 * Pins the client half of route_helpers.refuse_not_found: a 404 carrying
 * `X-SKUEL-Refusal: rendered` is opted into the HTMX swap by the parse-time
 * htmx:beforeSwap listener; every other response leaves the swap decision
 * as HTMX made it, and `isError` is never touched. A swap is not a success:
 * the htmx:afterSwap announcer stays silent when `successful` is false, so a
 * swapped refusal from a mutation route never reads as "Status updated".
 */
import { beforeEach, describe, expect, it } from 'vitest';
import { loadSkuel } from './helpers/load-skuel.js';

function fakeXhr(status, headers) {
  return {
    status,
    getResponseHeader(name) {
      return headers[name.toLowerCase()] ?? null;
    },
  };
}

function beforeSwap(xhr, shouldSwap) {
  const event = new CustomEvent('htmx:beforeSwap', {
    detail: { xhr, shouldSwap, isError: xhr.status >= 400 },
  });
  document.dispatchEvent(event);
  return event.detail;
}

describe('htmx:beforeSwap rendered-refusal opt-in', () => {
  beforeEach(() => {
    loadSkuel();
  });

  it('swaps a 404 that carries X-SKUEL-Refusal: rendered', () => {
    const detail = beforeSwap(fakeXhr(404, { 'x-skuel-refusal': 'rendered' }), false);
    expect(detail.shouldSwap).toBe(true);
    expect(detail.isError).toBe(true);
  });

  it('leaves a plain 404 unswapped', () => {
    const detail = beforeSwap(fakeXhr(404, {}), false);
    expect(detail.shouldSwap).toBe(false);
    expect(detail.isError).toBe(true);
  });

  it('ignores the header on any other status', () => {
    expect(beforeSwap(fakeXhr(403, { 'x-skuel-refusal': 'rendered' }), false).shouldSwap).toBe(false);
    expect(beforeSwap(fakeXhr(200, { 'x-skuel-refusal': 'rendered' }), true).shouldSwap).toBe(true);
  });

  it('survives a missing xhr', () => {
    const event = new CustomEvent('htmx:beforeSwap', { detail: { shouldSwap: false, isError: false } });
    document.dispatchEvent(event);
    expect(event.detail.shouldSwap).toBe(false);
  });
});

describe('htmx:afterSwap on a swapped refusal', () => {
  beforeEach(() => {
    document.body.innerHTML = '<div id="live-region"></div><div id="card"></div>';
    loadSkuel();
  });

  function afterSwap(successful) {
    const target = document.getElementById('card');
    const event = new CustomEvent('htmx:afterSwap', {
      bubbles: true,
      detail: {
        target,
        elt: target,
        successful,
        requestConfig: { verb: 'post', path: '/api/tasks/task_1/status' },
      },
    });
    target.setAttribute('aria-busy', 'true');
    target.dispatchEvent(event);
    return document.getElementById('live-region').textContent;
  }

  it('announces the mutation on a successful swap', () => {
    expect(afterSwap(true)).toBe('Status updated');
  });

  it('stays silent on a swapped refusal, but still clears aria-busy', () => {
    expect(afterSwap(false)).toBe('');
    expect(document.getElementById('card').getAttribute('aria-busy')).toBe('false');
  });
});
