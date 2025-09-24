import { ImageWithFallback } from './figma/ImageWithFallback';

interface CoverPageProps {
  travelerName: string;
  destination: string;
  duration: string;
  dates: string;
  coverImage: string;
}

export function CoverPage({ travelerName, destination, duration, dates, coverImage }: CoverPageProps) {
  return (
    <div className="h-screen relative overflow-hidden bg-gradient-to-br from-purple-900 via-blue-900 to-indigo-900">
      {/* Background Image */}
      <div className="absolute inset-0">
        <ImageWithFallback 
          src={coverImage}
          alt={destination}
          className="w-full h-full object-cover opacity-40"
        />
        <div className="absolute inset-0 bg-gradient-to-t from-black/60 via-transparent to-black/20"></div>
      </div>
      
      {/* Content */}
      <div className="relative z-10 h-full flex flex-col justify-center items-center text-center px-8">
        <div className="bg-white/10 backdrop-blur-sm rounded-3xl p-12 max-w-2xl mx-auto border border-white/20">
          <h1 className="text-6xl mb-6 bg-gradient-to-r from-white to-purple-200 bg-clip-text text-transparent">
            {travelerName}'s
          </h1>
          <h2 className="text-4xl mb-4 text-white">
            {duration}
          </h2>
          <h3 className="text-5xl mb-8 text-yellow-300">
            {destination}
          </h3>
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
}