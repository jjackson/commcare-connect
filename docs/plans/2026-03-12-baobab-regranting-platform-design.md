# Regranting Platform Design

**Date:** 2026-03-12
**Status:** Draft — for review

## Context

A regranting organization wants to use Connect as their platform for managing grants to local organizations. They have:

- An existing **large grant** (regranting to governments and local orgs)
- A **second fund** in late stages (~$500K per grant to local organizations, up to $2.5M direct to governments)

They want an end-to-end demo of how Connect could serve as their regranting platform — posting solicitations, selecting grantees, managing programs, and tracking delivery/payments.

## Design Principles

1. **Product-first** — design real features, not just a demo facade
2. **No core Connect changes** — new concepts live as LabsRecords; production Connect stays untouched
3. **API/MCP-first** — all core objects are CRUD/API/MCP accessible; UI composes them
4. **Leverage existing infrastructure** — user signup, org creation, opportunity management, verification, and payments all exist in production Connect already

## Scope

### In scope (Labs work)

| Module | What |
|--------|------|
| **solicitations_new** (enhance existing) | Solicitation management, response collection, review/scoring, award action |
| **funder_dashboard** (new) | Fund portfolio view, aggregated KPIs, drill-down into programs |

### In scope (Production Connect — minimal changes)

| Area | What |
|------|------|
| **Org creation permission** | Address `WORKSPACE_ENTITY_MANAGEMENT_ACCESS` gate so solicitation respondents can self-create orgs |

### Out of scope

- Platform fee mechanism (business decision, layered on later)
- Delivery flow changes (production Connect as-is)
- Verification flow changes (standard two-tier NM → PM as-is)
- Payment flow changes (Funder → NM → FLWs, existing invoice workflow)
- Workflow template dashboards (future phase — hardcode Django views for now)

## Entity Model

### Existing (Production Connect)

```
Organization (PM: AFC Richmond Foundation)
  → Program (Youth Coaching, Sports Medicine, Community Outreach, etc.)
    → ManagedOpportunity (1 per grantee per program)
      → NM Organization (grantee / local org)
        → FLWs (invited by NM)
```

### New (LabsRecords)

**FundRecord** — groups programs under a single funding source
- `name`, `description`, `total_budget`, `currency`
- `funder_org_id` (references the funder's Connect org)
- `program_ids[]` (references Connect Program IDs)
- `status`: active | closed

**SolicitationRecord** (exists in solicitations_new)
- `fund_id` (reference to FundRecord)
- `program_id` (optional — specific program within fund)
- `title`, `description`, `scope_of_work`
- `solicitation_type`: eoi | rfp
- `status`: draft | active | closed | awarded
- `questions`: JSON array of custom questions
- `application_deadline`, `expected_start_date`, `expected_end_date`
- `estimated_scale`, `contact_email`

**ResponseRecord** (exists in solicitations_new)
- `solicitation_id`, `llo_entity_id`, `llo_entity_name`
- `responses`: dict of question answers
- `status`: draft | submitted | awarded | rejected
- `submitted_by_name`, `submitted_by_email`
- `connect_org_id` (links to respondent's Connect org — populated on account creation)

**ReviewRecord** (exists in solicitations_new)
- `response_id`, `score` (1-100)
- `recommendation`: approved | rejected | needs_revision | under_review
- `notes`, `reviewer_username`

## End-to-End User Journey

### Phase 1: Fund & Solicitation Setup (Funder in Labs)

```
AFC Richmond Foundation logs into Labs
  → Creates FundRecord ("Greyhounds Youth Development Fund")
  → Links existing Connect Programs (Youth Coaching, Sports Medicine, Community Outreach)
  → Creates SolicitationRecord (RFP for Youth Coaching Partners)
    - Defines custom questions (org capacity, geographic coverage, prior experience, proposed budget)
    - Sets deadline, scope of work
  → Publishes solicitation (status: active)
  → Solicitation appears on public listing (no login required)
```

### Phase 2: Response & Self-Registration (Local Org in Connect + Labs)

```
Local org discovers RFP on public solicitation listing
  → Clicks "Submit Response"
  → Redirected to Connect signup (existing allauth flow)
    - Creates account (email, password, name)
    - Verifies email
    - Creates/joins Organization (existing org creation form)
  → Returns to Labs with authenticated session
  → Fills out solicitation response form (custom questions)
  → Submits response
  → ResponseRecord created with connect_org_id linked
```

**Production Connect change needed:** The `WORKSPACE_ENTITY_MANAGEMENT_ACCESS` permission gate on org creation needs to be addressed for solicitation respondents. Options:
1. Auto-grant permission when user arrives from a solicitation link
2. Create a solicitation-specific org creation view that bypasses the gate
3. Remove the gate entirely (if it's no longer needed)

*Open question: What's the intent of the WORKSPACE_ENTITY_MANAGEMENT_ACCESS gate? Is it safe to relax for solicitation respondents?*

### Phase 3: Review & Award (Funder in Labs)

```
Funder views responses in solicitations_new
  → Reviews each response (read answers, org details)
  → Scores responses (1-100 scale)
  → Adds review notes and recommendation
  → Ranks responses
  → Clicks "Award" on selected respondents
```

**Award triggers auto-setup (Labs → Connect API):**
1. Links NM org to the relevant Program (Connect API call)
2. Creates ManagedOpportunity from program template (Connect API call)
3. Allocates budget from fund (Connect API call)
4. Sends notification to NM org admin
5. Updates ResponseRecord status to "awarded"
6. Updates SolicitationRecord status to "awarded" (if all slots filled)

*Open question: What Connect API endpoints exist for programmatically creating ManagedOpportunities and linking orgs to programs? Do we need new API endpoints, or can we use existing ones?*

### Phase 4: Delivery (Production Connect — no Labs work)

```
NM org admin receives notification
  → Logs into production Connect
  → Configures opportunity details (if needed)
  → Invites FLWs via phone numbers (existing flow)
  → FLWs complete learning modules
  → FLWs deliver services
  → Visits flow into Connect via CommCare apps
```

### Phase 5: Verification & Payment (Production Connect — no Labs work)

```
NM reviews visits (tier 1 verification)
  → Funder reviews at PM level (tier 2 verification)
  → NM creates invoices for approved work
  → Funder approves invoices at PM level
  → Funder disburses funds to NM org
  → NM org pays FLWs
```

### Phase 6: Portfolio Monitoring (Funder in Labs)

```
Funder views Funder Dashboard
  → Sees all funds with aggregated KPIs
  → Drills into a fund to see programs, grantees, solicitation status
  → Drills into a program to see detailed delivery/payment stats
  → Tracks disbursements, completion rates, pending actions
```

## Module Design

### 1. solicitations_new (Enhance Existing)

**Existing on fork/labs-main** (~1500 lines, 32 tests passing). Needs:

#### Data model changes
- Add `fund_id` field to SolicitationRecord
- Add `connect_org_id` field to ResponseRecord
- Add `awarded` status to ResponseRecord and SolicitationRecord
- Add `proposed_budget` field to ResponseRecord

#### New: Award flow
- "Award" button on response detail view
- Award action calls Connect API to:
  - Link respondent's org to program
  - Create ManagedOpportunity
  - Allocate budget
- Batch award support (award multiple respondents at once)

#### New: Fund linkage
- Solicitation creation form includes fund selector
- Solicitation list filterable by fund

#### Enhancement: Public views
- Improve public solicitation listing for discoverability
- Add "Apply" CTA that routes through Connect signup if not authenticated
- Mobile-friendly response form

#### API/MCP (already exists, needs updates)
- Add fund-related filters to list endpoints
- Add award endpoint
- Update MCP tools with fund awareness

### 2. funder_dashboard (New Module)

#### FundRecord CRUD
- Create/edit/archive funds
- Link/unlink programs to funds
- API + MCP accessible

#### Portfolio Dashboard View
```
┌─────────────────────────────────────────────────────────────┐
│  AFC RICHMOND FOUNDATION — Funder Dashboard                 │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  Active Funds                                               │
│  ┌─────────────────────┐  ┌─────────────────────┐          │
│  │ Greyhounds Youth Dev │  │ Lasso Legacy Fund   │          │
│  │ $3M budget           │  │ $25M budget          │          │
│  │ 3 programs, 5 grants │  │ 4 programs, 12 grants│          │
│  │ $420K disbursed      │  │ $8.2M disbursed      │          │
│  └─────────────────────┘  └─────────────────────┘          │
│                                                             │
│  Open Solicitations (2)     Pending PM Reviews (7)         │
│                                                             │
│  Recent Activity                                            │
│  - Nelson Road FC submitted invoice #12 — $4,200           │
│  - 3 new responses to "Youth Coaching Partners RFP"        │
│  - Diamond Dogs SC completed 89% of Q1 target              │
└─────────────────────────────────────────────────────────────┘
```

**KPIs per fund:**
- Total budget vs. disbursed
- Number of programs, grantees (NM orgs)
- Active opportunities count
- Open solicitations / pending responses
- Pending PM actions (invoice approvals, visit reviews)

#### Fund Detail View
```
┌─────────────────────────────────────────────────────────────┐
│  Greyhounds Youth Development Fund                         │
├─────────────────────────────────────────────────────────────┤
│  Programs          Grantees   Budget    Disbursed  Status  │
│  ─────────         ────────   ──────    ─────────  ──────  │
│  Youth Coaching     2 orgs    $1.5M    $280K      Active  │
│  Sports Medicine    1 org     $800K    $120K      Active  │
│  Community Outreach 2 orgs    $700K    $20K       Setup   │
│                                                             │
│  Solicitations                                              │
│  - Youth Coaching RFP — Active, 8 responses, deadline Mar 30│
│  - Sports Medicine EOI — Closed, 3 awarded                 │
│                                                             │
│  Pending Actions                                            │
│  - 4 invoices awaiting PM approval                         │
│  - 3 solicitation responses to review                      │
└─────────────────────────────────────────────────────────────┘
```

**Drill-down:** Clicking a program navigates to existing PM views in production Connect (or deep-links).

#### Data sources
- FundRecords, SolicitationRecords → LabsRecord API
- Programs, Opportunities, Payments, Visits → Connect production API
- Aggregation happens in Django views (server-side)

#### API/MCP
- Fund CRUD endpoints
- Portfolio summary endpoint (aggregated KPIs)
- MCP tools for fund management and querying

### 3. Production Connect Changes (Minimal)

#### Org creation permission
- Address `WORKSPACE_ENTITY_MANAGEMENT_ACCESS` gate for solicitation respondents
- Preferred approach TBD (see open question above)

#### API endpoints for award auto-setup
- May need endpoints for: creating ManagedOpportunity, linking org to program, budget allocation
- Or existing endpoints may suffice — needs investigation

## Open Questions

1. **WORKSPACE_ENTITY_MANAGEMENT_ACCESS gate**: What's the original intent? Can we relax it for solicitation respondents, or do we need a dedicated bypass?

2. **ManagedOpportunity creation via API**: Do endpoints exist to programmatically create a ManagedOpportunity and link an NM org to a program? If not, what's the minimal API surface we'd need?

3. **Program templates**: When the funder awards a grantee, the system auto-creates a ManagedOpportunity. What should the "template" for this look like? Is it the Program's existing configuration (learn app, deliver app, payment units), or does the funder configure a template separately?

4. **Multiple programs per solicitation**: Can a single RFP cover multiple program types (e.g., "Apply for Youth Coaching or Sports Medicine"), or is it always one solicitation per program?

5. **Budget allocation on award**: Does the funder set the per-grantee budget during award, or is it predetermined by the solicitation/program?

6. **Funder Dashboard data freshness**: Is it acceptable for the dashboard to show slightly stale data (cached from Connect API), or does it need to be real-time?

7. **Demo content**: Do we need real CommCare apps configured for the demo programs, or can we use placeholder/test programs?

8. **Solicitation visibility**: Should solicitations be discoverable publicly on the internet, or only via direct link sharing? The current design has a public listing page.

## Technical Notes

- All new Labs code builds on the existing solicitations_new foundation (fork/labs-main branch)
- LabsRecordAPIClient handles all LabsRecord CRUD (existing pattern)
- Connect production API accessed via existing HTTP client
- Django templates with Tailwind + Alpine.js + htmx (existing Labs stack)
- MCP tools follow existing pattern in solicitations_new/mcp_tools.py

## Demo Narrative

The demo could walk through the full journey:

1. **"Here's your fund"** — Show Funder Dashboard with the fund and programs configured
2. **"Post a solicitation"** — Create an RFP for partners, define questions, publish
3. **"Local orgs apply"** — Show a local org discovering the RFP, creating an account, submitting a response
4. **"Select your grantees"** — Review responses, score, award winners
5. **"Automatic setup"** — Show how awarding auto-creates the opportunity, links the org, allocates budget
6. **"Grantees deliver"** — Show an NM managing their opportunity, FLWs delivering services (can use pre-loaded data)
7. **"Verify and pay"** — Show two-tier verification, invoice approval, payment tracking
8. **"Monitor everything"** — Return to Funder Dashboard showing real-time portfolio metrics

This tells the complete story of how a funder would use Connect as their regranting platform.
