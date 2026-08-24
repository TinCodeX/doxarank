import React, { useState, useEffect } from 'react';
import type { Keyword, SearchEngine, CountryCode, LanguageCode, DeviceType } from '../types/keyword';
import type { Ranking, CreateRankingPayload, UpdateRankingPayload } from '../types/ranking';

interface RankingFormModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSave: (payload: CreateRankingPayload | UpdateRankingPayload) => Promise<void>;
  keyword: Keyword;
  projectName: string;
  rankingToEdit?: Ranking | null;
}

// Helper to format ISO or Date to local datetime string for <input type="datetime-local">
const formatForDateTimeLocal = (dateString?: string): string => {
  const d = dateString ? new Date(dateString) : new Date();
  // Format as YYYY-MM-DDTHH:mm in local time
  const year = d.getFullYear();
  const month = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  const hours = String(d.getHours()).padStart(2, '0');
  const minutes = String(d.getMinutes()).padStart(2, '0');
  return `${year}-${month}-${day}T${hours}:${minutes}`;
};

export const RankingFormModal: React.FC<RankingFormModalProps> = ({
  isOpen,
  onClose,
  onSave,
  keyword,
  projectName,
  rankingToEdit,
}) => {
  const [position, setPosition] = useState<number | string>(1);
  const [rankingUrl, setRankingUrl] = useState('');
  const [searchEngine, setSearchEngine] = useState<SearchEngine>(keyword.search_engine || 'google');
  const [country, setCountry] = useState<CountryCode>(keyword.country || 'ET');
  const [language, setLanguage] = useState<LanguageCode>(keyword.language || 'en');
  const [device, setDevice] = useState<DeviceType>(keyword.device || 'desktop');
  const [recordedAt, setRecordedAt] = useState<string>(formatForDateTimeLocal());

  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  useEffect(() => {
    if (rankingToEdit) {
      setPosition(rankingToEdit.position);
      setRankingUrl(rankingToEdit.ranking_url || '');
      setSearchEngine(rankingToEdit.search_engine);
      setCountry(rankingToEdit.country);
      setLanguage(rankingToEdit.language);
      setDevice(rankingToEdit.device);
      setRecordedAt(formatForDateTimeLocal(rankingToEdit.recorded_at));
    } else {
      setPosition(1);
      setRankingUrl(keyword.project_website_url || '');
      setSearchEngine(keyword.search_engine || 'google');
      setCountry(keyword.country || 'ET');
      setLanguage(keyword.language || 'en');
      setDevice(keyword.device || 'desktop');
      setRecordedAt(formatForDateTimeLocal());
    }
    setError(null);
  }, [rankingToEdit, keyword, isOpen]);

  if (!isOpen) return null;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);

    const posNum = Number(position);
    if (isNaN(posNum) || posNum < 1 || posNum > 1000) {
      setError('Position must be an integer between 1 and 1000.');
      return;
    }

    if (!recordedAt) {
      setError('Recorded timestamp is required.');
      return;
    }

    // Convert local datetime to ISO string
    const isoRecordedAt = new Date(recordedAt).toISOString();

    setIsSubmitting(true);
    try {
      if (rankingToEdit) {
        const updatePayload: UpdateRankingPayload = {
          position: posNum,
          ranking_url: rankingUrl.trim() || undefined,
          search_engine: searchEngine,
          country: country,
          language: language,
          device: device,
          recorded_at: isoRecordedAt,
        };
        await onSave(updatePayload);
      } else {
        const createPayload: CreateRankingPayload = {
          keyword: keyword.id,
          position: posNum,
          ranking_url: rankingUrl.trim() || undefined,
          search_engine: searchEngine,
          country: country,
          language: language,
          device: device,
          recorded_at: isoRecordedAt,
        };
        await onSave(createPayload);
      }
      onClose();
    } catch (err: any) {
      if (err?.data?.non_field_errors) {
        setError(err.data.non_field_errors.join(' '));
      } else if (err?.data && typeof err.data === 'object') {
        const messages = Object.entries(err.data).map(
          ([key, value]) => `${key}: ${Array.isArray(value) ? value.join(', ') : value}`
        );
        setError(messages.join(' | '));
      } else if (err?.data?.detail) {
        setError(err.data.detail);
      } else {
        setError('Failed to save ranking observation. Please verify your inputs.');
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
              {rankingToEdit ? 'Edit Ranking Observation' : 'Record New Ranking'}
            </h3>
            <div style={{ fontSize: '12px', color: '#6b7280', marginTop: '2px' }}>
              Keyword: <strong style={{ color: '#0f172a' }}>"{keyword.keyword}"</strong> · Project: <strong style={{ color: '#1d4ed8' }}>{projectName}</strong>
            </div>
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
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
            <div>
              <label htmlFor="ranking-position" style={labelStyle}>
                Ranking Position (1-1000) *
              </label>
              <input
                id="ranking-position"
                type="number"
                min={1}
                max={1000}
                required
                value={position}
                onChange={(e) => setPosition(e.target.value)}
                placeholder="e.g. 1"
                style={inputStyle}
              />
            </div>

            <div>
              <label htmlFor="ranking-recorded-at" style={labelStyle}>
                Recorded At *
              </label>
              <input
                id="ranking-recorded-at"
                type="datetime-local"
                required
                value={recordedAt}
                onChange={(e) => setRecordedAt(e.target.value)}
                style={inputStyle}
              />
            </div>
          </div>

          <div>
            <label htmlFor="ranking-url" style={labelStyle}>
              Landing Page URL (Optional)
            </label>
            <input
              id="ranking-url"
              type="url"
              placeholder="https://example.com/target-page"
              value={rankingUrl}
              onChange={(e) => setRankingUrl(e.target.value)}
              style={inputStyle}
            />
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
            <div>
              <label htmlFor="ranking-engine" style={labelStyle}>
                Search Engine
              </label>
              <select
                id="ranking-engine"
                value={searchEngine}
                onChange={(e) => setSearchEngine(e.target.value as SearchEngine)}
                style={selectStyle}
              >
                <option value="google">Google</option>
              </select>
            </div>

            <div>
              <label htmlFor="ranking-country" style={labelStyle}>
                Country
              </label>
              <select
                id="ranking-country"
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
              <label htmlFor="ranking-language" style={labelStyle}>
                Language
              </label>
              <select
                id="ranking-language"
                value={language}
                onChange={(e) => setLanguage(e.target.value as LanguageCode)}
                style={selectStyle}
              >
                <option value="en">English (en)</option>
                <option value="am">Amharic (am)</option>
              </select>
            </div>

            <div>
              <label htmlFor="ranking-device" style={labelStyle}>
                Device
              </label>
              <select
                id="ranking-device"
                value={device}
                onChange={(e) => setDevice(e.target.value as DeviceType)}
                style={selectStyle}
              >
                <option value="desktop">Desktop</option>
                <option value="mobile">Mobile</option>
              </select>
            </div>
          </div>

          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '12px', marginTop: '12px' }}>
            <button
              type="button"
              onClick={onClose}
              style={cancelButtonStyle}
            >
              Cancel
            </button>
            <button
              id="save-ranking-button"
              type="submit"
              disabled={isSubmitting}
              style={{
                ...primaryButtonStyle,
                opacity: isSubmitting ? 0.7 : 1,
                cursor: isSubmitting ? 'not-allowed' : 'pointer',
              }}
            >
              {isSubmitting ? 'Saving...' : rankingToEdit ? 'Update Ranking' : 'Record Ranking'}
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
  maxWidth: '520px',
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
  fontSize: '14px',
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
