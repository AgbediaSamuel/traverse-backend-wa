const API_BASE: string = (import.meta as any).env?.VITE_API_BASE_URL || 'http://localhost:8000';

export const endpoints = {
  itinerary: (id: string) => `${API_BASE}/itineraries/${id}`,
};

export { API_BASE };


