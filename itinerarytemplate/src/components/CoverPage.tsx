import React from 'react';
import { ImageWithFallback } from './figma/ImageWithFallback';

interface CoverPageProps {
  tripName: string;
  travelerName: string;
  destination: string;
  duration: string;
  dates: string;
  coverImage: string;
  isGroupTrip?: boolean;
  participantCount?: number;
}

export const CoverPage = React.memo(function CoverPage({ tripName, travelerName, destination, duration, dates, coverImage, isGroupTrip, participantCount, printMode = false }: CoverPageProps) {
  return (
    <div className="h-screen relative overflow-hidden bg-gradient-to-br from-purple-900 via-blue-900 to-indigo-900">
      {/* Background Image */}
      <div className="absolute inset-0">
        <ImageWithFallback 
          src={coverImage}
          alt={destination}
          className="w-full h-full object-cover opacity-40"
          loading="eager"
        />
        <div className="absolute inset-0 bg-gradient-to-t from-black/60 via-transparent to-black/20"></div>
      </div>
      
      {/* Content */}
      <div className="relative z-10 h-full flex flex-col justify-center items-center text-center px-8">
        <div className="bg-white/10 backdrop-blur-sm rounded-3xl p-12 max-w-2xl mx-auto border border-white/20">
          {isGroupTrip && (
            <div className="inline-flex items-center bg-purple-500/80 backdrop-blur-sm px-4 py-2 rounded-full mb-4">
              <svg className="w-5 h-5 text-white mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0zm6 3a2 2 0 11-4 0 2 2 0 014 0zM7 10a2 2 0 11-4 0 2 2 0 014 0z" />
              </svg>
              <span className="text-white font-semibold">Group Trip{typeof participantCount === 'number' ? ` · ${participantCount} ${participantCount === 1 ? 'Traveler' : 'Travelers'}` : ''}</span>
            </div>
          )}
          <h1 className="text-5xl mb-6 bg-gradient-to-r from-white to-purple-200 bg-clip-text text-transparent">
            {tripName}
              </h1>
              <h2 className="text-5xl mb-8 text-yellow-300">
                {destination}
              </h2>
          <div className="text-xl text-purple-200 mb-8">
            {dates}
          </div>
          <div className="w-24 h-1 bg-gradient-to-r from-purple-400 to-pink-400 mx-auto rounded-full"></div>
        </div>
      </div>
      
      {/* Decorative Elements */}
      <div className="absolute top-10 left-10 w-20 h-20 border-2 border-white/30 rounded-full"></div>
      <div className="absolute bottom-20 right-20 w-16 h-16 border-2 border-purple-300/40 rounded-full"></div>
      <div className="absolute top-1/3 right-10 w-6 h-6 bg-yellow-300/60 rounded-full"></div>
    </div>
  );
});