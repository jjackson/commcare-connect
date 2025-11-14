"""
Proxy models for Audit LocalLabsRecords.

These proxy models provide convenient access to LocalLabsRecord data
for the audit workflow. LocalLabsRecord is a transient Python object
that deserializes production API responses - no database storage.
"""

from commcare_connect.labs.models import LocalLabsRecord


class AuditTemplateRecord(LocalLabsRecord):
    """Proxy model for AuditTemplate-type LocalLabsRecords."""

    # Properties for convenient access to template configuration
    @property
    def opportunity_ids(self):
        """List of opportunity IDs to audit."""
        return self.data.get("opportunity_ids", [])

    @property
    def audit_type(self):
        """Audit type: date_range, last_n_per_flw, last_n_per_opp, last_n_across_all."""
        return self.data.get("audit_type", "")

    @property
    def granularity(self):
        """Granularity: combined, per_opp, per_flw."""
        return self.data.get("granularity", "combined")

    @property
    def start_date(self):
        """Start date for date_range audits."""
        return self.data.get("start_date")

    @property
    def end_date(self):
        """End date for date_range audits."""
        return self.data.get("end_date")

    @property
    def count_per_flw(self):
        """Count for last_n_per_flw audits."""
        return self.data.get("count_per_flw")

    @property
    def count_per_opp(self):
        """Count for last_n_per_opp audits."""
        return self.data.get("count_per_opp")

    @property
    def count_across_all(self):
        """Count for last_n_across_all audits."""
        return self.data.get("count_across_all")

    @property
    def sample_percentage(self):
        """Sample percentage (1-100)."""
        return self.data.get("sample_percentage", 100)

    @property
    def preview_data(self):
        """Preview statistics from preview step."""
        return self.data.get("preview_data", [])


class AuditSessionRecord(LocalLabsRecord):
    """Proxy model for AuditSession-type LocalLabsRecords with nested visit results."""

    # Properties for convenient access
    @property
    def title(self):
        """Audit session title."""
        return self.data.get("title", "")

    @property
    def tag(self):
        """Audit session tag."""
        return self.data.get("tag", "")

    @property
    def status(self):
        """Audit status: in_progress or completed."""
        return self.data.get("status", "in_progress")

    @property
    def overall_result(self):
        """Overall result: pass, fail, or None."""
        return self.data.get("overall_result")

    @property
    def notes(self):
        """General audit notes."""
        return self.data.get("notes", "")

    @property
    def kpi_notes(self):
        """KPI-related notes."""
        return self.data.get("kpi_notes", "")

    @property
    def visit_ids(self):
        """List of UserVisit IDs to audit."""
        return self.data.get("visit_ids", [])

    @property
    def opportunity_id(self):
        """Primary opportunity ID for this audit session (the audit target, not Labs storage)."""
        return self.data.get("opportunity_id")

    @opportunity_id.setter
    def opportunity_id(self, value):
        """Allow setting opportunity_id from LocalLabsRecord.__init__."""
        # LocalLabsRecord.__init__ tries to set this from api_data
        # We intercept it here and store in internal attribute
        object.__setattr__(self, "_opportunity_id_from_api", value)

    @property
    def visit_results(self):
        """Dict of visit results keyed by visit_id."""
        return self.data.get("visit_results", {})

    # Helper methods for managing nested visit results
    def get_visit_result(self, visit_id: int) -> dict | None:
        """
        Get result for a specific visit by UserVisit ID.

        Args:
            visit_id: UserVisit ID from Connect

        Returns:
            Dict with xform_id, result, notes, assessments, or None if not found
        """
        return self.data.get("visit_results", {}).get(str(visit_id))

    def set_visit_result(
        self,
        visit_id: int,
        xform_id: str,
        result: str | None,
        notes: str,
        user_id: int,
        opportunity_id: int,
    ):
        """
        Set/update result for a visit using UserVisit ID as key.

        Args:
            visit_id: UserVisit ID from Connect
            xform_id: Form ID
            result: "pass" or "fail"
            notes: Notes about the visit
            user_id: FLW user ID
            opportunity_id: Opportunity ID
        """
        if "visit_results" not in self.data:
            self.data["visit_results"] = {}

        visit_key = str(visit_id)
        existing = self.data["visit_results"].get(visit_key, {})

        self.data["visit_results"][visit_key] = {
            "xform_id": xform_id,
            "result": result,
            "notes": notes,
            "user_id": user_id,
            "opportunity_id": opportunity_id,
            "assessments": existing.get("assessments", {}),
        }

    def clear_visit_result(self, visit_id: int):
        """
        Clear the stored result for a visit without losing assessments.

        Args:
            visit_id: UserVisit ID from Connect
        """
        visit_key = str(visit_id)
        visit_data = self.data.get("visit_results", {}).get(visit_key)
        if visit_data:
            visit_data["result"] = None
            visit_data["notes"] = ""

    def get_assessments(self, visit_id: int) -> dict:
        """
        Get all assessments for a visit by UserVisit ID.

        Args:
            visit_id: UserVisit ID from Connect

        Returns:
            Dict of assessments keyed by blob_id
        """
        return self.data.get("visit_results", {}).get(str(visit_id), {}).get("assessments", {})

    def set_assessment(self, visit_id: int, blob_id: str, question_id: str, result: str | None, notes: str):
        """
        Set/update assessment for an image.

        Args:
            visit_id: UserVisit ID from Connect
            blob_id: Blob ID
            question_id: CommCare question path
            result: "pass" or "fail"
            notes: Notes about the assessment
        """
        visit_key = str(visit_id)

        if "visit_results" not in self.data:
            self.data["visit_results"] = {}

        if visit_key not in self.data["visit_results"]:
            # Initialize visit result if doesn't exist
            self.data["visit_results"][visit_key] = {"assessments": {}}

        visit_result = self.data["visit_results"][visit_key]
        if "assessments" not in visit_result:
            visit_result["assessments"] = {}

        visit_result["assessments"][blob_id] = {
            "question_id": question_id,
            "result": result,
            "notes": notes,
        }

    def clear_assessment(self, visit_id: int, blob_id: str):
        """
        Remove an assessment entry for an image.

        Args:
            visit_id: UserVisit ID from Connect
            blob_id: Blob ID
        """
        visit_key = str(visit_id)
        visit_result = self.data.get("visit_results", {}).get(visit_key)
        if visit_result and "assessments" in visit_result:
            visit_result["assessments"].pop(blob_id, None)

    def get_progress_stats(self) -> dict:
        """
        Calculate progress statistics based on assessments.

        Returns:
            Dict with percentage, assessed count, and total count
        """
        total_assessments = 0
        assessed_count = 0

        for visit_result in self.data.get("visit_results", {}).values():
            for assessment in visit_result.get("assessments", {}).values():
                total_assessments += 1
                if assessment.get("result"):
                    assessed_count += 1

        percentage = (assessed_count / total_assessments * 100) if total_assessments > 0 else 0

        return {
            "percentage": round(percentage, 1),
            "assessed": assessed_count,
            "total": total_assessments,
        }

    def is_complete(self) -> bool:
        """Check if audit is completed."""
        return self.status == "completed"

    def get_visit_count(self) -> int:
        """Get total number of visits in this audit."""
        return len(self.visit_ids)
