/**
 * Journal upload form — HTMX lifecycle handlers.
 *
 * Paired with ui/journals/forms.py (render_upload_form / upload_form_script):
 * client-side preflight (no file selected), submit-button busy state, form
 * reset + the journals:upload-complete event on completion, and inline error
 * fallbacks for HTTP/network failures.
 */
(function () {
    'use strict';

    // The page shell can be re-swapped by HTMX (which re-executes scripts) —
    // the listeners live on document.body, so wire them exactly once.
    if (window.__skuelJournalsUploadWired) return;
    window.__skuelJournalsUploadWired = true;

    function setStatus(html) {
        var status = document.getElementById('upload-status');
        if (status) status.innerHTML = html;
    }

    document.body.addEventListener('htmx:beforeRequest', function (evt) {
        var form = evt.detail.elt;
        if (form.id !== 'upload-form') return;
        var fileInput = document.getElementById('file-input');
        var folderInput = document.getElementById('folder-input');
        var hasFiles = (fileInput && fileInput.files.length > 0) ||
                       (folderInput && folderInput.files.length > 0);
        if (!hasFiles) {
            evt.preventDefault();
            setStatus('<p class="text-destructive text-sm text-center mt-2">Please select a file first.</p>');
            return;
        }
        var count = (fileInput ? fileInput.files.length : 0) +
                    (folderInput ? folderInput.files.length : 0);
        var btn = form.querySelector('button[type="submit"]');
        if (btn) {
            btn.disabled = true;
            var label = btn.querySelector('.btn-label');
            if (label) label.textContent = count > 1
                ? 'Processing ' + count + ' files...'
                : 'Processing...';
        }
    });

    document.body.addEventListener('htmx:afterRequest', function (evt) {
        var form = evt.detail.elt;
        if (form.id !== 'upload-form') return;
        form.reset();
        var btn = form.querySelector('button[type="submit"]');
        if (btn) {
            btn.disabled = false;
            var label = btn.querySelector('.btn-label');
            if (label) label.textContent = 'Process';
        }
        window.dispatchEvent(new CustomEvent('journals:upload-complete'));
    });

    document.body.addEventListener('htmx:responseError', function (evt) {
        var form = evt.detail.elt;
        if (form.id !== 'upload-form') return;
        console.error('[Journals] Request failed:', evt.detail.xhr.status);
        setStatus('<p class="text-destructive text-sm text-center mt-2">Upload failed (' +
            evt.detail.xhr.status + '). Please try again.</p>');
    });

    document.body.addEventListener('htmx:sendError', function (evt) {
        var form = evt.detail.elt;
        if (form.id !== 'upload-form') return;
        console.error('[Journals] Network error:', evt.detail.error);
        setStatus('<p class="text-destructive text-sm text-center mt-2">Network error. Check your connection.</p>');
    });
})();
