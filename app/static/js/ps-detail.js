/**
 * PathStep detail — Alpine factory.
 *
 * Registered as Alpine.data('pathstep', factory). Paired with
 * x-data="pathstep({...})" on the content root (ui/explore/ps_detail.py).
 * The seed is inlined in the x-data expression — never a window global set
 * by a sibling <script>: htmx defers inline-script evaluation to the settle
 * phase, but Alpine initializes the swapped tree first, so the component
 * would read undefined (uid='' broke Start learning, 2026-07-05).
 *
 * Owns: progress state (not_started → learning → read; mastered is the
 * server's, derived from the step's Kus, and is the only state shown as
 * Completed), bookmark toggle, deps accordion open/close.
 *
 * All mutations POST via htmx.ajax() — skuel.js attaches X-CSRF-Token
 * to every htmx request automatically, so no manual token wiring needed.
 *
 * Progress updates are optimistic: the UI flips immediately, and if the
 * server rejects the write (prerequisites, enrollment cap, write error) the
 * htmx lifecycle listener in init() rolls the state back and surfaces the
 * server's X-Toast-Message as an error toast.
 *
 * Start learning is disabled while a prerequisite in the step's chain is not
 * mastered (`blocking`, the rows the server's gate admits by). On a step with
 * task templates the start is posted first and the engagement only once it
 * lands, so a refused start spawns nothing; an engagement that then fails
 * leaves the step Learning — the start did land — and says so in a toast.
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
      depsOpen: false,
      _syncedStatus: null,
      _engageAfterStart: false,

      init: function () {
        var self = this;
        this._syncedStatus = this.status;
        // postProgress() passes source: this.$el, so the htmx lifecycle
        // events for progress POSTs fire on this element (and the listener
        // is GC'd with it on page swaps). On failure, roll the optimistic
        // state back to the last server-confirmed value and show the toast.
        this.$el.addEventListener('htmx:afterRequest', function (evt) {
          var cfg = evt.detail && evt.detail.requestConfig;
          if (!cfg) return;
          var path = String(cfg.path);
          if (path.indexOf('/engage') !== -1) {
            self._engagementLanded(evt);
            return;
          }
          if (path.indexOf('/progress') === -1) return;
          if (evt.detail.successful) {
            self._syncedStatus = self.status;
            if (self._engageAfterStart) {
              self._engageAfterStart = false;
              htmx.ajax('POST', '/api/ps/' + self.uid + '/engage', {
                source: self.$el,
                swap: 'none',
              });
            }
            return;
          }
          self._engageAfterStart = false;
          self.status = self._syncedStatus;
          // The global toastManager (htmx:afterRequest on body) surfaces
          // X-Toast headers for every response — only dispatch the local
          // fallback when the failure carried no header (network error),
          // so the user never sees a double toast.
          var xhr = evt.detail.xhr;
          if (!xhr || !xhr.getResponseHeader('X-Toast-Message')) {
            window.dispatchEvent(
              new CustomEvent('toast', {
                detail: { message: 'Could not update progress — please try again', type: 'error' }
              })
            );
          }
        });
      },

      _engagementLanded: function (evt) {
        if (evt.detail.successful) {
          // Reload the tasks fragment now that the server has spawned them.
          var tasksEl = document.getElementById('ps-tasks-fragment');
          if (tasksEl) htmx.trigger(tasksEl, 'ps-engaged');
          return;
        }
        // The start landed, so the step stays Learning; only the activities failed.
        var xhr = evt.detail.xhr;
        if (!xhr || !xhr.getResponseHeader('X-Toast-Message')) {
          window.dispatchEvent(
            new CustomEvent('toast', {
              detail: {
                message: "Could not set up this step's activities — please try again",
                type: 'error',
              },
            })
          );
        }
      },

      postProgress: function (values) {
        htmx.ajax('POST', '/explore/ps/' + this.uid + '/progress', {
          source: this.$el,
          values: values,
          swap: 'none',
        });
      },

      get progressPct() {
        if (this.status === 'mastered') return 100;
        return this.status === 'read' ? 80 : this.status === 'learning' ? 55 : 0;
      },
      get allCompleted() {
        return this.blocking.every(function (d) { return d.status === 'completed'; });
      },
      get blockedCount() {
        return this.blocking.filter(function (d) { return d.status !== 'completed'; }).length;
      },
      // A step not yet started waits on every prerequisite in its chain.
      get startBlocked() {
        return this.status === 'not_started' && !this.allCompleted;
      },
      get primaryLabel() {
        if (this.startBlocked) {
          var n = this.blockedCount;
          return n + ' prerequisite' + (n === 1 ? '' : 's') + ' to clear';
        }
        return this.status === 'learning' ? 'Mark as read' : 'Start learning';
      },

      advance: function () {
        if (this.startBlocked) return;
        // A step with task templates is engaged once its start lands, so the
        // learner's activities are spawned only for a step they were admitted to.
        if (this.hasTaskTemplates && this.status === 'not_started') {
          this._engageAfterStart = true;
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
