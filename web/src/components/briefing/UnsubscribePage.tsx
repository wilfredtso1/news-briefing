import React from 'react';
import { Link } from 'react-router-dom';

export default function UnsubscribePage() {
  return (
    <div className="unsubscribe-container">
      <div className="unsubscribe-card">
        <h1>You've been unsubscribed.</h1>
        <p>
          We've stopped sending your daily briefs. Your Gmail connection has been removed.
        </p>
        <Link to="/" className="unsubscribe-link">
          Changed your mind? Sign in again.
        </Link>
      </div>
    </div>
  );
}
