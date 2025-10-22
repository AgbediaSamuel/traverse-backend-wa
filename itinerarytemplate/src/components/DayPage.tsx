import { ImageWithFallback } from './figma/ImageWithFallback';
import { Clock, MapPin, ArrowDown } from 'lucide-react';

interface Activity {
  time: string;
  title: string;
  location: string;
  description: string;
  image: string;
  distance_to_next?: number; // Distance in kilometers
}

interface DayPageProps {
  dayNumber: number;
  date: string;
  activities: Activity[];
  printMode?: boolean;
}

export function DayPage({ dayNumber, date, activities, printMode = false }: DayPageProps) {
  return (
    <div className={`${printMode ? '' : 'min-h-screen'} bg-gradient-to-br from-slate-50 to-slate-100 p-8`}>
      <div className="max-w-4xl mx-auto">
        {/* Header */}
        <div className="text-center mb-12">
          <h1 className="text-5xl mb-2 bg-gradient-to-r from-purple-600 to-pink-600 bg-clip-text text-transparent">
            Day {dayNumber}
          </h1>
          <p className="text-xl text-gray-600">{date}</p>
        </div>
        
        {/* Activities */}
        <div className="space-y-8 mb-12">
          {activities.map((activity, index) => (
            <>
              <div key={index} className="relative">
                <div className="bg-white rounded-2xl shadow-lg hover:shadow-xl transition-shadow p-6 relative z-10">
                <div className="space-y-4">
                  {/* Large hero image */}
                  <div className="relative h-80 rounded-xl overflow-hidden">
                    <ImageWithFallback 
                      src={activity.image}
                      alt={activity.title}
                      className="w-full h-full object-cover"
                    />
                    {/* Subtle bottom gradient to keep text readable without dimming entire image */}
                    <div className="absolute inset-x-0 bottom-0 h-24 bg-gradient-to-t from-black/25 to-transparent"></div>
                    <div className="absolute bottom-4 left-4 right-4 text-white flex items-center justify-between">
                      <div className="flex items-center space-x-2">
                        <div className="w-8 h-8 bg-white/20 backdrop-blur-sm rounded-full flex items-center justify-center">
                          <Clock className="w-4 h-4" />
                        </div>
                        <span className="text-sm font-medium">{activity.time}</span>
                      </div>
                      {/* Optional title overlay for better context */}
                      <span className="text-sm font-medium truncate max-w-[60%] text-white/95">
                        {activity.title}
                      </span>
                    </div>
                  </div>
                  
                  {/* Content below image */}
                  <div className="pt-2">
                    <h3 className="text-xl mb-2 text-gray-800">{activity.title}</h3>
                    <div className="flex items-center text-gray-600 mb-3">
                      <MapPin className="w-4 h-4 mr-1" />
                      <span className="text-sm">{activity.location}</span>
                    </div>
                    <p className="text-gray-700 mb-1">{activity.description}</p>
                  </div>
                </div>
              </div>
              </div>
              
              {/* Distance indicator - only show if next activity exists and has distance */}
              {activity.distance_to_next !== undefined && activity.distance_to_next !== null && index < activities.length - 1 && (
                <div className="flex items-center justify-center -mt-4 -mb-4">
                  <div className="flex items-center gap-2 bg-gradient-to-r from-purple-50 to-pink-50 px-4 py-2 rounded-full border border-purple-200 shadow-sm">
                    <ArrowDown className="w-4 h-4 text-purple-600" />
                    <span className="text-sm font-medium text-gray-700">
                      {activity.distance_to_next} km ({(activity.distance_to_next * 0.621371).toFixed(1)} mi)
                    </span>
                  </div>
                </div>
              )}
            </>
          ))}
        </div>
      </div>
    </div>
  );
}