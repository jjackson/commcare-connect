"""Unit tests for HQ app utility: image question extraction and filtering."""
from commcare_connect.audit.hq_app_utils import extract_image_questions


def _make_app(forms):
    """Helper: build minimal HQ app dict with one module."""
    return {
        "modules": [
            {
                "name": "Test Module",
                "forms": forms,
            }
        ]
    }


def _make_form(name, questions):
    return {"name": name, "xmlns": f"http://test/{name}", "questions": questions}


def _q(path, qtype, label="", relevant=None, calculate=None):
    """Helper: build a minimal question dict."""
    q = {"value": path, "type": qtype, "label": label}
    if relevant is not None:
        q["relevant"] = relevant
    if calculate is not None:
        q["calculate"] = calculate
    return q


class TestExtractImageQuestions:
    def test_returns_image_questions(self):
        app = _make_app(
            [
                _make_form(
                    "form1",
                    [
                        _q("/data/my_photo", "Image", label="Take a photo"),
                    ],
                )
            ]
        )
        result = extract_image_questions(app)
        assert len(result) == 1
        assert result[0]["id"] == "my_photo"
        assert result[0]["label"] == "Take a photo"
        assert result[0]["path"] == "my_photo"
        assert result[0]["form_name"] == "form1"

    def test_ignores_non_image_questions(self):
        app = _make_app(
            [
                _make_form(
                    "form1",
                    [
                        _q("/data/my_text", "Text", label="Enter text"),
                        _q("/data/my_int", "Int", label="Enter number"),
                    ],
                )
            ]
        )
        result = extract_image_questions(app)
        assert result == []

    def test_keeps_image_with_normal_relevant_condition(self):
        """Non-trivially-false relevant should NOT filter out the question."""
        app = _make_app(
            [
                _make_form(
                    "form1",
                    [
                        _q("/data/muac_group", "Group", relevant="/data/muac_colour != ''"),
                        _q(
                            "/data/muac_group/muac_photo",
                            "Image",
                            label="MUAC Photo",
                            relevant="/data/muac_group/muac_colour != ''",
                        ),
                    ],
                )
            ]
        )
        result = extract_image_questions(app)
        assert len(result) == 1
        assert result[0]["id"] == "muac_photo"

    def test_image_path_strips_data_prefix(self):
        app = _make_app(
            [
                _make_form(
                    "form1",
                    [
                        _q("/data/ors_group/ors_photo", "Image", label="ORS Photo"),
                    ],
                )
            ]
        )
        result = extract_image_questions(app)
        assert result[0]["path"] == "ors_group/ors_photo"

    def test_autodetects_hq_url_path(self):
        """DataBindOnly sibling whose calculate ends with the image path → hq_url_path."""
        app = _make_app(
            [
                _make_form(
                    "form1",
                    [
                        _q("/data/ors_group/ors_photo", "Image", label="ORS Photo"),
                        _q(
                            "/data/ors_group/photo_link_ors",
                            "DataBindOnly",
                            calculate="concat('https://hq.org/.../', /data/ors_group/ors_photo)",
                        ),
                    ],
                )
            ]
        )
        result = extract_image_questions(app)
        assert result[0]["hq_url_path"] == "ors_group/photo_link_ors"

    def test_hq_url_path_is_empty_when_none_found(self):
        app = _make_app(
            [
                _make_form(
                    "form1",
                    [
                        _q("/data/my_photo", "Image", label="Photo"),
                    ],
                )
            ]
        )
        result = extract_image_questions(app)
        assert result[0]["hq_url_path"] == ""

    def test_hq_url_path_handles_null_calculate(self):
        """DataBindOnly with calculate=None (not missing, but explicitly null) should not crash."""
        q = _q("/data/link_field", "DataBindOnly")
        q["calculate"] = None  # explicitly null, as some HQ apps return
        app = _make_app(
            [_make_form("form1", [_q("/data/my_photo", "Image", label="Photo"), q])]
        )
        result = extract_image_questions(app)
        assert result[0]["hq_url_path"] == ""

    def test_collects_images_from_multiple_forms(self):
        app = _make_app(
            [
                _make_form("form1", [_q("/data/photo_a", "Image", label="A")]),
                _make_form("form2", [_q("/data/photo_b", "Image", label="B")]),
            ]
        )
        result = extract_image_questions(app)
        assert len(result) == 2
        ids = {r["id"] for r in result}
        assert ids == {"photo_a", "photo_b"}

    def test_deduplicates_same_leaf_id_across_forms(self):
        """When two forms have same leaf ID, fall back to full path."""
        app = _make_app(
            [
                _make_form("form1", [_q("/data/group_a/photo", "Image", label="Form1 Photo")]),
                _make_form("form2", [_q("/data/group_b/photo", "Image", label="Form2 Photo")]),
            ]
        )
        result = extract_image_questions(app)
        assert len(result) == 2
        ids = {r["id"] for r in result}
        # First gets leaf "photo", second gets full path "group_b/photo"
        assert "photo" in ids
        assert "group_b/photo" in ids

    def test_deduplicates_identical_path_across_forms_uses_xmlns(self):
        """When leaf and full path are both taken, fall back to xmlns-qualified id."""

        def _make_form_with_xmlns(name, xmlns, questions):
            return {"name": name, "xmlns": xmlns, "questions": questions}

        # Three forms with the same question path:
        # form1 → gets leaf "photo"
        # form2 → leaf taken, gets full "group/photo"
        # form3 → leaf AND full path taken → falls back to xmlns:group/photo
        app = {
            "modules": [
                {
                    "name": "Module",
                    "forms": [
                        _make_form_with_xmlns(
                            "form1",
                            "http://openrosa.org/form/form1",
                            [_q("/data/group/photo", "Image", label="Photo A")],
                        ),
                        _make_form_with_xmlns(
                            "form2",
                            "http://openrosa.org/form/form2",
                            [_q("/data/group/photo", "Image", label="Photo B")],
                        ),
                        _make_form_with_xmlns(
                            "form3",
                            "http://openrosa.org/form/form3",
                            [_q("/data/group/photo", "Image", label="Photo C")],
                        ),
                    ],
                }
            ]
        }
        result = extract_image_questions(app)
        assert len(result) == 3
        ids = {r["id"] for r in result}
        assert "photo" in ids
        assert "group/photo" in ids
        assert any("form3" in qid for qid in ids), f"Expected xmlns-qualified id in {ids}"

