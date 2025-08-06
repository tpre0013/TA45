from django.db import models

class ParkingSpot(models.Model):
    location = models.CharField(max_length=255)
    available = models.BooleanField(default=True)
    duration_limit = models.IntegerField(help_text="Max duration in minutes")
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.location} - {'Available' if self.available else 'Taken'}"
