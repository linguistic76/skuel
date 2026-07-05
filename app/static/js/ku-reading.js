/**
 * Ku reader — Alpine factory.
 *
 * Registers Alpine.data('kuReading', factory); paired with
 * x-data="kuReading({...})" on the content root (ui/explore/ku_detail.py).
 * The seed is inlined in the x-data expression — never a window global set
 * by a sibling <script>: htmx defers inline-script evaluation to the settle
 * phase, but Alpine initializes the swapped tree first.
 *
 * Owns: status toggle (studying/understood), mastery level selection
 * for the perception-gap form, keyboard shortcuts (u / Escape).
 * Pin/unpin is handled by PinButton (self-contained HTMX).
 * All other content is server-rendered.
 */
(function () {
  'use strict';

  function kuReadingFactory(seed) {
    var s = seed || {};
    return {
      seed: s,
      status: s.status || 'none',
      mastery: 'familiar',
      note: '',
      open: { blocking: false, alt: false },

      setStatus: function (v) {
        this.status = (this.status === v) ? 'none' : v;
      },

      onKey: function (e) {
        var tag = (e.target.tagName || '').toLowerCase();
        if (tag === 'input' || tag === 'textarea' || tag === 'select') { return; }
        if (e.key === 'u') { e.preventDefault(); this.setStatus('understood'); }
        if (e.key === 'Escape') { window.location.href = '/explore'; }
      },
    };
  }

  document.addEventListener('alpine:init', function () {
    window.Alpine.data('kuReading', kuReadingFactory);
  });
})();
