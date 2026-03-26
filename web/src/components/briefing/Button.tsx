import React from 'react';

interface ButtonProps {
  children: React.ReactNode;
  onClick?: () => void;
  type?: 'button' | 'submit';
  variant?: 'primary' | 'secondary' | 'muted' | 'danger-link';
  isLoading?: boolean;
  disabled?: boolean;
  fullWidth?: boolean;
}

export const Button: React.FC<ButtonProps> = ({
  children,
  onClick,
  type = 'button',
  variant = 'primary',
  isLoading = false,
  disabled = false,
  fullWidth = false,
}) => {
  const getStyles = (): React.CSSProperties => {
    const baseStyles: React.CSSProperties = {
      display: 'inline-flex',
      alignItems: 'center',
      justifyContent: 'center',
      gap: '8px',
      padding: '12px 24px',
      borderRadius: 'var(--radius-md)',
      fontSize: '15px',
      fontWeight: 500,
      cursor: disabled || isLoading ? 'not-allowed' : 'pointer',
      opacity: disabled || isLoading ? 0.7 : 1,
      transition: 'all 0.15s ease',
      width: fullWidth ? '100%' : 'auto',
    };

    switch (variant) {
      case 'primary':
        return {
          ...baseStyles,
          backgroundColor: 'var(--color-accent)',
          color: 'var(--color-white)',
          border: 'none',
        };
      case 'secondary':
        return {
          ...baseStyles,
          backgroundColor: 'var(--color-white)',
          color: 'var(--color-black)',
          border: '1px solid var(--color-gray-200)',
        };
      case 'muted':
        return {
          ...baseStyles,
          backgroundColor: 'var(--color-gray-100)',
          color: 'var(--color-gray-700)',
          border: 'none',
        };
      case 'danger-link':
        return {
          ...baseStyles,
          backgroundColor: 'transparent',
          color: 'var(--color-danger)',
          border: 'none',
          padding: '8px 0',
        };
      default:
        return baseStyles;
    }
  };

  return (
    <button
      type={type}
      onClick={onClick}
      disabled={disabled || isLoading}
      style={getStyles()}
    >
      {isLoading && <Spinner />}
      {children}
    </button>
  );
};

const Spinner: React.FC = () => (
  <svg
    width="16"
    height="16"
    viewBox="0 0 24 24"
    fill="none"
    xmlns="http://www.w3.org/2000/svg"
    style={{ animation: 'spin 1s linear infinite' }}
  >
    <style>
      {`@keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }`}
    </style>
    <circle cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="3" opacity="0.3" />
    <path d="M12 2a10 10 0 0 1 10 10" stroke="currentColor" strokeWidth="3" strokeLinecap="round" />
  </svg>
);

export default Button;
