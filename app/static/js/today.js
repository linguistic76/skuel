/**
 * Today surface — Alpine factory.
 *
 * Registers ``Alpine.data('today', factory)``; pair with ``x-data="today"``
 * on the page root (``ui/today/page.py``). Seed comes from
 * ``window.SEED`` emitted by the server in the same document.
 *
 * Row rendering is structural: ``ui/today/page.py::_task_row`` emits the
 * markup, Alpine's ``x-text`` / ``:class`` handle escaping. The factory
 * here owns behavior only (drag, keyboard, optimistic state).
 *
 * Icons: we use <uk-icon icon="..."> (FrankenUI's Lit custom element,
 * Lucide-backed) so no client-side icon-replacer pass is needed — the
 * element auto-upgrades on insertion.
 */
(function () {
  'use strict';

  function todayFactory() {
    return {
      seed: window.SEED || {
        today_iso: '', date_label: '', heading: 'Today', is_today: true, now_hhmm: '00:00',
        stats: {nodes: 0, committed_min: 0, done: 0},
        triage: [], lifepaths: [], principles: [], goals: [], tasks: [], rituals: [], kinds: {},
      },
      // ---- (source, uid) card keying ----------------------------------------
      // A task can hold BOTH a ribbon card (scheduled/due == viewed day) and a
      // triage card (overdue). ALL per-card interaction state — optimistic
      // hide, selection, focus order, the drawer — is keyed by 'source:uid'
      // so acting on one card never touches the other (C7,
      // docs/roadmap/calendar-act-from-arc.md). Completion stays uid-keyed
      // deliberately: completing is a task-level fact and hides both cards.
      selectedKey: null,     // 'ribbon:<uid>' | 'triage:<uid>'
      openTaskKey: null,
      flash: null,
      flashTimer: null,
      deferred: {},          // cardKey -> '1d' | '1w' (optimistic hide, per card)
      completed: new Set(),  // uids
      _lastAction: null,     // for undo (complete only — defer has no truthful undo)

      cardKey(source, id) { return source + ':' + id; },
      keySource(key) { return key ? key.slice(0, key.indexOf(':')) : null; },
      keyId(key) { return key ? key.slice(key.indexOf(':') + 1) : null; },
      taskBy(source, id) {
        const list = source === 'triage' ? this.seed.triage : this.seed.tasks;
        return list.find(x => x.id === id) || null;
      },

      // ---- Derived ---------------------------------------------------------
      get fTasks()  { return this.seed.tasks.filter(t =>
        !this.deferred[this.cardKey('ribbon', t.id)] && !this.completed.has(t.id)); },
      get fTriage() { return this.seed.triage.filter(t =>
        !this.deferred[this.cardKey('triage', t.id)] && !this.completed.has(t.id)); },
      get allEmpty() { return this.fTasks.length === 0 && this.fTriage.length === 0; },

      get committedMin() { return this.fTasks.reduce((a, t) => a + (t.est_min || 0), 0); },
      get fmtCommitted() {
        const m = this.committedMin;
        return `${Math.floor(m/60)}h ${m%60}m`;
      },
      get statList() {
        return [
          { value: this.fTasks.length + this.fTriage.length, label: 'nodes' },
          { value: this.fmtCommitted,                        label: 'committed' },
          { value: this.completed.size,                      label: 'done',
            accent: 'text-priority-low' },
        ];
      },
      get nowPct() {
        const [h, m] = this.seed.now_hhmm.split(':').map(Number);
        const frac = h + m/60;
        return Math.max(0, Math.min(100, ((frac - 6) / 16) * 100));
      },

      principlesFor(lpId) {
        return this.seed.principles.filter(p => p.lifepath_id === lpId);
      },
      tasksFor(lpId) {
        return this.fTasks.filter(t => t.lifepath_id === lpId);
      },
      goalFor(t)      { return this.seed.goals.find(g => g.id === t.goal_id) || null; },
      principleFor(t) {
        const g = this.goalFor(t);
        if (g) return this.seed.principles.find(p => p.id === g.principle_id) || null;
        // fallback for rituals/journals linked directly to a principle
        return this.seed.principles.find(p => p.id === t.principle_id) || null;
      },
      lifepathFor(t)  { return this.seed.lifepaths.find(lp => lp.id === t.lifepath_id) || null; },
      strengthClass(s) {
        return {
          'core':       'bg-strength-core/10       text-strength-core',
          'strong':     'bg-strength-strong/10     text-strength-strong',
          'developing': 'bg-strength-developing/10 text-strength-developing',
        }[s] || 'bg-muted text-muted-foreground';
      },

      // Icon helpers — return pre-rendered inline <svg> markup (server-built in
      // ui/today/orchestrator.py) for x-html bindings. The SVG fills its wrapper
      // (w-full h-full), so the call-site element controls the display size. No
      // lucide.createIcons() / MutationObserver involved.
      kindIconHtml(kind) {
        return (this.seed.kinds[kind] || this.seed.kinds.submission || {}).icon_svg || '';
      },
      ritualIconHtml(hhmm) {
        return this.ritualPast(hhmm) ? this.seed.ritual_icons.past : this.seed.ritual_icons.upcoming;
      },
      openTaskIconHtml() {
        return (this.seed.kinds[this.openTask?.kind] || this.seed.kinds.submission || {}).icon_svg || '';
      },

      // Day-spine helpers
      ritualPct(hhmm) {
        const [h, m] = hhmm.split(':').map(Number);
        const frac = h + m/60;
        return Math.max(0, Math.min(1, (frac - 6) / 16));
      },
      // "Past" (dimmed + checked) only applies to the live day — while browsing
      // another date there is no "now" to be before, so rituals stay upcoming.
      ritualPast(hhmm) { return this.seed.is_today && hhmm < this.seed.now_hhmm; },

      get openTask() {
        if (!this.openTaskKey) return null;
        // Resolve from the drawer's originating surface — a dual-membership
        // task has one card per surface and the drawer belongs to ONE of them.
        return this.taskBy(this.keySource(this.openTaskKey), this.keyId(this.openTaskKey));
      },

      // ---- Interaction: keyboard, drag, click -------------------------------
      flatOrder() {
        return [
          ...this.fTriage.map(t => this.cardKey('triage', t.id)),
          ...this.seed.lifepaths.flatMap(lp =>
            this.tasksFor(lp.id).map(t => this.cardKey('ribbon', t.id))),
        ];
      },
      moveSelection(delta) {
        const order = this.flatOrder();
        if (order.length === 0) return;
        let idx = order.indexOf(this.selectedKey);
        if (idx < 0) idx = delta > 0 ? -1 : order.length;
        idx = (idx + delta + order.length) % order.length;
        this.selectedKey = order[idx];
        this.$nextTick(() => {
          const el = document.querySelector(`[data-task-row="${this.selectedKey}"]`);
          if (el) {
            const btn = el.querySelector('[role="button"]');
            if (btn) btn.focus({ preventScroll: false });
          }
        });
      },
      onKey(e) {
        if (this.openTaskKey) return; // drawer owns keys while open
        const k = e.key;
        if (k === 'j' || k === 'ArrowDown')      { e.preventDefault(); this.moveSelection(+1); }
        else if (k === 'k' || k === 'ArrowUp')   { e.preventDefault(); this.moveSelection(-1); }
        else if (k === 'Enter' && this.selectedKey) { e.preventDefault(); this.openDrawer(this.selectedKey); }
        else if (k === 'x' && this.selectedKey) {
          e.preventDefault(); this.completeTask(this.keyId(this.selectedKey));
        }
        else if (k === 'd' && this.selectedKey && !e.shiftKey) {
          e.preventDefault();
          this.deferTask(this.keySource(this.selectedKey), this.keyId(this.selectedKey), '1d');
        }
        else if ((k === 'D' || (k === 'd' && e.shiftKey)) && this.selectedKey) {
          e.preventDefault();
          this.deferTask(this.keySource(this.selectedKey), this.keyId(this.selectedKey), '1w');
        }
      },

      // Row handlers — bound via @click / @mousedown / @keydown in page.py.
      // ``key`` is the composite 'source:uid' card key.
      rowClick(e, key) {
        if (e.target.closest('button')) return;
        this.openDrawer(key);
      },
      rowKey(e, key) {
        if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); this.openDrawer(key); }
      },
      rowDown(e, key) {
        if (e.button !== 0) return;
        const rowEl = e.currentTarget;
        const backdropWrap = rowEl.parentElement;
        const backdrop = backdropWrap.querySelector('[data-defer-backdrop]');
        const hint = backdrop.querySelector('[data-defer-hint]');
        const start = { x: e.clientX, y: e.clientY };
        this.selectedKey = key;
        rowEl.classList.add('dragging');
        let dx = 0, stage = 0;

        const setStage = (s) => {
          if (s === stage) return;
          stage = s;
          backdrop.classList.toggle('stage-1', s === 1);
          backdrop.classList.toggle('stage-2', s === 2);
          hint.classList.toggle('opacity-50', s === 0);
          hint.textContent = s === 2 ? '→ next week'
                          : s === 1 ? '→ tomorrow'
                          : 'drag to defer';
        };

        const onMove = (ev) => {
          dx = Math.max(-20, ev.clientX - start.x);
          if (Math.abs(ev.clientY - start.y) > 20 && Math.abs(dx) < 8) return cancel();
          rowEl.style.setProperty('--dx', dx + 'px');
          setStage(dx > 180 ? 2 : dx > 70 ? 1 : 0);
        };
        const onUp = () => {
          cleanup();
          rowEl.classList.remove('dragging');
          rowEl.style.setProperty('--dx', '0px');
          setStage(0);
          if (dx > 180)      this.deferTask(this.keySource(key), this.keyId(key), '1w');
          else if (dx > 70)  this.deferTask(this.keySource(key), this.keyId(key), '1d');
        };
        const cancel = () => { cleanup(); rowEl.classList.remove('dragging');
                               rowEl.style.setProperty('--dx', '0px'); setStage(0); };
        const cleanup = () => {
          window.removeEventListener('mousemove', onMove);
          window.removeEventListener('mouseup', onUp);
        };
        window.addEventListener('mousemove', onMove);
        window.addEventListener('mouseup', onUp);
      },

      // ---- Actions (optimistic + server confirm) ----------------------------
      openDrawer(key) {
        this.openTaskKey = key;
        this.selectedKey = key;
        // Fire `load-drawer` once Alpine has updated the panel's :hx-get binding
        // to /today/tasks/${openTask.id}/drawer, so HTMX swaps the richer body
        // into #drawer-body (the panel listens via hx-trigger="load-drawer from:body").
        // Without this the drawer opens but its server-derived body stays empty.
        this.$nextTick(() => {
          document.body.dispatchEvent(new Event('load-drawer', { bubbles: true }));
        });
      },
      closeDrawer() {
        const key = this.openTaskKey;
        this.openTaskKey = null;
        this.$nextTick(() => {
          const el = document.querySelector(`[data-task-row="${key}"] [role="button"]`);
          if (el) el.focus();
        });
      },

      completeTask(id) {
        const t = this.taskBy('ribbon', id) || this.taskBy('triage', id);
        this.completed.add(id);
        this._lastAction = { type: 'complete', id };
        this.showFlash(`Completed "${(t && t.label) || id}"`, 'undo');
        if (window.htmx) window.htmx.ajax('POST', `/today/tasks/${id}/complete`, { swap: 'none' });
      },
      // Defer speaks the day it was asked from (C7): the POST carries the
      // lens day (seed.today_iso) and the card's surface, and the server
      // moves the field(s) that card spoke for to view_date + span. The hide
      // is optimistic PER CARD; on ANY non-2xx the card is restored and the
      // server's message shown. No Undo — the client could only lie about it
      // (the mutation already posted); the correction paths are the calendar
      // modal reschedule or deferring again from the new day's lens. Exactly
      // ONE transport per defer control — this fetch is it.
      deferTask(source, id, span) {
        const key = this.cardKey(source, id);
        // A repeat on an already-hidden card (held `d`, double-click) must not
        // re-post: the first request may already have moved the date, so its
        // twin would fail the fresh-membership guard and the non-2xx handler
        // would falsely restore a card whose defer succeeded (Codex #919 P2).
        if (this.deferred[key]) return Promise.resolve();
        const t = this.taskBy(source, id);
        this.deferred[key] = span;
        const label = (t && t.label) || id;
        this.showFlash(
          span === '1w' ? `Deferred "${label}" → next week`
                        : `Deferred "${label}" → tomorrow`);
        const body = new URLSearchParams({
          span: span,
          source: source,
          view_date: this.seed.today_iso || '',
        });
        return fetch(`/today/tasks/${id}/defer`, {
          method: 'POST',
          headers: { 'X-CSRF-Token': (window.SKUEL && window.SKUEL.csrf()) || '' },
          body: body,
        }).then((resp) => {
          if (resp.ok) return undefined;
          return resp.text().then((text) => {
            this.restoreDeferred(key, text || `Defer failed (${resp.status})`);
          });
        }).catch(() => {
          this.restoreDeferred(key, 'Defer failed — network error. The task was not moved.');
        });
      },
      restoreDeferred(key, msg) {
        delete this.deferred[key];
        this.showFlash(msg);
      },

      showFlash(msg, action = null) {
        this.flash = { msg, action };
        clearTimeout(this.flashTimer);
        this.flashTimer = setTimeout(() => this.flash = null, 4200);
      },
      undoFlash() {
        const a = this._lastAction;
        if (!a) { this.flash = null; return; }
        if (a.type === 'complete') this.completed.delete(a.id);
        this._lastAction = null;
        this.flash = null;
      },
    };
  }

  document.addEventListener('alpine:init', function () {
    if (window.Alpine) window.Alpine.data('today', todayFactory);
  });
})();
