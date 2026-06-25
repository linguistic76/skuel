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
 */
(function () {
  'use strict';

  function pathstepFactory(seed) {
    var s = seed || {};
    return {
      uid: s.uid || '',
      status: s.progress_state || 'not_started',
      bookmarked: s.is_bookmarked || false,
      blocking: s.blocking || [],
      prevStep: s.prev_step || null,
      nextStep: s.next_step || null,
      practiceOpen: true,
      depsOpen: false,

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
        var newState = this.status === 'learning' ? 'read' : 'learning';
        htmx.ajax('POST', '/explore/ps/' + this.uid + '/progress', {
          values: { state: newState },
          swap: 'none',
        });
        this.status = newState;
      },

      reviewAgain: function () {
        htmx.ajax('POST', '/explore/ps/' + this.uid + '/progress', {
          values: { state: 'learning', review: 'true' },
          swap: 'none',
        });
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
