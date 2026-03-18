from drf_spectacular.utils import extend_schema
from rest_framework import generics
from rest_framework.permissions import AllowAny, IsAuthenticated

from users.serializers import UserSerializer


@extend_schema(
    summary="Create user",
    description="Register a new user account.",
    request=UserSerializer,
    responses={201: UserSerializer},
)
class CreateUserView(generics.CreateAPIView):
    serializer_class = UserSerializer
    permission_classes = (AllowAny,)


@extend_schema(
    summary="Retrieve or update current user",
    description="Get or update the authenticated user's profile.",
    request=UserSerializer,
    responses={200: UserSerializer},
)
class ManageUserView(generics.RetrieveUpdateAPIView):
    serializer_class = UserSerializer
    permission_classes = (IsAuthenticated,)

    def get_object(self):
        return self.request.user
