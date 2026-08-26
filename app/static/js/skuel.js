/**
 * SKUEL - Core JavaScript utilities and Alpine.js components
 * ===========================================================
 *
 * Centralized Alpine.data() components for reuse across SKUEL.
 * Each component is self-contained with its own state and methods.
 *
 * Architecture:
 * - Alpine.js handles UI state (modals, sidebars, toggles)
 * - HTMX handles server communication (form submissions, data loading)
 * - fetch() used only for hybrid patterns (drag-drop reschedule)
 */

(function() {
    'use strict';

    // =========================================================================
    // SKUEL Namespace
    // =========================================================================

    window.SKUEL = window.SKUEL || {};

    window.SKUEL.debug = function(message, data) {
        if (console && console.log) {
            console.log('[SKUEL]', message, data || '');
        }
    };

    /**
     * Read the csrf_token cookie for double-submit CSRF (see adapters/inbound/csrf.py).
     * Attach the return value as the X-CSRF-Token header on every mutating fetch().
     * Returns '' when the cookie is absent — safe for truthiness-guarded consumers.
     */
    window.SKUEL.csrf = function() {
        var m = document.cookie.match(/(?:^|; )csrf_token=([^;]+)/);
        return m ? decodeURIComponent(m[1]) : '';
    };

    // -------------------------------------------------------------------------
    // JSON fetch helpers
    //
    // HTMX owns server communication; fetch() is reserved for hybrid patterns
    // (drag-drop reschedule, bulk selection, graph payloads). These two helpers
    // are the ONLY place those call sites encode the CSRF header, the
    // status check, and JSON parsing — a call site handles failure once, in a
    // single .catch()/catch block.
    //
    // Both reject with an Error carrying `.status` (HTTP code) and `.payload`
    // (parsed body, when the server sent JSON). The message prefers the
    // server's own wording, reading the three error shapes SKUEL emits:
    // `{error: {message}}` (Result envelope), `{detail}` (FastHTML
    // HTTPException), `{message}`.
    // -------------------------------------------------------------------------

    function _errorMessage(payload, status) {
        if (payload) {
            if (payload.error && payload.error.message) return payload.error.message;
            if (payload.detail) return payload.detail;
            if (payload.message) return payload.message;
        }
        return 'Request failed (' + status + ')';
    }

    function _requestJson(url, init) {
        return fetch(url, init).then(function(response) {
            // A body is not guaranteed to be JSON (502 HTML, 204 empty) — parse
            // defensively so the status check still reports a useful message.
            return response.text().then(function(text) {
                var payload = null;
                if (text) {
                    try {
                        payload = JSON.parse(text);
                    } catch (e) {
                        payload = null;
                    }
                }
                if (!response.ok) {
                    var error = new Error(_errorMessage(payload, response.status));
                    error.status = response.status;
                    error.payload = payload;
                    throw error;
                }
                return payload;
            });
        });
    }

    /**
     * GET a JSON endpoint. Rejects on any non-2xx.
     *
     * @param {string} url
     * @returns {Promise<Object>} parsed response body
     */
    window.SKUEL.getJson = function(url) {
        return _requestJson(url, undefined);
    };

    /**
     * Send a JSON body to a mutating endpoint with the CSRF header attached.
     * Rejects on any non-2xx.
     *
     * @param {string} url
     * @param {Object} [body] - serialized as JSON; omit for bodyless mutations
     * @param {Object} [options] - {method: 'POST'|'PATCH'|'PUT'|'DELETE'}
     * @returns {Promise<Object>} parsed response body
     */
    window.SKUEL.postJson = function(url, body, options) {
        options = options || {};
        var init = {
            method: options.method || 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRF-Token': window.SKUEL.csrf()
            }
        };
        if (body !== undefined) {
            init.body = JSON.stringify(body);
        }
        return _requestJson(url, init);
    };

    /**
     * Refresh the view after a fetch() mutation.
     *
     * SKUEL swaps partials, so prefer re-fetching the affected fragment: a full
     * document reload discards scroll position and unrelated Alpine state. Pass
     * the selector of an HTMX-bound container when one exists; the reload
     * fallback covers pages whose lists are rendered whole with no fragment
     * route to re-request.
     *
     * @param {string} [selector] - CSS selector of an HTMX container to refresh
     */
    window.SKUEL.refreshAfterMutation = function(selector) {
        if (selector && window.htmx) {
            var target = document.querySelector(selector);
            if (target) {
                window.htmx.trigger(target, 'refresh');
                return;
            }
        }
        window.location.reload();
    };

    // -------------------------------------------------------------------------
    // CSRF double-submit: attach X-CSRF-Token on every mutating HTMX call.
    // Registered on `document` at script-parse time (NOT inside DOMContentLoaded)
    // so it is ready before HTMX processes any `hx-trigger="load"` element —
    // otherwise a load-fired POST (e.g. the /search→Askesis auto-run) can race
    // ahead of listener registration and 403. The event bubbles to document.
    // Paired with adapters/inbound/csrf.py (cookie is readable, HttpOnly=False).
    // -------------------------------------------------------------------------
    document.addEventListener('htmx:configRequest', function(event) {
        var method = (event.detail.verb || '').toUpperCase();
        if (method === 'GET' || method === 'HEAD' || method === 'OPTIONS') {
            return;
        }
        var token = window.SKUEL.csrf();
        if (token) {
            event.detail.headers['X-CSRF-Token'] = token;
        }
    });

    /**
     * Live Region Announcer - Task 10: HTMX + Screen Reader Integration
     * Announces dynamic content changes to screen readers via ARIA live regions.
     *
     * @param {string} message - Message to announce
     * @param {string} priority - 'polite' (default) or 'assertive'
     */
    window.SKUEL.announce = function(message, priority) {
        priority = priority || 'polite';

        var liveRegion = document.getElementById('live-region');
        if (!liveRegion) {
            console.warn('[SKUEL] Live region not found');
            return;
        }

        // Set aria-live priority
        liveRegion.setAttribute('aria-live', priority);

        // Set message
        liveRegion.textContent = message;

        // Clear after 3 seconds to avoid stale announcements
        setTimeout(function() {
            liveRegion.textContent = '';
        }, 3000);
    };

    // =========================================================================
    // HTMX Integration - Task 10: Accessibility Announcements
    // =========================================================================

    /**
     * One route taxonomy for both announcement hooks: `verb` is announced while
     * the request is in flight (htmx:beforeRequest), `done` after the swap
     * lands (htmx:afterSwap). First match wins, so order is significant.
     *
     * A null `verb` means the route has no in-flight wording — the generic
     * "Loading..." is announced instead.
     */
    var ANNOUNCE_ROUTES = [
        { match: ['/create'], verb: 'Creating', done: 'Created successfully' },
        { match: ['/update', '/edit', '/save'], verb: 'Updating', done: 'Updated successfully' },
        { match: ['/delete', '/remove'], verb: 'Deleting', done: 'Deleted successfully' },
        { match: ['/complete'], verb: 'Completing', done: 'Completed successfully' },
        { match: ['/upload'], verb: 'Uploading', done: 'Uploaded successfully' },
        { match: ['/track'], verb: 'Tracking', done: 'Tracked successfully' },
        { match: ['/enroll'], verb: 'Enrolling', done: 'Enrolled successfully' },
        { match: ['/toggle', '/status'], verb: 'Updating status', done: 'Status updated' },
        { match: ['/decide'], verb: null, done: 'Decision recorded' }
    ];

    /**
     * Resolve the announcement entry for a request path.
     *
     * @param {string} path - request path (empty string for GETs we skip)
     * @returns {Object|null} the matching ANNOUNCE_ROUTES entry, or null
     */
    window.SKUEL.announceRouteFor = function(path) {
        if (!path) return null;
        for (var i = 0; i < ANNOUNCE_ROUTES.length; i++) {
            var route = ANNOUNCE_ROUTES[i];
            for (var j = 0; j < route.match.length; j++) {
                if (path.includes(route.match[j])) {
                    return route;
                }
            }
        }
        return null;
    };

    /**
     * HTMX event handlers for accessibility announcements.
     * Announces loading states, success, and errors to screen readers.
     */
    document.addEventListener('DOMContentLoaded', function() {
        var body = document.body;

        // HTMX CSRF header is wired at script-parse time above (races ahead of
        // any load-triggered POST). Native (non-HTMX) form CSRF is handled here.

        // Native form submissions (non-HTMX) — guarantee the hidden csrf_token
        // input exists and carries the current cookie value. Fires on capture
        // so we run before any other submit handler and before serialization.
        body.addEventListener('submit', function(event) {
            var form = event.target;
            if (!form || form.tagName !== 'FORM') return;
            var method = (form.method || 'GET').toUpperCase();
            if (method === 'GET' || method === 'HEAD') return;
            if (form.hasAttribute('hx-post') || form.hasAttribute('hx-put') ||
                form.hasAttribute('hx-delete') || form.hasAttribute('hx-patch')) {
                return;
            }
            var token = window.SKUEL.csrf();
            if (!token) return;
            var existing = form.querySelector('input[name="csrf_token"]');
            if (existing) {
                existing.value = token;
            } else {
                var input = document.createElement('input');
                input.type = 'hidden';
                input.name = 'csrf_token';
                input.value = token;
                form.appendChild(input);
            }
        }, true);

        // Before HTMX request - announce loading state
        body.addEventListener('htmx:beforeRequest', function(event) {
            var target = event.detail.target;
            var elt = event.detail.elt;  // The element that triggered the request

            // Add aria-busy to target element
            if (target) {
                target.setAttribute('aria-busy', 'true');
            }

            // Check for custom loading announcement on triggering element
            var loadingMessage = null;
            if (elt && elt.getAttribute) {
                loadingMessage = elt.getAttribute('data-announce-loading');
            }

            // If custom loading message exists, use it
            if (loadingMessage) {
                window.SKUEL.announce(loadingMessage + '...', 'polite');
                return;
            }

            // Otherwise, auto-detect from path/verb.
            // htmx 1.9 carries verb (lowercase) and path on requestConfig —
            // event.detail.verb / event.detail.path do not exist.
            var requestConfig = event.detail.requestConfig || {};
            var verb = (requestConfig.verb || 'get').toUpperCase();
            var path = requestConfig.path || '';

            // Announce for non-GET requests (mutations). The verb lookup covers
            // every mutating verb — DELETE /tasks/delete announces "Deleting",
            // not the generic "Loading" it used to get.
            if (verb !== 'GET') {
                var route = window.SKUEL.announceRouteFor(path);
                var operation = (route && route.verb) || 'Loading';
                window.SKUEL.announce(operation + '...', 'polite');
            }
        });

        // After HTMX request succeeds
        body.addEventListener('htmx:afterSwap', function(event) {
            var target = event.detail.target;
            var elt = event.detail.elt;  // The element that triggered the request

            // Remove aria-busy from target element
            if (target) {
                target.setAttribute('aria-busy', 'false');
            }

            var successMessage = null;

            // 1. Check for data-announce on triggering element (highest priority)
            if (elt && elt.getAttribute) {
                successMessage = elt.getAttribute('data-announce');
            }

            // 2. Check for data-announce in swapped content
            if (!successMessage && target) {
                var announceEl = target.querySelector('[data-announce]');
                if (announceEl) {
                    successMessage = announceEl.getAttribute('data-announce');
                }
            }

            // 3. Auto-detect from path if no custom message — mutations only.
            // htmx 1.9's pathInfo has requestPath/finalRequestPath (no .path);
            // verb lives on requestConfig (lowercase).
            if (!successMessage) {
                var requestConfig = event.detail.requestConfig || {};
                var verb = (requestConfig.verb || 'get').toUpperCase();
                var path = verb !== 'GET' ? (requestConfig.path || '') : '';
                var route = window.SKUEL.announceRouteFor(path);
                if (route) {
                    successMessage = route.done;
                }
            }

            if (successMessage) {
                window.SKUEL.announce(successMessage, 'polite');
            }
        });

        // After HTMX request fails
        body.addEventListener('htmx:responseError', function(event) {
            var target = event.detail.target;

            // Remove aria-busy from target element
            if (target) {
                target.setAttribute('aria-busy', 'false');
            }

            // Announce error
            var status = event.detail.xhr ? event.detail.xhr.status : null;
            var errorMessage = 'An error occurred. Please try again.';

            // More specific error messages
            if (status === 404) {
                errorMessage = 'Item not found';
            } else if (status === 403) {
                errorMessage = 'Permission denied';
            } else if (status === 400) {
                errorMessage = 'Invalid request';
            } else if (status >= 500) {
                errorMessage = 'Server error. Please try again later.';
            }

            window.SKUEL.announce(errorMessage, 'assertive');
        });

        // When HTMX encounters a client error
        body.addEventListener('htmx:sendError', function(event) {
            var target = event.detail.target;

            // Remove aria-busy from target element
            if (target) {
                target.setAttribute('aria-busy', 'false');
            }

            // Announce network error
            window.SKUEL.announce('Network error. Please check your connection.', 'assertive');
        });
    });

    // =========================================================================
    // Vis.js Network helpers
    //
    // Three networks are rendered in this file — the lateral-relationship graph
    // on detail pages, the Explore sidebar graph, and the Explore fullscreen
    // overlay. They differ only in sizing, physics tuning and where a node
    // click navigates, so the option literal, the styling passes and the
    // click-to-navigate handler live here once. Sizing lives in GRAPH_PROFILES;
    // a component picks a profile rather than re-typing the numbers.
    // =========================================================================

    window.SKUEL.graph = {};

    /**
     * Per-surface sizing and physics. `nodeFontColor`/`nodeFontStroke` are the
     * Explore surfaces' label treatment; the relationship graph overrides font
     * wholesale via `nodeFont`.
     */
    window.SKUEL.graph.PROFILES = {
        // Lateral-relationship graph on entity detail pages.
        relationship: {
            // One size for every node — this surface does not style per-node.
            globalNodeSize: 16,
            nodeFont: { size: 14, color: '#333' },
            nodeBorderWidth: 2,
            nodeShadow: true,
            edgeWidth: 2,
            edgeShadow: true,
            physics: {
                gravitationalConstant: -50,
                centralGravity: 0.01,
                springLength: 100,
                springConstant: 0.08
            },
            maxVelocity: 50,
            stabilization: 150,
            tooltipDelay: 200
        },
        // Explore sidebar — compact, must read in a narrow column.
        exploreSidebar: {
            centerSize: 24,
            nodeSize: 14,
            centerFontSize: 14,
            nodeFontSize: 11,
            edgeWidth: 1.5,
            physics: {
                gravitationalConstant: -40,
                centralGravity: 0.015,
                springLength: 80,
                springConstant: 0.06
            },
            maxVelocity: 30,
            stabilization: 100,
            tooltipDelay: 300,
            navigable: true
        },
        // Explore fullscreen overlay — roomier nodes, looser springs.
        exploreExpanded: {
            centerSize: 30,
            nodeSize: 18,
            centerFontSize: 16,
            nodeFontSize: 13,
            edgeWidth: 2,
            physics: {
                gravitationalConstant: -60,
                centralGravity: 0.01,
                springLength: 120,
                springConstant: 0.04
            },
            maxVelocity: 30,
            stabilization: 150,
            tooltipDelay: 300,
            navigable: true
        }
    };

    /** True when the Vis.js Network library finished loading. */
    window.SKUEL.graph.ready = function() {
        return typeof vis !== 'undefined' && !!vis.Network;
    };

    /**
     * Build the Vis.js options object for a profile.
     *
     * @param {Object} profile - an entry from SKUEL.graph.PROFILES
     * @returns {Object} vis.Network options
     */
    window.SKUEL.graph.buildOptions = function(profile) {
        var nodes = { shape: 'dot' };
        if (profile.globalNodeSize) {
            // Explore surfaces size every node individually (center vs. leaf);
            // the relationship graph sets one global size instead.
            nodes.size = profile.globalNodeSize;
        }
        nodes.font = profile.nodeFont || {
            size: profile.nodeFontSize,
            color: '#64748B',
            strokeWidth: 2,
            strokeColor: '#fff'
        };
        if (profile.nodeBorderWidth) nodes.borderWidth = profile.nodeBorderWidth;
        if (profile.nodeShadow) nodes.shadow = true;

        var edges = { width: profile.edgeWidth, smooth: { type: 'continuous' } };
        if (profile.edgeShadow) edges.shadow = true;

        var options = {
            nodes: nodes,
            edges: edges,
            physics: {
                forceAtlas2Based: profile.physics,
                maxVelocity: profile.maxVelocity,
                solver: 'forceAtlas2Based',
                timestep: 0.35,
                stabilization: { iterations: profile.stabilization }
            },
            interaction: {
                hover: true,
                tooltipDelay: profile.tooltipDelay
            }
        };
        if (profile.navigable) {
            options.interaction.zoomView = true;
            options.interaction.dragView = true;
            options.layout = { improvedLayout: true };
        }
        return options;
    };

    /**
     * Style Explore nodes by entity type, sized for the given profile.
     *
     * Carries `_entityType` / `_learningState` / `_isPinned` onto each node so
     * the sidebar filter tabs can re-colour without refetching.
     *
     * @param {Array} nodes - raw nodes from the graph API
     * @param {Object} profile - an entry from SKUEL.graph.PROFILES
     * @param {Object} ctx - {centerUid, colors, hubCenter}
     * @returns {Array} styled node objects
     */
    window.SKUEL.graph.styleNodes = function(nodes, profile, ctx) {
        return (nodes || []).map(function(node) {
            // Lateral mode carries the canonical entity_type ("path_step", "ku");
            // node.type there is the Neo4j label (a PathStep's is "Entity"), which
            // would mis-colour. Hub mode has no entity_type, so fall back to its
            // short-form node.type ("ku"/"ps"/"you").
            var nodeType = (node.entity_type || node.type || '').toLowerCase();
            // Map Neo4j labels to simple types
            if (nodeType === 'pathstep' || nodeType === 'path_step') nodeType = 'ps';
            var isCenter = (node.id === ctx.centerUid) || (node.group === 'center');
            var colors = ctx.colors[nodeType] || ctx.colors.default;

            if (isCenter && ctx.hubCenter) {
                colors = ctx.colors.you;
            }

            return Object.assign({}, node, {
                color: colors,
                size: isCenter ? profile.centerSize : profile.nodeSize,
                font: {
                    size: isCenter ? profile.centerFontSize : profile.nodeFontSize,
                    color: '#64748B',
                    strokeWidth: 2,
                    strokeColor: '#ffffff'
                },
                borderWidth: isCenter ? 3 : 1.5,
                // Store metadata for filtering
                _entityType: nodeType,
                _learningState: node.learning_state || null,
                _isPinned: node.is_pinned || false
            });
        });
    };

    /**
     * Style Explore edges at the profile's width, keeping any server-supplied
     * colour but defaulting the opacity.
     *
     * @param {Array} edges - raw edges from the graph API
     * @param {Object} profile - an entry from SKUEL.graph.PROFILES
     * @returns {Array} styled edge objects
     */
    window.SKUEL.graph.styleEdges = function(edges, profile) {
        return (edges || []).map(function(edge) {
            return Object.assign({}, edge, {
                width: profile.edgeWidth,
                color: Object.assign({ opacity: 0.6 }, edge.color || {}),
                smooth: { type: 'continuous' }
            });
        });
    };

    /**
     * Style lateral-relationship edges by confidence and priority: priority
     * drives stroke width, confidence drives dashing and opacity so a weakly
     * inferred link reads as tentative.
     *
     * @param {Array} edges - raw edges from the lateral graph API
     * @returns {Array} styled edge objects
     */
    window.SKUEL.graph.styleEdgesByConfidence = function(edges) {
        var priorityWidthMap = { critical: 4, high: 3, medium: 2, low: 1 };
        return (edges || []).map(function(edge) {
            var confidence = typeof edge.confidence === 'number' ? edge.confidence : 1.0;
            var priority = edge.priority || 'medium';
            var width = priorityWidthMap[priority] || 2;
            var dashes = false;
            var opacity = 1.0;

            if (confidence >= 0.8) {
                dashes = false;
                opacity = 1.0;
            } else if (confidence >= 0.5) {
                dashes = [8, 4];
                opacity = 0.7;
            } else {
                dashes = [3, 3];
                opacity = 0.5;
            }

            return Object.assign({}, edge, {
                width: width,
                dashes: dashes,
                color: Object.assign({}, edge.color || {}, { opacity: opacity })
            });
        });
    };

    /**
     * Navigate on node click. The centre node is never a link — it is the page
     * you are already on.
     *
     * @param {Object} network - vis.Network instance
     * @param {Array} nodes - the styled nodes rendered into that network
     * @param {string} centerUid - UID of the centre node
     * @param {Function} hrefFor - node => URL string, or null for "not a link"
     */
    window.SKUEL.graph.attachClickNav = function(network, nodes, centerUid, hrefFor) {
        network.on('click', function(params) {
            if (params.nodes.length === 0) return;
            var nodeId = params.nodes[0];
            var node = nodes.find(function(n) { return n.id === nodeId; });
            if (!node || node.id === centerUid || node.group === 'center') return;
            var href = hrefFor(node);
            if (href) {
                window.location.href = href;
            }
        });
    };

    /**
     * Resolve the Explore graph detail-page URL for a clicked node.
     *
     * Lateral mode: the server attaches `node.url`, resolved from the canonical
     * entity_type (node.type is a Neo4j label there, not a route) — always prefer it.
     * Hub mode: no url is emitted, so fall back to the short-form `_entityType`
     * ("ku"/"ps"), which maps straight to `/explore/{type}/{id}`.
     *
     * @param {Object} node - a styled graph node
     * @returns {string|null} detail-page URL, or null when the node is not a link
     */
    window.SKUEL.graph.exploreHrefFor = function(node) {
        if (node.url) return node.url;
        var type = node._entityType;
        return (type === 'ku' || type === 'ps') ? '/explore/' + type + '/' + node.id : null;
    };

    // =========================================================================
    // Alpine.js Component Definitions
    // =========================================================================

    document.addEventListener('alpine:init', function() {

        // ---------------------------------------------------------------------
        // Search Filters Component (Horizontal Layout)
        // ---------------------------------------------------------------------
        /**
         * Search filter bar component.
         * Manages entity type selection and dynamic filter visibility.
         *
         * @returns {Object} Alpine.js component
         * @property {string} entityType - Currently selected entity type
         * @property {boolean} showAdvanced - Advanced filter panel visibility
         * @property {Object} entityTypeFilters - Filter groups by entity type
         * @property {Object} entityTypeLabels - Display labels for entity types
         * @property {boolean} showContextFilters - Computed: show context filters row
         * @property {string} contextFilterLabel - Computed: label for filter section
         * @property {boolean} hasActiveFilters - Computed: has any active filters
         *
         * @example
         * <div x-data="searchFilters()">
         *   <button @click="entityType = 'task'">Tasks</button>
         * </div>
         */
        Alpine.data('searchFilters', function() {
            return {
                entityType: '',
                showAdvanced: false,

                // Layout state (horizontal bar + mobile drawer)
                filtersOpen: false,   // mobile: off-canvas filter drawer open?
                moreFilters: false,   // desktop: advanced facets revealed?
                isDesktop: true,      // ≥1024px — set from matchMedia in init()
                filterCount: 0,       // active facets, shown on the mobile trigger badge

                // Entity type to filter group mapping. Values are canonical
                // EntityType values, per the emission rule (aliases like 'ps'
                // are input-only). 'common' and 'knowledge' are MARKERS — no
                // control is named either; every other entry is a field name
                // that isFilterVisible() reveals.
                //
                // path_step / learning_path / user_entry are gone: they left
                // both the /search results (SEARCH_PAGE_ENTITY_TYPES, PR #1155)
                // and the Type dropdown, so no selection can reach them.
                //
                // 'ku' is KEPT DELIBERATELY — the one place the three vocabulary
                // sites diverge, for one PR. It is NOT keeping the four knowledge
                // filters (sel_category, learning_level, content_type,
                // educational_level) alive: nothing can set entityType to 'ku'
                // once Ku leaves the dropdown, so they are unreachable either way
                // until the next PR re-homes them onto a Nous-driven knowledge
                // mode. What this entry keeps is the MAPPING that PR's predicate
                // is built from — which four groups are the knowledge ones — and
                // Ku is still a live result type, so the key names something real.
                // See deferred-work.md § "/search Facet Redesign": this is a
                // filter-GROUP map, not the dropdown vocabulary.
                entityTypeFilters: {
                    'task': ['common', 'status', 'priority'],
                    'goal': ['common', 'status', 'priority'],
                    'habit': ['common', 'status', 'frequency'],
                    'event': ['common', 'status', 'priority', 'event_type'],
                    'choice': ['common', 'status', 'urgency'],
                    'principle': ['common', 'status', 'strength'],
                    'ku': ['knowledge', 'sel_category', 'learning_level', 'content_type', 'educational_level']
                },

                // Computed: should show context filters row
                get showContextFilters() {
                    return this.entityType !== '';
                },

                // Computed: label for context filter section. DERIVED from the
                // 'knowledge' marker group above rather than a second list of
                // type names — the list it replaced still named path_step and
                // learning_path after both left the surface, which is exactly
                // the drift a fourth vocabulary site invites.
                get contextFilterLabel() {
                    if (!this.entityType) return 'Filters';
                    return this.isFilterVisible('knowledge') ? 'Knowledge Filters' : 'Activity Filters';
                },

                // Computed: has any active filters
                get hasActiveFilters() {
                    return this.filterCount > 0 || this.entityType !== '';
                },

                // Count active facets: non-empty selects (Sort's 'relevance' default
                // excluded) + checked checkboxes, scoped to the filter panel. Driven
                // by x-on:change on .search-filters, so it re-tallies as controls move.
                updateFilterCount: function() {
                    var root = this.$root;
                    var count = 0;
                    root.querySelectorAll('.search-filters select').forEach(function(sel) {
                        if (sel.value && sel.value !== 'relevance') count++;
                    });
                    root.querySelectorAll('.search-filters input[type="checkbox"]').forEach(function(cb) {
                        if (cb.checked) count++;
                    });
                    this.filterCount = count;
                },

                isFilterVisible: function(group) {
                    if (!this.entityType) return false;
                    var filters = this.entityTypeFilters[this.entityType] || [];
                    return filters.indexOf(group) !== -1;
                },

                // Badge labels read from the server-rendered Type dropdown's
                // option text (ui/search/components.py _ENTITY_TYPE_OPTIONS is
                // the single source) — no client-side label map to drift.
                getFilterLabel: function(filterType, value) {
                    if (filterType === 'entity_type') {
                        var option = this.$root.querySelector(
                            '[name="entity_type"] option[value="' + value + '"]'
                        );
                        return (option && option.textContent) || value;
                    }
                    return value;
                },

                // Hand the current query + retrieval-scoping facets (nous +
                // nous_subtopic) to Askesis as a scoped Ask. Reads the live inputs
                // (they carry the truth via their `name` attrs) and builds
                // /askesis?question=&nous=&nous_subtopic=.
                // $root, NOT $el: invoked from the Ask button's x-on:click, where
                // $el is the BUTTON (Alpine 3 binds $el to the element evaluating
                // the expression) — button.querySelector found nothing, so every
                // param read empty and Ask navigated to a bare /askesis.
                askHref: function() {
                    var root = this.$root;
                    var qEl = root.querySelector('[name="query"]');
                    var nousEl = root.querySelector('[name="nous"]');
                    var subEl = root.querySelector('[name="nous_subtopic"]');
                    var q = (qEl && qEl.value || '').trim();
                    var nous = (nousEl && nousEl.value || '').trim();
                    var nousSubtopic = (subEl && subEl.value || '').trim();
                    var params = new URLSearchParams();
                    if (q) params.set('question', q);
                    if (nous) params.set('nous', nous);
                    if (nousSubtopic) params.set('nous_subtopic', nousSubtopic);
                    var qs = params.toString();
                    return '/askesis' + (qs ? '?' + qs : '');
                },

                clearFilter: function(filterName) {
                    if (filterName === 'entity_type') {
                        this.entityType = '';
                        var select = document.querySelector('[name="entity_type"]');
                        if (select) {
                            select.value = '';
                            select.dispatchEvent(new Event('change', { bubbles: true }));
                        }
                    }
                },

                // Narrow the Type filter from a result-breakdown chip: set the
                // select and dispatch change — x-model picks up the new state
                // and hx-trigger="change" re-fires the search, one event for both.
                setEntityType: function(value) {
                    var select = this.$root.querySelector('[name="entity_type"]');
                    if (!select) return;
                    select.value = value;
                    select.dispatchEvent(new Event('change', { bubbles: true }));
                },

                clearAllFilters: function() {
                    this.entityType = '';
                    this.showAdvanced = false;

                    // Reset all select elements
                    var selects = document.querySelectorAll('.search-container select');
                    selects.forEach(function(select) {
                        select.value = '';
                    });

                    // Uncheck all checkboxes
                    var checkboxes = document.querySelectorAll('.search-container input[type="checkbox"]');
                    checkboxes.forEach(function(cb) {
                        cb.checked = false;
                    });

                    this.filterCount = 0;

                    // Trigger search update. Dispatch on the NOUS select: its own
                    // hx-trigger re-runs /search/results (with every other cleared
                    // control included) AND the dependent sub-topic column listens
                    // for `change from:[name='nous']`, so the same event re-fetches
                    // the disabled "Choose a Nous first" gate — without it the old
                    // scoped sub-topic options would survive Clear all, enabled,
                    // with no parent topic (Codex #642).
                    var nousSelect = document.querySelector('[name="nous"]');
                    var trigger = nousSelect || document.querySelector('[name="entity_type"]');
                    if (trigger) {
                        trigger.dispatchEvent(new Event('change', { bubbles: true }));
                    }
                },

                init: function() {
                    // Track viewport so the advanced facets can be desktop-collapsible
                    // yet always shown inside the mobile drawer. Close a stray-open
                    // drawer when the viewport grows to desktop.
                    var self = this;
                    var mq = window.matchMedia('(min-width: 1024px)');
                    this.isDesktop = mq.matches;
                    mq.addEventListener('change', function(e) {
                        self.isDesktop = e.matches;
                        if (e.matches) self.filtersOpen = false;
                    });

                    // Seed the active-filter count (filters may be pre-checked on load)
                    this.updateFilterCount();
                }
            };
        });

        // ---------------------------------------------------------------------
        // Collapsible Section Component
        // ---------------------------------------------------------------------
        // Handles expand/collapse with smooth transitions
        Alpine.data('collapsible', function(initiallyOpen) {
            return {
                expanded: initiallyOpen || false,

                toggle: function() {
                    this.expanded = !this.expanded;
                }
            };
        });

        // ---------------------------------------------------------------------
        // Collapsible Sidebar Component (Tailwind + Alpine)
        // ---------------------------------------------------------------------
        // Unified sidebar for all pages: Profile, KU, Reports, Journals, Askesis.
        // Desktop: collapsible with toggle. Mobile: hidden (tabs shown instead).
        // Multiple instances share state via storageKey parameter.
        Alpine.data('collapsibleSidebar', function(storageKey, defaultCollapsed) {
            return {
                // Local getter reads from shared store
                get collapsed() {
                    var store = Alpine.store(storageKey);
                    return store ? store.collapsed : false;
                },

                init: function() {
                    // Register shared store if not yet created
                    if (!Alpine.store(storageKey)) {
                        var initial = defaultCollapsed === true;
                        if (window.innerWidth >= 1024) {
                            var stored = localStorage.getItem(storageKey + '-collapsed');
                            initial = stored !== null ? stored === 'true' : (defaultCollapsed === true);
                        }
                        Alpine.store(storageKey, { collapsed: initial });
                    }
                },

                toggle: function() {
                    var store = Alpine.store(storageKey);
                    store.collapsed = !store.collapsed;
                    localStorage.setItem(storageKey + '-collapsed', store.collapsed.toString());
                    // Screen reader announcement
                    var state = store.collapsed ? 'collapsed' : 'expanded';
                    if (window.SKUEL && window.SKUEL.announce) {
                        window.SKUEL.announce('Sidebar ' + state);
                    }
                }
            };
        });

        // ---------------------------------------------------------------------
        // Calendar Legend Filters Component
        // ---------------------------------------------------------------------
        /**
         * Calendar legend type filters: click a swatch to hide/show that item
         * type, hover to spotlight it (dim the others). Bound to the calendar
         * shell (outside the HTMX-swapped grid), it only toggles cal-hide-* /
         * cal-spot-* classes there — the hiding itself is pure CSS keyed off
         * data-item-type (calendar.css), so filters survive grid swaps with no
         * re-init. Hidden types persist in localStorage across views/sessions.
         *
         * @example
         * <div x-data="calendarLegend" :class="filterClasses()">
         *   <button @click="toggleType('event')" @mouseenter="spotlight = 'event'">
         * </div>
         */
        Alpine.data('calendarLegend', function() {
            var STORAGE_KEY = 'skuel-calendar-hidden-types';
            return {
                hidden: [],
                spotlight: null,

                init: function() {
                    try {
                        var stored = JSON.parse(localStorage.getItem(STORAGE_KEY) || '[]');
                        if (Array.isArray(stored)) {
                            this.hidden = stored.filter(function(t) {
                                return typeof t === 'string';
                            });
                        }
                    } catch (e) {
                        // Corrupted stored value — start unfiltered.
                        localStorage.removeItem(STORAGE_KEY);
                    }
                },

                isHidden: function(type) {
                    return this.hidden.indexOf(type) !== -1;
                },

                toggleType: function(type) {
                    var idx = this.hidden.indexOf(type);
                    if (idx === -1) {
                        this.hidden.push(type);
                    } else {
                        this.hidden.splice(idx, 1);
                    }
                    localStorage.setItem(STORAGE_KEY, JSON.stringify(this.hidden));
                    if (window.SKUEL && window.SKUEL.announce) {
                        var state = idx === -1 ? 'hidden' : 'shown';
                        window.SKUEL.announce(type.replace('_', ' ') + ' items ' + state);
                    }
                },

                // Class string for the shell wrapper: one cal-hide-* per hidden
                // type, plus cal-spot-* while hovering a visible swatch.
                filterClasses: function() {
                    var classes = this.hidden.map(function(t) {
                        return 'cal-hide-' + t;
                    });
                    if (this.spotlight && !this.isHidden(this.spotlight)) {
                        classes.push('cal-spot-' + this.spotlight);
                    }
                    return classes.join(' ');
                }
            };
        });

        // ---------------------------------------------------------------------
        // Chart.js Visualization Component
        // ---------------------------------------------------------------------
        // Renders Chart.js charts from API data
        Alpine.data('chartVis', function(dataUrl, chartType) {
            return {
                chart: null,
                loading: true,
                error: null,

                init: function() {
                    var self = this;
                    this.loadChart(dataUrl, chartType || 'line');
                },

                loadChart: function(url, type) {
                    var self = this;
                    this.loading = true;
                    this.error = null;

                    window.SKUEL.getJson(url)
                        .then(function(config) {
                            var canvas = self.$refs.canvas;
                            if (!canvas) {
                                throw new Error('Canvas element not found');
                            }

                            // Destroy existing chart if any
                            if (self.chart) {
                                self.chart.destroy();
                            }

                            // Create new chart
                            var ctx = canvas.getContext('2d');
                            self.chart = new Chart(ctx, config);
                            self.loading = false;
                        })
                        .catch(function(error) {
                            console.error('Chart error:', error);
                            self.error = error.message;
                            self.loading = false;
                        });
                },

                refresh: function(newUrl) {
                    this.loadChart(newUrl || dataUrl, chartType || 'line');
                },

                destroy: function() {
                    if (this.chart) {
                        this.chart.destroy();
                        this.chart = null;
                    }
                }
            };
        });

        // ---------------------------------------------------------------------
        // Toast Manager Component
        // ---------------------------------------------------------------------
        // Manages toast notifications with auto-dismiss
        Alpine.data('toastManager', function() {
            return {
                toasts: [],

                show: function(message, type, duration) {
                    type = type || 'info';
                    duration = typeof duration !== 'undefined' ? duration : 3000;

                    var id = Date.now();
                    this.toasts.push({ id: id, message: message, type: type });

                    if (duration > 0) {
                        var self = this;
                        setTimeout(function() {
                            self.dismiss(id);
                        }, duration);
                    }
                },

                dismiss: function(id) {
                    this.toasts = this.toasts.filter(function(t) {
                        return t.id !== id;
                    });
                },

                init: function() {
                    var self = this;
                    // afterRequest (not afterSwap): error responses never swap,
                    // so listening on afterSwap silently dropped every
                    // boundary_handler error toast (G7 totality find). One
                    // listener now surfaces X-Toast headers for successes,
                    // hx-swap="none" responses, AND 4xx/5xx errors.
                    document.body.addEventListener('htmx:afterRequest', function(event) {
                        var xhr = event.detail.xhr;
                        if (!xhr) return;

                        var msg = xhr.getResponseHeader('X-Toast-Message');
                        var type = xhr.getResponseHeader('X-Toast-Type') || 'success';

                        if (msg) {
                            self.show(msg, type);
                        }
                    });
                }
            };
        });

        // ---------------------------------------------------------------------
        // Form Validator Component
        // ---------------------------------------------------------------------
        // Client-side form validation with accessible error display
        Alpine.data('entityPicker', function() {
            // Searchable cross-domain UID picker — paired with EntityPicker
            // (ui/patterns/entity_picker.py) and GET /api/picker/search.
            // Hidden input ($refs.hidden) carries the form value; visible
            // input ($refs.search) is for human search and is unnamed so
            // the parent form never sees it.
            return {
                open: false,
                highlight: -1,

                init: function() {
                    var self = this;
                    // Reset highlight whenever HTMX swaps in new results.
                    this.$el.addEventListener('htmx:afterSwap', function() {
                        self.highlight = -1;
                        // If results came back and the input is focused, open.
                        if (document.activeElement === self.$refs.search) {
                            self.open = true;
                        }
                    });
                },

                onFocus: function() {
                    this.open = true;
                },

                onInput: function() {
                    this.open = true;
                    this.highlight = -1;
                },

                _items: function() {
                    var ul = this.$el.querySelector('ul[role="listbox"]');
                    return ul ? ul.querySelectorAll('li[role="option"]') : [];
                },

                onKeydown: function(event) {
                    var items = this._items();
                    if (event.key === 'ArrowDown') {
                        if (items.length === 0) return;
                        event.preventDefault();
                        this.open = true;
                        this.highlight = (this.highlight + 1) % items.length;
                        this._applyHighlight(items);
                    } else if (event.key === 'ArrowUp') {
                        if (items.length === 0) return;
                        event.preventDefault();
                        this.open = true;
                        this.highlight = (this.highlight - 1 + items.length) % items.length;
                        this._applyHighlight(items);
                    } else if (event.key === 'Enter') {
                        if (this.open && this.highlight >= 0 && items[this.highlight]) {
                            event.preventDefault();
                            this._pick(items[this.highlight]);
                        }
                    } else if (event.key === 'Escape') {
                        this.open = false;
                    }
                },

                _applyHighlight: function(items) {
                    var self = this;
                    items.forEach(function(li, idx) {
                        if (idx === self.highlight) {
                            li.setAttribute('aria-selected', 'true');
                            li.classList.add('bg-accent');
                            li.scrollIntoView({ block: 'nearest' });
                        } else {
                            li.removeAttribute('aria-selected');
                            li.classList.remove('bg-accent');
                        }
                    });
                },

                select: function(event) {
                    var li = event.target.closest('li[role="option"]');
                    if (!li) return;
                    this._pick(li);
                },

                _pick: function(li) {
                    var uid = li.getAttribute('data-uid') || '';
                    var title = li.getAttribute('data-title') || li.textContent.trim();
                    this.$refs.hidden.value = uid;
                    this.$refs.search.value = title;
                    // Notify FormGenerator's clearError() listener.
                    this.$refs.hidden.dispatchEvent(new Event('input', { bubbles: true }));
                    this.open = false;
                    this.highlight = -1;
                },

                clear: function() {
                    this.$refs.hidden.value = '';
                    this.$refs.search.value = '';
                    this.$refs.hidden.dispatchEvent(new Event('input', { bubbles: true }));
                    this.$refs.search.focus();
                },

                hasValue: function() {
                    return Boolean(this.$refs.hidden && this.$refs.hidden.value);
                }
            };
        });

        Alpine.data('formValidator', function() {
            return {
                errors: {},

                validate: function(event) {
                    this.errors = {};
                    var form = event.target;
                    var inputs = form.querySelectorAll('input, textarea, select');
                    var hasErrors = false;

                    var self = this;
                    inputs.forEach(function(input) {
                        if (!input.checkValidity()) {
                            hasErrors = true;
                            var errorDiv = document.getElementById(input.name + '-error');
                            var message = input.dataset.patternMsg || input.validationMessage;
                            self.errors[input.name] = message;

                            if (errorDiv) {
                                errorDiv.textContent = message;
                                errorDiv.style.display = 'block';
                            }

                            input.setAttribute('aria-invalid', 'true');
                        }
                    });

                    if (hasErrors) {
                        event.preventDefault();
                        var firstInvalid = form.querySelector('[aria-invalid="true"]');
                        if (firstInvalid && firstInvalid.focus) {
                            firstInvalid.focus();
                        }
                    }
                },

                clearError: function(fieldName) {
                    delete this.errors[fieldName];
                    var errorDiv = document.getElementById(fieldName + '-error');
                    if (errorDiv) {
                        errorDiv.style.display = 'none';
                    }
                    var input = document.getElementById(fieldName);
                    if (input) {
                        input.removeAttribute('aria-invalid');
                    }
                }
            };
        });

        window.SKUEL.debug('Alpine.js components initialized');
    });

    // =========================================================================
    // DOM Ready
    // =========================================================================

    document.addEventListener('DOMContentLoaded', function() {
        window.SKUEL.debug('DOM ready');

        // =========================================================================
        // HTMX Error Handling - Redirect to login on 401
        // Must be inside DOMContentLoaded because document.body doesn't exist in <head>
        // =========================================================================

        document.body.addEventListener('htmx:responseError', function(event) {
            var xhr = event.detail.xhr;
            if (xhr && xhr.status === 401) {
                window.SKUEL.debug('Session expired - redirecting to login');
                // Redirect to login with return URL
                var returnUrl = encodeURIComponent(window.location.pathname + window.location.search);
                window.location.href = '/login?next=' + returnUrl;
            }
        });

        // =========================================================================
        // HTMX + Alpine on dynamic content: NO glue needed.
        // =========================================================================
        // htmx processes hx-* attributes on swapped content itself, and Alpine 3
        // initializes new x-data trees via its own MutationObserver. Do NOT call
        // htmx.process() from an htmx:load handler: htmx fires htmx:load on <body>
        // at startup, and its init-hash covers ALL attributes (our aria-busy
        // writes invalidate it), so reprocessing re-fires every hx-trigger="load"
        // request — duplicating fragment loads and crashing the losing swap
        // (htmx:swapError on a detached target).

    });

    // =========================================================================
    // Alpine Component Registry
    // =========================================================================
    // MUST be alpine:init, not DOMContentLoaded (#468): Alpine is loaded `defer`
    // (ui/theme.py) and starts via queueMicrotask, walking the DOM BEFORE
    // DOMContentLoaded fires. Registering these here guarantees the components
    // exist when Alpine initializes initial server-rendered `x-data` (e.g.
    // bulkInsightManager / insightFiltersDebounced on /insights). Registering in
    // DOMContentLoaded left them undefined on hard load (only hx-boost re-init
    // via htmx:load masked it).

    document.addEventListener('alpine:init', function() {
        // ---------------------------------------------------------------------
        // Hierarchy Tree Component
        // ---------------------------------------------------------------------
        /**
         * State management for TreeView component.
         *
         * Features:
         * - Expand/collapse tracking
         * - Keyboard navigation (↑↓←→)
         * - Multi-select with checkboxes
         * - Drag-and-drop node movement
         * - Inline title editing
         *
         * @param {Object} config - Configuration object
         * @param {string} config.entityType - Entity type ("goal", "habit", etc.)
         * @param {string} config.childrenEndpoint - API endpoint template for children
         * @param {string} config.moveEndpoint - API endpoint for moving nodes
         * @param {boolean} config.showCheckboxes - Enable multi-select checkboxes
         * @param {boolean} config.keyboardNav - Enable keyboard navigation
         * @param {boolean} config.draggable - Enable drag-and-drop
         * @returns {Object} Alpine.js component
         */
        Alpine.data('hierarchyTree', function(config) {
            return {
                // Configuration
                entityType: config.entityType || 'goal',
                childrenEndpoint: config.childrenEndpoint || '',
                moveEndpoint: config.moveEndpoint || '',
                showCheckboxes: config.showCheckboxes || false,
                keyboardNav: config.keyboardNav || true,
                draggable: config.draggable || true,

                // State
                expanded: new Set(),      // Set of expanded node UIDs
                selected: [],             // Array of selected node UIDs (for checkboxes)
                focusedNode: null,        // Currently focused node UID (keyboard nav)
                editingNode: null,        // Node being edited inline
                draggedNode: null,        // Node being dragged

                // Expand/Collapse
                isExpanded: function(uid) {
                    return this.expanded.has(uid);
                },

                toggleExpand: function(uid) {
                    if (this.expanded.has(uid)) {
                        this.expanded.delete(uid);
                    } else {
                        this.expanded.add(uid);
                        // Trigger HTMX lazy load via custom event
                        document.body.dispatchEvent(new CustomEvent('expand-' + uid));
                    }
                },

                expandAll: function() {
                    var self = this;
                    var nodes = this.$el.querySelectorAll('.tree-node[data-has-children="true"]');
                    nodes.forEach(function(node) {
                        var uid = node.dataset.uid;
                        if (!self.expanded.has(uid)) {
                            self.toggleExpand(uid);
                        }
                    });
                },

                collapseAll: function() {
                    this.expanded.clear();
                },

                // Keyboard Navigation
                handleKeydown: function(event) {
                    if (!this.keyboardNav) return;

                    var key = event.key;
                    var nodes = Array.from(this.$el.querySelectorAll('.tree-node'));
                    var currentIndex = nodes.findIndex(function(n) { return n.dataset.uid === this.focusedNode; }.bind(this));

                    var handled = false;

                    switch(key) {
                        case 'ArrowDown':
                            // Move to next visible node
                            if (currentIndex < nodes.length - 1) {
                                var nextNode = nodes[currentIndex + 1];
                                this.focusNode(nextNode.dataset.uid);
                                handled = true;
                            }
                            break;

                        case 'ArrowUp':
                            // Move to previous visible node
                            if (currentIndex > 0) {
                                var prevNode = nodes[currentIndex - 1];
                                this.focusNode(prevNode.dataset.uid);
                                handled = true;
                            }
                            break;

                        case 'ArrowRight':
                            // Expand if collapsed, move to first child if expanded
                            if (this.focusedNode && !this.isExpanded(this.focusedNode)) {
                                this.toggleExpand(this.focusedNode);
                                handled = true;
                            } else if (currentIndex < nodes.length - 1) {
                                // Move to first child
                                var nextNode = nodes[currentIndex + 1];
                                var currentDepth = parseInt(nodes[currentIndex].dataset.depth);
                                var nextDepth = parseInt(nextNode.dataset.depth);
                                if (nextDepth > currentDepth) {
                                    this.focusNode(nextNode.dataset.uid);
                                    handled = true;
                                }
                            }
                            break;

                        case 'ArrowLeft':
                            // Collapse if expanded, move to parent if collapsed
                            if (this.focusedNode && this.isExpanded(this.focusedNode)) {
                                this.toggleExpand(this.focusedNode);
                                handled = true;
                            } else if (currentIndex > 0) {
                                // Move to parent
                                var currentDepth = parseInt(nodes[currentIndex].dataset.depth);
                                for (var i = currentIndex - 1; i >= 0; i--) {
                                    var parentDepth = parseInt(nodes[i].dataset.depth);
                                    if (parentDepth < currentDepth) {
                                        this.focusNode(nodes[i].dataset.uid);
                                        handled = true;
                                        break;
                                    }
                                }
                            }
                            break;

                        case 'Enter':
                        case ' ':
                            // Toggle expand/collapse
                            if (this.focusedNode) {
                                this.toggleExpand(this.focusedNode);
                                handled = true;
                            }
                            break;
                    }

                    if (handled) {
                        event.preventDefault();
                    }
                },

                focusNode: function(uid) {
                    this.focusedNode = uid;
                    var node = this.$el.querySelector('[data-uid="' + uid + '"]');
                    if (node) {
                        node.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
                        // Visual highlight
                        node.classList.add('ring-2', 'ring-primary');
                        setTimeout(function() {
                            node.classList.remove('ring-2', 'ring-primary');
                        }, 300);
                    }
                },

                // Multi-Select
                selectAll: function() {
                    var allUids = Array.from(this.$el.querySelectorAll('.tree-node'))
                        .map(function(n) { return n.dataset.uid; });
                    this.selected = allUids;
                },

                deselectAll: function() {
                    this.selected = [];
                },

                bulkDelete: function() {
                    if (this.selected.length === 0) return;
                    if (!confirm('Delete ' + this.selected.length + ' items?')) return;

                    var self = this;
                    // Send bulk delete request
                    window.SKUEL.postJson('/api/' + this.entityType + '/bulk-delete', {uids: this.selected})
                    .then(function() {
                        self.$dispatch('toast', {
                            message: 'Deleted ' + self.selected.length + ' items',
                            type: 'success',
                        });
                        self.selected = [];
                        // Refresh tree — the whole tree is rendered server-side,
                        // so there is no fragment route to re-request.
                        window.SKUEL.refreshAfterMutation();
                    })
                    .catch(function(error) {
                        self.$dispatch('toast', {
                            message: 'Delete failed: ' + error.message,
                            type: 'error',
                        });
                    });
                },

                // Drag and Drop
                handleDragStart: function(event, uid) {
                    if (!this.draggable) return;
                    this.draggedNode = uid;
                    event.dataTransfer.effectAllowed = 'move';
                    event.target.classList.add('opacity-50');
                },

                handleDragOver: function(event) {
                    event.preventDefault();
                    event.dataTransfer.dropEffect = 'move';
                },

                handleDrop: function(event, newParentUid) {
                    event.preventDefault();
                    if (!this.draggedNode || this.draggedNode === newParentUid) return;

                    // Prevent dropping onto descendant (would create cycle)
                    if (this.isDescendant(newParentUid, this.draggedNode)) {
                        this.$dispatch('toast', {
                            message: 'Cannot move parent into its own descendant',
                            type: 'error',
                        });
                        return;
                    }

                    var self = this;
                    // Send move request
                    window.SKUEL.postJson(
                        this.moveEndpoint.replace('{uid}', this.draggedNode),
                        {new_parent_uid: newParentUid}
                    )
                    .then(function() {
                        self.$dispatch('toast', {
                            message: 'Moved successfully',
                            type: 'success',
                        });
                        // Refresh affected nodes via HTMX
                        window.SKUEL.refreshAfterMutation('#children-' + newParentUid);
                    })
                    .catch(function(error) {
                        self.$dispatch('toast', {
                            message: 'Move failed: ' + error.message,
                            type: 'error',
                        });
                    });

                    this.draggedNode = null;
                    event.target.classList.remove('opacity-50');
                },

                isDescendant: function(potentialDescendant, ancestor) {
                    // Check if potentialDescendant is a child/grandchild of ancestor
                    var current = this.$el.querySelector('[data-uid="' + potentialDescendant + '"]');
                    while (current) {
                        var parentNode = current.parentElement ? current.parentElement.closest('.tree-node') : null;
                        if (!parentNode) return false;
                        if (parentNode.dataset.uid === ancestor) return true;
                        current = parentNode;
                    }
                    return false;
                },

                // Inline Editing
                startEdit: function(uid) {
                    this.editingNode = uid;
                    // Focus input after Alpine renders it
                    var self = this;
                    this.$nextTick(function() {
                        var input = self.$el.querySelector('#edit-input-' + uid);
                        if (input) {
                            input.focus();
                            input.select();
                        }
                    });
                },

                saveEdit: function(uid, newTitle) {
                    var self = this;
                    window.SKUEL.postJson(
                        '/api/' + this.entityType + '/' + uid,
                        {title: newTitle},
                        {method: 'PATCH'}
                    )
                    .then(function() {
                        self.$dispatch('toast', {
                            message: 'Title updated',
                            type: 'success',
                        });
                        self.editingNode = null;
                        // Update DOM
                        var titleSpan = self.$el.querySelector('[data-uid="' + uid + '"] .node-title');
                        if (titleSpan) titleSpan.textContent = newTitle;
                    })
                    .catch(function(error) {
                        self.$dispatch('toast', {
                            message: 'Update failed: ' + error.message,
                            type: 'error',
                        });
                    });
                },

                cancelEdit: function() {
                    this.editingNode = null;
                },
            };
        });

        // ---------------------------------------------------------------------
        // Bulk Insight Manager Component - Phase 2 Task 9
        // ---------------------------------------------------------------------
        /**
         * Manages bulk selection and actions for insights dashboard.
         * Allows selecting multiple insights and performing batch operations.
         *
         * @returns {Object} Alpine.js component
         * @property {Set} selectedUids - Set of selected insight UIDs
         * @property {boolean} selectAllChecked - Select all checkbox state
         * @property {boolean} showBulkActions - Computed: show bulk action bar
         * @property {number} selectedCount - Computed: count of selected insights
         *
         * @example
         * <div x-data="bulkInsightManager()">
         *   <input type="checkbox" @change="toggleSelection(insight.uid)">
         *   <button @click="bulkDismiss()">Dismiss Selected</button>
         * </div>
         */
        Alpine.data('bulkInsightManager', function() {
            return {
                selectedUids: new Set(),
                selectAllChecked: false,

                // Computed: show bulk action bar when insights selected
                get showBulkActions() {
                    return this.selectedUids.size > 0;
                },

                // Computed: selected count
                get selectedCount() {
                    return this.selectedUids.size;
                },

                // Toggle individual insight selection
                toggleSelection: function(uid) {
                    if (this.selectedUids.has(uid)) {
                        this.selectedUids.delete(uid);
                    } else {
                        this.selectedUids.add(uid);
                    }
                    // Update select-all checkbox state
                    this.updateSelectAllState();
                },

                // Check if insight is selected
                isSelected: function(uid) {
                    return this.selectedUids.has(uid);
                },

                // Select all visible insights
                selectAll: function() {
                    var self = this;
                    var checkboxes = document.querySelectorAll('input[name="insight-checkbox"]');
                    checkboxes.forEach(function(checkbox) {
                        self.selectedUids.add(checkbox.value);
                    });
                    this.selectAllChecked = true;
                },

                // Deselect all insights
                deselectAll: function() {
                    this.selectedUids.clear();
                    this.selectAllChecked = false;
                },

                // Toggle select all
                toggleSelectAll: function() {
                    if (this.selectAllChecked) {
                        this.selectAll();
                    } else {
                        this.deselectAll();
                    }
                },

                // Update select-all checkbox state based on selections
                updateSelectAllState: function() {
                    var checkboxes = document.querySelectorAll('input[name="insight-checkbox"]');
                    var totalCount = checkboxes.length;
                    this.selectAllChecked = totalCount > 0 && this.selectedUids.size === totalCount;
                },

                // Bulk dismiss selected insights
                bulkDismiss: async function() {
                    var self = this;
                    if (this.selectedUids.size === 0) return;

                    var uids = Array.from(this.selectedUids);

                    try {
                        await window.SKUEL.postJson('/api/insights/bulk/dismiss', { uids: uids });
                        // The insights list is rendered whole — no fragment route.
                        window.SKUEL.refreshAfterMutation();
                    } catch (err) {
                        console.error('Bulk dismiss failed:', err);
                        self.$dispatch('toast', {
                            message: 'Failed to dismiss insights: ' + err.message,
                            type: 'error',
                        });
                    }
                },

                // Bulk mark as actioned
                bulkMarkActioned: async function() {
                    var self = this;
                    if (this.selectedUids.size === 0) return;

                    var uids = Array.from(this.selectedUids);

                    try {
                        await window.SKUEL.postJson('/api/insights/bulk/action', { uids: uids });
                        // The insights list is rendered whole — no fragment route.
                        window.SKUEL.refreshAfterMutation();
                    } catch (err) {
                        console.error('Bulk action failed:', err);
                        self.$dispatch('toast', {
                            message: 'Failed to mark insights as actioned: ' + err.message,
                            type: 'error',
                        });
                    }
                }
            };
        });

        // ---------------------------------------------------------------------
        // Relationship Graph Component (Vis.js Network) - Phase 5
        // ---------------------------------------------------------------------
        /**
         * Interactive force-directed graph for lateral relationships.
         * Uses Vis.js Network library for visualization.
         *
         * @param {string} entity_uid - Center entity UID
         * @param {string} entity_type - Entity type (tasks, goals, etc.)
         * @param {number} initial_depth - Initial graph depth (1-3)
         * @returns {Object} Alpine.js component
         *
         * @example
         * <div x-data="relationshipGraph('task_abc', 'tasks', 2)" x-init="init()">
         *   <div id="network-task_abc"></div>
         * </div>
         */
        Alpine.data('relationshipGraph', function(entity_uid, entity_type, initial_depth) {
            return {
                entity_uid: entity_uid,
                entity_type: entity_type,
                depth: initial_depth || 2,
                network: null,
                loading: false,
                error: null,

                init: function() {
                    this.loadGraph(this.depth);
                },

                loadGraph: async function(depth) {
                    var self = this;
                    self.loading = true;
                    self.error = null;

                    try {
                        var data = await window.SKUEL.getJson(
                            '/api/' + self.entity_type + '/' + self.entity_uid + '/lateral/graph?depth=' + depth
                        );
                        self.renderNetwork(data);

                    } catch (err) {
                        console.error('Failed to load relationship graph:', err);
                        self.error = 'Failed to load graph. Please try again.';
                    } finally {
                        self.loading = false;
                    }
                },

                renderNetwork: function(data) {
                    var container = document.getElementById('network-' + this.entity_uid);

                    if (!container) {
                        console.error('Network container not found:', 'network-' + this.entity_uid);
                        return;
                    }

                    // Destroy existing network
                    if (this.network) {
                        this.network.destroy();
                    }

                    // Check if vis.Network is available
                    if (!window.SKUEL.graph.ready()) {
                        console.error('Vis.js Network library not loaded');
                        this.error = 'Graph library not loaded';
                        return;
                    }

                    data.edges = window.SKUEL.graph.styleEdgesByConfidence(data.edges);

                    var options = window.SKUEL.graph.buildOptions(
                        window.SKUEL.graph.PROFILES.relationship
                    );

                    // Create network
                    this.network = new vis.Network(container, data, options);

                    // Click handler - navigate to the entity's real detail page. The
                    // server resolves node.url from the canonical entity_type (node.type
                    // is a Neo4j label, not a route); attachClickNav no-ops on a null url.
                    window.SKUEL.graph.attachClickNav(
                        this.network, data.nodes, this.entity_uid,
                        function(node) { return node.url || null; }
                    );
                },

                changeDepth: function(newDepth) {
                    this.depth = parseInt(newDepth);
                    this.loadGraph(this.depth);
                }
            };
        });

        // ---------------------------------------------------------------------
        // Profile Domain Filter Component (Phase 3, Task 12)
        // ---------------------------------------------------------------------
        /**
         * Manages sorting and filtering for profile domain views.
         * Used in Tasks, Goals, Habits, Events, Choices, Principles domain views.
         *
         * @returns {Object} Alpine.js component
         *
         * @example
         * <div x-data="domainFilter()">
         *   <select x-model="sortBy">
         *     <option value="priority">Priority</option>
         *     <option value="due_date">Due Date</option>
         *   </select>
         *   <div x-show="matchesFilter(item)">...</div>
         * </div>
         */
        Alpine.data('domainFilter', function() {
            return {
                sortBy: 'priority',  // priority, due_date, created, title
                filterPreset: 'all', // all, overdue, high_priority, this_week
                showAll: false,      // Show all items vs limited view

                // Check if item matches current filter
                matchesFilter: function(status, isOverdue, isHighPriority, isThisWeek) {
                    if (this.filterPreset === 'all') return true;
                    if (this.filterPreset === 'overdue') return isOverdue === true;
                    if (this.filterPreset === 'high_priority') return isHighPriority === true;
                    if (this.filterPreset === 'this_week') return isThisWeek === true;
                    if (this.filterPreset === 'at_risk') return status === 'warning' || status === 'at_risk';
                    if (this.filterPreset === 'keystone') return status === 'keystone';
                    if (this.filterPreset === 'today') return status === 'today';
                    if (this.filterPreset === 'near_complete') return status === 'near_complete';
                    return true;
                },

                // Toggle show all
                toggleShowAll: function() {
                    this.showAll = !this.showAll;
                }
            };
        });

        // ---------------------------------------------------------------------
        // Insight Detail Modal Component (Phase 3, Task 13)
        // ---------------------------------------------------------------------
        /**
         * Modal for displaying detailed insight information with transparency.
         * Shows full description, supporting data, confidence breakdown, and snooze options.
         *
         * @param {string} insightUid - Insight UID to load details for
         * @returns {Object} Alpine.js component
         *
         * @example
         * <div x-data="insightDetailModal('insight.difficulty_pattern.habit_abc123.20260131')">
         *   <button @click="open()">View Details</button>
         *   <div x-show="isOpen" class="modal">...</div>
         * </div>
         */
        Alpine.data('insightDetailModal', function(insightUid) {
            return {
                isOpen: false,
                loading: false,
                error: null,
                insight: null,
                insightUid: insightUid,

                open: function() {
                    this.isOpen = true;
                    if (!this.insight) {
                        this.loadDetails();
                    }
                },

                close: function() {
                    this.isOpen = false;
                },

                loadDetails: function() {
                    var self = this;
                    self.loading = true;
                    self.error = null;

                    window.SKUEL.getJson('/api/insights/' + this.insightUid + '/details')
                        .then(function(data) {
                            self.insight = data;
                            self.loading = false;
                        })
                        .catch(function(err) {
                            self.error = err.message;
                            self.loading = false;
                            SKUEL.debug('Failed to load insight details', err);
                        });
                },

                snooze: function(days) {
                    var self = this;
                    if (!confirm('Snooze this insight for ' + days + ' day(s)?')) {
                        return;
                    }

                    window.SKUEL.postJson('/api/insights/' + this.insightUid + '/snooze', {days: days})
                        .then(function() {
                            self.close();
                            // The card list is rendered whole — no fragment route.
                            window.SKUEL.refreshAfterMutation();
                        })
                        .catch(function(err) {
                            self.$dispatch('toast', {
                                message: 'Failed to snooze insight: ' + err.message,
                                type: 'error',
                            });
                        });
                }
                // Confidence colors/labels are rendered server-side
                // (ui/insights/insight_card.py) — no client-side mirror.
            };
        });

        // ---------------------------------------------------------------------
        // Profile Drawer Component (Phase 3, Task 14)
        // (profileDrawer removed — replaced by collapsibleSidebar above)

        // ---------------------------------------------------------------------
        // Profile Focus Handler Component (Phase 3, Task 11)
        // ---------------------------------------------------------------------
        /**
         * Handles deep linking from insights to profile with scroll and highlight.
         * Used in profile domain views when ?focus={entity_uid} query param is present.
         *
         * @param {string} focusUid - Entity UID to scroll to and highlight
         * @returns {Object} Alpine.js component
         *
         * @example
         * <div x-data="profileFocusHandler('habit_meditation_abc123')"
         *      x-init="$nextTick(() => scrollToFocused())">
         *   <!-- entity list items with data-uid attributes -->
         * </div>
         */
        Alpine.data('profileFocusHandler', function(focusUid) {
            return {
                focusUid: focusUid,

                scrollToFocused: function() {
                    if (!this.focusUid) return;

                    var self = this;
                    // Find element with matching data-uid attribute
                    var targetElement = this.$el.querySelector('[data-uid="' + this.focusUid + '"]');

                    if (targetElement) {
                        // Scroll to element with smooth behavior
                        setTimeout(function() {
                            targetElement.scrollIntoView({
                                behavior: 'smooth',
                                block: 'center',
                                inline: 'nearest'
                            });

                            // Apply yellow border flash animation
                            targetElement.classList.add('border-2', 'border-warning', 'transition-all', 'duration-1000');

                            // Remove highlight after 2 seconds
                            setTimeout(function() {
                                targetElement.classList.remove('border-2', 'border-warning');
                            }, 2000);
                        }, 300); // Small delay to ensure DOM is ready
                    } else {
                        SKUEL.debug('Focus target not found', self.focusUid);
                    }
                }
            };
        });

        // ---------------------------------------------------------------------
        // Phase 4, Task 16: Debounced Insight Filters
        // ---------------------------------------------------------------------
        /**
         * Manages debounced filter updates for insights dashboard.
         * Prevents rapid filter changes from triggering multiple server requests.
         *
         * Features:
         * - 300ms debounce on search input
         * - Immediate updates for select dropdowns
         * - Cancels in-flight requests when new filter changes arrive
         * - Shows loading indicator during filter application
         *
         * @param {Object} initialFilters - Initial filter values {search, domain, impact, type, status}
         * @returns {Object} Alpine.js component
         *
         * @example
         * <div x-data="insightFiltersDebounced({search: '', domain: '', impact: '', type: '', status: 'all'})">
         *   <input x-model="filters.search" @input.debounce.300ms="applyFilters()">
         *   <select x-model="filters.domain" @change="applyFilters()">
         * </div>
         */
        Alpine.data('insightFiltersDebounced', function(initialFilters) {
            return {
                filters: initialFilters || {
                    search: '',
                    domain: '',
                    impact: '',
                    type: '',
                    status: 'all'
                },
                loading: false,

                /**
                 * Apply filters by constructing URL and navigating.
                 * Uses window.location to ensure proper browser history.
                 */
                applyFilters: function() {
                    var self = this;
                    self.loading = true;

                    // Build query params
                    var params = [];
                    if (self.filters.search) params.push('search=' + encodeURIComponent(self.filters.search));
                    if (self.filters.domain) params.push('domain=' + encodeURIComponent(self.filters.domain));
                    if (self.filters.impact) params.push('impact=' + encodeURIComponent(self.filters.impact));
                    if (self.filters.type) params.push('type=' + encodeURIComponent(self.filters.type));
                    if (self.filters.status && self.filters.status !== 'all') {
                        params.push('status=' + encodeURIComponent(self.filters.status));
                    }

                    var queryString = params.length > 0 ? '?' + params.join('&') : '';
                    window.location.href = '/insights' + queryString;
                },

                /**
                 * Clear all filters and reload page.
                 */
                clearFilters: function() {
                    this.filters = {
                        search: '',
                        domain: '',
                        impact: '',
                        type: '',
                        status: 'all'
                    };
                    window.location.href = '/insights';
                }
            };
        });

    });

    // =========================================================================
    // Offline Status Indicator
    // =========================================================================

    document.addEventListener('alpine:init', function() {

        Alpine.data('offlineIndicator', function() {
            return {
                isOffline: !navigator.onLine,

                init: function() {
                    var self = this;
                    window.addEventListener('online', function() {
                        self.isOffline = false;
                    });
                    window.addEventListener('offline', function() {
                        self.isOffline = true;
                    });
                }
            };
        });

    });

    // =========================================================================
    // Explore Search Panel
    // =========================================================================

    document.addEventListener('alpine:init', function() {

        Alpine.data('exploreSearch', function(initialTag) {
            return {
                query: '',
                activeTag: initialTag || '',
                moreFilters: false,  // "More filters" disclosure (learning-level facet)

                init: function() {
                    // reactive state — query tracked via x-model, activeTag via hidden input
                },

                setTag: function(tag) {
                    var self = this;
                    if (self.activeTag === tag) {
                        self.activeTag = '';
                    } else {
                        self.activeTag = tag;
                    }
                    // fire HTMX search with updated tag value
                    self.$nextTick(function() {
                        var form = self.$refs.searchInput.closest('form');
                        var params = new URLSearchParams(new FormData(form));
                        htmx.ajax('GET', '/api/explore/search?' + params.toString(), {
                            target: '#explore-grid',
                            swap: 'innerHTML'
                        });
                    });
                }
            };
        });

        // ---------------------------------------------------------------------
        // Explore Graph Component — sidebar graph with filters + expand
        // ---------------------------------------------------------------------
        /**
         * Interactive graph for the Explore sidebar. Shows entity relationships
         * with filter tabs (Learning/Saved/All) and full-screen overlay expansion.
         *
         * @param {string} mode - 'hub' (learning universe) or 'entity' (entity-centered)
         * @param {string} entity_uid - Entity UID (ignored when mode='hub')
         * @param {string} entity_type - 'ku' or 'ps' (ignored when mode='hub')
         *
         * @example
         * <div x-data="exploreGraph('entity', 'ku_abc', 'ku')" x-init="init()">
         *   <div id="explore-graph-container"></div>
         * </div>
         */
        Alpine.data('exploreGraph', function(mode, entity_uid, entity_type) {
            return {
                mode: mode || 'hub',
                entity_uid: entity_uid || '',
                entity_type: entity_type || '',
                network: null,
                graphData: null,
                loading: false,
                error: null,
                filter: 'all',
                expanded: false,
                isEmpty: true,

                // Node color map by entity type
                NODE_COLORS: {
                    ku: { background: '#8B5CF6', border: '#7C3AED', highlight: { background: '#A78BFA', border: '#7C3AED' } },
                    ps: { background: '#14B8A6', border: '#0D9488', highlight: { background: '#2DD4BF', border: '#0D9488' } },
                    you: { background: '#3B82F6', border: '#2563EB', highlight: { background: '#60A5FA', border: '#2563EB' } },
                    default: { background: '#6B7280', border: '#4B5563', highlight: { background: '#9CA3AF', border: '#4B5563' } }
                },

                init: function() {
                    this.loadGraph();

                    // Escape key closes expanded view
                    var self = this;
                    document.addEventListener('keydown', function(e) {
                        if (e.key === 'Escape' && self.expanded) {
                            self.collapseGraph();
                        }
                    });
                },

                getApiUrl: function() {
                    if (this.mode === 'hub') {
                        return '/api/explore/graph';
                    }
                    // Map explore entity types to API domain names
                    var domainMap = { ku: 'ku', ps: 'ps' };
                    var domain = domainMap[this.entity_type] || this.entity_type;
                    return '/api/' + domain + '/' + this.entity_uid + '/lateral/graph?depth=2';
                },

                loadGraph: async function() {
                    var self = this;
                    self.loading = true;
                    self.error = null;

                    try {
                        self.graphData = await window.SKUEL.getJson(self.getApiUrl());
                        self.isEmpty = !self.graphData.nodes || self.graphData.nodes.length === 0;
                        self.renderNetwork();
                    } catch (err) {
                        console.error('Failed to load explore graph:', err);
                        self.error = 'Failed to load graph';
                    } finally {
                        self.loading = false;
                    }
                },

                /**
                 * Render this component's graph data into `container` at the
                 * given size profile. Shared by the sidebar graph and the
                 * fullscreen overlay — they differ only in profile.
                 *
                 * @param {Element} container
                 * @param {Object} profile - an entry from SKUEL.graph.PROFILES
                 * @returns {Object|null} {network, nodes, edges}, or null when
                 *   the library or the data is not ready
                 */
                _buildNetwork: function(container, profile) {
                    if (!window.SKUEL.graph.ready()) {
                        this.error = 'Graph library not loaded';
                        return null;
                    }

                    var data = this.graphData;
                    if (!data || !data.nodes) return null;

                    var styledNodes = window.SKUEL.graph.styleNodes(data.nodes, profile, {
                        centerUid: this.entity_uid,
                        colors: this.NODE_COLORS,
                        hubCenter: this.mode === 'hub'
                    });
                    var styledEdges = window.SKUEL.graph.styleEdges(data.edges, profile);

                    var visData = {
                        nodes: new vis.DataSet(styledNodes),
                        edges: new vis.DataSet(styledEdges)
                    };
                    var network = new vis.Network(
                        container, visData, window.SKUEL.graph.buildOptions(profile)
                    );

                    // Click → navigate to the entity's real detail page. In lateral
                    // mode the server resolves node.url from the canonical entity_type
                    // (node.type there is a Neo4j label, not a route). Hub mode carries
                    // no url, so exploreHrefFor falls back to its short-form _entityType.
                    // attachClickNav no-ops on a null href.
                    window.SKUEL.graph.attachClickNav(
                        network, styledNodes, this.entity_uid,
                        window.SKUEL.graph.exploreHrefFor
                    );

                    return { network: network, nodes: visData.nodes, edges: visData.edges };
                },

                renderNetwork: function() {
                    var container = document.getElementById('explore-graph-container');
                    if (!container) return;

                    if (this.network) {
                        this.network.destroy();
                    }

                    var skel = container.querySelector('#explore-graph-skeleton');
                    if (skel) skel.remove();

                    var built = this._buildNetwork(
                        container, window.SKUEL.graph.PROFILES.exploreSidebar
                    );
                    if (!built) return;

                    this.network = built.network;
                    this._visNodes = built.nodes;
                    this._visEdges = built.edges;

                    // Hover cursor
                    this.network.on('hoverNode', function() { container.style.cursor = 'pointer'; });
                    this.network.on('blurNode', function() { container.style.cursor = 'default'; });
                },

                setFilter: function(filterName) {
                    this.filter = filterName;
                    this.applyFilter();
                },

                applyFilter: function() {
                    if (!this._visNodes) return;

                    var self = this;
                    this._visNodes.forEach(function(node) {
                        var isCenter = (node.id === self.entity_uid) || (node.group === 'center');
                        var match = true;

                        if (self.filter === 'learning') {
                            match = isCenter || (node._learningState === 'studying' || node._learningState === 'in_progress');
                        } else if (self.filter === 'saved') {
                            match = isCenter || node._isPinned;
                        }
                        // 'all' — everything matches

                        var colors = self.NODE_COLORS[node._entityType] || self.NODE_COLORS.default;
                        if (isCenter && self.mode === 'hub') colors = self.NODE_COLORS.you;

                        self._visNodes.update({
                            id: node.id,
                            opacity: match ? 1.0 : 0.15,
                            font: { color: match ? '#64748B' : '#CBD5E1' },
                            color: match ? colors : {
                                background: '#E2E8F0',
                                border: '#CBD5E1',
                                highlight: { background: '#E2E8F0', border: '#CBD5E1' }
                            }
                        });
                    });
                },

                expandGraph: function() {
                    this.expanded = true;
                    var self = this;
                    // Fullscreen overlay mounted on document.body with a second
                    // Vis.js network — this sidesteps the sidebar's
                    // overflow:hidden and transform traps. Classes mirror the
                    // AlpineModal pattern (ui/patterns/modal.py): a bg-black/50
                    // backdrop over a bg-background panel, so the overlay
                    // follows the design tokens and the dark theme instead of
                    // the hardcoded light-mode colours it used to inline.
                    var overlay = document.createElement('div');
                    overlay.id = 'explore-graph-overlay';
                    overlay.className = 'fixed inset-0 z-9999';
                    overlay.setAttribute('role', 'dialog');
                    overlay.setAttribute('aria-modal', 'true');
                    overlay.setAttribute('aria-label', 'Expanded relationship graph');

                    // Backdrop
                    var backdrop = document.createElement('div');
                    backdrop.className = 'absolute inset-0 bg-black/50 backdrop-blur-xs';
                    backdrop.addEventListener('click', function() { self.collapseGraph(); });
                    overlay.appendChild(backdrop);

                    // Graph panel — tighter inset on phones so a 375px viewport
                    // still leaves the canvas a usable width.
                    var panel = document.createElement('div');
                    panel.className = 'absolute inset-2 sm:inset-4 bg-background '
                        + 'rounded-lg shadow-lg overflow-hidden';
                    overlay.appendChild(panel);

                    // Close button — 44px touch target (w-11 h-11).
                    var closeBtn = document.createElement('button');
                    closeBtn.type = 'button';
                    closeBtn.innerHTML = '&times;';
                    closeBtn.setAttribute('aria-label', 'Close expanded graph');
                    closeBtn.className = 'absolute top-2 right-2 z-10 w-11 h-11 '
                        + 'flex items-center justify-center rounded-lg border border-border '
                        + 'bg-background text-foreground text-xl leading-none cursor-pointer '
                        + 'hover:bg-muted';
                    closeBtn.addEventListener('click', function(e) { e.stopPropagation(); self.collapseGraph(); });
                    panel.appendChild(closeBtn);

                    // Graph canvas container
                    var canvas = document.createElement('div');
                    canvas.className = 'w-full h-full';
                    panel.appendChild(canvas);

                    document.body.appendChild(overlay);
                    this._overlay = overlay;

                    // Render a second network with the same data, sized up.
                    var built = this._buildNetwork(
                        canvas, window.SKUEL.graph.PROFILES.exploreExpanded
                    );
                    if (built) {
                        this._expandedNetwork = built.network;
                    }
                },

                collapseGraph: function() {
                    this.expanded = false;
                    if (this._expandedNetwork) {
                        this._expandedNetwork.destroy();
                        this._expandedNetwork = null;
                    }
                    if (this._overlay) {
                        this._overlay.remove();
                        this._overlay = null;
                    }
                    // Resize sidebar graph back
                    var self = this;
                    setTimeout(function() {
                        if (self.network) {
                            self.network.redraw();
                            self.network.fit({ animation: { duration: 300, easingFunction: 'easeInOutQuad' } });
                        }
                    }, 50);
                }
            };
        });

        // ====================================================================
        // REVISION FORM — Dynamic feedback point rows for teacher review panel
        // ====================================================================
        Alpine.data('revisionForm', function() {
            return {
                points: [],
                categories: [
                    { value: 'accuracy', label: 'Accuracy' },
                    { value: 'completeness', label: 'Completeness' },
                    { value: 'depth', label: 'Depth' },
                    { value: 'clarity', label: 'Clarity' },
                    { value: 'application', label: 'Application' },
                    { value: 'methodology', label: 'Methodology' }
                ],
                addPoint: function() {
                    var idx = this.points.length;
                    this.points.push({ category: 'accuracy', detail: '' });
                    var row = document.createElement('div');
                    row.className = 'flex gap-2 mb-2 items-start';
                    row.setAttribute('data-fp-idx', idx);
                    row.innerHTML =
                        '<select name="fp_category_' + idx + '" class="text-sm border rounded-sm px-2 py-1 w-36">' +
                        this.categories.map(function(c) {
                            return '<option value="' + c.value + '">' + c.label + '</option>';
                        }).join('') +
                        '</select>' +
                        '<input type="text" name="fp_detail_' + idx + '" placeholder="Specific feedback..." ' +
                        'class="text-sm border rounded-sm px-2 py-1 flex-1" required />' +
                        '<button type="button" class="text-xs text-destructive hover:text-destructive/80 px-1" ' +
                        'onclick="this.parentElement.remove()">✕</button>';
                    this.$refs.fpRows.appendChild(row);
                }
            };
        });

        // Shared factory for batch audio→text transcription panels.
        // Used by both the admin console (batchTranscribe) and the user journals
        // submit page (userFolderTranscribe) — same UX, different endpoint + defaults.
        function _batchTranscribeFactory(endpoint, defaultInputDir, defaultOutputDir) {
            return {
                inputDir: defaultInputDir,
                outputDir: defaultOutputDir,
                skipExisting: true,
                loading: false,
                error: '',
                preview: null,
                result: null,

                _call: async function(previewOnly) {
                    this.loading = true;
                    this.error = '';
                    if (previewOnly) { this.result = null; } else { this.preview = null; }
                    try {
                        var data = await window.SKUEL.postJson(endpoint, {
                            input_dir: this.inputDir,
                            output_dir: this.outputDir,
                            skip_existing: this.skipExisting,
                            preview_only: previewOnly
                        });
                        if (previewOnly) { this.preview = data; } else { this.result = data; }
                    } catch (e) {
                        // postJson already unwrapped the server's error message.
                        this.error = (e && e.status)
                            ? e.message
                            : 'Request failed: ' + (e && e.message ? e.message : e);
                    } finally {
                        this.loading = false;
                    }
                },

                previewFiles: function() { return this._call(true); },
                transcribeAll: function() { return this._call(false); },

                previewSummary: function() {
                    if (!this.preview) return '';
                    var already = this.preview.already_transcribed
                        ? this.preview.already_transcribed.length : 0;
                    return this.preview.total_files + ' file(s), ' +
                        this.preview.total_size_mb + ' MB total · ' +
                        already + ' already transcribed';
                },

                resultSummary: function() {
                    if (!this.result) return '';
                    return this.result.succeeded + ' succeeded, ' +
                        this.result.failed + ' failed, ' +
                        this.result.skipped + ' skipped (of ' +
                        this.result.total_files + ')';
                }
            };
        }

        // Admin console: any server-side path, admin-only endpoint.
        Alpine.data('batchTranscribe', function() {
            return _batchTranscribeFactory(
                '/api/journals/batch-transcribe',
                'data/je_inputs',
                'data/je_outputs'
            );
        });

        // User journals submit page: paths are fixed server-side to the vault
        // je_in/je_out staging folders (/api/journals/folder-transcribe ignores
        // client-supplied paths), so these are display-only labels.
        Alpine.data('userFolderTranscribe', function() {
            return _batchTranscribeFactory(
                '/api/journals/folder-transcribe',
                'je_in (in your vault)',
                'je_out (in your vault)'
            );
        });

        // ---------------------------------------------------------------------
        // /submit page — destination dropdown + file uploader
        // ---------------------------------------------------------------------
        Alpine.data('submit', function(defaultDest, portfolioMode, teacherDisabled) {
            return {
                dest: defaultDest || 'teacher',
                menuOpen: false,
                file: null,
                sent: false,
                dragOver: false,
                _st: null,
                _onDoc: null,
                _onKey: null,

                get sendLabel() {
                    if (this.dest === 'ai') return 'Get AI feedback';
                    if (this.dest === 'portfolio') return 'Add to portfolio';
                    return 'Send to teacher';
                },
                get canSend() { return !!this.file && !this.sent; },
                get pipeline() {
                    if (this.dest === 'ai') return 'llm_summary';
                    if (this.dest === 'teacher' && !teacherDisabled) return 'teacher_review';
                    return 'none';
                },
                get audience() {
                    if (this.dest === 'ai') return 'private';
                    if (this.dest === 'portfolio') return 'public';
                    if (this.dest === 'teacher' && !teacherDisabled) return 'teachers';
                    return 'private';
                },

                fmtSize: function(b) {
                    if (b < 1024) return b + ' B';
                    if (b < 1048576) return (b / 1024).toFixed(0) + ' KB';
                    return (b / 1048576).toFixed(1) + ' MB';
                },

                selectDest: function(d) {
                    if (d === 'portfolio' && portfolioMode !== 'active') return;
                    if (d === 'teacher' && teacherDisabled) return;
                    this.dest = d;
                    this.menuOpen = false;
                },

                browse: function() {
                    this.$refs.fileInput.click();
                },

                onFileChange: function(e) {
                    var f = e.target.files && e.target.files[0];
                    if (f) { this.file = f; this.sent = false; }
                },

                onDrop: function(e) {
                    e.preventDefault();
                    this.dragOver = false;
                    var f = e.dataTransfer.files && e.dataTransfer.files[0];
                    if (f) {
                        try {
                            var dt = new DataTransfer();
                            dt.items.add(f);
                            this.$refs.fileInput.files = dt.files;
                        } catch(_) {}
                        this.file = f;
                        this.sent = false;
                    }
                },

                onDragOver: function(e) {
                    e.preventDefault();
                    this.dragOver = true;
                },

                onDragLeave: function(e) {
                    if (!e.currentTarget.contains(e.relatedTarget)) {
                        this.dragOver = false;
                    }
                },

                removeFile: function() {
                    this.file = null;
                    this.sent = false;
                    this.$refs.fileInput.value = '';
                },

                init: function() {
                    var self = this;
                    this._onDoc = function(e) {
                        if (self.menuOpen && self.$refs.dropdown && !self.$refs.dropdown.contains(e.target)) {
                            self.menuOpen = false;
                        }
                    };
                    this._onKey = function(e) {
                        if (e.key === 'Escape' && self.menuOpen) self.menuOpen = false;
                    };
                    document.addEventListener('mousedown', this._onDoc);
                    document.addEventListener('keydown', this._onKey);

                    this.$el.addEventListener('htmx:afterRequest', function(e) {
                        if (e.detail.successful) {
                            self.sent = true;
                            self.file = null;
                            self.$refs.fileInput.value = '';
                            clearTimeout(self._st);
                            self._st = setTimeout(function() { self.sent = false; }, 3400);
                        }
                    });
                },

                destroy: function() {
                    document.removeEventListener('mousedown', this._onDoc);
                    document.removeEventListener('keydown', this._onKey);
                    clearTimeout(this._st);
                }
            };
        });

    });

    // Icons are server-rendered inline SVG (ui/components/icon.py) and pre-rendered
    // into x-html bindings (ui/today/orchestrator.py), so there is no client-side
    // icon scan — no lucide.createIcons() and no MutationObserver to self-trigger.

})();
