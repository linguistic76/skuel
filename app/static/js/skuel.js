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

                // Entity type to filter group mapping
                entityTypeFilters: {
                    'task': ['common', 'status', 'priority'],
                    'goal': ['common', 'status', 'priority'],
                    'habit': ['common', 'status', 'frequency'],
                    'event': ['common', 'status', 'priority', 'event_type'],
                    'choice': ['common', 'status', 'urgency'],
                    'principle': ['common', 'status', 'strength'],
                    'ku': ['knowledge', 'sel_category', 'learning_level', 'content_type', 'educational_level'],
                    'ls': ['knowledge', 'sel_category', 'learning_level'],
                    'lp': ['knowledge', 'sel_category', 'learning_level'],
                    'moc': ['knowledge', 'sel_category']
                },

                // Entity type labels for badges
                entityTypeLabels: {
                    'task': 'Tasks',
                    'goal': 'Goals',
                    'habit': 'Habits',
                    'event': 'Events',
                    'choice': 'Choices',
                    'principle': 'Principles',
                    'ku': 'Knowledge Units',
                    'ls': 'Learning Steps',
                    'lp': 'Learning Paths',
                    'moc': 'Maps of Content'
                },

                // Computed: should show context filters row
                get showContextFilters() {
                    return this.entityType !== '';
                },

                // Computed: label for context filter section
                get contextFilterLabel() {
                    if (!this.entityType) return 'Filters';
                    var isKnowledge = ['ku', 'ls', 'lp', 'moc'].indexOf(this.entityType) !== -1;
                    return isKnowledge ? 'Knowledge Filters' : 'Activity Filters';
                },

                // Computed: has any active filters
                get hasActiveFilters() {
                    return this.entityType !== '';
                },

                isFilterVisible: function(group) {
                    if (!this.entityType) return false;
                    var filters = this.entityTypeFilters[this.entityType] || [];
                    return filters.indexOf(group) !== -1;
                },

                getFilterLabel: function(filterType, value) {
                    if (filterType === 'entity_type') {
                        return this.entityTypeLabels[value] || value;
                    }
                    return value;
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

                    // Trigger search update
                    var firstSelect = document.querySelector('[name="entity_type"]');
                    if (firstSelect) {
                        firstSelect.dispatchEvent(new Event('change', { bubbles: true }));
                    }
                },

                init: function() {
                    // Nothing special needed for horizontal layout
                }
            };
        });

        // ---------------------------------------------------------------------
        // Search Sidebar Component (Legacy - kept for backward compatibility)
        // ---------------------------------------------------------------------
        // Handles sidebar toggle, filter visibility, and localStorage persistence
        Alpine.data('searchSidebar', function() {
            return {
                collapsed: localStorage.getItem('search-sidebar-collapsed') === 'true',
                isMobile: window.innerWidth <= 768,
                entityType: '',

                // Entity type to filter group mapping
                entityTypeFilters: {
                    'task': ['common', 'status', 'priority'],
                    'goal': ['common', 'status', 'priority'],
                    'habit': ['common', 'status', 'frequency'],
                    'event': ['common', 'status', 'priority', 'event_type'],
                    'choice': ['common', 'status', 'urgency'],
                    'principle': ['common', 'status', 'strength'],
                    'ku': ['knowledge', 'sel_category', 'learning_level', 'content_type', 'educational_level'],
                    'ls': ['knowledge', 'sel_category', 'learning_level'],
                    'lp': ['knowledge', 'sel_category', 'learning_level'],
                    'moc': ['knowledge', 'sel_category']
                },

                toggle: function() {
                    this.collapsed = !this.collapsed;
                    localStorage.setItem('search-sidebar-collapsed', this.collapsed);
                },

                isFilterVisible: function(group) {
                    if (!this.entityType) return true;
                    var filters = this.entityTypeFilters[this.entityType] || [];
                    return filters.indexOf(group) !== -1;
                },

                setEntityType: function(type) {
                    this.entityType = type;
                },

                init: function() {
                    var self = this;
                    // Start collapsed on mobile
                    if (this.isMobile) {
                        this.collapsed = true;
                    }
                    // Listen for resize
                    window.addEventListener('resize', function() {
                        self.isMobile = window.innerWidth <= 768;
                    });
                }
            };
        });

        // ---------------------------------------------------------------------
        // Calendar Page Component (Combined Modal + Drag-Drop)
        // ---------------------------------------------------------------------
        // Unified component for calendar views - modal state and drag-drop
        Alpine.data('calendarPage', function() {
            return {
                // Modal state
                open: false,
                datetime: '',

                // Drag-drop state
                draggedItemId: null,

                // Modal methods
                openQuickAdd: function(defaultDate, defaultHour) {
                    this.open = true;
                    if (defaultDate && defaultHour !== undefined) {
                        var hour = String(defaultHour).padStart(2, '0');
                        this.datetime = defaultDate + 'T' + hour + ':00';
                    } else if (defaultDate) {
                        this.datetime = defaultDate + 'T09:00';
                    } else {
                        var now = new Date();
                        var local = new Date(now.getTime() - now.getTimezoneOffset() * 60000);
                        this.datetime = local.toISOString().slice(0, 16);
                    }
                },

                closeQuickAdd: function() {
                    this.open = false;
                    // Clear status if present
                    var status = document.getElementById('quick-add-status');
                    if (status) status.innerHTML = '';
                },

                // Drag-drop methods
                handleDragStart: function(event, itemId) {
                    this.draggedItemId = itemId;
                    event.dataTransfer.effectAllowed = 'move';
                },

                handleDragOver: function(event) {
                    event.preventDefault();
                },

                handleDrop: function(event, newDateTime) {
                    event.preventDefault();

                    if (!this.draggedItemId) return;

                    // Set hidden form values for HTMX submission
                    this.$refs.rescheduleUid.value = this.draggedItemId;
                    this.$refs.rescheduleTime.value = newDateTime;

                    // Trigger HTMX form submission
                    htmx.trigger(this.$refs.rescheduleForm, 'submit');

                    // Clear drag state
                    this.draggedItemId = null;
                }
            };
        });

        // Standalone modal component (for cases where only modal is needed)
        Alpine.data('calendarModal', function() {
            return {
                open: false,
                datetime: '',

                openQuickAdd: function(defaultDate, defaultHour) {
                    this.open = true;
                    if (defaultDate && defaultHour !== undefined) {
                        var hour = String(defaultHour).padStart(2, '0');
                        this.datetime = defaultDate + 'T' + hour + ':00';
                    } else if (defaultDate) {
                        this.datetime = defaultDate + 'T09:00';
                    } else {
                        var now = new Date();
                        var local = new Date(now.getTime() - now.getTimezoneOffset() * 60000);
                        this.datetime = local.toISOString().slice(0, 16);
                    }
                },

                closeQuickAdd: function() {
                    this.open = false;
                    var status = document.getElementById('quick-add-status');
                    if (status) status.innerHTML = '';
                }
            };
        });

        // Standalone drag-drop component (for cases where only drag is needed)
        Alpine.data('calendarDrag', function() {
            return {
                draggedItemId: null,

                handleDragStart: function(event, itemId) {
                    this.draggedItemId = itemId;
                    event.dataTransfer.effectAllowed = 'move';
                },

                handleDragOver: function(event) {
                    event.preventDefault();
                },

                handleDrop: function(event, newDateTime) {
                    event.preventDefault();

                    if (!this.draggedItemId) return;

                    // Set hidden form values for HTMX submission
                    this.$refs.rescheduleUid.value = this.draggedItemId;
                    this.$refs.rescheduleTime.value = newDateTime;

                    // Trigger HTMX form submission
                    htmx.trigger(this.$refs.rescheduleForm, 'submit');

                    // Clear drag state
                    this.draggedItemId = null;
                }
            };
        });

        // ---------------------------------------------------------------------
        // Task Edit Modal Component
        // ---------------------------------------------------------------------
        // Handles task edit modal state (open/close)
        Alpine.data('taskEditModal', function() {
            return {
                open: false,

                init: function() {
                    // Open modal immediately when component initializes
                    this.open = true;
                },

                closeModal: function() {
                    var self = this;
                    this.open = false;
                    // Remove modal from DOM after close animation
                    setTimeout(function() {
                        var modal = document.getElementById('task-edit-modal');
                        if (modal) {
                            modal.remove();
                        }
                    }, 200);
                }
            };
        });

        // ---------------------------------------------------------------------
        // Timeline Viewer Component
        // ---------------------------------------------------------------------
        // Handles Markwhen timeline integration and URL history
        Alpine.data('timelineViewer', function(initialSource) {
            return {
                loading: true,
                source: initialSource || '/api/tasks/timeline',
                stats: {},
                timeline: null,

                init: function() {
                    var self = this;
                    this.loadTimeline(this.source);

                    // Handle browser back/forward
                    window.addEventListener('popstate', function() {
                        var params = new URLSearchParams(window.location.search);
                        var src = params.get('src') || '/api/tasks/timeline';
                        self.loadTimeline(src);
                    });
                },

                loadTimeline: function(sourceUrl) {
                    var self = this;
                    this.loading = true;

                    fetch(sourceUrl)
                        .then(function(response) {
                            if (!response.ok) {
                                throw new Error('Failed to load timeline: ' + response.status);
                            }
                            return response.text();
                        })
                        .then(function(markwhenContent) {
                            // Load stats
                            var previewUrl = sourceUrl.replace('/api/tasks/timeline', '/api/tasks/timeline/preview');
                            fetch(previewUrl)
                                .then(function(r) { return r.json(); })
                                .then(function(data) {
                                    if (data.success && data.stats) {
                                        self.stats = data.stats;
                                    }
                                })
                                .catch(function() { /* Stats are optional */ });

                            // Initialize Markwhen
                            var container = self.$refs.timelineContainer;
                            if (container) {
                                container.innerHTML = '';

                                if (window.markwhen) {
                                    self.timeline = window.markwhen.timeline(markwhenContent, {
                                        container: container,
                                        theme: 'light',
                                        showNow: true,
                                        showControls: true
                                    });
                                } else {
                                    // Fallback display
                                    container.innerHTML = '<pre style="padding:1rem;background:#f8f9fa;overflow:auto;">' +
                                        markwhenContent + '</pre>' +
                                        '<p><em>Install Markwhen for interactive visualization.</em></p>';
                                }
                            }
                            self.loading = false;
                        })
                        .catch(function(error) {
                            console.error('Timeline error:', error);
                            var container = self.$refs.timelineContainer;
                            if (container) {
                                container.innerHTML = '<div class="error"><h3>Timeline Load Error</h3>' +
                                    '<p>' + error.message + '</p></div>';
                            }
                            self.loading = false;
                        });
                },

                updateTimeline: function() {
                    var params = new URLSearchParams();

                    var startDate = this.$refs.startDate ? this.$refs.startDate.value : '';
                    var endDate = this.$refs.endDate ? this.$refs.endDate.value : '';
                    var project = this.$refs.project ? this.$refs.project.value : '';
                    var status = this.$refs.status ? this.$refs.status.value : '';

                    if (startDate) params.set('start_date', startDate);
                    if (endDate) params.set('end_date', endDate);
                    if (project) params.set('project', project);
                    if (status) params.set('status', status);
                    params.set('include_completed', 'true');

                    var newSource = '/api/tasks/timeline?' + params.toString();

                    // Update URL without reload
                    var newUrl = new URL(window.location);
                    newUrl.searchParams.set('src', newSource);
                    window.history.pushState({}, '', newUrl);

                    this.loadTimeline(newSource);
                }
            };
        });

        // ---------------------------------------------------------------------
        // Swipe Handler Component (from atomic_habits_mobile.py)
        // ---------------------------------------------------------------------
        /**
         * Touch gesture handler for mobile card swiping.
         * Supports velocity-based detection and adaptive thresholds.
         *
         * @param {number} totalCards - Total number of cards in the swipeable set
         * @returns {Object} Alpine.js component
         * @property {number} swipeIndex - Current card index (0-based)
         * @property {number} touchStartX - Touch start X coordinate
         * @property {number} touchStartY - Touch start Y coordinate
         * @property {number} touchStartTime - Touch start timestamp
         * @property {number} totalCards - Total number of cards
         *
         * @example
         * <div x-data="swipeHandler(3)" @touchstart="handleTouchStart($event)" @touchend="handleTouchEnd($event)">
         *   <div x-show="swipeIndex === 0">Card 1</div>
         *   <div x-show="swipeIndex === 1">Card 2</div>
         * </div>
         */
        Alpine.data('swipeHandler', function(totalCards) {
            return {
                swipeIndex: 0,
                touchStartX: 0,
                touchStartY: 0,
                touchStartTime: 0,
                totalCards: totalCards || 0,

                handleTouchStart: function(event) {
                    this.touchStartX = event.changedTouches[0].screenX;
                    this.touchStartY = event.changedTouches[0].screenY;
                    this.touchStartTime = Date.now();
                },

                handleTouchEnd: function(event) {
                    var touchEndX = event.changedTouches[0].screenX;
                    var touchEndY = event.changedTouches[0].screenY;
                    var touchEndTime = Date.now();

                    var deltaX = touchEndX - this.touchStartX;
                    var deltaY = touchEndY - this.touchStartY;
                    var duration = touchEndTime - this.touchStartTime;

                    // Velocity-based threshold (pixels per ms)
                    var velocity = Math.abs(deltaX) / duration;
                    var minVelocity = 0.3; // 0.3px/ms = fast flick

                    // Distance threshold (adaptive based on screen width)
                    var minDistance = window.innerWidth * 0.15; // 15% of screen width

                    // Horizontal swipe detection (more horizontal than vertical)
                    if (Math.abs(deltaY) < Math.abs(deltaX)) {
                        if (Math.abs(deltaX) > minDistance || velocity > minVelocity) {
                            if (deltaX > 0 && this.swipeIndex > 0) {
                                // Swipe right - previous
                                this.swipeIndex--;
                            } else if (deltaX < 0 && this.swipeIndex < this.totalCards - 1) {
                                // Swipe left - next
                                this.swipeIndex++;
                            }
                        }
                    }
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
        // Loading Button Component
        // ---------------------------------------------------------------------
        // Shows loading state during HTMX requests
        Alpine.data('loadingButton', function() {
            return {
                loading: false
            };
        });

        // ---------------------------------------------------------------------
        // Navbar Component
        // ---------------------------------------------------------------------
        // Handles mobile menu and profile dropdown state
        Alpine.data('navbar', function() {
            return {
                mobileMenuOpen: false,
                profileMenuOpen: false,

                toggleMobile: function() {
                    this.mobileMenuOpen = !this.mobileMenuOpen;
                },

                toggleProfile: function() {
                    this.profileMenuOpen = !this.profileMenuOpen;
                },

                closeProfile: function() {
                    this.profileMenuOpen = false;
                },

                init: function() {
                    var self = this;
                    // Close profile menu when clicking outside
                    document.addEventListener('click', function(e) {
                        var profileButton = e.target.closest('[data-profile-trigger]');
                        var profileMenu = document.getElementById('profile-dropdown');

                        if (!profileButton && profileMenu && !profileMenu.contains(e.target)) {
                            self.profileMenuOpen = false;
                        }
                    });
                }
            };
        });

        // ---------------------------------------------------------------------
        // Profile Sidebar Component
        // ---------------------------------------------------------------------
        // Handles profile hub drawer state with localStorage persistence
        Alpine.data('profileSidebar', function() {
            return {
                // Sync with drawer checkbox state
                init: function() {
                    var self = this;
                    var checkbox = document.getElementById('profile-drawer');
                    if (checkbox) {
                        // Restore saved state on desktop
                        if (window.innerWidth >= 1024) {
                            var savedState = localStorage.getItem('profile-sidebar-open');
                            // Default to open on desktop unless explicitly closed
                            checkbox.checked = savedState !== 'false';
                        }

                        // Persist state changes
                        checkbox.addEventListener('change', function() {
                            if (window.innerWidth >= 1024) {
                                localStorage.setItem('profile-sidebar-open', checkbox.checked);
                            }
                        });
                    }
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

                    fetch(url)
                        .then(function(response) {
                            if (!response.ok) {
                                throw new Error('Failed to load chart data: ' + response.status);
                            }
                            return response.json();
                        })
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
        // Vis.js Timeline Visualization Component
        // ---------------------------------------------------------------------
        // Renders interactive timeline using Vis.js
        Alpine.data('timelineVis', function(dataUrl) {
            return {
                timeline: null,
                loading: true,
                error: null,

                init: function() {
                    this.loadTimeline(dataUrl);
                },

                loadTimeline: function(url) {
                    var self = this;
                    this.loading = true;
                    this.error = null;

                    fetch(url)
                        .then(function(response) {
                            if (!response.ok) {
                                throw new Error('Failed to load timeline data: ' + response.status);
                            }
                            return response.json();
                        })
                        .then(function(data) {
                            var container = self.$refs.container;
                            if (!container) {
                                throw new Error('Container element not found');
                            }

                            // Destroy existing timeline if any
                            if (self.timeline) {
                                self.timeline.destroy();
                            }

                            // Check if vis-timeline is available
                            if (!window.vis || !window.vis.Timeline) {
                                throw new Error('Vis.js Timeline library not loaded');
                            }

                            // Create DataSets
                            var items = new vis.DataSet(data.items || []);
                            var groups = data.groups ? new vis.DataSet(data.groups) : null;

                            // Create timeline
                            var options = Object.assign({
                                stack: true,
                                showCurrentTime: true,
                                zoomable: true,
                                moveable: true,
                                orientation: { axis: 'top', item: 'bottom' }
                            }, data.options || {});

                            self.timeline = new vis.Timeline(container, items, groups, options);

                            // Event handlers
                            self.timeline.on('select', function(properties) {
                                if (properties.items.length > 0) {
                                    self.$dispatch('timeline-select', { itemId: properties.items[0] });
                                }
                            });

                            self.loading = false;
                        })
                        .catch(function(error) {
                            console.error('Timeline error:', error);
                            self.error = error.message;
                            self.loading = false;
                        });
                },

                refresh: function(newUrl) {
                    this.loadTimeline(newUrl || dataUrl);
                },

                fit: function() {
                    if (this.timeline) {
                        this.timeline.fit();
                    }
                },

                zoomIn: function() {
                    if (this.timeline) {
                        this.timeline.zoomIn(0.5);
                    }
                },

                zoomOut: function() {
                    if (this.timeline) {
                        this.timeline.zoomOut(0.5);
                    }
                },

                destroy: function() {
                    if (this.timeline) {
                        this.timeline.destroy();
                        this.timeline = null;
                    }
                }
            };
        });

        // ---------------------------------------------------------------------
        // Frappe Gantt Visualization Component
        // ---------------------------------------------------------------------
        // Renders Gantt chart using Frappe Gantt
        Alpine.data('ganttVis', function(dataUrl) {
            return {
                gantt: null,
                loading: true,
                error: null,
                viewMode: 'Week',

                init: function() {
                    this.loadGantt(dataUrl);
                },

                loadGantt: function(url) {
                    var self = this;
                    this.loading = true;
                    this.error = null;

                    fetch(url)
                        .then(function(response) {
                            if (!response.ok) {
                                throw new Error('Failed to load Gantt data: ' + response.status);
                            }
                            return response.json();
                        })
                        .then(function(data) {
                            var container = self.$refs.container;
                            if (!container) {
                                throw new Error('Container element not found');
                            }

                            // Check if Frappe Gantt is available
                            if (!window.Gantt) {
                                throw new Error('Frappe Gantt library not loaded');
                            }

                            // Clear container
                            container.innerHTML = '';

                            // Set view mode from data or default
                            self.viewMode = (data.options && data.options.view_mode) || 'Week';

                            // Create Gantt chart
                            self.gantt = new Gantt(container, data.tasks || [], {
                                view_mode: self.viewMode,
                                date_format: data.options?.date_format || 'YYYY-MM-DD',
                                popup_trigger: 'click',
                                language: 'en',

                                on_click: function(task) {
                                    self.$dispatch('gantt-click', { task: task });
                                },

                                on_date_change: function(task, start, end) {
                                    self.$dispatch('gantt-date-change', {
                                        task: task,
                                        start: start,
                                        end: end
                                    });
                                },

                                on_progress_change: function(task, progress) {
                                    self.$dispatch('gantt-progress-change', {
                                        task: task,
                                        progress: progress
                                    });
                                }
                            });

                            self.loading = false;
                        })
                        .catch(function(error) {
                            console.error('Gantt error:', error);
                            self.error = error.message;
                            self.loading = false;
                        });
                },

                refresh: function(newUrl) {
                    this.loadGantt(newUrl || dataUrl);
                },

                setViewMode: function(mode) {
                    if (this.gantt) {
                        this.viewMode = mode;
                        this.gantt.change_view_mode(mode);
                    }
                },

                destroy: function() {
                    if (this.gantt) {
                        // Frappe Gantt doesn't have a destroy method, clear container
                        var container = this.$refs.container;
                        if (container) {
                            container.innerHTML = '';
                        }
                        this.gantt = null;
                    }
                }
            };
        });

        // ---------------------------------------------------------------------
        // Choice Options Component (Dynamic Option Management)
        // ---------------------------------------------------------------------
        // Manages dynamic add/remove of options in Create Decision form
        Alpine.data('choiceOptions', function() {
            return {
                options: [
                    { title: '', description: '' },
                    { title: '', description: '' }
                ],

                addOption: function() {
                    this.options.push({ title: '', description: '' });
                },

                removeOption: function(index) {
                    if (this.options.length > 2) {
                        this.options.splice(index, 1);
                    }
                },

                canRemove: function() {
                    return this.options.length > 2;
                },

                isValid: function() {
                    if (this.options.length < 2) return false;
                    var self = this;
                    return this.options.every(function(o) {
                        return o.title.trim() !== '' && o.description.trim() !== '';
                    });
                }
            };
        });

        // ---------------------------------------------------------------------
        // Focus Trap Modal Component
        // ---------------------------------------------------------------------
        // Manages modal focus trapping and keyboard navigation
        Alpine.data('focusTrapModal', function(isOpen) {
            return {
                isOpen: isOpen || false,
                previousFocus: null,

                open: function() {
                    this.previousFocus = document.activeElement;
                    this.isOpen = true;

                    var self = this;
                    this.$nextTick(function() {
                        var modal = self.$refs.modal;
                        if (!modal) return;

                        var focusable = modal.querySelectorAll(
                            'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
                        );
                        if (focusable.length > 0) {
                            focusable[0].focus();
                        }
                    });
                },

                close: function() {
                    this.isOpen = false;
                    if (this.previousFocus && this.previousFocus.focus) {
                        this.previousFocus.focus();
                    }
                },

                handleKeydown: function(e) {
                    if (e.key === 'Escape') {
                        this.close();
                    } else if (e.key === 'Tab') {
                        this.trapFocus(e);
                    }
                },

                trapFocus: function(e) {
                    var modal = this.$refs.modal;
                    if (!modal) return;

                    var focusable = Array.from(modal.querySelectorAll(
                        'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
                    ));

                    if (focusable.length === 0) return;

                    var firstFocusable = focusable[0];
                    var lastFocusable = focusable[focusable.length - 1];

                    if (e.shiftKey && document.activeElement === firstFocusable) {
                        lastFocusable.focus();
                        e.preventDefault();
                    } else if (!e.shiftKey && document.activeElement === lastFocusable) {
                        firstFocusable.focus();
                        e.preventDefault();
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
                    document.body.addEventListener('htmx:afterSwap', function(event) {
                        var xhr = event.detail.xhr;
                        if (!xhr) return;

                        var successMsg = xhr.getResponseHeader('X-Toast-Message');
                        var successType = xhr.getResponseHeader('X-Toast-Type') || 'success';

                        if (successMsg) {
                            self.show(successMsg, successType);
                        }
                    });
                }
            };
        });

        // ---------------------------------------------------------------------
        // Form Validator Component
        // ---------------------------------------------------------------------
        // Client-side form validation with accessible error display
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
        // Live Region for Screen Reader Announcements
        // =========================================================================

        document.body.addEventListener('htmx:afterSwap', function(event) {
            var liveRegion = document.getElementById('live-region');
            if (!liveRegion) return;

            var target = event.detail.target;
            var announcement = target.dataset.liveAnnounce || 'Content updated';

            liveRegion.textContent = announcement;
            setTimeout(function() {
                liveRegion.textContent = '';
            }, 1000);
        });

        // =========================================================================
        // HTMX Integration - Initialize Alpine on dynamic content
        // =========================================================================

        // htmx:load fires on every element loaded via HTMX
        document.body.addEventListener('htmx:load', function(event) {
            var loadedElement = event.detail.elt;

            // Initialize Alpine.js if element has x-data
            if (window.Alpine && loadedElement) {
                if (loadedElement.hasAttribute && loadedElement.hasAttribute('x-data')) {
                    if (!loadedElement._x_dataStack) {
                        window.Alpine.initTree(loadedElement);
                    }
                }
                // Also check children
                var alpineElements = loadedElement.querySelectorAll ? loadedElement.querySelectorAll('[x-data]') : [];
                alpineElements.forEach(function(el) {
                    if (!el._x_dataStack) {
                        window.Alpine.initTree(el);
                    }
                });
            }

            // Process HTMX attributes on loaded content
            if (window.htmx && loadedElement) {
                window.htmx.process(loadedElement);
            }
        });
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
                    fetch('/api/' + this.entityType + '/bulk-delete', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({uids: this.selected}),
                    })
                    .then(function(response) { return response.json(); })
                    .then(function(data) {
                        self.$dispatch('toast', {
                            message: 'Deleted ' + self.selected.length + ' items',
                            type: 'success',
                        });
                        self.selected = [];
                        // Refresh tree
                        window.location.reload();
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
                    fetch(this.moveEndpoint.replace('{uid}', this.draggedNode), {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({new_parent_uid: newParentUid}),
                    })
                    .then(function(response) { return response.json(); })
                    .then(function(data) {
                        self.$dispatch('toast', {
                            message: 'Moved successfully',
                            type: 'success',
                        });
                        // Refresh affected nodes via HTMX
                        if (window.htmx) {
                            window.htmx.trigger('#children-' + newParentUid, 'refresh');
                        }
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
                    fetch('/api/' + this.entityType + '/' + uid, {
                        method: 'PATCH',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({title: newTitle}),
                    })
                    .then(function(response) { return response.json(); })
                    .then(function(data) {
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

    });

})();
