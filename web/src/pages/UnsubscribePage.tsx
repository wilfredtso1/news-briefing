import React from 'react';

export const UnsubscribePage: React.FC = () => {
  return (
    <div style={{
      minHeight: '100vh',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      padding: '24px',
    }}>
      <div style={{
        maxWidth: '400px',
        width: '100%',
        textAlign: 'center',
      }}>
        <h1 style={{
          fontSize: '24px',
          fontWeight: 600,
          letterSpacing: '-0.01em',
          color: 'var(--color-black)',
          marginBottom: '12px',
        }}>
          You've been unsubscribed.
        </h1>
        <p style={{
          fontSize: '15px',
          color: 'var(--color-gray-600)',
          lineHeight: 1.6,
          marginBottom: '24px',
        }}>
          We've stopped sending your daily briefs. Your Gmail connection has been removed.
        </p>
        <a
          href="/"
          style={{
            fontSize: '14px',
            color: 'var(--color-accent)',
            textDecoration: 'none',
          }}
        >
          Changed your mind? Sign in again.
        </a>
      </div>
    </div>
  );
};

export default UnsubscribePage;
