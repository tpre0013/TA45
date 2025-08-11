from rest_framework.decorators import api_view
from rest_framework.response import Response
from .models import ParkingSpot, LiveParkingData
from .serializers import ParkingSpotSerializer
from django.shortcuts import render
from django.db.models import Q
from math import radians, cos, sin, asin, sqrt
import requests
from django.http import JsonResponse
import logging
#import folium
#from folium import plugins
import json
from django.http import HttpResponse
from django.conf import settings
import os



# Set up logging
logger = logging.getLogger(__name__)

def home_page(request):
    return render(request, 'home.html')

def traffic_page(request):
    return render(request, 'traffic.html')

@api_view(['GET'])
def hello_world(request):
    return Response({"message": "Hello, API world!"})

@api_view(['GET'])
def get_spots(request):
    spots = ParkingSpot.objects.all()
    serializer = ParkingSpotSerializer(spots, many=True)
    return Response(serializer.data)

# ---------------------------
# Utilities / helpers
# ---------------------------

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
    Updated to include Southern Cross Station and all major CBD locations
    """
    # Melbourne CBD boundaries (expanded to include Southern Cross Station)
    return (
        -37.845 <= lat <= -37.790 and  # South: Yarra River area, North: Queen Victoria Market
        144.920 <= lng <= 145.000     # West: Southern Cross area, East: Parliament/Treasury area
    )

def get_cbd_info():
    """Return CBD boundary information for debugging"""
    return {
        "lat_min": -37.845,   # Southern boundary (includes Southbank/Yarra area)
        "lat_max": -37.790,   # Northern boundary (includes Queen Victoria Market)
        "lng_min": 144.920,   # Western boundary (includes Southern Cross Station at 144.9526)
        "lng_max": 145.000    # Eastern boundary (includes Parliament area)
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
        logger.info(f"Unknown status encountered: {status_description}")
        return "Unknown"

def get_status_color(status):
    """Get color for parking spot status markers"""
    color_map = {
        'Available': '#4CAF50',    # Green
        'Limited': '#FF9800',      # Orange
        'Occupied': '#F44336',     # Red
        'Unknown': '#9E9E9E'       # Grey
    }
    return color_map.get(status, '#9E9E9E')

def get_status_icon(status):
    """Get icon for parking spot status"""
    icon_map = {
        'Available': '✓',
        'Limited': '!',
        'Occupied': '✗',
        'Unknown': '?'
    }
    return icon_map.get(status, '?')

# === NEW: Build per-street-segment statistics ===
def build_segment_stats(qs):
    """
    Build per-street-segment stats:
    {
      "<RoadSegmentDescription>": {
        "total": int,
        "available": int,
        "occupied": int,
        "limited": int,
        "unknown": int,
        "ids": [kerbsideid, ...]
      },
      ...
    }
    """
    stats = {}
    for spot in qs:
        address = spot.RoadSegmentDescription or f"Parking Spot {spot.kerbsideid}"
        norm = normalize_status(spot.status_description)
        if address not in stats:
            stats[address] = {
                "total": 0, "available": 0, "occupied": 0, "limited": 0, "unknown": 0, "ids": []
            }
        stats[address]["total"] += 1
        stats[address]["ids"].append(spot.kerbsideid)
        key = norm.lower()
        if key in ("available", "occupied", "limited", "unknown"):
            stats[address][key] += 1
        else:
            stats[address]["unknown"] += 1
    return stats

# ---------------------------
# APIs
# ---------------------------

# Location suggestions endpoint
@api_view(['GET'])
def get_location_suggestions(request):
    """
    Get location suggestions from real Melbourne locations using Nominatim API
    No CBD restrictions - users can search anywhere in Melbourne
    """
    query = request.GET.get('q', '').strip()
    if not query or len(query) < 2:
        return JsonResponse({'suggestions': []})

    suggestions = []
    
    try:
        # First, get parking spot street names (still from CBD for parking context)
        try:
            parking_locations = LiveParkingData.objects.filter(
                RoadSegmentDescription__icontains=query,
                lat__isnull=False,
                lon__isnull=False
            ).values_list('RoadSegmentDescription', flat=True).distinct()[:5]

            street_suggestions = set()
            for location in parking_locations:
                if location:
                    parts = location.split(' between ')
                    street_name = parts[0].strip()
                    street_name = street_name.replace(' ST', ' Street').replace(' AVE', ' Avenue').replace(' RD', ' Road')
                    street_name = ' '.join(word.capitalize() for word in street_name.split())
                    if len(street_name) > 3:
                        street_suggestions.add(street_name)

            for street in sorted(street_suggestions):
                suggestions.append({
                    'text': street,
                    'type': 'street',
                    'description': 'Street with parking data'
                })
        except Exception as e:
            logger.warning(f"Failed to get parking street suggestions: {e}")

        # Get real Melbourne location suggestions from Nominatim (no restrictions)
        try:
            nominatim_url = "https://nominatim.openstreetmap.org/search"
            params = {
                'format': 'json',
                'q': f"{query}, Melbourne, Victoria, Australia",
                'limit': 8,
                'countrycodes': 'au',
                'addressdetails': 1,
                'extratags': 1,
                'bounded': 1,
                # Melbourne metropolitan area boundaries (much larger than CBD)
                'viewbox': '144.5,-38.2,145.5,-37.4'  # Covers all of Melbourne metro
            }
            
            response = requests.get(
                nominatim_url, 
                params=params, 
                headers={'User-Agent': 'SpotLocator/1.0'}, 
                timeout=5
            )
            
            if response.status_code == 200:
                locations = response.json()
                
                for location in locations:
                    try:
                        lat, lng = float(location['lat']), float(location['lon'])
                        display_name = location.get('display_name', '')
                        
                        # Extract main name (first part before comma)
                        main_name = display_name.split(',')[0].strip()
                        
                        # Determine location type based on OSM data
                        location_type = 'landmark'
                        description = 'Melbourne location'
                        
                        # Categorize based on OSM class and type
                        osm_class = location.get('class', '')
                        osm_type = location.get('type', '')
                        
                        if osm_class == 'highway' or 'road' in osm_type or 'street' in osm_type:
                            location_type = 'street'
                            description = 'Street in Melbourne'
                        elif osm_class == 'railway' or osm_type == 'station':
                            location_type = 'transport'
                            description = 'Transport hub'
                        elif osm_class == 'amenity':
                            if osm_type in ['hospital', 'school', 'university', 'library']:
                                location_type = 'institution'
                                description = f'{osm_type.title()} in Melbourne'
                            elif osm_type in ['restaurant', 'cafe', 'bar', 'pub']:
                                location_type = 'dining'
                                description = f'{osm_type.title()} in Melbourne'
                            elif osm_type in ['cinema', 'theatre', 'arts_centre']:
                                location_type = 'entertainment'
                                description = 'Entertainment venue'
                            else:
                                location_type = 'amenity'
                                description = f'{osm_type.replace("_", " ").title()}'
                        elif osm_class == 'tourism':
                            location_type = 'tourist'
                            description = 'Tourist attraction'
                        elif osm_class == 'shop':
                            location_type = 'shopping'
                            description = 'Shopping location'
                        elif osm_class == 'place':
                            if osm_type == 'suburb':
                                location_type = 'suburb'
                                description = 'Melbourne suburb'
                            else:
                                location_type = 'landmark'
                                description = 'Melbourne location'
                        
                        # Skip if name is too generic or empty
                        if len(main_name) < 3 or main_name.lower() in ['melbourne', 'victoria', 'australia']:
                            continue
                            
                        # Check if we already have this suggestion
                        existing = any(s['text'].lower() == main_name.lower() for s in suggestions)
                        if not existing:
                            suggestions.append({
                                'text': main_name,
                                'type': location_type,
                                'description': description,
                                'lat': lat,
                                'lng': lng
                            })
                            
                    except (ValueError, KeyError) as e:
                        logger.warning(f"Error processing location result: {e}")
                        continue
                        
        except requests.Timeout:
            logger.warning("Nominatim API timeout")
        except requests.RequestException as e:
            logger.warning(f"Nominatim API error: {e}")
        except Exception as e:
            logger.error(f"Unexpected error with Nominatim API: {e}")

        # If we don't have many suggestions, add some popular Melbourne locations
        if len(suggestions) < 3:
            popular_locations = [
                {'name': 'Melbourne CBD', 'lat': -37.8136, 'lng': 144.9631, 'desc': 'Central Business District'},
                {'name': 'Federation Square', 'lat': -37.8179, 'lng': 144.9690, 'desc': 'Cultural precinct'},
                {'name': 'Flinders Street Station', 'lat': -37.8183, 'lng': 144.9671, 'desc': 'Railway station'},
                {'name': 'Southern Cross Station', 'lat': -37.8183, 'lng': 144.9526, 'desc': 'Railway station'},
                {'name': 'Melbourne Central', 'lat': -37.8102, 'lng': 144.9629, 'desc': 'Shopping center'},
                {'name': 'Queen Victoria Market', 'lat': -37.8076, 'lng': 144.9568, 'desc': 'Historic market'},
                {'name': 'Royal Melbourne Hospital', 'lat': -37.7988, 'lng': 144.9563, 'desc': 'Major hospital'},
                {'name': 'University of Melbourne', 'lat': -37.7963, 'lng': 144.9614, 'desc': 'University campus'},
                {'name': 'Crown Casino', 'lat': -37.8226, 'lng': 144.9588, 'desc': 'Entertainment complex'},
                {'name': 'St Kilda', 'lat': -37.8677, 'lng': 144.9811, 'desc': 'Beachside suburb'},
                {'name': 'Brighton Beach', 'lat': -37.9061, 'lng': 144.9864, 'desc': 'Popular beach'},
                {'name': 'Chapel Street', 'lat': -37.8467, 'lng': 144.9904, 'desc': 'Shopping strip'},
            ]
            
            for location in popular_locations:
                if query.lower() in location['name'].lower():
                    # Check if not already added
                    existing = any(s['text'].lower() == location['name'].lower() for s in suggestions)
                    if not existing:
                        suggestions.append({
                            'text': location['name'],
                            'type': 'landmark',
                            'description': location['desc'],
                            'lat': location['lat'],
                            'lng': location['lng']
                        })

        # Sort suggestions: streets with parking data first, then by type
        def sort_key(item):
            type_priority = {
                'street': 0,      # Streets with parking data
                'transport': 1,   # Train stations, tram stops
                'landmark': 2,    # Major landmarks
                'institution': 3, # Schools, hospitals, universities
                'tourist': 4,     # Tourist attractions
                'suburb': 5,      # Suburbs
                'shopping': 6,    # Shopping centers
                'amenity': 7,     # Other amenities
                'entertainment': 8, # Entertainment venues
                'dining': 9       # Restaurants, cafes
            }
            return (type_priority.get(item['type'], 10), item['text'].lower())
        
        suggestions.sort(key=sort_key)
        
        # Limit to 10 suggestions
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

    logger.info(f"=== SEARCH DEBUG ===")
    logger.info(f"Query: '{query}', Lat: {lat}, Lng: {lng}")

    results = []
    search_location = {"lat": None, "lng": None}

    # Geocoding if needed
    if query and (not lat or not lng):
        geocode_url = f"https://nominatim.openstreetmap.org/search?q={query}, Melbourne, Australia&format=json&limit=1"
        try:
            logger.info(f"Geocoding URL: {geocode_url}")
            response = requests.get(geocode_url, headers={"User-Agent": "ParkingFinder/1.0"}, timeout=10)
            logger.info(f"Geocoding response status: {response.status_code}")
            if response.status_code == 200:
                geo_data = response.json()
                logger.info(f"Geocoding data: {geo_data}")
                if geo_data:
                    lat = float(geo_data[0]['lat'])
                    lng = float(geo_data[0]['lon'])
                    logger.info(f"Geocoded '{query}' to {lat}, {lng}")
                else:
                    logger.warning(f"No geocoding results for query: {query}")
                    return JsonResponse({
                        "error": "Location not found",
                        "message": f"Could not find coordinates for '{query}'. Please try a different location or landmark.",
                        "search_location": search_location,
                        "query": query,
                        "success": False,
                        "results": []
                    }, status=404)
            else:
                logger.error(f"Geocoding API returned status {response.status_code}")
                return JsonResponse({
                    "error": "Geocoding service unavailable",
                    "message": "Unable to convert location to coordinates. Please try again later.",
                    "search_location": search_location,
                    "query": query,
                    "success": False,
                    "results": []
                }, status=503)
        except requests.Timeout:
            logger.error(f"Geocoding timeout for query: {query}")
            return JsonResponse({
                "error": "Request timeout",
                "message": "Location search timed out. Please check your connection and try again.",
                "search_location": search_location,
                "query": query,
                "success": False,
                "results": []
            }, status=408)
        except requests.RequestException as e:
            logger.error(f"Geocoding failed: {e}")
            return JsonResponse({
                "error": "Network error",
                "message": "Unable to connect to location service. Please check your internet connection.",
                "search_location": search_location,
                "query": query,
                "success": False,
                "results": []
            }, status=503)

    # Validate coordinates if provided
    if lat and lng:
        try:
            lat = float(lat)
            lng = float(lng)
        except (ValueError, TypeError) as e:
            logger.error(f"Invalid coordinates: lat={lat}, lng={lng}, error={e}")
            return JsonResponse({
                "error": "Invalid coordinates",
                "message": "The provided coordinates are not valid numbers.",
                "search_location": search_location,
                "query": query,
                "success": False,
                "results": []
            }, status=400)

        search_location = {"lat": lat, "lng": lng}
        logger.info(f"Final coordinates: {lat}, {lng}")

        # CBD bounds info
        cbd_info = get_cbd_info()
        in_bounds = is_in_cbd(lat, lng)
        logger.info(f"Is in CBD: {in_bounds}")
        logger.info(f"CBD boundaries: {cbd_info}")

        if not in_bounds:
            logger.warning(f"Location {lat}, {lng} is outside CBD bounds")
            return JsonResponse({
                "message": "Location is outside Melbourne CBD area",
                "search_location": search_location,
                "cbd_boundaries": cbd_info,
                "query": query,
                "in_cbd": False,
                "success": False,
                "total_count": 0,
                "results": []
            }, safe=False)

        # Get all spots in CBD and build segment stats once
        try:
            all_spots = LiveParkingData.objects.filter(
                lat__isnull=False,
                lon__isnull=False,
                lat__gte=cbd_info["lat_min"],
                lat__lte=cbd_info["lat_max"],
                lon__gte=cbd_info["lng_min"],
                lon__lte=cbd_info["lng_max"]
            )
            logger.info(f"Found {all_spots.count()} total spots in CBD database")

            # NEW: build one lookup of segment counts
            segment_stats = build_segment_stats(all_spots)

            for spot in all_spots:
                if spot.lat and spot.lon:
                    try:
                        dist = haversine(lat, lng, spot.lat, spot.lon)
                        if dist <= 2:  # Within 2km radius
                            normalized_status = normalize_status(spot.status_description)

                            # Handle datetime fields safely
                            last_updated = spot.lastupdated if spot.lastupdated else "Unknown"
                            status_timestamp = spot.status_timestamp if spot.status_timestamp else "Unknown"

                            address = spot.RoadSegmentDescription or f"Parking Spot {spot.kerbsideid}"
                            seg = segment_stats.get(address, {
                                "total": 1, "available": 0, "occupied": 0, "limited": 0, "unknown": 0, "ids": [spot.kerbsideid]
                            })

                            results.append({
                                "kerbsideid": spot.kerbsideid,
                                "address": address,
                                "lat": float(spot.lat),
                                "lng": float(spot.lon),
                                "status": normalized_status,
                                "raw_status": spot.status_description,
                                "distance": round(dist, 2),
                                "last_updated": last_updated,
                                "status_timestamp": status_timestamp,
                                # NEW: segment-level counts & ids
                                "segment_counts": {
                                    "total": seg["total"],
                                    "available": seg["available"],
                                    "occupied": seg["occupied"],
                                    "limited": seg["limited"],
                                    "unknown": seg["unknown"]
                                },
                                "segment_kerbsideids": seg["ids"]
                            })
                    except Exception as spot_error:
                        logger.warning(f"Error processing spot {spot.kerbsideid}: {spot_error}")
                        continue

            logger.info(f"Found {len(results)} spots within 2km of search location")

        except Exception as e:
            logger.error(f"Database query failed: {e}")
            return JsonResponse({
                "error": "Database error",
                "message": "Failed to retrieve parking data from database. Please try again.",
                "search_location": search_location,
                "query": query,
                "success": False,
                "results": []
            }, status=500)

    # Fallback keyword search (when no geo results; still limited to CBD)
    if not results and query:
        logger.info(f"Trying fallback keyword search for: {query}")

        if lat and lng and not is_in_cbd(lat, lng):
            return JsonResponse({
                "message": "No results found and location is outside CBD area",
                "search_location": search_location,
                "query": query,
                "in_cbd": False,
                "success": False,
                "results": []
            }, safe=False)

        try:
            cbd = get_cbd_info()
            matches = LiveParkingData.objects.filter(
                RoadSegmentDescription__icontains=query,
                lat__isnull=False,
                lon__isnull=False,
                lat__gte=cbd["lat_min"],
                lat__lte=cbd["lat_max"],
                lon__gte=cbd["lng_min"],
                lon__lte=cbd["lng_max"]
            )[:50]
            logger.info(f"Keyword search found {matches.count()} matches in CBD")

            # Build stats for this subset (keeps counts consistent even on keyword search)
            segment_stats = build_segment_stats(matches)

            for spot in matches:
                try:
                    normalized_status = normalize_status(spot.status_description)
                    last_updated = spot.lastupdated if spot.lastupdated else "Unknown"
                    status_timestamp = spot.status_timestamp if spot.status_timestamp else "Unknown"
                    address = spot.RoadSegmentDescription or f"Parking Spot {spot.kerbsideid}"
                    seg = segment_stats.get(address, {
                        "total": 1, "available": 0, "occupied": 0, "limited": 0, "unknown": 0, "ids": [spot.kerbsideid]
                    })

                    results.append({
                        "kerbsideid": spot.kerbsideid,
                        "address": address,
                        "lat": float(spot.lat),
                        "lng": float(spot.lon),
                        "status": normalized_status,
                        "raw_status": spot.status_description,
                        "distance": "?",
                        "last_updated": last_updated,
                        "status_timestamp": status_timestamp,
                        # NEW: segment-level counts & ids
                        "segment_counts": {
                            "total": seg["total"],
                            "available": seg["available"],
                            "occupied": seg["occupied"],
                            "limited": seg["limited"],
                            "unknown": seg["unknown"]
                        },
                        "segment_kerbsideids": seg["ids"]
                    })
                except Exception as spot_error:
                    logger.warning(f"Error processing keyword search spot {spot.kerbsideid}: {spot_error}")
                    continue

        except Exception as e:
            logger.error(f"Keyword search failed: {e}")
            return JsonResponse({
                "error": "Search failed",
                "message": "Unable to search for parking spots. Please try again.",
                "search_location": search_location,
                "query": query,
                "success": False,
                "results": []
            }, status=500)

    # Sort results by availability then distance
    def sort_key(spot):
        status_priority = {
            'Available': 0,
            'Limited': 1,
            'Unknown': 2,
            'Occupied': 3
        }.get(spot['status'], 4)
        distance = float(spot['distance']) if spot['distance'] != '?' else 999
        return (status_priority, distance)

    if results:
        results.sort(key=sort_key)

    # Status summary (all categories)
    status_summary = {'Available': 0, 'Occupied': 0, 'Limited': 0, 'Unknown': 0}
    for spot in results:
        status_summary[spot['status']] = status_summary.get(spot['status'], 0) + 1

    response_data = {
        "total_count": len(results),
        "search_location": search_location,
        "query": query,
        "in_cbd": is_in_cbd(lat, lng) if (lat and lng) else None,
        "cbd_boundaries": get_cbd_info(),
        "status_summary": status_summary,
        "results": results,
        "success": True,
        "message": "Success" if results else (
            "No parking spots found in this CBD area" if (lat and lng and is_in_cbd(lat, lng))
            else "Location outside CBD or no results"
        )
    }
    return JsonResponse(response_data, safe=False)

# Map data endpoint for filtered results
@api_view(['GET'])
def get_map_data(request):
    """Get parking data formatted for map display with filtering support"""
    lat = request.GET.get('lat')
    lng = request.GET.get('lng')
    max_distance = request.GET.get('max_distance', '2')
    status_filter = request.GET.get('status_filter', 'all')  # all, available, limited, occupied, unknown

    try:
        max_distance = float(max_distance)
    except (ValueError, TypeError):
        max_distance = 2.0

    if not lat or not lng:
        return JsonResponse({
            "error": "Latitude and longitude required",
            "success": False
        }, status=400)

    try:
        lat = float(lat)
        lng = float(lng)
    except (ValueError, TypeError):
        return JsonResponse({
            "error": "Invalid latitude or longitude",
            "success": False
        }, status=400)

    if not is_in_cbd(lat, lng):
        return JsonResponse({
            "error": "Location outside Melbourne CBD",
            "success": False,
            "cbd_boundaries": get_cbd_info()
        }, status=400)

    try:
        cbd_info = get_cbd_info()
        all_spots = LiveParkingData.objects.filter(
            lat__isnull=False,
            lon__isnull=False,
            lat__gte=cbd_info["lat_min"],
            lat__lte=cbd_info["lat_max"],
            lon__gte=cbd_info["lng_min"],
            lon__lte=cbd_info["lng_max"]
        )

        map_markers = []
        for spot in all_spots:
            if spot.lat and spot.lon:
                dist = haversine(lat, lng, spot.lat, spot.lon)
                if dist > max_distance:
                    continue
                normalized_status = normalize_status(spot.status_description)
                if status_filter != 'all' and normalized_status.lower() != status_filter.lower():
                    continue

                marker = {
                    "kerbsideid": spot.kerbsideid,
                    "lat": float(spot.lat),
                    "lng": float(spot.lon),
                    "address": spot.RoadSegmentDescription or f"Parking Spot {spot.kerbsideid}",
                    "status": normalized_status,
                    "color": get_status_color(normalized_status),
                    "icon": get_status_icon(normalized_status),
                    "distance": round(dist, 2),
                    "last_updated": spot.lastupdated or "Unknown",
                    "status_timestamp": spot.status_timestamp or "Unknown"
                }
                map_markers.append(marker)

        # Sort by status priority then distance
        map_markers.sort(key=lambda x: (
            {'Available': 0, 'Limited': 1, 'Unknown': 2, 'Occupied': 3}.get(x['status'], 4),
            x['distance']
        ))

        # Calculate summary
        status_counts = {'Available': 0, 'Limited': 0, 'Occupied': 0, 'Unknown': 0}
        for marker in map_markers:
            status_counts[marker['status']] += 1

        return JsonResponse({
            "success": True,
            "search_location": {"lat": lat, "lng": lng},
            "total_markers": len(map_markers),
            "status_summary": status_counts,
            "filters_applied": {
                "max_distance": max_distance,
                "status_filter": status_filter
            },
            "markers": map_markers,
            "cbd_boundaries": cbd_info
        })

    except Exception as e:
        logger.error(f"Error generating map data: {e}")
        return JsonResponse({
            "error": str(e),
            "success": False
        }, status=500)

# Real-time status for a specific bay
@api_view(['GET'])
def get_spot_status(request, kerbside_id):
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

# All available spots in CBD
@api_view(['GET'])
def get_available_spots(request):
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
            if normalized_status == "Available":
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



def normalize_status(status_description):
    """Normalize raw feed to: Available, Occupied, Limited, Unknown"""
    if not status_description:
        return "Unknown"

    status = str(status_description).lower().strip()

    # Available
    if any(w in status for w in ["available", "unoccupied", "free", "vacant", "open"]):
        return "Available"

    # Occupied (IMPORTANT: 'present' in your dataset means a car is there)
    if any(w in status for w in ["occupied", "present", "taken", "full", "busy", "in use"]):
        return "Occupied"

    # Limited / restricted
    if any(w in status for w in ["limited", "partial", "restricted", "loading", "short stay", "permit", "disabled", "clearway"]):
        return "Limited"

    # Unknown / no data
    if any(w in status for w in ["unknown", "no data", "offline", "error", "haven't published"]):
        return "Unknown"

    # Fallback
    return "Unknown"

# Add this new endpoint AFTER the existing get_available_spots function
# Place it around line 650-700 in your views.py file


def debug_static(request):
    """Debug view to check static file configuration"""
    
    static_dirs = getattr(settings, 'STATICFILES_DIRS', [])
    static_url = getattr(settings, 'STATIC_URL', '')
    
    response = f"""
    <h2>Django Static Files Debug</h2>
    <p><strong>STATIC_URL:</strong> {static_url}</p>
    <p><strong>STATICFILES_DIRS:</strong> {static_dirs}</p>
    
    <h3>Files in static directory:</h3>
    """
    
    if static_dirs:
        static_dir = static_dirs[0]
        response += f"<p><strong>Checking directory:</strong> {static_dir}</p>"
        
        if os.path.exists(static_dir):
            files = os.listdir(static_dir)
            response += f"<p><strong>Files found:</strong></p><ul>"
            for file in files:
                response += f"<li>{file}</li>"
            response += "</ul>"
        else:
            response += f"<p><strong>ERROR:</strong> Directory {static_dir} does not exist!</p>"
    else:
        response += "<p><strong>ERROR:</strong> No STATICFILES_DIRS configured!</p>"
    
    return HttpResponse(response)