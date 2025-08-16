from django.shortcuts import get_object_or_404, redirect, render
from django.views.generic import ListView, DetailView, CreateView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Q, Count
from django.utils import timezone
from django.urls import reverse_lazy, reverse
from django.forms import modelformset_factory
from django.core.mail import send_mail
from django.conf import settings
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_exempt
from django.core.files.storage import default_storage
from django.core.exceptions import PermissionDenied
import json
import os

from .models import Solicitation, SolicitationType, SolicitationResponse, SolicitationQuestion, ResponseStatus, ResponseAttachment
from .forms import SolicitationResponseForm
from commcare_connect.users.models import User
from commcare_connect.organization.models import Organization


class PublicSolicitationListView(ListView):
    """
    Public list view of all publicly listed solicitations
    Beautiful donor-facing page
    """
    model = Solicitation
    template_name = 'solicitations/public_list.html'
    context_object_name = 'solicitations'
    paginate_by = 12

    def get_queryset(self):
        # Only show publicly listed and active solicitations
        queryset = Solicitation.objects.filter(
            is_publicly_listed=True,
            status='active'
        ).select_related(
            'program',
            'program__organization'
        ).annotate(
            total_responses=Count('responses')
        )

        # Filter by type if specified
        solicitation_type = self.kwargs.get('type')
        if solicitation_type in ['eoi', 'rfp']:
            queryset = queryset.filter(solicitation_type=solicitation_type)

        # Search functionality
        search = self.request.GET.get('search')
        if search:
            queryset = queryset.filter(
                Q(title__icontains=search) |
                Q(description__icontains=search) |
                Q(target_population__icontains=search) |
                Q(program__name__icontains=search)
            )

        return queryset.order_by('-date_created')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Add filter information
        context['current_type'] = self.kwargs.get('type', 'all')
        context['search_query'] = self.request.GET.get('search', '')
        
        # Add summary statistics for the page
        context['total_active'] = Solicitation.objects.filter(
            is_publicly_listed=True,
            status='active'
        ).count()
        
        context['eoi_count'] = Solicitation.objects.filter(
            is_publicly_listed=True,
            status='active',
            solicitation_type='eoi'
        ).count()
        
        context['rfp_count'] = Solicitation.objects.filter(
            is_publicly_listed=True,
            status='active',
            solicitation_type='rfp'
        ).count()
        
        return context


class PublicSolicitationDetailView(DetailView):
    """
    Public detail view of a specific solicitation
    Accessible even if not publicly listed (via direct URL)
    """
    model = Solicitation
    template_name = 'solicitations/public_detail.html'
    context_object_name = 'solicitation'

    def get_queryset(self):
        # Allow access to any solicitation via direct URL
        # but must be active status
        return Solicitation.objects.filter(
            status='active'
        ).select_related(
            'program',
            'program__organization'
        ).prefetch_related(
            'questions'
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Add deadline information
        solicitation = self.object
        today = timezone.now().date()
        
        if solicitation.application_deadline:
            days_remaining = (solicitation.application_deadline - today).days
            context['days_remaining'] = max(0, days_remaining)
            context['deadline_passed'] = days_remaining < 0
        
        # Add questions for display
        context['questions'] = solicitation.questions.all().order_by('order')
        
        # Add related solicitations (same program, different type)
        context['related_solicitations'] = Solicitation.objects.filter(
            program=solicitation.program,
            is_publicly_listed=True,
            status='active'
        ).exclude(
            pk=solicitation.pk
        )[:3]
        
        # Check for existing draft if user is authenticated and has organization
        context['has_draft'] = False
        context['has_submitted_response'] = False
        
        if self.request.user.is_authenticated and self.request.user.memberships.exists():
            user_org = self.request.user.memberships.first().organization
            
            # Check for existing draft
            draft = SolicitationResponse.objects.filter(
                solicitation=solicitation,
                organization=user_org,
                status=ResponseStatus.DRAFT
            ).first()
            
            if draft:
                context['has_draft'] = True
                context['draft'] = draft
            
            # Check for submitted response
            submitted_response = SolicitationResponse.objects.filter(
                solicitation=solicitation,
                organization=user_org,
                status__in=[ResponseStatus.SUBMITTED, 
                           ResponseStatus.UNDER_REVIEW,
                           ResponseStatus.ACCEPTED,
                           ResponseStatus.REJECTED,
                           ResponseStatus.PROGRESSED_TO_RFP]
            ).first()
            
            if submitted_response:
                context['has_submitted_response'] = True
                context['submitted_response'] = submitted_response
        
        return context


# Type-specific views that inherit from the main list view
class PublicEOIListView(PublicSolicitationListView):
    """EOI-specific list view"""
    
    def get_queryset(self):
        return super().get_queryset().filter(solicitation_type='eoi')


class PublicRFPListView(PublicSolicitationListView):
    """RFP-specific list view"""
    
    def get_queryset(self):
        return super().get_queryset().filter(solicitation_type='rfp')


# Phase 2: Authenticated Response Submission Views

class SolicitationResponseCreateView(LoginRequiredMixin, CreateView):
    """
    Authenticated view for submitting responses to solicitations
    Requires user authentication and organization membership
    """
    model = SolicitationResponse
    form_class = SolicitationResponseForm
    template_name = 'solicitations/response_form.html'
    
    def dispatch(self, request, *args, **kwargs):
        # First, let LoginRequiredMixin handle authentication
        if not request.user.is_authenticated:
            return super().dispatch(request, *args, **kwargs)
        
        self.solicitation = get_object_or_404(Solicitation, pk=kwargs['pk'])
        
        # Check if solicitation accepts responses
        if not self.solicitation.can_accept_responses:
            messages.error(request, "This solicitation is not currently accepting responses.")
            return redirect('solicitations:detail', pk=self.solicitation.pk)
        
        # Check if user has organization membership
        if not request.user.memberships.exists():
            return render(request, 'solicitations/organization_required.html', {
                'solicitation': self.solicitation
            })
        
        # Check if organization already submitted a response (not draft)
        user_org = request.user.memberships.first().organization
        existing_submitted_response = SolicitationResponse.objects.filter(
            solicitation=self.solicitation,
            organization=user_org,
            status__in=[ResponseStatus.SUBMITTED, 
                       ResponseStatus.UNDER_REVIEW,
                       ResponseStatus.ACCEPTED,
                       ResponseStatus.REJECTED,
                       ResponseStatus.PROGRESSED_TO_RFP]
        ).first()
        
        if existing_submitted_response:
            messages.warning(
                request,
                f"Your organization has already submitted a response on {existing_submitted_response.submission_date.strftime('%B %d, %Y')}."
            )
            return redirect('solicitations:detail', pk=self.solicitation.pk)
        
        # Check if there's an existing draft
        self.existing_draft = SolicitationResponse.objects.filter(
            solicitation=self.solicitation,
            organization=user_org,
            status=ResponseStatus.DRAFT
        ).first()
        
        return super().dispatch(request, *args, **kwargs)
    
    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['solicitation'] = self.solicitation
        kwargs['user'] = self.request.user
        
        # Check if this is a draft save
        if self.request.method == 'POST':
            kwargs['is_draft_save'] = self.request.POST.get('action') == 'save_draft'
        else:
            kwargs['is_draft_save'] = False
        
        # If there's an existing draft, load it for editing
        if hasattr(self, 'existing_draft') and self.existing_draft:
            kwargs['instance'] = self.existing_draft
        
        return kwargs
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['solicitation'] = self.solicitation
        context['questions'] = SolicitationQuestion.objects.filter(
            solicitation=self.solicitation
        ).order_by('order')
        context['is_editing_draft'] = hasattr(self, 'existing_draft') and self.existing_draft
        if context['is_editing_draft']:
            context['draft'] = self.existing_draft
            # Add existing attachments for the draft
            context['existing_attachments'] = self.existing_draft.file_attachments.all()
        else:
            context['existing_attachments'] = []
        return context
    
    def form_valid(self, form):
        response = form.save()
        
        # Check if this is a draft save or final submission
        if self.request.POST.get('action') == 'save_draft':
            # Keep as draft
            response.status = ResponseStatus.DRAFT
            response.save(update_fields=['status', 'responses'])
            
            messages.success(
                self.request,
                f"Your draft response to '{self.solicitation.title}' has been saved!"
            )
            
            return redirect('solicitations:respond', pk=self.solicitation.pk)
        else:
            # Submit the response
            response.status = ResponseStatus.SUBMITTED
            response.save(update_fields=['status', 'responses'])
            
            # Send email notification to program managers
            self._send_notification_email(response)
            
            messages.success(
                self.request,
                f"Your response to '{self.solicitation.title}' has been submitted successfully!"
            )
            
            return redirect('solicitations:response_success', pk=response.pk)
    
    def _send_notification_email(self, response):
        """Send email notification to program managers"""
        try:
            program_managers = self.solicitation.program.organization.members.filter(
                organizationusermembership__role__in=['admin', 'program_manager']
            )
            
            if program_managers.exists():
                recipient_emails = [user.email for user in program_managers if user.email]
                
                if recipient_emails:
                    subject = f"New Response Submitted: {self.solicitation.title}"
                    message = f"""
A new response has been submitted for the solicitation "{self.solicitation.title}".

Organization: {response.organization.name}
Submitted by: {response.submitted_by.get_full_name()} ({response.submitted_by.email})
Submission date: {response.submission_date.strftime('%B %d, %Y at %I:%M %p')}

Please log in to review the response.
                    """
                    
                    send_mail(
                        subject=subject,
                        message=message,
                        from_email=settings.DEFAULT_FROM_EMAIL,
                        recipient_list=recipient_emails,
                        fail_silently=True
                    )
        except Exception:
            # Don't fail the response submission if email fails
            pass


class ResponseSuccessView(LoginRequiredMixin, DetailView):
    """
    Success page after submitting a response
    """
    model = SolicitationResponse
    template_name = 'solicitations/response_success.html'
    context_object_name = 'response'
    
    def get_queryset(self):
        # Only allow users to view their own organization's responses
        if self.request.user.memberships.exists():
            user_org = self.request.user.memberships.first().organization
            return SolicitationResponse.objects.filter(organization=user_org)
        return SolicitationResponse.objects.none()


@login_required
@require_POST
def save_draft_ajax(request, pk):
    """
    AJAX endpoint for saving draft responses
    """
    try:
        solicitation = get_object_or_404(Solicitation, pk=pk)
        
        # Check if user has organization membership
        if not request.user.memberships.exists():
            return JsonResponse({'error': 'Organization membership required'}, status=403)
        
        user_org = request.user.memberships.first().organization
        
        # Get or create draft
        draft, created = SolicitationResponse.objects.get_or_create(
            solicitation=solicitation,
            organization=user_org,
            status=ResponseStatus.DRAFT,
            defaults={
                'submitted_by': request.user,
                'responses': {}
            }
        )
        
        # Update draft with form data (no validation needed for drafts)
        form_data = json.loads(request.body)
        draft.responses = form_data.get('responses', {})
        draft.save(update_fields=['responses', 'date_modified'])
        
        return JsonResponse({
            'success': True,
            'message': 'Draft saved successfully',
            'draft_id': draft.pk
        })
        
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@login_required
@require_POST
def upload_attachment(request, pk):
    """
    Standard Django file upload endpoint (following opportunity app pattern)
    """
    solicitation = get_object_or_404(Solicitation, pk=pk)
    
    # Check user has organization membership
    if not request.user.memberships.exists():
        messages.error(request, "Organization membership required")
        return redirect('solicitations:respond', pk=pk)
        
    user_org = request.user.memberships.first().organization
    
    # Get or create draft response
    draft, created = SolicitationResponse.objects.get_or_create(
        solicitation=solicitation,
        organization=user_org,
        status=ResponseStatus.DRAFT,
        defaults={'submitted_by': request.user, 'responses': {}}
    )
    
    # Handle file upload
    uploaded_file = request.FILES.get('attachment')
    if not uploaded_file:
        messages.error(request, "No file provided")
        return redirect('solicitations:respond', pk=pk)
    
    # Validate file size (10MB limit)
    max_size = 10 * 1024 * 1024  # 10MB
    if uploaded_file.size > max_size:
        messages.error(request, "File too large. Maximum size is 10MB.")
        return redirect('solicitations:respond', pk=pk)
    
    # Validate file type
    allowed_extensions = ['.pdf', '.doc', '.docx', '.xls', '.xlsx', '.jpg', '.jpeg', '.png']
    file_extension = os.path.splitext(uploaded_file.name)[1].lower()
    if file_extension not in allowed_extensions:
        messages.error(request, f"File type not allowed. Allowed types: {', '.join(allowed_extensions)}")
        return redirect('solicitations:respond', pk=pk)
    
    # Create attachment using the standard pattern
    try:
        attachment = ResponseAttachment.objects.create(
            response=draft,
            file=uploaded_file,
            original_filename=uploaded_file.name,
            file_size=uploaded_file.size,
            uploaded_by=request.user
        )
        messages.success(request, f"File '{uploaded_file.name}' uploaded successfully")
    except Exception as e:
        messages.error(request, f"Failed to upload file: {str(e)}")
    
    return redirect('solicitations:respond', pk=pk)


@login_required
@require_POST  
def delete_attachment(request, pk, attachment_id):
    """
    Standard Django file deletion endpoint
    """
    solicitation = get_object_or_404(Solicitation, pk=pk)
    attachment = get_object_or_404(ResponseAttachment, pk=attachment_id)
    
    # Check permissions - user must be the uploader or in same org
    if (attachment.uploaded_by != request.user and 
        not request.user.memberships.filter(organization=attachment.response.organization).exists()):
        messages.error(request, "You don't have permission to delete this file")
        return redirect('solicitations:respond', pk=pk)
    
    try:
        filename = attachment.original_filename
        attachment.delete()
        messages.success(request, f"File '{filename}' deleted successfully")
    except Exception as e:
        messages.error(request, f"Failed to delete file: {str(e)}")
    
    return redirect('solicitations:respond', pk=pk)


class UserDraftListView(LoginRequiredMixin, ListView):
    """
    View to list user's draft responses
    """
    model = SolicitationResponse
    template_name = 'solicitations/draft_list.html'
    context_object_name = 'drafts'
    
    def get_queryset(self):
        if not self.request.user.memberships.exists():
            return SolicitationResponse.objects.none()
        
        user_org = self.request.user.memberships.first().organization
        return SolicitationResponse.objects.filter(
            organization=user_org,
            status=ResponseStatus.DRAFT
        ).order_by('-date_modified')

