from rest_framework.decorators import api_view
from rest_framework.response import Response
from .models import ParkingSpot
from .serializers import ParkingSpotSerializer

@api_view(['GET'])
def hello_world(request):
    return Response({"message": "Hello, API world!"})

@api_view(['GET'])
def get_spots(request):
    spots = ParkingSpot.objects.all()
    serializer = ParkingSpotSerializer(spots, many=True)
    return Response(serializer.data)