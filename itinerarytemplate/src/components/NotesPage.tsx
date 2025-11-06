import React from 'react';
import { CheckCircle } from 'lucide-react';

interface NotesPageProps {
  notes: string[];
}

export const NotesPage = React.memo(function NotesPage({ notes }: NotesPageProps) {
  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 to-slate-100 p-8">
      <div className="max-w-4xl mx-auto">
        <div className="text-center mb-12">
          <h1 className="text-5xl mb-4 bg-gradient-to-r from-slate-700 to-slate-900 bg-clip-text text-transparent">
            Notes
          </h1>
          <p className="text-xl text-gray-600">Key info for your trip</p>
        </div>

        <div className="grid md:grid-cols-2 gap-4">
          {notes.map((note, index) => (
            <div key={index} className="flex items-start bg-white rounded-xl shadow p-4">
              <CheckCircle className="w-5 h-5 text-indigo-500 mr-2 mt-0.5 flex-shrink-0" />
              <span className="text-gray-700">{note}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
});


