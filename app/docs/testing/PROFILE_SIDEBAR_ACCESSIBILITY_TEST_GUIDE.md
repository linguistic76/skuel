# Profile Sidebar Accessibility Testing Guide

**Date:** 2026-02-01
**Feature:** Profile Hub Sidebar Mobile Enhancement
**Target:** WCAG 2.1 Level AA Compliance

## Quick Start

```bash
# 1. Start the development server
poetry run python main.py

# 2. Navigate to Profile Hub
# Open: http://localhost:8000/profile

# 3. Run automated tests (if available)
npm run lighthouse -- --only-categories=accessibility /profile
npm run axe -- /profile
```

## Test Environment Setup

### Required Tools

1. **Chrome DevTools** (built-in)
   - Device emulation
   - Touch target inspection
   - Console logging

2. **Screen Readers** (at least one)
   - **NVDA** (Windows): https://www.nvaccess.org/download/
   - **JAWS** (Windows): https://www.freedomscientific.com/products/software/jaws/
   - **VoiceOver** (macOS/iOS): Built-in (Cmd+F5 to toggle)

3. **Browser Extensions** (optional but recommended)
   - **axe DevTools**: https://www.deque.com/axe/devtools/
   - **WAVE**: https://wave.webaim.org/extension/

### Device Testing Setup

**Physical Devices (Recommended):**
- 1× iOS device (iPhone/iPad)
- 1× Android device (any modern phone)

**Emulation (Fallback):**
```javascript
// Chrome DevTools → Device Toolbar (Ctrl+Shift+M)
// Select device presets:
// - iPhone SE (320px width)
// - iPhone 12 Pro (390px width)
// - iPad Air (820px width)
```

## Test Procedures

### Test 1: Touch Target Compliance (P0)

**Requirement:** All interactive elements ≥44×44px (WCAG 2.5.5)

**Steps:**
1. Open Chrome DevTools (F12)
2. Navigate to Profile Hub: `/profile`
3. Toggle Device Toolbar (Ctrl+Shift+M)
4. Select "iPhone SE" (320px)
5. Inspect elements:

```javascript
// Console check:
document.querySelector('.sidebar-toggle').getBoundingClientRect()
// Expected: width ≥ 44, height ≥ 44

document.querySelector('.mobile-menu-button').getBoundingClientRect()
// Expected: width ≥ 44, height ≥ 44

document.querySelectorAll('.sidebar-nav li a').forEach(el => {
    const rect = el.getBoundingClientRect();
    console.log(`${el.textContent.trim()}: ${rect.height}px`);
});
// Expected: All ≥ 44px height
```

**Pass Criteria:**
- ✅ Toggle button: 44×44px
- ✅ Mobile menu button: ≥44×44px
- ✅ All navigation links: ≥44px vertical height

**Screenshot:** Capture DevTools with measurements visible

---

### Test 2: Focus Trapping (P0)

**Requirement:** Focus stays within drawer when open (WCAG 2.1.2)

**Steps:**
1. Navigate to `/profile` (mobile viewport)
2. Open drawer (click Menu button)
3. Press Tab repeatedly (10+ times)
4. Observe focus indicator
5. Press Shift+Tab repeatedly
6. Verify focus cycles within drawer

**Detailed Test:**
```
1. Click "Menu" button
2. Drawer opens, focus moves to first link (Profile heading)
3. Press Tab → Focus moves to "Overview"
4. Press Tab → Focus moves to "Tasks"
5. Continue tabbing through all links
6. After last link → Press Tab → Focus returns to first link
7. Press Shift+Tab → Focus moves to last link
8. Continue Shift+Tab → Focus cycles backward
```

**Pass Criteria:**
- ✅ Tab cycles forward through all focusable elements
- ✅ After last element, Tab returns to first element
- ✅ Shift+Tab cycles backward
- ✅ Focus never leaves drawer while open
- ✅ No focus on background content (overlay, main content)

**Failure Examples:**
- ❌ Tab reaches browser address bar (focus trap broken)
- ❌ Focus moves to content behind drawer
- ❌ Focus disappears (lost focus)

---

### Test 3: Keyboard Accessibility (P0)

**Requirement:** Escape key closes drawer, focus restoration (WCAG 2.1.1)

**Steps:**
1. Navigate to `/profile` (mobile viewport)
2. Click "Menu" button with mouse
3. Drawer opens
4. Press Escape key
5. Verify drawer closes
6. Verify focus returns to Menu button

**Detailed Test:**
```
1. Initial state: Drawer closed, focus on page
2. Click "Menu" button → Drawer opens
3. Press Escape → Drawer closes immediately
4. Focus returns to "Menu" button (visible outline)
5. Press Enter/Space on "Menu" button → Drawer reopens
```

**Pass Criteria:**
- ✅ Escape key closes drawer
- ✅ Focus returns to trigger button (Menu or Toggle)
- ✅ Enter/Space on Menu button opens drawer
- ✅ Works on mobile viewport (≤1024px)
- ✅ Does not interfere with desktop behavior (>1024px)

**Desktop Behavior:**
- Desktop toggle button: Escape should NOT close sidebar
- Only mobile drawer uses Escape key

---

### Test 4: ARIA Attributes (P0)

**Requirement:** Correct ARIA markup for screen readers (WCAG 4.1.2)

**Inspection:**
```javascript
// Console checks:
const sidebar = document.getElementById('profile-sidebar');

// Check role and modal attributes
console.log('role:', sidebar.getAttribute('role'));  // Expected: "dialog"
console.log('aria-modal:', sidebar.getAttribute('aria-modal'));  // Expected: "false" (closed) or "true" (open on mobile)
console.log('aria-labelledby:', sidebar.getAttribute('aria-labelledby'));  // Expected: "profile-sidebar-heading"

// Check toggle button
const toggleBtn = document.querySelector('.sidebar-toggle');
console.log('aria-expanded:', toggleBtn.getAttribute('aria-expanded'));  // Expected: "false" (closed) or "true" (open)
console.log('aria-controls:', toggleBtn.getAttribute('aria-controls'));  // Expected: "profile-sidebar-nav"

// Check mobile menu button
const menuBtn = document.querySelector('.mobile-menu-button');
console.log('aria-expanded:', menuBtn.getAttribute('aria-expanded'));  // Expected: "false" (closed) or "true" (open)
console.log('aria-label:', menuBtn.getAttribute('aria-label'));  // Expected: "Open profile navigation"
```

**Dynamic State Test:**
```
1. Initial: aria-expanded="false", aria-modal="false"
2. Open drawer → aria-expanded="true", aria-modal="true" (mobile)
3. Close drawer → aria-expanded="false", aria-modal="false"
```

**Pass Criteria:**
- ✅ `role="dialog"` on sidebar
- ✅ `aria-modal="true"` when drawer open on mobile
- ✅ `aria-labelledby` references correct heading ID
- ✅ `aria-expanded` updates dynamically on toggle
- ✅ `aria-controls` links buttons to sidebar
- ✅ `aria-label` present on Menu button

---

### Test 5: Screen Reader Announcements (P1)

**Requirement:** State changes announced to screen readers (WCAG 4.1.3)

**Tools:** NVDA, JAWS, or VoiceOver

#### NVDA (Windows):
```
1. Install NVDA: https://www.nvaccess.org/download/
2. Launch NVDA (Ctrl+Alt+N)
3. Open Profile Hub in browser
4. Set viewport to mobile (≤1024px)
5. Tab to "Menu" button
6. Press Enter
7. Listen for announcement: "Profile navigation opened"
8. Press Escape
9. Listen for announcement: "Profile navigation closed"
```

#### VoiceOver (macOS/iOS):
```
# macOS:
1. Enable VoiceOver: Cmd+F5
2. Navigate to /profile
3. Resize window to <1024px
4. Use VoiceOver navigation to "Menu" button
5. Activate button (VO+Space)
6. Listen for: "Profile navigation opened"
7. Press Escape
8. Listen for: "Profile navigation closed"

# iOS:
1. Enable VoiceOver: Settings → Accessibility → VoiceOver
2. Open Safari, navigate to /profile
3. Swipe to "Menu" button
4. Double-tap to activate
5. Listen for announcement
```

**Pass Criteria:**
- ✅ Opening drawer announces "Profile navigation opened"
- ✅ Closing drawer announces "Profile navigation closed"
- ✅ Announcement is polite (does not interrupt)
- ✅ Announcement clears after ~1 second
- ✅ Works with NVDA, JAWS, or VoiceOver

**Technical Verification:**
```javascript
// Check live region exists
const announcer = document.getElementById('sidebar-sr-announcements');
console.log('Live region:', announcer);
console.log('role:', announcer.getAttribute('role'));  // Expected: "status"
console.log('aria-live:', announcer.getAttribute('aria-live'));  // Expected: "polite"
console.log('aria-atomic:', announcer.getAttribute('aria-atomic'));  // Expected: "true"

// Check announcement
// After opening drawer, within 1 second:
console.log('Announcement:', announcer.textContent);  // Expected: "Profile navigation opened"
```

---

### Test 6: Landscape Optimization (P1)

**Requirement:** Drawer width optimized for landscape orientation

**Steps:**
1. Use physical device or Chrome DevTools
2. Set viewport to landscape: 736×414 (iPhone landscape)
3. Open drawer
4. Measure drawer width

**Expected Behavior:**

| Orientation | Width | Max Width |
|-------------|-------|-----------|
| Portrait (≤1024px) | 85% | 320px |
| Landscape (≤1024px) | 60% | 280px |

**Console Measurement:**
```javascript
// Open drawer in landscape
const sidebar = document.getElementById('profile-sidebar');
const rect = sidebar.getBoundingClientRect();
const viewportWidth = window.innerWidth;

console.log(`Viewport: ${viewportWidth}px`);
console.log(`Drawer width: ${rect.width}px`);
console.log(`Percentage: ${(rect.width / viewportWidth * 100).toFixed(1)}%`);

// Expected (landscape ≤1024px):
// - Width: ~60% of viewport or 280px (whichever is smaller)
// - Content area visible (40% of viewport)
```

**Pass Criteria:**
- ✅ Landscape: Drawer is 60% width (max 280px)
- ✅ Portrait: Drawer is 85% width (max 320px)
- ✅ Content area visible in landscape (not obscured)
- ✅ Smooth transition when rotating device

---

### Test 7: Badge Responsiveness (P2)

**Requirement:** Badges adapt gracefully on small screens

**Test Matrix:**

| Screen Width | Insight Badge | Count Badge | Status Dot | Layout |
|--------------|---------------|-------------|------------|--------|
| ≥376px | Visible | Visible | Visible | Horizontal |
| 375px | Visible | Visible | Hidden | Vertical |
| 320px | Hidden | Visible | Hidden | Vertical |

**Steps:**
```
1. Set viewport to 375px width
2. Open drawer
3. Inspect "Tasks" link (has badges)
4. Verify:
   - Count badge (e.g., "3/10"): Visible
   - Insight badge (bell icon + count): Visible
   - Status dot: Hidden
   - Badges stacked vertically

5. Set viewport to 320px width
6. Verify:
   - Count badge: Visible
   - Insight badge: Hidden
   - Status dot: Hidden
```

**CSS Verification:**
```javascript
// At 375px:
const link = document.querySelector('.sidebar-nav li a');
const badgeContainer = link.querySelector('div:last-child');
const statusDot = link.querySelector('.w-2.h-2');

console.log('Badge container flex-direction:', window.getComputedStyle(badgeContainer).flexDirection);  // Expected: "column"
console.log('Status dot display:', window.getComputedStyle(statusDot).display);  // Expected: "none"

// At 320px:
const insightBadge = link.querySelector('.badge-warning');
console.log('Insight badge display:', window.getComputedStyle(insightBadge).display);  // Expected: "none"
```

**Pass Criteria:**
- ✅ 375px: Vertical badge layout, status dot hidden
- ✅ 320px: Insight badge hidden, count badge visible
- ✅ No text overflow or badge overlap
- ✅ Long domain names truncate cleanly

---

## Regression Testing

### Desktop Behavior (Must Not Break)

**Requirement:** Desktop sidebar behavior unchanged

**Steps:**
1. Set viewport to >1024px (desktop)
2. Verify:
   - Sidebar is visible (not drawer)
   - Toggle button collapses sidebar (not modal)
   - No overlay appears
   - No focus trap (can Tab to browser chrome)
   - Escape key does NOT close sidebar
   - `aria-modal="false"` always

**Pass Criteria:**
- ✅ Desktop sidebar works as before
- ✅ Toggle button collapses/expands sidebar
- ✅ No mobile drawer behavior on desktop
- ✅ No ARIA changes that break existing functionality

---

## Common Issues & Troubleshooting

### Issue: Focus trap not working
**Symptoms:** Tab key moves focus outside drawer

**Check:**
1. Console errors? (Check browser console)
2. Event listeners registered?
```javascript
// After opening drawer:
getEventListeners(document).keydown
// Should show trapFocusInSidebar and handleSidebarKeydown
```
3. Viewport width check:
```javascript
console.log(window.innerWidth);  // Must be ≤1024
```

**Fix:** Verify mobile viewport, check console for JS errors

---

### Issue: Escape key not closing drawer
**Symptoms:** Escape key does nothing

**Check:**
1. Viewport width:
```javascript
console.log(window.innerWidth);  // Must be ≤1024
```
2. Drawer state:
```javascript
console.log(profileSidebarCollapsed);  // Must be false (drawer open)
```
3. Event listener:
```javascript
getEventListeners(document).keydown
// Should include handleSidebarKeydown
```

**Fix:** Only works on mobile (≤1024px), verify viewport and drawer state

---

### Issue: Screen reader not announcing
**Symptoms:** No announcement when opening/closing drawer

**Check:**
1. Live region exists:
```javascript
document.getElementById('sidebar-sr-announcements')
// Should return element
```
2. Announcement text:
```javascript
// Immediately after opening drawer:
document.getElementById('sidebar-sr-announcements').textContent
// Should be "Profile navigation opened"
```
3. Screen reader active?
   - NVDA: Check system tray icon
   - VoiceOver: Check for speech output

**Fix:** Verify live region element, check screen reader settings

---

### Issue: Touch targets too small
**Symptoms:** Difficult to tap on mobile device

**Check:**
1. Actual size:
```javascript
document.querySelector('.sidebar-toggle').getBoundingClientRect()
// width and height should be ≥44
```
2. CSS applied?
```javascript
window.getComputedStyle(document.querySelector('.sidebar-toggle')).width
// Should be "44px"
```

**Fix:** Clear browser cache, verify CSS loaded

---

## Automated Testing Scripts

### Lighthouse Accessibility Audit

```bash
# Requires: npm install -g lighthouse

# Run audit
lighthouse http://localhost:8000/profile \
  --only-categories=accessibility \
  --output=html \
  --output-path=./lighthouse-profile-sidebar.html

# Target score: 100
# Key checks:
# - Touch targets ≥48×48px (Lighthouse uses 48px, we use 44px WCAG minimum)
# - ARIA attributes present and valid
# - Focus order logical
# - Contrast ratios ≥4.5:1
```

### axe-core Automated Checks

```javascript
// Browser console (with axe extension installed):
axe.run(document.querySelector('.profile-sidebar')).then(results => {
    console.log('Violations:', results.violations.length);
    results.violations.forEach(v => {
        console.log(`[${v.impact}] ${v.description}`);
        console.log('  Fix:', v.help);
    });
});

// Expected: 0 violations
```

### Custom Test Script

```javascript
// Run in browser console at /profile
function testProfileSidebarAccessibility() {
    const tests = [];

    // Test 1: Touch targets
    const toggleBtn = document.querySelector('.sidebar-toggle');
    const toggleRect = toggleBtn.getBoundingClientRect();
    tests.push({
        name: 'Toggle button size',
        pass: toggleRect.width >= 44 && toggleRect.height >= 44,
        actual: `${toggleRect.width}×${toggleRect.height}`,
        expected: '≥44×44'
    });

    // Test 2: ARIA attributes
    const sidebar = document.getElementById('profile-sidebar');
    tests.push({
        name: 'Sidebar role',
        pass: sidebar.getAttribute('role') === 'dialog',
        actual: sidebar.getAttribute('role'),
        expected: 'dialog'
    });

    tests.push({
        name: 'aria-labelledby',
        pass: sidebar.getAttribute('aria-labelledby') === 'profile-sidebar-heading',
        actual: sidebar.getAttribute('aria-labelledby'),
        expected: 'profile-sidebar-heading'
    });

    // Test 3: Live region
    const announcer = document.getElementById('sidebar-sr-announcements');
    tests.push({
        name: 'Live region exists',
        pass: announcer !== null,
        actual: announcer ? 'found' : 'missing',
        expected: 'found'
    });

    tests.push({
        name: 'Live region role',
        pass: announcer && announcer.getAttribute('role') === 'status',
        actual: announcer?.getAttribute('role'),
        expected: 'status'
    });

    // Report results
    console.table(tests);
    const failed = tests.filter(t => !t.pass);
    console.log(`\n${tests.length - failed.length}/${tests.length} tests passed`);
    if (failed.length > 0) {
        console.error('Failed tests:', failed.map(t => t.name).join(', '));
    }
}

// Run test
testProfileSidebarAccessibility();
```

---

## Test Report Template

```markdown
# Profile Sidebar Accessibility Test Report

**Date:** YYYY-MM-DD
**Tester:** [Name]
**Environment:** [Browser/Device]
**Build:** [Git commit hash]

## Test Results Summary

| Test | Status | Notes |
|------|--------|-------|
| Touch Target Compliance | ⬜ PASS / ❌ FAIL | |
| Focus Trapping | ⬜ PASS / ❌ FAIL | |
| Keyboard Accessibility | ⬜ PASS / ❌ FAIL | |
| ARIA Attributes | ⬜ PASS / ❌ FAIL | |
| Screen Reader | ⬜ PASS / ❌ FAIL | |
| Landscape Optimization | ⬜ PASS / ❌ FAIL | |
| Badge Responsiveness | ⬜ PASS / ❌ FAIL | |
| Desktop Regression | ⬜ PASS / ❌ FAIL | |

## Issues Found

1. [Issue description]
   - Severity: Critical / High / Medium / Low
   - Steps to reproduce:
   - Expected behavior:
   - Actual behavior:
   - Screenshot: [attach]

## Recommendations

- [Any suggestions for improvement]

## Sign-off

- [ ] All critical (P0) tests passed
- [ ] All important (P1) tests passed
- [ ] No regressions detected
- [ ] Ready for production deployment

**Tester Signature:** ___________________
**Date:** ___________________
```

---

## Resources

**WCAG 2.1 Quick Reference:**
https://www.w3.org/WAI/WCAG21/quickref/

**ARIA Authoring Practices:**
https://www.w3.org/WAI/ARIA/apg/patterns/dialog-modal/

**Screen Reader Testing:**
- NVDA User Guide: https://www.nvaccess.org/files/nvda/documentation/userGuide.html
- VoiceOver Guide (macOS): https://support.apple.com/guide/voiceover/welcome/mac
- VoiceOver Guide (iOS): https://support.apple.com/guide/iphone/turn-on-and-practice-voiceover-iph3e2e415f/ios

**Mobile Testing:**
- Chrome DevTools Device Mode: https://developer.chrome.com/docs/devtools/device-mode/
- Remote Debugging (Android): https://developer.chrome.com/docs/devtools/remote-debugging/
- Web Inspector (iOS): https://webkit.org/web-inspector/enabling-web-inspector/

---

**Last Updated:** 2026-02-01
**Maintainer:** SKUEL Engineering Team
