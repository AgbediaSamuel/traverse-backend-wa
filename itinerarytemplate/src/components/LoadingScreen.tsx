function Spinner() {
  return (
    <div
      style={{
        width: '48px',
        height: '48px',
        border: '3px solid rgba(139, 92, 246, 0.2)',
        borderTopColor: '#9333ea',
        borderRadius: '50%',
        animation: 'spin 1s linear infinite',
      }}
      role="status"
      aria-label="Loading"
    >
      <span style={{ position: 'absolute', width: '1px', height: '1px', margin: '-1px', overflow: 'hidden', clip: 'rect(0, 0, 0, 0)' }}>
        Loading...
      </span>
    </div>
  );
}

interface LoadingScreenProps {
  message?: string;
}

export default function LoadingScreen({ message }: LoadingScreenProps) {
  return (
    <>
      <style>{`
        @keyframes spin {
          to {
            transform: rotate(360deg);
          }
        }
        
        .gradient-text {
          background: linear-gradient(to right, #9333ea, #ec4899);
          -webkit-background-clip: text;
          -webkit-text-fill-color: transparent;
          background-clip: text;
        }
      `}</style>
      <div
        style={{
          position: 'fixed',
          top: 0,
          left: 0,
          right: 0,
          bottom: 0,
          background: 'linear-gradient(to bottom right, #f8fafc, #f1f5f9)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          fontFamily: 'ui-sans-serif, system-ui, sans-serif, "Apple Color Emoji", "Segoe UI Emoji", "Segoe UI Symbol", "Noto Color Emoji"',
          zIndex: 9999,
        }}
      >
        <div
          style={{
            textAlign: 'center',
            padding: '0 1rem',
            maxWidth: '100%',
            width: '100%',
          }}
        >
          {/* Logo/Brand */}
          <div style={{ marginBottom: '3rem' }}>
            <h1
              className="gradient-text"
              style={{
                fontSize: '3rem',
                fontWeight: 600,
                marginBottom: '0.75rem',
                margin: '0 0 0.75rem 0',
                padding: 0,
                lineHeight: 1.2,
                background: 'linear-gradient(to right, #9333ea, #ec4899)',
                WebkitBackgroundClip: 'text',
                WebkitTextFillColor: 'transparent',
                backgroundClip: 'text',
              }}
            >
              Traverse
            </h1>
            <p
              style={{
                color: '#64748b',
                fontSize: '1.125rem',
                margin: 0,
                padding: 0,
                fontWeight: 400,
                lineHeight: 1.5,
              }}
            >
              Your AI Travel Companion
            </p>
          </div>

          {/* Loading Spinner */}
          <div
            style={{
              marginBottom: '2rem',
              display: 'flex',
              justifyContent: 'center',
            }}
          >
            <Spinner />
          </div>

          {/* Loading Text */}
          <div>
            <p
              style={{
                color: '#64748b',
                fontSize: '1.125rem',
                fontWeight: 400,
                padding: '0 1rem',
                margin: 0,
                lineHeight: 1.5,
              }}
            >
              {message || "Loading your itinerary..."}
            </p>
          </div>
        </div>
      </div>
    </>
  );
}
