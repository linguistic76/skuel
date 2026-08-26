/**
 * searchFilters Alpine component pins for static/js/skuel.js.
 *
 * Pins the per-entity-type facet visibility map, the badge labels, the
 * active-facet counter, and the scoped-Ask URL builder ($root-based — the $el
 * regression is pinned).
 *
 * The map's keys are canonical EntityType values, per the emission rule. They
 * mirror the Type dropdown in ui/search/components.py with ONE deliberate
 * divergence: 'ku' is not a dropdown option — it is the mapping KNOWLEDGE MODE
 * reads to learn which four groups are the knowledge ones (see the comment on
 * entityTypeFilters). The cross-language drift check lives in
 * tests/unit/test_search_page_scope.py, which reads both sites; these
 * assertions cover the component's behaviour.
 *
 * Knowledge mode is driven by the NOUS topic, NOT by an entity type: nothing
 * writes entityType = 'ku' any more, so a test that reaches the knowledge
 * facets by assigning it would pass while testing a path no user can take.
 * The mutual exclusion of the two scope controls lives in the MARKUP
 * (x-bind:disabled), so it is pinned in test_search_page_scope.py § 7 — this
 * file asserts the state machine those bindings read.
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

  it('reveals the four knowledge facets from a NOUS topic, not a type', () => {
    const component = skuel.make('searchFilters');
    component.nousTopic = 'body';

    expect(component.isKnowledgeMode).toBe(true);
    ['sel_category', 'learning_level', 'content_type', 'educational_level'].forEach((group) => {
      expect(component.isFilterVisible(group)).toBe(true);
    });
    // The activity columns stay hidden — a Ku carries none of them.
    expect(component.isFilterVisible('priority')).toBe(false);
    expect(component.isFilterVisible('status')).toBe(false);
  });

  it('reads the knowledge groups from the ku map entry, not a second list', () => {
    const component = skuel.make('searchFilters');

    expect(component.knowledgeFilterGroups).toEqual(component.entityTypeFilters.ku);
  });

  it('leaves the four knowledge facets hidden while no NOUS topic is chosen', () => {
    // The regression PR #1156 knowingly shipped for one PR: Ku left the Type
    // dropdown, so nothing revealed these until knowledge mode existed.
    const component = skuel.make('searchFilters');
    component.entityType = 'task';

    expect(component.isKnowledgeMode).toBe(false);
    expect(component.isFilterVisible('sel_category')).toBe(false);
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

  it('offers exactly the six Activity Domains plus the ku knowledge-mode key', () => {
    const component = skuel.make('searchFilters');
    expect(Object.keys(component.entityTypeFilters).sort()).toEqual(
      ['choice', 'event', 'goal', 'habit', 'ku', 'principle', 'task'],
    );
  });
});

describe('the context-filter row', () => {
  it('opens for either scope facet and stays shut for neither', () => {
    const component = skuel.make('searchFilters');
    expect(component.showContextFilters).toBe(false);

    component.entityType = 'habit';
    expect(component.showContextFilters).toBe(true);

    component.entityType = '';
    component.nousTopic = 'body';
    expect(component.showContextFilters).toBe(true);
  });
});

describe('labels', () => {
  it('contextFilterLabel distinguishes knowledge from activity', () => {
    // Derived from the 'knowledge' marker group, not a second list of type
    // names — the list it replaced still named path_step after that type left.
    const component = skuel.make('searchFilters');
    expect(component.contextFilterLabel).toBe('Filters');
    component.nousTopic = 'body';
    expect(component.contextFilterLabel).toBe('Knowledge Filters');
    component.nousTopic = '';
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

describe('adoptScope (capture phase)', () => {
  function mountScopeAndContext() {
    document.body.innerHTML = `
      <div class="search-container">
        <select name="entity_type"><option value="task" selected>Tasks</option></select>
        <select name="nous"><option value="body" selected>Body</option></select>
        <select name="nous_subtopic"><option value="nervous-system" selected>NS</option></select>
        <div class="context-filters">
          <select name="status"><option value="completed" selected>Completed</option></select>
          <select name="sel_category"><option value="self_awareness" selected>SA</option></select>
        </div>
      </div>`;
    return document.querySelector('.search-container');
  }

  function change(name) {
    return { target: document.querySelector('[name="' + name + '"]') };
  }

  it('disables the columns the new scope does not own, synchronously', () => {
    // Synchronously: htmx serializes in its own change listener on the target,
    // and Alpine's reactive x-bind:disabled flushes a frame later — too late.
    const component = skuel.make('searchFilters');
    component.$root = mountScopeAndContext();
    component.nousTopic = 'body';

    document.querySelector('[name="nous"]').value = '';
    component.adoptScope(change('nous'));

    expect(component.nousTopic).toBe('');
    expect(document.querySelector('[name="sel_category"]').disabled).toBe(true);
    expect(document.querySelector('[name="status"]').disabled).toBe(true);
  });

  it('enables exactly the columns the new scope owns', () => {
    const component = skuel.make('searchFilters');
    component.$root = mountScopeAndContext();

    component.adoptScope(change('entity_type'));

    expect(component.entityType).toBe('task');
    expect(document.querySelector('[name="status"]').disabled).toBe(false);
    expect(document.querySelector('[name="sel_category"]').disabled).toBe(true);
  });

  it('reveals the knowledge columns when a NOUS topic arrives', () => {
    const component = skuel.make('searchFilters');
    component.$root = mountScopeAndContext();
    document.querySelector('[name="entity_type"]').value = '';

    component.adoptScope(change('nous'));

    expect(document.querySelector('[name="sel_category"]').disabled).toBe(false);
    expect(document.querySelector('[name="status"]').disabled).toBe(true);
  });

  it.each([
    ['clearing the topic', 'nous', ''],
    ['switching to another topic', 'nous', 'mind'],
    ['adopting an activity scope', 'entity_type', 'task'],
  ])('invalidates the dependent sub-topic when %s', (_label, control, value) => {
    // The sub-topic column is SERVER-owned: /search/subtopics re-renders it, and
    // that swap is a separate in-flight request. Until it lands the old value is
    // still enabled and every other control's hx-include names it — so a slow
    // connection would send a curriculum-only facet into an activity search.
    // A new topic orphans the old sub-topic just as surely as clearing one does.
    const component = skuel.make('searchFilters');
    component.$root = mountScopeAndContext();
    component.nousTopic = 'body';
    document.querySelector('[name="' + control + '"]').value = value;

    component.adoptScope(change(control));

    const subtopic = document.querySelector('[name="nous_subtopic"]');
    expect(subtopic.disabled).toBe(true);
    expect(subtopic.value).toBe('');
  });

  it('ignores a change on any control that is not a scope facet', () => {
    // EVERY control's change passes through the panel's capture listener, so
    // the handler must key on the two scope facets and touch nothing otherwise.
    // Pinned from a state only this handler could "correct": no scope is set,
    // yet status is enabled. A scope change would disable it; a status change
    // must leave it exactly as it found it.
    const component = skuel.make('searchFilters');
    component.$root = mountScopeAndContext();
    component.entityType = '';
    component.nousTopic = '';
    document.querySelector('[name="status"]').disabled = false;

    component.adoptScope(change('status'));

    expect(component.entityType).toBe('');
    expect(document.querySelector('[name="status"]').disabled).toBe(false);
    expect(document.querySelector('[name="nous_subtopic"]').value).toBe('nervous-system');
  });
});

describe('clearAllFilters', () => {
  function mountFilters() {
    document.body.innerHTML = `
      <div class="search-container">
        <select name="entity_type"><option value="task" selected>Tasks</option></select>
        <select name="nous" disabled><option value="" selected>All Nous</option></select>
      </div>`;
  }

  it('resets the NOUS topic too, so knowledge mode cannot survive it', () => {
    // The value loop writes select values directly and dispatches no per-control
    // event, so x-model never hears it — every modelled control must be reset in
    // state explicitly or Clear All leaves the page in a mode nothing shows.
    const component = skuel.make('searchFilters');
    mountFilters();
    component.entityType = 'task';
    component.nousTopic = 'body';

    component.clearAllFilters();

    expect(component.nousTopic).toBe('');
    expect(component.isKnowledgeMode).toBe(false);
    expect(component.showContextFilters).toBe(false);
  });

  it('re-fires the search from an ENABLED control when NOUS is disabled', () => {
    // With a Type selected the NOUS select is disabled, and htmx omits disabled
    // elements from a request — so the trigger falls back to the Type select
    // rather than dispatching into a control the request would skip.
    const component = skuel.make('searchFilters');
    mountFilters();
    const fired = [];
    document.querySelectorAll('select').forEach((select) => {
      select.addEventListener('change', () => fired.push(select.name));
    });

    component.clearAllFilters();

    expect(fired).toEqual(['entity_type']);
  });

  it('prefers the NOUS select while it is enabled', () => {
    const component = skuel.make('searchFilters');
    mountFilters();
    document.querySelector('[name="nous"]').removeAttribute('disabled');
    const fired = [];
    document.querySelectorAll('select').forEach((select) => {
      select.addEventListener('change', () => fired.push(select.name));
    });

    component.clearAllFilters();

    expect(fired).toEqual(['nous']);
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

  it('skips a disabled select — it keeps its value but rides no request', () => {
    // An out-of-scope context filter is disabled, not cleared, so returning to
    // that scope restores it visibly. Counting it would advertise a facet that
    // htmx withholds — the same lie as submitting it.
    const component = skuel.make('searchFilters');
    const root = document.createElement('div');
    root.innerHTML = `
      <div class="search-filters">
        <select><option value="active" selected>active</option></select>
        <select disabled><option value="self_awareness" selected>SA</option></select>
      </div>`;
    component.$root = root;

    component.updateFilterCount();

    expect(component.filterCount).toBe(1);
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
