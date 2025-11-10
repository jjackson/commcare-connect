"""
Blob Metadata API for Audit.

Simulates blob metadata availability from Connect APIs by actually
fetching from CommCare HQ. Extracts question_ids from form JSON.
"""

import os
from typing import Any

import requests

from commcare_connect.audit.management.extractors.commcare_extractor import CommCareExtractor


class BlobMetadataAPI:
    """
    API for retrieving blob metadata with question IDs.

    Pretends Connect provides blob metadata, but actually fetches
    from CommCare HQ APIs.
    """

    def __init__(self, commcare_username: str | None = None, commcare_api_key: str | None = None):
        """
        Initialize the BlobMetadataAPI.

        Args:
            commcare_username: CommCare username (defaults to COMMCARE_USERNAME env var)
            commcare_api_key: CommCare API key (defaults to COMMCARE_API_KEY env var)
        """
        self.username = commcare_username or os.getenv("COMMCARE_USERNAME")
        self.api_key = commcare_api_key or os.getenv("COMMCARE_API_KEY")

        if not self.username or not self.api_key:
            raise ValueError("CommCare credentials required (COMMCARE_USERNAME, COMMCARE_API_KEY)")

    def get_blob_metadata_for_visit(self, xform_id: str, cc_domain: str) -> dict[str, dict[str, Any]]:
        """
        Fetch form from CommCare and extract blob metadata with question_ids.

        Args:
            xform_id: Form ID
            cc_domain: CommCare domain

        Returns:
            Dict mapping blob_id to metadata:
            {
                "blob_id_abc": {
                    "question_id": "/data/group1/photo",
                    "content_type": "image/jpeg",
                    "url": "https://...",
                    "filename": "photo.jpg"
                }
            }
        """
        # Initialize CommCare extractor
        extractor = CommCareExtractor(domain=cc_domain, username=self.username, api_key=self.api_key)

        try:
            # Fetch the form by ID using the direct form URL pattern
            form_url = f"https://www.commcarehq.org/a/{cc_domain}/api/v0.5/form/{xform_id}/"
            response = extractor.session.get(form_url, timeout=30)
            response.raise_for_status()

            form = response.json()

            # Extract blob metadata
            blob_metadata = {}
            attachments = form.get("attachments", {})

            if not attachments:
                return blob_metadata

            # Get form data for question ID extraction
            form_data = form.get("form", {})

            for filename, attachment_info in attachments.items():
                # Extract URL and content type
                if isinstance(attachment_info, dict):
                    attachment_url = attachment_info.get("url")
                    content_type = attachment_info.get("content_type", "application/octet-stream")
                else:
                    attachment_url = attachment_info
                    content_type = "application/octet-stream"

                if not attachment_url:
                    continue

                # Extract blob_id from URL
                # CommCare URLs look like: .../multimedia/download/blob_id/?...
                blob_id = self._extract_blob_id_from_url(attachment_url)

                # Extract question_id for this attachment
                question_id = self._extract_question_id_for_attachment(form_data, filename)

                blob_metadata[blob_id] = {
                    "question_id": question_id,
                    "content_type": content_type,
                    "url": attachment_url,
                    "filename": filename,
                }

            return blob_metadata

        finally:
            extractor.close()

    def download_blob(self, blob_url: str) -> bytes:
        """
        Download blob content from CommCare URL.

        Args:
            blob_url: Full URL to the blob

        Returns:
            Blob content as bytes
        """
        # Create a session with CommCare auth
        session = requests.Session()
        session.auth = (self.username, self.api_key)

        try:
            response = session.get(blob_url, timeout=30)
            response.raise_for_status()
            return response.content
        finally:
            session.close()

    def _extract_blob_id_from_url(self, url: str) -> str:
        """
        Extract blob ID from CommCare attachment URL.

        CommCare URLs typically look like:
        https://www.commcarehq.org/a/domain/api/form/attachment/xform_id/filename
        or
        https://www.commcarehq.org/a/domain/multimedia/download/blob_id/?...

        For now, we'll use filename as blob_id since that's what's stored in BlobMeta.

        Args:
            url: Attachment URL

        Returns:
            Blob ID (filename)
        """
        # Extract filename from URL
        # Try multimedia URL pattern first
        if "/multimedia/download/" in url:
            parts = url.split("/multimedia/download/")
            if len(parts) > 1:
                blob_id = parts[1].split("?")[0].split("/")[0]
                return blob_id

        # Fall back to extracting filename from end of URL
        filename = url.split("/")[-1].split("?")[0]
        return filename

    def _extract_question_id_for_attachment(self, form_data: dict, filename: str) -> str | None:
        """
        Extract the question ID that corresponds to an attachment filename.

        CommCare form data structure has question IDs as keys, and filenames as values
        for image/attachment questions. This recursively searches the form data to find
        the matching question ID.

        Args:
            form_data: The form data dict (typically form["form"])
            filename: The attachment filename to search for

        Returns:
            The question ID (key) if found, None otherwise
        """

        def search_dict(data, target_filename, path=""):
            """Recursively search for filename in nested dict structure"""
            if not isinstance(data, dict):
                return None

            for key, value in data.items():
                # Skip metadata and special fields
                if key in ["@xmlns", "@name", "@uiVersion", "@version", "meta", "#type"]:
                    continue

                current_path = f"{path}/{key}" if path else key

                # Check if this value matches our filename
                if isinstance(value, str) and value == target_filename:
                    return current_path

                # Recursively search nested dicts
                if isinstance(value, dict):
                    result = search_dict(value, target_filename, current_path)
                    if result:
                        return result

            return None

        # Search for the filename in the form data
        question_path = search_dict(form_data, filename)
        return question_path
