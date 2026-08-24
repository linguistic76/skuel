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
      // docs/roadmap/done/calendar-act-from-arc.md). Completion stays uid-keyed
      // deliberately: completing is a task-level fact and hides both cards.
      selectedKey: null,     // 'ribbon:<uid>' | 'triage:<uid>'
      openTaskKey: null,
      flash: null,
      flashTimer: null,
      deferred: {},          // cardKey -> '1d' | '1w' (optimistic hide, per card)
      completed: new Set(),  // uids
      // For undo (complete only — defer has no truthful undo).
      // { type: 'complete', id, status } — `status` is the status the card
      // carried BEFORE the complete, and is what undo posts back to reopen.
      _lastAction: null,
      // taskId -> the in-flight write for THAT task. Writes to one task are
      // serialized in click order (see _queueWrite); writes to different tasks
      // stay parallel.
      _pendingWrites: {},

      // Serialize the writes for ONE task, and only that task. Undo posts a
      // reopen that directly opposes a complete which may still be in flight,
      // so the two must land in click order — but a single shared promise would
      // also chain every OTHER task's complete behind the previous one's slow
      // cascade, turning parallel writes into a serial queue. Keying by task id
      // is what makes "ordered" and "parallel" both true.
      //
      // ``send`` runs when the previous write for this task SETTLES, not when it
      // succeeds: a failed complete means the task is not completed, so posting
      // the prior status is a harmless no-op in the safe direction, and a
      // rejection must never strand the next write. The stored link swallows for
      // the same reason.
      _queueWrite(id, send) {
        const previous = this._pendingWrites[id];
        // Fire IMMEDIATELY when nothing is in flight for this task. Routing the
        // first write through a resolved promise would delay every write by a
        // microtask for no benefit — only a write that has something to wait for
        // waits.
        const pending = (previous ? previous.then(send, send) : Promise.resolve(send()))
          .catch(() => undefined);
        this._pendingWrites[id] = pending;
        // Drop the entry once this is the last write for the task, so the map
        // does not accumulate a settled promise for every card ever touched.
        // The identity check is what makes this safe: if another write was
        // queued while this one was in flight, the map already holds THAT link.
        pending.then(() => {
          if (this._pendingWrites[id] === pending) delete this._pendingWrites[id];
        });
        return pending;
      },

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
        // Never hijack keystrokes typed into a field: j/k/x/d are single-key
        // actions, but the day-lens quick-add input needs those letters as text.
        const el = e.target;
        if (el && (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA' ||
                   el.tagName === 'SELECT' || el.isContentEditable)) return;
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

      // Undo carries the PRIOR status so it can truthfully reopen the task
      // (see undoFlash). It is offered only when that status is known — a card
      // with no seeded status could be un-hidden but not reopened, which is the
      // exact lie deferTask refuses to offer.
      completeTask(id) {
        const t = this.taskBy('ribbon', id) || this.taskBy('triage', id);
        const prevStatus = (t && t.status) || null;
        this.completed.add(id);
        this._lastAction = prevStatus ? { type: 'complete', id, status: prevStatus } : null;
        this.showFlash(`Completed "${(t && t.label) || id}"`, prevStatus ? 'undo' : null);
        if (!window.htmx) return Promise.resolve();
        // Queued, not fired: a re-complete after Undo has to wait for that
        // reopen, exactly as the reopen waits for the complete before it.
        return this._queueWrite(id, () =>
          window.htmx.ajax('POST', `/today/tasks/${id}/complete`, { swap: 'none' }),
        );
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
      // Undo POSTS the reopen; it does not merely un-hide the card. The
      // complete already persisted, so clearing local state alone would leave
      // the card reading "not done" over a graph that has it completed —
      // deferTask's comment above names that class of lie exactly.
      // The prior status goes back through the live status chokepoint
      // (CSRF-protected, ownership-checked); `swap: 'none'` discards the card
      // fragment it returns, since Alpine already owns this row's rendering.
      // Reopening also clears `completion_date` at that chokepoint, so the
      // stamp stays non-null exactly when the task is completed.
      //
      // ORDERING: the flash appears immediately, so Undo is routinely clicked
      // while the complete POST is still in flight, and the two requests oppose
      // each other. Both doors are settled now (ADR-087 PR-1 + PR-2) and they are
      // NOT symmetric:
      //
      //   complete → POST /today/tasks/{uid}/complete → complete_task_with_cascade,
      //       which reads the task and its relationships for the cascade fan-out
      //       before its one guarded write;
      //   reopen   → POST /api/tasks/{uid}/status → update_task, which for a
      //       status-only change reads NOTHING — one guarded write.
      //
      // So the complete is the slower request, by a wider margin than before. An
      // unqueued reopen can land FIRST and then be overwritten by the complete,
      // leaving the task completed under a card that already reads "not done"
      // (Codex #1133 P1).
      //
      // The server fixes the VERDICT, not the ORDER. Each write captures the
      // status it overwrites under the node's lock, so whichever sequence the
      // requests arrive in, every completion/reopen verdict — and the completion
      // stamp that follows from it — is exact, and the stamp stays non-null
      // exactly when the task is completed. What no server-side guard can decide
      // is which of two opposing requests the user MEANT to win. That is what
      // this queue is for, and why it stays.
      //
      // It is keyed PER TASK: only writes to the same task need ordering, and a
      // single shared promise would chain every task's complete behind the
      // previous one's cascade. See _queueWrite.
      undoFlash() {
        const a = this._lastAction;
        this._lastAction = null;
        this.flash = null;
        if (!a || a.type !== 'complete') return Promise.resolve();
        this.completed.delete(a.id);
        if (!window.htmx) return Promise.resolve();
        return this._queueWrite(a.id, () =>
          window.htmx.ajax('POST', `/api/tasks/${a.id}/status`, {
            swap: 'none',
            values: { status: a.status },
          }),
        );
      },
    };
  }

  document.addEventListener('alpine:init', function () {
    if (window.Alpine) window.Alpine.data('today', todayFactory);
  });
})();
