from django.db import models

class ParkingSpot(models.Model):
    location = models.CharField(max_length=255)
    available = models.BooleanField(default=True)
    duration_limit = models.IntegerField(help_text="Max duration in minutes")
    updated_at = models.DateTimeField(auto_now=True)
    latitude = models.FloatField()
    longitude = models.FloatField()
    
    def __str__(self):
        return f"{self.location} - {'Available' if self.available else 'Taken'}"


class LiveParkingData(models.Model):
    lastupdated = models.CharField(max_length=50, blank=True, null=True)
    status_timestamp = models.CharField(max_length=50, blank=True, null=True)
    zone_number = models.FloatField(blank=True, null=True)
    status_description = models.CharField(max_length=50, blank=True, null=True)
    kerbsideid = models.IntegerField(primary_key=True)
    lat = models.FloatField(blank=True, null=True)
    lon = models.FloatField(blank=True, null=True)
    RoadSegmentDescription = models.CharField(max_length=128, blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'parking_data_withStreet'

