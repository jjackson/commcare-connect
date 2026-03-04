from crispy_forms.layout import LayoutObject
from django.template.loader import render_to_string


class ActiveToggleMetadata(LayoutObject):
    template = "opportunity/partials/active_toggle_metadata.html"

    def __init__(self, latest_active_event):
        self.latest_active_event = latest_active_event

    def render(self, *args, **kwargs):
        return render_to_string(
            self.template,
            {"latest_active_event": self.latest_active_event},
        )
