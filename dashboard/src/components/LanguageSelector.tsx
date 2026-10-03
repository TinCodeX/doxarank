import React, { useState, useRef, useEffect } from 'react';
import { Globe, ChevronDown, Check } from 'lucide-react';
import { useLanguage, type SupportedLanguage } from '../context/LanguageContext';

interface LanguageSelectorProps {
  variant?: 'light' | 'dark';
}

const languages: { code: SupportedLanguage; label: string; nativeName: string }[] = [
  { code: 'en', label: 'English', nativeName: 'English' },
  { code: 'am', label: 'Amharic', nativeName: 'አማርኛ' },
  { code: 'om', label: 'Afaan Oromoo', nativeName: 'Afaan Oromoo' },
];

export const LanguageSelector: React.FC<LanguageSelectorProps> = ({ variant = 'light' }) => {
  const { language, setLanguage, t } = useLanguage();
  const [isOpen, setIsOpen] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);

  const currentLang = languages.find((l) => l.code === language) || languages[0];

  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setIsOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const isDark = variant === 'dark';

  return (
    <div ref={dropdownRef} style={{ position: 'relative', display: 'inline-block' }}>
      <button
        id="language-selector-button"
        type="button"
        onClick={() => setIsOpen(!isOpen)}
        aria-haspopup="listbox"
        aria-expanded={isOpen}
        aria-label={t('header.select_language', 'Select Language')}
        style={{
          display: 'inline-flex',
          alignItems: 'center',
          gap: '6px',
          padding: '6px 10px',
          fontSize: '12px',
          fontWeight: 600,
          borderRadius: '8px',
          cursor: 'pointer',
          transition: 'all 0.15s ease',
          backgroundColor: isDark ? 'rgba(255, 255, 255, 0.08)' : '#f8fafc',
          color: isDark ? '#ffffff' : '#24143C',
          border: isDark ? '1px solid rgba(255, 255, 255, 0.15)' : '1px solid #cbd5e1',
          outline: 'none',
        }}
        onMouseEnter={(e) => {
          e.currentTarget.style.borderColor = '#774DA9';
          if (!isDark) e.currentTarget.style.backgroundColor = '#f6f2fb';
        }}
        onMouseLeave={(e) => {
          e.currentTarget.style.borderColor = isDark ? 'rgba(255, 255, 255, 0.15)' : '#cbd5e1';
          if (!isDark) e.currentTarget.style.backgroundColor = '#f8fafc';
        }}
      >
        <Globe size={14} color={isDark ? '#a372df' : '#774DA9'} />
        <span>{currentLang.nativeName}</span>
        <ChevronDown size={12} style={{ opacity: 0.7, transform: isOpen ? 'rotate(180deg)' : 'none', transition: 'transform 0.15s' }} />
      </button>

      {isOpen && (
        <div
          role="listbox"
          aria-label="Available languages"
          style={{
            position: 'absolute',
            top: 'calc(100% + 4px)',
            right: 0,
            zIndex: 100,
            minWidth: '150px',
            backgroundColor: '#ffffff',
            borderRadius: '8px',
            boxShadow: '0 10px 25px -5px rgba(36, 20, 60, 0.2), 0 4px 6px -2px rgba(0, 0, 0, 0.05)',
            border: '1px solid #e2e8f0',
            padding: '4px',
            display: 'flex',
            flexDirection: 'column',
            gap: '2px',
          }}
        >
          {languages.map((item) => {
            const isSelected = item.code === language;
            return (
              <button
                key={item.code}
                role="option"
                aria-selected={isSelected}
                onClick={() => {
                  setLanguage(item.code);
                  setIsOpen(false);
                }}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  width: '100%',
                  padding: '7px 10px',
                  fontSize: '13px',
                  fontWeight: isSelected ? 700 : 500,
                  color: isSelected ? '#774DA9' : '#0f172a',
                  backgroundColor: isSelected ? '#f6f2fb' : 'transparent',
                  border: 'none',
                  borderRadius: '6px',
                  cursor: 'pointer',
                  textAlign: 'left',
                  transition: 'background-color 0.1s ease',
                }}
                onMouseEnter={(e) => {
                  if (!isSelected) e.currentTarget.style.backgroundColor = '#f8fafc';
                }}
                onMouseLeave={(e) => {
                  if (!isSelected) e.currentTarget.style.backgroundColor = 'transparent';
                }}
              >
                <span>{item.nativeName}</span>
                {isSelected && <Check size={14} color="#774DA9" />}
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
};
