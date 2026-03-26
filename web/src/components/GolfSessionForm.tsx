import React, { useState, useEffect } from 'react';
import './GolfSessionForm.css';

// Mock data - in production this would come from Supabase via URL params
const mockSessionData = {
  sessionId: 'abc123',
  playerId: 'player456',
  leadName: 'Mike',
  targetDate: 'Saturday, March 14th',
  candidateCourses: ['Bethpage Black', 'Marine Park', 'Dyker Beach'],
  isNewPlayer: true, // Toggle this to show/hide new player fields
  agentPhone: '(555) 123-4567',
};

const timeSlots = [
  { id: '9_10am', label: '9–10 AM' },
  { id: '10_11am', label: '10–11 AM' },
  { id: '11_12pm', label: '11 AM–12 PM' },
  { id: '12_1pm', label: '12–1 PM' },
  { id: '1_2pm', label: '1–2 PM' },
  { id: '2_3pm', label: '2–3 PM' },
];

function GolfSessionForm() {
  const [isAttending, setIsAttending] = useState<boolean | null>(null);
  const [selectedCourses, setSelectedCourses] = useState<string[]>([]);
  const [selectedTimeSlots, setSelectedTimeSlots] = useState<string[]>([]);
  const [playerName, setPlayerName] = useState('');
  const [playerPhone, setPlayerPhone] = useState('');
  const [generalAvailability, setGeneralAvailability] = useState<string[]>([]);
  const [coursePreferences, setCoursePreferences] = useState('');
  const [isSubmitted, setIsSubmitted] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const { leadName, targetDate, candidateCourses, isNewPlayer, agentPhone } = mockSessionData;

  const handleCourseToggle = (course: string) => {
    setSelectedCourses(prev =>
      prev.includes(course) ? prev.filter(c => c !== course) : [...prev, course]
    );
  };

  const handleTimeSlotToggle = (slotId: string) => {
    setSelectedTimeSlots(prev =>
      prev.includes(slotId) ? prev.filter(s => s !== slotId) : [...prev, slotId]
    );
  };

  const handleAvailabilityToggle = (slotId: string) => {
    setGeneralAvailability(prev =>
      prev.includes(slotId) ? prev.filter(s => s !== slotId) : [...prev, slotId]
    );
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsSubmitting(true);

    // Simulate Supabase write
    const formData = {
      sessionId: mockSessionData.sessionId,
      playerId: mockSessionData.playerId,
      status: isAttending ? 'confirmed' : 'declined',
      availableTimeBlocks: selectedTimeSlots,
      approvedCourses: selectedCourses,
      respondedAt: new Date().toISOString(),
      // New player profile data
      ...(isNewPlayer && {
        playerProfile: {
          name: playerName,
          phone: playerPhone,
          generalAvailability,
          coursePreferences: coursePreferences.split(',').map(c => c.trim()).filter(Boolean),
        },
      }),
    };

    console.log('Form submission data:', formData);

    // Simulate API delay
    await new Promise(resolve => setTimeout(resolve, 800));

    setIsSubmitting(false);
    setIsSubmitted(true);
  };

  const isFormValid = () => {
    if (isAttending === null) return false;
    if (isAttending && (selectedCourses.length === 0 || selectedTimeSlots.length === 0)) return false;
    if (isNewPlayer && isAttending && (!playerName.trim() || !playerPhone.trim())) return false;
    return true;
  };

  if (isSubmitted) {
    return (
      <div className="golf-form-container">
        <div className="golf-form-card">
          <div className="success-state">
            <div className="success-icon">
              <svg width="64" height="64" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" />
                <polyline points="22 4 12 14.01 9 11.01" />
              </svg>
            </div>
            <h2>You're all set!</h2>
            <p>
              {isAttending
                ? `${leadName} will get back to you once everyone responds.`
                : `We've let ${leadName} know you can't make it this time.`}
            </p>
            <div className="contact-info">
              <p>Need to make changes? Text the agent at:</p>
              <span className="phone-number">{agentPhone}</span>
            </div>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="golf-form-container">
      <div className="golf-form-card">
        <div className="form-header">
          <div className="golf-icon">⛳</div>
          <h1>Golf Round</h1>
          <p className="subtitle">
            <span className="lead-name">{leadName}</span> is organizing a round for <span className="target-date">{targetDate}</span>
          </p>
        </div>

        <form onSubmit={handleSubmit}>
          {/* Attendance Question */}
          <div className="form-section">
            <h3>Are you in?</h3>
            <div className="attendance-buttons">
              <button
                type="button"
                className={`attendance-btn ${isAttending === true ? 'selected yes' : ''}`}
                onClick={() => setIsAttending(true)}
              >
                <span className="btn-icon">✓</span>
                <span>Yes, I'm in!</span>
              </button>
              <button
                type="button"
                className={`attendance-btn ${isAttending === false ? 'selected no' : ''}`}
                onClick={() => setIsAttending(false)}
              >
                <span className="btn-icon">✕</span>
                <span>Can't make it</span>
              </button>
            </div>
          </div>

          {/* Show rest of form only if attending */}
          {isAttending && (
            <>
              {/* Course Selection */}
              <div className="form-section">
                <h3>Which courses work for you?</h3>
                <p className="section-hint">Select all that you'd be happy playing</p>
                <div className="checkbox-group courses">
                  {candidateCourses.map(course => (
                    <label key={course} className={`checkbox-card ${selectedCourses.includes(course) ? 'checked' : ''}`}>
                      <input
                        type="checkbox"
                        checked={selectedCourses.includes(course)}
                        onChange={() => handleCourseToggle(course)}
                      />
                      <span className="checkbox-indicator">
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round">
                          <polyline points="20 6 9 17 4 12" />
                        </svg>
                      </span>
                      <span className="checkbox-label">{course}</span>
                    </label>
                  ))}
                </div>
              </div>

              {/* Time Slot Selection */}
              <div className="form-section">
                <h3>What tee times work for you?</h3>
                <p className="section-hint">Select all available time windows</p>
                <div className="checkbox-group time-slots-grid">
                  {timeSlots.map(slot => (
                    <label key={slot.id} className={`checkbox-card time-card-compact ${selectedTimeSlots.includes(slot.id) ? 'checked' : ''}`}>
                      <input
                        type="checkbox"
                        checked={selectedTimeSlots.includes(slot.id)}
                        onChange={() => handleTimeSlotToggle(slot.id)}
                      />
                      <span className="checkbox-indicator">
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round">
                          <polyline points="20 6 9 17 4 12" />
                        </svg>
                      </span>
                      <span className="time-slot-label">{slot.label}</span>
                    </label>
                  ))}
                </div>
              </div>

              {/* New Player Profile Section */}
              {isNewPlayer && (
                <div className="form-section profile-section">
                  <div className="profile-header">
                    <h3>Quick profile setup</h3>
                    <span className="new-badge">First time</span>
                  </div>
                  <p className="section-hint">This helps us coordinate future rounds faster</p>

                  <div className="form-field">
                    <label htmlFor="playerName">Your name</label>
                    <input
                      type="text"
                      id="playerName"
                      value={playerName}
                      onChange={e => setPlayerName(e.target.value)}
                      placeholder="What should we call you?"
                      required
                    />
                  </div>

                  <div className="form-field">
                    <label htmlFor="playerPhone">Phone number</label>
                    <input
                      type="tel"
                      id="playerPhone"
                      value={playerPhone}
                      onChange={e => setPlayerPhone(e.target.value)}
                      placeholder="(555) 123-4567"
                      required
                    />
                    <span className="field-hint">We'll use this for future round invites</span>
                  </div>

                  <div className="form-field">
                    <label>General availability</label>
                    <p className="field-hint">When can you typically play golf?</p>
                    <div className="checkbox-group horizontal">
                      {timeSlots.map(slot => (
                        <label key={`general-${slot.id}`} className={`checkbox-pill ${generalAvailability.includes(slot.id) ? 'checked' : ''}`}>
                          <input
                            type="checkbox"
                            checked={generalAvailability.includes(slot.id)}
                            onChange={() => handleAvailabilityToggle(slot.id)}
                          />
                          <span>{slot.label}</span>
                        </label>
                      ))}
                    </div>
                  </div>

                  <div className="form-field">
                    <label htmlFor="coursePrefs">Favorite courses</label>
                    <input
                      type="text"
                      id="coursePrefs"
                      value={coursePreferences}
                      onChange={e => setCoursePreferences(e.target.value)}
                      placeholder="e.g., Bethpage, Pelham Bay, Van Cortlandt"
                    />
                    <span className="field-hint">Comma-separated list of courses you enjoy</span>
                  </div>
                </div>
              )}
            </>
          )}

          {/* Submit Button */}
          <div className="form-actions">
            <button
              type="submit"
              className="submit-btn"
              disabled={!isFormValid() || isSubmitting}
            >
              {isSubmitting ? (
                <span className="loading-state">
                  <span className="spinner"></span>
                  Submitting...
                </span>
              ) : (
                isAttending === false ? 'Let them know' : 'Submit my preferences'
              )}
            </button>
          </div>
        </form>

        <div className="form-footer">
          <p>
            Powered by <strong>Golf Agent</strong> 🤖
          </p>
        </div>
      </div>
    </div>
  );
}

export default GolfSessionForm;
