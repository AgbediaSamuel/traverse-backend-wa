import React, { useEffect, useMemo, useState } from 'react';
import { CoverPage } from './components/CoverPage';
import { DayPage } from './components/DayPage';
import { NotesPage } from './components/NotesPage';
import { ParticipantsPage } from './components/ParticipantsPage';
import { NavigationControls } from './components/NavigationControls';
import { endpoints } from './config';

const defaultItineraryData = {
  traveler: "Sheriff",
  destination: "Las Vegas",
  duration: "Three Day Weekend",
  dates: "March 15-17, 2025",
  coverImage: "https://images.unsplash.com/photo-1683645012230-e3a3c1255434?crop=entropy&cs=tinysrgb&fit=max&fm=jpg&ixid=M3w3Nzg4Nzd8MHwxfHNlYXJjaHwxfHxsYXMlMjB2ZWdhcyUyMHN0cmlwJTIwc2t5bGluZSUyMG5pZ2h0fGVufDF8fHx8MTc1ODQ0MTc5M3ww&ixlib=rb-4.1.0&q=80&w=1080&utm_source=figma&utm_medium=referral",
  tripType: null,
  group: null,
  days: [
    {
      dayNumber: 1,
      date: "Friday, March 15",
      activities: [
        {
          time: "12:00 PM",
          title: "Arrival & Check-in",
          location: "Bellagio Hotel & Casino",
          description: "Check into the luxurious Bellagio suite and get settled. Take in the famous fountain views from your room.",
          image: "https://images.unsplash.com/photo-1683645012230-e3a3c1255434?crop=entropy&cs=tinysrgb&fit=max&fm=jpg&ixid=M3w3Nzg4Nzd8MHwxfHNlYXJjaHwxfHxsYXMlMjB2ZWdhcyUyMHN0cmlwJTIwc2t5bGluZSUyMG5pZ2h0fGVufDF8fHx8MTc1ODQ0MTc5M3ww&ixlib=rb-4.1.0&q=80&w=1080&utm_source=figma&utm_medium=referral"
        },
        {
          time: "2:30 PM",
          title: "Late Lunch at Le Cirque",
          location: "Bellagio Hotel",
          description: "Exquisite French cuisine with Strip views. Try the signature tasting menu and celebrate your arrival in style.",
          image: "https://images.unsplash.com/photo-1750943041213-db8328856b48?crop=entropy&cs=tinysrgb&fit=max&fm=jpg&ixid=M3w3Nzg4Nzd8MHwxfHNlYXJjaHwxfHxmaW5lJTIwZGluaW5nJTIwcmVzdGF1cmFudCUyMGVsZWdhbnR8ZW58MXx8fHwxNzU4Mzc1NTk5fDA&ixlib=rb-4.1.0&q=80&w=1080&utm_source=figma&utm_medium=referral"
        },
        {
          time: "6:00 PM",
          title: "Casino Gaming Experience",
          location: "Bellagio Casino Floor",
          description: "Try your luck at the high-limit slots and blackjack tables. Set a budget and enjoy the thrill of Vegas gaming.",
          image: "https://images.unsplash.com/photo-1582603518944-5b55c828487e?crop=entropy&cs=tinysrgb&fit=max&fm=jpg&ixid=M3w3Nzg4Nzd8MHwxfHNlYXJjaHwxfHxjYXNpbm8lMjBzbG90JTIwbWFjaGluZXMlMjB2ZWdhc3xlbnwxfHx8fDE3NTg0NDE3OTN8MA&ixlib=rb-4.1.0&q=80&w=1080&utm_source=figma&utm_medium=referral"
        },
        {
          time: "9:00 PM",
          title: "Cirque du Soleil Show",
          location: "MGM Grand Theater",
          description: "Be amazed by the world-renowned 'O' show featuring incredible acrobatics, artistry, and surrealism in an aquatic stage.",
          image: "https://images.unsplash.com/photo-1635885648209-b30a48f4304e?crop=entropy&cs=tinysrgb&fit=max&fm=jpg&ixid=M3w3Nzg4Nzd8MHwxfHNlYXJjaHwxfHx2ZWdhcyUyMHNob3clMjBlbnRlcnRhaW5tZW50fGVufDF8fHx8MTc1ODQ0MTc5NHww&ixlib=rb-4.1.0&q=80&w=1080&utm_source=figma&utm_medium=referral"
        }
      ]
    },
    {
      dayNumber: 2,
      date: "Saturday, March 16",
      activities: [
        {
          time: "10:00 AM",
          title: "Brunch at Bacchanal Buffet",
          location: "Caesars Palace",
          description: "Legendary Las Vegas buffet experience with over 500 dishes from around the world. Come hungry!",
          image: "https://images.unsplash.com/photo-1755862922067-8a0135afc1bb?crop=entropy&cs=tinysrgb&fit=max&fm=jpg&ixid=M3w3Nzg4Nzd8MHwxfHNlYXJjaHwxfHxidWZmZXQlMjBicnVuY2glMjBmb29kJTIwc3ByZWFkfGVufDF8fHx8MTc1ODQ0MTc5N3ww&ixlib=rb-4.1.0&q=80&w=1080&utm_source=figma&utm_medium=referral"
        },
        {
          time: "1:00 PM",
          title: "Shopping at The Forum Shops",
          location: "Caesars Palace",
          description: "Luxury shopping experience with over 160 stores. Browse designer brands and unique Vegas souvenirs in this Roman-themed mall.",
          image: "https://images.unsplash.com/photo-1572533177115-5bea803c0f49?crop=entropy&cs=tinysrgb&fit=max&fm=jpg&ixid=M3w3Nzg4Nzd8MHwxfHNlYXJjaHwxfHxzaG9wcGluZyUyMG1hbGwlMjBsdXh1cnklMjBicmFuZHN8ZW58MXx8fHwxNzU4NDQxNzk0fDA&ixlib=rb-4.1.0&q=80&w=1080&utm_source=figma&utm_medium=referral"
        },
        {
          time: "4:00 PM",
          title: "Pool Party at Flamingo Go Pool",
          location: "Flamingo Las Vegas",
          description: "Relax and party poolside with DJ music, tropical cocktails, and Vegas energy. Perfect for afternoon sun and socializing.",
          image: "https://images.unsplash.com/photo-1695177823880-c7691f7f99f1?crop=entropy&cs=tinysrgb&fit=max&fm=jpg&ixid=M3w3Nzg4Nzd8MHwxfHNlYXJjaHwxfHxwb29sJTIwcGFydHklMjB2ZWdhcyUyMGRheXxlbnwxfHx8fDE3NTg0NDE3OTd8MA&ixlib=rb-4.1.0&q=80&w=1080&utm_source=figma&utm_medium=referral"
        }
      ]
    },
    {
      dayNumber: 3,
      date: "Sunday, March 17",
      activities: [
        {
          time: "11:00 AM",
          title: "Helicopter Tour of Las Vegas",
          location: "McCarran Airport Helicopter Tours",
          description: "Spectacular 30-minute helicopter flight over the Strip, downtown Vegas, and Red Rock Canyon. Unforgettable aerial views and photo opportunities.",
          image: "https://images.unsplash.com/photo-1597067707867-e0cde9736709?crop=entropy&cs=tinysrgb&fit=max&fm=jpg&ixid=M3w3Nzg4Nzd8MHwxfHNlYXJjaHwxfHxoZWxpY29wdGVyJTIwdmlldyUyMGNpdHklMjBsaWdodHN8ZW58MXx8fHwxNzU4NDQxNzk4fDA&ixlib=rb-4.1.0&q=80&w=1080&utm_source=figma&utm_medium=referral"
        }
      ]
    }
  ],
  notes: [
    "Bring ID - required everywhere in Vegas",
    "Set gambling budget beforehand",
    "Stay hydrated - desert climate",
    "Download hotel app for room access",
    "Keep emergency cash on hand",
    "Check show start times day-of"
  ]
};

export default function App() {
  const [currentPage, setCurrentPage] = useState(0);
  const [data, setData] = useState(defaultItineraryData);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isPrintMode, setIsPrintMode] = useState(false);

  // Map backend document shape to this template's shape
  function mapDocumentToTemplate(doc: any) {
    const placeholderImg = 'https://images.unsplash.com/photo-1500530855697-b586d89ba3ee?q=80&w=1200&auto=format&fit=crop';
    return {
      traveler: doc.traveler_name ?? 'Traveler',
      destination: doc.destination ?? 'Destination',
      duration: doc.duration ?? 'Trip',
      dates: doc.dates ?? '',
      coverImage: doc.cover_image ?? placeholderImg,
      days: (doc.days ?? []).map((day: any, idx: number) => ({
        dayNumber: idx + 1,
        date: day.date ?? '',
        activities: (day.activities ?? []).map((a: any) => ({
          time: a.time ?? '',
          title: a.title ?? '',
          location: a.location ?? '',
          description: a.description ?? '',
          image: a.image ?? placeholderImg,
          // Pass through backend-computed distance to next activity (in kilometers)
          distance_to_next: typeof a.distance_to_next === 'number' ? a.distance_to_next : undefined,
        })),
      })),
      notes: doc.notes ?? [],
      tripType: doc.trip_type ?? null,
      group: doc.group ?? null,
    };
  }

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const itineraryId = params.get('itineraryId');
    const printParam = params.get('print');
    setIsPrintMode(printParam === '1');
    if (!itineraryId) return; // stay on default data

    setLoading(true);
    setError(null);
    fetch(endpoints.itinerary(itineraryId))
      .then(async (res) => {
        if (!res.ok) throw new Error(`failed to load itinerary: ${res.status}`);
        const payload = await res.json();
        const doc = payload.document ?? payload; // support both shapes
        setData(mapDocumentToTemplate(doc));
        setCurrentPage(0);
      })
      .catch((e) => setError(String(e)))
      .finally(() => setLoading(false));
  }, []);

  const isGroupTrip = data.tripType === 'group';
  const hasParticipants = Boolean(data.group?.participants && data.group.participants.length > 0);
  const totalPages = useMemo(() => {
    // Cover + (Participants if present) + days + notes
    return 1 + (hasParticipants ? 1 : 0) + data.days.length + 1;
  }, [data, hasParticipants]);

  const handleNext = () => {
    if (currentPage < totalPages - 1) {
      setCurrentPage(currentPage + 1);
    }
  };

  const handlePrevious = () => {
    if (currentPage > 0) {
      setCurrentPage(currentPage - 1);
    }
  };

  // Render all pages sequentially for print/PDF
  const renderAllPages = () => {
    const pages: JSX.Element[] = [];
    // Cover
    pages.push(
      <div key="cover" className="print-page print-break">
        <CoverPage
          travelerName={data.traveler}
          destination={data.destination}
          duration={data.duration}
          dates={data.dates}
          coverImage={data.coverImage}
          isGroupTrip={isGroupTrip}
          participantCount={data.group?.participants?.length ?? 0}
          printMode
        />
      </div>
    );

    // Participants page (optional)
    if (hasParticipants) {
      pages.push(
        <div key="participants" className="print-page print-break">
          <ParticipantsPage
            participants={data.group!.participants}
            collectPreferences={data.group!.collect_preferences ?? false}
          />
        </div>
      );
    }

    // Day pages
    data.days.forEach((d, idx) => {
      const isLastContentPage = idx === data.days.length - 1 && (data.notes?.length ?? 0) === 0;
      pages.push(
        <div key={`day-${idx}`} className={`print-page ${isLastContentPage ? '' : 'print-break'}`}>
          <DayPage dayNumber={d.dayNumber} date={d.date} activities={d.activities} printMode />
        </div>
      );
    });

    // Notes page (last)
    if (data.notes && data.notes.length > 0) {
      pages.push(
        <div key="notes" className="print-page">
          <NotesPage notes={data.notes} />
        </div>
      );
    }

    return <div>{pages}</div>;
  };

  const renderCurrentPage = () => {
    // Page 0: Cover
    if (currentPage === 0) {
      return (
        <CoverPage
          travelerName={data.traveler}
          destination={data.destination}
          duration={data.duration}
          dates={data.dates}
          coverImage={data.coverImage}
          isGroupTrip={isGroupTrip}
          participantCount={data.group?.participants?.length ?? 0}
        />
      );
    }

    // Page 1: Participants (only if participants exist)
    if (hasParticipants && currentPage === 1) {
      return (
        <ParticipantsPage
          participants={data.group.participants}
          collectPreferences={data.group.collect_preferences ?? false}
        />
      );
    }

    // Days: page offset depends on whether participants page is present
    const daysStartPage = hasParticipants ? 2 : 1;
    const daysCount = data.days.length;
    const daysEndPage = daysStartPage + daysCount - 1;

    if (currentPage >= daysStartPage && currentPage <= daysEndPage) {
      const dayIndex = currentPage - daysStartPage;
      return (
        <DayPage
          dayNumber={data.days[dayIndex].dayNumber}
          date={data.days[dayIndex].date}
          activities={data.days[dayIndex].activities}
        />
      );
    }

    // Last page: Notes
    return <NotesPage notes={data.notes} />;
  };

  return (
    <div className="relative">
      {loading && (
        <div className="fixed inset-0 flex items-center justify-center z-50">
          <div className="bg-white/90 backdrop-blur-sm rounded-xl p-4 shadow">Loading itinerary…</div>
        </div>
      )}
      {error && (
        <div className="fixed inset-0 flex items-center justify-center z-50">
          <div className="bg-red-50 text-red-700 rounded-xl p-4 shadow">{error}</div>
        </div>
      )}
      {isPrintMode ? renderAllPages() : renderCurrentPage()}
      {!isPrintMode && (
        <NavigationControls
          currentPage={currentPage}
          totalPages={totalPages}
          onNext={handleNext}
          onPrevious={handlePrevious}
        />
      )}
    </div>
  );
}