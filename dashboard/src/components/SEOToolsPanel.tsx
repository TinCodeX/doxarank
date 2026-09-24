import React, { useState, useEffect } from 'react';
import {
  seoToolsApi,
  type MetaTagResult,
  type SchemaResult,
  type SocialPreviewResult,
  type SEOToolsQuotaStatus,
} from '../api/seoTools';

type ToolTab = 'meta' | 'schema' | 'social';

export const SEOToolsPanel: React.FC = () => {
  const [activeTab, setActiveTab] = useState<ToolTab>('meta');
  const [quotaStatus, setQuotaStatus] = useState<SEOToolsQuotaStatus | null>(null);
  const [copiedKey, setCopiedKey] = useState<string | null>(null);

  // Meta Tag Generator State
  const [metaTitle, setMetaTitle] = useState('');
  const [metaDescription, setMetaDescription] = useState('');
  const [metaCanonical, setMetaCanonical] = useState('');
  const [metaRobots, setMetaRobots] = useState('index, follow');
  const [metaAuthor, setMetaAuthor] = useState('');
  const [metaKeywords, setMetaKeywords] = useState('');
  const [metaResult, setMetaResult] = useState<MetaTagResult | null>(null);
  const [metaLoading, setMetaLoading] = useState(false);
  const [metaError, setMetaError] = useState<string | null>(null);

  // Schema Generator State
  const [schemaType, setSchemaType] = useState<'LocalBusiness' | 'Article' | 'Product' | 'FAQ' | 'BreadcrumbList'>('LocalBusiness');
  const [schemaResult, setSchemaResult] = useState<SchemaResult | null>(null);
  const [schemaLoading, setSchemaLoading] = useState(false);
  const [schemaError, setSchemaError] = useState<string | null>(null);

  // Schema Form Fields
  // LocalBusiness
  const [bizName, setBizName] = useState('');
  const [bizUrl, setBizUrl] = useState('');
  const [bizPhone, setBizPhone] = useState('');
  const [bizPrice, setBizPrice] = useState('$$');
  const [bizStreet, setBizStreet] = useState('');
  const [bizCity, setBizCity] = useState('');
  const [bizCountry, setBizCountry] = useState('ET');
  const [bizHours, setBizHours] = useState('Mo-Fr 08:30-17:30');

  // Article
  const [artHeadline, setArtHeadline] = useState('');
  const [artAuthor, setArtAuthor] = useState('');
  const [artDate, setArtDate] = useState(new Date().toISOString().split('T')[0]);
  const [artDesc, setArtDesc] = useState('');
  const [artUrl, setArtUrl] = useState('');
  const [artImage, setArtImage] = useState('');
  const [artPublisher, setArtPublisher] = useState('');

  // Product
  const [prodName, setProdName] = useState('');
  const [prodDesc, setProdDesc] = useState('');
  const [prodImage, setProdImage] = useState('');
  const [prodSku, setProdSku] = useState('');
  const [prodBrand, setProdBrand] = useState('');
  const [prodPrice, setProdPrice] = useState('');
  const [prodCurrency, setProdCurrency] = useState('USD');

  // FAQ
  const [faqItems, setFaqItems] = useState<Array<{ question: string; answer: string }>>([
    { question: 'What is DoxaRank?', answer: 'An autonomous SEO rank tracking and intelligence platform.' },
    { question: 'Does DoxaRank support Ethiopian queries?', answer: 'Yes, with native Amharic keyword tracking on google.com.et.' },
  ]);

  // Breadcrumbs
  const [breadcrumbItems, setBreadcrumbItems] = useState<Array<{ name: string; item: string }>>([
    { name: 'Home', item: 'https://example.com' },
    { name: 'Services', item: 'https://example.com/services' },
    { name: 'SEO Audits', item: 'https://example.com/services/seo-audits' },
  ]);

  // Social Preview State
  const [socialTitle, setSocialTitle] = useState('');
  const [socialDesc, setSocialDesc] = useState('');
  const [socialUrl, setSocialUrl] = useState('');
  const [socialImage, setSocialImage] = useState('');
  const [socialSiteName, setSocialSiteName] = useState('');
  const [socialOgType, setSocialOgType] = useState('website');
  const [socialTwitterCard, setSocialTwitterCard] = useState('summary_large_image');
  const [socialTwitterSite, setSocialTwitterSite] = useState('');
  const [socialResult, setSocialResult] = useState<SocialPreviewResult | null>(null);
  const [socialLoading, setSocialLoading] = useState(false);
  const [socialError, setSocialError] = useState<string | null>(null);

  // Fetch Quota Status
  const refreshQuota = async () => {
    try {
      const data = await seoToolsApi.getQuotaStatus();
      setQuotaStatus(data);
    } catch {
      // Ignored if user not yet authenticated
    }
  };

  useEffect(() => {
    refreshQuota();
  }, []);

  const handleCopy = (text: string, key: string) => {
    navigator.clipboard.writeText(text);
    setCopiedKey(key);
    setTimeout(() => setCopiedKey(null), 2500);
  };

  // --- META ACTIONS ---
  const handleGenerateMeta = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    setMetaLoading(true);
    setMetaError(null);
    try {
      const res = await seoToolsApi.generateMetaTags({
        title: metaTitle,
        description: metaDescription,
        canonical_url: metaCanonical || undefined,
        robots: metaRobots,
        author: metaAuthor || undefined,
        keywords: metaKeywords || undefined,
      });
      setMetaResult(res);
      refreshQuota();
    } catch (err: any) {
      setMetaError(err?.data?.detail || err?.data?.error || 'Failed to generate meta tags.');
    } finally {
      setMetaLoading(false);
    }
  };

  const handleResetMeta = () => {
    setMetaTitle('');
    setMetaDescription('');
    setMetaCanonical('');
    setMetaRobots('index, follow');
    setMetaAuthor('');
    setMetaKeywords('');
    setMetaResult(null);
    setMetaError(null);
  };

  // --- SCHEMA ACTIONS ---
  const handleGenerateSchema = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    setSchemaLoading(true);
    setSchemaError(null);

    let dataPayload: Record<string, any> = {};
    if (schemaType === 'LocalBusiness') {
      dataPayload = {
        name: bizName,
        url: bizUrl || undefined,
        telephone: bizPhone || undefined,
        priceRange: bizPrice || undefined,
        address: {
          streetAddress: bizStreet,
          addressLocality: bizCity,
          addressCountry: bizCountry,
        },
        openingHours: bizHours ? [bizHours] : undefined,
      };
    } else if (schemaType === 'Article') {
      dataPayload = {
        headline: artHeadline,
        author: artAuthor,
        datePublished: artDate,
        description: artDesc || undefined,
        url: artUrl || undefined,
        image: artImage || undefined,
        publisher_name: artPublisher || undefined,
      };
    } else if (schemaType === 'Product') {
      dataPayload = {
        name: prodName,
        description: prodDesc || undefined,
        image: prodImage || undefined,
        sku: prodSku || undefined,
        brand: prodBrand || undefined,
        price: prodPrice || undefined,
        priceCurrency: prodCurrency,
      };
    } else if (schemaType === 'FAQ') {
      dataPayload = {
        items: faqItems.filter((i) => i.question.trim() && i.answer.trim()),
      };
    } else if (schemaType === 'BreadcrumbList') {
      dataPayload = {
        items: breadcrumbItems.filter((i) => i.name.trim() && i.item.trim()),
      };
    }

    try {
      const res = await seoToolsApi.generateSchema({
        schema_type: schemaType,
        data: dataPayload,
      });
      setSchemaResult(res);
      refreshQuota();
    } catch (err: any) {
      setSchemaError(err?.data?.detail || err?.data?.error || 'Failed to generate Schema.org markup.');
    } finally {
      setSchemaLoading(false);
    }
  };

  const handleResetSchema = () => {
    setSchemaResult(null);
    setSchemaError(null);
    setBizName('');
    setBizUrl('');
    setArtHeadline('');
    setProdName('');
  };

  // --- SOCIAL PREVIEW ACTIONS ---
  const handleGenerateSocial = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    setSocialLoading(true);
    setSocialError(null);
    try {
      const res = await seoToolsApi.generateSocialPreview({
        title: socialTitle,
        description: socialDesc,
        url: socialUrl || undefined,
        image_url: socialImage || undefined,
        site_name: socialSiteName || undefined,
        og_type: socialOgType,
        twitter_card: socialTwitterCard,
        twitter_site: socialTwitterSite || undefined,
      });
      setSocialResult(res);
      refreshQuota();
    } catch (err: any) {
      setSocialError(err?.data?.detail || err?.data?.error || 'Failed to generate social preview tags.');
    } finally {
      setSocialLoading(false);
    }
  };

  const handleResetSocial = () => {
    setSocialTitle('');
    setSocialDesc('');
    setSocialUrl('');
    setSocialImage('');
    setSocialSiteName('');
    setSocialTwitterSite('');
    setSocialResult(null);
    setSocialError(null);
  };

  return (
    <section id="seo-tools-section" style={sectionCardStyle}>
      {/* Section Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: '16px', marginBottom: '20px' }}>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <span style={{ fontSize: '20px' }}>🛠️</span>
            <h3 style={{ margin: 0, fontSize: '20px', fontWeight: 700, color: '#111827' }}>
              Core SEO Tools
            </h3>
            <span style={toolBadgeStyle}>BASIC SEO TOOLS</span>
          </div>
          <p style={{ margin: '6px 0 0 0', fontSize: '13px', color: '#6b7280' }}>
            Production-grade metadata and structured data generators for on-page SEO optimization.
          </p>
        </div>

        {/* Quota Indicator */}
        {quotaStatus && (
          <div style={quotaCardStyle}>
            <span style={{ fontSize: '11px', fontWeight: 700, textTransform: 'uppercase', color: '#64748b' }}>
              Daily Tool Usage ({quotaStatus.plan_code})
            </span>
            <div style={{ display: 'flex', gap: '12px', marginTop: '4px', fontSize: '12px' }}>
              <span>
                Meta: <strong>{quotaStatus.tools.meta_tag_generator.used_today}</strong>
                {quotaStatus.daily_limit !== 'unlimited' && `/${quotaStatus.daily_limit}`}
              </span>
              <span style={{ color: '#cbd5e1' }}>|</span>
              <span>
                Schema: <strong>{quotaStatus.tools.schema_generator.used_today}</strong>
                {quotaStatus.daily_limit !== 'unlimited' && `/${quotaStatus.daily_limit}`}
              </span>
              <span style={{ color: '#cbd5e1' }}>|</span>
              <span>
                Social: <strong>{quotaStatus.tools.open_graph_previewer.used_today}</strong>
                {quotaStatus.daily_limit !== 'unlimited' && `/${quotaStatus.daily_limit}`}
              </span>
            </div>
          </div>
        )}
      </div>

      {/* Tool Navigation Tabs */}
      <div style={tabContainerStyle}>
        <button
          id="seo-tool-tab-meta"
          onClick={() => setActiveTab('meta')}
          style={{
            ...tabButtonStyle,
            borderBottom: activeTab === 'meta' ? '2px solid #2563eb' : '2px solid transparent',
            color: activeTab === 'meta' ? '#1d4ed8' : '#64748b',
            fontWeight: activeTab === 'meta' ? 700 : 500,
          }}
        >
          🏷️ Meta Tag Generator
        </button>
        <button
          id="seo-tool-tab-schema"
          onClick={() => setActiveTab('schema')}
          style={{
            ...tabButtonStyle,
            borderBottom: activeTab === 'schema' ? '2px solid #2563eb' : '2px solid transparent',
            color: activeTab === 'schema' ? '#1d4ed8' : '#64748b',
            fontWeight: activeTab === 'schema' ? 700 : 500,
          }}
        >
          📐 Schema.org JSON-LD Generator
        </button>
        <button
          id="seo-tool-tab-social"
          onClick={() => setActiveTab('social')}
          style={{
            ...tabButtonStyle,
            borderBottom: activeTab === 'social' ? '2px solid #2563eb' : '2px solid transparent',
            color: activeTab === 'social' ? '#1d4ed8' : '#64748b',
            fontWeight: activeTab === 'social' ? 700 : 500,
          }}
        >
          📱 Open Graph & Twitter Preview
        </button>
      </div>

      {/* ============================================================== */}
      {/* TAB 1: META TAG GENERATOR */}
      {/* ============================================================== */}
      {activeTab === 'meta' && (
        <div style={{ marginTop: '20px' }}>
          {metaError && <div style={errorBannerStyle}>{metaError}</div>}

          <div style={grid2ColStyle}>
            {/* Input Form */}
            <form onSubmit={handleGenerateMeta} style={formCardStyle}>
              <h4 style={{ margin: '0 0 16px 0', fontSize: '15px', fontWeight: 700, color: '#111827' }}>
                Page Metadata Inputs
              </h4>

              <div style={formGroupStyle}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <label style={labelStyle}>
                    Page Title <span style={{ color: '#ef4444' }}>*</span>
                  </label>
                  <span style={{ fontSize: '11px', color: metaTitle.length >= 30 && metaTitle.length <= 60 ? '#10b981' : '#f59e0b' }}>
                    {metaTitle.length} / 60 chars {metaTitle.length >= 30 && metaTitle.length <= 60 ? '(Optimal)' : ''}
                  </span>
                </div>
                <input
                  id="meta-input-title"
                  type="text"
                  value={metaTitle}
                  onChange={(e) => setMetaTitle(e.target.value)}
                  placeholder="e.g. Best Coffee Exporters in Addis Ababa | Top Ranked"
                  required
                  style={inputStyle}
                />
              </div>

              <div style={formGroupStyle}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <label style={labelStyle}>
                    Meta Description <span style={{ color: '#ef4444' }}>*</span>
                  </label>
                  <span style={{ fontSize: '11px', color: metaDescription.length >= 70 && metaDescription.length <= 160 ? '#10b981' : '#f59e0b' }}>
                    {metaDescription.length} / 160 chars {metaDescription.length >= 70 && metaDescription.length <= 160 ? '(Optimal)' : ''}
                  </span>
                </div>
                <textarea
                  id="meta-input-description"
                  value={metaDescription}
                  onChange={(e) => setMetaDescription(e.target.value)}
                  placeholder="e.g. Discover certified Ethiopian specialty coffee beans, direct export prices, and origin grading standards in Addis Ababa."
                  rows={3}
                  required
                  style={textareaStyle}
                />
              </div>

              <div style={formGroupStyle}>
                <label style={labelStyle}>Canonical URL</label>
                <input
                  id="meta-input-canonical"
                  type="url"
                  value={metaCanonical}
                  onChange={(e) => setMetaCanonical(e.target.value)}
                  placeholder="https://example.com/coffee-exporters"
                  style={inputStyle}
                />
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
                <div style={formGroupStyle}>
                  <label style={labelStyle}>Robots Directive</label>
                  <select
                    id="meta-select-robots"
                    value={metaRobots}
                    onChange={(e) => setMetaRobots(e.target.value)}
                    style={selectStyle}
                  >
                    <option value="index, follow">index, follow (Default)</option>
                    <option value="noindex, follow">noindex, follow</option>
                    <option value="index, nofollow">index, nofollow</option>
                    <option value="noindex, nofollow">noindex, nofollow</option>
                  </select>
                </div>

                <div style={formGroupStyle}>
                  <label style={labelStyle}>Author</label>
                  <input
                    id="meta-input-author"
                    type="text"
                    value={metaAuthor}
                    onChange={(e) => setMetaAuthor(e.target.value)}
                    placeholder="e.g. Bizrat Tekle"
                    style={inputStyle}
                  />
                </div>
              </div>

              <div style={formGroupStyle}>
                <label style={labelStyle}>Keywords (Comma-separated)</label>
                <input
                  id="meta-input-keywords"
                  type="text"
                  value={metaKeywords}
                  onChange={(e) => setMetaKeywords(e.target.value)}
                  placeholder="ethiopian coffee, yirgacheffe, arabica beans"
                  style={inputStyle}
                />
              </div>

              <div style={{ display: 'flex', gap: '10px', marginTop: '16px' }}>
                <button
                  id="meta-generate-btn"
                  type="submit"
                  disabled={metaLoading || !metaTitle.trim() || !metaDescription.trim()}
                  style={primaryBtnStyle}
                >
                  {metaLoading ? 'Generating...' : '⚡ Generate Meta Tags'}
                </button>
                <button
                  id="meta-reset-btn"
                  type="button"
                  onClick={handleResetMeta}
                  style={secondaryBtnStyle}
                >
                  Reset
                </button>
              </div>
            </form>

            {/* Output Card */}
            <div style={resultCardStyle}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
                <h4 style={{ margin: 0, fontSize: '15px', fontWeight: 700, color: '#111827' }}>
                  Generated HTML Output
                </h4>
                {metaResult && (
                  <button
                    id="meta-copy-btn"
                    onClick={() => handleCopy(metaResult.html, 'meta')}
                    style={copyBtnStyle}
                  >
                    {copiedKey === 'meta' ? '✓ Copied!' : '📋 Copy HTML'}
                  </button>
                )}
              </div>

              {metaResult ? (
                <div>
                  <pre style={codeBlockStyle}>{metaResult.html}</pre>

                  {metaResult.warnings && metaResult.warnings.length > 0 && (
                    <div style={{ marginTop: '14px' }}>
                      <span style={{ fontSize: '12px', fontWeight: 700, color: '#b45309' }}>
                        SEO Guidance Recommendations:
                      </span>
                      <ul style={{ margin: '6px 0 0 0', paddingLeft: '20px', fontSize: '12px', color: '#92400e' }}>
                        {metaResult.warnings.map((w, idx) => (
                          <li key={idx}>{w}</li>
                        ))}
                      </ul>
                    </div>
                  )}
                </div>
              ) : (
                <div style={placeholderBoxStyle}>
                  <p style={{ margin: 0, color: '#94a3b8', fontSize: '13px' }}>
                    Enter page title and description on the left, then click <strong>Generate</strong> to inspect valid, HTML-escaped meta tags.
                  </p>
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* ============================================================== */}
      {/* TAB 2: SCHEMA.ORG / JSON-LD GENERATOR */}
      {/* ============================================================== */}
      {activeTab === 'schema' && (
        <div style={{ marginTop: '20px' }}>
          {schemaError && <div style={errorBannerStyle}>{schemaError}</div>}

          {/* Type Selector Pills */}
          <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap', marginBottom: '16px' }}>
            {(['LocalBusiness', 'Article', 'Product', 'FAQ', 'BreadcrumbList'] as const).map((type) => (
              <button
                key={type}
                id={`schema-pill-${type}`}
                onClick={() => {
                  setSchemaType(type);
                  setSchemaResult(null);
                }}
                style={{
                  ...schemaPillStyle,
                  backgroundColor: schemaType === type ? '#eff6ff' : '#ffffff',
                  borderColor: schemaType === type ? '#2563eb' : '#e2e8f0',
                  color: schemaType === type ? '#1d4ed8' : '#475569',
                  fontWeight: schemaType === type ? 700 : 500,
                }}
              >
                {type === 'FAQ' ? 'FAQ Page' : type === 'BreadcrumbList' ? 'Breadcrumbs' : type}
              </button>
            ))}
          </div>

          <div style={grid2ColStyle}>
            {/* Dynamic Type Form */}
            <form onSubmit={handleGenerateSchema} style={formCardStyle}>
              <h4 style={{ margin: '0 0 16px 0', fontSize: '15px', fontWeight: 700, color: '#111827' }}>
                {schemaType} Parameters
              </h4>

              {/* LocalBusiness Fields */}
              {schemaType === 'LocalBusiness' && (
                <>
                  <div style={formGroupStyle}>
                    <label style={labelStyle}>Business Name <span style={{ color: '#ef4444' }}>*</span></label>
                    <input
                      id="schema-biz-name"
                      type="text"
                      value={bizName}
                      onChange={(e) => setBizName(e.target.value)}
                      placeholder="e.g. Abyssinia Tech Solutions"
                      required
                      style={inputStyle}
                    />
                  </div>
                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
                    <div style={formGroupStyle}>
                      <label style={labelStyle}>Website URL</label>
                      <input
                        id="schema-biz-url"
                        type="url"
                        value={bizUrl}
                        onChange={(e) => setBizUrl(e.target.value)}
                        placeholder="https://example.com"
                        style={inputStyle}
                      />
                    </div>
                    <div style={formGroupStyle}>
                      <label style={labelStyle}>Phone Number</label>
                      <input
                        id="schema-biz-phone"
                        type="text"
                        value={bizPhone}
                        onChange={(e) => setBizPhone(e.target.value)}
                        placeholder="+251 911 000000"
                        style={inputStyle}
                      />
                    </div>
                  </div>
                  <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr', gap: '12px' }}>
                    <div style={formGroupStyle}>
                      <label style={labelStyle}>Street Address</label>
                      <input
                        type="text"
                        value={bizStreet}
                        onChange={(e) => setBizStreet(e.target.value)}
                        placeholder="Bole Road, Mega Building"
                        style={inputStyle}
                      />
                    </div>
                    <div style={formGroupStyle}>
                      <label style={labelStyle}>City</label>
                      <input
                        type="text"
                        value={bizCity}
                        onChange={(e) => setBizCity(e.target.value)}
                        placeholder="Addis Ababa"
                        style={inputStyle}
                      />
                    </div>
                  </div>
                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '12px' }}>
                    <div style={formGroupStyle}>
                      <label style={labelStyle}>Price Range</label>
                      <input
                        type="text"
                        value={bizPrice}
                        onChange={(e) => setBizPrice(e.target.value)}
                        placeholder="$$"
                        style={inputStyle}
                      />
                    </div>
                    <div style={formGroupStyle}>
                      <label style={labelStyle}>Country Code</label>
                      <input
                        type="text"
                        value={bizCountry}
                        onChange={(e) => setBizCountry(e.target.value)}
                        placeholder="ET"
                        style={inputStyle}
                      />
                    </div>
                    <div style={formGroupStyle}>
                      <label style={labelStyle}>Opening Hours</label>
                      <input
                        type="text"
                        value={bizHours}
                        onChange={(e) => setBizHours(e.target.value)}
                        placeholder="Mo-Fr 08:30-17:30"
                        style={inputStyle}
                      />
                    </div>
                  </div>
                </>
              )}

              {/* Article Fields */}
              {schemaType === 'Article' && (
                <>
                  <div style={formGroupStyle}>
                    <label style={labelStyle}>Article Headline <span style={{ color: '#ef4444' }}>*</span></label>
                    <input
                      id="schema-art-headline"
                      type="text"
                      value={artHeadline}
                      onChange={(e) => setArtHeadline(e.target.value)}
                      placeholder="Complete Guide to SEO in Ethiopia"
                      required
                      style={inputStyle}
                    />
                  </div>
                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
                    <div style={formGroupStyle}>
                      <label style={labelStyle}>Author Name</label>
                      <input
                        type="text"
                        value={artAuthor}
                        onChange={(e) => setArtAuthor(e.target.value)}
                        placeholder="Bizrat Tekle"
                        style={inputStyle}
                      />
                    </div>
                    <div style={formGroupStyle}>
                      <label style={labelStyle}>Date Published</label>
                      <input
                        type="date"
                        value={artDate}
                        onChange={(e) => setArtDate(e.target.value)}
                        style={inputStyle}
                      />
                    </div>
                  </div>
                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
                    <div style={formGroupStyle}>
                      <label style={labelStyle}>Article URL</label>
                      <input
                        type="url"
                        value={artUrl}
                        onChange={(e) => setArtUrl(e.target.value)}
                        placeholder="https://example.com/guide"
                        style={inputStyle}
                      />
                    </div>
                    <div style={formGroupStyle}>
                      <label style={labelStyle}>Image URL</label>
                      <input
                        type="url"
                        value={artImage}
                        onChange={(e) => setArtImage(e.target.value)}
                        placeholder="https://example.com/cover.jpg"
                        style={inputStyle}
                      />
                    </div>
                  </div>
                  <div style={formGroupStyle}>
                    <label style={labelStyle}>Publisher Name</label>
                    <input
                      type="text"
                      value={artPublisher}
                      onChange={(e) => setArtPublisher(e.target.value)}
                      placeholder="DoxaRank Media"
                      style={inputStyle}
                    />
                  </div>
                  <div style={formGroupStyle}>
                    <label style={labelStyle}>Article Description</label>
                    <textarea
                      value={artDesc}
                      onChange={(e) => setArtDesc(e.target.value)}
                      placeholder="Brief overview of organic search factors in the Horn of Africa."
                      rows={2}
                      style={textareaStyle}
                    />
                  </div>
                </>
              )}

              {/* Product Fields */}
              {schemaType === 'Product' && (
                <>
                  <div style={formGroupStyle}>
                    <label style={labelStyle}>Product Name <span style={{ color: '#ef4444' }}>*</span></label>
                    <input
                      id="schema-prod-name"
                      type="text"
                      value={prodName}
                      onChange={(e) => setProdName(e.target.value)}
                      placeholder="DoxaRank Starter Subscription"
                      required
                      style={inputStyle}
                    />
                  </div>
                  <div style={formGroupStyle}>
                    <label style={labelStyle}>Product Description</label>
                    <textarea
                      value={prodDesc}
                      onChange={(e) => setProdDesc(e.target.value)}
                      placeholder="High-performance SEO software package."
                      rows={2}
                      style={textareaStyle}
                    />
                  </div>
                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
                    <div style={formGroupStyle}>
                      <label style={labelStyle}>Image URL</label>
                      <input
                        type="url"
                        value={prodImage}
                        onChange={(e) => setProdImage(e.target.value)}
                        placeholder="https://example.com/product.jpg"
                        style={inputStyle}
                      />
                    </div>
                    <div style={formGroupStyle}>
                      <label style={labelStyle}>SKU</label>
                      <input
                        type="text"
                        value={prodSku}
                        onChange={(e) => setProdSku(e.target.value)}
                        placeholder="DX-STARTER"
                        style={inputStyle}
                      />
                    </div>
                  </div>
                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '12px' }}>
                    <div style={formGroupStyle}>
                      <label style={labelStyle}>Price ($)</label>
                      <input
                        type="number"
                        step="0.01"
                        value={prodPrice}
                        onChange={(e) => setProdPrice(e.target.value)}
                        placeholder="49.00"
                        style={inputStyle}
                      />
                    </div>
                    <div style={formGroupStyle}>
                      <label style={labelStyle}>Currency</label>
                      <input
                        type="text"
                        value={prodCurrency}
                        onChange={(e) => setProdCurrency(e.target.value)}
                        placeholder="USD"
                        style={inputStyle}
                      />
                    </div>
                    <div style={formGroupStyle}>
                      <label style={labelStyle}>Brand</label>
                      <input
                        type="text"
                        value={prodBrand}
                        onChange={(e) => setProdBrand(e.target.value)}
                        placeholder="DoxaRank"
                        style={inputStyle}
                      />
                    </div>
                  </div>
                </>
              )}

              {/* FAQ Fields */}
              {schemaType === 'FAQ' && (
                <div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
                    <label style={labelStyle}>Questions & Answers ({faqItems.length})</label>
                    <button
                      type="button"
                      onClick={() => setFaqItems([...faqItems, { question: '', answer: '' }])}
                      style={addPillBtnStyle}
                    >
                      + Add Question
                    </button>
                  </div>
                  {faqItems.map((item, idx) => (
                    <div key={idx} style={itemBoxStyle}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '4px' }}>
                        <span style={{ fontSize: '11px', fontWeight: 700, color: '#475569' }}>Q&A #{idx + 1}</span>
                        {faqItems.length > 1 && (
                          <button
                            type="button"
                            onClick={() => setFaqItems(faqItems.filter((_, i) => i !== idx))}
                            style={removeBtnStyle}
                          >
                            Remove
                          </button>
                        )}
                      </div>
                      <input
                        type="text"
                        value={item.question}
                        onChange={(e) => {
                          const updated = [...faqItems];
                          updated[idx].question = e.target.value;
                          setFaqItems(updated);
                        }}
                        placeholder="Question..."
                        style={{ ...inputStyle, marginBottom: '6px' }}
                      />
                      <textarea
                        value={item.answer}
                        onChange={(e) => {
                          const updated = [...faqItems];
                          updated[idx].answer = e.target.value;
                          setFaqItems(updated);
                        }}
                        placeholder="Answer text..."
                        rows={2}
                        style={textareaStyle}
                      />
                    </div>
                  ))}
                </div>
              )}

              {/* BreadcrumbList Fields */}
              {schemaType === 'BreadcrumbList' && (
                <div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
                    <label style={labelStyle}>Breadcrumb Hierarchy ({breadcrumbItems.length})</label>
                    <button
                      type="button"
                      onClick={() => setBreadcrumbItems([...breadcrumbItems, { name: '', item: '' }])}
                      style={addPillBtnStyle}
                    >
                      + Add Item
                    </button>
                  </div>
                  {breadcrumbItems.map((bc, idx) => (
                    <div key={idx} style={{ display: 'flex', gap: '8px', marginBottom: '8px', alignItems: 'center' }}>
                      <span style={{ fontSize: '12px', fontWeight: 700, color: '#64748b', width: '20px' }}>
                        #{idx + 1}
                      </span>
                      <input
                        type="text"
                        value={bc.name}
                        onChange={(e) => {
                          const updated = [...breadcrumbItems];
                          updated[idx].name = e.target.value;
                          setBreadcrumbItems(updated);
                        }}
                        placeholder="Label (e.g. Products)"
                        style={{ ...inputStyle, flex: 1 }}
                      />
                      <input
                        type="url"
                        value={bc.item}
                        onChange={(e) => {
                          const updated = [...breadcrumbItems];
                          updated[idx].item = e.target.value;
                          setBreadcrumbItems(updated);
                        }}
                        placeholder="https://example.com/products"
                        style={{ ...inputStyle, flex: 2 }}
                      />
                      {breadcrumbItems.length > 1 && (
                        <button
                          type="button"
                          onClick={() => setBreadcrumbItems(breadcrumbItems.filter((_, i) => i !== idx))}
                          style={removeBtnStyle}
                        >
                          ✕
                        </button>
                      )}
                    </div>
                  ))}
                </div>
              )}

              <div style={{ display: 'flex', gap: '10px', marginTop: '16px' }}>
                <button
                  id="schema-generate-btn"
                  type="submit"
                  disabled={schemaLoading}
                  style={primaryBtnStyle}
                >
                  {schemaLoading ? 'Generating...' : `⚡ Generate ${schemaType} JSON-LD`}
                </button>
                <button
                  id="schema-reset-btn"
                  type="button"
                  onClick={handleResetSchema}
                  style={secondaryBtnStyle}
                >
                  Reset
                </button>
              </div>
            </form>

            {/* Schema Output */}
            <div style={resultCardStyle}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
                <h4 style={{ margin: 0, fontSize: '15px', fontWeight: 700, color: '#111827' }}>
                  JSON-LD & Script Tag
                </h4>
                {schemaResult && (
                  <div style={{ display: 'flex', gap: '8px' }}>
                    <button
                      id="schema-copy-script-btn"
                      onClick={() => handleCopy(schemaResult.script_tag, 'schema_script')}
                      style={copyBtnStyle}
                    >
                      {copiedKey === 'schema_script' ? '✓ Copied Tag!' : '📋 Copy <script>'}
                    </button>
                  </div>
                )}
              </div>

              {schemaResult ? (
                <div>
                  <pre style={codeBlockStyle}>{schemaResult.script_tag}</pre>
                </div>
              ) : (
                <div style={placeholderBoxStyle}>
                  <p style={{ margin: 0, color: '#94a3b8', fontSize: '13px' }}>
                    Select a schema type and fill in required fields to generate canonical Schema.org JSON-LD markup.
                  </p>
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* ============================================================== */}
      {/* TAB 3: OPEN GRAPH & TWITTER CARD PREVIEW */}
      {/* ============================================================== */}
      {activeTab === 'social' && (
        <div style={{ marginTop: '20px' }}>
          {socialError && <div style={errorBannerStyle}>{socialError}</div>}

          <div style={grid2ColStyle}>
            {/* Social Inputs */}
            <form onSubmit={handleGenerateSocial} style={formCardStyle}>
              <h4 style={{ margin: '0 0 16px 0', fontSize: '15px', fontWeight: 700, color: '#111827' }}>
                Social Card Inputs
              </h4>

              <div style={formGroupStyle}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <label style={labelStyle}>
                    Card Title <span style={{ color: '#ef4444' }}>*</span>
                  </label>
                  <span style={{ fontSize: '11px', color: socialTitle.length <= 60 ? '#10b981' : '#f59e0b' }}>
                    {socialTitle.length} / 60 chars
                  </span>
                </div>
                <input
                  id="social-input-title"
                  type="text"
                  value={socialTitle}
                  onChange={(e) => setSocialTitle(e.target.value)}
                  placeholder="e.g. Autonomous SEO Intelligence for Emerging Markets"
                  required
                  style={inputStyle}
                />
              </div>

              <div style={formGroupStyle}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <label style={labelStyle}>
                    Card Description <span style={{ color: '#ef4444' }}>*</span>
                  </label>
                  <span style={{ fontSize: '11px', color: socialDesc.length <= 160 ? '#10b981' : '#f59e0b' }}>
                    {socialDesc.length} / 160 chars
                  </span>
                </div>
                <textarea
                  id="social-input-desc"
                  value={socialDesc}
                  onChange={(e) => setSocialDesc(e.target.value)}
                  placeholder="Track rankings on Google Ethiopia and automate your technical SEO roadmap with multi-agent orchestration."
                  rows={3}
                  required
                  style={textareaStyle}
                />
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
                <div style={formGroupStyle}>
                  <label style={labelStyle}>Target URL</label>
                  <input
                    id="social-input-url"
                    type="url"
                    value={socialUrl}
                    onChange={(e) => setSocialUrl(e.target.value)}
                    placeholder="https://doxarank.com/platform"
                    style={inputStyle}
                  />
                </div>
                <div style={formGroupStyle}>
                  <label style={labelStyle}>Image URL</label>
                  <input
                    id="social-input-image"
                    type="url"
                    value={socialImage}
                    onChange={(e) => setSocialImage(e.target.value)}
                    placeholder="https://doxarank.com/og-banner.png"
                    style={inputStyle}
                  />
                </div>
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
                <div style={formGroupStyle}>
                  <label style={labelStyle}>Site Name</label>
                  <input
                    type="text"
                    value={socialSiteName}
                    onChange={(e) => setSocialSiteName(e.target.value)}
                    placeholder="DoxaRank"
                    style={inputStyle}
                  />
                </div>
                <div style={formGroupStyle}>
                  <label style={labelStyle}>Twitter @Handle</label>
                  <input
                    type="text"
                    value={socialTwitterSite}
                    onChange={(e) => setSocialTwitterSite(e.target.value)}
                    placeholder="@doxarank"
                    style={inputStyle}
                  />
                </div>
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
                <div style={formGroupStyle}>
                  <label style={labelStyle}>OG Type</label>
                  <select
                    id="social-select-og-type"
                    value={socialOgType}
                    onChange={(e) => setSocialOgType(e.target.value)}
                    style={selectStyle}
                  >
                    <option value="website">website</option>
                    <option value="article">article</option>
                    <option value="book">book</option>
                    <option value="profile">profile</option>
                  </select>
                </div>
                <div style={formGroupStyle}>
                  <label style={labelStyle}>Twitter Card Format</label>
                  <select
                    id="social-select-twitter-card"
                    value={socialTwitterCard}
                    onChange={(e) => setSocialTwitterCard(e.target.value)}
                    style={selectStyle}
                  >
                    <option value="summary_large_image">summary_large_image (Large Banner)</option>
                    <option value="summary">summary (Small Square)</option>
                  </select>
                </div>
              </div>

              <div style={{ display: 'flex', gap: '10px', marginTop: '16px' }}>
                <button
                  id="social-generate-btn"
                  type="submit"
                  disabled={socialLoading || !socialTitle.trim() || !socialDesc.trim()}
                  style={primaryBtnStyle}
                >
                  {socialLoading ? 'Generating...' : '⚡ Generate Tags & Preview'}
                </button>
                <button
                  id="social-reset-btn"
                  type="button"
                  onClick={handleResetSocial}
                  style={secondaryBtnStyle}
                >
                  Reset
                </button>
              </div>
            </form>

            {/* Visual Previews and Meta Tags */}
            <div style={resultCardStyle}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
                <h4 style={{ margin: 0, fontSize: '15px', fontWeight: 700, color: '#111827' }}>
                  Interactive Social Previews
                </h4>
                {socialResult && (
                  <button
                    id="social-copy-btn"
                    onClick={() => handleCopy(socialResult.html, 'social')}
                    style={copyBtnStyle}
                  >
                    {copiedKey === 'social' ? '✓ Copied Tags!' : '📋 Copy Meta Tags'}
                  </button>
                )}
              </div>

              {/* Dynamic Live Cards */}
              <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
                {/* 1. Open Graph Card */}
                <div>
                  <span style={{ fontSize: '11px', fontWeight: 700, color: '#475569', textTransform: 'uppercase' }}>
                    Open Graph Card (Facebook / LinkedIn)
                  </span>
                  <div style={ogCardPreviewStyle}>
                    {socialImage ? (
                      <div style={{ height: '140px', backgroundColor: '#e2e8f0', overflow: 'hidden' }}>
                        <img
                          src={socialImage}
                          alt="Social Preview"
                          onError={(e) => {
                            (e.target as HTMLElement).style.display = 'none';
                          }}
                          style={{ width: '100%', height: '100%', objectFit: 'cover' }}
                        />
                      </div>
                    ) : (
                      <div style={cardImagePlaceholderStyle}>
                        <span>🖼️ No image URL specified (Text-only display)</span>
                      </div>
                    )}
                    <div style={{ padding: '12px' }}>
                      <span style={{ fontSize: '11px', color: '#64748b', textTransform: 'uppercase', fontWeight: 600 }}>
                        {socialResult?.preview.domain || 'example.com'}
                      </span>
                      <h5 style={{ margin: '4px 0', fontSize: '15px', fontWeight: 700, color: '#1e293b' }}>
                        {socialTitle || 'Card Title will appear here'}
                      </h5>
                      <p style={{ margin: 0, fontSize: '13px', color: '#64748b', lineHeight: 1.4 }}>
                        {socialDesc || 'Enter a descriptive snippet to see how social platforms format this card.'}
                      </p>
                    </div>
                  </div>
                </div>

                {/* 2. Twitter / X Card */}
                <div>
                  <span style={{ fontSize: '11px', fontWeight: 700, color: '#475569', textTransform: 'uppercase' }}>
                    Twitter / X Card Preview
                  </span>
                  <div style={twitterCardPreviewStyle}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '8px' }}>
                      <div style={avatarMockStyle}>D</div>
                      <div>
                        <span style={{ fontSize: '13px', fontWeight: 700, color: '#0f1419' }}>DoxaRank</span>
                        <span style={{ fontSize: '12px', color: '#536471', marginLeft: '6px' }}>
                          {socialTwitterSite || '@doxarank'} · Now
                        </span>
                      </div>
                    </div>
                    <div style={{ borderRadius: '12px', overflow: 'hidden', border: '1px solid #cfd9de' }}>
                      {socialImage ? (
                        <div style={{ height: '120px', backgroundColor: '#e2e8f0' }}>
                          <img
                            src={socialImage}
                            alt="Twitter Card"
                            onError={(e) => {
                              (e.target as HTMLElement).style.display = 'none';
                            }}
                            style={{ width: '100%', height: '100%', objectFit: 'cover' }}
                          />
                        </div>
                      ) : null}
                      <div style={{ padding: '8px 12px', backgroundColor: '#ffffff' }}>
                        <span style={{ fontSize: '11px', color: '#536471' }}>
                          {socialResult?.preview.domain || 'example.com'}
                        </span>
                        <div style={{ fontSize: '14px', fontWeight: 700, color: '#0f1419', marginTop: '2px' }}>
                          {socialTitle || 'Post title preview'}
                        </div>
                      </div>
                    </div>
                  </div>
                </div>

                {/* Generated Tags Code Block */}
                {socialResult && (
                  <div style={{ marginTop: '10px' }}>
                    <span style={{ fontSize: '12px', fontWeight: 700, color: '#1e293b' }}>
                      Generated Social HTML Tags:
                    </span>
                    <pre style={{ ...codeBlockStyle, marginTop: '6px' }}>{socialResult.html}</pre>
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
      )}
    </section>
  );
};

// --- STYLES ---
const sectionCardStyle: React.CSSProperties = {
  backgroundColor: '#ffffff',
  borderRadius: '12px',
  border: '1px solid #e2e8f0',
  padding: '24px',
  marginTop: '36px',
  boxShadow: '0 1px 3px rgba(0, 0, 0, 0.05)',
};

const toolBadgeStyle: React.CSSProperties = {
  backgroundColor: '#ecfdf5',
  color: '#065f46',
  border: '1px solid #a7f3d0',
  borderRadius: '6px',
  padding: '2px 8px',
  fontSize: '11px',
  fontWeight: 700,
  letterSpacing: '0.05em',
};

const quotaCardStyle: React.CSSProperties = {
  backgroundColor: '#f8fafc',
  border: '1px solid #e2e8f0',
  borderRadius: '8px',
  padding: '8px 14px',
  textAlign: 'right',
};

const tabContainerStyle: React.CSSProperties = {
  display: 'flex',
  gap: '16px',
  borderBottom: '1px solid #e2e8f0',
  paddingBottom: '2px',
};

const tabButtonStyle: React.CSSProperties = {
  background: 'none',
  border: 'none',
  padding: '8px 12px',
  fontSize: '14px',
  cursor: 'pointer',
  transition: 'all 0.15s ease',
};

const schemaPillStyle: React.CSSProperties = {
  border: '1px solid',
  borderRadius: '20px',
  padding: '6px 14px',
  fontSize: '12px',
  cursor: 'pointer',
  transition: 'all 0.15s ease',
};

const grid2ColStyle: React.CSSProperties = {
  display: 'grid',
  gridTemplateColumns: 'minmax(320px, 1fr) minmax(320px, 1fr)',
  gap: '24px',
};

const formCardStyle: React.CSSProperties = {
  backgroundColor: '#f8fafc',
  border: '1px solid #e2e8f0',
  borderRadius: '8px',
  padding: '20px',
};

const resultCardStyle: React.CSSProperties = {
  backgroundColor: '#ffffff',
  border: '1px solid #e2e8f0',
  borderRadius: '8px',
  padding: '20px',
  display: 'flex',
  flexDirection: 'column',
};

const formGroupStyle: React.CSSProperties = {
  marginBottom: '14px',
};

const labelStyle: React.CSSProperties = {
  display: 'block',
  fontSize: '12px',
  fontWeight: 600,
  color: '#334155',
  marginBottom: '4px',
};

const inputStyle: React.CSSProperties = {
  width: '100%',
  boxSizing: 'border-box',
  padding: '8px 12px',
  fontSize: '13px',
  border: '1px solid #cbd5e1',
  borderRadius: '6px',
  backgroundColor: '#ffffff',
  color: '#0f172a',
};

const textareaStyle: React.CSSProperties = {
  width: '100%',
  boxSizing: 'border-box',
  padding: '8px 12px',
  fontSize: '13px',
  border: '1px solid #cbd5e1',
  borderRadius: '6px',
  backgroundColor: '#ffffff',
  color: '#0f172a',
  resize: 'vertical',
  fontFamily: 'inherit',
};

const selectStyle: React.CSSProperties = {
  width: '100%',
  boxSizing: 'border-box',
  padding: '8px 12px',
  fontSize: '13px',
  border: '1px solid #cbd5e1',
  borderRadius: '6px',
  backgroundColor: '#ffffff',
  color: '#0f172a',
};

const primaryBtnStyle: React.CSSProperties = {
  backgroundColor: '#2563eb',
  color: '#ffffff',
  border: 'none',
  borderRadius: '6px',
  padding: '8px 16px',
  fontSize: '13px',
  fontWeight: 600,
  cursor: 'pointer',
  transition: 'background-color 0.15s ease',
};

const secondaryBtnStyle: React.CSSProperties = {
  backgroundColor: '#ffffff',
  color: '#475569',
  border: '1px solid #cbd5e1',
  borderRadius: '6px',
  padding: '8px 14px',
  fontSize: '13px',
  fontWeight: 500,
  cursor: 'pointer',
};

const copyBtnStyle: React.CSSProperties = {
  backgroundColor: '#eff6ff',
  color: '#1d4ed8',
  border: '1px solid #bfdbfe',
  borderRadius: '6px',
  padding: '4px 10px',
  fontSize: '12px',
  fontWeight: 600,
  cursor: 'pointer',
};

const codeBlockStyle: React.CSSProperties = {
  backgroundColor: '#0f172a',
  color: '#38bdf8',
  padding: '14px',
  borderRadius: '6px',
  fontSize: '12px',
  lineHeight: 1.5,
  overflowX: 'auto',
  maxHeight: '340px',
  fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace',
  margin: 0,
};

const placeholderBoxStyle: React.CSSProperties = {
  backgroundColor: '#f8fafc',
  border: '2px dashed #cbd5e1',
  borderRadius: '6px',
  padding: '32px 20px',
  textAlign: 'center',
  marginTop: '12px',
};

const errorBannerStyle: React.CSSProperties = {
  backgroundColor: '#fef2f2',
  color: '#991b1b',
  border: '1px solid #fecaca',
  borderRadius: '6px',
  padding: '10px 14px',
  fontSize: '13px',
  marginBottom: '16px',
};

const ogCardPreviewStyle: React.CSSProperties = {
  border: '1px solid #e2e8f0',
  borderRadius: '8px',
  overflow: 'hidden',
  backgroundColor: '#f8fafc',
  marginTop: '6px',
};

const cardImagePlaceholderStyle: React.CSSProperties = {
  height: '80px',
  backgroundColor: '#f1f5f9',
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'center',
  color: '#94a3b8',
  fontSize: '12px',
};

const twitterCardPreviewStyle: React.CSSProperties = {
  border: '1px solid #e2e8f0',
  borderRadius: '12px',
  padding: '12px',
  backgroundColor: '#ffffff',
  marginTop: '6px',
};

const avatarMockStyle: React.CSSProperties = {
  width: '32px',
  height: '32px',
  borderRadius: '50%',
  backgroundColor: '#1d9bf0',
  color: '#ffffff',
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'center',
  fontWeight: 700,
  fontSize: '13px',
};

const itemBoxStyle: React.CSSProperties = {
  backgroundColor: '#ffffff',
  border: '1px solid #e2e8f0',
  borderRadius: '6px',
  padding: '10px',
  marginBottom: '10px',
};

const addPillBtnStyle: React.CSSProperties = {
  backgroundColor: '#f1f5f9',
  color: '#2563eb',
  border: 'none',
  borderRadius: '4px',
  padding: '3px 8px',
  fontSize: '11px',
  fontWeight: 600,
  cursor: 'pointer',
};

const removeBtnStyle: React.CSSProperties = {
  backgroundColor: 'transparent',
  color: '#ef4444',
  border: 'none',
  fontSize: '11px',
  cursor: 'pointer',
  padding: '2px 4px',
};
