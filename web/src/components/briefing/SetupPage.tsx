import React, { useState, useEffect, KeyboardEvent } from 'react';
import { Link, useNavigate } from 'react-router-dom';

const TOPICS = [
  'Technology',
  'Markets & Finance',
  'Policy & Politics',
  'Health & Science',
  'Venture & Startups',
  'Geopolitics',
  'Sports',
  'Other'
];

const TIMEZONES = [
  'America/New_York',
  'America/Chicago',
  'America/Denver',
  'America/Los_Angeles',
  'America/Anchorage',
  'Pacific/Honolulu',
  'Europe/London',
  'Europe/Paris',
  'Europe/Berlin',
  'Asia/Tokyo',
  'Asia/Shanghai',
  'Asia/Singapore',
  'Australia/Sydney',
  'UTC'
];

function getTimezoneLabel(tz: string): string {
  try {
    const formatter = new Intl.DateTimeFormat('en-US', {
      timeZone: tz,
      timeZoneName: 'short'
    });
    const parts = formatter.formatToParts(new Date());
    const tzPart = parts.find(p => p.type === 'timeZoneName');
    return `${tz.replace(/_/g, ' ')} (${tzPart?.value || ''})`;
  } catch {
    return tz;
  }
}

function detectTimezone(): string {
  try {
    const detected = Intl.DateTimeFormat().resolvedOptions().timeZone;
    if (TIMEZONES.includes(detected)) {
      return detected;
    }
  } catch {}
  return 'America/New_York';
}

export default function SetupPage() {
  const navigate = useNavigate();
  const [email, setEmail] = useState('user@gmail.com');
  const [selectedTopics, setSelectedTopics] = useState<string[]>([]);
  const [timezone, setTimezone] = useState(detectTimezone());
  const [anchors, setAnchors] = useState<string[]>([]);
  const [anchorInput, setAnchorInput] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);

  const toggleTopic = (topic: string) => {
    setSelectedTopics(prev =>
      prev.includes(topic)
        ? prev.filter(t => t !== topic)
        : [...prev, topic]
    );
  };

  const handleAnchorKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if ((e.key === 'Enter' || e.key === ',') && anchorInput.trim()) {
      e.preventDefault();
      const newAnchor = anchorInput.trim().replace(/,$/, '');
      if (newAnchor && !anchors.includes(newAnchor)) {
        setAnchors([...anchors, newAnchor]);
      }
      setAnchorInput('');
    } else if (e.key === 'Backspace' && !anchorInput && anchors.length > 0) {
      setAnchors(anchors.slice(0, -1));
    }
  };

  const removeAnchor = (anchor: string) => {
    setAnchors(anchors.filter(a => a !== anchor));
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsSubmitting(true);

    // Simulate API call
    await new Promise(resolve => setTimeout(resolve, 1000));

    navigate('/account');
  };

  return (
    <div className="page-container">
      <div className="content-wrapper">
        <header className="logo">
          <Link to="/" className="logo-text">briefing</Link>
        </header>

        <section className="form-section">
          <div className="form-header">
            <h1>Set up your briefings</h1>
            <p>Configure how and when you receive your daily digest.</p>
          </div>

          <form onSubmit={handleSubmit}>
            <div className="form-group">
              <label className="form-label">Where should your brief be delivered?</label>
              <input
                type="email"
                className="form-input"
                value={email}
                onChange={e => setEmail(e.target.value)}
                required
              />
            </div>

            <div className="form-group">
              <label className="form-label">What topics matter to you?</label>
              <p className="form-helper" style={{ marginBottom: '8px' }}>
                Used to prioritize stories. You can adjust anytime by replying to a brief.
              </p>
              <div className="checkbox-grid">
                {TOPICS.map(topic => (
                  <label
                    key={topic}
                    className={`checkbox-item ${selectedTopics.includes(topic) ? 'selected' : ''}`}
                  >
                    <input
                      type="checkbox"
                      checked={selectedTopics.includes(topic)}
                      onChange={() => toggleTopic(topic)}
                    />
                    <span className="checkbox-label">{topic}</span>
                  </label>
                ))}
              </div>
            </div>

            <div className="form-group">
              <label className="form-label">Your timezone</label>
              <select
                className="form-select"
                value={timezone}
                onChange={e => setTimezone(e.target.value)}
              >
                {TIMEZONES.map(tz => (
                  <option key={tz} value={tz}>
                    {getTimezoneLabel(tz)}
                  </option>
                ))}
              </select>
              <p className="form-helper">
                Your brief arrives when your anchor newsletters land, typically 7–9am.
              </p>
            </div>

            <div className="form-group">
              <label className="form-label">Which newsletters should we wait for before sending?</label>
              <div
                className="tag-input-container"
                onClick={() => document.getElementById('anchor-input')?.focus()}
              >
                {anchors.map(anchor => (
                  <span key={anchor} className="tag">
                    {anchor}
                    <button
                      type="button"
                      className="tag-remove"
                      onClick={() => removeAnchor(anchor)}
                    >
                      ×
                    </button>
                  </span>
                ))}
                <input
                  id="anchor-input"
                  type="text"
                  className="tag-input"
                  value={anchorInput}
                  onChange={e => setAnchorInput(e.target.value)}
                  onKeyDown={handleAnchorKeyDown}
                  placeholder={anchors.length === 0 ? "e.g. Axios AM, The Diff" : ""}
                />
              </div>
              <p className="form-helper">
                The agent sends your brief once these arrive. Leave blank to use defaults (Axios AM, Morning Brew).
              </p>
            </div>

            <div className="form-submit">
              <button type="submit" className="btn btn-primary" disabled={isSubmitting}>
                {isSubmitting ? (
                  <>
                    <span className="spinner"></span>
                    Setting up...
                  </>
                ) : (
                  'Start my briefings'
                )}
              </button>
              <p className="form-submit-note">
                Your first brief will arrive tomorrow morning. Reply to any brief to give feedback.
              </p>
            </div>
          </form>
        </section>
      </div>
    </div>
  );
}
