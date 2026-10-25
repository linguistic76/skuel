/**
 * Chart.js colours follow the theme: chartVis on the cards the Python renders
 * (tests/js/fixtures/, drift-pinned by tests/unit/ui/test_chart_cards.py), mounted
 * by the real vendored Alpine and drawn by the real vendored Chart.js, over the
 * theme tokens of static/css/input.css.
 *
 * Chart.js draws on a canvas, which no CSS reaches. Pins: each chart's text, grid,
 * radial tick backdrop and arc borders resolve from the light tokens, and from the
 * dark ones when the page is dark; flipping `.dark` on <html> redraws every live
 * chart with the new colours from the config it fetched; a class change that keeps
 * the theme redraws nothing; the theme watcher is one observer that lives only
 * while a chart does; a card removed before its config arrives draws nothing and
 * reports no error.
 */
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';
import { fixture, loadAlpine, settle } from './helpers/load-alpine.js';

const APP_ROOT = join(dirname(fileURLToPath(import.meta.url)), '..', '..');
const INPUT_CSS = readFileSync(join(APP_ROOT, 'static', 'css', 'input.css'), 'utf8');
const CHART_JS = readFileSync(join(APP_ROOT, 'static', 'vendor', 'chart.js', 'chart.umd.js'), 'utf8');

/** The `:root` or `.dark` token block of input.css, as plain CSS. */
function tokenBlock(selector) {
  const escaped = selector.replace('.', '\\.');
  const match = INPUT_CSS.match(new RegExp('\\n  ' + escaped + ' \\{([\\s\\S]*?)\\n  \\}'));
  if (!match) throw new Error(selector + ' block not found in input.css');
  return selector + ' {' + match[1] + '\n}';
}

/** A token as the comma form of hsl()/hsla() Chart.js's colour parser reads. */
function token(theme, name, alpha) {
  const block = tokenBlock(theme === 'dark' ? '.dark' : ':root');
  const match = block.match(new RegExp('--' + name + ':\\s*([^;]+);'));
  if (!match) throw new Error('--' + name + ' not found');
  const parts = match[1].trim().split(/\s+/).join(', ');
  return alpha === undefined ? 'hsl(' + parts + ')' : 'hsla(' + parts + ', ' + alpha + ')';
}

function expected(theme) {
  return {
    text: token(theme, 'muted-foreground'),
    grid: token(theme, 'border'),
    backdrop: token(theme, 'card', 0.75),
    arcBorder: token(theme, 'card'),
  };
}

const PAYLOADS = {
  '/api/insights/charts/impact-distribution': { type: 'doughnut', data: { labels: ['Low'], datasets: [{ data: [3] }] } },
  '/api/insights/charts/domain-distribution': {
    type: 'bar',
    data: { labels: ['Tasks', 'Habits'], datasets: [{ label: 'Active Insights', data: [2, 1] }] },
    options: { responsive: true, scales: { y: { beginAtZero: true, ticks: { stepSize: 1 } } } },
  },
  '/api/insights/charts/type-distribution': { type: 'doughnut', data: { labels: ['A', 'B'], datasets: [{ data: [2, 1] }] } },
  '/api/insights/charts/action-rate': { type: 'doughnut', data: { labels: ['Actioned', 'Not'], datasets: [{ data: [25, 75] }] } },
  '/api/lifepath/alignment/chart': {
    type: 'radar',
    data: { labels: ['K', 'A', 'G', 'P', 'M'], datasets: [{ label: 'Alignment', data: [0.5, 0.4, 0.6, 0.3, 0.7] }] },
    options: { scales: { r: { min: 0, max: 1, ticks: { stepSize: 0.2 } } } },
  },
};

let held;
let themeObservers;

/** A 2D context with no-op drawing: enough for Chart.js to build and resolve a chart. */
function stubContext(canvas) {
  const target = {
    canvas,
    measureText: () => ({ width: 10, actualBoundingBoxAscent: 5, actualBoundingBoxDescent: 2 }),
    createLinearGradient: () => ({ addColorStop() {} }),
    createRadialGradient: () => ({ addColorStop() {} }),
    getLineDash: () => [],
  };
  return new Proxy(target, {
    get(t, key) {
      if (key in t) return t[key];
      // Chart.js reads `length` to tell a list of canvases from one canvas.
      if (typeof key === 'string' && key !== 'length' && key !== 'then' && /^[a-z]/.test(key)) {
        t[key] = () => {};
        return t[key];
      }
      return undefined;
    },
    set(t, key, value) {
      t[key] = value;
      return true;
    },
  });
}

beforeAll(async () => {
  const style = document.createElement('style');
  style.textContent = tokenBlock(':root') + '\n' + tokenBlock('.dark');
  document.head.appendChild(style);

  window.ResizeObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
  };
  HTMLCanvasElement.prototype.getContext = function getContext() {
    return stubContext(this);
  };
  new Function(CHART_JS)();
  window.Chart.defaults.animation = false;

  window.fetch = (url) => {
    const respond = () => ({ ok: true, status: 200, text: async () => JSON.stringify(PAYLOADS[String(url)]) });
    if (held) {
      return new Promise((resolve) => held.push(() => resolve(respond())));
    }
    return Promise.resolve(respond());
  };

  await loadAlpine();

  // Every observer watching <html>'s class attribute, while it is connected.
  const { observe, disconnect } = MutationObserver.prototype;
  MutationObserver.prototype.observe = function patchedObserve(target, options) {
    if (target === document.documentElement && options?.attributeFilter?.includes('class')) {
      themeObservers.add(this);
    }
    return observe.call(this, target, options);
  };
  MutationObserver.prototype.disconnect = function patchedDisconnect() {
    themeObservers.delete(this);
    return disconnect.call(this);
  };
});

beforeEach(() => {
  held = null;
  themeObservers = new Set();
  document.documentElement.className = '';
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

function liveCharts() {
  return Object.values(window.Chart.instances);
}

function chartFor(url) {
  return liveCharts().find((chart) => chart.canvas.closest('[x-data]').getAttribute('x-data').includes(url));
}

function expectTheme(theme) {
  const colours = expected(theme);
  const charts = liveCharts();
  expect(charts).toHaveLength(5);
  for (const chart of charts) {
    expect(chart.options.color).toBe(colours.text);
    expect(chart.legend.options.labels.color).toBe(colours.text);
  }
  const bar = chartFor('domain-distribution');
  expect(bar.scales.y.options.ticks.color).toBe(colours.text);
  expect(bar.scales.y.options.grid.color).toBe(colours.grid);
  expect(bar.scales.x.options.border.color).toBe(colours.grid);

  const radar = chartFor('alignment');
  expect(radar.scales.r.options.ticks.color).toBe(colours.text);
  expect(radar.scales.r.options.ticks.backdropColor).toBe(colours.backdrop);
  expect(radar.scales.r.options.grid.color).toBe(colours.grid);
  expect(radar.scales.r.options.angleLines.color).toBe(colours.grid);
  expect(radar.scales.r.options.pointLabels.color).toBe(colours.text);

  const arc = chartFor('impact-distribution').getDatasetMeta(0).data[0];
  expect(arc.options.borderColor).toBe(colours.arcBorder);
}

async function mountAll() {
  await mount('insight-charts.html');
  await mount('alignment-radar.html');
}

describe('chart colours from the theme tokens', () => {
  it('a light page draws every chart in the light tokens', async () => {
    await mountAll();
    expectTheme('light');
  });

  it('a dark page draws every chart in the dark tokens', async () => {
    document.documentElement.classList.add('dark');
    await mountAll();
    expectTheme('dark');
  });

  it('every colour it sets is one Chart.js parses, hover colour included', () => {
    for (const theme of ['light', 'dark']) {
      for (const colour of Object.values(expected(theme))) {
        expect(window.Chart.helpers.color(colour).valid, colour).toBe(true);
        expect(window.Chart.helpers.getHoverColor(colour), colour).toMatch(/^#[0-9A-F]{6,8}$/i);
      }
    }
  });
});

describe('a theme switch', () => {
  it('redraws every live chart in the new theme, from the config it fetched', async () => {
    await mountAll();
    const before = liveCharts();

    document.documentElement.classList.add('dark');
    await settle();

    for (const chart of before) expect(window.Chart.instances[chart.id]).toBeUndefined();
    expectTheme('dark');
    for (const chart of liveCharts()) {
      const url = chart.canvas.closest('[x-data]').getAttribute('x-data').match(/"([^"]+)"|'([^']+)'/).slice(1).find(Boolean);
      expect(chart.config.data).toEqual(PAYLOADS[url].data);
    }

    document.documentElement.classList.remove('dark');
    await settle();
    expectTheme('light');
  });

  it('a class change that keeps the theme redraws nothing', async () => {
    await mountAll();
    const ids = liveCharts().map((chart) => chart.id);

    document.documentElement.classList.add('overflow-hidden');
    await settle();

    expect(liveCharts().map((chart) => chart.id)).toEqual(ids);
  });
});

describe('the theme watcher', () => {
  it('is one observer while charts are live, and none once the last card leaves', async () => {
    const insights = await mount('insight-charts.html');
    const radar = await mount('alignment-radar.html');
    expect(themeObservers.size).toBe(1);

    insights.remove();
    await settle();
    expect(themeObservers.size).toBe(1);

    radar.remove();
    await settle();
    expect(themeObservers.size).toBe(0);
    expect(liveCharts()).toHaveLength(0);
  });

  it('a card removed before its config arrives draws, watches and reports nothing', async () => {
    held = [];
    const card = await mount('alignment-radar.html');
    card.remove();
    await settle();

    for (const release of held) release();
    await settle();
    await settle();

    expect(liveCharts()).toHaveLength(0);
    expect(themeObservers.size).toBe(0);
    expect(console.error).not.toHaveBeenCalled();
  });
});
