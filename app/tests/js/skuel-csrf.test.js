/**
 * CSRF double-submit pins for static/js/skuel.js.
 *
 * Pins the client half of adapters/inbound/csrf.py: cookie parsing, the
 * htmx:configRequest header hook (registered at script-parse time so it beats
 * hx-trigger="load" POSTs), and the native-form hidden-input fallback.
 */
import { beforeEach, describe, expect, it } from 'vitest';
import { loadSkuel } from './helpers/load-skuel.js';

function clearCsrfCookie() {
  document.cookie = 'csrf_token=; expires=Thu, 01 Jan 1970 00:00:00 GMT';
}

describe('SKUEL.csrf cookie parsing', () => {
  beforeEach(() => {
    clearCsrfCookie();
    loadSkuel();
  });

  it('returns empty string when the cookie is absent', () => {
    expect(window.SKUEL.csrf()).toBe('');
  });

  it('returns the decoded token when present', () => {
    document.cookie = 'csrf_token=abc%3D123';
    expect(window.SKUEL.csrf()).toBe('abc=123');
  });
});

describe('htmx:configRequest header hook', () => {
  beforeEach(() => {
    clearCsrfCookie();
    loadSkuel();
  });

  function configRequest(verb) {
    const event = new CustomEvent('htmx:configRequest', {
      detail: { verb, headers: {} },
    });
    document.dispatchEvent(event);
    return event.detail.headers;
  }

  it('attaches X-CSRF-Token on mutating verbs', () => {
    document.cookie = 'csrf_token=tok1';
    expect(configRequest('post')['X-CSRF-Token']).toBe('tok1');
    expect(configRequest('delete')['X-CSRF-Token']).toBe('tok1');
  });

  it('leaves safe verbs alone', () => {
    document.cookie = 'csrf_token=tok1';
    expect(configRequest('get')).toEqual({});
    expect(configRequest('head')).toEqual({});
  });

  it('does nothing without a cookie', () => {
    expect(configRequest('post')).toEqual({});
  });
});

describe('native form hidden-input fallback', () => {
  beforeEach(() => {
    document.body.innerHTML = '';
    clearCsrfCookie();
    loadSkuel();
  });

  function submitForm(form) {
    // jsdom would actually "submit"; cancel at the end of the capture chain.
    form.addEventListener('submit', (e) => e.preventDefault());
    form.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }));
  }

  it('injects csrf_token into plain POST forms', () => {
    document.cookie = 'csrf_token=tok2';
    const form = document.createElement('form');
    form.method = 'post';
    document.body.appendChild(form);

    submitForm(form);

    const input = form.querySelector('input[name="csrf_token"]');
    expect(input).not.toBeNull();
    expect(input.value).toBe('tok2');
  });

  it('refreshes an existing hidden input instead of duplicating', () => {
    document.cookie = 'csrf_token=fresh';
    const form = document.createElement('form');
    form.method = 'post';
    form.innerHTML = '<input type="hidden" name="csrf_token" value="stale">';
    document.body.appendChild(form);

    submitForm(form);

    const inputs = form.querySelectorAll('input[name="csrf_token"]');
    expect(inputs).toHaveLength(1);
    expect(inputs[0].value).toBe('fresh');
  });

  it('leaves HTMX-managed forms alone (header hook owns those)', () => {
    document.cookie = 'csrf_token=tok3';
    const form = document.createElement('form');
    form.method = 'post';
    form.setAttribute('hx-post', '/api/x');
    document.body.appendChild(form);

    submitForm(form);

    expect(form.querySelector('input[name="csrf_token"]')).toBeNull();
  });

  it('leaves GET forms alone', () => {
    document.cookie = 'csrf_token=tok4';
    const form = document.createElement('form');
    document.body.appendChild(form);

    submitForm(form);

    expect(form.querySelector('input[name="csrf_token"]')).toBeNull();
  });
});
