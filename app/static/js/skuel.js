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

        // ---------------------------------------------------------------------
        // Insight Swipe Actions Component - Phase 2 Task 10
        // ---------------------------------------------------------------------
        /**
         * Touch-friendly swipe and long-press actions for insight cards.
         * Supports swipe-to-dismiss and long-press action menu.
         *
         * @param {string} insight_uid - Insight UID
         * @returns {Object} Alpine.js component
         *
         * @example
         * <div x-data="insightSwipeActions('insight_abc')" @touchstart="handleTouchStart($event)" @touchend="handleTouchEnd($event)">
         *   <div x-show="showDismissButton">Swipe left to dismiss</div>
         * </div>
         */
        Alpine.data('insightSwipeActions', function(insight_uid) {
            return {
                insight_uid: insight_uid,
                touchStartX: 0,
                touchStartY: 0,
                touchStartTime: 0,
                longPressTimer: null,
                showActionMenu: false,
                showDismissButton: false,
                translateX: 0,

                handleTouchStart: function(event) {
                    this.touchStartX = event.changedTouches[0].screenX;
                    this.touchStartY = event.changedTouches[0].screenY;
                    this.touchStartTime = Date.now();

                    // Start long-press timer (800ms)
                    var self = this;
                    this.longPressTimer = setTimeout(function() {
                        self.showActionMenu = true;
                        // Haptic feedback (if supported)
                        if (navigator.vibrate) {
                            navigator.vibrate(50);
                        }
                    }, 800);
                },

                handleTouchMove: function(event) {
                    var touchX = event.changedTouches[0].screenX;
                    var deltaX = touchX - this.touchStartX;

                    // Only allow left swipe
                    if (deltaX < 0) {
                        this.translateX = Math.max(deltaX, -100); // Max 100px left
                    }

                    // Cancel long-press if moved
                    if (Math.abs(deltaX) > 10) {
                        clearTimeout(this.longPressTimer);
                    }
                },

                handleTouchEnd: function(event) {
                    clearTimeout(this.longPressTimer);

                    var touchEndX = event.changedTouches[0].screenX;
                    var deltaX = touchEndX - this.touchStartX;

                    // Swipe left threshold: -80px
                    if (deltaX < -80) {
                        this.showDismissButton = true;
                        this.translateX = -100;
                    } else {
                        // Reset position
                        this.translateX = 0;
                        this.showDismissButton = false;
                    }
                },

                dismissCard: async function() {
                    var self = this;
                    try {
                        var response = await fetch('/api/insights/' + this.insight_uid + '/dismiss', {
                            method: 'POST'
                        });

                        if (response.ok) {
                            // Hide card with animation
                            var card = document.getElementById('insight-' + this.insight_uid);
                            if (card) {
                                card.style.opacity = '0';
                                card.style.transform = 'translateX(-100%)';
                                card.style.transition = 'all 0.3s ease';

                                // Remove after animation
                                setTimeout(function() {
                                    card.remove();
                                }, 300);
                            }
                        } else {
                            alert('Failed to dismiss insight');
                        }
                    } catch (err) {
                        console.error('Dismiss failed:', err);
                        alert('Failed to dismiss insight');
                    }
                },

                actionCard: async function() {
                    var self = this;
                    this.showActionMenu = false;

                    try {
                        var response = await fetch('/api/insights/' + this.insight_uid + '/action', {
                            method: 'POST'
                        });

                        if (response.ok) {
                            // Reload page to show updated state
                            window.location.reload();
                        } else {
                            alert('Failed to mark insight as actioned');
                        }
                    } catch (err) {
                        console.error('Action failed:', err);
                        alert('Failed to mark insight as actioned');
                    }
                },

                closeActionMenu: function() {
                    this.showActionMenu = false;
                }
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
                        var response = await fetch('/api/insights/bulk/dismiss', {
                            method: 'POST',
                            headers: {
                                'Content-Type': 'application/json'
                            },
                            body: JSON.stringify({ uids: uids })
                        });

                        if (response.ok) {
                            // Reload page to show updated insights
                            window.location.reload();
                        } else {
                            var error = await response.json();
                            alert('Failed to dismiss insights: ' + (error.detail || 'Unknown error'));
                        }
                    } catch (err) {
                        console.error('Bulk dismiss failed:', err);
                        alert('Failed to dismiss insights. Please try again.');
                    }
                },

                // Bulk mark as actioned
                bulkMarkActioned: async function() {
                    var self = this;
                    if (this.selectedUids.size === 0) return;

                    var uids = Array.from(this.selectedUids);

                    try {
                        var response = await fetch('/api/insights/bulk/action', {
                            method: 'POST',
                            headers: {
                                'Content-Type': 'application/json'
                            },
                            body: JSON.stringify({ uids: uids })
                        });

                        if (response.ok) {
                            // Reload page to show updated insights
                            window.location.reload();
                        } else {
                            var error = await response.json();
                            alert('Failed to mark insights as actioned: ' + (error.detail || 'Unknown error'));
                        }
                    } catch (err) {
                        console.error('Bulk action failed:', err);
                        alert('Failed to mark insights as actioned. Please try again.');
                    }
                },

                // Smart bulk dismiss (dismiss all of a certain type/impact)
                smartDismiss: async function(filter_type, filter_value) {
                    try {
                        var response = await fetch('/api/insights/bulk/smart-dismiss', {
                            method: 'POST',
                            headers: {
                                'Content-Type': 'application/json'
                            },
                            body: JSON.stringify({
                                filter_type: filter_type,
                                filter_value: filter_value
                            })
                        });

                        if (response.ok) {
                            // Reload page to show updated insights
                            window.location.reload();
                        } else {
                            var error = await response.json();
                            alert('Failed to dismiss insights: ' + (error.detail || 'Unknown error'));
                        }
                    } catch (err) {
                        console.error('Smart dismiss failed:', err);
                        alert('Failed to dismiss insights. Please try again.');
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
                        var response = await fetch(
                            '/api/' + self.entity_type + '/' + self.entity_uid + '/lateral/graph?depth=' + depth
                        );

                        if (!response.ok) {
                            throw new Error('HTTP ' + response.status);
                        }

                        var data = await response.json();
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
                    if (typeof vis === 'undefined' || !vis.Network) {
                        console.error('Vis.js Network library not loaded');
                        this.error = 'Graph library not loaded';
                        return;
                    }

                    // Vis.js options
                    var options = {
                        nodes: {
                            shape: 'dot',
                            size: 16,
                            font: {
                                size: 14,
                                color: '#333'
                            },
                            borderWidth: 2,
                            shadow: true
                        },
                        edges: {
                            width: 2,
                            shadow: true,
                            smooth: {
                                type: 'continuous'
                            }
                        },
                        physics: {
                            forceAtlas2Based: {
                                gravitationalConstant: -50,
                                centralGravity: 0.01,
                                springLength: 100,
                                springConstant: 0.08
                            },
                            maxVelocity: 50,
                            solver: 'forceAtlas2Based',
                            timestep: 0.35,
                            stabilization: {
                                iterations: 150
                            }
                        },
                        interaction: {
                            hover: true,
                            tooltipDelay: 200
                        }
                    };

                    // Create network
                    this.network = new vis.Network(container, data, options);

                    // Click handler - navigate to entity
                    var self = this;
                    this.network.on('click', function(params) {
                        if (params.nodes.length > 0) {
                            var nodeId = params.nodes[0];
                            var node = data.nodes.find(function(n) { return n.id === nodeId; });
                            if (node && node.id !== self.entity_uid) {
                                window.location.href = '/' + node.type + '/' + node.id;
                            }
                        }
                    });
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

                // Sort options by domain type
                getSortOptions: function(domainType) {
                    var common = [
                        { value: 'title', label: 'Alphabetical' },
                        { value: 'created', label: 'Recently Created' }
                    ];

                    if (domainType === 'tasks') {
                        return [
                            { value: 'priority', label: 'Priority' },
                            { value: 'due_date', label: 'Due Date' }
                        ].concat(common);
                    } else if (domainType === 'goals') {
                        return [
                            { value: 'priority', label: 'Priority' },
                            { value: 'target_date', label: 'Target Date' },
                            { value: 'progress', label: 'Progress' }
                        ].concat(common);
                    } else if (domainType === 'habits') {
                        return [
                            { value: 'streak', label: 'Streak' },
                            { value: 'frequency', label: 'Frequency' }
                        ].concat(common);
                    } else if (domainType === 'events') {
                        return [
                            { value: 'start_date', label: 'Start Date' }
                        ].concat(common);
                    } else {
                        return common;
                    }
                },

                // Filter presets by domain type
                getFilterPresets: function(domainType) {
                    if (domainType === 'tasks') {
                        return [
                            { value: 'all', label: 'All Tasks' },
                            { value: 'overdue', label: 'Overdue' },
                            { value: 'high_priority', label: 'High Priority' },
                            { value: 'this_week', label: 'Due This Week' }
                        ];
                    } else if (domainType === 'goals') {
                        return [
                            { value: 'all', label: 'All Goals' },
                            { value: 'at_risk', label: 'At Risk' },
                            { value: 'near_complete', label: 'Almost Done' }
                        ];
                    } else if (domainType === 'habits') {
                        return [
                            { value: 'all', label: 'All Habits' },
                            { value: 'at_risk', label: 'At Risk' },
                            { value: 'keystone', label: 'Keystone Habits' }
                        ];
                    } else if (domainType === 'events') {
                        return [
                            { value: 'all', label: 'All Events' },
                            { value: 'today', label: 'Today' },
                            { value: 'this_week', label: 'This Week' }
                        ];
                    } else {
                        return [
                            { value: 'all', label: 'All' }
                        ];
                    }
                },

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

                    fetch('/api/insights/' + this.insightUid + '/details')
                        .then(function(response) {
                            if (!response.ok) {
                                throw new Error('Failed to load insight details');
                            }
                            return response.json();
                        })
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

                    fetch('/api/insights/' + this.insightUid + '/snooze', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({days: days})
                    })
                        .then(function(response) {
                            if (!response.ok) {
                                throw new Error('Failed to snooze insight');
                            }
                            self.close();
                            // Reload page or remove card
                            window.location.reload();
                        })
                        .catch(function(err) {
                            alert('Failed to snooze insight: ' + err.message);
                        });
                },

                // Get color class for confidence level
                getConfidenceColor: function(confidence) {
                    if (confidence >= 0.8) return 'text-success';
                    if (confidence >= 0.6) return 'text-warning';
                    return 'text-error';
                },

                // Get label for confidence level
                getConfidenceLabel: function(confidence) {
                    if (confidence >= 0.8) return 'High Confidence';
                    if (confidence >= 0.6) return 'Medium Confidence';
                    return 'Low Confidence';
                }
            };
        });

        // ---------------------------------------------------------------------
        // Profile Drawer Component (Phase 3, Task 14)
        // ---------------------------------------------------------------------
        /**
         * Manages profile sidebar drawer with swipe gestures and smart persistence.
         * Handles mobile drawer state, swipe-to-open/close, and localStorage persistence.
         *
         * @returns {Object} Alpine.js component
         *
         * @example
         * <div x-data="profileDrawer()">
         *   <input type="checkbox" id="profile-drawer" x-model="isOpen">
         *   <div @touchstart="handleTouchStart" @touchmove="handleTouchMove" @touchend="handleTouchEnd">
         *     <!-- Content -->
         *   </div>
         * </div>
         */
        Alpine.data('profileDrawer', function() {
            return {
                isOpen: false,
                touchStartX: 0,
                touchCurrentX: 0,
                isSwiping: false,

                init: function() {
                    // Restore drawer state from localStorage
                    var stored = localStorage.getItem('profile-drawer-open');
                    if (stored !== null) {
                        this.isOpen = stored === 'true';
                    }

                    // On tablet/desktop (≥768px), keep drawer open by default
                    if (window.innerWidth >= 768 && stored === null) {
                        this.isOpen = true;
                    }

                    // Sync with checkbox
                    var checkbox = document.getElementById('profile-drawer');
                    if (checkbox) {
                        checkbox.checked = this.isOpen;
                    }

                    // Watch for window resize
                    var self = this;
                    window.addEventListener('resize', function() {
                        // Auto-open on tablet+ if not explicitly closed
                        if (window.innerWidth >= 768 && localStorage.getItem('profile-drawer-open') !== 'false') {
                            self.isOpen = true;
                            if (checkbox) checkbox.checked = true;
                        }
                    });
                },

                toggle: function() {
                    this.isOpen = !this.isOpen;
                    this.saveState();
                },

                open: function() {
                    this.isOpen = true;
                    this.saveState();
                },

                close: function() {
                    this.isOpen = false;
                    this.saveState();
                },

                saveState: function() {
                    localStorage.setItem('profile-drawer-open', this.isOpen.toString());
                    // Sync with checkbox
                    var checkbox = document.getElementById('profile-drawer');
                    if (checkbox) {
                        checkbox.checked = this.isOpen;
                    }
                },

                // Touch event handlers for swipe gestures
                handleTouchStart: function(event) {
                    this.touchStartX = event.touches[0].clientX;
                    this.isSwiping = true;
                },

                handleTouchMove: function(event) {
                    if (!this.isSwiping) return;
                    this.touchCurrentX = event.touches[0].clientX;
                },

                handleTouchEnd: function(event) {
                    if (!this.isSwiping) return;
                    this.isSwiping = false;

                    var deltaX = this.touchCurrentX - this.touchStartX;
                    var threshold = 50; // Minimum swipe distance in pixels

                    // Swipe right to open (only if starting from left edge)
                    if (deltaX > threshold && this.touchStartX < 50 && !this.isOpen) {
                        this.open();
                    }
                    // Swipe left to close
                    else if (deltaX < -threshold && this.isOpen) {
                        this.close();
                    }

                    // Reset
                    this.touchStartX = 0;
                    this.touchCurrentX = 0;
                },

                // Close drawer on mobile after navigation (optional)
                closeOnMobile: function() {
                    if (window.innerWidth < 768) {
                        this.close();
                    }
                }
            };
        });

        // ---------------------------------------------------------------------
        // Profile Intelligence Cache Component (Phase 4, Task 15)
        // ---------------------------------------------------------------------
        /**
         * Caches profile intelligence data with background refresh.
         * Uses localStorage to persist data and reduce 2-3s load times.
         *
         * @returns {Object} Alpine.js component
         *
         * @example
         * <div x-data="intelligenceCache()">
         *   <div x-show="loading && !hasCache">Loading...</div>
         *   <div x-show="hasCache" x-html="intelligenceHtml"></div>
         *   <span x-text="lastUpdatedText"></span>
         * </div>
         */
        Alpine.data('intelligenceCache', function() {
            return {
                intelligenceHtml: '',
                lastUpdated: null,
                loading: false,
                error: null,
                refreshInterval: null,

                // Computed: has cached data
                get hasCache() {
                    return this.intelligenceHtml !== '';
                },

                // Computed: last updated text
                get lastUpdatedText() {
                    if (!this.lastUpdated) return '';

                    var now = new Date();
                    var updated = new Date(this.lastUpdated);
                    var diffMinutes = Math.floor((now - updated) / 60000);

                    if (diffMinutes < 1) return 'Updated just now';
                    if (diffMinutes === 1) return 'Updated 1 minute ago';
                    if (diffMinutes < 60) return 'Updated ' + diffMinutes + ' minutes ago';

                    var diffHours = Math.floor(diffMinutes / 60);
                    if (diffHours === 1) return 'Updated 1 hour ago';
                    return 'Updated ' + diffHours + ' hours ago';
                },

                init: function() {
                    var self = this;

                    // Load from localStorage
                    this.loadFromCache();

                    // Fetch fresh data (optimistic - show cache while loading)
                    this.refresh();

                    // Set up auto-refresh every 5 minutes
                    this.refreshInterval = setInterval(function() {
                        self.refresh();
                    }, 5 * 60 * 1000); // 5 minutes

                    // Clean up interval on component destroy
                    this.$cleanup = function() {
                        if (self.refreshInterval) {
                            clearInterval(self.refreshInterval);
                        }
                    };
                },

                loadFromCache: function() {
                    try {
                        var cached = localStorage.getItem('profile-intelligence-cache');
                        if (cached) {
                            var data = JSON.parse(cached);
                            this.intelligenceHtml = data.html || '';
                            this.lastUpdated = data.timestamp || null;

                            // Check if cache is stale (> 5 minutes)
                            if (this.lastUpdated) {
                                var age = Date.now() - new Date(this.lastUpdated).getTime();
                                if (age > 5 * 60 * 1000) {
                                    SKUEL.debug('Intelligence cache is stale, will refresh');
                                }
                            }
                        }
                    } catch (e) {
                        SKUEL.debug('Failed to load intelligence from cache', e);
                    }
                },

                saveToCache: function() {
                    try {
                        var data = {
                            html: this.intelligenceHtml,
                            timestamp: this.lastUpdated
                        };
                        localStorage.setItem('profile-intelligence-cache', JSON.stringify(data));
                    } catch (e) {
                        SKUEL.debug('Failed to save intelligence to cache', e);
                    }
                },

                refresh: function() {
                    var self = this;
                    self.loading = true;
                    self.error = null;

                    fetch('/api/profile/intelligence-section')
                        .then(function(response) {
                            if (!response.ok) {
                                throw new Error('Failed to load intelligence data');
                            }
                            return response.text();
                        })
                        .then(function(html) {
                            self.intelligenceHtml = html;
                            self.lastUpdated = new Date().toISOString();
                            self.saveToCache();
                            self.loading = false;
                        })
                        .catch(function(err) {
                            self.error = err.message;
                            self.loading = false;
                            SKUEL.debug('Failed to refresh intelligence', err);
                        });
                },

                invalidate: function() {
                    // Clear cache and force refresh
                    this.intelligenceHtml = '';
                    this.lastUpdated = null;
                    localStorage.removeItem('profile-intelligence-cache');
                    this.refresh();
                }
            };
        });

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

})();
