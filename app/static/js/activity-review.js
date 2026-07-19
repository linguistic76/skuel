/**
 * Activity review — keep the feedback form's hidden subject/period fields in
 * sync with the snapshot form after a snapshot swap.
 *
 * Paired with ui/activity_review/forms.py.
 */
(function () {
    'use strict';

    if (window.__skuelActivityReviewWired) return;
    window.__skuelActivityReviewWired = true;

    document.body.addEventListener('htmx:afterRequest', function (evt) {
        if (evt.detail.elt.getAttribute('hx-target') === '#snapshot-display') {
            var subjectEl = document.getElementById('snapshot-subject-uid');
            var periodEl = document.getElementById('snapshot-time-period');
            var fbSubjectEl = document.getElementById('feedback-subject-uid');
            var fbPeriodEl = document.getElementById('feedback-time-period');
            if (subjectEl && fbSubjectEl) fbSubjectEl.value = subjectEl.value;
            if (periodEl && fbPeriodEl) fbPeriodEl.value = periodEl.value;
        }
    });
})();
