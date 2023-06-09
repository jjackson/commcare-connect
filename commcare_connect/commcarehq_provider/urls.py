from allauth.socialaccount.providers.oauth2.urls import default_urlpatterns

from .provider import CommcareHQProvider

urlpatterns = default_urlpatterns(CommcareHQProvider)
