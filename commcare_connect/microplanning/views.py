from django.shortcuts import render


def microplanning_home(request, org_slug):
    return render(request, template_name="microplanning/home.html")
