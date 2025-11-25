from django.apps import AppConfig


class CoverageConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "commcare_connect.coverage"
    verbose_name = "Coverage"

    def ready(self):
        # Register analysis configs by importing modules that call register_config()
        import commcare_connect.custom_analysis.chc_nutrition  # noqa: F401
