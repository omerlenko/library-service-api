from django.db import models


class Book(models.Model):

    class Cover(models.TextChoices):
        HARD = "HARD", "Hard"
        PUBLISHED = "SOFT", "Soft"

    title = models.CharField(max_length=255)
    author = models.CharField(max_length=100)
    cover = models.CharField(max_length=4, choices=Cover.choices, default=Cover.HARD)
    inventory = models.PositiveIntegerField()
    daily_fee = models.DecimalField(max_digits=6, decimal_places=2)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["author", "title"], name="unique_book")
        ]
