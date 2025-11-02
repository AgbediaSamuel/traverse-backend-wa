import { ImageWithFallback } from './figma/ImageWithFallback';
import { Clock, MapPin, ArrowDown } from 'lucide-react';

interface Activity {
  time: string;
  title: string;
  location: string;
  description: string;
  image: string;
  distance_to_next?: number | null;
}

interface DayPageProps {
  dayNumber: number;
  date: string;
  activities: Activity[];
}

export function DayPage({ dayNumber, date, activities }: DayPageProps) {
  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 to-slate-100 p-8">
      <div className="max-w-4xl mx-auto">
        {/* Header */}
        <div className="text-center mb-12" style={{ overflow: 'visible' }}>
          <h1 className="text-5xl mb-4 bg-gradient-to-r from-purple-600 to-pink-600 bg-clip-text text-transparent" style={{ lineHeight: '1.2', paddingBottom: '0.15em' }}>
            Day {dayNumber}
          </h1>
          <p className="text-xl text-gray-600">{date}</p>
        </div>
        
        {/* Activities */}
        <div className="space-y-8 mb-12">
          {activities.map((activity, index) => (
            <div key={index}>
              <div className="relative">
              {/* Timeline line */}
              {index < activities.length - 1 && (
                <div className="absolute left-6 top-16 w-0.5 h-20 bg-gradient-to-b from-slate-200 to-slate-300 z-0"></div>
              )}
              
              <div className="bg-white rounded-2xl shadow-lg hover:shadow-xl transition-shadow p-6 relative z-10">
                <div className="space-y-4">
                  {/* Large hero image */}
                  <div className="relative h-64 rounded-xl overflow-hidden">
                    <ImageWithFallback 
                      src={activity.image}
                      alt={activity.title}
                      className="w-full h-full object-cover"
                    />
                  </div>
                  
                  {/* Content below image */}
                  <div className="pt-2">
                    <h3 className="text-xl mb-2 text-gray-800">{activity.title}</h3>
                    <div className="flex items-center text-gray-600 mb-2">
                      <Clock className="w-4 h-4 mr-2" />
                      <span className="text-sm font-medium">{activity.time}</span>
                    </div>
                    <div className="flex items-center text-gray-600 mb-3">
                      <MapPin className="w-4 h-4 mr-1" />
                      <span className="text-sm">{activity.location}</span>
                    </div>
                    <p className="text-gray-700 mb-1">{activity.description}</p>
                  </div>
                </div>
              </div>
              </div>
              
              {/* Distance to next activity */}
              {activity.distance_to_next !== null && activity.distance_to_next !== undefined && index < activities.length - 1 && (
                <div className="flex justify-center items-center mt-8">
                  <div className="flex items-center gap-2 px-4 py-2 rounded-full bg-slate-50 border border-slate-200">
                    <ArrowDown className="w-4 h-4 text-blue-600" strokeWidth={2.5} />
                    <span className="text-sm font-medium text-blue-600">
                      {activity.distance_to_next} km ({Math.round(activity.distance_to_next * 0.621371 * 10) / 10} mi)
                    </span>
                  </div>
                </div>
              )}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}