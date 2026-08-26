/**
 * searchFilters Alpine component pins for static/js/skuel.js.
 *
 * Pins the per-entity-type facet visibility map, the badge labels, the
 * active-facet counter, and the scoped-Ask URL builder ($root-based — the $el
 * regression is pinned).
 *
 * The map's keys are canonical EntityType values, per the emission rule. They
 * mirror the Type dropdown in ui/search/components.py with ONE deliberate
 * divergence: 'ku' is kept as the staging point for the Nous-driven knowledge
 * mode (see the comment on entityTypeFilters). The cross-language drift check
 * lives in tests/unit/test_search_page_scope.py, which reads both sites; these
 * assertions cover the component's behaviour.
 *
 * ⚠️ This file previously asserted 'path_step' and 'user_entry' behaviour and
 * would have stayed GREEN after they were removed — nothing here reads the real
 * dropdown, so a deleted key just falls through `|| []`. A passing vitest run is
 * not evidence the vocabulary is current.
 */
import { beforeEach, describe, expect, it } from 'vitest';
import { loadSkuel } from './helpers/load-skuel.js';

let skuel;

beforeEach(() => {
  document.body.innerHTML = '';
  skuel = loadSkuel();
});

describe('facet visibility', () => {
  it('shows nothing without an entity type', () => {
    const component = skuel.make('searchFilters');
    expect(component.isFilterVisible('status')).toBe(false);
  });

  it('maps activity types to activity facets', () => {
    const component = skuel.make('searchFilters');
    component.entityType = 'task';
    expect(component.isFilterVisible('status')).toBe(true);
    expect(component.isFilterVisible('sel_category')).toBe(false);
  });

  it('maps ku to the knowledge facets it still stages for knowledge mode', () => {
    const component = skuel.make('searchFilters');
    component.entityType = 'ku';
    expect(component.isFilterVisible('sel_category')).toBe(true);
    expect(component.isFilterVisible('priority')).toBe(false);
  });

  it('reveals nothing for a type the page no longer offers', () => {
    // path_step, learning_path and user_entry left both the results and the
    // dropdown. isFilterVisible falls through `|| []`, so the failure mode is
    // silence — assert it rather than assume it.
    const component = skuel.make('searchFilters');
    ['path_step', 'learning_path', 'user_entry'].forEach((removed) => {
      component.entityType = removed;
      expect(component.isFilterVisible('common')).toBe(false);
      expect(component.isFilterVisible('sel_category')).toBe(false);
      expect(component.isFilterVisible('knowledge')).toBe(false);
    });
  });

  it('offers exactly the six Activity Domains plus the ku staging key', () => {
    const component = skuel.make('searchFilters');
    expect(Object.keys(component.entityTypeFilters).sort()).toEqual(
      ['choice', 'event', 'goal', 'habit', 'ku', 'principle', 'task'],
    );
  });
});

describe('labels', () => {
  it('contextFilterLabel distinguishes knowledge from activity', () => {
    // Derived from the 'knowledge' marker group, not a second list of type
    // names — the list it replaced still named path_step after that type left.
    const component = skuel.make('searchFilters');
    expect(component.contextFilterLabel).toBe('Filters');
    component.entityType = 'ku';
    expect(component.contextFilterLabel).toBe('Knowledge Filters');
    component.entityType = 'habit';
    expect(component.contextFilterLabel).toBe('Activity Filters');
  });

  it('contextFilterLabel does not call a removed type knowledge', () => {
    const component = skuel.make('searchFilters');
    component.entityType = 'path_step';
    expect(component.contextFilterLabel).toBe('Activity Filters');
  });

  it('getFilterLabel reads entity_type badges from the server-rendered dropdown', () => {
    // The Type dropdown (ui/search/components.py _ENTITY_TYPE_OPTIONS) is the
    // single label source — the component reads option text, no JS map.
    const component = skuel.make('searchFilters');
    const root = document.createElement('div');
    root.innerHTML = `
      <select name="entity_type">
        <option value="">All Types</option>
        <option value="task">Tasks</option>
      </select>`;
    component.$root = root;
    expect(component.getFilterLabel('entity_type', 'task')).toBe('Tasks');
    // 'ku' is a live result type but no longer a dropdown option, so it has no
    // badge text to read — the same fallback any unknown value takes.
    expect(component.getFilterLabel('entity_type', 'ku')).toBe('ku');
    expect(component.getFilterLabel('entity_type', 'unknown')).toBe('unknown');
    expect(component.getFilterLabel('status', 'active')).toBe('active');
  });
});

describe('updateFilterCount', () => {
  it('counts non-default selects and checked checkboxes only', () => {
    const component = skuel.make('searchFilters');
    const root = document.createElement('div');
    root.innerHTML = `
      <div class="search-filters">
        <select><option value="" selected></option></select>
        <select><option value="relevance" selected>relevance</option></select>
        <select><option value="active" selected>active</option></select>
        <input type="checkbox" checked>
        <input type="checkbox">
      </div>`;
    component.$root = root;

    component.updateFilterCount();

    // 1 non-default select + 1 checked checkbox; '' and 'relevance' excluded.
    expect(component.filterCount).toBe(2);
  });
});

describe('askHref (scoped Ask)', () => {
  function makeRoot({ query = '', nous = '', sub = '' } = {}) {
    const root = document.createElement('div');
    root.innerHTML = `
      <input name="query" value="${query}">
      <select name="nous"><option value="${nous}" selected>${nous}</option></select>
      <select name="nous_subtopic"><option value="${sub}" selected>${sub}</option></select>`;
    return root;
  }

  it('builds a fully scoped Ask URL', () => {
    const component = skuel.make('searchFilters');
    component.$root = makeRoot({ query: 'what is arete', nous: 'philosophy', sub: 'stoicism' });

    expect(component.askHref()).toBe(
      '/askesis?question=what+is+arete&nous=philosophy&nous_subtopic=stoicism',
    );
  });

  it('omits empty params and degrades to a bare /askesis', () => {
    const component = skuel.make('searchFilters');
    component.$root = makeRoot();

    expect(component.askHref()).toBe('/askesis');
  });
});
