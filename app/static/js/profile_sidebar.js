/* Profile Sidebar Toggle - Inspired by /nous pattern */

let profileSidebarCollapsed = false;

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
        sidebar.classList.add('collapsed');
        content.classList.add('expanded');
        overlay.classList.remove('active');
    } else {
        sidebar.classList.remove('collapsed');
        content.classList.remove('expanded');

        // Show overlay on mobile
        if (window.innerWidth <= 1024) {
            overlay.classList.add('active');
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
