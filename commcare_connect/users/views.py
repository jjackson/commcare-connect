from django.contrib.auth import get_user_model
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.messages.views import SuccessMessageMixin
from django.http import HttpResponse
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.utils.translation import gettext_lazy as _
from django.views.decorators.csrf import csrf_exempt
from django.views.generic import DetailView, RedirectView, UpdateView, View
from oauth2_provider.views.mixins import ClientProtectedResourceMixin
from oauth2_provider.contrib.rest_framework import OAuth2Authentication
from rest_framework import parsers, status
from rest_framework.decorators import api_view, authentication_classes

from .models import ConnectIDUserLink

User = get_user_model()


class UserDetailView(LoginRequiredMixin, DetailView):
    model = User
    slug_field = "id"
    slug_url_kwarg = "id"


user_detail_view = UserDetailView.as_view()


class UserUpdateView(LoginRequiredMixin, SuccessMessageMixin, UpdateView):
    model = User
    fields = ["name"]
    success_message = _("Information successfully updated")

    def get_success_url(self):
        assert self.request.user.is_authenticated  # for mypy to know that the user is authenticated
        return self.request.user.get_absolute_url()

    def get_object(self):
        return self.request.user


user_update_view = UserUpdateView.as_view()


class UserRedirectView(LoginRequiredMixin, RedirectView):
    permanent = False

    def get_redirect_url(self):
        organization = self.request.org
        if organization:
            return reverse("opportunity:list", kwargs={"org_slug": organization.slug})
        return reverse("users:detail", kwargs={"pk": self.request.user.pk})


user_redirect_view = UserRedirectView.as_view()


@method_decorator(csrf_exempt, name="dispatch")
class CreateUserLinkView(ClientProtectedResourceMixin, View):
    def post(self, request):
        commcare_username = request.POST.get("commcare_username")
        connect_username = request.POST.get("connect_username")
        if not commcare_username or not connect_username:
            return HttpResponse("commcare_username and connect_username required", status=400)
        try:
            user = User.objects.get(username=connect_username)
        except User.DoesNotExist:
            return HttpResponse("connect user does not exist", status=400)
        user_link, new = ConnectIDUserLink.objects.get_or_create(commcare_username=commcare_username, user=user)
        if new:
            return HttpResponse(status=201)
        else:
            return HttpResponse(status=200)


create_user_link_view = CreateUserLinkView.as_view()


@csrf_exempt
@api_view(['POST'])
@authentication_classes([OAuth2Authentication])
def create_hq_user(request):
    opportunity = request.POST.get("opportunity")
    app = request.POST.get("app")
    if app is None or opportunity is None:
        return HttpResponse("app and opportunity required", status=400)
    api_key = Opportunity.objects.get(pk=opportunity).api_key
    if api_key is None:
        return HttpResponse("Opportunity requires API Key", status=400)
    domain = CommCareApp.objects.get(pk=app).cc_domain
    mobile_worker_api_url = f"{settings.COMMCARE_HQ_URL}/a/{domain}/api/v0.5/user"
    hq_request  = requests.post(mobile_worker_api_url,
                                data={
                                    "username": request.user.username,
                                    "connect_user": request.user.username,
                                },
                                headers={"Authorization": f"ApiKey {api_key.user.email}:{api_key.api_key}"}
                                )
    if hq_request.status_code == 201:
        ConnectIDUserLink.objects.create(commcare_username=request.user.username, user=request.user)
        return HttpResponse(status=200)
    return HttpResponse(status=400)
