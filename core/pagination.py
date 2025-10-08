# core/pagination.py
from rest_framework.pagination import CursorPagination
from rest_framework.response import Response


# --------------------------------
# Standard Cursor Pagination
# --------------------------------
class StandardCursorPagination(CursorPagination):
    page_size = 20
    ordering = '-created_at'  # Descending = newest first

    def get_paginated_response(self, data):
        return Response({
            'next': self.get_next_link(),
            'previous': self.get_previous_link(),
            'has_next': bool(self.get_next_link()),
            'results': data
        })


