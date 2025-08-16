# EOI Implementation Plan - CommCare Connect

## Goal

Build new web pages for **CommCare Connect** that support a two-phase procurement process:

1. **Expression of Interest (EOI)** - Initial screening phase
2. **Request for Proposal (RFP)** - Detailed proposal phase for EOI winners

**Key Features**:
1. **Program-owned Solicitations**: Programs can create and publish EOIs/RFPs
2. **Public Viewing**: Beautiful public pages to showcase active solicitations (for donors/stakeholders)
3. **Authenticated Responses**: Organizations submit responses on behalf of their org
4. **Flexible Review Process**: Admin ability to review, score, and progress responses
5. **Two-Phase Workflow**: EOI → RFP → Opportunity (final phase out of scope).  Some RFPs may not require EOIs.

## Implementation Notes

- **First-time contributor**: This is the contributor's first PR to Connect codebase
- **Clean approach**: Implementation should be extremely clean and isolated
- **Limited scope**: PR should only touch areas directly related to EOI/RFP functionality
- **Donor-facing**: Public pages must look extremely professional for donor presentations

## Core Data Models

### 1. Solicitation (unified model for EOI/RFP)
- `title` - Name of the solicitation
- `description` - Rich text description of the program
- `target_population` - Who will be served
- `scope_of_work` - What work needs to be done
- `expected_start_date` / `expected_end_date` - Timeline
- `estimated_scale` - Number of beneficiaries/FLWs
- `application_deadline` - When responses are due
- `solicitation_type` - 'eoi' or 'rfp'
- `status` - draft, active, completed, closed
- `is_publicly_listed` - Boolean to control public listing visibility
- `program` - Foreign key to Program (owner)
- `created_by` - Admin who created it
- `parent_solicitation` - Self-referencing FK (RFP references parent EOI)
- `attachments` - File field for supporting documents

### 2. SolicitationResponse
- `solicitation` - Foreign key to Solicitation
- `organization` - Foreign key to Organization (responding org)
- `submitted_by` - User who submitted the response
- `submission_date` - When submitted
- `responses` - JSON field for flexible question/answer storage
- `attachments` - File field for supporting documents
- `status` - submitted, under_review, accepted, rejected, progressed_to_rfp
- `progressed_to_solicitation` - FK to RFP if EOI response was accepted

### 3. SolicitationReview (for admin scoring)
- `response` - Foreign key to SolicitationResponse
- `reviewer` - Admin doing the review
- `score` - Numeric score
- `tags` - Text field for tags
- `notes` - Review notes
- `review_date` - When reviewed
- `recommendation` - accept, reject, needs_more_info

### 4. SolicitationQuestion (for flexible forms)
- `solicitation` - Foreign key to Solicitation
- `question_text` - The question
- `question_type` - text, textarea, number, file, multiple_choice
- `is_required` - Boolean
- `options` - JSON field for multiple choice options
- `order` - Display order

## Implementation Phases

### Phase 1: Public Solicitation Viewing (Start Here)
**Goal**: Beautiful public pages to showcase active EOIs/RFPs (donor-facing)

**Implementation**:
- Create new Django app: `commcare_connect/solicitations/`
- Add public URLs outside org-specific paths (e.g., `/solicitations/`)
- Create core models with unified Solicitation model
- Build stunning public list and detail views
- Create professional templates with modern design
- Support both EOI and RFP types in same views

**Key Features**:
- Filter by type (EOI vs RFP)
- Status-based visibility (active vs completed)
- Direct URL access for non-publicly-listed items
- File attachment display
- Professional design suitable for donor presentations

### Phase 2: Authenticated Response Submission
**Goal**: Allow authenticated organization users to submit responses

**Implementation**:
- Require user authentication and organization membership
- Create flexible response forms based on SolicitationQuestion
- Support file uploads for supporting documents
- Build confirmation and thank you pages
- Add email notifications on submission
- Validate user has organization membership

**Key Features**:
- Dynamic form generation from questions
- File upload support
- Organization context validation
- Email notifications to program managers

### Phase 3: Admin Review Interface
**Goal**: Program managers can review, score, and progress responses

**Implementation**:
- Add review models and forms within program structure
- Create program manager dashboard for solicitations
- Build individual response review pages
- Add scoring, tagging, and progression workflow
- Support EOI → RFP progression workflow

**Key Features**:
- Review dashboard showing all responses
- Individual response review with scoring
- Bulk actions for common operations
- EOI acceptance → RFP creation workflow

### Phase 4: Admin Solicitation Authoring
**Goal**: Program managers can create and publish EOIs/RFPs

**Implementation**:
- Create solicitation creation and editing forms
- Add rich text editor for descriptions
- Build draft/publish workflow with visibility controls
- Add dynamic question builder
- Support file attachments

**Key Features**:
- WYSIWYG editor for descriptions
- Dynamic question builder interface
- Draft/active/completed status management
- Public listing toggle
- File attachment management

## Technical Approach

### App Structure
```
commcare_connect/solicitations/
├── __init__.py
├── admin.py
├── apps.py
├── models.py
├── views.py
├── urls.py
├── forms.py
├── tasks.py               # For email notifications
├── migrations/
└── tests/
```

### URL Structure
```
# Public URLs (no auth required - donor-facing)
/solicitations/                    # List all publicly listed solicitations
/solicitations/eoi/                # Filter to EOIs only
/solicitations/rfp/                # Filter to RFPs only
/solicitations/<int:pk>/           # Solicitation detail view (works for unlisted too)
/solicitations/<int:pk>/respond/   # Response submission form (auth required)

# Program Manager URLs (within org structure)
/a/<org_slug>/program/<int:program_id>/solicitations/           # Program solicitation dashboard
/a/<org_slug>/program/<int:program_id>/solicitations/create/    # Create new solicitation
/a/<org_slug>/program/<int:program_id>/solicitations/<pk>/edit/ # Edit solicitation
/a/<org_slug>/program/<int:program_id>/solicitations/<pk>/responses/ # View responses
/a/<org_slug>/program/<int:program_id>/solicitations/response/<pk>/review/ # Review response
/a/<org_slug>/program/<int:program_id>/solicitations/<pk>/create-rfp/ # Create RFP from EOI
```

### Template Structure
```
commcare_connect/templates/solicitations/
├── public_base.html              # Donor-facing base template (professional)
├── public_list.html              # Public solicitation list (beautiful)
├── public_detail.html            # Public solicitation detail (professional)
├── response_form.html            # Response submission form
├── response_success.html         # Thank you page
├── program_manager/
│   ├── dashboard.html           # Program manager solicitation dashboard
│   ├── create_solicitation.html # Create solicitation form
│   ├── edit_solicitation.html   # Edit solicitation form
│   ├── responses_list.html      # List responses for a solicitation
│   ├── review_response.html     # Review individual response
│   └── create_rfp.html          # Create RFP from accepted EOI
```

### Integration Points

**Program Integration**:
- Solicitations are owned by Programs
- Program managers can create/manage solicitations
- Follows existing program permission patterns

**Organization Integration**:
- Responses require organization membership
- Users respond on behalf of their organization
- Uses existing organization models and permissions

**User Integration**:
- Authentication required for responses
- Uses existing user/organization membership system
- Email notifications via existing task system

**File Management**:
- Support file attachments for both solicitations and responses
- Uses Django's file handling system
- Proper security for file access

## Key Design Decisions (Based on Clarifications)

1. **Authentication**: ✅ Users must be authenticated and respond on behalf of their organization
2. **Ownership**: ✅ Solicitations are owned by Programs (not individual orgs)
3. **Flexibility**: ✅ Custom questions per solicitation (with standardization goal)
4. **Visibility**: ✅ Two toggles - status (draft/active/completed) and public listing (yes/no)
5. **File uploads**: ✅ Support for both solicitations and responses
6. **Notifications**: ✅ Email notifications on response submission
7. **Two-phase process**: ✅ EOI → RFP → Opportunity workflow
8. **Unified model**: ✅ Same data structure for EOI and RFP (different labels)
9. **Donor presentation**: ✅ Public pages must be extremely professional

## Workflow Summary

```
Program Manager creates EOI → Publishes (with visibility controls)
↓
Organizations view public EOI → Authenticated users submit responses
↓
Program Manager reviews responses → Accepts some for RFP phase
↓
Program Manager creates RFP for accepted orgs → RFP response process
↓
Program Manager reviews RFP responses → Creates Opportunities (out of scope)
```

## Next Steps

This plan provides a comprehensive foundation for implementing the EOI/RFP system. The phased approach allows for:

1. **Quick wins** with public viewing (donor-facing showcase)
2. **Iterative development** of the response and review system
3. **Clean integration** with existing Program and Organization models
4. **Professional presentation** suitable for donor/stakeholder viewing

The unified Solicitation model supports both EOI and RFP phases while maintaining clean separation of concerns and following existing CommCare Connect patterns.

## Implementation Progress (Current Status)

### ✅ COMPLETED - Phase 1: Public Solicitation Viewing
**Goal**: Beautiful donor-facing public pages to showcase active EOIs/RFPs

**What's Done**:
- ✅ Created complete Django app: `commcare_connect/solicitations/`
- ✅ Implemented all core models:
  - `Solicitation` (unified EOI/RFP model)
  - `SolicitationQuestion` (flexible forms)
  - `SolicitationResponse` (ready for Phase 2)
  - `SolicitationReview` (ready for Phase 3)
- ✅ Built beautiful public views:
  - `PublicSolicitationListView` with filtering and search
  - `PublicSolicitationDetailView` with professional layout
  - Type-specific views for EOI/RFP filtering
- ✅ Created professional donor-facing templates:
  - Modern card-based grid layout
  - Responsive design with professional styling
  - Search and filter functionality
  - Detailed solicitation pages with timelines
- ✅ Configured URLs: `/solicitations/`, `/solicitations/eoi/`, `/solicitations/rfp/`
- ✅ Added to Django settings and main URL config
- ✅ Created comprehensive tests and factories
- ✅ Built Django admin interface
- ✅ Database migrations completed

**URLs Ready for Testing**:
- http://localhost:8000/solicitations/ (all opportunities)
- http://localhost:8000/solicitations/eoi/ (EOIs only)
- http://localhost:8000/solicitations/rfp/ (RFPs only)
- http://localhost:8000/solicitations/<id>/ (individual solicitation)

### ✅ COMPLETED - Sample Data & Initial Testing
**What's Done**:
- ✅ Fixed Django management command `create_sample_solicitations`
  - Resolved `TypeError` with `fake.future_date()` method
  - Fixed `AttributeError` with model property conflicts
  - Fixed `FieldError` with incorrect `select_related()` calls
- ✅ Successfully generated sample data with realistic solicitations
- ✅ All public pages working correctly:
  - List view showing multiple opportunities
  - Detail views with full solicitation information
  - Filtering by EOI/RFP types working
  - Search functionality operational

### ✅ COMPLETED - Phase 2: Authenticated Response Submission
**Goal**: Allow authenticated organization users to submit responses

**What's Done**:
- ✅ **Authentication & Authorization**: 
  - Implemented `LoginRequiredMixin` for secure access
  - Added organization membership validation
  - Prevent duplicate submissions from same organization
- ✅ **Dynamic Response Forms**: 
  - Created `SolicitationResponseForm` with dynamic field generation
  - Support for all question types: text, textarea, number, file, multiple_choice
  - Form validation and error handling
- ✅ **File Upload Support**: 
  - Multiple file attachment support for supporting documents
  - Proper file handling and security
- ✅ **Email Notifications**: 
  - Automatic email notifications to program managers on submission
  - Includes submission details and organization information
- ✅ **User Experience**: 
  - Beautiful response submission form with clear UI
  - Success page with next steps and submission details
  - Breadcrumb navigation and consistent styling
- ✅ **Templates Created**:
  - `response_form.html` - Dynamic form with solicitation context
  - `response_success.html` - Professional confirmation page
- ✅ **URL Integration**: 
  - `/solicitations/<id>/respond/` - Response submission
  - `/solicitations/response/<id>/success/` - Success confirmation
  - Updated "Submit Response" button with proper linking

**URLs Ready for Testing**:
- http://localhost:8000/solicitations/<id>/respond/ (authenticated response submission)
- http://localhost:8000/solicitations/response/<id>/success/ (success page)

### ✅ COMPLETED - Final Phase 2 Fixes
**Focus**: Draft validation and user experience improvements
- ✅ Fixed draft validation issue - required fields can now be left empty when saving drafts
- ✅ Implemented simple HTML5 validation bypass with `novalidate` attribute
- ✅ Added client-side validation for final submissions only
- ✅ Enhanced visual feedback with notifications and field highlighting
- ✅ Simplified JavaScript approach for better reliability

### 🔄 CURRENTLY WORKING ON: Phase 3 - Admin Review Interface
**Goal**: Program managers can review, score, and progress responses

**Phase 3 Requirements**:
- Add review models and forms within program structure
- Create program manager dashboard for solicitations
- Build individual response review pages
- Add scoring, tagging, and progression workflow
- Support EOI → RFP progression workflow

**Key Features to Implement**:
- Review dashboard showing all responses
- Individual response review with scoring
- Bulk actions for common operations
- EOI acceptance → RFP creation workflow

### 📋 NEXT PHASES (Ready to Begin After Phase 3):
- **Phase 4**: Admin Solicitation Authoring

**Status**: Phase 1 & 2 are 100% complete and fully functional. Public viewing with beautiful donor-facing pages, authenticated response submission with email notifications, and draft validation are all working perfectly. Now beginning Phase 3 (Admin Review Interface).
