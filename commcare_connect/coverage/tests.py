"""
Tests for coverage models and data access.
"""

from django.test import TestCase

from commcare_connect.coverage.models import DeliveryUnit, LocalUserVisit
from commcare_connect.coverage.utils import extract_gps_from_form_json


class DeliveryUnitTestCase(TestCase):
    """Tests for DeliveryUnit model"""

    def test_delivery_unit_from_commcare_case(self):
        """Test creating a DeliveryUnit from CommCare case data"""
        case_data = {
            "case_id": "test123",
            "case_name": "DU-001",
            "owner_id": "user123",
            "last_modified": "2024-01-01T12:00:00Z",
            "properties": {
                "service_area_id": "1-5",
                "du_status": "completed",
                "WKT": "POLYGON((0 0, 1 0, 1 1, 0 1, 0 0))",
                "buildings": "50",
                "surface_area": "1000.5",
            },
        }

        du = DeliveryUnit.from_commcare_case(case_data)

        self.assertEqual(du.du_name, "DU-001")
        self.assertEqual(du.id, "test123")
        self.assertEqual(du.buildings, 50)
        self.assertEqual(du.surface_area, 1000.5)
        self.assertEqual(du.status, "completed")
        self.assertIsNotNone(du.geometry)

    def test_delivery_unit_geometry(self):
        """Test that geometry can be parsed from WKT"""
        case_data = {
            "case_id": "test456",
            "case_name": "DU-002",
            "owner_id": "user456",
            "properties": {
                "service_area_id": "2-10",
                "du_status": "unvisited",
                "WKT": "POLYGON((0 0, 1 0, 1 1, 0 1, 0 0))",
            },
        }

        du = DeliveryUnit.from_commcare_case(case_data)

        geometry = du.geometry
        self.assertIsNotNone(geometry)
        self.assertEqual(geometry.geom_type, "Polygon")

        centroid = du.centroid
        self.assertIsNotNone(centroid)
        self.assertEqual(len(centroid), 2)  # lat, lon tuple


class LocalUserVisitTestCase(TestCase):
    """Tests for LocalUserVisit proxy model"""

    def test_gps_extraction(self):
        """Test GPS extraction from form_json"""
        visit_data = {
            "xform_id": "visit123",
            "form_json": {"metadata": {"location": "9.0 8.5 100 15.2"}},
            "username": "testuser",
            "deliver_unit": "DU-001",
            "status": "approved",
            "visit_date": "2024-01-01",
            "flagged": False,
            "user_id": "user123",
        }

        point = LocalUserVisit(visit_data)

        self.assertEqual(point.latitude, 9.0)
        self.assertEqual(point.longitude, 8.5)
        self.assertEqual(point.accuracy_in_m, 15.2)

    def test_visit_properties(self):
        """Test LocalUserVisit properties"""
        visit_data = {
            "xform_id": "visit456",
            "form_json": {"metadata": {"location": "10.5 7.3 50 20.0"}},
            "username": "testuser2",
            "deliver_unit": "DU-002",
            "status": "pending",
            "visit_date": "2024-01-02T14:30:00Z",
            "flagged": True,
            "user_id": "user456",
        }

        point = LocalUserVisit(visit_data)

        self.assertEqual(point.id, "visit456")
        self.assertEqual(point.username, "testuser2")
        self.assertEqual(point.deliver_unit_name, "DU-002")
        self.assertEqual(point.status, "pending")
        self.assertTrue(point.flagged)

    def test_visit_with_missing_gps(self):
        """Test handling of missing GPS data"""
        visit_data = {
            "xform_id": "visit789",
            "form_json": {"metadata": {}},  # No location
            "username": "testuser3",
            "deliver_unit": "DU-003",
            "status": "approved",
            "visit_date": "2024-01-03",
            "flagged": False,
            "user_id": "user789",
        }

        point = LocalUserVisit(visit_data)

        # Should return 0.0 for missing coordinates
        self.assertEqual(point.latitude, 0.0)
        self.assertEqual(point.longitude, 0.0)
        self.assertIsNone(point.accuracy_in_m)


class UtilsTestCase(TestCase):
    """Tests for utility functions"""

    def test_extract_gps_from_form_json(self):
        """Test GPS extraction utility"""
        form_json = {"metadata": {"location": "12.5 34.7 150 25.0"}}

        lat, lon, accuracy = extract_gps_from_form_json(form_json)

        self.assertEqual(lat, 12.5)
        self.assertEqual(lon, 34.7)
        self.assertEqual(accuracy, 25.0)

    def test_extract_gps_with_missing_metadata(self):
        """Test GPS extraction with missing metadata"""
        form_json = {}

        lat, lon, accuracy = extract_gps_from_form_json(form_json)

        self.assertEqual(lat, 0.0)
        self.assertEqual(lon, 0.0)
        self.assertIsNone(accuracy)

    def test_extract_gps_with_partial_location(self):
        """Test GPS extraction with partial location data"""
        form_json = {"metadata": {"location": "12.5"}}

        lat, lon, accuracy = extract_gps_from_form_json(form_json)

        self.assertEqual(lat, 12.5)
        self.assertEqual(lon, 0.0)
        self.assertIsNone(accuracy)
