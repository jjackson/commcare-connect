from django.apps import AppConfig


class MultidbConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "commcare_connect.multidb"
