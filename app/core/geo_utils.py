"""
Geographic utilities for venue clustering and distance calculations.
"""

import math
import random
from typing import Any, Dict, List, Optional, Tuple


def haversine_distance(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """
    Calculate the great-circle distance between two points on Earth.

    Args:
        lat1, lng1: Coordinates of point 1
        lat2, lng2: Coordinates of point 2

    Returns:
        Distance in kilometers
    """
    R = 6371  # Earth's radius in kilometers

    # Convert to radians
    lat1_rad = math.radians(lat1)
    lat2_rad = math.radians(lat2)
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)

    # Haversine formula
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(dlng / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    return R * c


def cluster_venues_by_days(
    venues: List[Dict[str, Any]], num_days: int, randomize_start: bool = True
) -> List[List[Dict[str, Any]]]:
    """
    Cluster venues into groups (one per day) based on geographic proximity.
    Uses k-means-like algorithm to minimize intra-cluster distance.

    Args:
        venues: List of venue dicts with 'lat' and 'lng' keys
        num_days: Number of clusters (days)
        randomize_start: Whether to randomize initial cluster centers

    Returns:
        List of venue lists, one per day
    """
    # Filter venues with valid coordinates
    valid_venues = [v for v in venues if v.get("lat") and v.get("lng")]

    if not valid_venues:
        # No valid coords - distribute evenly
        return distribute_evenly(venues, num_days)

    if num_days >= len(valid_venues):
        # More days than venues - one venue per day
        return [[v] for v in venues[:num_days]] + [[] for _ in range(num_days - len(venues))]

    # Initialize cluster centers
    if randomize_start:
        centers = random.sample(valid_venues, num_days)
    else:
        # Spread centers across the venue list
        step = len(valid_venues) // num_days
        centers = [valid_venues[i * step] for i in range(num_days)]

    # K-means-like clustering (3 iterations)
    for _ in range(3):
        # Assign each venue to nearest center
        clusters: List[List[Dict[str, Any]]] = [[] for _ in range(num_days)]

        for venue in valid_venues:
            v_lat = venue["lat"]
            v_lng = venue["lng"]

            # Find nearest center
            min_dist = float("inf")
            nearest_idx = 0

            for i, center in enumerate(centers):
                c_lat = center["lat"]
                c_lng = center["lng"]
                dist = haversine_distance(v_lat, v_lng, c_lat, c_lng)

                if dist < min_dist:
                    min_dist = dist
                    nearest_idx = i

            clusters[nearest_idx].append(venue)

        # Update centers to cluster centroids
        for i, cluster in enumerate(clusters):
            if cluster:
                avg_lat = sum(v["lat"] for v in cluster) / len(cluster)
                avg_lng = sum(v["lng"] for v in cluster) / len(cluster)

                # Find venue closest to centroid as new center
                min_dist = float("inf")
                best_venue = cluster[0]

                for v in cluster:
                    dist = haversine_distance(v["lat"], v["lng"], avg_lat, avg_lng)
                    if dist < min_dist:
                        min_dist = dist
                        best_venue = v

                centers[i] = best_venue

    # Final assignment
    final_clusters: List[List[Dict[str, Any]]] = [[] for _ in range(num_days)]

    for venue in valid_venues:
        v_lat = venue["lat"]
        v_lng = venue["lng"]

        min_dist = float("inf")
        nearest_idx = 0

        for i, center in enumerate(centers):
            c_lat = center["lat"]
            c_lng = center["lng"]
            dist = haversine_distance(v_lat, v_lng, c_lat, c_lng)

            if dist < min_dist:
                min_dist = dist
                nearest_idx = i

        final_clusters[nearest_idx].append(venue)

    # Handle venues without coordinates (distribute evenly)
    invalid_venues = [v for v in venues if not (v.get("lat") and v.get("lng"))]
    for i, v in enumerate(invalid_venues):
        final_clusters[i % num_days].append(v)

    return final_clusters


def distribute_evenly(venues: List[Dict[str, Any]], num_groups: int) -> List[List[Dict[str, Any]]]:
    """Fallback: distribute venues evenly across groups."""
    groups: List[List[Dict[str, Any]]] = [[] for _ in range(num_groups)]
    for i, v in enumerate(venues):
        groups[i % num_groups].append(v)
    return groups


def optimize_daily_route(venues: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Optimize the order of venues within a day using nearest-neighbor TSP heuristic.

    Args:
        venues: List of venues with lat/lng

    Returns:
        Reordered list of venues
    """
    if len(venues) <= 1:
        return venues

    valid_venues = [v for v in venues if v.get("lat") and v.get("lng")]
    invalid_venues = [v for v in venues if not (v.get("lat") and v.get("lng"))]

    if not valid_venues:
        return venues

    # Start with first venue
    route = [valid_venues[0]]
    remaining = valid_venues[1:]

    # Nearest-neighbor: always pick closest unvisited venue
    while remaining:
        current = route[-1]
        c_lat = current["lat"]
        c_lng = current["lng"]

        min_dist = float("inf")
        nearest = remaining[0]

        for venue in remaining:
            v_lat = venue["lat"]
            v_lng = venue["lng"]
            dist = haversine_distance(c_lat, c_lng, v_lat, v_lng)

            if dist < min_dist:
                min_dist = dist
                nearest = venue

        route.append(nearest)
        remaining.remove(nearest)

    # Append venues without coordinates at the end
    return route + invalid_venues
