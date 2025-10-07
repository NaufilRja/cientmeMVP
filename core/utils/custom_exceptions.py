from rest_framework.views import exception_handler
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from rest_framework.response import Response
from rest_framework import status

def custom_exception_handler(exc, context):
    # Call REST framework's default exception handler first
    response = exception_handler(exc, context)

    # Handle Simple JWT errors
    if isinstance(exc, (InvalidToken, TokenError)):
        return Response(
            {"detail": "You are not logged in. Please login to see this page."},
            status=status.HTTP_401_UNAUTHORIZED
        )

    return response
