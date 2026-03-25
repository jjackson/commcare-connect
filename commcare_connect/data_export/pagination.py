from urllib.parse import urlencode

from rest_framework.exceptions import ValidationError
from rest_framework.pagination import BasePagination
from rest_framework.response import Response

FORWARD = "forward"
REVERSE = "reverse"
VALID_CURSOR_ORDERS = (FORWARD, REVERSE)


def _parse_int(value, field_name, positive=False):
    try:
        value = int(value)
    except (ValueError, TypeError):
        raise ValidationError({field_name: "Must be an integer."})

    if positive and value <= 0:
        raise ValidationError({field_name: "Must be a positive integer."})

    return value


class IdKeysetPagination(BasePagination):
    """Keyset (cursor) pagination using the integer ``id`` primary key.

    Assumes every model in the queryset has an auto-incrementing integer
    ``id`` column. The cursor is the ``last_id`` value from the previous
    page; the next page returns rows with ``id > last_id`` (forward) or
    ``id < last_id`` (reverse).

    Query parameters:
        last_id      – cursor: id of the last item on the previous page
        page_size    – items per page (default 1000, max 5000)
        cursor_order – ``forward`` (ascending id) or ``reverse`` (descending id)

    All other query parameters are preserved in the ``next`` link.
    """

    default_page_size = 1000
    max_page_size = 5000
    page_size_query_param = "page_size"
    last_id_query_param = "last_id"
    cursor_order_query_param = "cursor_order"

    def paginate_queryset(self, queryset, request, view=None):
        self.request = request

        self.cursor_order = request.query_params.get(self.cursor_order_query_param, FORWARD)
        if self.cursor_order not in VALID_CURSOR_ORDERS:
            raise ValidationError({"cursor_order": f"Must be one of {', '.join(VALID_CURSOR_ORDERS)}."})

        raw_last_id = request.query_params.get(self.last_id_query_param)
        self.last_id = _parse_int(raw_last_id, "last_id", positive=True) if raw_last_id is not None else None

        raw_page_size = request.query_params.get(self.page_size_query_param)
        if raw_page_size is not None:
            page_size = _parse_int(raw_page_size, "page_size", positive=True)
            self.page_size = min(page_size, self.max_page_size)
        else:
            self.page_size = self.default_page_size

        # Apply ordering and cursor filter
        is_forward = self.cursor_order == FORWARD
        queryset = queryset.order_by("id" if is_forward else "-id")
        if self.last_id is not None:
            queryset = queryset.filter(id__gt=self.last_id) if is_forward else queryset.filter(id__lt=self.last_id)

        # Fetch one extra to detect next page
        results = list(queryset[: self.page_size + 1])
        self.has_next = len(results) > self.page_size
        self.page = results[: self.page_size]

        return self.page

    def get_next_link(self):
        if not self.has_next or not self.page:
            return None

        last_item = self.page[-1]
        params = {
            self.last_id_query_param: last_item.id,
            self.page_size_query_param: self.page_size,
            self.cursor_order_query_param: self.cursor_order,
        }

        for key, value in self.request.query_params.items():
            if key not in params:
                params[key] = value

        return self.request.build_absolute_uri(f"{self.request.path}?{urlencode(params)}")

    def get_paginated_response(self, data):
        return Response(
            {
                "next": self.get_next_link(),
                "results": data,
            }
        )
