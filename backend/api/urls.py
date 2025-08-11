from django.urls import path
<<<<<<< HEAD
from .views import hello_world, get_spots
=======
from .views import (
    hello_world, get_spots, get_nearby_spots,
    get_spot_status, get_available_spots, get_location_suggestions
)
>>>>>>> origin/aws/hosting

urlpatterns = [
    path('hello/', hello_world),
    path('spots/', get_spots),
<<<<<<< HEAD
]
=======
    path('spots/nearby/', get_nearby_spots),
    path('spots/status/<int:kerbside_id>/', get_spot_status),
    path('spots/available/', get_available_spots),
    path('location-suggestions/', get_location_suggestions), 
    
]
>>>>>>> origin/aws/hosting
