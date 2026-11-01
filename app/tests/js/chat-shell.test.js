/**
 * The chat pages' sidebar, mounted by the real vendored Alpine on the markup the
 * Python renders (tests/js/fixtures/chat-shell.html, drift-pinned by
 * tests/unit/ui/test_chat_shell.py).
 *
 * Below lg a phone opens on the rail, the open panel overlays the chat, and a tap
 * outside it or Escape closes it without touching the remembered choice. At lg and
 * up the sidebar opens by default, a tap on the chat leaves it alone, and a collapse
 * is remembered for the next visit.
 *
 * The side panel (Journals' uploads) mirrors it from the right: below lg the toggle
 * opens it over the chat, a tap outside or Escape closes it, a swap into the chat
 * closes it onto the result, and opening either overlay closes the other. At lg it
 * is always in the row.
 */
import { afterEach, beforeAll, describe, expect, it } from 'vitest';
import { fixture, loadAlpine, settle } from './helpers/load-alpine.js';

let Alpine;
let wide = false;

function mount() {
  window.matchMedia = (query) => ({
    matches: query === '(min-width: 1024px)' && wide,
    media: query,
    addEventListener() {},
    removeEventListener() {},
  });
  const host = document.createElement('div');
  host.innerHTML = fixture('chat-shell.html');
  document.body.appendChild(host);
  return host;
}

const root = (host) => host.querySelector('[x-data]');
const isOpen = (host) => Alpine.$data(root(host)).sidebarOpen;
const button = (host, label) => host.querySelector(`[aria-label="${label}"]`);
const panel = (host) => host.querySelector('#chat-side-panel');
const panelOpen = (host) => Alpine.$data(root(host)).panelOpen;

// Alpine's .outside ignores an element with no layout (offsetWidth < 1), and jsdom lays
// nothing out: give an element the width a browser would. The side panel gets its width
// before the toggle is tapped, so the panel's tap-outside close sees the tap on the
// toggle the way a browser does (a real tap's microtask checkpoint shows the panel
// before the document hears the click).
function layOut(el, width) {
  Object.defineProperty(el, 'offsetWidth', { value: width, configurable: true });
}

function swapInto(id) {
  window.dispatchEvent(new CustomEvent('htmx:after-swap', { detail: { target: { id } } }));
}

beforeAll(async () => {
  Alpine = await loadAlpine();
});

afterEach(() => {
  document.body.innerHTML = '';
  localStorage.clear();
});

describe('on a phone', () => {
  it('opens on the rail', async () => {
    wide = false;
    const host = mount();
    await settle();
    expect(isOpen(host)).toBe(false);
  });

  it('closes the overlay on a tap outside it, and remembers nothing', async () => {
    wide = false;
    const host = mount();
    await settle();
    button(host, 'Expand sidebar').click();
    await settle();
    expect(isOpen(host)).toBe(true);

    // Alpine's .outside ignores an element with no layout (offsetWidth < 1), and
    // jsdom lays nothing out: give the open sidebar the width a browser would.
    const sidebar = root(host).firstElementChild.firstElementChild;
    Object.defineProperty(sidebar, 'offsetWidth', { value: 274 });
    host.querySelector('#chat').click();
    await settle();
    expect(isOpen(host)).toBe(false);
    expect(localStorage.getItem('journal-sidebar')).toBeNull();
  });

  it('closes the overlay on Escape', async () => {
    wide = false;
    const host = mount();
    await settle();
    button(host, 'Expand sidebar').click();
    await settle();

    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }));
    await settle();
    expect(isOpen(host)).toBe(false);
  });
});

describe('on a wide screen', () => {
  it('opens by default and stays open on a tap on the chat', async () => {
    wide = true;
    const host = mount();
    await settle();
    expect(isOpen(host)).toBe(true);

    const sidebar = root(host).firstElementChild.firstElementChild;
    Object.defineProperty(sidebar, 'offsetWidth', { value: 274 });
    host.querySelector('#chat').click();
    await settle();
    expect(isOpen(host)).toBe(true);
  });

  it('remembers a collapse for the next visit', async () => {
    wide = true;
    const host = mount();
    await settle();
    button(host, 'Collapse sidebar').click();
    await settle();
    expect(isOpen(host)).toBe(false);
    expect(localStorage.getItem('journal-sidebar')).toBe('false');

    document.body.innerHTML = '';
    const again = mount();
    await settle();
    expect(isOpen(again)).toBe(false);
  });
});

describe('the side panel on a phone', () => {
  it('starts closed and opens from its toggle', async () => {
    wide = false;
    const host = mount();
    await settle();
    expect(panelOpen(host)).toBe(false);
    expect(panel(host).hasAttribute('data-open')).toBe(false);
    expect(host.querySelector('#toggle').getAttribute('aria-expanded')).toBe('false');

    layOut(panel(host), 313);
    host.querySelector('#toggle').click();
    await settle();
    expect(panelOpen(host)).toBe(true);
    expect(panel(host).hasAttribute('data-open')).toBe(true);
    expect(host.querySelector('#toggle').getAttribute('aria-expanded')).toBe('true');
  });

  it('stays open on a tap inside it and closes on a tap outside it', async () => {
    wide = false;
    const host = mount();
    await settle();
    layOut(panel(host), 313);
    host.querySelector('#toggle').click();
    await settle();

    host.querySelector('#inside').click();
    await settle();
    expect(panelOpen(host)).toBe(true);

    host.querySelector('#chat').click();
    await settle();
    expect(panelOpen(host)).toBe(false);
  });

  it('closes on Escape', async () => {
    wide = false;
    const host = mount();
    await settle();
    host.querySelector('#toggle').click();
    await settle();

    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }));
    await settle();
    expect(panelOpen(host)).toBe(false);
  });

  it('closes onto a swap into the chat, and not on one inside it', async () => {
    wide = false;
    const host = mount();
    await settle();
    host.querySelector('#toggle').click();
    await settle();

    swapInto('status');
    await settle();
    expect(panelOpen(host)).toBe(true);

    swapInto('chat');
    await settle();
    expect(panelOpen(host)).toBe(false);
  });

  it('closes the sidebar when it opens, and closes when the sidebar opens', async () => {
    wide = false;
    const host = mount();
    await settle();
    layOut(root(host).firstElementChild.firstElementChild, 274);
    layOut(panel(host), 313);

    button(host, 'Expand sidebar').click();
    await settle();
    host.querySelector('#toggle').click();
    await settle();
    expect(isOpen(host)).toBe(false);
    expect(panelOpen(host)).toBe(true);

    button(host, 'Expand sidebar').click();
    await settle();
    expect(isOpen(host)).toBe(true);
    expect(panelOpen(host)).toBe(false);
  });
});

describe('the side panel on a wide screen', () => {
  it('is never closed by a tap on the chat or Escape (it is in the row)', async () => {
    wide = true;
    const host = mount();
    await settle();
    Alpine.$data(root(host)).panelOpen = true;
    await settle();
    layOut(panel(host), 320);

    host.querySelector('#chat').click();
    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }));
    await settle();
    expect(panelOpen(host)).toBe(true);
  });
});
