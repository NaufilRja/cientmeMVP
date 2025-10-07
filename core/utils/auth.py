from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework import exceptions


# -----------------------
# Optional JWT for public access
# -----------------------
class OptionalJWTAuthentication(JWTAuthentication):
    """
    Allow unauthenticated requests without failing.
    """
    def authenticate(self, request):
        try:
            return super().authenticate(request)
        except exceptions.AuthenticationFailed:
            return None  # silently ignore invalid/missing tokens

