import React from 'react';
import Logo from '../components/briefing/Logo';

export const ConfirmPage: React.FC = () => {
  return (
    <div style={{
      minHeight: '100vh',
      display: 'flex',
      flexDirection: 'column',
    }}>
      {/* Header */}
      <header style={{
        padding: '24px 32px',
      }}>
        <Logo />
      </header>

      {/* Main Content */}
      <main style={{
        flex: 1,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        padding: '24px',
      }}>
        <div style={{
          maxWidth: '420px',
          width: '100%',
          textAlign: 'center',
        }}>
          <h1 style={{
            fontSize: '24px',
            fontWeight: 600,
            letterSpacing: '-0.01em',
            color: 'var(--color-black)',
            marginBottom: '16px',
          }}>
            We're scanning your inbox.
          </h1>
          <p style={{
            fontSize: '15px',
            color: 'var(--color-gray-600)',
            lineHeight: 1.6,
            marginBottom: '24px',
          }}>
            You'll receive a setup email in the next few minutes listing the newsletters we found. Reply to that email to confirm your sources and tell us what topics you care about.
          </p>
          <p style={{
            fontSize: '14px',
            color: 'var(--color-gray-500)',
          }}>
            Your first brief will arrive the morning after you reply.
          </p>
        </div>
      </main>
    </div>
  );
};

export default ConfirmPage;
