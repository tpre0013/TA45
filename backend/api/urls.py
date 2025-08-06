from django.urls import path
from .views import hello_world, get_spots

urlpatterns = [
    path('hello/', hello_world),
    path('spots/', get_spots),
]