"""UserEntry UI package (ADR-054 Step 9).

Home for the rewritten submit form with first-class audience + pipeline
controls. Replaces ``ui/submissions/forms.py``'s ``render_upload_form``
post-cleanup; both live side-by-side through Step 13 per the
additive-through-Step-13 discipline.
"""

from ui.user_entry.forms import render_upload_form, upload_form_script

__all__ = ["render_upload_form", "upload_form_script"]
