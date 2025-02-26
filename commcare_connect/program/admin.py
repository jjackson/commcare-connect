from django.contrib import admin

from commcare_connect.program.models import Program


@admin.register(Program)
class ProgramAdmin(admin.ModelAdmin):
    list_display = ("name", "organization")  # Display program name and organization in the list
