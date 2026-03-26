import React from 'react';

interface TopicCheckboxProps {
  label: string;
  checked: boolean;
  onChange: (checked: boolean) => void;
}

export const TopicCheckbox: React.FC<TopicCheckboxProps> = ({
  label,
  checked,
  onChange
}) => {
  return (
    <label
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: '10px',
        padding: '12px 14px',
        border: `1px solid ${checked ? 'var(--color-accent)' : 'var(--color-gray-200)'}`,
        borderRadius: 'var(--radius-md)',
        cursor: 'pointer',
        backgroundColor: checked ? 'var(--color-accent-light)' : 'var(--color-white)',
        transition: 'all 0.15s ease',
        userSelect: 'none',
      }}
      onMouseEnter={(e) => {
        if (!checked) {
          e.currentTarget.style.borderColor = 'var(--color-gray-300)';
          e.currentTarget.style.backgroundColor = 'var(--color-gray-50)';
        }
      }}
      onMouseLeave={(e) => {
        if (!checked) {
          e.currentTarget.style.borderColor = 'var(--color-gray-200)';
          e.currentTarget.style.backgroundColor = 'var(--color-white)';
        }
      }}
    >
      <input
        type="checkbox"
        checked={checked}
        onChange={(e) => onChange(e.target.checked)}
        style={{
          width: '16px',
          height: '16px',
          accentColor: 'var(--color-accent)',
          cursor: 'pointer',
        }}
      />
      <span style={{
        fontSize: '14px',
        color: 'var(--color-black)',
        fontWeight: checked ? 500 : 400,
      }}>
        {label}
      </span>
    </label>
  );
};

export default TopicCheckbox;
