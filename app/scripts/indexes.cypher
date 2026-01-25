// Priority 1: User UID indexes (10-100x faster)
CREATE INDEX task_user_uid IF NOT EXISTS FOR (t:Task) ON (t.user_uid);
CREATE INDEX habit_user_uid IF NOT EXISTS FOR (h:Habit) ON (h.user_uid);
CREATE INDEX goal_user_uid IF NOT EXISTS FOR (g:Goal) ON (g.user_uid);
CREATE INDEX event_user_uid IF NOT EXISTS FOR (e:Event) ON (e.user_uid);
CREATE INDEX expense_user_uid IF NOT EXISTS FOR (e:Expense) ON (e.user_uid);
CREATE INDEX choice_user_uid IF NOT EXISTS FOR (c:Choice) ON (c.user_uid);
CREATE INDEX principle_user_uid IF NOT EXISTS FOR (p:Principle) ON (p.user_uid);

// Priority 2: Status indexes (5-10x faster)
CREATE INDEX task_status IF NOT EXISTS FOR (t:Task) ON (t.status);
CREATE INDEX habit_status IF NOT EXISTS FOR (h:Habit) ON (h.status);
CREATE INDEX goal_status IF NOT EXISTS FOR (g:Goal) ON (g.status);
CREATE INDEX event_status IF NOT EXISTS FOR (e:Event) ON (e.status);

// Priority 2: Date indexes (10-50x faster)
CREATE INDEX task_due_date IF NOT EXISTS FOR (t:Task) ON (t.due_date);
CREATE INDEX event_event_date IF NOT EXISTS FOR (e:Event) ON (e.event_date);
CREATE INDEX goal_target_date IF NOT EXISTS FOR (g:Goal) ON (g.target_date);
CREATE INDEX expense_expense_date IF NOT EXISTS FOR (e:Expense) ON (e.expense_date);

// Priority 3: Knowledge indexes (5-10x faster)
CREATE INDEX ku_sel_category IF NOT EXISTS FOR (ku:Ku) ON (ku.sel_category);
CREATE INDEX ku_learning_level IF NOT EXISTS FOR (ku:Ku) ON (ku.learning_level);
CREATE INDEX ku_content_type IF NOT EXISTS FOR (ku:Ku) ON (ku.content_type);

// Priority 4: Combined indexes (maximum performance)
CREATE INDEX task_user_status IF NOT EXISTS FOR (t:Task) ON (t.user_uid, t.status);
CREATE INDEX expense_user_category IF NOT EXISTS FOR (e:Expense) ON (e.user_uid, e.category);
CREATE INDEX goal_user_status IF NOT EXISTS FOR (g:Goal) ON (g.user_uid, g.status);
