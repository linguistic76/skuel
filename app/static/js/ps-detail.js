/**
 * PathStep detail — Alpine factory.
 *
 * Registered as Alpine.data('pathstep', factory). Paired with
 * x-data="pathstep(window.PS_SEED)" on the content root
 * (ui/explore/ps_detail.py). Seed is emitted by the server in the
 * HTMX fragment.
 *
 * Owns: progress state (not_started → learning → read), bookmark
 * toggle, practice + deps accordion open/close.
 *
 * All mutations POST via htmx.ajax() — skuel.js attaches X-CSRF-Token
 * to every htmx request automatically, so no manual token wiring needed.
 *
 * Progress updates are optimistic: the UI flips immediately, and if the
 * server rejects the write (enrollment cap, write error) the htmx
 * lifecycle listener in init() rolls the state back and surfaces the
 * server's X-Toast-Message as an error toast (G7).
 */
(function () {
  'use strict';

  function pathstepFactory(seed) {
    var s = seed || {};
    return {
      uid: s.uid || '',
      status: s.progress_state || 'not_started',
      bookmarked: s.is_bookmarked || false,
      hasTaskTemplates: s.has_task_templates || false,
      blocking: s.blocking || [],
      prevStep: s.prev_step || null,
      nextStep: s.next_step || null,
      practiceOpen: true,
      depsOpen: false,
      _syncedStatus: null,

      init: function () {
        var self = this;
        this._syncedStatus = this.status;
        // postProgress() passes source: this.$el, so the htmx lifecycle
        // events for progress POSTs fire on this element (and the listener
        // is GC'd with it on page swaps). On failure, roll the optimistic
        // state back to the last server-confirmed value and show the toast.
        this.$el.addEventListener('htmx:afterRequest', function (evt) {
          var cfg = evt.detail && evt.detail.requestConfig;
          if (!cfg || String(cfg.path).indexOf('/progress') === -1) return;
          if (evt.detail.successful) {
            self._syncedStatus = self.status;
            return;
          }
          self.status = self._syncedStatus;
          var xhr = evt.detail.xhr;
          var msg =
            (xhr && xhr.getResponseHeader('X-Toast-Message')) ||
            'Could not update progress — please try again';
          window.dispatchEvent(
            new CustomEvent('toast', { detail: { message: msg, type: 'error' } })
          );
        });
      },

      postProgress: function (values) {
        htmx.ajax('POST', '/explore/ps/' + this.uid + '/progress', {
          source: this.$el,
          values: values,
          swap: 'none',
        });
      },

      get progressPct() {
        return this.status === 'read' ? 100 : this.status === 'learning' ? 55 : 0;
      },
      get allMet() {
        return this.blocking.every(function (d) { return d.status === 'met'; });
      },
      get blockedCount() {
        return this.blocking.filter(function (d) { return d.status !== 'met'; }).length;
      },

      advance: function () {
        // When the PS has TaskTemplates and learning hasn't started, engage the
        // PS to spawn tasks rather than just toggling read-progress.
        if (this.hasTaskTemplates && this.status === 'not_started') {
          this.status = 'learning';
          htmx.ajax('POST', '/api/ps/' + this.uid + '/engage', { swap: 'none' });
          // Mark as in-progress so mastery state persists across page reloads.
          this.postProgress({ state: 'learning' });
          // Reload the tasks fragment after the server has had time to spawn tasks.
          var tasksEl = document.getElementById('ps-tasks-fragment');
          if (tasksEl) {
            setTimeout(function () { htmx.trigger(tasksEl, 'ps-engaged'); }, 700);
          }
          return;
        }
        var newState = this.status === 'learning' ? 'read' : 'learning';
        this.postProgress({ state: newState });
        this.status = newState;
      },

      reviewAgain: function () {
        this.postProgress({ state: 'learning', review: 'true' });
        this.status = 'learning';
      },

      toggleBookmark: function () {
        this.bookmarked = !this.bookmarked;
        htmx.ajax('POST', '/explore/ps/' + this.uid + '/bookmark', {
          values: { on: this.bookmarked.toString() },
          swap: 'none',
        });
      },
    };
  }

  document.addEventListener('alpine:init', function () {
    window.Alpine.data('pathstep', pathstepFactory);
  });
})();
