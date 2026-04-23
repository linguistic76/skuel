/**
 * Today surface — Alpine factory.
 *
 * Registers ``Alpine.data('today', factory)``; pair with ``x-data="today"``
 * on the page root (``ui/today/page.py``). Seed comes from
 * ``window.SEED`` emitted by the server in the same document.
 *
 * Row rendering uses a hand-written template literal (vs. Alpine's
 * <template x-for>) so drag handlers, dynamic classes, and optimistic
 * state can all live in one render path — see today.md §7 and the plan's
 * "Row rendering decision" note.
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
        date_label: '', now_hhmm: '00:00', stats: {nodes: 0, committed_min: 0, done: 0},
        triage: [], lifepaths: [], principles: [], goals: [], tasks: [], rituals: [], kinds: {},
      },
      selectedId: null,
      openTaskId: null,
      flash: null,
      flashTimer: null,
      deferred: {},          // id -> '1d' | '1w' (optimistic hidden until confirm)
      completed: new Set(),  // ids
      _lastAction: null,     // for undo

      init() {
        // Expose for innerHTML-rendered row handlers that can't see Alpine's `this`.
        window._today = this;
      },

      // ---- Derived ---------------------------------------------------------
      get fTasks()  { return this.seed.tasks.filter(t =>
        !this.deferred[t.id] && !this.completed.has(t.id)); },
      get fTriage() { return this.seed.triage.filter(t =>
        !this.deferred[t.id] && !this.completed.has(t.id)); },
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

      // Day-spine helpers
      ritualPct(hhmm) {
        const [h, m] = hhmm.split(':').map(Number);
        const frac = h + m/60;
        return Math.max(0, Math.min(1, (frac - 6) / 16));
      },
      ritualPast(hhmm) { return hhmm < this.seed.now_hhmm; },

      get openTask() {
        if (!this.openTaskId) return null;
        const t = this.seed.tasks.find(x => x.id === this.openTaskId);
        if (t) return t;
        const tri = this.seed.triage.find(x => x.id === this.openTaskId);
        return tri || null;
      },

      // ---- Row renderer -----------------------------------------------------
      renderRow(t, opts = {}) {
        const k = this.seed.kinds[t.kind] || this.seed.kinds['submission'] || {icon: 'file-text'};
        const priClass = t.priority === 'high' ? 'bg-priority-high'
                       : t.priority === 'medium' ? 'bg-priority-medium' : 'bg-priority-low';
        const selected = this.selectedId === t.id;
        const rightLabel = opts.isTriage ? t.reason : t.due_label;
        const label = (t.label || '').replace(/"/g, '&quot;');
        return `
          <div class="relative" data-task-row="${t.id}">
            <div class="defer-backdrop absolute inset-0 rounded-md flex items-center justify-end
                        px-4 text-xs font-semibold tracking-wide pointer-events-none"
                 data-defer-backdrop>
              <span data-defer-hint class="opacity-50">drag to defer</span>
            </div>
            <div class="task-row relative flex items-center gap-3 px-3.5 py-2.5 bg-card
                        ${opts.isTriage ? 'border border-border' : ''}
                        ${selected ? 'ring-2 ring-primary/40 shadow-focus' : ''}
                        rounded-md cursor-grab select-none"
                 role="button" tabindex="0"
                 aria-label="${label} · ${rightLabel || ''} · ${t.est_min}m"
                 onmousedown="window._today.rowDown(event, '${t.id}')"
                 onclick="window._today.rowClick(event, '${t.id}')"
                 onkeydown="window._today.rowKey(event, '${t.id}')">

              <div class="w-[30px] h-[30px] rounded flex-none flex items-center justify-center
                          bg-muted text-muted-foreground">
                <uk-icon icon="${k.icon}" height="14" width="14"></uk-icon>
              </div>

              <div class="flex-1 min-w-0">
                <div class="flex items-center gap-2">
                  <span class="text-[13.5px] font-semibold text-foreground leading-snug truncate">
                    ${t.label}
                  </span>
                  <span class="w-1.5 h-1.5 rounded-full ${priClass} flex-none"
                        title="${t.priority}"></span>
                </div>
                <div class="text-[11px] text-muted-foreground font-mono mt-0.5 truncate">
                  ${t.meta || ''}
                </div>
              </div>

              <div class="flex flex-col items-end gap-0.5 flex-none">
                <span class="text-[11px] font-semibold text-foreground">${rightLabel || ''}</span>
                <span class="text-[10px] text-muted-foreground font-mono">${t.est_min}m</span>
              </div>

              <button type="button"
                      class="w-7 h-7 rounded flex-none flex items-center justify-center
                             ${selected ? 'bg-primary text-primary-foreground' : 'text-muted-foreground hover:bg-muted'}"
                      aria-label="Open ${label}"
                      onclick="event.stopPropagation(); window._today.openDrawer('${t.id}')">
                <uk-icon icon="play" height="12" width="12"></uk-icon>
              </button>
            </div>
          </div>
        `;
      },

      // ---- Interaction: keyboard, drag, click -------------------------------
      flatOrder() {
        return [
          ...this.fTriage.map(t => t.id),
          ...this.seed.lifepaths.flatMap(lp => this.tasksFor(lp.id).map(t => t.id)),
        ];
      },
      moveSelection(delta) {
        const order = this.flatOrder();
        if (order.length === 0) return;
        let idx = order.indexOf(this.selectedId);
        if (idx < 0) idx = delta > 0 ? -1 : order.length;
        idx = (idx + delta + order.length) % order.length;
        this.selectedId = order[idx];
        this.$nextTick(() => {
          const el = document.querySelector(`[data-task-row="${this.selectedId}"]`);
          if (el) {
            const btn = el.querySelector('[role="button"]');
            if (btn) btn.focus({ preventScroll: false });
          }
        });
      },
      onKey(e) {
        if (this.openTaskId) return; // drawer owns keys while open
        const k = e.key;
        if (k === 'j' || k === 'ArrowDown')      { e.preventDefault(); this.moveSelection(+1); }
        else if (k === 'k' || k === 'ArrowUp')   { e.preventDefault(); this.moveSelection(-1); }
        else if (k === 'Enter' && this.selectedId) { e.preventDefault(); this.openDrawer(this.selectedId); }
        else if (k === 'x' && this.selectedId)     { e.preventDefault(); this.completeTask(this.selectedId); }
        else if (k === 'd' && this.selectedId && !e.shiftKey) {
          e.preventDefault(); this.deferTask(this.selectedId, '1d');
        }
        else if ((k === 'D' || (k === 'd' && e.shiftKey)) && this.selectedId) {
          e.preventDefault(); this.deferTask(this.selectedId, '1w');
        }
      },

      // Row handlers — innerHTML-rendered rows call these via window._today.
      rowClick(e, id) {
        if (e.target.closest('button')) return;
        this.openDrawer(id);
      },
      rowKey(e, id) {
        if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); this.openDrawer(id); }
      },
      rowDown(e, id) {
        if (e.button !== 0) return;
        const rowEl = e.currentTarget;
        const backdropWrap = rowEl.parentElement;
        const backdrop = backdropWrap.querySelector('[data-defer-backdrop]');
        const hint = backdrop.querySelector('[data-defer-hint]');
        const start = { x: e.clientX, y: e.clientY };
        this.selectedId = id;
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
          if (dx > 180)      this.deferTask(id, '1w');
          else if (dx > 70)  this.deferTask(id, '1d');
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

      // ---- Actions (optimistic + HTMX confirm) ------------------------------
      openDrawer(id) {
        this.openTaskId = id;
        this.selectedId = id;
      },
      closeDrawer() {
        const id = this.openTaskId;
        this.openTaskId = null;
        this.$nextTick(() => {
          const el = document.querySelector(`[data-task-row="${id}"] [role="button"]`);
          if (el) el.focus();
        });
      },

      completeTask(id) {
        const t = this.openTask || this.seed.tasks.find(x => x.id === id)
                                || this.seed.triage.find(x => x.id === id);
        this.completed.add(id);
        this._lastAction = { type: 'complete', id };
        this.showFlash(`Completed "${(t && t.label) || id}"`, 'undo');
        if (window.htmx) window.htmx.ajax('POST', `/today/tasks/${id}/complete`, { swap: 'none' });
      },
      deferTask(id, span) {
        const t = this.openTask || this.seed.tasks.find(x => x.id === id)
                                || this.seed.triage.find(x => x.id === id);
        this.deferred[id] = span;
        this._lastAction = { type: 'defer', id, span };
        this.showFlash(
          span === '1w' ? `Deferred "${(t && t.label) || id}" → next week`
                        : `Deferred "${(t && t.label) || id}" → tomorrow`,
          'undo');
        if (window.htmx) window.htmx.ajax('POST', `/today/tasks/${id}/defer`,
          { swap: 'none', values: { span }});
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
        if (a.type === 'defer')    delete this.deferred[a.id];
        this._lastAction = null;
        this.flash = null;
      },
    };
  }

  document.addEventListener('alpine:init', function () {
    if (window.Alpine) window.Alpine.data('today', todayFactory);
  });
})();
