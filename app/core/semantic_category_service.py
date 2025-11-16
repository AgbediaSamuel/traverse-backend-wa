"""
Semantic category matching service for matching user preferences to venue categories.
"""

import os
from typing import Any

import numpy as np
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity

# Google Place types (official list)
GOOGLE_PLACE_TYPES = [
    "accounting",
    "airport",
    "amusement_park",
    "aquarium",
    "art_gallery",
    "atm",
    "bakery",
    "bank",
    "bar",
    "beauty_salon",
    "bicycle_store",
    "book_store",
    "bowling_alley",
    "bus_station",
    "cafe",
    "campground",
    "car_dealer",
    "car_rental",
    "car_repair",
    "car_wash",
    "casino",
    "cemetery",
    "church",
    "city_hall",
    "clothing_store",
    "convenience_store",
    "courthouse",
    "dentist",
    "department_store",
    "doctor",
    "drugstore",
    "electrician",
    "electronics_store",
    "embassy",
    "fire_station",
    "florist",
    "funeral_home",
    "furniture_store",
    "gas_station",
    "gym",
    "hair_care",
    "hardware_store",
    "hindu_temple",
    "home_goods_store",
    "hospital",
    "insurance_agency",
    "jewelry_store",
    "laundry",
    "lawyer",
    "library",
    "light_rail_station",
    "liquor_store",
    "local_government_office",
    "locksmith",
    "lodging",
    "meal_delivery",
    "meal_takeaway",
    "mosque",
    "movie_rental",
    "movie_theater",
    "moving_company",
    "museum",
    "night_club",
    "painter",
    "park",
    "parking",
    "pet_store",
    "pharmacy",
    "physiotherapist",
    "plumber",
    "police",
    "post_office",
    "primary_school",
    "real_estate_agency",
    "restaurant",
    "roofing_contractor",
    "rv_park",
    "school",
    "secondary_school",
    "shoe_store",
    "shopping_mall",
    "spa",
    "stadium",
    "storage",
    "store",
    "subway_station",
    "supermarket",
    "synagogue",
    "taxi_stand",
    "tourist_attraction",
    "train_station",
    "transit_station",
    "travel_agency",
    "university",
    "veterinary_care",
    "zoo",
]

MODEL_NAME = "all-MiniLM-L6-v2"


class SemanticCategoryService:
    """Service for semantic category matching using sentence embeddings."""

    def __init__(self):
        self.model: SentenceTransformer | None = None
        self.type_embeddings: Any | None = None
        self._model_loaded = False

    def _load_model(self):
        """Lazy load the SentenceTransformer model and generate type embeddings."""
        if self._model_loaded:
            return

        try:
            self.model = SentenceTransformer(MODEL_NAME)
            # Generate embeddings for all place types (one-time)
            type_descriptions = [
                f"A place of type: {t.replace('_', ' ')}" for t in GOOGLE_PLACE_TYPES
            ]
            self.type_embeddings = self.model.encode(type_descriptions, show_progress_bar=False)
            self._model_loaded = True
        except Exception as e:
            print(f"[SemanticCategoryService] Failed to load model: {e}")
            raise

    def find_relevant_categories(
        self,
        user_preference_text: str,
        valid_city_categories: set[str],
        top_n: int = 10,
    ) -> list[tuple[str, float]]:
        """
        Find the most relevant venue categories for a user's preferences.

        Args:
            user_preference_text: Combined text of user preferences
            valid_city_categories: Set of categories that exist in the destination
            top_n: Number of top categories to return

        Returns:
            List of tuples (category_name, similarity_score) sorted by relevance
        """
        if not self._model_loaded:
            self._load_model()

        if self.model is None or self.type_embeddings is None:
            raise RuntimeError("Model not loaded")

        # Validate input
        if not user_preference_text or not user_preference_text.strip():
            print("[SemanticCategoryService] WARNING: Empty preference text, " "using default")
            user_preference_text = "tourist attractions, popular places"

        # Generate embedding for user preference
        try:
            user_embedding = self.model.encode([user_preference_text])
        except Exception as e:
            print(f"[SemanticCategoryService] ERROR encoding preference: {e}")
            raise

        # Validate embedding
        if user_embedding is None or user_embedding.size == 0:
            print("[SemanticCategoryService] ERROR: Empty embedding generated")
            raise ValueError("Failed to generate embedding")

        # Calculate cosine similarity
        try:
            similarities = cosine_similarity(user_embedding, self.type_embeddings)[0]
        except Exception as e:
            print(f"[SemanticCategoryService] ERROR calculating similarity: {e}")
            raise

        # Validate similarities
        if similarities is None or len(similarities) == 0:
            print("[SemanticCategoryService] ERROR: Empty similarities")
            raise ValueError("Failed to calculate similarities")

        # Check for NaN or inf values
        if np.any(np.isnan(similarities)) or np.any(np.isinf(similarities)):
            print(
                "[SemanticCategoryService] WARNING: NaN or Inf in similarities, " "replacing with 0"
            )
            similarities = np.nan_to_num(similarities, nan=0.0, posinf=0.0, neginf=0.0)

        # Score categories
        scored_categories = list(zip(GOOGLE_PLACE_TYPES, similarities))

        # Filter to only valid city categories
        valid_scored_categories = [
            (cat, score) for cat, score in scored_categories if cat in valid_city_categories
        ]

        if len(valid_scored_categories) == 0:
            print(
                "[SemanticCategoryService] WARNING: No valid categories found, "
                "returning default categories"
            )
            # Return default categories if none match
            default_categories = [
                "tourist_attraction",
                "park",
                "museum",
                "restaurant",
                "cafe",
            ]
            return [(cat, 0.5) for cat in default_categories if cat in valid_city_categories]

        # Sort by similarity (highest first)
        valid_scored_categories.sort(key=lambda x: x[1], reverse=True)

        return valid_scored_categories[:top_n]


# Singleton instance
semantic_category_service = SemanticCategoryService()
