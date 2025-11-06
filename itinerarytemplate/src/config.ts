// Use relative path /api when behind nginx reverse proxy
// Falls back to full URL only if VITE_API_BASE_URL is explicitly set
const API_BASE: string = (import.meta as any).env?.VITE_API_BASE_URL || '/api';

export const endpoints = {
  itinerary: (id: string) => `${API_BASE}/itineraries/${id}`,
};

export { API_BASE };


