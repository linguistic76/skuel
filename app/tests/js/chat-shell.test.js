/**
 * The chat pages' sidebar, mounted by the real vendored Alpine on the markup the
 * Python renders (tests/js/fixtures/chat-shell.html, drift-pinned by
 * tests/unit/ui/test_chat_shell.py).
 *
 * Below lg a phone opens on the rail, the open panel overlays the chat, and a tap
 * outside it or Escape closes it without touching the remembered choice. At lg and
 * up the sidebar opens by default, a tap on the chat leaves it alone, and a collapse
 * is remembered for the next visit.
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
