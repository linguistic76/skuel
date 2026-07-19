/**
 * searchFilters Alpine component pins for static/js/skuel.js.
 *
 * Pins the per-entity-type facet visibility map (keys mirror the Type
 * dropdown in ui/search/components.py — canonical EntityType values only,
 * per the emission rule), the badge labels, the active-facet counter, and
 * the scoped-Ask URL builder ($root-based — the $el regression is pinned).
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

  it('maps knowledge types to knowledge facets', () => {
    const component = skuel.make('searchFilters');
    component.entityType = 'ku';
    expect(component.isFilterVisible('sel_category')).toBe(true);
    expect(component.isFilterVisible('priority')).toBe(false);
  });

  it('user_entry has no facet groups', () => {
    const component = skuel.make('searchFilters');
    component.entityType = 'user_entry';
    expect(component.isFilterVisible('common')).toBe(false);
  });
});

describe('labels', () => {
  it('contextFilterLabel distinguishes knowledge from activity', () => {
    const component = skuel.make('searchFilters');
    expect(component.contextFilterLabel).toBe('Filters');
    component.entityType = 'path_step';
    expect(component.contextFilterLabel).toBe('Knowledge Filters');
    component.entityType = 'habit';
    expect(component.contextFilterLabel).toBe('Activity Filters');
  });

  it('getFilterLabel resolves entity_type badges and passes values through', () => {
    const component = skuel.make('searchFilters');
    expect(component.getFilterLabel('entity_type', 'ku')).toBe('Knowledge Units');
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
