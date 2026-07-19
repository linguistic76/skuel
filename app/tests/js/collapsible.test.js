/**
 * collapsible + collapsibleSidebar Alpine component pins for skuel.js.
 *
 * Pins the toggle contract, the shared-store registration, the localStorage
 * persistence key format (`{storageKey}-collapsed`), and the screen-reader
 * announcement on toggle.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { loadSkuel } from './helpers/load-skuel.js';

let skuel;

beforeEach(() => {
  localStorage.clear();
  document.body.innerHTML = '<div id="live-region"></div>';
  skuel = loadSkuel();
});

describe('collapsible', () => {
  it('defaults to closed', () => {
    const component = skuel.make('collapsible');
    expect(component.expanded).toBe(false);
  });

  it('honours the initial state and toggles', () => {
    const component = skuel.make('collapsible', true);
    expect(component.expanded).toBe(true);
    component.toggle();
    expect(component.expanded).toBe(false);
  });
});

describe('collapsibleSidebar', () => {
  it('registers a shared store on init and reads through it', () => {
    const component = skuel.make('collapsibleSidebar', 'profile-sidebar', false);
    component.init();

    expect(skuel.alpine.store('profile-sidebar')).toEqual({ collapsed: false });
    expect(component.collapsed).toBe(false);
  });

  it('restores the persisted desktop state from localStorage', () => {
    localStorage.setItem('profile-sidebar-collapsed', 'true');

    const component = skuel.make('collapsibleSidebar', 'profile-sidebar', false);
    component.init();

    expect(component.collapsed).toBe(true);
  });

  it('toggle persists and announces the new state', () => {
    const announce = vi.spyOn(window.SKUEL, 'announce');
    const component = skuel.make('collapsibleSidebar', 'ku-sidebar', false);
    component.init();

    component.toggle();

    expect(component.collapsed).toBe(true);
    expect(localStorage.getItem('ku-sidebar-collapsed')).toBe('true');
    expect(announce).toHaveBeenCalledWith('Sidebar collapsed');
  });

  it('second instance reuses the shared store', () => {
    const first = skuel.make('collapsibleSidebar', 'shared-key', false);
    first.init();
    first.toggle();

    const second = skuel.make('collapsibleSidebar', 'shared-key', false);
    second.init();

    expect(second.collapsed).toBe(true);
  });
});
