/* Profile Sidebar Toggle - Inspired by /nous pattern
 * Updated: 2026-02-02 - Task 9: Integrated FocusTrap utility for WCAG 2.1 Level AA compliance
 */

let profileSidebarCollapsed = false;
let focusTrap = null;  // FocusTrap instance for mobile drawer

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

        // Deactivate focus trap on mobile
        if (focusTrap) {
            focusTrap.deactivate();  // Automatically restores focus
        }

        // Update ARIA states
        const toggleButton = document.querySelector('.sidebar-toggle');
        const mobileMenuButton = document.querySelector('.mobile-menu-button');
        if (toggleButton) toggleButton.setAttribute('aria-expanded', 'false');
        if (mobileMenuButton) mobileMenuButton.setAttribute('aria-expanded', 'false');
        if (window.innerWidth <= 1024) {
            sidebar.setAttribute('aria-modal', 'false');
        }

        // Announce state change
        announceDrawerState(false);
    } else {
        // Opening drawer
        sidebar.classList.remove('collapsed');
        content.classList.remove('expanded');

        // Show overlay on mobile
        if (window.innerWidth <= 1024) {
            overlay.classList.add('active');

            // Initialize and activate focus trap
            if (!focusTrap) {
                focusTrap = new FocusTrap(sidebar, {
                    onEscape: toggleProfileSidebar,
                    initialFocus: 'button, [href]',  // Focus first interactive element
                    restoreFocus: true,
                });
            }
            focusTrap.activate();

            // Announce state change
            announceDrawerState(true);
        }

        // Update ARIA states
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
