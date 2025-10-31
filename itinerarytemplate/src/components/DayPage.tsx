import { ImageWithFallback } from './figma/ImageWithFallback';
import { Clock, MapPin } from 'lucide-react';

interface Activity {
  time: string;
  title: string;
  location: string;
  description: string;
  image: string;
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
        <div className="text-center mb-12">
          <h1 className="text-5xl mb-2 bg-gradient-to-r from-purple-600 to-pink-600 bg-clip-text text-transparent">
            Day {dayNumber}
          </h1>
          <p className="text-xl text-gray-600">{date}</p>
        </div>
        
        {/* Activities */}
        <div className="space-y-8 mb-12">
          {activities.map((activity, index) => (
            <div key={index} className="relative">
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
          ))}
        </div>
      </div>
    </div>
  );
}