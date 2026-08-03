/**
 * Behavior pins for static/js/today.js — the C7 defer contract.
 *
 * Covers the client half of the calendar act-from arc's C7 ruling
 * (docs/roadmap/calendar-act-from-arc.md):
 *   - (source, uid) keying: a dual-membership task's two cards act
 *     independently (hide, selection, focus order, drawer);
 *   - one transport per defer: a single fetch carrying span + source +
 *     view_date, with rollback + server message on ANY non-2xx;
 *   - no Undo for defers (the removed control only cleared local state
 *     while the persisted date stayed moved); complete keeps its undo.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { loadToday } from './helpers/load-today.js';

function seed() {
  return {
    today_iso: '2026-08-02',
    date_label: 'Sunday · August 2',
    heading: 'Today',
    is_today: true,
    now_hhmm: '09:00',
    stats: { nodes: 0, committed_min: 0, done: 0 },
    // t-dual is overdue AND on today's ribbon — one card per surface.
    triage: [
      { id: 't-dual', label: 'Dual card', lifepath_id: 'lp-1', est_min: 10,
        reason: 'Overdue · 7d', severity: 'overdue', pinned: false },
      { id: 't-late', label: 'Late only', lifepath_id: 'lp-1', est_min: 15,
        reason: 'Overdue · 2d', severity: 'overdue', pinned: false },
    ],
    lifepaths: [{ id: 'lp-1', label: 'Path', blurb: null, color: '', dormant: false,
      last_touched: null }],
    principles: [],
    goals: [],
    tasks: [
      { id: 't-dual', label: 'Dual card', lifepath_id: 'lp-1', est_min: 10, pinned: false },
      { id: 't-work', label: 'Work only', lifepath_id: 'lp-1', est_min: 20, pinned: false },
    ],
    rituals: [],
    kinds: {},
    ritual_icons: { past: '', upcoming: '' },
  };
}

function okResponse() {
  return { ok: true, status: 204, text: () => Promise.resolve('') };
}

function errorResponse(status, body) {
  return { ok: false, status, text: () => Promise.resolve(body) };
}

let c;

beforeEach(() => {
  global.fetch = vi.fn().mockResolvedValue(okResponse());
  c = loadToday(seed());
});

afterEach(() => {
  vi.restoreAllMocks();
  delete global.fetch;
});

describe('(source, uid) card keying', () => {
  it('hides only the acted-on surface for a dual-membership task', () => {
    c.deferred[c.cardKey('triage', 't-dual')] = '1d';
    expect(c.fTriage.map((t) => t.id)).toEqual(['t-late']);
    // The ribbon card of the SAME task stays visible.
    expect(c.fTasks.map((t) => t.id)).toEqual(['t-dual', 't-work']);
  });

  it('hides only the ribbon card when the ribbon surface is deferred', () => {
    c.deferred[c.cardKey('ribbon', 't-dual')] = '1w';
    expect(c.fTasks.map((t) => t.id)).toEqual(['t-work']);
    expect(c.fTriage.map((t) => t.id)).toEqual(['t-dual', 't-late']);
  });

  it('completion is task-level: both cards hide', () => {
    c.completeTask('t-dual');
    expect(c.fTasks.map((t) => t.id)).toEqual(['t-work']);
    expect(c.fTriage.map((t) => t.id)).toEqual(['t-late']);
  });

  it('flatOrder lists the repeated uid once per surface, as distinct keys', () => {
    expect(c.flatOrder()).toEqual([
      'triage:t-dual', 'triage:t-late', 'ribbon:t-dual', 'ribbon:t-work',
    ]);
  });

  it('j/k traverses both cards of a dual-membership task without stalling', () => {
    const visited = [];
    for (let i = 0; i < 4; i++) {
      c.moveSelection(+1);
      visited.push(c.selectedKey);
    }
    expect(visited).toEqual([
      'triage:t-dual', 'triage:t-late', 'ribbon:t-dual', 'ribbon:t-work',
    ]);
    c.moveSelection(-1);
    expect(c.selectedKey).toBe('ribbon:t-dual');
  });

  it('openTask resolves from the originating surface', () => {
    c.openDrawer('triage:t-dual');
    expect(c.openTask.reason).toBe('Overdue · 7d'); // triage variant object
    expect(c.selectedKey).toBe('triage:t-dual');
    c.openDrawer('ribbon:t-dual');
    expect(c.openTask.reason).toBeUndefined(); // ribbon variant object
  });
});

describe('deferTask transport (C7)', () => {
  it('posts exactly ONE request carrying span, source and view_date', async () => {
    await c.deferTask('ribbon', 't-work', '1d');
    expect(global.fetch).toHaveBeenCalledTimes(1);
    const [url, init] = global.fetch.mock.calls[0];
    expect(url).toBe('/today/tasks/t-work/defer');
    expect(init.method).toBe('POST');
    const body = init.body.toString();
    expect(body).toContain('span=1d');
    expect(body).toContain('source=ribbon');
    expect(body).toContain('view_date=2026-08-02');
  });

  it("keyboard defer routes the selected card's source", async () => {
    c.selectedKey = 'triage:t-dual';
    c.onKey({ key: 'd', shiftKey: false, preventDefault() {} });
    await Promise.resolve();
    const body = global.fetch.mock.calls[0][1].body.toString();
    expect(body).toContain('source=triage');
    expect(c.deferred['triage:t-dual']).toBe('1d');
    expect(c.deferred['ribbon:t-dual']).toBeUndefined();
  });

  it('success: card stays hidden, flash offers NO undo, no undoable action', async () => {
    await c.deferTask('ribbon', 't-work', '1w');
    expect(c.deferred['ribbon:t-work']).toBe('1w');
    expect(c.flash.msg).toContain('next week');
    expect(c.flash.action).toBeNull();
    expect(c._lastAction).toBeNull();
  });

  it('non-2xx: restores the card and shows the server message', async () => {
    global.fetch.mockResolvedValue(
      errorResponse(400, "Work date would pass the task's deadline (2026-08-04)"),
    );
    await c.deferTask('ribbon', 't-work', '1w');
    expect(c.deferred['ribbon:t-work']).toBeUndefined();
    expect(c.fTasks.map((t) => t.id)).toContain('t-work');
    expect(c.flash.msg).toContain('deadline');
  });

  it('non-2xx with empty body: falls back to a status message', async () => {
    global.fetch.mockResolvedValue(errorResponse(500, ''));
    await c.deferTask('triage', 't-late', '1d');
    expect(c.deferred['triage:t-late']).toBeUndefined();
    expect(c.flash.msg).toContain('500');
  });

  it('network error: restores the card and reports failure', async () => {
    global.fetch.mockRejectedValue(new TypeError('network down'));
    await c.deferTask('triage', 't-dual', '1d');
    expect(c.deferred['triage:t-dual']).toBeUndefined();
    expect(c.flash.msg).toContain('not moved');
  });

  it('repeat defer on an already-hidden card is a no-op (no second POST)', async () => {
    // Held `d` / double-click: the twin request would fail the fresh-membership
    // guard and falsely restore a card whose first defer succeeded.
    const first = c.deferTask('ribbon', 't-work', '1d');
    const second = c.deferTask('ribbon', 't-work', '1d');
    await Promise.all([first, second]);
    expect(global.fetch).toHaveBeenCalledTimes(1);
    expect(c.deferred['ribbon:t-work']).toBe('1d');
  });
});

describe('quick-add input does not hijack single-key actions (C6)', () => {
  it('ignores a keydown originating from a text input', async () => {
    c.selectedKey = 'triage:t-dual';
    // Typing "d" into the quick-add title field must NOT defer the selected card.
    c.onKey({ key: 'd', shiftKey: false, target: { tagName: 'INPUT' }, preventDefault() {} });
    await Promise.resolve();
    expect(global.fetch).not.toHaveBeenCalled();
    expect(c.deferred['triage:t-dual']).toBeUndefined();
  });

  it('still acts on keystrokes outside a field', async () => {
    c.selectedKey = 'triage:t-dual';
    c.onKey({ key: 'd', shiftKey: false, target: { tagName: 'BODY' }, preventDefault() {} });
    await Promise.resolve();
    expect(c.deferred['triage:t-dual']).toBe('1d');
  });
});

describe('undo truthfulness', () => {
  it('undoFlash no longer resurrects deferred cards', async () => {
    await c.deferTask('ribbon', 't-work', '1d');
    c.undoFlash();
    // The defer already posted — local state must NOT pretend otherwise.
    expect(c.deferred['ribbon:t-work']).toBe('1d');
    expect(c.fTasks.map((t) => t.id)).not.toContain('t-work');
  });

  it('complete keeps its undo path', () => {
    c.completeTask('t-work');
    expect(c.flash.action).toBe('undo');
    c.undoFlash();
    expect(c.completed.has('t-work')).toBe(false);
  });
});
