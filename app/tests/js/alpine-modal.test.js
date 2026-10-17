/**
 * AlpineModal's dialog behaviour, mounted by the real vendored Alpine on the
 * markup the Python renders (tests/js/fixtures/alpine-modal-*.html,
 * drift-pinned by tests/unit/ui/test_alpine_modal_markup.py).
 *
 * Pins what a stub Alpine cannot see: focus moves into the dialog when it
 * opens (after x-show's deferred reveal), Tab and Shift+Tab cycle inside it,
 * Escape closes it through the caller's own close expression, focus returns
 * to the opener, and the component's members never shadow the caller's
 * open()/close().
 */
import { afterEach, beforeAll, describe, expect, it } from 'vitest';
import { fixture, loadAlpine } from './helpers/load-alpine.js';

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

function key(target, name, opts = {}) {
  const event = new KeyboardEvent('keydown', { key: name, bubbles: true, cancelable: true, ...opts });
  target.dispatchEvent(event);
  return event;
}

function mount(name) {
  const host = document.createElement('div');
  host.innerHTML = fixture(name);
  document.body.appendChild(host);
  return host;
}

function shown(el) {
  return el.style.display !== 'none';
}

beforeAll(async () => {
  // The insight modal loads its details on open; answer with nothing.
  window.fetch = () => new Promise(() => {});
  await loadAlpine();
});

afterEach(() => {
  document.body.innerHTML = '';
});

describe('add relationship modal', () => {
  async function opened() {
    const host = mount('alpine-modal-add-relationship.html');
    await frames();
    const opener = host.querySelector('button');
    const wrapper = host.querySelector('[x-data="alpineModal"]');
    const dialog = host.querySelector('[role="dialog"]');
    opener.focus();
    opener.click();
    await frames();
    return { host, opener, wrapper, dialog };
  }

  it('is a named modal dialog', async () => {
    const { host, dialog } = await opened();
    expect(dialog.getAttribute('aria-modal')).toBe('true');
    const title = host.querySelector('#' + dialog.getAttribute('aria-labelledby'));
    expect(title.textContent).toBe('Add relationship');
  });

  it('moves focus into the dialog once it is displayed', async () => {
    // jsdom lets a hidden element take focus; a browser does not. Record
    // whether the dialog was displayed when focus arrived.
    const host = mount('alpine-modal-add-relationship.html');
    await frames();
    const opener = host.querySelector('button');
    const wrapper = host.querySelector('[x-data="alpineModal"]');
    const dialog = host.querySelector('[role="dialog"]');
    let displayedOnFocus = null;
    dialog.addEventListener('focusin', () => {
      if (displayedOnFocus === null) displayedOnFocus = shown(wrapper);
    });
    opener.focus();
    opener.click();
    await frames();
    expect(displayedOnFocus).toBe(true);
    expect(document.activeElement).toBe(dialog.querySelector('select'));
  });

  it('cycles Tab and Shift+Tab among the visible controls only', async () => {
    const { dialog } = await opened();
    const visible = Array.from(dialog.querySelectorAll('select, input:not([type=hidden]), button'))
      .filter((el) => !el.closest('[style*="display: none"]') && el.tabIndex !== -1);
    const first = visible[0];
    const last = visible[visible.length - 1];
    expect(last.textContent).toBe('Cancel');

    last.focus();
    expect(key(last, 'Tab').defaultPrevented).toBe(true);
    expect(document.activeElement).toBe(first);

    expect(key(first, 'Tab', { shiftKey: true }).defaultPrevented).toBe(true);
    expect(document.activeElement).toBe(last);

    // A Tab between two inner controls is left to the browser.
    first.focus();
    expect(key(first, 'Tab').defaultPrevented).toBe(false);
  });

  it('closes on Escape and returns focus to the opener', async () => {
    const { opener, wrapper } = await opened();
    key(document.activeElement, 'Escape');
    await frames();
    expect(shown(wrapper)).toBe(false);
    expect(document.activeElement).toBe(opener);
  });

  it('lets Escape close an open picker list without closing the dialog', async () => {
    const { wrapper, dialog } = await opened();
    const search = dialog.querySelector('[role="combobox"]');
    search.focus();
    await frames();
    const picker = search.closest('[x-data="entityPicker"]');
    expect(window.Alpine.$data(picker).open).toBe(true);

    key(search, 'Escape');
    await frames();
    expect(window.Alpine.$data(picker).open).toBe(false);
    expect(shown(wrapper)).toBe(true);

    key(search, 'Escape');
    await frames();
    expect(shown(wrapper)).toBe(false);
  });

  it('closes on a backdrop click', async () => {
    const { opener, wrapper } = await opened();
    wrapper.firstElementChild.click();
    await frames();
    expect(shown(wrapper)).toBe(false);
    expect(document.activeElement).toBe(opener);
  });
});

describe('insight detail modal', () => {
  it("opens and closes through the caller's own open() and close()", async () => {
    const host = mount('alpine-modal-insight.html');
    await frames();
    const opener = host.querySelector('button[x-on\\:click="open()"]');
    const wrapper = host.querySelector('[x-data="alpineModal"]');
    const dialog = host.querySelector('[role="dialog"]');
    opener.focus();
    opener.click();
    await frames();
    expect(shown(wrapper)).toBe(true);
    expect(document.activeElement.getAttribute('aria-label')).toBe('Close');
    expect(dialog.contains(document.activeElement)).toBe(true);

    key(document.activeElement, 'Escape');
    await frames();
    expect(shown(wrapper)).toBe(false);
    expect(window.Alpine.$data(host.firstElementChild).isOpen).toBe(false);
    expect(document.activeElement).toBe(opener);
  });
});

describe('gradebook share panel', () => {
  it('opens, traps and restores', async () => {
    const host = mount('alpine-modal-share.html');
    await frames();
    const opener = host.querySelector('button');
    const wrapper = host.querySelector('[x-data="alpineModal"]');
    opener.focus();
    opener.click();
    await frames();
    expect(shown(wrapper)).toBe(true);
    const close = document.activeElement;
    expect(close.getAttribute('aria-label')).toBe('Close');
    // The close button is the only control: Tab stays on it.
    expect(key(close, 'Tab').defaultPrevented).toBe(true);
    expect(document.activeElement).toBe(close);
    close.click();
    await frames();
    expect(shown(wrapper)).toBe(false);
    expect(document.activeElement).toBe(opener);
  });
});

describe('calendar item modal', () => {
  it('opens on mount, focuses the dialog, and on close removes itself and refocuses the chip', async () => {
    const chip = document.createElement('button');
    chip.textContent = 'Meditate';
    document.body.appendChild(chip);
    chip.focus();
    // The swapped-in fragment arrives already open.
    mount('alpine-modal-calendar.html');
    await frames();
    const dialog = document.querySelector('[role="dialog"]');
    expect(dialog.contains(document.activeElement)).toBe(true);
    expect(document.activeElement.getAttribute('aria-label')).toBe('Close');

    key(document.activeElement, 'Escape');
    await frames();
    expect(document.getElementById('item-details-modal')).toBeNull();
    expect(document.activeElement).toBe(chip);
  });
});
