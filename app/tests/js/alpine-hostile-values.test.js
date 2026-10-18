/**
 * A value carrying quotes, a backslash, a newline, U+2028 or a closing
 * </script> reaches an Alpine component as data, mounted by the REAL vendored
 * Alpine on the markup the Python renders (tests/js/fixtures/, drift-pinned by
 * tests/unit/ui/test_alpine_hostile_fixtures.py).
 *
 * Alpine evaluates x-data and every directive as JavaScript statements, so a
 * value hand-quoted into one ends its string at its first quote and the rest
 * runs. Each hostile value tries to set window.__pwned; none may, and the
 * component state must equal the value exactly.
 */
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';
import { fixture, loadAlpine, settle } from './helpers/load-alpine.js';

const HOSTILE = JSON.parse(fixture('hostile-values.json'));

let Alpine;
let warnings;

beforeAll(async () => {
  Alpine = await loadAlpine();
});

beforeEach(() => {
  delete window.__pwned;
  warnings = [];
  vi.spyOn(console, 'warn').mockImplementation((...args) => warnings.push(args.join(' ')));
  vi.spyOn(console, 'error').mockImplementation(() => {});
});

afterEach(async () => {
  document.body.replaceChildren();
  await settle();
  vi.restoreAllMocks();
});

async function mount(name) {
  document.body.insertAdjacentHTML('beforeend', fixture(name));
  await settle();
  await settle();
  return document.body.lastElementChild;
}

describe('insight filter form (render_filter_form)', () => {
  it('holds the search value as data, running none of it', async () => {
    const root = await mount('insight-filters-hostile.html');
    expect(window.__pwned).toBeUndefined();
    const cases = root.querySelectorAll('[data-case]');
    expect(cases).toHaveLength(HOSTILE.length);

    cases.forEach((wrapper) => {
      const value = HOSTILE[Number(wrapper.dataset.case)];
      const form = wrapper.querySelector('[x-data]');
      expect(Alpine.$data(form).filters).toEqual({
        search: value,
        domain: '',
        impact: '',
        type: '',
      });
    });
    expect(warnings).toEqual([]);
  });

  it('binds the search box to the value it was rendered with', async () => {
    const root = await mount('insight-filters-hostile.html');
    const wrapper = root.querySelector('[data-case="0"]');
    expect(wrapper.querySelector('input[type="text"]').value).toBe(HOSTILE[0]);
  });
});

describe('groups hub (GroupsHub)', () => {
  it('holds every group uid as data and switches tabs by it', async () => {
    const root = await mount('groups-hub-hostile.html');
    const scope = root.matches('[x-data]') ? root : root.querySelector('[x-data]');
    expect(window.__pwned).toBeUndefined();
    const state = Alpine.$data(scope);
    expect(state.activeTab).toBe(HOSTILE[0]);
    expect(Array.from(state.tabs)).toEqual(HOSTILE);

    const tabs = scope.querySelectorAll('[role="tab"]');
    expect(tabs).toHaveLength(HOSTILE.length);
    for (const [index, button] of tabs.entries()) {
      button.click();
      await settle();
      expect(state.activeTab).toBe(HOSTILE[index]);
      expect(button.getAttribute('aria-selected')).toBe('true');
    }
    expect(window.__pwned).toBeUndefined();
    expect(warnings).toEqual([]);
  });
});
