# Agent Guidelines for CommCare Connect Labs

## Data Access Architecture

### Critical: No Direct Database Access to Production Data

The labs environment does **NOT** have direct database access to CommCare Connect production data. All production data must be retrieved through the **Data Export APIs**.

### Data Export API Endpoints

Base URL: Configured via `settings.CONNECT_PRODUCTION_URL`

**Authentication:** OAuth Bearer token with `export` scope

#### Key Endpoints:

1. **List Opportunities, Organizations, Programs**

   - `GET /export/opp_org_program_list/`
   - Returns JSON with `opportunities`, `organizations`, and `programs` arrays
   - Opportunity fields: `id`, `name`, `date_created`, `organization` (slug), `end_date`, `is_active`, `program`, `visit_count`, `org_pay_per_visit`
   - **Note:** Does NOT include `learn_app` or `deliver_app` - use the details endpoint for app info

2. **Opportunity Details**

   - `GET /export/opportunity/<opp_id>/`
   - Returns full opportunity details including `learn_app` and `deliver_app` with nested CommCareApp info
   - CommCareApp fields: `cc_domain`, `cc_app_id`, `name`, `hq_server` (nested with `url`)

3. **Opportunity-scoped Data** (CSV streams)
   - `/export/opportunity/<opp_id>/user_data/`
   - `/export/opportunity/<opp_id>/user_visits/`
   - `/export/opportunity/<opp_id>/completed_works/`
   - `/export/opportunity/<opp_id>/payment/`
   - `/export/opportunity/<opp_id>/invoice/`
   - `/export/opportunity/<opp_id>/assessment/`
   - `/export/opportunity/<opp_id>/completed_module/`

### Example API Client Pattern

See `commcare_connect/tasks/data_access.py` for the `TaskDataAccess` class pattern:

```python
class TaskDataAccess:
    def __init__(self, access_token: str, ...):
        self.access_token = access_token
        self.production_url = settings.CONNECT_PRODUCTION_URL.rstrip("/")
        self.http_client = httpx.Client(
            headers={"Authorization": f"Bearer {self.access_token}"},
            timeout=120.0,
        )

    def _call_connect_api(self, endpoint: str) -> httpx.Response:
        url = f"{self.production_url}{endpoint}"
        return self.http_client.get(url)
```

### OAuth Token Access

Labs views can access OAuth tokens from the session:

- `request.session.get("labs_oauth")` - Labs OAuth token data
- Token must have `export` scope for data export API access

### When Building Labs Features

1. Never query Django ORM models directly expecting production data
2. Always use the data export APIs to fetch opportunity/organization/program data
3. Use the existing `TaskDataAccess` or similar patterns for API calls
4. Handle API errors gracefully (timeouts, auth failures, etc.)
