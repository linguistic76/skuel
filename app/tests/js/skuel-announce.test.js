/**
 * Screen-reader announcement pins for static/js/skuel.js (SKUEL.announce).
 *
 * Pins the ARIA live-region contract: message + priority land on the
 * #live-region element, stale announcements clear after 3s, and a missing
 * region degrades to a console warning (never a throw).
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { loadSkuel } from './helpers/load-skuel.js';

describe('SKUEL.announce', () => {
  beforeEach(() => {
    document.body.innerHTML = '<div id="live-region"></div>';
    loadSkuel();
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('writes the message with polite priority by default', () => {
    window.SKUEL.announce('Saved');

    const region = document.getElementById('live-region');
    expect(region.textContent).toBe('Saved');
    expect(region.getAttribute('aria-live')).toBe('polite');
  });

  it('honours assertive priority', () => {
    window.SKUEL.announce('Error occurred', 'assertive');

    expect(document.getElementById('live-region').getAttribute('aria-live')).toBe(
      'assertive',
    );
  });

  it('clears the region after 3 seconds', () => {
    window.SKUEL.announce('Temporary');
    expect(document.getElementById('live-region').textContent).toBe('Temporary');

    vi.advanceTimersByTime(3000);

    expect(document.getElementById('live-region').textContent).toBe('');
  });

  it('warns instead of throwing when the region is missing', () => {
    document.body.innerHTML = '';
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {});

    expect(() => window.SKUEL.announce('Nowhere to go')).not.toThrow();
    expect(warn).toHaveBeenCalled();
  });
});
