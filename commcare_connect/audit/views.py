"""
Audit Views - Legacy Implementation Removed

All audit views have been migrated to the ExperimentRecord-based implementation.
See experiment_views.py for the current audit view implementation.

The old Django ORM models (Audit, AuditTemplate, AuditResult, Assessment) and
their associated views have been replaced with:
- experiment_models.py: Proxy models for ExperimentRecord
- experiment_views.py: New view implementations
- data_access.py: Data access layer for audit operations

Legacy views that were removed:
- AuditListView, AuditDetailView
- AuditExportView, AuditExportAllView
- BulkAssessmentView
- AuditResultUpdateView, AssessmentUpdateView, VisitResultUpdateView
- ApplyAssessmentResultsView, AuditCompleteView, AuditUncompleteView
- AuditVisitDataView
- DatabaseStatsAPIView, DatabaseResetAPIView
- DownloadMissingAttachmentsAPIView
- AuditTemplateExportView, AuditTemplateImportView
- AuditImageView
"""
