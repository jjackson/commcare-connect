from django.urls import path

from commcare_connect.users.views import (
    create_hq_user,
    create_user_link_view,
    user_detail_view,
    user_redirect_view,
    user_update_view
)

app_name = "users"
urlpatterns = [
    path("redirect/", view=user_redirect_view, name="redirect"),
    path("update/", view=user_update_view, name="update"),
    path("<int:pk>/", view=user_detail_view, name="detail"),
    path("create_user_link/", view=create_user_link_view, name="create_user_link"),
    path("create_hq_user/", view=create_hq_user, name="create_hq_user"),
]
