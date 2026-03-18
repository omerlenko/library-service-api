from drf_spectacular.utils import extend_schema_view, extend_schema
from rest_framework import viewsets

from books.models import Book
from books.permissions import IsAdminOrReadOnly
from books.serializers import BookSerializer, BookListSerializer


@extend_schema_view(
    list=extend_schema(
        summary="List books",
        description="Return a list of all books.",
        responses=BookListSerializer(many=True),
    ),
    retrieve=extend_schema(
        summary="Retrieve a book",
        description="Return detailed information about a specific book.",
        responses=BookSerializer,
    ),
    create=extend_schema(
        summary="Create a book",
        description="Create a new book.",
        request=BookSerializer,
        responses=BookSerializer,
    ),
    update=extend_schema(
        summary="Update a book",
        description="Fully update a book.",
        request=BookSerializer,
        responses=BookSerializer,
    ),
    partial_update=extend_schema(
        summary="Partially update a book",
        description="Partially update a book.",
        request=BookSerializer,
        responses=BookSerializer,
    ),
    destroy=extend_schema(
        summary="Delete a book",
        description="Delete a book.",
        responses={204: None},
    ),
)
class BookViewSet(viewsets.ModelViewSet):
    queryset = Book.objects.all()
    serializer_class = BookSerializer
    permission_classes = (IsAdminOrReadOnly,)

    def get_serializer_class(self):
        if self.action in ("list",):
            return BookListSerializer

        return super().get_serializer_class()
