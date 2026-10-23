from django.contrib.auth import authenticate
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenRefreshView  # noqa: F401  (used in urls)

from cases.audit import log
from .serializers import LoginSerializer, user_payload


class LoginView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        s = LoginSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        user = authenticate(request, email=s.validated_data["email"], password=s.validated_data["password"])
        if user is None:
            return Response({"detail": "Wrong email or password."}, status=status.HTTP_401_UNAUTHORIZED)
        if not hasattr(user, "profile"):
            return Response({"detail": "This account has no portal role. Ask MeshKor."}, status=status.HTTP_403_FORBIDDEN)
        refresh = RefreshToken.for_user(user)
        log(user, "Signed in")
        return Response({"access": str(refresh.access_token), "refresh": str(refresh), "user": user_payload(user)})


class MeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(user_payload(request.user))


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        token = request.data.get("refresh")
        if token:
            try:
                RefreshToken(token).blacklist()
            except TokenError:
                pass
        log(request.user, "Signed out")
        return Response(status=status.HTTP_204_NO_CONTENT)
