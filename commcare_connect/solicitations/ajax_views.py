"""
AJAX views for solicitation question management
"""
import json

from django.contrib.auth.decorators import login_required
from django.db import models
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_POST

from .models import Solicitation, SolicitationQuestion


@login_required
@require_POST
def solicitation_question_create(request, org_slug, program_pk, solicitation_pk):
    """
    AJAX endpoint to create a new question for a solicitation
    """
    try:
        solicitation = get_object_or_404(
            Solicitation.objects.select_related("program", "program__organization"),
            pk=solicitation_pk,
            program__pk=program_pk,
            program__organization=request.org,
        )

        data = json.loads(request.body)

        # Get the next order number
        max_order = (
            SolicitationQuestion.objects.filter(solicitation=solicitation).aggregate(models.Max("order"))["order__max"]
            or 0
        )

        question = SolicitationQuestion.objects.create(
            solicitation=solicitation,
            question_text=data.get("question_text", ""),
            question_type=data.get("question_type", "textarea"),
            is_required=data.get("is_required", True),
            options=data.get("options", None),
            order=max_order + 1,
        )

        return JsonResponse(
            {
                "success": True,
                "question": {
                    "id": question.id,
                    "question_text": question.question_text,
                    "question_type": question.question_type,
                    "is_required": question.is_required,
                    "options": question.options,
                    "order": question.order,
                },
            }
        )

    except Exception as e:
        return JsonResponse({"success": False, "error": str(e)}, status=400)


@login_required
@require_POST
def solicitation_question_update(request, org_slug, program_pk, solicitation_pk, question_pk):
    """
    AJAX endpoint to update a question
    """
    try:
        question = get_object_or_404(
            SolicitationQuestion.objects.select_related(
                "solicitation", "solicitation__program", "solicitation__program__organization"
            ),
            pk=question_pk,
            solicitation__pk=solicitation_pk,
            solicitation__program__pk=program_pk,
            solicitation__program__organization=request.org,
        )

        data = json.loads(request.body)

        question.question_text = data.get("question_text", question.question_text)
        question.question_type = data.get("question_type", question.question_type)
        question.is_required = data.get("is_required", question.is_required)
        question.options = data.get("options", question.options)
        question.save()

        return JsonResponse(
            {
                "success": True,
                "question": {
                    "id": question.id,
                    "question_text": question.question_text,
                    "question_type": question.question_type,
                    "is_required": question.is_required,
                    "options": question.options,
                    "order": question.order,
                },
            }
        )

    except Exception as e:
        return JsonResponse({"success": False, "error": str(e)}, status=400)


@login_required
@require_POST
def solicitation_question_delete(request, org_slug, program_pk, solicitation_pk, question_pk):
    """
    AJAX endpoint to delete a question
    """
    try:
        question = get_object_or_404(
            SolicitationQuestion.objects.select_related(
                "solicitation", "solicitation__program", "solicitation__program__organization"
            ),
            pk=question_pk,
            solicitation__pk=solicitation_pk,
            solicitation__program__pk=program_pk,
            solicitation__program__organization=request.org,
        )

        question.delete()

        return JsonResponse({"success": True})

    except Exception as e:
        return JsonResponse({"success": False, "error": str(e)}, status=400)


@login_required
@require_POST
def solicitation_question_reorder(request, org_slug, program_pk, solicitation_pk):
    """
    AJAX endpoint to reorder questions
    """
    try:
        solicitation = get_object_or_404(
            Solicitation.objects.select_related("program", "program__organization"),
            pk=solicitation_pk,
            program__pk=program_pk,
            program__organization=request.org,
        )

        data = json.loads(request.body)
        question_orders = data.get("question_orders", [])

        # Update order for each question
        for item in question_orders:
            question_id = item.get("id")
            new_order = item.get("order")

            SolicitationQuestion.objects.filter(id=question_id, solicitation=solicitation).update(order=new_order)

        return JsonResponse({"success": True})

    except Exception as e:
        return JsonResponse({"success": False, "error": str(e)}, status=400)
