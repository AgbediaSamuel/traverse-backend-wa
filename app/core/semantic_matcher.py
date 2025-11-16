"""
Semantic similarity matching using sentence transformers for preference-venue matching.
Optimized with batching, improved text representation, and weighted scoring.
"""

from typing import Any

try:
    import numpy as np
    from sentence_transformers import SentenceTransformer

    SEMANTIC_MATCHING_AVAILABLE = True
except ImportError:
    SEMANTIC_MATCHING_AVAILABLE = False
    print(
        "[SemanticMatcher] Warning: sentence-transformers not installed. "
        "Falling back to keyword matching."
    )


class SemanticMatcher:
    """Handles semantic similarity matching using embeddings."""

    def __init__(self, model_name: str = "BAAI/bge-base-en-v1.5"):
        """
        Initialize the semantic matcher with a pre-trained model.

        Args:
            model_name: Name of the sentence transformer model to use
        """
        self.model = None
        self.model_name = model_name
        self._initialize_model()

    def _initialize_model(self):
        """Lazy load the model only when needed."""
        if not SEMANTIC_MATCHING_AVAILABLE:
            return

        try:
            print(f"[SemanticMatcher] Loading model: {self.model_name}")
            # Don't specify device - sentence-transformers will auto-detect
            # (uses GPU if available, CPU otherwise)
            # This works well for Vercel/deployment where GPU may not be available
            self.model = SentenceTransformer(self.model_name)
            # Enable normalization for faster cosine similarity calculation
            # Normalized embeddings allow direct dot product for cosine similarity
            print("[SemanticMatcher] Model loaded successfully")
        except Exception as e:
            print(f"[SemanticMatcher] Error loading model: {e}")
            print("[SemanticMatcher] Will fall back to keyword matching")
            self.model = None

    def is_available(self) -> bool:
        """Check if semantic matching is available."""
        return SEMANTIC_MATCHING_AVAILABLE and self.model is not None

    def encode(
        self, texts: list[str], normalize: bool = True, batch_size: int = 32
    ) -> list[list[float]]:
        """
        Generate embeddings for a list of texts with batching support.

        Args:
            texts: List of text strings to encode
            normalize: Whether to normalize embeddings (faster cosine similarity)
            batch_size: Number of texts to process in each batch

        Returns:
            List of embedding vectors (each is a list of floats)
        """
        if not self.is_available():
            raise RuntimeError("Semantic matching not available")

        if not texts:
            return []

        try:
            # Batch encode with normalization and progress bar disabled for speed
            embeddings = self.model.encode(
                texts,
                convert_to_numpy=True,
                normalize_embeddings=normalize,
                batch_size=batch_size,
                show_progress_bar=False,
            )
            # Convert numpy arrays to lists for JSON serialization
            return [emb.tolist() for emb in embeddings]
        except Exception as e:
            print(f"[SemanticMatcher] Error encoding texts: {e}")
            raise

    def cosine_similarity_batch(
        self, embeddings1: np.ndarray, embeddings2: np.ndarray
    ) -> np.ndarray:
        """
        Calculate cosine similarity between two sets of embeddings in batch.
        Optimized for normalized embeddings (uses dot product directly).

        Args:
            embeddings1: First set of embeddings (numpy array)
            embeddings2: Second set of embeddings (numpy array)

        Returns:
            2D numpy array of similarity scores [len(embeddings1), len(embeddings2)]
        """
        if embeddings1.shape[0] == 0 or embeddings2.shape[0] == 0:
            return np.array([])

        # If embeddings are normalized, cosine similarity = dot product
        # This is much faster than computing norms each time
        try:
            # Compute all pairwise similarities in one operation
            similarities = np.dot(embeddings1, embeddings2.T)

            # Clamp to [0, 1] range (should already be normalized, but safety check)
            similarities = np.clip(similarities, 0.0, 1.0)
            return similarities
        except Exception as e:
            print(f"[SemanticMatcher] Error in batch similarity: {e}")
            return np.zeros((embeddings1.shape[0], embeddings2.shape[0]))

    def cosine_similarity_score(self, embedding1: list[float], embedding2: list[float]) -> float:
        """
        Calculate cosine similarity between two embeddings.
        Optimized for normalized embeddings.

        Args:
            embedding1: First embedding vector
            embedding2: Second embedding vector

        Returns:
            Cosine similarity score between 0.0 and 1.0
        """
        if not embedding1 or not embedding2:
            return 0.0

        try:
            # Convert to numpy arrays
            emb1 = np.array(embedding1)
            emb2 = np.array(embedding2)

            # For normalized embeddings, cosine similarity = dot product
            # This is much faster than computing norms
            similarity = np.dot(emb1, emb2)

            # Clamp to [0, 1] range
            return float(max(0.0, min(1.0, similarity)))
        except Exception as e:
            print(f"[SemanticMatcher] Error calculating similarity: {e}")
            return 0.0

    def _build_venue_text(self, venue: dict[str, Any]) -> str:
        """
        Build comprehensive text representation of a venue.
        Includes name, types, description, and address context.

        Args:
            venue: Venue dictionary

        Returns:
            Combined text string representing the venue
        """
        parts = []

        # Name (most important)
        name = venue.get("name") or ""
        if name:
            parts.append(name)

        # Types (category information)
        types = venue.get("types") or []
        if types:
            # Filter out generic types like "establishment", "point_of_interest"
            filtered_types = [
                t for t in types if t not in ["establishment", "point_of_interest", "location"]
            ]
            if filtered_types:
                parts.extend(filtered_types[:5])  # Limit to top 5 types

        # Address/neighborhood context (if available)
        address = venue.get("address") or venue.get("formatted_address") or ""
        if address:
            # Extract neighborhood/district info from address
            address_parts = address.split(",")
            if len(address_parts) > 1:
                # Usually format: "Street, Neighborhood, City"
                parts.append(address_parts[0].strip())  # Street/neighborhood

        # Description (if available from Google Places details)
        description = venue.get("description") or ""
        if description:
            # Limit description length to avoid token bloat
            parts.append(description[:200])

        return " ".join(parts).strip()

    def match_interests_semantic(
        self,
        venue: dict[str, Any],
        selected_interests: list[str],
        extracted_keywords: list[str],
    ) -> float:
        """
        Calculate semantic similarity score between venue and preferences.
        Single venue version (for backward compatibility).

        Args:
            venue: Venue dictionary
            selected_interests: List of user's selected interests
            extracted_keywords: List of extracted keywords from vibe notes

        Returns:
            Similarity score between 0.0 and 1.0
        """
        results = self.match_interests_batch([venue], selected_interests, extracted_keywords)
        return results[0] if results else 0.0

    def match_interests_batch(
        self,
        venues: list[dict[str, Any]],
        selected_interests: list[str],
        extracted_keywords: list[str],
    ) -> list[float]:
        """
        Calculate semantic similarity scores for multiple venues in batch.
        Much faster than calling match_interests_semantic for each venue.

        Args:
            venues: List of venue dictionaries
            selected_interests: List of user's selected interests
            extracted_keywords: List of extracted keywords from vibe notes

        Returns:
            List of similarity scores (one per venue), between 0.0 and 1.0
        """
        if not self.is_available() or not venues:
            return [0.0] * len(venues)

        # Build venue texts with improved representation
        venue_texts = []
        for venue in venues:
            text = self._build_venue_text(venue)
            if text:
                venue_texts.append(text)
            else:
                venue_texts.append("")  # Empty placeholder

        # Build preference texts with weighted structure
        preference_texts = []
        preference_weights = []  # Track weights for each preference

        # Selected interests (higher weight - these are explicit user choices)
        for interest in selected_interests:
            if interest.strip():
                preference_texts.append(interest.strip())
                preference_weights.append(2.0)  # 2x weight for selected interests

        # Extracted keywords (lower weight - inferred from text)
        if extracted_keywords:
            # Combine keywords into meaningful chunks (max 2 groups of 5 keywords)
            keyword_groups = []
            for i in range(0, min(10, len(extracted_keywords)), 5):
                group = " ".join(extracted_keywords[i : i + 5])
                if group.strip():
                    keyword_groups.append(group.strip())

            for keyword_text in keyword_groups:
                preference_texts.append(keyword_text)
                preference_weights.append(1.0)  # 1x weight for extracted keywords

        if not preference_texts or not any(venue_texts):
            return [0.0] * len(venues)

        try:
            # Batch encode all texts at once (much faster!)
            all_texts = venue_texts + preference_texts
            all_embeddings = self.encode(all_texts, normalize=True, batch_size=32)

            # Split embeddings back into venues and preferences
            venue_embeddings = np.array(all_embeddings[: len(venue_texts)])
            preference_embeddings = np.array(all_embeddings[len(venue_texts) :])

            # Filter out empty venue texts (they'll have zero embeddings)
            valid_venue_mask = np.array([bool(text) for text in venue_texts])

            # Calculate all pairwise similarities in one operation
            # Shape: [num_venues, num_preferences]
            similarities = self.cosine_similarity_batch(venue_embeddings, preference_embeddings)

            # Apply weighted aggregation
            scores = []
            for i, venue in enumerate(venues):
                if not valid_venue_mask[i]:
                    scores.append(0.0)
                    continue

                # Get similarities for this venue
                venue_similarities = similarities[i]

                # Weighted average: apply weights to each preference's similarity
                weighted_sum = 0.0
                total_weight = 0.0

                for j, weight in enumerate(preference_weights):
                    sim = float(venue_similarities[j])
                    weighted_sum += sim * weight
                    total_weight += weight

                if total_weight > 0:
                    weighted_avg = weighted_sum / total_weight
                else:
                    weighted_avg = float(np.max(venue_similarities))  # Fallback to max

                # Also track max similarity for strong matches
                max_sim = float(np.max(venue_similarities))

                # Hybrid scoring: combine weighted average with max
                # This balances overall relevance with strong individual matches
                hybrid_score = 0.6 * weighted_avg + 0.4 * max_sim

                # Improved normalization: percentile-based scaling
                # Semantic similarities are typically in the 0.3-0.7 range for good matches
                # Scale to make them more comparable to keyword matches
                if hybrid_score > 0.6:
                    # Strong match: boost it
                    normalized_score = min(1.0, hybrid_score * 1.15)
                elif hybrid_score > 0.4:
                    # Medium match: slight boost
                    normalized_score = min(1.0, hybrid_score * 1.05)
                else:
                    # Weak match: keep as-is
                    normalized_score = hybrid_score

                scores.append(normalized_score)

            return scores

        except Exception as e:
            print(f"[SemanticMatcher] Error in batch matching: {e}")
            return [0.0] * len(venues)


# Global instance (lazy-loaded)
_semantic_matcher = None


def get_semantic_matcher() -> SemanticMatcher:
    """Get or create the global semantic matcher instance."""
    global _semantic_matcher
    if _semantic_matcher is None:
        _semantic_matcher = SemanticMatcher()
    return _semantic_matcher
