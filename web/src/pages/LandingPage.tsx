import React from 'react';
import Logo from '../components/briefing/Logo';
import GoogleSignInButton from '../components/briefing/GoogleSignInButton';
import { Mail, Reply, Inbox } from 'lucide-react';

export const LandingPage: React.FC = () => {
  const handleSignIn = () => {
    window.location.href = '/auth/google';
  };

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

      {/* Hero Section */}
      <main style={{
        flex: 1,
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        padding: '48px 24px 96px',
      }}>
        <div style={{
          maxWidth: '640px',
          textAlign: 'center',
        }}>
          <h1 style={{
            fontSize: 'clamp(32px, 5vw, 48px)',
            fontWeight: 600,
            letterSpacing: '-0.02em',
            color: 'var(--color-black)',
            marginBottom: '16px',
            lineHeight: 1.1,
          }}>
            Your newsletters, synthesized.
          </h1>
          <p style={{
            fontSize: '18px',
            color: 'var(--color-gray-600)',
            lineHeight: 1.6,
            marginBottom: '40px',
            maxWidth: '520px',
            marginLeft: 'auto',
            marginRight: 'auto',
          }}>
            One email every morning. All your newsletters, deduplicated and distilled.
            Reply to give feedback — the agent learns your preferences over time.
          </p>

          <div style={{ marginBottom: '16px' }}>
            <GoogleSignInButton onClick={handleSignIn} />
          </div>

          <p style={{
            fontSize: '13px',
            color: 'var(--color-gray-500)',
          }}>
            Requires Gmail access to read your newsletters and send your brief.
          </p>
        </div>

        {/* How it works */}
        <section style={{
          marginTop: '96px',
          maxWidth: '900px',
          width: '100%',
        }}>
          <h2 style={{
            fontSize: '13px',
            fontWeight: 600,
            textTransform: 'uppercase',
            letterSpacing: '0.05em',
            color: 'var(--color-gray-500)',
            textAlign: 'center',
            marginBottom: '48px',
          }}>
            How it works
          </h2>

          <div style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(250px, 1fr))',
            gap: '48px',
          }}>
            <Step
              icon={<Mail size={24} />}
              title="Connect Gmail"
              description="Grant read and send access. The agent scans your inbox for newsletters automatically."
            />
            <Step
              icon={<Reply size={24} />}
              title="Reply to your setup email"
              description="We'll email you a list of what we found. Reply to confirm sources and tell us what topics you care about."
            />
            <Step
              icon={<Inbox size={24} />}
              title="Receive your brief"
              description="Every morning, one clean email. Top stories in full, secondary stories in brief. Reply to keep training it."
            />
          </div>
        </section>
      </main>

      {/* Footer */}
      <footer style={{
        padding: '24px 32px',
        borderTop: '1px solid var(--color-gray-100)',
        display: 'flex',
        justifyContent: 'center',
        fontSize: '13px',
        color: 'var(--color-gray-500)',
      }}>
        <a href="/privacy" style={{ color: 'var(--color-gray-500)' }}>Privacy Policy</a>
      </footer>
    </div>
  );
};

interface StepProps {
  icon: React.ReactNode;
  title: string;
  description: string;
}

const Step: React.FC<StepProps> = ({ icon, title, description }) => (
  <div style={{
    textAlign: 'center',
  }}>
    <div style={{
      width: '48px',
      height: '48px',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      borderRadius: 'var(--radius-lg)',
      backgroundColor: 'var(--color-gray-100)',
      color: 'var(--color-gray-700)',
      margin: '0 auto 16px',
    }}>
      {icon}
    </div>
    <h3 style={{
      fontSize: '16px',
      fontWeight: 600,
      color: 'var(--color-black)',
      marginBottom: '8px',
    }}>
      {title}
    </h3>
    <p style={{
      fontSize: '14px',
      color: 'var(--color-gray-600)',
      lineHeight: 1.6,
    }}>
      {description}
    </p>
  </div>
);

export default LandingPage;
