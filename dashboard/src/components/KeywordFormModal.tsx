import React, { useState, useEffect } from 'react';
import type { Keyword, SearchEngine, CountryCode, LanguageCode, DeviceType, CreateKeywordPayload, UpdateKeywordPayload } from '../types/keyword';

interface KeywordFormModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSave: (payload: CreateKeywordPayload | UpdateKeywordPayload) => Promise<void>;
  projectId: number;
  projectName: string;
  keywordToEdit?: Keyword | null;
}

export const KeywordFormModal: React.FC<KeywordFormModalProps> = ({
  isOpen,
  onClose,
  onSave,
  projectId,
  projectName,
  keywordToEdit,
}) => {
  const [keywordText, setKeywordText] = useState('');
  const [searchEngine, setSearchEngine] = useState<SearchEngine>('google');
  const [country, setCountry] = useState<CountryCode>('ET');
  const [language, setLanguage] = useState<LanguageCode>('en');
  const [device, setDevice] = useState<DeviceType>('desktop');
  const [isActive, setIsActive] = useState<boolean>(true);

  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  useEffect(() => {
    if (keywordToEdit) {
      setKeywordText(keywordToEdit.keyword);
      setSearchEngine(keywordToEdit.search_engine);
      setCountry(keywordToEdit.country);
      setLanguage(keywordToEdit.language);
      setDevice(keywordToEdit.device);
      setIsActive(keywordToEdit.is_active);
    } else {
      setKeywordText('');
      setSearchEngine('google');
      setCountry('ET');
      setLanguage('en');
      setDevice('desktop');
      setIsActive(true);
    }
    setError(null);
  }, [keywordToEdit, isOpen]);

  if (!isOpen) return null;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);

    const trimmed = keywordText.trim();
    if (!trimmed) {
      setError('Keyword text is required.');
      return;
    }

    setIsSubmitting(true);
    try {
      if (keywordToEdit) {
        const updatePayload: UpdateKeywordPayload = {
          keyword: trimmed,
          search_engine: searchEngine,
          country: country,
          language: language,
          device: device,
          is_active: isActive,
        };
        await onSave(updatePayload);
      } else {
        const createPayload: CreateKeywordPayload = {
          project: projectId,
          keyword: trimmed,
          search_engine: searchEngine,
          country: country,
          language: language,
          device: device,
          is_active: isActive,
        };
        await onSave(createPayload);
      }
      onClose();
    } catch (err: any) {
      if (err?.data?.keyword) {
        const msg = Array.isArray(err.data.keyword) ? err.data.keyword.join(' ') : err.data.keyword;
        setError(msg);
      } else if (err?.data?.non_field_errors) {
        setError(err.data.non_field_errors.join(' '));
      } else if (err?.data && typeof err.data === 'object') {
        const messages = Object.entries(err.data).map(
          ([key, value]) => `${key}: ${Array.isArray(value) ? value.join(', ') : value}`
        );
        setError(messages.join(' | '));
      } else {
        setError('Failed to save keyword. Please check your inputs.');
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div style={overlayStyle}>
      <div style={modalStyle}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px' }}>
          <div>
            <h3 style={{ margin: 0, fontSize: '20px', fontWeight: 700, color: '#111827' }}>
              {keywordToEdit ? 'Edit Keyword' : 'Track New Keyword'}
            </h3>
            <span style={{ fontSize: '12px', color: '#6b7280' }}>
              Project: <strong style={{ color: '#1d4ed8' }}>{projectName}</strong>
            </span>
          </div>
          <button
            type="button"
            onClick={onClose}
            style={closeButtonStyle}
          >
            ✕
          </button>
        </div>

        {error && (
          <div style={errorBannerStyle}>
            {error}
          </div>
        )}

        <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
          <div>
            <label htmlFor="keyword-input" style={labelStyle}>
              Keyword / Search Query
            </label>
            <input
              id="keyword-input"
              type="text"
              required
              placeholder="e.g. seo agency ethiopia"
              value={keywordText}
              onChange={(e) => setKeywordText(e.target.value)}
              style={inputStyle}
            />
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
            <div>
              <label htmlFor="keyword-engine" style={labelStyle}>
                Search Engine
              </label>
              <select
                id="keyword-engine"
                value={searchEngine}
                onChange={(e) => setSearchEngine(e.target.value as SearchEngine)}
                style={selectStyle}
              >
                <option value="google">Google</option>
              </select>
            </div>

            <div>
              <label htmlFor="keyword-country" style={labelStyle}>
                Target Country
              </label>
              <select
                id="keyword-country"
                value={country}
                onChange={(e) => setCountry(e.target.value as CountryCode)}
                style={selectStyle}
              >
                <option value="ET">Ethiopia (ET)</option>
              </select>
            </div>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
            <div>
              <label htmlFor="keyword-language" style={labelStyle}>
                Language
              </label>
              <select
                id="keyword-language"
                value={language}
                onChange={(e) => setLanguage(e.target.value as LanguageCode)}
                style={selectStyle}
              >
                <option value="en">English (en)</option>
                <option value="am">Amharic (am)</option>
              </select>
            </div>

            <div>
              <label htmlFor="keyword-device" style={labelStyle}>
                Device
              </label>
              <select
                id="keyword-device"
                value={device}
                onChange={(e) => setDevice(e.target.value as DeviceType)}
                style={selectStyle}
              >
                <option value="desktop">Desktop</option>
                <option value="mobile">Mobile</option>
              </select>
            </div>
          </div>

          {keywordToEdit && (
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginTop: '4px' }}>
              <input
                id="keyword-is-active"
                type="checkbox"
                checked={isActive}
                onChange={(e) => setIsActive(e.target.checked)}
                style={{ width: '16px', height: '16px', cursor: 'pointer' }}
              />
              <label htmlFor="keyword-is-active" style={{ fontSize: '14px', color: '#374151', cursor: 'pointer' }}>
                Active Tracking
              </label>
            </div>
          )}

          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '12px', marginTop: '12px' }}>
            <button
              type="button"
              onClick={onClose}
              style={cancelButtonStyle}
            >
              Cancel
            </button>
            <button
              id="save-keyword-button"
              type="submit"
              disabled={isSubmitting}
              style={{
                ...primaryButtonStyle,
                opacity: isSubmitting ? 0.7 : 1,
                cursor: isSubmitting ? 'not-allowed' : 'pointer',
              }}
            >
              {isSubmitting ? 'Saving...' : keywordToEdit ? 'Update Keyword' : 'Track Keyword'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};

const overlayStyle: React.CSSProperties = {
  position: 'fixed',
  top: 0,
  left: 0,
  right: 0,
  bottom: 0,
  backgroundColor: 'rgba(0, 0, 0, 0.5)',
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'center',
  zIndex: 1000,
  padding: '16px',
};

const modalStyle: React.CSSProperties = {
  backgroundColor: '#ffffff',
  borderRadius: '12px',
  padding: '24px',
  width: '100%',
  maxWidth: '480px',
  boxShadow: '0 20px 25px -5px rgba(0, 0, 0, 0.1), 0 10px 10px -5px rgba(0, 0, 0, 0.04)',
};

const labelStyle: React.CSSProperties = {
  display: 'block',
  fontSize: '14px',
  fontWeight: 600,
  color: '#374151',
  marginBottom: '6px',
};

const inputStyle: React.CSSProperties = {
  width: '100%',
  padding: '10px 12px',
  fontSize: '15px',
  border: '1px solid #d1d5db',
  borderRadius: '6px',
  boxSizing: 'border-box',
  outline: 'none',
};

const selectStyle: React.CSSProperties = {
  width: '100%',
  padding: '10px 12px',
  fontSize: '14px',
  border: '1px solid #d1d5db',
  borderRadius: '6px',
  backgroundColor: '#ffffff',
  color: '#111827',
  boxSizing: 'border-box',
  outline: 'none',
};

const closeButtonStyle: React.CSSProperties = {
  background: 'none',
  border: 'none',
  fontSize: '16px',
  color: '#6b7280',
  cursor: 'pointer',
  padding: '4px',
};

const cancelButtonStyle: React.CSSProperties = {
  padding: '10px 16px',
  backgroundColor: '#f3f4f6',
  color: '#374151',
  border: '1px solid #d1d5db',
  borderRadius: '6px',
  fontSize: '14px',
  fontWeight: 600,
  cursor: 'pointer',
};

const primaryButtonStyle: React.CSSProperties = {
  padding: '10px 18px',
  backgroundColor: '#2563eb',
  color: '#ffffff',
  border: 'none',
  borderRadius: '6px',
  fontSize: '14px',
  fontWeight: 600,
};

const errorBannerStyle: React.CSSProperties = {
  backgroundColor: '#fef2f2',
  color: '#b91c1c',
  padding: '10px 12px',
  borderRadius: '6px',
  fontSize: '13px',
  marginBottom: '16px',
  border: '1px solid #fca5a5',
};
