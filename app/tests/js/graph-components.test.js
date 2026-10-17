/**
 * relationshipGraph + exploreGraph mounted by the real vendored Alpine on the
 * markup the Python renders (tests/js/fixtures/, drift-pinned by
 * tests/unit/ui/test_graph_alpine_markup.py).
 *
 * Pins what a stub Alpine cannot see: one graph fetch per mount, a depth
 * select that the component actually binds, an error the markup shows, and a
 * teardown that leaves no network, listener or overlay behind when the
 * component is removed from the page; and the expanded overlay's focus: in on
 * its close button, Tab kept inside, back on the expand button once x-show
 * has revealed it.
 */
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';
import { fixture, loadAlpine, settle } from './helpers/load-alpine.js';

let fetches;
let failNext;
let networks;
let keydownAdds;
let keydownRemoves;

class FakeNetwork {
  constructor() {
    this.destroyed = false;
    networks.push(this);
  }
  destroy() { this.destroyed = true; }
  on() {}
  redraw() {}
  fit() {}
}

class FakeDataSet {
  constructor(items) { this.items = items; }
  forEach(fn) { this.items.forEach(fn); }
  update() {}
}

const GRAPH = { nodes: [{ id: 'task_abc', label: 'Centre' }, { id: 'task_b', label: 'B' }], edges: [] };

beforeAll(async () => {
  window.vis = { Network: FakeNetwork, DataSet: FakeDataSet };
  window.fetch = async (url) => {
    fetches.push(String(url));
    if (failNext) {
      failNext = false;
      return { ok: false, status: 503, text: async () => '' };
    }
    return { ok: true, status: 200, text: async () => JSON.stringify(GRAPH) };
  };
  const addListener = document.addEventListener.bind(document);
  const removeListener = document.removeEventListener.bind(document);
  document.addEventListener = (type, ...rest) => {
    if (type === 'keydown') keydownAdds += 1;
    return addListener(type, ...rest);
  };
  document.removeEventListener = (type, ...rest) => {
    if (type === 'keydown') keydownRemoves += 1;
    return removeListener(type, ...rest);
  };
  await loadAlpine();
});

beforeEach(() => {
  fetches = [];
  failNext = false;
  networks = [];
  keydownAdds = 0;
  keydownRemoves = 0;
  vi.spyOn(console, 'error').mockImplementation(() => {});
});

afterEach(async () => {
  document.body.replaceChildren();
  await settle();
  vi.restoreAllMocks();
});

/** x-show reveals one animation frame after the state flips. */
function frames(n = 3) {
  return new Promise((resolve) => {
    function step(left) {
      if (left === 0) return resolve();
      requestAnimationFrame(() => step(left - 1));
    }
    step(n);
  });
}

function tab(target, opts = {}) {
  const event = new KeyboardEvent('keydown', { key: 'Tab', bubbles: true, cancelable: true, ...opts });
  target.dispatchEvent(event);
  return event;
}

function displayed(el) {
  return el.style.display !== 'none';
}

async function mount(name) {
  document.body.insertAdjacentHTML('beforeend', fixture(name));
  await settle();
  await settle();
  return document.body.lastElementChild;
}

describe('relationshipGraph (RelationshipGraphView)', () => {
  it('fetches the graph once per mount', async () => {
    await mount('relationship-graph.html');

    expect(fetches).toEqual(['/api/tasks/task_abc/lateral/graph?depth=2']);
    expect(networks).toHaveLength(1);
  });

  it('refetches at the depth the select chooses', async () => {
    const card = await mount('relationship-graph.html');
    const select = card.querySelector('select[name="graph_depth"]');

    select.value = '3';
    select.dispatchEvent(new Event('change', { bubbles: true }));
    await settle();
    await settle();

    expect(fetches.at(-1)).toBe('/api/tasks/task_abc/lateral/graph?depth=3');
  });

  it('shows the error when the graph cannot load', async () => {
    failNext = true;
    const card = await mount('relationship-graph.html');
    const slot = card.querySelector('[x-text="error"]');

    await vi.waitFor(() => {
      expect(slot.textContent).toBe('Failed to load graph. Please try again.');
      expect(slot.style.display).not.toBe('none');
    });
  });

  it('tears its network down when removed', async () => {
    const card = await mount('relationship-graph.html');
    expect(networks).toHaveLength(1);

    card.remove();
    await settle();

    expect(networks[0].destroyed).toBe(true);
  });
});

describe('exploreGraph (ExploreGraphView, standalone)', () => {
  it('fetches the hub graph once and listens for Escape once', async () => {
    await mount('explore-graph.html');

    expect(fetches).toEqual(['/api/explore/graph']);
    expect(keydownAdds).toBe(1);
  });

  it('Escape closes the expanded overlay', async () => {
    const wrapper = await mount('explore-graph.html');
    wrapper.querySelector('[aria-label="Expand graph view"]').click();
    await settle();
    expect(document.getElementById('explore-graph-overlay')).not.toBeNull();

    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }));
    await settle();

    expect(document.getElementById('explore-graph-overlay')).toBeNull();
  });

  it('moves focus to the close button when the overlay opens', async () => {
    const wrapper = await mount('explore-graph.html');
    const expand = wrapper.querySelector('[aria-label="Expand graph view"]');
    expand.focus();
    expand.click();
    await settle();

    const overlay = document.getElementById('explore-graph-overlay');
    expect(document.activeElement).toBe(overlay.querySelector('[aria-label="Close expanded graph"]'));
  });

  it('keeps Tab and Shift+Tab inside the overlay', async () => {
    const wrapper = await mount('explore-graph.html');
    wrapper.querySelector('[aria-label="Expand graph view"]').click();
    await settle();
    const overlay = document.getElementById('explore-graph-overlay');
    const close = overlay.querySelector('[aria-label="Close expanded graph"]');
    // A second focusable, standing in for the canvas frame Vis.js makes
    // focusable (tabIndex 0) in a browser.
    const frame = document.createElement('div');
    frame.tabIndex = 0;
    close.parentElement.appendChild(frame);

    frame.focus();
    expect(tab(frame).defaultPrevented).toBe(true);
    expect(document.activeElement).toBe(close);

    expect(tab(close, { shiftKey: true }).defaultPrevented).toBe(true);
    expect(document.activeElement).toBe(frame);

    // A Tab between two inner controls is left to the browser.
    close.focus();
    expect(tab(close).defaultPrevented).toBe(false);
  });

  it.each([
    ['Escape', () => document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))],
    ['the close button', () => document.querySelector('[aria-label="Close expanded graph"]').click()],
  ])('%s returns focus to the expand button once it is displayed', async (_name, close) => {
    const wrapper = await mount('explore-graph.html');
    const expand = wrapper.querySelector('[aria-label="Expand graph view"]');
    expand.click();
    await frames();
    expect(displayed(expand)).toBe(false);
    // jsdom lets a hidden element take focus; a browser does not. Record
    // whether the button was displayed when focus arrived.
    let displayedOnFocus = null;
    expand.addEventListener('focus', () => {
      if (displayedOnFocus === null) displayedOnFocus = displayed(expand);
    });

    close();
    await frames();

    expect(document.getElementById('explore-graph-overlay')).toBeNull();
    expect(document.activeElement).toBe(expand);
    expect(displayedOnFocus).toBe(true);
  });

  it('leaves no network, listener or overlay behind when removed', async () => {
    const wrapper = await mount('explore-graph.html');
    wrapper.querySelector('[aria-label="Expand graph view"]').click();
    await settle();
    expect(networks).toHaveLength(2);

    wrapper.remove();
    await settle();

    expect(networks.every((network) => network.destroyed)).toBe(true);
    expect(keydownRemoves).toBe(keydownAdds);
    expect(document.getElementById('explore-graph-overlay')).toBeNull();
  });
});
