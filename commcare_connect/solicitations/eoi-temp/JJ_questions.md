# Dev Team Questions

**Question**: File Upload Implementation - Django FileField vs Direct Processing?

**Context**: Code reviewer questioned whether file uploads are properly configured and if FileField approach follows project patterns.

**Current Implementation**:

- Solicitation model uses `FileField(upload_to="solicitations/attachments/")`
- ResponseAttachment model uses `FileField(upload_to="solicitations/response_attachments/")`
- Full upload/validation/deletion system implemented

**Key Findings**:

**✅ Infrastructure Exists**:

- S3 storage configured for production (`MediaRootS3Boto3Storage`)
- Media URL serving configured in main urls.py
- Custom storage backends in `utils/storages.py`

**❌ Pattern Inconsistency**:

- **Human-written opportunity app** uses direct file processing:
  ```python
  file = request.FILES.get("visits")
  saved_path = default_storage.save(file_path, file)
  # Process immediately, no FileField storage
  ```
- **Zero FileField usage** in existing human-written code
- Files processed immediately for Excel/CSV imports, not stored as attachments

**Questions for Senior Dev**:

1. Is S3 file storage actually configured/working in production?
2. Should solicitations follow existing pattern (direct processing) or introduce persistent file attachments?
3. Are persistent file attachments desired for solicitation documents?

**Answer**:
