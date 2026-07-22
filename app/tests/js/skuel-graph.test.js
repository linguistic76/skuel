/**
 * Vis.js Network helper pins for static/js/skuel.js (SKUEL.graph).
 *
 * The three graph surfaces — the lateral-relationship graph, the Explore
 * sidebar and the Explore fullscreen overlay — now share one option builder,
 * two styling passes and one click-to-navigate handler. These pin the parts
 * that differ per surface (sizing, physics, navigability) and the parts that
 * must not: the centre node is never a link, and confidence drives how
 * tentative a relationship edge looks.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { loadSkuel } from './helpers/load-skuel.js';

const COLORS = {
  ku: { background: '#8B5CF6' },
  ps: { background: '#14B8A6' },
  you: { background: '#3B82F6' },
  default: { background: '#6B7280' },
};

describe('SKUEL.graph.buildOptions', () => {
  beforeEach(() => {
    loadSkuel();
  });

  it('gives the relationship graph one global node size and shadows', () => {
    const options = window.SKUEL.graph.buildOptions(
      window.SKUEL.graph.PROFILES.relationship,
    );

    expect(options.nodes.size).toBe(16);
    expect(options.nodes.shadow).toBe(true);
    expect(options.edges.shadow).toBe(true);
    expect(options.physics.forceAtlas2Based.springLength).toBe(100);
    // Not a pan/zoom surface — no layout block, no view interaction.
    expect(options.interaction.zoomView).toBeUndefined();
    expect(options.layout).toBeUndefined();
  });

  it('leaves Explore surfaces to size nodes individually', () => {
    const sidebar = window.SKUEL.graph.buildOptions(
      window.SKUEL.graph.PROFILES.exploreSidebar,
    );

    expect(sidebar.nodes.size).toBeUndefined();
    expect(sidebar.nodes.font.size).toBe(11);
    expect(sidebar.interaction.zoomView).toBe(true);
    expect(sidebar.interaction.dragView).toBe(true);
    expect(sidebar.layout).toEqual({ improvedLayout: true });
  });

  it('loosens the springs on the expanded profile', () => {
    const sidebar = window.SKUEL.graph.PROFILES.exploreSidebar;
    const expanded = window.SKUEL.graph.PROFILES.exploreExpanded;

    expect(expanded.physics.springLength).toBeGreaterThan(sidebar.physics.springLength);
    expect(expanded.centerSize).toBeGreaterThan(sidebar.centerSize);
    expect(expanded.nodeSize).toBeGreaterThan(sidebar.nodeSize);
  });
});

describe('SKUEL.graph.styleNodes', () => {
  beforeEach(() => {
    loadSkuel();
  });

  const profile = () => window.SKUEL.graph.PROFILES.exploreSidebar;

  it('sizes the centre node up and colours by entity type', () => {
    const [center, leaf] = window.SKUEL.graph.styleNodes(
      [
        { id: 'ku_1', type: 'ku' },
        { id: 'ps_1', type: 'ps' },
      ],
      profile(),
      { centerUid: 'ku_1', colors: COLORS, hubCenter: false },
    );

    expect(center.size).toBe(24);
    expect(center.color).toBe(COLORS.ku);
    expect(leaf.size).toBe(14);
    expect(leaf.color).toBe(COLORS.ps);
  });

  it('normalises Neo4j PathStep labels to ps', () => {
    const styled = window.SKUEL.graph.styleNodes(
      [{ id: 'x', type: 'PathStep' }, { id: 'y', type: 'path_step' }],
      profile(),
      { centerUid: '', colors: COLORS, hubCenter: false },
    );

    expect(styled.map((n) => n._entityType)).toEqual(['ps', 'ps']);
  });

  it('paints the hub centre with the "you" colour', () => {
    const [node] = window.SKUEL.graph.styleNodes(
      [{ id: 'me', group: 'center', type: 'ku' }],
      profile(),
      { centerUid: '', colors: COLORS, hubCenter: true },
    );

    expect(node.color).toBe(COLORS.you);
  });

  it('carries filter metadata through', () => {
    const [node] = window.SKUEL.graph.styleNodes(
      [{ id: 'k', type: 'ku', learning_state: 'studying', is_pinned: true }],
      profile(),
      { centerUid: '', colors: COLORS, hubCenter: false },
    );

    expect(node._learningState).toBe('studying');
    expect(node._isPinned).toBe(true);
  });

  it('falls back to the default colour for unknown types', () => {
    const [node] = window.SKUEL.graph.styleNodes(
      [{ id: 'z', type: 'wat' }],
      profile(),
      { centerUid: '', colors: COLORS, hubCenter: false },
    );

    expect(node.color).toBe(COLORS.default);
  });

  it('tolerates a missing node list', () => {
    expect(
      window.SKUEL.graph.styleNodes(undefined, profile(), {
        centerUid: '',
        colors: COLORS,
        hubCenter: false,
      }),
    ).toEqual([]);
  });
});

describe('SKUEL.graph.styleEdges', () => {
  beforeEach(() => {
    loadSkuel();
  });

  it('applies the profile width and a default opacity', () => {
    const [edge] = window.SKUEL.graph.styleEdges(
      [{ from: 'a', to: 'b' }],
      window.SKUEL.graph.PROFILES.exploreSidebar,
    );

    expect(edge.width).toBe(1.5);
    expect(edge.color.opacity).toBe(0.6);
  });

  it('lets a server-supplied colour win over the default', () => {
    const [edge] = window.SKUEL.graph.styleEdges(
      [{ from: 'a', to: 'b', color: { opacity: 1, color: '#f00' } }],
      window.SKUEL.graph.PROFILES.exploreExpanded,
    );

    expect(edge.width).toBe(2);
    expect(edge.color).toEqual({ opacity: 1, color: '#f00' });
  });
});

describe('SKUEL.graph.styleEdgesByConfidence', () => {
  beforeEach(() => {
    loadSkuel();
  });

  it('maps priority to stroke width', () => {
    const styled = window.SKUEL.graph.styleEdgesByConfidence([
      { priority: 'critical' },
      { priority: 'high' },
      { priority: 'medium' },
      { priority: 'low' },
      {},
    ]);

    expect(styled.map((e) => e.width)).toEqual([4, 3, 2, 1, 2]);
  });

  it('dashes and fades low-confidence edges', () => {
    const [high, mid, low] = window.SKUEL.graph.styleEdgesByConfidence([
      { confidence: 0.9 },
      { confidence: 0.6 },
      { confidence: 0.2 },
    ]);

    expect(high.dashes).toBe(false);
    expect(high.color.opacity).toBe(1.0);
    expect(mid.dashes).toEqual([8, 4]);
    expect(mid.color.opacity).toBe(0.7);
    expect(low.dashes).toEqual([3, 3]);
    expect(low.color.opacity).toBe(0.5);
  });

  it('treats a missing confidence as fully confident', () => {
    const [edge] = window.SKUEL.graph.styleEdgesByConfidence([{ from: 'a' }]);

    expect(edge.color.opacity).toBe(1.0);
    expect(edge.dashes).toBe(false);
  });
});

describe('SKUEL.graph.attachClickNav', () => {
  let handler;
  let network;

  beforeEach(() => {
    loadSkuel();
    handler = null;
    network = {
      on: (event, fn) => {
        if (event === 'click') handler = fn;
      },
    };
  });

  const NODES = [
    { id: 'center_1', _entityType: 'ku' },
    { id: 'ku_2', _entityType: 'ku' },
    { id: 'hub', group: 'center', _entityType: 'ku' },
    { id: 'other_3', _entityType: 'task' },
  ];

  function navigate(nodeId) {
    const assign = vi.fn();
    vi.stubGlobal('location', {
      set href(value) {
        assign(value);
      },
    });
    handler({ nodes: nodeId === null ? [] : [nodeId] });
    vi.unstubAllGlobals();
    return assign;
  }

  beforeEach(() => {
    window.SKUEL.graph.attachClickNav(network, NODES, 'center_1', (node) =>
      node._entityType === 'ku' ? `/explore/ku/${node.id}` : null,
    );
  });

  it('navigates to a clicked neighbour', () => {
    expect(navigate('ku_2')).toHaveBeenCalledWith('/explore/ku/ku_2');
  });

  it('never navigates away from the centre node', () => {
    expect(navigate('center_1')).not.toHaveBeenCalled();
  });

  it('never navigates from a node marked as the hub centre', () => {
    expect(navigate('hub')).not.toHaveBeenCalled();
  });

  it('stays put when hrefFor declines the node', () => {
    expect(navigate('other_3')).not.toHaveBeenCalled();
  });

  it('ignores clicks on empty canvas', () => {
    expect(navigate(null)).not.toHaveBeenCalled();
  });
});

describe('SKUEL.graph.exploreHrefFor', () => {
  beforeEach(() => {
    loadSkuel();
  });

  it('prefers the server-resolved url (lateral mode)', () => {
    // Lateral nodes carry a Neo4j label as type but a canonical url; a path-step
    // whose label is "Entity" would derive nothing from _entityType — url wins.
    const node = { id: 'ps_1', _entityType: 'entity', url: '/explore/ps/ps_1' };
    expect(window.SKUEL.graph.exploreHrefFor(node)).toBe('/explore/ps/ps_1');
  });

  it('falls back to the short-form type in hub mode (no url)', () => {
    expect(window.SKUEL.graph.exploreHrefFor({ id: 'ku_1', _entityType: 'ku' })).toBe(
      '/explore/ku/ku_1',
    );
    expect(window.SKUEL.graph.exploreHrefFor({ id: 'ps_1', _entityType: 'ps' })).toBe(
      '/explore/ps/ps_1',
    );
  });

  it('returns null for a hub node with no route and no url', () => {
    expect(window.SKUEL.graph.exploreHrefFor({ id: 'you', _entityType: 'you' })).toBeNull();
  });
});

describe('Explore click-nav pipeline (styleNodes → exploreHrefFor → attachClickNav)', () => {
  let handler;
  const network = {
    on: (event, fn) => {
      if (event === 'click') handler = fn;
    },
  };

  beforeEach(() => {
    loadSkuel();
    handler = null;
  });

  function clickNavTarget(rawNodes, centerUid) {
    const styled = window.SKUEL.graph.styleNodes(rawNodes, window.SKUEL.graph.PROFILES.exploreSidebar, {
      centerUid,
      colors: COLORS,
      hubCenter: false,
    });
    window.SKUEL.graph.attachClickNav(network, styled, centerUid, window.SKUEL.graph.exploreHrefFor);

    const assign = vi.fn();
    vi.stubGlobal('location', {
      set href(value) {
        assign(value);
      },
    });
    handler({ nodes: [rawNodes[1].id] });
    vi.unstubAllGlobals();
    return assign;
  }

  it('navigates a lateral path-step node (label "Entity") via its server url — the bug fix', () => {
    // Lateral graph nodes: type is the Neo4j label (PathStep → "Entity"), so
    // _entityType would derive nothing; the server-resolved url carries it.
    const target = clickNavTarget(
      [
        { id: 'ps_center', type: 'Entity', entity_type: 'path_step', url: '/explore/ps/ps_center' },
        { id: 'ps_leaf', type: 'Entity', entity_type: 'path_step', url: '/explore/ps/ps_leaf' },
      ],
      'ps_center',
    );
    expect(target).toHaveBeenCalledWith('/explore/ps/ps_leaf');
  });

  it('navigates a hub short-form node with no url', () => {
    const target = clickNavTarget(
      [
        { id: 'ku_center', type: 'ku' },
        { id: 'ku_leaf', type: 'ku' },
      ],
      'ku_center',
    );
    expect(target).toHaveBeenCalledWith('/explore/ku/ku_leaf');
  });
});
