from pathlib import Path

from django.conf import settings
from django.http import HttpResponse
from django.views import View

# The marketing page is plain static HTML imported from
# dimagi-internal/connect-prelogin and lives under static/prelogin/.
# We swap one placeholder at request time so the Login CTA can be retargeted
# per-deploy via PRELOGIN_APP_LOGIN_URL.
_INDEX_HTML = Path(__file__).resolve().parent.parent / "static" / "prelogin" / "index.html"
_LOGIN_PLACEHOLDER = "__APP_LOGIN_URL__"


class HomeView(View):
    def get(self, request):
        login_url = getattr(settings, "PRELOGIN_APP_LOGIN_URL", "/accounts/login/")
        html = _INDEX_HTML.read_text(encoding="utf-8").replace(_LOGIN_PLACEHOLDER, login_url)
        return HttpResponse(html)


home = HomeView.as_view()
