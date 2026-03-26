import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import Logo from '../components/briefing/Logo';
import Button from '../components/briefing/Button';
import ConfirmModal from '../components/briefing/ConfirmModal';

interface User {
  id: string;
  email: string;
  delivery_email: string;
  display_name: string;
  first_name: string;
  timezone: string;
  status: 'active' | 'waiting' | 'paused';
  onboarding_complete: boolean;
  last_brief_at: string | null;
}

export const AccountPage: React.FC = () => {
  const navigate = useNavigate();
  const [showDeleteModal, setShowDeleteModal] = useState(false);
  const [isPausing, setIsPausing] = useState(false);
  const [user, setUser] = useState<User | null>(null);

  useEffect(() => {
    fetch('/api/me')
      .then(r => { if (!r.ok) throw new Error(); return r.json(); })
      .then(setUser)
      .catch(() => navigate('/'));
  }, []);

  const getStatusColor = () => {
    switch (user?.status) {
      case 'active': return 'var(--color-success)';
      case 'waiting': return '#F59E0B'; // amber
      case 'paused': return 'var(--color-gray-400)';
      default: return 'var(--color-gray-400)';
    }
  };

  const getStatusText = () => {
    switch (user?.status) {
      case 'active': return 'Your brief is active.';
      case 'waiting': return 'Waiting for your setup reply.';
      case 'paused': return 'Your brief is paused.';
      default: return 'Your brief is paused.';
    }
  };

  const handlePause = async () => {
    setIsPausing(true);
    await fetch('/api/pause', { method: 'POST' });
    setUser(u => u ? { ...u, status: 'paused' } : u);
    setIsPausing(false);
  };

  const handleDelete = async () => {
    setShowDeleteModal(false);
    await fetch('/api/account', { method: 'DELETE' });
    navigate('/unsubscribe');
  };

  if (!user) return null;

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
        justifyContent: 'center',
        padding: '24px 24px 96px',
      }}>
        <div style={{
          maxWidth: '480px',
          width: '100%',
        }}>
          {/* Greeting */}
          <h1 style={{
            fontSize: '24px',
            fontWeight: 600,
            letterSpacing: '-0.01em',
            color: 'var(--color-black)',
            marginBottom: '32px',
          }}>
            Hey {user.first_name}.
          </h1>

          {/* Status Card */}
          <div style={{
            padding: '20px',
            border: '1px solid var(--color-gray-200)',
            borderRadius: 'var(--radius-lg)',
            marginBottom: '40px',
          }}>
            <div style={{
              display: 'flex',
              alignItems: 'center',
              gap: '8px',
              marginBottom: '16px',
            }}>
              <div style={{
                width: '8px',
                height: '8px',
                borderRadius: '50%',
                backgroundColor: getStatusColor(),
              }} />
              <span style={{
                fontSize: '15px',
                fontWeight: 500,
                color: 'var(--color-black)',
              }}>
                {getStatusText()}
              </span>
            </div>
            <div style={{
              fontSize: '14px',
              color: 'var(--color-gray-600)',
              lineHeight: 1.8,
            }}>
              <p>
                Last brief sent: {user.last_brief_at ? new Date(user.last_brief_at).toLocaleString() : 'No brief sent yet'}
              </p>
              <p>
                Delivering to: {user.delivery_email || user.email}
              </p>
            </div>
          </div>

          {/* How to use it */}
          <section style={{ marginBottom: '48px' }}>
            <h2 style={{
              fontSize: '14px',
              fontWeight: 600,
              color: 'var(--color-black)',
              marginBottom: '16px',
            }}>
              How to use it
            </h2>
            <ul style={{
              listStyle: 'none',
              padding: 0,
              margin: 0,
              fontSize: '14px',
              color: 'var(--color-gray-600)',
              lineHeight: 1.8,
            }}>
              <li style={{
                display: 'flex',
                alignItems: 'flex-start',
                gap: '12px',
                marginBottom: '8px',
              }}>
                <span style={{ color: 'var(--color-gray-400)' }}>•</span>
                <span>Reply <code style={{
                  backgroundColor: 'var(--color-gray-100)',
                  padding: '2px 6px',
                  borderRadius: '4px',
                  fontSize: '13px',
                }}>"read"</code> or <code style={{
                  backgroundColor: 'var(--color-gray-100)',
                  padding: '2px 6px',
                  borderRadius: '4px',
                  fontSize: '13px',
                }}>"done"</code> to acknowledge a brief</span>
              </li>
              <li style={{
                display: 'flex',
                alignItems: 'flex-start',
                gap: '12px',
                marginBottom: '8px',
              }}>
                <span style={{ color: 'var(--color-gray-400)' }}>•</span>
                <span>Reply with feedback like <code style={{
                  backgroundColor: 'var(--color-gray-100)',
                  padding: '2px 6px',
                  borderRadius: '4px',
                  fontSize: '13px',
                }}>"more markets coverage"</code> or <code style={{
                  backgroundColor: 'var(--color-gray-100)',
                  padding: '2px 6px',
                  borderRadius: '4px',
                  fontSize: '13px',
                }}>"shorter stories"</code> to train the agent</span>
              </li>
              <li style={{
                display: 'flex',
                alignItems: 'flex-start',
                gap: '12px',
              }}>
                <span style={{ color: 'var(--color-gray-400)' }}>•</span>
                <span>Reply <code style={{
                  backgroundColor: 'var(--color-gray-100)',
                  padding: '2px 6px',
                  borderRadius: '4px',
                  fontSize: '13px',
                }}>"send brief"</code> to trigger one on demand</span>
              </li>
            </ul>
          </section>

          {/* Danger Zone */}
          <section style={{
            borderTop: '1px solid var(--color-gray-200)',
            paddingTop: '24px',
          }}>
            <h2 style={{
              fontSize: '13px',
              fontWeight: 500,
              color: 'var(--color-gray-500)',
              marginBottom: '16px',
              textTransform: 'uppercase',
              letterSpacing: '0.05em',
            }}>
              Danger zone
            </h2>
            <div style={{
              display: 'flex',
              flexDirection: 'column',
              gap: '12px',
              alignItems: 'flex-start',
            }}>
              <Button
                variant="muted"
                onClick={handlePause}
                isLoading={isPausing}
              >
                {isPausing ? 'Pausing...' : 'Pause briefings'}
              </Button>
              <Button
                variant="danger-link"
                onClick={() => setShowDeleteModal(true)}
              >
                Delete my account
              </Button>
            </div>
          </section>
        </div>
      </main>

      {/* Delete Confirmation Modal */}
      <ConfirmModal
        isOpen={showDeleteModal}
        title="Delete your account?"
        message="This will permanently delete your account and disconnect Gmail. Your preferences and history will be erased. This action cannot be undone."
        confirmLabel="Delete account"
        cancelLabel="Keep my account"
        onConfirm={handleDelete}
        onCancel={() => setShowDeleteModal(false)}
        isDestructive
      />
    </div>
  );
};

export default AccountPage;
