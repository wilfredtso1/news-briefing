import React, { useState, KeyboardEvent } from 'react';
import { X } from 'lucide-react';

interface TagInputProps {
  tags: string[];
  onChange: (tags: string[]) => void;
  placeholder?: string;
}

export const TagInput: React.FC<TagInputProps> = ({
  tags,
  onChange,
  placeholder = 'Type and press Enter...'
}) => {
  const [inputValue, setInputValue] = useState('');

  const handleKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter' && inputValue.trim()) {
      e.preventDefault();
      if (!tags.includes(inputValue.trim())) {
        onChange([...tags, inputValue.trim()]);
      }
      setInputValue('');
    } else if (e.key === 'Backspace' && !inputValue && tags.length > 0) {
      onChange(tags.slice(0, -1));
    }
  };

  const removeTag = (tagToRemove: string) => {
    onChange(tags.filter(tag => tag !== tagToRemove));
  };

  return (
    <div
      style={{
        display: 'flex',
        flexWrap: 'wrap',
        gap: '8px',
        padding: '10px 12px',
        border: '1px solid var(--color-gray-200)',
        borderRadius: 'var(--radius-md)',
        backgroundColor: 'var(--color-white)',
        minHeight: '44px',
        cursor: 'text',
      }}
      onClick={(e) => {
        const input = e.currentTarget.querySelector('input');
        input?.focus();
      }}
    >
      {tags.map((tag) => (
        <span
          key={tag}
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: '4px',
            padding: '4px 8px',
            backgroundColor: 'var(--color-gray-100)',
            borderRadius: 'var(--radius-sm)',
            fontSize: '13px',
            color: 'var(--color-gray-700)',
          }}
        >
          {tag}
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation();
              removeTag(tag);
            }}
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              padding: 0,
              border: 'none',
              background: 'none',
              cursor: 'pointer',
              color: 'var(--color-gray-500)',
            }}
            onMouseEnter={(e) => {
              e.currentTarget.style.color = 'var(--color-gray-700)';
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.color = 'var(--color-gray-500)';
            }}
          >
            <X size={14} />
          </button>
        </span>
      ))}
      <input
        type="text"
        value={inputValue}
        onChange={(e) => setInputValue(e.target.value)}
        onKeyDown={handleKeyDown}
        placeholder={tags.length === 0 ? placeholder : ''}
        style={{
          flex: 1,
          minWidth: '120px',
          border: 'none',
          outline: 'none',
          fontSize: '14px',
          backgroundColor: 'transparent',
        }}
      />
    </div>
  );
};

export default TagInput;
