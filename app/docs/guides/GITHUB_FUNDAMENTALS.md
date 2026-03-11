---
title: GitHub Fundamentals - Local to Remote Workflow
updated: 2026-01-29
status: current
category: guides
tags: [git, github, guide, workflow]
related: []
tracking: conceptual
last_reviewed: 2026-01-29
review_frequency: quarterly
---

# GitHub Fundamentals - Local to Remote Workflow

**Last Updated:** January 29, 2026
**Audience:** Developers working on SKUEL
**Purpose:** Understand Git basics and the daily workflow for syncing local changes to GitHub

---

## Table of Contents

- [Overview](#overview)
- [Key Concepts](#key-concepts)
- [Local vs Remote Repository](#local-vs-remote-repository)
- [Daily Workflow](#daily-workflow)
- [Commit vs Push - The Critical Difference](#commit-vs-push---the-critical-difference)
- [When to Commit and Push](#when-to-commit-and-push)
- [Best Practices for SKUEL](#best-practices-for-skuel)
- [Common Scenarios](#common-scenarios)
- [Troubleshooting](#troubleshooting)

---

## Overview

**Git** is a version control system that tracks changes to your code over time. **GitHub** is a cloud hosting service for Git repositories that allows collaboration and backup.

**Think of it like this:**
- **Git** = Your local filing cabinet where you organize versions of your work
- **GitHub** = A cloud backup service where you store copies of your filing cabinet

**SKUEL Repository:**
- **Local:** `/home/mike/skuel/app/` (on your computer)
- **Remote:** `https://github.com/your-username/skuel` (on GitHub's servers)

---

## Key Concepts

### Repository (Repo)
A folder containing your project code plus a hidden `.git` directory that tracks all changes.

```bash
/home/mike/skuel/app/
├── core/           # Your code
├── adapters/       # Your code
├── .git/          # Git's tracking database (hidden)
└── README.md
```

### Commit
A **snapshot** of your code at a specific point in time. Like saving a game checkpoint.

**Analogy:** Taking a photo of your workspace at the end of the day.

**What it does:**
- Records changes to your **local** repository only
- Creates a permanent record with a message describing what changed
- Does NOT send anything to GitHub yet

### Push
Uploading your **local commits** to GitHub's servers.

**Analogy:** Uploading photos from your camera to cloud storage.

**What it does:**
- Sends all your local commits to GitHub
- Makes your changes visible to collaborators
- Creates a backup on GitHub's servers

### Pull
Downloading changes from GitHub to your local machine.

**Analogy:** Downloading photos from cloud storage to your camera.

**What it does:**
- Fetches commits from GitHub that you don't have locally
- Updates your local files to match the remote
- Used when working across multiple computers or with collaborators

### Branch
A parallel version of your code. The default branch is usually `main` or `master`.

**Analogy:** A branch is like a separate notebook where you try out ideas before copying them into your main notebook.

### Staging Area
A holding area where you prepare changes before committing them.

**Analogy:** A staging area is like a packing list - you choose what to include in your shipment before sealing the box.

---

## Local vs Remote Repository

### Visual Representation

```
┌─────────────────────────────────────────────────────────────┐
│  YOUR COMPUTER (Local Repository)                           │
│  /home/mike/skuel/app/                                      │
│                                                              │
│  Working Directory     Staging Area        Local Git DB     │
│  (Your files)          (Ready to commit)   (.git folder)    │
│       │                     │                    │          │
│       │  git add .          │   git commit       │          │
│       ├────────────────────→│───────────────────→│          │
│       │                     │                    │          │
└───────┼─────────────────────┼────────────────────┼──────────┘
        │                     │                    │
        │                     │        git push    │
        │                     │                    ↓
┌───────┼─────────────────────┼────────────────────────────────┐
│       │                     │         GITHUB (Remote)        │
│       │                     │    github.com/user/skuel       │
│       │        git pull     │                                │
│       ←─────────────────────┴────────────────────────────────│
│                                                               │
│  Remote Git DB (online backup + collaboration)               │
└───────────────────────────────────────────────────────────────┘
```

### Key Understanding

**Three Stages of Your Work:**
1. **Working Directory** - Files you're actively editing
2. **Staging Area** - Changes you've marked to include in next commit
3. **Local Repository** - Committed snapshots stored in `.git/`
4. **Remote Repository** - Commits pushed to GitHub

**Flow:**
```
Edit files → Stage changes → Commit locally → Push to GitHub
   ↓              ↓              ↓                 ↓
Working       Staging         Local            Remote
Directory     Area            Repo             (GitHub)
```

---

## Daily Workflow

### Step-by-Step: Making Changes and Syncing to GitHub

#### 1. Check Current Status

Before starting work, see what branch you're on and if there are uncommitted changes:

```bash
cd /home/mike/skuel/app
git status
```

**Output example:**
```
On branch main
Your branch is up to date with 'origin/main'.

nothing to commit, working tree clean
```

#### 2. Pull Latest Changes (if working with others or across machines)

Get the latest code from GitHub before making changes:

```bash
git pull
```

**Why?** Ensures you're working with the most recent version and avoids conflicts.

#### 3. Make Your Changes

Edit files as needed using your editor (VS Code, vim, etc.):

```bash
# Example: Edit a service file
vim core/services/tasks_service.py

# Or open in VS Code
code core/services/tasks_service.py
```

#### 4. Check What Changed

See which files you modified:

```bash
git status
```

**Output example:**
```
On branch main
Changes not staged for commit:
  modified:   core/services/tasks_service.py
  modified:   docs/patterns/SERVICE_PATTERNS.md

Untracked files:
  tests/test_new_feature.py
```

See the actual changes:

```bash
# See all changes
git diff

# See changes in a specific file
git diff core/services/tasks_service.py
```

#### 5. Stage Your Changes

Add files to the staging area (preparing them for commit):

```bash
# Add specific files
git add core/services/tasks_service.py
git add tests/test_new_feature.py

# OR add all changed files at once
git add .

# OR add all files in a directory
git add core/services/
```

**Check staged changes:**
```bash
git status
```

**Output example:**
```
On branch main
Changes to be committed:
  modified:   core/services/tasks_service.py
  new file:   tests/test_new_feature.py
```

#### 6. Commit Your Changes

Create a snapshot with a descriptive message:

```bash
git commit -m "Add task completion analytics method

- Implement get_completion_analytics() in TasksService
- Add integration test for completion tracking
- Update service documentation

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>"
```

**Commit message format:**
- **First line:** Short summary (50-70 characters)
- **Blank line**
- **Body:** Detailed explanation (what and why, not how)
- **Co-Author:** Credit collaborators (optional)

**After commit:**
```bash
git status
```

**Output:**
```
On branch main
Your branch is ahead of 'origin/main' by 1 commit.
  (use "git push" to publish your local commits)

nothing to commit, working tree clean
```

**Note:** "ahead of 'origin/main' by 1 commit" means you have 1 local commit not yet on GitHub.

#### 7. Push to GitHub

Upload your commits to GitHub:

```bash
git push
```

**Output:**
```
Enumerating objects: 8, done.
Counting objects: 100% (8/8), done.
Delta compression using up to 8 threads
Compressing objects: 100% (5/5), done.
Writing objects: 100% (5/5), 1.23 KiB | 1.23 MiB/s, done.
Total 5 (delta 3), reused 0 (delta 0)
To github.com:your-username/skuel.git
   d47385a..e359d55  main -> main
```

**Success!** Your changes are now on GitHub.

#### 8. Verify on GitHub

Visit your repository on GitHub to confirm:
```
https://github.com/your-username/skuel/commits/main
```

You should see your commit message and changes.

---

## Commit vs Push - The Critical Difference

### The Fundamental Difference

| Aspect | Commit | Push |
|--------|--------|------|
| **Location** | Local only | Local → GitHub |
| **Visibility** | Only you can see it | Everyone with access can see it |
| **Network Required** | No | Yes |
| **Can be undone** | Yes, easily | Yes, but affects others |
| **Frequency** | Often (every logical change) | Less often (end of work session) |
| **Purpose** | Save progress, create checkpoint | Backup, share, collaborate |

### Visual Example

**Scenario:** You're adding a new feature over 2 hours.

```
Time    Action                          Local Commits    Remote (GitHub)
────────────────────────────────────────────────────────────────────────
10:00   Start work                           0                0
10:15   Add service method                   1                0  ← Committed locally
10:30   Add tests                            2                0  ← Committed locally
10:45   Update documentation                 3                0  ← Committed locally
11:00   Fix bug found in testing             4                0  ← Committed locally
11:15   git push                             4                4  ← Pushed to GitHub
```

**Key Insight:**
- You made **4 commits** locally over 75 minutes
- You **pushed once** when the work was complete and tested
- GitHub only knows about your changes after the push

### Why This Matters

**Commits are cheap and safe:**
```bash
# You can commit tiny changes without worry
git commit -m "Fix typo in docstring"
git commit -m "Add input validation"
git commit -m "Refactor method name for clarity"
# Still local - no one sees these yet
```

**Push is the "publish" button:**
```bash
git push  # Now everyone sees ALL your commits
```

### Real-World Analogy

**Commit** = Saving drafts of an email as you write it
- You can save multiple times
- You can edit previous drafts
- No one else sees them
- You can delete drafts

**Push** = Clicking "Send" on the email
- All your drafts become the final version
- Others can now read it
- Can't easily take it back
- Creates a permanent record

---

## When to Commit and Push

### When to Commit

**Commit often, whenever you complete a logical unit of work:**

✅ **Good times to commit:**
- You fixed a bug (even a small one)
- You added a new method/function
- You completed a test
- You updated documentation for a change
- You refactored code to be clearer
- Before trying something experimental
- Before taking a break

❌ **Bad times to commit:**
- Code doesn't run at all
- Tests are failing (unless intentional TDD)
- In the middle of editing a function
- You just changed a single character

**Rule of thumb:** If you can describe the change in one sentence, it's ready to commit.

**Example commit frequency for a 4-hour coding session:**
```
10:00 - Start work
10:30 - Commit: "Add User authentication check to TasksService"
11:00 - Commit: "Write tests for authentication validation"
11:30 - Commit: "Update API routes with auth decorator"
12:00 - Commit: "Add authentication documentation"
12:15 - Commit: "Fix edge case in auth when user is None"
12:30 - Push all commits to GitHub
```

**Total:** 5 commits, 1 push

### When to Push

**Push less frequently, when your work is stable and ready to share:**

✅ **Good times to push:**
- End of your work session
- After completing a feature (all tests pass)
- Before switching computers
- After a series of related commits
- Before asking for code review
- At least once per day if you made changes

❌ **Bad times to push:**
- Code is broken or incomplete
- Tests are failing (unless you're explicitly documenting a bug)
- You haven't tested your changes locally
- You just committed 30 seconds ago (too soon)

**Rule of thumb:** Push when you have a coherent set of commits that tell a story.

### Practical Guidelines for SKUEL

**Minimum:** Push once per day if you made any commits.

**Typical workflow:**
```bash
# Morning: Start work
git pull                          # Get latest

# Work session 1 (1-2 hours)
# ... make changes ...
git add .
git commit -m "..."              # Commit logical changes
# ... make more changes ...
git commit -m "..."              # Another commit

# Lunch break: Push progress
git push                         # Backup work before break

# Afternoon session
# ... make changes ...
git commit -m "..."              # More commits

# End of day: Push everything
git push                         # Final backup
```

### Quick Decision Matrix

```
Question: Should I commit now?
├─ Can I describe what I changed in one sentence? YES
├─ Does the code run without errors? YES
└─ Are my tests passing (or intentionally failing for TDD)? YES
   → ✅ COMMIT NOW

Question: Should I push now?
├─ Do I have unpushed commits? YES
├─ Is my work in a stable state? YES
├─ Have I tested my changes? YES
└─ Am I about to: take a break, end the day, switch computers? YES
   → ✅ PUSH NOW
```

---

## Best Practices for SKUEL

### 1. Always Pull Before Starting Work

```bash
cd /home/mike/skuel/app
git pull
```

**Why:** Ensures you have the latest code and avoids merge conflicts.

### 2. Use Descriptive Commit Messages

**Bad:**
```bash
git commit -m "fix"
git commit -m "updates"
git commit -m "wip"
```

**Good:**
```bash
git commit -m "Fix null pointer error in TasksService.get_task()

When task_uid was None, get_task() would crash. Added validation
to return an error Result instead.

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>"
```

**SKUEL Format:**
```
<Short summary - imperative mood, 50-70 chars>

<Blank line>

<Detailed explanation of what changed and why>
- Bullet points for clarity
- Multiple lines are fine

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>
```

### 3. Commit Related Changes Together

**Bad:** One commit with unrelated changes
```bash
git commit -m "Fix bug and add new feature and update docs and refactor"
```

**Good:** Separate commits for separate concerns
```bash
git commit -m "Fix authentication bug in login flow"
git commit -m "Add password strength validation"
git commit -m "Update security documentation"
```

### 4. Don't Commit Sensitive Information

**Never commit:**
- API keys, passwords, secrets
- `.env` files with real credentials
- Personal data or tokens

**Already committed secrets?** Remove them from history:
```bash
# Contact your team lead - this requires special handling
# DO NOT just delete and commit - it's still in history!
```

### 5. Check Status Before Committing

```bash
# Always check what you're about to commit
git status
git diff

# Then stage and commit
git add .
git commit -m "..."
```

### 6. Test Before Pushing

```bash
# Run tests before pushing
uv run pytest

# If tests pass, then push
git push
```

### 7. Push at Least Daily

Even if your work isn't "done", push your commits daily for backup:

```bash
# End of day, even if feature isn't complete
git add .
git commit -m "WIP: Add user analytics (partial implementation)

- Implemented data collection
- TODO: Add aggregation logic
- TODO: Add tests"

git push
```

**WIP** = Work In Progress (signals incomplete work)

---

## Common Scenarios

### Scenario 1: You Made Changes But Forgot to Pull First

**Problem:**
```bash
git push
# Error: Updates were rejected because the remote contains work you don't have
```

**Solution:**
```bash
# Pull the latest changes
git pull

# Git will attempt to merge automatically
# If successful:
git push

# If there are conflicts, Git will tell you which files
# Edit those files, resolve conflicts, then:
git add .
git commit -m "Merge remote changes"
git push
```

### Scenario 2: You Committed Too Soon (Code Doesn't Work)

**Problem:** You committed broken code and want to fix it before pushing.

**Solution - Amend the commit:**
```bash
# Make your fixes
vim core/services/tasks_service.py

# Stage the fixes
git add .

# Amend the previous commit (rewrites it)
git commit --amend

# No need to change the message, just save and exit
# Now your commit includes the fixes
```

**⚠️ Warning:** Only amend commits that haven't been pushed yet!

### Scenario 3: You Want to Undo the Last Commit

**Problem:** You committed something you shouldn't have.

**Solution - Before pushing:**
```bash
# Undo commit but keep changes in working directory
git reset HEAD~1

# Now you can modify files and recommit
# Or discard changes entirely:
git checkout .
```

**⚠️ Warning:** If you already pushed, contact your team lead!

### Scenario 4: You Accidentally Committed a Large File

**Problem:**
```bash
git push
# Error: file size exceeds GitHub's maximum (100MB)
```

**Solution:**
```bash
# Remove the file from Git tracking
git rm --cached path/to/large/file

# Add to .gitignore to prevent future commits
echo "path/to/large/file" >> .gitignore

# Commit the removal
git commit -m "Remove large file from version control"

# If the file was in previous commits:
# Contact your team lead - requires rewriting history
```

### Scenario 5: Checking Commit History

**See recent commits:**
```bash
# Short format
git log --oneline -10

# Detailed format
git log -5

# See what changed in each commit
git log -p -3
```

**See commits not yet pushed:**
```bash
git log origin/main..HEAD
```

### Scenario 6: Working on a Feature Branch

**Create and switch to a new branch:**
```bash
# Create feature branch
git checkout -b feature/user-analytics

# Make changes and commit
git add .
git commit -m "Add user analytics endpoint"

# Push the branch to GitHub
git push -u origin feature/user-analytics

# Switch back to main
git checkout main

# Merge your feature (after review)
git merge feature/user-analytics
git push
```

---

## Troubleshooting

### Problem: "fatal: not a git repository"

**Cause:** You're not in the SKUEL directory.

**Solution:**
```bash
cd /home/mike/skuel/app
git status  # Should work now
```

### Problem: "Your branch is behind 'origin/main'"

**Cause:** Someone else pushed changes to GitHub that you don't have locally.

**Solution:**
```bash
git pull
```

### Problem: "Permission denied (publickey)"

**Cause:** GitHub doesn't recognize your SSH key.

**Solution:**
```bash
# Check if you have SSH keys
ls ~/.ssh/

# If no keys, generate one:
ssh-keygen -t ed25519 -C "your-email@example.com"

# Add key to GitHub:
cat ~/.ssh/id_ed25519.pub
# Copy the output and add it to GitHub settings → SSH Keys
```

### Problem: "Merge conflict"

**Cause:** You and someone else changed the same lines of code.

**Solution:**
```bash
git pull
# Git will show conflict markers in files:

<<<<<<< HEAD
Your changes
=======
Their changes
>>>>>>> origin/main

# Edit the file to resolve conflicts
# Remove the markers (<<<, ===, >>>)
# Keep the correct version or combine both

# Stage the resolved file
git add path/to/conflicted/file

# Complete the merge
git commit -m "Merge remote changes and resolve conflicts"
git push
```

### Problem: "Detached HEAD state"

**Cause:** You checked out a specific commit instead of a branch.

**Solution:**
```bash
# Go back to the main branch
git checkout main
```

### Problem: Need to See What Changed in a File

**See changes not yet staged:**
```bash
git diff path/to/file
```

**See changes staged for commit:**
```bash
git diff --staged path/to/file
```

**See changes in last commit:**
```bash
git show HEAD path/to/file
```

---

## Quick Reference Commands

### Essential Daily Commands

```bash
# Check status
git status

# Pull latest changes
git pull

# Stage changes
git add .                              # All files
git add path/to/specific/file          # Specific file

# Commit
git commit -m "Description of changes"

# Push to GitHub
git push

# See recent commits
git log --oneline -10
```

### Less Common But Useful

```bash
# See what changed
git diff                               # Unstaged changes
git diff --staged                      # Staged changes

# Unstage a file (before commit)
git reset path/to/file

# Discard changes in a file
git checkout -- path/to/file

# Undo last commit (keep changes)
git reset HEAD~1

# See commit history
git log
git log --oneline --graph --all

# Create new branch
git checkout -b branch-name

# Switch branches
git checkout branch-name

# List branches
git branch -a
```

### Emergency Commands (Use with Caution)

```bash
# Discard ALL uncommitted changes
git reset --hard HEAD

# Undo pushed commit (creates new commit that reverses it)
git revert HEAD
git push
```

---

## Additional Resources

**SKUEL-Specific Documentation:**
- [CLAUDE.md](/home/mike/skuel/app/CLAUDE.md) - Project conventions
- [Git Commit Instructions](/home/mike/skuel/app/CLAUDE.md#committing-changes-with-git) - Detailed commit workflow

**External Resources:**
- [Git Documentation](https://git-scm.com/doc)
- [GitHub Guides](https://guides.github.com/)
- [Pro Git Book](https://git-scm.com/book/en/v2) (free online)

**GitHub Desktop (GUI Alternative):**
If you prefer a visual interface: https://desktop.github.com/

---

## Summary

**Key Takeaways:**

1. **Commit** = Save a snapshot locally (do this often)
2. **Push** = Upload commits to GitHub (do this less often, when stable)
3. **Pull** = Download changes from GitHub (do this before starting work)

**Daily Workflow:**
```bash
git pull          # Start of day
# ... work ...
git add .         # Stage changes
git commit -m ""  # Commit logical units
# ... more work ...
git commit -m ""  # More commits
git push          # End of day/session
```

**Golden Rules:**
- Pull before starting work
- Commit often (every logical change)
- Push at least daily (when work is stable)
- Test before pushing
- Write clear commit messages
- Never commit secrets

---

**Last Updated:** January 29, 2026
**Maintained By:** SKUEL Core Team
**Questions?** Ask your team lead or refer to CLAUDE.md
