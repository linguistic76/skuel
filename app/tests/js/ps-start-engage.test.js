/**
 * Starting a PathStep that has task templates, on the hero card the Python renders
 * (tests/js/fixtures/ps-hero-states.html, drift-pinned by tests/unit/ui/test_ps_hero_states.py),
 * with static/js/ps-detail.js as its component.
 *
 * The start is posted first and the engagement only once the start lands: the start carries
 * the server's refusals (the prerequisite gate, the enrollment cap), so a refused start must
 * spawn nothing. An engagement that fails after the start landed leaves the step Learning —
 * the start is real — and says so in a toast.
 *
 * htmx is stubbed: each request is recorded, and the test answers it by dispatching the
 * htmx:afterRequest the real library fires on the request's source element.
 */
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { afterEach, beforeAll, beforeEach, describe, expect, it } from 'vitest';
import { fixture, loadAlpine, settle } from './helpers/load-alpine.js';

const PS_DETAIL_JS = readFileSync(
  join(dirname(fileURLToPath(import.meta.url)), '..', '..', 'static', 'js', 'ps-detail.js'),
  'utf8',
);

let Alpine;
let requests;
let triggers;
let toasts;

function onToast(evt) {
  toasts.push(evt.detail);
}

function mount() {
  const host = document.createElement('div');
  host.innerHTML = fixture('ps-hero-states.html');
  const tasks = document.createElement('div');
  tasks.id = 'ps-tasks-fragment';
  host.appendChild(tasks);
  document.body.appendChild(host);
  return host;
}

async function notStartedAndClear(host) {
  await settle();
  const component = Alpine.$data(host.querySelector('[x-data]'));
  component.status = 'not_started';
  component._syncedStatus = 'not_started';
  component.blocking = [];
  await settle();
  return component;
}

/** Answer the recorded request at `index` the way htmx reports it on its source. */
function answer(index, successful, toastHeader = null) {
  const { path, source } = requests[index];
  const xhr = { getResponseHeader: (name) => (name === 'X-Toast-Message' ? toastHeader : null) };
  source.dispatchEvent(
    new CustomEvent('htmx:afterRequest', {
      detail: { requestConfig: { path }, successful, xhr },
    }),
  );
}

function paths() {
  return requests.map((request) => request.path);
}

beforeAll(async () => {
  new Function(PS_DETAIL_JS)();
  Alpine = await loadAlpine();
});

beforeEach(() => {
  requests = [];
  triggers = [];
  toasts = [];
  window.htmx = {
    ajax: (method, path, options) => requests.push({ method, path, source: options.source }),
    trigger: (element, name) => triggers.push([element.id, name]),
  };
  window.addEventListener('toast', onToast);
});

afterEach(() => {
  window.removeEventListener('toast', onToast);
  document.body.replaceChildren();
});

describe('Starting a step with task templates', () => {
  it('posts the start alone, and engages only once the start lands', async () => {
    const host = mount();
    const component = await notStartedAndClear(host);

    component.advance();
    expect(paths()).toEqual(['/explore/ps/ps.test.hero/progress']);
    expect(component.status).toBe('learning');

    answer(0, true);
    expect(paths()).toEqual(['/explore/ps/ps.test.hero/progress', '/api/ps/ps.test.hero/engage']);
    expect(triggers).toEqual([]);

    answer(1, true);
    expect(triggers).toEqual([['ps-tasks-fragment', 'ps-engaged']]);
    expect(component.status).toBe('learning');
  });

  it('spawns nothing when the start is refused, and rolls the step back', async () => {
    const host = mount();
    const component = await notStartedAndClear(host);

    component.advance();
    answer(0, false, 'Master First before starting this step.');

    expect(paths()).toEqual(['/explore/ps/ps.test.hero/progress']);
    expect(component.status).toBe('not_started');
  });

  it('keeps the step Learning when only the engagement fails, and says so', async () => {
    const host = mount();
    const component = await notStartedAndClear(host);

    component.advance();
    answer(0, true);
    answer(1, false);

    expect(component.status).toBe('learning');
    expect(triggers).toEqual([]);
    expect(toasts).toEqual([
      { message: "Could not set up this step's activities — please try again", type: 'error' },
    ]);
  });

  it('leaves a failed engagement to its own toast when the server sent one', async () => {
    const host = mount();
    const component = await notStartedAndClear(host);

    component.advance();
    answer(0, true);
    answer(1, false, 'Nothing to engage with.');

    expect(component.status).toBe('learning');
    expect(toasts).toEqual([]);
  });

  it('posts nothing while a prerequisite blocks the start', async () => {
    const host = mount();
    await settle();
    const component = Alpine.$data(host.querySelector('[x-data]'));
    component.status = 'not_started';
    await settle();

    component.advance();

    expect(component.startBlocked).toBe(true);
    expect(requests).toEqual([]);
    expect(component.status).toBe('not_started');
  });
});
