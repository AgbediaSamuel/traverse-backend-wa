import { ChevronLeft, ChevronRight } from 'lucide-react';
import { Button } from './ui/button';

interface NavigationControlsProps {
  currentPage: number;
  totalPages: number;
  onNext: () => void;
  onPrevious: () => void;
}

export function NavigationControls({ currentPage, totalPages, onNext, onPrevious }: NavigationControlsProps) {
  return (
    <div className="fixed bottom-8 left-1/2 transform -translate-x-1/2 z-50">
      <div className="bg-white/80 backdrop-blur-sm rounded-full shadow-lg border border-white/20 p-2 flex items-center space-x-4">
        <Button
          variant="ghost"
          size="sm"
          onClick={onPrevious}
          disabled={currentPage === 0}
          className="rounded-full w-10 h-10 p-0 hover:bg-purple-100"
        >
          <ChevronLeft className="w-5 h-5" />
        </Button>
        
        <div className="flex space-x-2">
          {Array.from({ length: totalPages }, (_, i) => (
            <div
              key={i}
              className={`w-2 h-2 rounded-full transition-colors ${
                i === currentPage ? 'bg-purple-500' : 'bg-gray-300'
              }`}
            />
          ))}
        </div>
        
        <Button
          variant="ghost"
          size="sm"
          onClick={onNext}
          disabled={currentPage === totalPages - 1}
          className="rounded-full w-10 h-10 p-0 hover:bg-purple-100"
        >
          <ChevronRight className="w-5 h-5" />
        </Button>
      </div>
      
      <div className="text-center mt-2">
        <span className="text-sm text-gray-600 bg-white/80 backdrop-blur-sm px-3 py-1 rounded-full">
          {currentPage + 1} of {totalPages}
        </span>
      </div>
    </div>
  );
}