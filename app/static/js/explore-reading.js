/**
 * Explore reading surface — Alpine factory.
 *
 * Registers Alpine.data('exploreReading', factory); pair with
 * x-data="exploreReading({...})" on the page root
 * (ui/explore/reading_plan.py). The seed is inlined in the x-data
 * expression — never a window global set by a sibling <script>: htmx
 * defers inline-script evaluation to the settle phase, but Alpine
 * initializes the swapped tree first.
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
        saved_uids: [],
      },
      whyOpen: false,
      saved: new Set((seed && seed.saved_uids) || []),

      greeting: function () {
        var h = new Date().getHours();
        return h < 12 ? 'Good morning' : h < 18 ? 'Good afternoon' : 'Good evening';
      },

      isSaved: function (uid) { return this.saved.has(uid); },
      toggleSave: function (uid) {
        var saving = !this.saved.has(uid);
        if (saving) { this.saved.add(uid); } else { this.saved.delete(uid); }
        this.saved = new Set(this.saved);
        this._persistSave(uid, saving);
      },

      // Persist through the pins API (same store as the library PinButton);
      // revert the optimistic toggle if the server rejects it.
      _persistSave: function (uid, saving) {
        var self = this;
        var csrf = (window.SKUEL && window.SKUEL.csrf) ? window.SKUEL.csrf() : '';
        var req = saving
          ? fetch('/api/user/pins', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrf },
              body: JSON.stringify({ entity_uid: uid }),
            })
          : fetch('/api/user/pins/' + encodeURIComponent(uid), {
              method: 'DELETE',
              headers: { 'X-CSRF-Token': csrf },
            });
        req.then(function (resp) {
          if (!resp.ok) { throw new Error('HTTP ' + resp.status); }
        }).catch(function () {
          if (saving) { self.saved.delete(uid); } else { self.saved.add(uid); }
          self.saved = new Set(self.saved);
        });
      },

      onKey: function (e) {
        var tag = (e.target.tagName || '').toLowerCase();
        if (tag === 'input' || tag === 'textarea') { return; }
        if (e.key === 'w') {
          e.preventDefault();
          this.whyOpen = !this.whyOpen;
        } else if (e.key === 's') {
          e.preventDefault();
          // No featured KU (empty library, no in-progress step) — hero is
          // collapsed, so the save/read shortcuts have no target.
          if (this.seed.featured_uid) { this.toggleSave(this.seed.featured_uid); }
        } else if (e.key === 'r') {
          e.preventDefault();
          if (this.seed.featured_uid) {
            window.location.href = '/explore/read/' + this.seed.featured_uid;
          }
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
