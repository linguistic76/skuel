/**
 * chartVis takes one argument: the URL of a Chart.js config. The config's own
 * `type` picks the chart kind, so there is no second argument to pass.
 */
import { expect, it } from 'vitest';
import { loadSkuel } from './helpers/load-skuel.js';

it('chartVis is registered with the data URL as its only parameter', () => {
  const skuel = loadSkuel();
  expect(skuel.alpine._registry.get('chartVis').length).toBe(1);
});
