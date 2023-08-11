from django.contrib import messages
from django.http import HttpResponseRedirect
from django.utils.safestring import mark_safe

from commcare_connect.utils.commcarehq_api import CommCareTokenException

API_KEY_ERROR = """
    Unable to retrieve applications from CommCare HQ.<br>
    Please re-login using CommCare HQ or add a <a href="{url}">CommCare API Key</a>.
"""


class CustomErrorHandlingMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, *args, **kwargs):
        return self.get_response(*args, **kwargs)

    def process_exception(self, request, exception):
        if isinstance(exception, CommCareTokenException):
            api_url = "#"  # TODO: make this a real URL
            messages.error(request, mark_safe(API_KEY_ERROR.format(url=api_url)))
            return HttpResponseRedirect(request.headers["referer"])
