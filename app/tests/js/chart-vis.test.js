/**
 * chartVis mounted by the real vendored Alpine on the cards the Python renders
 * (tests/js/fixtures/, drift-pinned by tests/unit/ui/test_chart_cards.py).
 *
 * Pins: one fetch per card, of the card's own URL; the fetched config handed
 * to Chart.js as it arrived (its own `type` picks the chart); a failed fetch
 * shown in the card; refresh() re-drawing in place; and the chart torn down
 * when the card leaves the page.
 */
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';
import { fixture, loadAlpine, settle } from './helpers/load-alpine.js';

let fetches;
let failNext;
let charts;

class FakeChart {
  constructor(ctx, config) {
    this.canvas = ctx.canvas;
    this.config = config;
    this.destroyed = false;
    charts.push(this);
  }
  destroy() { this.destroyed = true; }
}

function payloadFor(url) {
  return {
    type: url.includes('alignment') ? 'radar' : 'doughnut',
    data: { labels: ['A', 'B'], datasets: [{ label: url, data: [1, 2] }] },
    options: { responsive: true },
  };
}

beforeAll(async () => {
  HTMLCanvasElement.prototype.getContext = function getContext() {
    return { canvas: this };
  };
  window.Chart = FakeChart;
  window.fetch = async (url) => {
    fetches.push(String(url));
    if (failNext) {
      failNext = false;
      return { ok: false, status: 503, text: async () => '' };
    }
    return { ok: true, status: 200, text: async () => JSON.stringify(payloadFor(String(url))) };
  };
  await loadAlpine();
});

beforeEach(() => {
  fetches = [];
  failNext = false;
  charts = [];
  vi.spyOn(console, 'error').mockImplementation(() => {});
});

afterEach(async () => {
  document.body.replaceChildren();
  await settle();
  vi.restoreAllMocks();
});

async function mount(name) {
  document.body.insertAdjacentHTML('beforeend', fixture(name));
  await settle();
  await settle();
  return document.body.lastElementChild;
}

function component(el) {
  return window.Alpine.$data(el);
}

describe('chartVis on the insight charts', () => {
  it('fetches each card once, from its own URL', async () => {
    await mount('insight-charts.html');
    expect(fetches).toEqual([
      '/api/insights/charts/impact-distribution',
      '/api/insights/charts/domain-distribution',
      '/api/insights/charts/type-distribution',
      '/api/insights/charts/action-rate',
    ]);
  });

  it('hands each fetched config to Chart.js unchanged', async () => {
    await mount('insight-charts.html');
    expect(charts.map((chart) => chart.config)).toEqual(fetches.map(payloadFor));
    for (const chart of charts) {
      expect(chart.canvas.closest('[x-data]').getAttribute('x-data')).toContain(chart.config.data.datasets[0].label);
    }
  });
});

describe('chartVis on the alignment radar', () => {
  it('draws the radar the config names', async () => {
    await mount('alignment-radar.html');
    expect(fetches).toEqual(['/api/lifepath/alignment/chart']);
    expect(charts).toHaveLength(1);
    expect(charts[0].config.type).toBe('radar');
  });

  it('shows a failed fetch in the card and draws nothing', async () => {
    failNext = true;
    const card = await mount('alignment-radar.html');
    expect(charts).toHaveLength(0);
    expect(component(card).loading).toBe(false);
    expect(component(card).error).toBeTruthy();
    const slot = card.querySelector('[x-text="error"]');
    expect(slot.textContent).toBe(component(card).error);
  });

  it('refresh() redraws in place, from its own URL or a new one', async () => {
    const card = await mount('alignment-radar.html');
    const first = charts[0];

    component(card).refresh();
    await settle();
    await settle();
    expect(fetches).toEqual(['/api/lifepath/alignment/chart', '/api/lifepath/alignment/chart']);
    expect(first.destroyed).toBe(true);
    expect(charts).toHaveLength(2);

    component(card).refresh('/api/lifepath/alignment/chart?week=2');
    await settle();
    await settle();
    expect(fetches.at(-1)).toBe('/api/lifepath/alignment/chart?week=2');
    expect(charts[1].destroyed).toBe(true);
    expect(charts).toHaveLength(3);
  });

  it('tears the chart down when the card leaves the page', async () => {
    const card = await mount('alignment-radar.html');
    card.remove();
    await settle();
    expect(charts[0].destroyed).toBe(true);
  });
});
