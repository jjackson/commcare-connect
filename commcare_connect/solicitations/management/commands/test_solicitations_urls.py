"""
Management command to test all solicitations URLs.
Run with: python manage.py test_solicitations_urls
"""
from commcare_connect.labs.management.commands.base_labs_url_test import BaseLabsURLTest


class Command(BaseLabsURLTest):
    help = "Test all solicitations URLs"

    project_name = "solicitations"
    base_urls = [
        "/solicitations/",
        "/solicitations/manage/",
        "/solicitations/opportunities/",
        "/solicitations/responses/",
    ]
