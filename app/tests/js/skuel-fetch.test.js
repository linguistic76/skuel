/**
 * JSON fetch-helper pins for static/js/skuel.js
 * (SKUEL.getJson / SKUEL.postJson / SKUEL.refreshAfterMutation).
 *
 * These three helpers are the single chokepoint every hybrid fetch() call site
 * in skuel.js goes through, so this pins what those call sites now rely on:
 * the CSRF header on mutations (the client half of adapters/inbound/csrf.py),
 * rejection on any non-2xx, the server's own error wording surfacing on the
 * Error, and the fragment-refresh-else-reload policy after a mutation.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { loadSkuel } from './helpers/load-skuel.js';

/** Build a minimal Response stand-in — the helpers only read ok/status/text(). */
function jsonResponse(body, { ok = true, status = 200 } = {}) {
  return {
    ok,
    status,
    text: () => Promise.resolve(body === undefined ? '' : JSON.stringify(body)),
  };
}

function textResponse(text, { ok = true, status = 200 } = {}) {
  return { ok, status, text: () => Promise.resolve(text) };
}

describe('SKUEL.getJson', () => {
  beforeEach(() => {
    loadSkuel();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('resolves with the parsed body', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ items: [1, 2] }));
    vi.stubGlobal('fetch', fetchMock);

    await expect(window.SKUEL.getJson('/api/things')).resolves.toEqual({
      items: [1, 2],
    });
    expect(fetchMock).toHaveBeenCalledWith('/api/things', undefined);
  });

  it('rejects on a non-2xx and carries the status', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(jsonResponse({ detail: 'Nope' }, { ok: false, status: 404 })),
    );

    await expect(window.SKUEL.getJson('/api/missing')).rejects.toMatchObject({
      message: 'Nope',
      status: 404,
    });
  });

  it('falls back to a generic message when the body is not JSON', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(textResponse('<html>502</html>', { ok: false, status: 502 })),
    );

    await expect(window.SKUEL.getJson('/api/down')).rejects.toThrow(
      'Request failed (502)',
    );
  });

  it('resolves to null on an empty body', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(textResponse('')));

    await expect(window.SKUEL.getJson('/api/empty')).resolves.toBeNull();
  });
});

describe('SKUEL.postJson', () => {
  beforeEach(() => {
    document.cookie = 'csrf_token=; expires=Thu, 01 Jan 1970 00:00:00 GMT';
    loadSkuel();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('sends the CSRF header and a JSON body', async () => {
    document.cookie = 'csrf_token=tok-abc';
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ ok: true }));
    vi.stubGlobal('fetch', fetchMock);

    await window.SKUEL.postJson('/api/tasks/bulk-delete', { uids: ['a'] });

    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe('/api/tasks/bulk-delete');
    expect(init.method).toBe('POST');
    expect(init.headers['X-CSRF-Token']).toBe('tok-abc');
    expect(init.headers['Content-Type']).toBe('application/json');
    expect(JSON.parse(init.body)).toEqual({ uids: ['a'] });
  });

  it('honours a method override', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({}));
    vi.stubGlobal('fetch', fetchMock);

    await window.SKUEL.postJson('/api/tasks/t1', { title: 'x' }, { method: 'PATCH' });

    expect(fetchMock.mock.calls[0][1].method).toBe('PATCH');
  });

  it('omits the body entirely when none is given', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({}));
    vi.stubGlobal('fetch', fetchMock);

    await window.SKUEL.postJson('/api/ping');

    expect(fetchMock.mock.calls[0][1].body).toBeUndefined();
  });

  it('prefers the Result-envelope error message', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        jsonResponse({ error: { message: 'Not your task' } }, { ok: false, status: 403 }),
      ),
    );

    await expect(window.SKUEL.postJson('/api/tasks/x', {})).rejects.toMatchObject({
      message: 'Not your task',
      status: 403,
    });
  });

  it('exposes the parsed payload on the rejection', async () => {
    const body = { detail: 'Bad input', field: 'title' };
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(jsonResponse(body, { ok: false, status: 422 })),
    );

    await expect(window.SKUEL.postJson('/api/tasks', {})).rejects.toMatchObject({
      payload: body,
    });
  });
});

describe('SKUEL.refreshAfterMutation', () => {
  beforeEach(() => {
    document.body.innerHTML = '';
    loadSkuel();
  });

  afterEach(() => {
    delete window.htmx;
    vi.unstubAllGlobals();
  });

  it('refreshes the HTMX fragment when the container exists', () => {
    document.body.innerHTML = '<div id="children-goal_1"></div>';
    const trigger = vi.fn();
    window.htmx = { trigger };
    const reload = vi.fn();
    vi.stubGlobal('location', { reload });

    window.SKUEL.refreshAfterMutation('#children-goal_1');

    expect(trigger).toHaveBeenCalledWith(
      document.getElementById('children-goal_1'),
      'refresh',
    );
    expect(reload).not.toHaveBeenCalled();
  });

  it('reloads when no selector is given', () => {
    const reload = vi.fn();
    vi.stubGlobal('location', { reload });

    window.SKUEL.refreshAfterMutation();

    expect(reload).toHaveBeenCalled();
  });

  it('reloads when the selector matches nothing', () => {
    window.htmx = { trigger: vi.fn() };
    const reload = vi.fn();
    vi.stubGlobal('location', { reload });

    window.SKUEL.refreshAfterMutation('#not-there');

    expect(window.htmx.trigger).not.toHaveBeenCalled();
    expect(reload).toHaveBeenCalled();
  });
});

describe('SKUEL.announceRouteFor', () => {
  beforeEach(() => {
    loadSkuel();
  });

  it('resolves the in-flight verb and the completion message together', () => {
    expect(window.SKUEL.announceRouteFor('/api/tasks/create')).toMatchObject({
      verb: 'Creating',
      done: 'Created successfully',
    });
    expect(window.SKUEL.announceRouteFor('/api/tasks/t1/delete')).toMatchObject({
      verb: 'Deleting',
      done: 'Deleted successfully',
    });
  });

  it('treats the /update /edit /save synonyms as one route', () => {
    ['/edit', '/save', '/update'].forEach((path) => {
      expect(window.SKUEL.announceRouteFor(path).done).toBe('Updated successfully');
    });
  });

  it('leaves /decide without an in-flight verb', () => {
    const route = window.SKUEL.announceRouteFor('/api/choices/c1/decide');
    expect(route.verb).toBeNull();
    expect(route.done).toBe('Decision recorded');
  });

  it('returns null for unmatched and empty paths', () => {
    expect(window.SKUEL.announceRouteFor('/api/tasks/list')).toBeNull();
    expect(window.SKUEL.announceRouteFor('')).toBeNull();
  });
});
