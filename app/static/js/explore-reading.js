/**
 * Explore reading surface — Alpine factory.
 *
 * Registers Alpine.data('exploreReading', factory); pair with
 * x-data="exploreReading(window.SEED)" on the page root
 * (ui/explore/reading_plan.py). Seed comes from window.SEED emitted
 * by the server in the same document.
 *
 * Owns: greeting text, "why am I ready?" disclosure, save toggle,
 * keyboard shortcuts. All other content is server-rendered.
 */
(function () {
  'use strict';

  function exploreReadingFactory(seed) {
    return {
      seed: seed || {
        reader_name: '',
        date_label: '',
        featured_uid: '',
        why: [],
        last_completed_title: '',
      },
      whyOpen: false,
      saved: new Set(),

      greeting: function () {
        var h = new Date().getHours();
        return h < 12 ? 'Good morning' : h < 18 ? 'Good afternoon' : 'Good evening';
      },

      isSaved: function (uid) { return this.saved.has(uid); },
      toggleSave: function (uid) {
        if (this.saved.has(uid)) { this.saved.delete(uid); }
        else { this.saved.add(uid); }
        this.saved = new Set(this.saved);
      },

      onKey: function (e) {
        var tag = (e.target.tagName || '').toLowerCase();
        if (tag === 'input' || tag === 'textarea') { return; }
        if (e.key === 'w') {
          e.preventDefault();
          this.whyOpen = !this.whyOpen;
        } else if (e.key === 's') {
          e.preventDefault();
          this.toggleSave(this.seed.featured_uid);
        } else if (e.key === 'r') {
          e.preventDefault();
          window.location.href = '/explore/read/' + this.seed.featured_uid;
        } else if (e.key === '/') {
          e.preventDefault();
          window.location.href = '/explore/library';
        }
      },
    };
  }

  document.addEventListener('alpine:init', function () {
    window.Alpine.data('exploreReading', exploreReadingFactory);
  });

})();
