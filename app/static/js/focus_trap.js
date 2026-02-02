/**
 * Focus Trap Utility
 * ===================
 *
 * Accessible focus management for modals, dialogs, and drawers.
 * Implements WCAG 2.1 Level AA requirements for focus management.
 *
 * Features:
 * - Tab cycles within container (no focus escape)
 * - Shift+Tab reverses direction
 * - Escape key support (customizable)
 * - Focus restoration when trap is released
 * - Auto-focus first/specified element when activated
 *
 * Usage:
 *   const trap = new FocusTrap(element, {
 *     onEscape: () => closeModal(),
 *     initialFocus: '.modal-input',
 *     restoreFocus: true
 *   });
 *   trap.activate();
 *   // Later...
 *   trap.deactivate();
 *
 * WCAG Success Criteria:
 * - 2.1.2 No Keyboard Trap (Level A)
 * - 2.4.3 Focus Order (Level A)
 * - 2.4.7 Focus Visible (Level AA)
 */

(function(window) {
    'use strict';

    /**
     * Focusable element selectors
     * @const {string}
     */
    const FOCUSABLE_ELEMENTS = [
        'a[href]',
        'area[href]',
        'input:not([disabled]):not([type="hidden"])',
        'select:not([disabled])',
        'textarea:not([disabled])',
        'button:not([disabled])',
        'iframe',
        'object',
        'embed',
        '[contenteditable]',
        '[tabindex]:not([tabindex^="-"])'
    ].join(', ');

    /**
     * FocusTrap Constructor
     * @param {HTMLElement} element - Container element to trap focus within
     * @param {Object} options - Configuration options
     * @param {Function} options.onEscape - Callback when Escape is pressed
     * @param {string|HTMLElement} options.initialFocus - Element to focus when activated
     * @param {boolean} options.restoreFocus - Whether to restore focus on deactivate (default: true)
     * @param {boolean} options.allowEscape - Whether Escape key closes trap (default: true)
     * @param {Function} options.onActivate - Callback when trap is activated
     * @param {Function} options.onDeactivate - Callback when trap is deactivated
     */
    function FocusTrap(element, options) {
        if (!element) {
            throw new Error('FocusTrap requires an element');
        }

        this.element = element;
        this.options = Object.assign({
            onEscape: null,
            initialFocus: null,
            restoreFocus: true,
            allowEscape: true,
            onActivate: null,
            onDeactivate: null
        }, options || {});

        this.active = false;
        this.previousFocus = null;
        this.boundKeydownHandler = this._handleKeydown.bind(this);
        this.boundFocusHandler = this._handleFocus.bind(this);
    }

    /**
     * Get all focusable elements within the container
     * @returns {HTMLElement[]} Array of focusable elements
     * @private
     */
    FocusTrap.prototype._getFocusableElements = function() {
        var elements = this.element.querySelectorAll(FOCUSABLE_ELEMENTS);
        // Filter out elements that are not visible or have visibility:hidden
        return Array.from(elements).filter(function(el) {
            return !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length);
        });
    };

    /**
     * Handle keydown events (Tab, Shift+Tab, Escape)
     * @param {KeyboardEvent} e - Keyboard event
     * @private
     */
    FocusTrap.prototype._handleKeydown = function(e) {
        if (!this.active) return;

        // Escape key
        if (e.key === 'Escape' || e.keyCode === 27) {
            if (this.options.allowEscape) {
                e.preventDefault();
                if (typeof this.options.onEscape === 'function') {
                    this.options.onEscape();
                } else {
                    this.deactivate();
                }
            }
            return;
        }

        // Tab key
        if (e.key === 'Tab' || e.keyCode === 9) {
            this._handleTab(e);
        }
    };

    /**
     * Handle Tab/Shift+Tab to cycle through focusable elements
     * @param {KeyboardEvent} e - Keyboard event
     * @private
     */
    FocusTrap.prototype._handleTab = function(e) {
        var focusableElements = this._getFocusableElements();

        if (focusableElements.length === 0) {
            e.preventDefault();
            return;
        }

        if (focusableElements.length === 1) {
            e.preventDefault();
            focusableElements[0].focus();
            return;
        }

        var firstElement = focusableElements[0];
        var lastElement = focusableElements[focusableElements.length - 1];
        var activeElement = document.activeElement;

        // Shift+Tab on first element -> focus last element
        if (e.shiftKey) {
            if (activeElement === firstElement) {
                e.preventDefault();
                lastElement.focus();
            }
        }
        // Tab on last element -> focus first element
        else {
            if (activeElement === lastElement) {
                e.preventDefault();
                firstElement.focus();
            }
        }
    };

    /**
     * Handle focus events to prevent focus from escaping
     * @param {FocusEvent} e - Focus event
     * @private
     */
    FocusTrap.prototype._handleFocus = function(e) {
        if (!this.active) return;

        var target = e.target;

        // If focus moves outside the container, bring it back
        if (!this.element.contains(target)) {
            e.preventDefault();
            e.stopPropagation();

            var focusableElements = this._getFocusableElements();
            if (focusableElements.length > 0) {
                focusableElements[0].focus();
            }
        }
    };

    /**
     * Activate the focus trap
     * @public
     */
    FocusTrap.prototype.activate = function() {
        if (this.active) return;

        // Save currently focused element
        this.previousFocus = document.activeElement;

        // Activate trap
        this.active = true;

        // Add event listeners
        document.addEventListener('keydown', this.boundKeydownHandler, true);
        document.addEventListener('focus', this.boundFocusHandler, true);

        // Focus initial element
        this._setInitialFocus();

        // Callback
        if (typeof this.options.onActivate === 'function') {
            this.options.onActivate();
        }
    };

    /**
     * Set initial focus when trap is activated
     * @private
     */
    FocusTrap.prototype._setInitialFocus = function() {
        var self = this;

        // Use requestAnimationFrame to ensure DOM is ready
        requestAnimationFrame(function() {
            var elementToFocus = null;

            // 1. Try specified initialFocus option
            if (self.options.initialFocus) {
                if (typeof self.options.initialFocus === 'string') {
                    elementToFocus = self.element.querySelector(self.options.initialFocus);
                } else if (self.options.initialFocus instanceof HTMLElement) {
                    elementToFocus = self.options.initialFocus;
                }
            }

            // 2. Try to find an element with autofocus attribute
            if (!elementToFocus) {
                elementToFocus = self.element.querySelector('[autofocus]');
            }

            // 3. Fall back to first focusable element
            if (!elementToFocus) {
                var focusableElements = self._getFocusableElements();
                if (focusableElements.length > 0) {
                    elementToFocus = focusableElements[0];
                }
            }

            // 4. If still nothing, focus the container itself (if it's focusable)
            if (!elementToFocus && self.element.tabIndex >= 0) {
                elementToFocus = self.element;
            }

            // Focus the element
            if (elementToFocus) {
                elementToFocus.focus();
            }
        });
    };

    /**
     * Deactivate the focus trap
     * @public
     */
    FocusTrap.prototype.deactivate = function() {
        if (!this.active) return;

        // Deactivate trap
        this.active = false;

        // Remove event listeners
        document.removeEventListener('keydown', this.boundKeydownHandler, true);
        document.removeEventListener('focus', this.boundFocusHandler, true);

        // Restore focus
        if (this.options.restoreFocus && this.previousFocus) {
            // Use requestAnimationFrame to ensure element is still in DOM
            var previousFocus = this.previousFocus;
            requestAnimationFrame(function() {
                if (document.body.contains(previousFocus)) {
                    previousFocus.focus();
                }
            });
        }

        this.previousFocus = null;

        // Callback
        if (typeof this.options.onDeactivate === 'function') {
            this.options.onDeactivate();
        }
    };

    /**
     * Update trap options
     * @param {Object} newOptions - New options to merge
     * @public
     */
    FocusTrap.prototype.updateOptions = function(newOptions) {
        this.options = Object.assign(this.options, newOptions || {});
    };

    /**
     * Check if trap is active
     * @returns {boolean}
     * @public
     */
    FocusTrap.prototype.isActive = function() {
        return this.active;
    };

    /**
     * Destroy the focus trap (cleanup)
     * @public
     */
    FocusTrap.prototype.destroy = function() {
        this.deactivate();
        this.element = null;
        this.options = null;
        this.previousFocus = null;
    };

    // Expose to global scope
    window.FocusTrap = FocusTrap;

    // Also expose as SKUEL.FocusTrap
    if (window.SKUEL) {
        window.SKUEL.FocusTrap = FocusTrap;
    }

})(window);
