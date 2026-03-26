import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import Logo from '../components/briefing/Logo';
import TimezoneSelect, { getDefaultTimezone } from '../components/briefing/TimezoneSelect';
import Button from '../components/briefing/Button';

export const SetupPage: React.FC = () => {
  const navigate = useNavigate();
  const [isSubmitting, setIsSubmitting] = useState(false);

  // Form state
  const [email, setEmail] = useState('');
  const [timezone, setTimezone] = useState(getDefaultTimezone());

  useEffect(() => {
    fetch('/api/me')
      .then(r => r.json())
      .then(user => setEmail(user.delivery_email || user.email));
  }, []);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsSubmitting(true);

    const res = await fetch('/api/setup', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ delivery_email: email, timezone }),
    });
    if (!res.ok) {
      setIsSubmitting(false);
      return;
    }
    navigate('/confirm');
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

      {/* Main Content */}
      <main style={{
        flex: 1,
        display: 'flex',
        justifyContent: 'center',
        padding: '24px 24px 96px',
      }}>
        <form onSubmit={handleSubmit} style={{
          maxWidth: '400px',
          width: '100%',
        }}>
          <h1 style={{
            fontSize: '24px',
            fontWeight: 600,
            letterSpacing: '-0.01em',
            color: 'var(--color-black)',
            marginBottom: '40px',
          }}>
            Set up your brief
          </h1>

          {/* Delivery Email */}
          <FormField label="Where should your brief be delivered?">
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              style={{
                width: '100%',
                padding: '10px 12px',
                border: '1px solid var(--color-gray-200)',
                borderRadius: 'var(--radius-md)',
                fontSize: '14px',
              }}
            />
          </FormField>

          {/* Timezone */}
          <FormField
            label="Your timezone"
            helper="Used to schedule your morning brief."
          >
            <TimezoneSelect value={timezone} onChange={setTimezone} />
          </FormField>

          {/* Submit */}
          <div style={{ marginTop: '40px' }}>
            <Button
              type="submit"
              variant="primary"
              fullWidth
              isLoading={isSubmitting}
            >
              Set up my briefings →
            </Button>
            <p style={{
              fontSize: '13px',
              color: 'var(--color-gray-500)',
              textAlign: 'center',
              marginTop: '16px',
            }}>
              Next: we'll scan your inbox and send you a setup email.
            </p>
          </div>
        </form>
      </main>
    </div>
  );
};

interface FormFieldProps {
  label: string;
  helper?: string;
  children: React.ReactNode;
}

const FormField: React.FC<FormFieldProps> = ({ label, helper, children }) => (
  <div style={{ marginBottom: '24px' }}>
    <label style={{
      display: 'block',
      fontSize: '14px',
      fontWeight: 500,
      color: 'var(--color-black)',
      marginBottom: '8px',
    }}>
      {label}
    </label>
    {children}
    {helper && (
      <p style={{
        fontSize: '13px',
        color: 'var(--color-gray-500)',
        marginTop: '6px',
      }}>
        {helper}
      </p>
    )}
  </div>
);

export default SetupPage;
