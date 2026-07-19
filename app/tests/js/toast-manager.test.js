/**
 * toastManager Alpine component pins for skuel.js.
 *
 * Pins the toast lifecycle (show/dismiss/auto-dismiss) and the
 * htmx:afterRequest X-Toast header surface — afterRequest, NOT afterSwap,
 * because error responses never swap (the G7 totality find): boundary_handler
 * error toasts must still appear on 4xx/5xx.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { loadSkuel } from './helpers/load-skuel.js';

let skuel;

beforeEach(() => {
  document.body.innerHTML = '';
  skuel = loadSkuel();
  vi.useFakeTimers();
});

afterEach(() => {
  vi.useRealTimers();
});

describe('toast lifecycle', () => {
  it('show defaults to info and auto-dismisses after the duration', () => {
    const component = skuel.make('toastManager');

    component.show('Hello');

    expect(component.toasts).toHaveLength(1);
    expect(component.toasts[0].type).toBe('info');

    vi.advanceTimersByTime(3000);
    expect(component.toasts).toHaveLength(0);
  });

  it('duration 0 keeps the toast until dismissed', () => {
    const component = skuel.make('toastManager');

    component.show('Sticky', 'error', 0);
    vi.advanceTimersByTime(60_000);

    expect(component.toasts).toHaveLength(1);
    component.dismiss(component.toasts[0].id);
    expect(component.toasts).toHaveLength(0);
  });
});

describe('X-Toast header surface', () => {
  function fireAfterRequest(headers) {
    const xhr = {
      getResponseHeader: (name) => headers[name] ?? null,
    };
    document.body.dispatchEvent(
      new CustomEvent('htmx:afterRequest', { bubbles: true, detail: { xhr } }),
    );
  }

  it('surfaces X-Toast-Message with X-Toast-Type', () => {
    const component = skuel.make('toastManager');
    component.init();

    fireAfterRequest({ 'X-Toast-Message': 'Task created', 'X-Toast-Type': 'success' });

    expect(component.toasts).toHaveLength(1);
    expect(component.toasts[0]).toMatchObject({ message: 'Task created', type: 'success' });
  });

  it('error responses also toast (afterRequest, not afterSwap — G7)', () => {
    const component = skuel.make('toastManager');
    component.init();

    fireAfterRequest({ 'X-Toast-Message': 'Ownership check failed', 'X-Toast-Type': 'error' });

    expect(component.toasts[0].type).toBe('error');
  });

  it('stays quiet without a toast header', () => {
    const component = skuel.make('toastManager');
    component.init();

    fireAfterRequest({});

    expect(component.toasts).toHaveLength(0);
  });
});
