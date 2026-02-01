/* Profile Sidebar Toggle - Inspired by /nous pattern */

let profileSidebarCollapsed = false;
let previousFocusElement = null;  // Store focus before opening drawer

/**
 * P0: Trap focus within sidebar (prevent tabbing outside).
 * Based on focusTrapModal pattern from skuel.js.
 */
function trapFocusInSidebar(event) {
    if (event.key !== 'Tab') return;

    const sidebar = document.getElementById('profile-sidebar');
    if (!sidebar || profileSidebarCollapsed) return;

    const focusableSelector = 'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])';
    const focusableElements = Array.from(sidebar.querySelectorAll(focusableSelector));

    if (focusableElements.length === 0) return;

    const firstFocusable = focusableElements[0];
    const lastFocusable = focusableElements[focusableElements.length - 1];

    // Shift+Tab on first element → focus last element
    if (event.shiftKey && document.activeElement === firstFocusable) {
        lastFocusable.focus();
        event.preventDefault();
    }
    // Tab on last element → focus first element
    else if (!event.shiftKey && document.activeElement === lastFocusable) {
        firstFocusable.focus();
        event.preventDefault();
    }
}

/**
 * P0: Handle Escape key to close drawer (WCAG requirement).
 */
function handleSidebarKeydown(event) {
    if (event.key === 'Escape' && !profileSidebarCollapsed && window.innerWidth <= 1024) {
        toggleProfileSidebar();
    }
}

/**
 * P1: Announce drawer state change to screen readers.
 */
function announceDrawerState(isOpen) {
    const announcer = document.getElementById('sidebar-sr-announcements');
    if (!announcer) return;

    const message = isOpen
        ? 'Profile navigation opened'
        : 'Profile navigation closed';

    announcer.textContent = message;

    // Clear after 1 second (polite announcement)
    setTimeout(function() {
        announcer.textContent = '';
    }, 1000);
}

function toggleProfileSidebar() {
    const sidebar = document.getElementById('profile-sidebar');
    const content = document.getElementById('profile-content');
    const overlay = document.getElementById('profile-overlay');

    if (!sidebar || !content || !overlay) {
        console.warn('Profile sidebar elements not found');
        return;
    }

    profileSidebarCollapsed = !profileSidebarCollapsed;

    if (profileSidebarCollapsed) {
        // Closing drawer
        sidebar.classList.add('collapsed');
        content.classList.add('expanded');
        overlay.classList.remove('active');

        // P0: Remove event listeners
        document.removeEventListener('keydown', trapFocusInSidebar);
        document.removeEventListener('keydown', handleSidebarKeydown);

        // P0: Restore focus to trigger element
        if (previousFocusElement && previousFocusElement.focus) {
            previousFocusElement.focus();
            previousFocusElement = null;
        }

        // P0: Update ARIA states
        const toggleButton = document.querySelector('.sidebar-toggle');
        const mobileMenuButton = document.querySelector('.mobile-menu-button');
        if (toggleButton) toggleButton.setAttribute('aria-expanded', 'false');
        if (mobileMenuButton) mobileMenuButton.setAttribute('aria-expanded', 'false');
        if (window.innerWidth <= 1024) {
            sidebar.setAttribute('aria-modal', 'false');
        }

        // P1: Announce state change
        announceDrawerState(false);
    } else {
        // Opening drawer
        sidebar.classList.remove('collapsed');
        content.classList.remove('expanded');

        // Show overlay on mobile
        if (window.innerWidth <= 1024) {
            overlay.classList.add('active');

            // P0: Store current focus
            previousFocusElement = document.activeElement;

            // P0: Focus first focusable element in sidebar
            const focusableSelector = 'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])';
            const firstFocusable = sidebar.querySelector(focusableSelector);
            if (firstFocusable) {
                setTimeout(function() {
                    firstFocusable.focus();
                }, 100);
            }

            // P0: Add event listeners for focus trapping and Escape key
            document.addEventListener('keydown', trapFocusInSidebar);
            document.addEventListener('keydown', handleSidebarKeydown);

            // P1: Announce state change
            announceDrawerState(true);
        }

        // P0: Update ARIA states
        const toggleButton = document.querySelector('.sidebar-toggle');
        const mobileMenuButton = document.querySelector('.mobile-menu-button');
        if (toggleButton) toggleButton.setAttribute('aria-expanded', 'true');
        if (mobileMenuButton) mobileMenuButton.setAttribute('aria-expanded', 'true');
        if (window.innerWidth <= 1024) {
            sidebar.setAttribute('aria-modal', 'true');
        }
    }

    // Save state to localStorage
    localStorage.setItem('profile-sidebar-collapsed', profileSidebarCollapsed);
}

// Restore saved state on load
document.addEventListener('DOMContentLoaded', function() {
    const savedState = localStorage.getItem('profile-sidebar-collapsed');

    // Desktop: restore saved state
    if (window.innerWidth > 1024 && savedState === 'true') {
        toggleProfileSidebar();
    }

    // Mobile: always start collapsed
    if (window.innerWidth <= 1024) {
        profileSidebarCollapsed = false;
        toggleProfileSidebar();
    }
});

// Handle window resize
window.addEventListener('resize', function() {
    const overlay = document.getElementById('profile-overlay');
    if (overlay && window.innerWidth > 1024) {
        overlay.classList.remove('active');
    }
});
