from rest_framework.decorators import api_view
from rest_framework.response import Response
from .models import ParkingSpot
from .serializers import ParkingSpotSerializer
from django.shortcuts import render
from django.db.models import Q
from .models import LiveParkingData
from math import radians, cos, sin, asin, sqrt
import requests
from django.http import JsonResponse
import logging
from django.shortcuts import render
import requests


# Set up logging
logger = logging.getLogger(__name__)

def home_page(request):
    return render(request, 'home.html')

def traffic_page(request):
    return render(request, 'traffic.html')

@api_view(['GET'])
def hello_world(request):
    return Response({"message": "Hello, API world!"})

def traffic_page(request):
    return render(request, "traffic.html")

@api_view(['GET'])
def get_spots(request):
    spots = ParkingSpot.objects.all()
    serializer = ParkingSpotSerializer(spots, many=True)
    return Response(serializer.data)

# Haversine distance in kilometers
def haversine(lat1, lon1, lat2, lon2):
    R = 6371  # Earth radius in km
    lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
    c = 2 * asin(sqrt(a))
    return R * c

def is_in_cbd(lat, lng):
    """
    Check if coordinates are within Melbourne CBD boundaries
    Expanded CBD area to include more parking areas
    """
    # Melbourne CBD extended boundaries
    return (
        -37.830 <= lat <= -37.800 and  # Extended north-south
        144.940 <= lng <= 144.985     # Extended east-west
    )

def get_cbd_info():
    """Return CBD boundary information for debugging"""
    return {
        "lat_min": -37.830,
        "lat_max": -37.800, 
        "lng_min": 144.940,
        "lng_max": 144.985
    }

def normalize_status(status_description):
    """Normalize status description to consistent format for real-time display"""
    if not status_description:
        return "Unknown"
    
    status = status_description.lower().strip()
    
    # Real-time status mapping
    if any(word in status for word in ['available', 'unoccupied', 'free', 'vacant', 'open']):
        return "Available"
    elif any(word in status for word in ['occupied', 'taken', 'full', 'busy', 'in use']):
        return "Occupied" 
    elif any(word in status for word in ['limited', 'partial', 'restricted', 'some']):
        return "Limited"
    else:
        # Log unknown statuses for debugging
        logger.info(f"Unknown status encountered: {status_description}")
        return "Unknown"

# NEW: Location suggestions endpoint
@api_view(['GET'])
def get_location_suggestions(request):
    """
    Get location suggestions from parking spot addresses and popular CBD locations
    """
    query = request.GET.get('q', '').strip()
    
    if not query or len(query) < 2:
        return JsonResponse({'suggestions': []})
    
    suggestions = []
    
    try:
        # Get unique street/location names from parking data
        cbd_info = get_cbd_info()
        parking_locations = LiveParkingData.objects.filter(
            RoadSegmentDescription__icontains=query,
            lat__isnull=False,
            lon__isnull=False,
            lat__gte=cbd_info["lat_min"],
            lat__lte=cbd_info["lat_max"],
            lon__gte=cbd_info["lng_min"],
            lon__lte=cbd_info["lng_max"]
        ).values_list('RoadSegmentDescription', flat=True).distinct()[:8]
        
        # Extract street names and clean them up
        street_suggestions = set()
        for location in parking_locations:
            if location:
                # Extract street name from descriptions like "FLINDERS ST between SPRING ST and EXHIBITION ST"
                parts = location.split(' between ')
                street_name = parts[0].strip()
                
                # Clean up street name
                street_name = street_name.replace(' ST', ' Street').replace(' AVE', ' Avenue').replace(' RD', ' Road')
                street_name = ' '.join(word.capitalize() for word in street_name.split())
                
                if len(street_name) > 3:  # Filter out very short names
                    street_suggestions.add(street_name)
        
        # Add street suggestions
        for street in sorted(street_suggestions):
            suggestions.append({
                'text': street,
                'type': 'street',
                'description': f'Street in Melbourne CBD'
            })
        
        # Add popular CBD landmarks if they match the query
        landmarks = [
            {'name': 'Federation Square', 'lat': -37.8179, 'lng': 144.9690},
            {'name': 'Flinders Street Station', 'lat': -37.8183, 'lng': 144.9671},
            {'name': 'Southern Cross Station', 'lat': -37.8183, 'lng': 144.9526},
            {'name': 'Melbourne Central', 'lat': -37.8102, 'lng': 144.9629},
            {'name': 'Collins Street', 'lat': -37.8136, 'lng': 144.9631},
            {'name': 'Bourke Street Mall', 'lat': -37.8136, 'lng': 144.9651},
            {'name': 'Queen Victoria Market', 'lat': -37.8076, 'lng': 144.9568},
            {'name': 'State Library of Victoria', 'lat': -37.8098, 'lng': 144.9652},
            {'name': 'Parliament House', 'lat': -37.8118, 'lng': 144.9727},
            {'name': 'Royal Melbourne Hospital', 'lat': -37.7988, 'lng': 144.9563},
            {'name': 'RMIT University', 'lat': -37.8076, 'lng': 144.9631},
            {'name': 'University of Melbourne', 'lat': -37.7963, 'lng': 144.9614},
            {'name': 'Crown Casino', 'lat': -37.8226, 'lng': 144.9588},
            {'name': 'Southbank', 'lat': -37.8226, 'lng': 144.9648},
            {'name': 'Docklands', 'lat': -37.8142, 'lng': 144.9441}
        ]
        
        for landmark in landmarks:
            if query.lower() in landmark['name'].lower():
                suggestions.append({
                    'text': landmark['name'],
                    'type': 'landmark',
                    'description': 'Popular Melbourne location',
                    'lat': landmark['lat'],
                    'lng': landmark['lng']
                })
        
        # Limit total suggestions
        suggestions = suggestions[:10]
        
    except Exception as e:
        logger.error(f"Error getting location suggestions: {e}")
        suggestions = []
    
    return JsonResponse({'suggestions': suggestions})

@api_view(['GET'])
def get_nearby_spots(request):
    query = request.GET.get('query')
    lat = request.GET.get('lat')
    lng = request.GET.get('lng')

    logger.info(f"Search request - Query: {query}, Lat: {lat}, Lng: {lng}")

    results = []
    search_location = {"lat": None, "lng": None}

    # Geocoding if needed
    if query and (not lat or not lng):
        geocode_url = f"https://nominatim.openstreetmap.org/search?q={query}, Melbourne, Australia&format=json&limit=1"
        try:
            response = requests.get(geocode_url, headers={"User-Agent": "ParkingFinder/1.0"}, timeout=5)
            if response.status_code == 200:
                geo_data = response.json()
                if geo_data:
                    lat = float(geo_data[0]['lat'])
                    lng = float(geo_data[0]['lon'])
                    logger.info(f"Geocoded '{query}' to {lat}, {lng}")
                else:
                    logger.warning(f"No geocoding results for query: {query}")
        except requests.RequestException as e:
            logger.error(f"Geocoding failed: {e}")

    if lat and lng:
        lat = float(lat)
        lng = float(lng)
        search_location = {"lat": lat, "lng": lng}

        logger.info(f"Searching near coordinates: {lat}, {lng}")
        cbd_info = get_cbd_info()
        is_in_bounds = is_in_cbd(lat, lng)
        logger.info(f"Is in CBD: {is_in_bounds}")
        logger.info(f"CBD boundaries: {cbd_info}")

        # Check if location is within CBD boundaries
        if not is_in_bounds:
            logger.warning(f"Location {lat}, {lng} is outside CBD bounds")
            return JsonResponse({
                "message": "Location is outside Melbourne CBD area",
                "search_location": search_location,
                "cbd_boundaries": cbd_info,
                "query": query,
                "in_cbd": False,
                "total_count": 0,
                "results": []
            }, safe=False)

        # Get parking spots within CBD and calculate distances
        try:
            all_spots = LiveParkingData.objects.filter(
                lat__isnull=False, 
                lon__isnull=False,
                # Optional: filter by CBD bounds in database query for performance
                lat__gte=cbd_info["lat_min"],
                lat__lte=cbd_info["lat_max"],
                lon__gte=cbd_info["lng_min"], 
                lon__lte=cbd_info["lng_max"]
            )
            
            logger.info(f"Found {all_spots.count()} total spots in CBD database")

            for spot in all_spots:
                if spot.lat and spot.lon:
                    dist = haversine(lat, lng, spot.lat, spot.lon)
                    if dist <= 2:  # Within 2km radius
                        normalized_status = normalize_status(spot.status_description)
                        results.append({
                            "kerbsideid": spot.kerbsideid,
                            "address": spot.RoadSegmentDescription or f"Parking Spot {spot.kerbsideid}",
                            "lat": float(spot.lat),
                            "lng": float(spot.lon), 
                            "status": normalized_status,
                            "raw_status": spot.status_description,  # For debugging
                            "distance": round(dist, 2),
                            "last_updated": spot.lastupdated or "Unknown",
                            "status_timestamp": spot.status_timestamp or "Unknown"
                        })

            logger.info(f"Found {len(results)} spots within 2km of search location")

        except Exception as e:
            logger.error(f"Database query failed: {e}")
            return JsonResponse({
                "error": "Failed to query parking data",
                "message": str(e),
                "results": []
            }, safe=False)

    # Fallback keyword search (only if within CBD or no location provided)
    if not results and query:
        logger.info(f"Trying fallback keyword search for: {query}")
        
        # If we have coordinates and they're outside CBD, don't do keyword search
        if lat and lng and not is_in_cbd(lat, lng):
            return JsonResponse({
                "message": "No results found and location is outside CBD area",
                "search_location": search_location,
                "query": query,
                "in_cbd": False,
                "results": []
            }, safe=False)
            
        try:
            # Search within CBD boundaries
            matches = LiveParkingData.objects.filter(
                RoadSegmentDescription__icontains=query,
                lat__isnull=False,
                lon__isnull=False,
                lat__gte=get_cbd_info()["lat_min"],
                lat__lte=get_cbd_info()["lat_max"],
                lon__gte=get_cbd_info()["lng_min"],
                lon__lte=get_cbd_info()["lng_max"]
            )[:50]  # Limit results
            
            logger.info(f"Keyword search found {matches.count()} matches in CBD")
            
            for spot in matches:
                normalized_status = normalize_status(spot.status_description)
                results.append({
                    "kerbsideid": spot.kerbsideid,
                    "address": spot.RoadSegmentDescription or f"Parking Spot {spot.kerbsideid}",
                    "lat": float(spot.lat),
                    "lng": float(spot.lon),
                    "status": normalized_status,
                    "raw_status": spot.status_description,
                    "distance": "?",
                    "last_updated": spot.lastupdated or "Unknown",
                    "status_timestamp": spot.status_timestamp or "Unknown"
                })
                
        except Exception as e:
            logger.error(f"Keyword search failed: {e}")

    # Sort results by distance if available, then by availability
    def sort_key(spot):
        # Primary sort: availability (Available = 0, Limited = 1, Unknown = 2, Occupied = 3)
        status_priority = {
            'Available': 0,
            'Limited': 1, 
            'Unknown': 2,
            'Occupied': 3
        }.get(spot['status'], 4)
        
        # Secondary sort: distance
        distance = float(spot['distance']) if spot['distance'] != '?' else 999
        
        return (status_priority, distance)

    if results:
        results.sort(key=sort_key)

    # Calculate status summary
    status_summary = {'Available': 0, 'Occupied': 0, 'Limited': 0, 'Unknown': 0}
    for spot in results:
        status_summary[spot['status']] = status_summary.get(spot['status'], 0) + 1

    logger.info(f"Returning {len(results)} results")
    
    # Return comprehensive response
    response_data = {
        "total_count": len(results),
        "search_location": search_location,
        "query": query,
        "in_cbd": is_in_cbd(lat, lng) if lat and lng else None,
        "cbd_boundaries": get_cbd_info(),
        "status_summary": status_summary,
        "results": results,
        "message": "Success" if results else ("No parking spots found in this CBD area" if lat and lng and is_in_cbd(lat, lng) else "Location outside CBD or no results")
    }
    
    return JsonResponse(response_data, safe=False)

# Additional endpoint for real-time status updates
@api_view(['GET'])
def get_spot_status(request, kerbside_id):
    """Get real-time status for a specific parking spot"""
    try:
        spot = LiveParkingData.objects.get(kerbsideid=kerbside_id)
        return JsonResponse({
            "kerbsideid": spot.kerbsideid,
            "status": normalize_status(spot.status_description),
            "raw_status": spot.status_description,
            "address": spot.RoadSegmentDescription,
            "lat": float(spot.lat) if spot.lat else None,
            "lng": float(spot.lon) if spot.lon else None,
            "last_updated": spot.lastupdated,
            "status_timestamp": spot.status_timestamp,
            "success": True
        })
    except LiveParkingData.DoesNotExist:
        return JsonResponse({
            "error": "Parking spot not found",
            "kerbsideid": kerbside_id,
            "success": False
        }, status=404)
    except Exception as e:
        return JsonResponse({
            "error": str(e),
            "success": False
        }, status=500)

# Endpoint to get all available spots in CBD
@api_view(['GET']) 
def get_available_spots(request):
    """Get all currently available parking spots in CBD"""
    try:
        cbd_info = get_cbd_info()
        available_spots = LiveParkingData.objects.filter(
            lat__isnull=False,
            lon__isnull=False,
            lat__gte=cbd_info["lat_min"],
            lat__lte=cbd_info["lat_max"],
            lon__gte=cbd_info["lng_min"],
            lon__lte=cbd_info["lng_max"]
        )
        
        results = []
        for spot in available_spots:
            normalized_status = normalize_status(spot.status_description)
            if normalized_status == "Available":  # Only return available spots
                results.append({
                    "kerbsideid": spot.kerbsideid,
                    "address": spot.RoadSegmentDescription or f"Parking Spot {spot.kerbsideid}",
                    "lat": float(spot.lat),
                    "lng": float(spot.lon),
                    "status": normalized_status,
                    "last_updated": spot.lastupdated,
                    "status_timestamp": spot.status_timestamp
                })
        
        return JsonResponse({
            "total_available": len(results),
            "results": results,
            "cbd_boundaries": cbd_info,
            "success": True
        })
        
    except Exception as e:
        return JsonResponse({
            "error": str(e),
            "success": False
        }, status=500)