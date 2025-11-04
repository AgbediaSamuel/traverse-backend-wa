import React from 'react';
import { Users } from 'lucide-react';

interface Participant {
  first_name: string;
  last_name: string;
}

interface ParticipantsPageProps {
  participants: Participant[];
  collectPreferences: boolean;
}

export const ParticipantsPage = React.memo(function ParticipantsPage({ participants, collectPreferences }: ParticipantsPageProps) {
  return (
    <div className="min-h-screen bg-gradient-to-br from-indigo-50 to-purple-50 p-8">
      <div className="max-w-4xl mx-auto">
        <div className="text-center mb-12">
          <div className="flex justify-center mb-4">
            <div className="bg-gradient-to-r from-purple-500 to-indigo-500 rounded-full p-4">
              <Users className="w-12 h-12 text-white" />
            </div>
          </div>
          <h1 className="text-5xl mb-4 bg-gradient-to-r from-purple-700 to-indigo-900 bg-clip-text text-transparent">
            Trip Participants
          </h1>
          <p className="text-xl text-gray-600">Traveling together</p>
        </div>

        <div className="grid md:grid-cols-2 gap-8 mb-8">
          {participants.map((participant, index) => {
            const firstInitial = participant.first_name?.charAt(0)?.toUpperCase() || '';
            const lastInitial = participant.last_name?.charAt(0)?.toUpperCase() || '';
            const initials = firstInitial + lastInitial;
            
            return (
              <div 
                key={index} 
                className="relative overflow-hidden bg-white rounded-3xl border-4 border-gray-200 p-6 shadow-lg transition-all duration-300 hover:shadow-2xl hover:scale-105 hover:border-purple-400"
              >
                <div className="flex items-center gap-8">
                  <div className="bg-gradient-to-br from-purple-500 to-indigo-600 rounded-full w-16 h-16 flex items-center justify-center flex-shrink-0">
                    <span className="text-white font-bold text-xl">
                      {initials}
                    </span>
                  </div>
                  <div className="flex-1 min-w-0">
                    <h3 className="text-xl leading-tight font-bold text-gray-900 truncate">
                      {participant.first_name} {participant.last_name}
                    </h3>
                    {index === 0 && (
                      <p className="text-sm text-purple-600 font-medium mt-1">Trip Organizer</p>
                    )}
                  </div>
                </div>
              </div>
            );
          })}
        </div>

        {collectPreferences && (
          <div className="bg-gradient-to-r from-purple-50 to-indigo-50 rounded-xl p-6 border border-purple-200">
            <div className="flex items-start">
              <div className="bg-purple-500 rounded-full p-2 mr-3 mt-1">
                <svg className="w-4 h-4 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
              </div>
              <div>
                <h4 className="font-semibold text-purple-900 mb-1">Preferences Collected</h4>
                <p className="text-gray-700">
                  This itinerary was created taking into account the travel preferences of all participants.
                </p>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
});

