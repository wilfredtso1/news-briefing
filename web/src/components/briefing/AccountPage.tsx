import React, { useState } from 'react';
import { Link } from 'react-router-dom';

interface ConfirmModalProps {
  isOpen: boolean;
  onClose: () => void;
  onConfirm: () => void;
}

function ConfirmModal({ isOpen, onClose, onConfirm }: ConfirmModalProps) {
  if (!isOpen) return null;

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal" onClick={e => e.stopPropagation()}>
        <h3>Delete your account?</h3>
        <p>
          This will permanently remove your account and stop all briefings.
          Your Gmail connection will be revoked.
        </p>
        <div className="modal-actions">
          <button className="btn btn-secondary" onClick={onClose}>
            Cancel
          </button>
          <button className="btn btn-danger" onClick={onConfirm}>
            Delete account
          </button>
        </div>
      </div>
    </div>
  );
}

export default function AccountPage() {
  const [isPaused, setIsPaused] = useState(false);
  const [showDeleteModal, setShowDeleteModal] = useState(false);

  const firstName = 'Alex';
  const email = 'alex@gmail.com';
  const lastBriefDate = 'March 25, 2026';
  const lastBriefTime = '7:42 AM';

  const handlePause = () => {
    setIsPaused(!isPaused);
  };

  const handleDelete = () => {
    // Would navigate to unsubscribe page after API call
    window.location.href = '/unsubscribe';
  };

  return (
    <div className="page-container">
      <div className="content-wrapper">
        <header className="logo">
          <Link to="/" className="logo-text">briefing</Link>
        </header>

        <section className="account-section">
          <h1 className="account-greeting">Hey {firstName}.</h1>

          <div className="status-card">
            <div className="status-header">
              <span className={`status-dot ${isPaused ? 'inactive' : ''}`}></span>
              <span className="status-title">
                {isPaused ? 'Your brief is paused.' : 'Your brief is active.'}
              </span>
            </div>
            <p className="status-detail">Last brief sent: {lastBriefDate} at {lastBriefTime}</p>
            <p className="status-detail">Delivering to: {email}</p>
          </div>

          <div className="how-to-use">
            <h3>How to use it</h3>
            <ul>
              <li>
                Reply <code>read</code> or <code>done</code> to acknowledge a brief
              </li>
              <li>
                Reply with feedback like <code>more markets coverage</code> or <code>shorter stories</code> to train the agent
              </li>
              <li>
                Reply <code>send brief</code> to trigger one on demand
              </li>
            </ul>
          </div>

          <div className="danger-zone">
            <h3>Danger zone</h3>
            <div className="danger-actions">
              <button className="btn btn-muted" onClick={handlePause}>
                {isPaused ? 'Resume briefings' : 'Pause briefings'}
              </button>
              <button
                className="btn-danger-text"
                onClick={() => setShowDeleteModal(true)}
              >
                Delete my account
              </button>
            </div>
          </div>
        </section>
      </div>

      <ConfirmModal
        isOpen={showDeleteModal}
        onClose={() => setShowDeleteModal(false)}
        onConfirm={handleDelete}
      />
    </div>
  );
}
