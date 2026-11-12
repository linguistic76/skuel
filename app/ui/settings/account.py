"""The Account card on ``/settings``: the name a user is shown by.

One field and its own Save, posting to ``POST /api/user/display-name``; the door
answers with this card re-rendered, so saving swaps the card and nothing else on
the page.
"""

from fasthtml.common import FT, H3, Form, P

from core.models.user.user import DISPLAY_NAME_MAX_LENGTH
from ui.components import Button, ButtonT, Card, CardBody
from ui.forms.components import LabelInput

ACCOUNT_CARD_ID = "account-card"

#: What the card says when the door refuses a name.
DISPLAY_NAME_REFUSAL = f"Enter a name of 1 to {DISPLAY_NAME_MAX_LENGTH} characters, on one line."


def render_account_card(
    display_name: str | None, *, note: str | None = None, saved: bool = False
) -> FT:
    """The Account card, its field holding ``display_name`` (the stored name).

    ``note`` is a refusal from the door, shown on the field; ``saved`` says the
    name in the field was just stored.
    """
    return Card(
        CardBody(
            H3("Account", cls="font-semibold mb-2"),
            Form(
                LabelInput(
                    "Display name",
                    id="account-display-name",
                    name="display_name",
                    value=display_name or "",
                    required=True,
                    maxlength=str(DISPLAY_NAME_MAX_LENGTH),
                    autocomplete="name",
                    help_text="Shown to your teachers and the people you share with",
                    error_text=note,
                ),
                Button("Save", type="submit", cls=f"{ButtonT.primary} mt-4"),
                P("Saved", cls="text-sm text-success mt-2", role="status") if saved else None,
                hx_post="/api/user/display-name",
                hx_target=f"#{ACCOUNT_CARD_ID}",
                hx_swap="outerHTML",
                data_announce="Display name saved",
            ),
        ),
        id=ACCOUNT_CARD_ID,
        cls="bg-background shadow-xs mb-6",
    )


__all__ = ["ACCOUNT_CARD_ID", "DISPLAY_NAME_REFUSAL", "render_account_card"]
