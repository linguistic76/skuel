/**
 * The teacher revision form's feedback points, mounted by the real vendored
 * Alpine on the markup the Python renders (tests/js/fixtures/revision-form.html,
 * drift-pinned by tests/unit/ui/test_teacher_review_actions.py).
 *
 * Pins what the server-side pins cannot see: "+ Add feedback point" appends a
 * copy of the template row with its index filled in, the remove button takes
 * its own row away, fp_count counts every row added (so indices never repeat),
 * and the template's placeholder row never posts.
 */
import { afterEach, beforeAll, describe, expect, it } from 'vitest';
import { fixture, loadAlpine, settle } from './helpers/load-alpine.js';

function mount() {
  const host = document.createElement('div');
  host.innerHTML = fixture('revision-form.html');
  document.body.appendChild(host);
  return host;
}

function addButton(host) {
  return [...host.querySelectorAll('button')].find((b) => b.textContent.includes('Add feedback point'));
}

/** The fp_* fields the form would submit, by name. */
function posted(form) {
  return Object.fromEntries([...new FormData(form).entries()].filter(([name]) => name.startsWith('fp_')));
}

beforeAll(async () => {
  await loadAlpine();
});

afterEach(() => {
  document.body.innerHTML = '';
});

describe('revision form feedback points', () => {
  it('posts nothing but fp_count before a point is added', async () => {
    const host = mount();
    await settle();
    const form = host.querySelector('form');

    expect(posted(form)).toEqual({ fp_count: '0' });
  });

  it('adds copies of the template row, removes one, and posts the rest', async () => {
    const host = mount();
    await settle();
    const form = host.querySelector('form');

    addButton(host).click();
    addButton(host).click();
    await settle();
    const rows = host.querySelectorAll('[data-fp-row]:not(template [data-fp-row])');
    expect([...rows].map((r) => r.getAttribute('data-fp-row'))).toEqual(['0', '1']);

    form.querySelector('[name="fp_detail_0"]').value = 'first gap';
    form.querySelector('[name="fp_category_1"]').value = 'depth';
    form.querySelector('[name="fp_detail_1"]').value = 'second gap';
    rows[0].querySelector('[aria-label="Remove feedback point"]').click();
    await settle();

    expect(posted(form)).toEqual({ fp_count: '2', fp_category_1: 'depth', fp_detail_1: 'second gap' });
  });

  it('gives a point added after a removal a fresh index', async () => {
    const host = mount();
    await settle();
    const form = host.querySelector('form');

    addButton(host).click();
    await settle();
    form.querySelector('[aria-label="Remove feedback point"]').click();
    addButton(host).click();
    await settle();

    expect(posted(form)).toEqual({ fp_count: '2', fp_category_1: 'accuracy', fp_detail_1: '' });
  });
});
