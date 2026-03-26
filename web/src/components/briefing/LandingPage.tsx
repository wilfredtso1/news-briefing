import React from 'react';
import { Link } from 'react-router-dom';
import { Mail, Inbox, MessageSquare } from 'lucide-react';

const GoogleIcon = () => (
  <svg viewBox="0 0 24 24" width="18" height="18">
    <path
      fill="#4285F4"
      d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"
    />
    <path
      fill="#34A853"
      d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"
    />
    <path
      fill="#FBBC05"
      d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"
    />
    <path
      fill="#EA4335"
      d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"
    />
  </svg>
);

export default function LandingPage() {
  return (
    <div className="page-container">
      <div className="content-wrapper">
        <header className="logo">
          <Link to="/" className="logo-text">briefing</Link>
        </header>

        <section className="hero">
          <h1>Your newsletters, synthesized.</h1>
          <p className="hero-subtitle">
            One email every morning. All your newsletters, deduplicated and distilled.
            Reply to give feedback — the agent learns your preferences over time.
          </p>

          <div className="cta-section">
            <Link to="/setup" className="btn btn-google">
              <GoogleIcon />
              Sign in with Google
            </Link>
            <p className="cta-note">
              Requires Gmail access to read your newsletters and send your brief.
            </p>
          </div>
        </section>

        <section className="how-it-works">
          <h2>How it works</h2>

          <div className="steps">
            <div className="step">
              <div className="step-icon">
                <Inbox size={20} />
              </div>
              <div className="step-content">
                <h3>Connect Gmail</h3>
                <p>Grant read and send access. The agent scans your inbox for newsletters.</p>
              </div>
            </div>

            <div className="step">
              <div className="step-icon">
                <Mail size={20} />
              </div>
              <div className="step-content">
                <h3>Receive your brief</h3>
                <p>Every morning, one clean email. Top stories in full, secondary stories in brief, everything else as a one-liner.</p>
              </div>
            </div>

            <div className="step">
              <div className="step-icon">
                <MessageSquare size={20} />
              </div>
              <div className="step-content">
                <h3>Reply to train it</h3>
                <p>Reply "I want more markets coverage" or "write shorter stories". The agent applies changes on the next run.</p>
              </div>
            </div>
          </div>
        </section>
      </div>

      <footer className="footer">
        <div className="content-wrapper">
          <div className="footer-content">
            <span className="footer-text">Built on Claude</span>
            <a href="/privacy" className="footer-link">Privacy Policy</a>
          </div>
        </div>
      </footer>
    </div>
  );
}
