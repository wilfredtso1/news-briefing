import React from 'react';

interface LogoProps {
  className?: string;
}

export const Logo: React.FC<LogoProps> = ({ className }) => {
  return (
    <a
      href="/"
      className={className}
      style={{
        display: 'flex',
        alignItems: 'center',
        textDecoration: 'none',
        color: 'var(--color-black)',
      }}
    >
      <span style={{
        fontWeight: 600,
        fontSize: '16px',
        letterSpacing: '-0.02em'
      }}>
        Brief
      </span>
    </a>
  );
};

export default Logo;
