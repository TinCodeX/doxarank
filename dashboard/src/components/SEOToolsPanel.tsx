import React, { useState, useEffect } from 'react';
import {
  seoToolsApi,
  type MetaTagResult,
  type SchemaResult,
  type SocialPreviewResult,
  type RobotsToolResult,
  type SitemapToolResult,
  type HreflangResult,
  type SEOToolsQuotaStatus,
} from '../api/seoTools';

type ToolTab = 'meta' | 'schema' | 'social' | 'robots' | 'sitemap' | 'hreflang';

export const SEOToolsPanel: React.FC = () => {
  const [activeTab, setActiveTab] = useState<ToolTab>('meta');
  const [quotaStatus, setQuotaStatus] = useState<SEOToolsQuotaStatus | null>(null);
  const [copiedKey, setCopiedKey] = useState<string | null>(null);

  // =========================================================================
  // 1. Meta Tag Generator State
  // =========================================================================
  const [metaTitle, setMetaTitle] = useState('');
  const [metaDescription, setMetaDescription] = useState('');
  const [metaCanonical, setMetaCanonical] = useState('');
  const [metaRobots, setMetaRobots] = useState('index, follow');
  const [metaAuthor, setMetaAuthor] = useState('');
  const [metaKeywords, setMetaKeywords] = useState('');
  const [metaResult, setMetaResult] = useState<MetaTagResult | null>(null);
  const [metaLoading, setMetaLoading] = useState(false);
  const [metaError, setMetaError] = useState<string | null>(null);

  // =========================================================================
  // 2. Schema Generator State
  // =========================================================================
  const [schemaType, setSchemaType] = useState<'LocalBusiness' | 'Article' | 'Product' | 'FAQ' | 'BreadcrumbList'>('LocalBusiness');
  const [schemaResult, setSchemaResult] = useState<SchemaResult | null>(null);
  const [schemaLoading, setSchemaLoading] = useState(false);
  const [schemaError, setSchemaError] = useState<string | null>(null);

  // LocalBusiness Fields
  const [bizName, setBizName] = useState('');
  const [bizUrl, setBizUrl] = useState('');
  const [bizPhone, setBizPhone] = useState('');
  const [bizPrice, setBizPrice] = useState('$$');
  const [bizStreet, setBizStreet] = useState('');
  const [bizCity, setBizCity] = useState('');
  const [bizCountry, setBizCountry] = useState('ET');
  const [bizHours, setBizHours] = useState('Mo-Fr 08:30-17:30');

  // Article Fields
  const [artHeadline, setArtHeadline] = useState('');
  const [artAuthor, setArtAuthor] = useState('');
  const [artDate, setArtDate] = useState(new Date().toISOString().split('T')[0]);
  const [artDesc, setArtDesc] = useState('');
  const [artUrl, setArtUrl] = useState('');
  const [artImage, setArtImage] = useState('');
  const [artPublisher, setArtPublisher] = useState('');

  // Product Fields
  const [prodName, setProdName] = useState('');
  const [prodDesc, setProdDesc] = useState('');
  const [prodImage, setProdImage] = useState('');
  const [prodSku, setProdSku] = useState('');
  const [prodBrand, setProdBrand] = useState('');
  const [prodPrice, setProdPrice] = useState('');
  const [prodCurrency, setProdCurrency] = useState('USD');

  // FAQ Fields
  const [faqItems, setFaqItems] = useState<Array<{ question: string; answer: string }>>([
    { question: 'What is DoxaRank?', answer: 'An autonomous SEO rank tracking and intelligence platform.' },
    { question: 'Does DoxaRank support Ethiopian queries?', answer: 'Yes, with native Amharic keyword tracking on google.com.et.' },
  ]);

  // Breadcrumbs Fields
  const [breadcrumbItems, setBreadcrumbItems] = useState<Array<{ name: string; item: string }>>([
    { name: 'Home', item: 'https://example.com' },
    { name: 'Services', item: 'https://example.com/services' },
    { name: 'SEO Audits', item: 'https://example.com/services/seo-audits' },
  ]);

  // =========================================================================
  // 3. Social Preview State
  // =========================================================================
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

  // =========================================================================
  // 4. Robots.txt Tool State
  // =========================================================================
  const [robotsMode, setRobotsMode] = useState<'generate' | 'test'>('generate');
  const [robotsGroups, setRobotsGroups] = useState<Array<{ user_agent: string; disallow: string; allow: string; crawl_delay: string }>>([
    { user_agent: '*', disallow: '/admin/\n/private/', allow: '/public/\n/', crawl_delay: '' },
  ]);
  const [robotsSitemaps, setRobotsSitemaps] = useState('https://example.com/sitemap.xml');
  const [robotsHost, setRobotsHost] = useState('');
  const [robotsTestContent, setRobotsTestContent] = useState('User-agent: *\nDisallow: /admin/\nAllow: /\n\nSitemap: https://example.com/sitemap.xml');
  const [robotsTestPath, setRobotsTestPath] = useState('/admin/users');
  const [robotsTestAgent, setRobotsTestAgent] = useState('*');
  const [robotsResult, setRobotsResult] = useState<RobotsToolResult | null>(null);
  const [robotsLoading, setRobotsLoading] = useState(false);
  const [robotsError, setRobotsError] = useState<string | null>(null);

  // =========================================================================
  // 5. XML Sitemap Tool State
  // =========================================================================
  const [sitemapMode, setSitemapMode] = useState<'generate' | 'validate'>('generate');
  const [sitemapEntries, setSitemapEntries] = useState<Array<{ loc: string; lastmod: string; changefreq: string; priority: string }>>([
    { loc: 'https://example.com/', lastmod: new Date().toISOString().split('T')[0], changefreq: 'daily', priority: '1.0' },
    { loc: 'https://example.com/services', lastmod: new Date().toISOString().split('T')[0], changefreq: 'weekly', priority: '0.8' },
  ]);
  const [sitemapXmlContent, setSitemapXmlContent] = useState('');
  const [sitemapResult, setSitemapResult] = useState<SitemapToolResult | null>(null);
  const [sitemapLoading, setSitemapLoading] = useState(false);
  const [sitemapError, setSitemapError] = useState<string | null>(null);

  // =========================================================================
  // 6. hreflang Builder State
  // =========================================================================
  const [hreflangEntries, setHreflangEntries] = useState<Array<{ lang: string; url: string }>>([
    { lang: 'en', url: 'https://example.com/en/' },
    { lang: 'am', url: 'https://example.com/am/' },
    { lang: 'om', url: 'https://example.com/om/' },
  ]);
  const [hreflangXDefault, setHreflangXDefault] = useState('https://example.com/');
  const [hreflangResult, setHreflangResult] = useState<HreflangResult | null>(null);
  const [hreflangLoading, setHreflangLoading] = useState(false);
  const [hreflangError, setHreflangError] = useState<string | null>(null);

  // =========================================================================
  // Quota Status Management
  // =========================================================================
  const refreshQuota = async () => {
    try {
      const data = await seoToolsApi.getQuotaStatus();
      setQuotaStatus(data);
    } catch {
      // Ignored if unauthenticated
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

  // --- META HANDLERS ---
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

  // --- SCHEMA HANDLERS ---
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

  // --- SOCIAL PREVIEW HANDLERS ---
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

  // --- ROBOTS.TXT HANDLERS ---
  const handleProcessRobots = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    setRobotsLoading(true);
    setRobotsError(null);
    try {
      if (robotsMode === 'generate') {
        const parsedGroups = robotsGroups.map((g) => ({
          user_agent: g.user_agent,
          disallow: g.disallow.split('\n').map((d) => d.trim()).filter(Boolean),
          allow: g.allow.split('\n').map((a) => a.trim()).filter(Boolean),
          crawl_delay: g.crawl_delay || undefined,
        }));
        const parsedSitemaps = robotsSitemaps.split('\n').map((s) => s.trim()).filter(Boolean);

        const res = await seoToolsApi.processRobots({
          action: 'generate',
          groups: parsedGroups,
          sitemaps: parsedSitemaps,
          host: robotsHost || undefined,
        });
        setRobotsResult(res);
        if (res.content) {
          setRobotsTestContent(res.content);
        }
      } else {
        const res = await seoToolsApi.processRobots({
          action: 'test',
          robots_content: robotsTestContent,
          path: robotsTestPath,
          user_agent: robotsTestAgent,
        });
        setRobotsResult(res);
      }
      refreshQuota();
    } catch (err: any) {
      setRobotsError(err?.data?.detail || err?.data?.error || 'Failed to process robots.txt request.');
    } finally {
      setRobotsLoading(false);
    }
  };

  const handleResetRobots = () => {
    setRobotsResult(null);
    setRobotsError(null);
    setRobotsTestPath('/admin/users');
  };

  // --- SITEMAP HANDLERS ---
  const handleProcessSitemap = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    setSitemapLoading(true);
    setSitemapError(null);
    try {
      if (sitemapMode === 'generate') {
        const res = await seoToolsApi.processSitemap({
          action: 'generate',
          entries: sitemapEntries.filter((e) => e.loc.trim()),
        });
        setSitemapResult(res);
        if (res.xml) {
          setSitemapXmlContent(res.xml);
        }
      } else {
        const res = await seoToolsApi.processSitemap({
          action: 'validate',
          xml_content: sitemapXmlContent,
        });
        setSitemapResult(res);
      }
      refreshQuota();
    } catch (err: any) {
      setSitemapError(err?.data?.detail || err?.data?.error || 'Failed to process sitemap request.');
    } finally {
      setSitemapLoading(false);
    }
  };

  const handleResetSitemap = () => {
    setSitemapResult(null);
    setSitemapError(null);
    setSitemapXmlContent('');
  };

  // --- HREFLANG HANDLERS ---
  const handleGenerateHreflang = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    setHreflangLoading(true);
    setHreflangError(null);
    try {
      const res = await seoToolsApi.generateHreflang({
        entries: hreflangEntries.filter((e) => e.lang.trim() && e.url.trim()),
        x_default: hreflangXDefault || undefined,
      });
      setHreflangResult(res);
      refreshQuota();
    } catch (err: any) {
      setHreflangError(err?.data?.detail || err?.data?.error || 'Failed to generate hreflang annotations.');
    } finally {
      setHreflangLoading(false);
    }
  };

  const handleResetHreflang = () => {
    setHreflangResult(null);
    setHreflangError(null);
  };

  return (
    <section id="seo-tools-section" style={sectionCardStyle}>
      {/* Section Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: '16px', marginBottom: '20px' }}>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <span style={{ fontSize: '20px' }}>🛠️</span>
            <h3 style={{ margin: 0, fontSize: '20px', fontWeight: 700, color: '#111827' }}>
              Standalone Core SEO Tools
            </h3>
            <span style={toolBadgeStyle}>BASIC SEO TOOLS</span>
          </div>
          <p style={{ margin: '6px 0 0 0', fontSize: '13px', color: '#6b7280' }}>
            Original DoxaRank standalone utility tools for meta tags, Schema markup, social previews, robots, sitemaps, and Ethiopian hreflang localization.
          </p>
        </div>

        {/* Quota Indicator */}
        {quotaStatus && (
          <div style={quotaCardStyle}>
            <span style={{ fontSize: '11px', fontWeight: 700, textTransform: 'uppercase', color: '#64748b' }}>
              Daily Tool Usage ({quotaStatus.plan_code})
            </span>
            <div style={{ display: 'flex', gap: '10px', marginTop: '4px', fontSize: '12px', flexWrap: 'wrap' }}>
              <span>Meta: <strong>{quotaStatus.tools.meta_tag_generator?.used_today ?? 0}</strong>{quotaStatus.daily_limit !== 'unlimited' && `/${quotaStatus.daily_limit}`}</span>
              <span style={{ color: '#cbd5e1' }}>|</span>
              <span>Schema: <strong>{quotaStatus.tools.schema_generator?.used_today ?? 0}</strong>{quotaStatus.daily_limit !== 'unlimited' && `/${quotaStatus.daily_limit}`}</span>
              <span style={{ color: '#cbd5e1' }}>|</span>
              <span>Social: <strong>{quotaStatus.tools.open_graph_previewer?.used_today ?? 0}</strong>{quotaStatus.daily_limit !== 'unlimited' && `/${quotaStatus.daily_limit}`}</span>
              <span style={{ color: '#cbd5e1' }}>|</span>
              <span>Robots: <strong>{quotaStatus.tools.robots_txt_tool?.used_today ?? 0}</strong>{quotaStatus.daily_limit !== 'unlimited' && `/${quotaStatus.daily_limit}`}</span>
              <span style={{ color: '#cbd5e1' }}>|</span>
              <span>Sitemap: <strong>{quotaStatus.tools.xml_sitemap_tool?.used_today ?? 0}</strong>{quotaStatus.daily_limit !== 'unlimited' && `/${quotaStatus.daily_limit}`}</span>
              <span style={{ color: '#cbd5e1' }}>|</span>
              <span>hreflang: <strong>{quotaStatus.tools.hreflang_builder?.used_today ?? 0}</strong>{quotaStatus.daily_limit !== 'unlimited' && `/${quotaStatus.daily_limit}`}</span>
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
          🏷️ Meta Tags
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
          📐 Schema JSON-LD
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
          📱 Social Preview
        </button>
        <button
          id="seo-tool-tab-robots"
          onClick={() => setActiveTab('robots')}
          style={{
            ...tabButtonStyle,
            borderBottom: activeTab === 'robots' ? '2px solid #2563eb' : '2px solid transparent',
            color: activeTab === 'robots' ? '#1d4ed8' : '#64748b',
            fontWeight: activeTab === 'robots' ? 700 : 500,
          }}
        >
          🤖 Robots.txt
        </button>
        <button
          id="seo-tool-tab-sitemap"
          onClick={() => setActiveTab('sitemap')}
          style={{
            ...tabButtonStyle,
            borderBottom: activeTab === 'sitemap' ? '2px solid #2563eb' : '2px solid transparent',
            color: activeTab === 'sitemap' ? '#1d4ed8' : '#64748b',
            fontWeight: activeTab === 'sitemap' ? 700 : 500,
          }}
        >
          🗺️ XML Sitemap
        </button>
        <button
          id="seo-tool-tab-hreflang"
          onClick={() => setActiveTab('hreflang')}
          style={{
            ...tabButtonStyle,
            borderBottom: activeTab === 'hreflang' ? '2px solid #2563eb' : '2px solid transparent',
            color: activeTab === 'hreflang' ? '#1d4ed8' : '#64748b',
            fontWeight: activeTab === 'hreflang' ? 700 : 500,
          }}
        >
          🌐 hreflang Builder
        </button>
      </div>

      {/* ============================================================== */}
      {/* TAB 1: META TAG GENERATOR */}
      {/* ============================================================== */}
      {activeTab === 'meta' && (
        <div style={{ marginTop: '20px' }}>
          {metaError && <div style={errorBannerStyle}>{metaError}</div>}
          <div style={grid2ColStyle}>
            <form onSubmit={handleGenerateMeta} style={formCardStyle}>
              <h4 style={{ margin: '0 0 16px 0', fontSize: '15px', fontWeight: 700, color: '#111827' }}>
                Page Metadata Inputs
              </h4>
              <div style={formGroupStyle}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <label style={labelStyle}>Page Title <span style={{ color: '#ef4444' }}>*</span></label>
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
                  <label style={labelStyle}>Meta Description <span style={{ color: '#ef4444' }}>*</span></label>
                  <span style={{ fontSize: '11px', color: metaDescription.length >= 70 && metaDescription.length <= 160 ? '#10b981' : '#f59e0b' }}>
                    {metaDescription.length} / 160 chars {metaDescription.length >= 70 && metaDescription.length <= 160 ? '(Optimal)' : ''}
                  </span>
                </div>
                <textarea
                  id="meta-input-description"
                  value={metaDescription}
                  onChange={(e) => setMetaDescription(e.target.value)}
                  placeholder="Discover certified Ethiopian specialty coffee beans in Addis Ababa."
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
                <label style={labelStyle}>Keywords</label>
                <input
                  id="meta-input-keywords"
                  type="text"
                  value={metaKeywords}
                  onChange={(e) => setMetaKeywords(e.target.value)}
                  placeholder="ethiopian coffee, arabica beans"
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
                <button id="meta-reset-btn" type="button" onClick={handleResetMeta} style={secondaryBtnStyle}>
                  Reset
                </button>
              </div>
            </form>
            <div style={resultCardStyle}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
                <h4 style={{ margin: 0, fontSize: '15px', fontWeight: 700, color: '#111827' }}>Generated HTML</h4>
                {metaResult && (
                  <button id="meta-copy-btn" onClick={() => handleCopy(metaResult.html, 'meta')} style={copyBtnStyle}>
                    {copiedKey === 'meta' ? '✓ Copied!' : '📋 Copy HTML'}
                  </button>
                )}
              </div>
              {metaResult ? (
                <div>
                  <pre style={codeBlockStyle}>{metaResult.html}</pre>
                </div>
              ) : (
                <div style={placeholderBoxStyle}>
                  <p style={{ margin: 0, color: '#94a3b8', fontSize: '13px' }}>Enter title and description to generate tags.</p>
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* ============================================================== */}
      {/* TAB 2: SCHEMA GENERATOR */}
      {/* ============================================================== */}
      {activeTab === 'schema' && (
        <div style={{ marginTop: '20px' }}>
          {schemaError && <div style={errorBannerStyle}>{schemaError}</div>}
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
            <form onSubmit={handleGenerateSchema} style={formCardStyle}>
              <h4 style={{ margin: '0 0 16px 0', fontSize: '15px', fontWeight: 700, color: '#111827' }}>
                {schemaType} Parameters
              </h4>
              {schemaType === 'LocalBusiness' && (
                <>
                  <div style={formGroupStyle}>
                    <label style={labelStyle}>Business Name <span style={{ color: '#ef4444' }}>*</span></label>
                    <input type="text" value={bizName} onChange={(e) => setBizName(e.target.value)} placeholder="Abyssinia Tech" required style={inputStyle} />
                  </div>
                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
                    <div style={formGroupStyle}>
                      <label style={labelStyle}>Website URL</label>
                      <input type="url" value={bizUrl} onChange={(e) => setBizUrl(e.target.value)} placeholder="https://example.com" style={inputStyle} />
                    </div>
                    <div style={formGroupStyle}>
                      <label style={labelStyle}>Phone Number</label>
                      <input type="text" value={bizPhone} onChange={(e) => setBizPhone(e.target.value)} placeholder="+251 911 000000" style={inputStyle} />
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
                      <input type="text" value={bizPrice} onChange={(e) => setBizPrice(e.target.value)} placeholder="$$" style={inputStyle} />
                    </div>
                    <div style={formGroupStyle}>
                      <label style={labelStyle}>Country</label>
                      <input type="text" value={bizCountry} onChange={(e) => setBizCountry(e.target.value)} placeholder="ET" style={inputStyle} />
                    </div>
                    <div style={formGroupStyle}>
                      <label style={labelStyle}>Hours</label>
                      <input type="text" value={bizHours} onChange={(e) => setBizHours(e.target.value)} placeholder="Mo-Fr 08:30-17:30" style={inputStyle} />
                    </div>
                  </div>
                </>
              )}
              {schemaType === 'Article' && (
                <>
                  <div style={formGroupStyle}>
                    <label style={labelStyle}>Headline <span style={{ color: '#ef4444' }}>*</span></label>
                    <input type="text" value={artHeadline} onChange={(e) => setArtHeadline(e.target.value)} placeholder="Ethiopian SEO Guide" required style={inputStyle} />
                  </div>
                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
                    <div style={formGroupStyle}>
                      <label style={labelStyle}>Author</label>
                      <input type="text" value={artAuthor} onChange={(e) => setArtAuthor(e.target.value)} placeholder="Bizrat Tekle" style={inputStyle} />
                    </div>
                    <div style={formGroupStyle}>
                      <label style={labelStyle}>Date</label>
                      <input type="date" value={artDate} onChange={(e) => setArtDate(e.target.value)} style={inputStyle} />
                    </div>
                  </div>
                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
                    <div style={formGroupStyle}>
                      <label style={labelStyle}>URL</label>
                      <input type="url" value={artUrl} onChange={(e) => setArtUrl(e.target.value)} placeholder="https://example.com/guide" style={inputStyle} />
                    </div>
                    <div style={formGroupStyle}>
                      <label style={labelStyle}>Image URL</label>
                      <input type="url" value={artImage} onChange={(e) => setArtImage(e.target.value)} placeholder="https://example.com/img.jpg" style={inputStyle} />
                    </div>
                  </div>
                  <div style={formGroupStyle}>
                    <label style={labelStyle}>Publisher</label>
                    <input type="text" value={artPublisher} onChange={(e) => setArtPublisher(e.target.value)} placeholder="DoxaRank Media" style={inputStyle} />
                  </div>
                  <div style={formGroupStyle}>
                    <label style={labelStyle}>Description</label>
                    <textarea value={artDesc} onChange={(e) => setArtDesc(e.target.value)} rows={2} style={textareaStyle} />
                  </div>
                </>
              )}
              {schemaType === 'Product' && (
                <>
                  <div style={formGroupStyle}>
                    <label style={labelStyle}>Product Name <span style={{ color: '#ef4444' }}>*</span></label>
                    <input type="text" value={prodName} onChange={(e) => setProdName(e.target.value)} placeholder="Starter Subscription" required style={inputStyle} />
                  </div>
                  <div style={formGroupStyle}>
                    <label style={labelStyle}>Description</label>
                    <textarea value={prodDesc} onChange={(e) => setProdDesc(e.target.value)} rows={2} style={textareaStyle} />
                  </div>
                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
                    <div style={formGroupStyle}>
                      <label style={labelStyle}>Image URL</label>
                      <input type="url" value={prodImage} onChange={(e) => setProdImage(e.target.value)} placeholder="https://example.com/img.jpg" style={inputStyle} />
                    </div>
                    <div style={formGroupStyle}>
                      <label style={labelStyle}>SKU</label>
                      <input type="text" value={prodSku} onChange={(e) => setProdSku(e.target.value)} placeholder="DX-STARTER" style={inputStyle} />
                    </div>
                  </div>
                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '12px' }}>
                    <div style={formGroupStyle}>
                      <label style={labelStyle}>Price ($)</label>
                      <input type="number" step="0.01" value={prodPrice} onChange={(e) => setProdPrice(e.target.value)} placeholder="49.00" style={inputStyle} />
                    </div>
                    <div style={formGroupStyle}>
                      <label style={labelStyle}>Currency</label>
                      <input type="text" value={prodCurrency} onChange={(e) => setProdCurrency(e.target.value)} placeholder="USD" style={inputStyle} />
                    </div>
                    <div style={formGroupStyle}>
                      <label style={labelStyle}>Brand</label>
                      <input type="text" value={prodBrand} onChange={(e) => setProdBrand(e.target.value)} placeholder="DoxaRank" style={inputStyle} />
                    </div>
                  </div>
                </>
              )}
              {schemaType === 'FAQ' && (
                <div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
                    <label style={labelStyle}>Q&A Pairs ({faqItems.length})</label>
                    <button type="button" onClick={() => setFaqItems([...faqItems, { question: '', answer: '' }])} style={addPillBtnStyle}>
                      + Add Question
                    </button>
                  </div>
                  {faqItems.map((item, idx) => (
                    <div key={idx} style={itemBoxStyle}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '4px' }}>
                        <span style={{ fontSize: '11px', fontWeight: 700 }}>Q&A #{idx + 1}</span>
                        {faqItems.length > 1 && (
                          <button type="button" onClick={() => setFaqItems(faqItems.filter((_, i) => i !== idx))} style={removeBtnStyle}>
                            Remove
                          </button>
                        )}
                      </div>
                      <input type="text" value={item.question} onChange={(e) => { const u = [...faqItems]; u[idx].question = e.target.value; setFaqItems(u); }} placeholder="Question..." style={{ ...inputStyle, marginBottom: '6px' }} />
                      <textarea value={item.answer} onChange={(e) => { const u = [...faqItems]; u[idx].answer = e.target.value; setFaqItems(u); }} placeholder="Answer..." rows={2} style={textareaStyle} />
                    </div>
                  ))}
                </div>
              )}
              {schemaType === 'BreadcrumbList' && (
                <div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
                    <label style={labelStyle}>Breadcrumbs ({breadcrumbItems.length})</label>
                    <button type="button" onClick={() => setBreadcrumbItems([...breadcrumbItems, { name: '', item: '' }])} style={addPillBtnStyle}>
                      + Add Item
                    </button>
                  </div>
                  {breadcrumbItems.map((bc, idx) => (
                    <div key={idx} style={{ display: 'flex', gap: '8px', marginBottom: '8px', alignItems: 'center' }}>
                      <span style={{ fontSize: '12px', fontWeight: 700, width: '20px' }}>#{idx + 1}</span>
                      <input type="text" value={bc.name} onChange={(e) => { const u = [...breadcrumbItems]; u[idx].name = e.target.value; setBreadcrumbItems(u); }} placeholder="Label" style={{ ...inputStyle, flex: 1 }} />
                      <input type="url" value={bc.item} onChange={(e) => { const u = [...breadcrumbItems]; u[idx].item = e.target.value; setBreadcrumbItems(u); }} placeholder="https://example.com" style={{ ...inputStyle, flex: 2 }} />
                      {breadcrumbItems.length > 1 && (
                        <button type="button" onClick={() => setBreadcrumbItems(breadcrumbItems.filter((_, i) => i !== idx))} style={removeBtnStyle}>✕</button>
                      )}
                    </div>
                  ))}
                </div>
              )}
              <div style={{ display: 'flex', gap: '10px', marginTop: '16px' }}>
                <button id="schema-generate-btn" type="submit" disabled={schemaLoading} style={primaryBtnStyle}>
                  {schemaLoading ? 'Generating...' : `⚡ Generate ${schemaType}`}
                </button>
                <button type="button" onClick={handleResetSchema} style={secondaryBtnStyle}>Reset</button>
              </div>
            </form>
            <div style={resultCardStyle}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
                <h4 style={{ margin: 0, fontSize: '15px', fontWeight: 700 }}>JSON-LD Output</h4>
                {schemaResult && (
                  <button id="schema-copy-script-btn" onClick={() => handleCopy(schemaResult.script_tag, 'schema_script')} style={copyBtnStyle}>
                    {copiedKey === 'schema_script' ? '✓ Copied!' : '📋 Copy <script>'}
                  </button>
                )}
              </div>
              {schemaResult ? (
                <pre style={codeBlockStyle}>{schemaResult.script_tag}</pre>
              ) : (
                <div style={placeholderBoxStyle}>
                  <p style={{ margin: 0, color: '#94a3b8', fontSize: '13px' }}>Select schema type and click generate.</p>
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* ============================================================== */}
      {/* TAB 3: SOCIAL PREVIEW */}
      {/* ============================================================== */}
      {activeTab === 'social' && (
        <div style={{ marginTop: '20px' }}>
          {socialError && <div style={errorBannerStyle}>{socialError}</div>}
          <div style={grid2ColStyle}>
            <form onSubmit={handleGenerateSocial} style={formCardStyle}>
              <h4 style={{ margin: '0 0 16px 0', fontSize: '15px', fontWeight: 700 }}>Social Card Inputs</h4>
              <div style={formGroupStyle}>
                <label style={labelStyle}>Title <span style={{ color: '#ef4444' }}>*</span></label>
                <input type="text" value={socialTitle} onChange={(e) => setSocialTitle(e.target.value)} placeholder="Autonomous SEO Intelligence" required style={inputStyle} />
              </div>
              <div style={formGroupStyle}>
                <label style={labelStyle}>Description <span style={{ color: '#ef4444' }}>*</span></label>
                <textarea value={socialDesc} onChange={(e) => setSocialDesc(e.target.value)} rows={3} placeholder="Track rankings on Google Ethiopia." required style={textareaStyle} />
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
                <div style={formGroupStyle}>
                  <label style={labelStyle}>Target URL</label>
                  <input type="url" value={socialUrl} onChange={(e) => setSocialUrl(e.target.value)} placeholder="https://example.com" style={inputStyle} />
                </div>
                <div style={formGroupStyle}>
                  <label style={labelStyle}>Image URL</label>
                  <input type="url" value={socialImage} onChange={(e) => setSocialImage(e.target.value)} placeholder="https://example.com/banner.png" style={inputStyle} />
                </div>
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
                <div style={formGroupStyle}>
                  <label style={labelStyle}>Site Name</label>
                  <input type="text" value={socialSiteName} onChange={(e) => setSocialSiteName(e.target.value)} placeholder="DoxaRank" style={inputStyle} />
                </div>
                <div style={formGroupStyle}>
                  <label style={labelStyle}>Twitter Handle</label>
                  <input type="text" value={socialTwitterSite} onChange={(e) => setSocialTwitterSite(e.target.value)} placeholder="@doxarank" style={inputStyle} />
                </div>
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
                <div style={formGroupStyle}>
                  <label style={labelStyle}>OG Type</label>
                  <select value={socialOgType} onChange={(e) => setSocialOgType(e.target.value)} style={selectStyle}>
                    <option value="website">website</option>
                    <option value="article">article</option>
                    <option value="book">book</option>
                    <option value="profile">profile</option>
                  </select>
                </div>
                <div style={formGroupStyle}>
                  <label style={labelStyle}>Twitter Card</label>
                  <select value={socialTwitterCard} onChange={(e) => setSocialTwitterCard(e.target.value)} style={selectStyle}>
                    <option value="summary_large_image">summary_large_image</option>
                    <option value="summary">summary</option>
                  </select>
                </div>
              </div>
              <div style={{ display: 'flex', gap: '10px', marginTop: '16px' }}>
                <button type="submit" disabled={socialLoading || !socialTitle.trim() || !socialDesc.trim()} style={primaryBtnStyle}>
                  {socialLoading ? 'Generating...' : '⚡ Generate Tags & Preview'}
                </button>
                <button type="button" onClick={handleResetSocial} style={secondaryBtnStyle}>Reset</button>
              </div>
            </form>
            <div style={resultCardStyle}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
                <h4 style={{ margin: 0, fontSize: '15px', fontWeight: 700 }}>Card Preview & Tags</h4>
                {socialResult && (
                  <button onClick={() => handleCopy(socialResult.html, 'social')} style={copyBtnStyle}>
                    {copiedKey === 'social' ? '✓ Copied!' : '📋 Copy Meta Tags'}
                  </button>
                )}
              </div>
              <div style={ogCardPreviewStyle}>
                {socialImage ? (
                  <div style={{ height: '120px', overflow: 'hidden' }}>
                    <img src={socialImage} alt="Preview" onError={(e) => { (e.target as HTMLElement).style.display = 'none'; }} style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
                  </div>
                ) : (
                  <div style={cardImagePlaceholderStyle}><span>🖼️ No image URL specified</span></div>
                )}
                <div style={{ padding: '10px' }}>
                  <span style={{ fontSize: '11px', color: '#64748b', textTransform: 'uppercase', fontWeight: 600 }}>
                    {socialResult?.preview.domain || 'example.com'}
                  </span>
                  <h5 style={{ margin: '4px 0', fontSize: '14px', fontWeight: 700 }}>{socialTitle || 'Title preview'}</h5>
                  <p style={{ margin: 0, fontSize: '12px', color: '#64748b' }}>{socialDesc || 'Description snippet'}</p>
                </div>
              </div>
              {socialResult && <pre style={{ ...codeBlockStyle, marginTop: '12px' }}>{socialResult.html}</pre>}
            </div>
          </div>
        </div>
      )}

      {/* ============================================================== */}
      {/* TAB 4: ROBOTS.TXT (GENERATOR & TESTER) */}
      {/* ============================================================== */}
      {activeTab === 'robots' && (
        <div style={{ marginTop: '20px' }}>
          {robotsError && <div style={errorBannerStyle}>{robotsError}</div>}

          {/* Sub-mode selector */}
          <div style={{ display: 'flex', gap: '8px', marginBottom: '16px' }}>
            <button
              id="robots-mode-generate"
              type="button"
              onClick={() => { setRobotsMode('generate'); setRobotsResult(null); }}
              style={{
                ...schemaPillStyle,
                backgroundColor: robotsMode === 'generate' ? '#eff6ff' : '#ffffff',
                borderColor: robotsMode === 'generate' ? '#2563eb' : '#e2e8f0',
                color: robotsMode === 'generate' ? '#1d4ed8' : '#475569',
                fontWeight: robotsMode === 'generate' ? 700 : 500,
              }}
            >
              🛠️ Robots.txt Generator
            </button>
            <button
              id="robots-mode-test"
              type="button"
              onClick={() => { setRobotsMode('test'); setRobotsResult(null); }}
              style={{
                ...schemaPillStyle,
                backgroundColor: robotsMode === 'test' ? '#eff6ff' : '#ffffff',
                borderColor: robotsMode === 'test' ? '#2563eb' : '#e2e8f0',
                color: robotsMode === 'test' ? '#1d4ed8' : '#475569',
                fontWeight: robotsMode === 'test' ? 700 : 500,
              }}
            >
              🧪 URL Access Tester
            </button>
          </div>

          <div style={grid2ColStyle}>
            {/* Input Form */}
            <form onSubmit={handleProcessRobots} style={formCardStyle}>
              {robotsMode === 'generate' ? (
                <>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
                    <h4 style={{ margin: 0, fontSize: '15px', fontWeight: 700 }}>Rule Groups ({robotsGroups.length})</h4>
                    <button
                      type="button"
                      onClick={() => setRobotsGroups([...robotsGroups, { user_agent: 'Googlebot', disallow: '', allow: '', crawl_delay: '' }])}
                      style={addPillBtnStyle}
                    >
                      + Add Rule Group
                    </button>
                  </div>

                  {robotsGroups.map((group, idx) => (
                    <div key={idx} style={itemBoxStyle}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
                        <span style={{ fontSize: '11px', fontWeight: 700 }}>Group #{idx + 1}</span>
                        {robotsGroups.length > 1 && (
                          <button
                            type="button"
                            onClick={() => setRobotsGroups(robotsGroups.filter((_, i) => i !== idx))}
                            style={removeBtnStyle}
                          >
                            Remove
                          </button>
                        )}
                      </div>
                      <div style={formGroupStyle}>
                        <label style={labelStyle}>User-agent</label>
                        <input
                          type="text"
                          value={group.user_agent}
                          onChange={(e) => {
                            const u = [...robotsGroups];
                            u[idx].user_agent = e.target.value;
                            setRobotsGroups(u);
                          }}
                          placeholder="* or Googlebot"
                          required
                          style={inputStyle}
                        />
                      </div>
                      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '8px' }}>
                        <div style={formGroupStyle}>
                          <label style={labelStyle}>Disallow (1 per line)</label>
                          <textarea
                            value={group.disallow}
                            onChange={(e) => {
                              const u = [...robotsGroups];
                              u[idx].disallow = e.target.value;
                              setRobotsGroups(u);
                            }}
                            rows={3}
                            placeholder="/admin/&#10;/cart/"
                            style={textareaStyle}
                          />
                        </div>
                        <div style={formGroupStyle}>
                          <label style={labelStyle}>Allow (1 per line)</label>
                          <textarea
                            value={group.allow}
                            onChange={(e) => {
                              const u = [...robotsGroups];
                              u[idx].allow = e.target.value;
                              setRobotsGroups(u);
                            }}
                            rows={3}
                            placeholder="/public/&#10;/"
                            style={textareaStyle}
                          />
                        </div>
                      </div>
                      <div style={formGroupStyle}>
                        <label style={labelStyle}>Crawl-delay (Optional seconds)</label>
                        <input
                          type="number"
                          value={group.crawl_delay}
                          onChange={(e) => {
                            const u = [...robotsGroups];
                            u[idx].crawl_delay = e.target.value;
                            setRobotsGroups(u);
                          }}
                          placeholder="e.g. 5"
                          style={inputStyle}
                        />
                      </div>
                    </div>
                  ))}

                  <div style={formGroupStyle}>
                    <label style={labelStyle}>Sitemap Declarations (1 per line)</label>
                    <textarea
                      value={robotsSitemaps}
                      onChange={(e) => setRobotsSitemaps(e.target.value)}
                      rows={2}
                      placeholder="https://example.com/sitemap.xml"
                      style={textareaStyle}
                    />
                  </div>

                  <div style={formGroupStyle}>
                    <label style={labelStyle}>Host (Optional preferred domain)</label>
                    <input
                      type="text"
                      value={robotsHost}
                      onChange={(e) => setRobotsHost(e.target.value)}
                      placeholder="example.com"
                      style={inputStyle}
                    />
                  </div>
                </>
              ) : (
                <>
                  <h4 style={{ margin: '0 0 14px 0', fontSize: '15px', fontWeight: 700 }}>Robots.txt Content & Test Path</h4>
                  <div style={formGroupStyle}>
                    <label style={labelStyle}>Robots.txt Content to Test</label>
                    <textarea
                      id="robots-test-content-input"
                      value={robotsTestContent}
                      onChange={(e) => setRobotsTestContent(e.target.value)}
                      rows={6}
                      required
                      style={textareaStyle}
                    />
                  </div>
                  <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr', gap: '12px' }}>
                    <div style={formGroupStyle}>
                      <label style={labelStyle}>Path or URL to Test <span style={{ color: '#ef4444' }}>*</span></label>
                      <input
                        id="robots-test-path-input"
                        type="text"
                        value={robotsTestPath}
                        onChange={(e) => setRobotsTestPath(e.target.value)}
                        placeholder="/admin/dashboard"
                        required
                        style={inputStyle}
                      />
                    </div>
                    <div style={formGroupStyle}>
                      <label style={labelStyle}>User-agent</label>
                      <input
                        id="robots-test-agent-input"
                        type="text"
                        value={robotsTestAgent}
                        onChange={(e) => setRobotsTestAgent(e.target.value)}
                        placeholder="*"
                        style={inputStyle}
                      />
                    </div>
                  </div>
                </>
              )}

              <div style={{ display: 'flex', gap: '10px', marginTop: '16px' }}>
                <button
                  id="robots-submit-btn"
                  type="submit"
                  disabled={robotsLoading}
                  style={primaryBtnStyle}
                >
                  {robotsLoading ? 'Processing...' : robotsMode === 'generate' ? '⚡ Generate Robots.txt' : '🧪 Test Access'}
                </button>
                <button type="button" onClick={handleResetRobots} style={secondaryBtnStyle}>
                  Reset
                </button>
              </div>
            </form>

            {/* Output Card */}
            <div style={resultCardStyle}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
                <h4 style={{ margin: 0, fontSize: '15px', fontWeight: 700 }}>
                  {robotsMode === 'generate' ? 'Generated Robots.txt' : 'Access Test Verdict'}
                </h4>
                {robotsResult?.content && (
                  <button id="robots-copy-btn" onClick={() => handleCopy(robotsResult.content!, 'robots')} style={copyBtnStyle}>
                    {copiedKey === 'robots' ? '✓ Copied!' : '📋 Copy Robots.txt'}
                  </button>
                )}
              </div>

              {robotsResult ? (
                <div>
                  {robotsResult.action === 'generate' && robotsResult.content && (
                    <>
                      <pre style={codeBlockStyle}>{robotsResult.content}</pre>
                      {robotsResult.warnings && robotsResult.warnings.length > 0 && (
                        <div style={{ marginTop: '12px' }}>
                          <span style={{ fontSize: '12px', fontWeight: 700, color: '#b45309' }}>Robots.txt Warnings:</span>
                          <ul style={{ margin: '4px 0 0 0', paddingLeft: '20px', fontSize: '12px', color: '#92400e' }}>
                            {robotsResult.warnings.map((w, i) => <li key={i}>{w}</li>)}
                          </ul>
                        </div>
                      )}
                    </>
                  )}

                  {robotsResult.action === 'test' && (
                    <div>
                      <div
                        style={{
                          padding: '16px',
                          borderRadius: '8px',
                          backgroundColor: robotsResult.allowed ? '#f0fdf4' : '#fef2f2',
                          border: `1px solid ${robotsResult.allowed ? '#bbf7d0' : '#fecaca'}`,
                          marginBottom: '14px',
                        }}
                      >
                        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                          <span style={{ fontSize: '18px' }}>{robotsResult.allowed ? '✅' : '🚫'}</span>
                          <span
                            style={{
                              fontSize: '15px',
                              fontWeight: 700,
                              color: robotsResult.allowed ? '#166534' : '#991b1b',
                            }}
                          >
                            {robotsResult.status}: {robotsResult.test_path}
                          </span>
                        </div>
                        <p style={{ margin: '8px 0 0 0', fontSize: '13px', color: robotsResult.allowed ? '#14532d' : '#7f1d1d' }}>
                          {robotsResult.reason}
                        </p>
                        {robotsResult.matched_rule && (
                          <div style={{ marginTop: '8px', fontSize: '12px', color: '#475569' }}>
                            Matched rule: <code>{robotsResult.matched_rule}</code>
                          </div>
                        )}
                      </div>
                    </div>
                  )}
                </div>
              ) : (
                <div style={placeholderBoxStyle}>
                  <p style={{ margin: 0, color: '#94a3b8', fontSize: '13px' }}>
                    Configure rule groups or enter test URL to evaluate robots.txt behavior.
                  </p>
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* ============================================================== */}
      {/* TAB 5: XML SITEMAP (GENERATOR & VALIDATOR) */}
      {/* ============================================================== */}
      {activeTab === 'sitemap' && (
        <div style={{ marginTop: '20px' }}>
          {sitemapError && <div style={errorBannerStyle}>{sitemapError}</div>}

          {/* Sub-mode selector */}
          <div style={{ display: 'flex', gap: '8px', marginBottom: '16px' }}>
            <button
              id="sitemap-mode-generate"
              type="button"
              onClick={() => { setSitemapMode('generate'); setSitemapResult(null); }}
              style={{
                ...schemaPillStyle,
                backgroundColor: sitemapMode === 'generate' ? '#eff6ff' : '#ffffff',
                borderColor: sitemapMode === 'generate' ? '#2563eb' : '#e2e8f0',
                color: sitemapMode === 'generate' ? '#1d4ed8' : '#475569',
                fontWeight: sitemapMode === 'generate' ? 700 : 500,
              }}
            >
              🗺️ Sitemap Generator
            </button>
            <button
              id="sitemap-mode-validate"
              type="button"
              onClick={() => { setSitemapMode('validate'); setSitemapResult(null); }}
              style={{
                ...schemaPillStyle,
                backgroundColor: sitemapMode === 'validate' ? '#eff6ff' : '#ffffff',
                borderColor: sitemapMode === 'validate' ? '#2563eb' : '#e2e8f0',
                color: sitemapMode === 'validate' ? '#1d4ed8' : '#475569',
                fontWeight: sitemapMode === 'validate' ? 700 : 500,
              }}
            >
              🔍 Local XML Validator
            </button>
          </div>

          <div style={grid2ColStyle}>
            {/* Input Form */}
            <form onSubmit={handleProcessSitemap} style={formCardStyle}>
              {sitemapMode === 'generate' ? (
                <>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
                    <h4 style={{ margin: 0, fontSize: '15px', fontWeight: 700 }}>Sitemap URLs ({sitemapEntries.length})</h4>
                    <button
                      type="button"
                      onClick={() => setSitemapEntries([...sitemapEntries, { loc: '', lastmod: new Date().toISOString().split('T')[0], changefreq: 'weekly', priority: '0.8' }])}
                      style={addPillBtnStyle}
                    >
                      + Add URL Entry
                    </button>
                  </div>

                  {sitemapEntries.map((item, idx) => (
                    <div key={idx} style={itemBoxStyle}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '6px' }}>
                        <span style={{ fontSize: '11px', fontWeight: 700 }}>URL #{idx + 1}</span>
                        {sitemapEntries.length > 1 && (
                          <button
                            type="button"
                            onClick={() => setSitemapEntries(sitemapEntries.filter((_, i) => i !== idx))}
                            style={removeBtnStyle}
                          >
                            Remove
                          </button>
                        )}
                      </div>
                      <div style={formGroupStyle}>
                        <label style={labelStyle}>URL (loc) <span style={{ color: '#ef4444' }}>*</span></label>
                        <input
                          type="url"
                          value={item.loc}
                          onChange={(e) => {
                            const u = [...sitemapEntries];
                            u[idx].loc = e.target.value;
                            setSitemapEntries(u);
                          }}
                          placeholder="https://example.com/page"
                          required
                          style={inputStyle}
                        />
                      </div>
                      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '8px' }}>
                        <div style={formGroupStyle}>
                          <label style={labelStyle}>Lastmod</label>
                          <input
                            type="date"
                            value={item.lastmod}
                            onChange={(e) => {
                              const u = [...sitemapEntries];
                              u[idx].lastmod = e.target.value;
                              setSitemapEntries(u);
                            }}
                            style={inputStyle}
                          />
                        </div>
                        <div style={formGroupStyle}>
                          <label style={labelStyle}>Changefreq</label>
                          <select
                            value={item.changefreq}
                            onChange={(e) => {
                              const u = [...sitemapEntries];
                              u[idx].changefreq = e.target.value;
                              setSitemapEntries(u);
                            }}
                            style={selectStyle}
                          >
                            <option value="daily">daily</option>
                            <option value="weekly">weekly</option>
                            <option value="monthly">monthly</option>
                            <option value="hourly">hourly</option>
                            <option value="yearly">yearly</option>
                            <option value="always">always</option>
                            <option value="never">never</option>
                          </select>
                        </div>
                        <div style={formGroupStyle}>
                          <label style={labelStyle}>Priority</label>
                          <input
                            type="number"
                            step="0.1"
                            min="0.0"
                            max="1.0"
                            value={item.priority}
                            onChange={(e) => {
                              const u = [...sitemapEntries];
                              u[idx].priority = e.target.value;
                              setSitemapEntries(u);
                            }}
                            placeholder="0.8"
                            style={inputStyle}
                          />
                        </div>
                      </div>
                    </div>
                  ))}
                </>
              ) : (
                <>
                  <h4 style={{ margin: '0 0 12px 0', fontSize: '15px', fontWeight: 700 }}>Paste XML Sitemap</h4>
                  <div style={formGroupStyle}>
                    <label style={labelStyle}>Sitemap XML String <span style={{ color: '#ef4444' }}>*</span></label>
                    <textarea
                      id="sitemap-xml-input"
                      value={sitemapXmlContent}
                      onChange={(e) => setSitemapXmlContent(e.target.value)}
                      rows={8}
                      placeholder="<?xml version='1.0' encoding='UTF-8'?>&#10;<urlset xmlns='http://www.sitemaps.org/schemas/sitemap/0.9'>&#10;  <url>&#10;    <loc>https://example.com/</loc>&#10;  </url>&#10;</urlset>"
                      required
                      style={textareaStyle}
                    />
                  </div>
                </>
              )}

              <div style={{ display: 'flex', gap: '10px', marginTop: '16px' }}>
                <button id="sitemap-submit-btn" type="submit" disabled={sitemapLoading} style={primaryBtnStyle}>
                  {sitemapLoading ? 'Processing...' : sitemapMode === 'generate' ? '⚡ Generate XML Sitemap' : '🔍 Validate XML'}
                </button>
                <button type="button" onClick={handleResetSitemap} style={secondaryBtnStyle}>
                  Reset
                </button>
              </div>
            </form>

            {/* Sitemap Output */}
            <div style={resultCardStyle}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
                <h4 style={{ margin: 0, fontSize: '15px', fontWeight: 700 }}>
                  {sitemapMode === 'generate' ? 'Generated XML Sitemap' : 'Validation Report'}
                </h4>
                {sitemapResult?.xml && (
                  <button id="sitemap-copy-btn" onClick={() => handleCopy(sitemapResult.xml!, 'sitemap')} style={copyBtnStyle}>
                    {copiedKey === 'sitemap' ? '✓ Copied XML!' : '📋 Copy XML'}
                  </button>
                )}
              </div>

              {sitemapResult ? (
                <div>
                  {sitemapResult.action === 'generate' && sitemapResult.xml && (
                    <>
                      <pre style={codeBlockStyle}>{sitemapResult.xml}</pre>
                      <div style={{ marginTop: '8px', fontSize: '12px', color: '#64748b' }}>
                        Total URLs: <strong>{sitemapResult.metrics?.url_count}</strong> | Size: <strong>{sitemapResult.metrics?.byte_size} bytes</strong>
                      </div>
                    </>
                  )}

                  {sitemapResult.action === 'validate' && (
                    <div>
                      <div
                        style={{
                          padding: '14px',
                          borderRadius: '8px',
                          backgroundColor: sitemapResult.is_valid ? '#f0fdf4' : '#fef2f2',
                          border: `1px solid ${sitemapResult.is_valid ? '#bbf7d0' : '#fecaca'}`,
                          marginBottom: '12px',
                        }}
                      >
                        <span style={{ fontSize: '14px', fontWeight: 700, color: sitemapResult.is_valid ? '#166534' : '#991b1b' }}>
                          {sitemapResult.is_valid ? '✅ VALID SITEMAP PROTOCOL' : '❌ INVALID SITEMAP STRUCTURE'}
                        </span>
                        <div style={{ fontSize: '12px', marginTop: '4px', color: '#475569' }}>
                          Parsed URLs: <strong>{sitemapResult.url_count}</strong> | Root element: <code>&lt;{sitemapResult.root_tag}&gt;</code>
                        </div>
                      </div>

                      {sitemapResult.errors && sitemapResult.errors.length > 0 && (
                        <div style={{ marginBottom: '12px' }}>
                          <span style={{ fontSize: '12px', fontWeight: 700, color: '#b91c1c' }}>Errors Found:</span>
                          <ul style={{ margin: '4px 0 0 0', paddingLeft: '20px', fontSize: '12px', color: '#dc2626' }}>
                            {sitemapResult.errors.map((err, i) => <li key={i}>{err}</li>)}
                          </ul>
                        </div>
                      )}

                      {sitemapResult.warnings && sitemapResult.warnings.length > 0 && (
                        <div>
                          <span style={{ fontSize: '12px', fontWeight: 700, color: '#b45309' }}>Recommendations:</span>
                          <ul style={{ margin: '4px 0 0 0', paddingLeft: '20px', fontSize: '12px', color: '#d97706' }}>
                            {sitemapResult.warnings.map((w, i) => <li key={i}>{w}</li>)}
                          </ul>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              ) : (
                <div style={placeholderBoxStyle}>
                  <p style={{ margin: 0, color: '#94a3b8', fontSize: '13px' }}>
                    Generate valid XML sitemaps or validate existing markup locally without SSRF risks.
                  </p>
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* ============================================================== */}
      {/* TAB 6: HREFLANG BUILDER */}
      {/* ============================================================== */}
      {activeTab === 'hreflang' && (
        <div style={{ marginTop: '20px' }}>
          {hreflangError && <div style={errorBannerStyle}>{hreflangError}</div>}

          <div style={grid2ColStyle}>
            {/* Form */}
            <form onSubmit={handleGenerateHreflang} style={formCardStyle}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
                <h4 style={{ margin: 0, fontSize: '15px', fontWeight: 700 }}>Language Cluster ({hreflangEntries.length})</h4>
                <div style={{ display: 'flex', gap: '6px' }}>
                  <button
                    type="button"
                    onClick={() => setHreflangEntries([...hreflangEntries, { lang: '', url: '' }])}
                    style={addPillBtnStyle}
                  >
                    + Add Language
                  </button>
                </div>
              </div>

              {/* Ethiopian Quick Presets */}
              <div style={{ display: 'flex', gap: '6px', marginBottom: '14px', flexWrap: 'wrap' }}>
                <span style={{ fontSize: '11px', color: '#64748b', fontWeight: 600 }}>Quick Presets:</span>
                <button
                  type="button"
                  onClick={() => {
                    if (!hreflangEntries.some((e) => e.lang === 'am')) {
                      setHreflangEntries([...hreflangEntries, { lang: 'am', url: 'https://example.com/am/' }]);
                    }
                  }}
                  style={presetBtnStyle}
                >
                  + Amharic (am)
                </button>
                <button
                  type="button"
                  onClick={() => {
                    if (!hreflangEntries.some((e) => e.lang === 'om')) {
                      setHreflangEntries([...hreflangEntries, { lang: 'om', url: 'https://example.com/om/' }]);
                    }
                  }}
                  style={presetBtnStyle}
                >
                  + Afaan Oromo (om)
                </button>
                <button
                  type="button"
                  onClick={() => {
                    if (!hreflangEntries.some((e) => e.lang === 'ti')) {
                      setHreflangEntries([...hreflangEntries, { lang: 'ti', url: 'https://example.com/ti/' }]);
                    }
                  }}
                  style={presetBtnStyle}
                >
                  + Tigrinya (ti)
                </button>
              </div>

              {hreflangEntries.map((item, idx) => (
                <div key={idx} style={{ display: 'flex', gap: '8px', marginBottom: '8px', alignItems: 'center' }}>
                  <input
                    type="text"
                    value={item.lang}
                    onChange={(e) => {
                      const u = [...hreflangEntries];
                      u[idx].lang = e.target.value;
                      setHreflangEntries(u);
                    }}
                    placeholder="e.g. en, am, om"
                    required
                    style={{ ...inputStyle, width: '90px' }}
                  />
                  <input
                    type="url"
                    value={item.url}
                    onChange={(e) => {
                      const u = [...hreflangEntries];
                      u[idx].url = e.target.value;
                      setHreflangEntries(u);
                    }}
                    placeholder="https://example.com/am/page"
                    required
                    style={{ ...inputStyle, flex: 1 }}
                  />
                  {hreflangEntries.length > 1 && (
                    <button
                      type="button"
                      onClick={() => setHreflangEntries(hreflangEntries.filter((_, i) => i !== idx))}
                      style={removeBtnStyle}
                    >
                      ✕
                    </button>
                  )}
                </div>
              ))}

              <div style={{ ...formGroupStyle, marginTop: '14px' }}>
                <label style={labelStyle}>x-default Fallback URL (Recommended)</label>
                <input
                  type="url"
                  value={hreflangXDefault}
                  onChange={(e) => setHreflangXDefault(e.target.value)}
                  placeholder="https://example.com/"
                  style={inputStyle}
                />
              </div>

              <div style={{ display: 'flex', gap: '10px', marginTop: '16px' }}>
                <button id="hreflang-submit-btn" type="submit" disabled={hreflangLoading} style={primaryBtnStyle}>
                  {hreflangLoading ? 'Generating...' : '⚡ Generate hreflang Tags'}
                </button>
                <button type="button" onClick={handleResetHreflang} style={secondaryBtnStyle}>
                  Reset
                </button>
              </div>
            </form>

            {/* Output */}
            <div style={resultCardStyle}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
                <h4 style={{ margin: 0, fontSize: '15px', fontWeight: 700 }}>hreflang Annotations</h4>
                {hreflangResult && (
                  <button id="hreflang-copy-btn" onClick={() => handleCopy(hreflangResult.html, 'hreflang')} style={copyBtnStyle}>
                    {copiedKey === 'hreflang' ? '✓ Copied HTML!' : '📋 Copy HTML Tags'}
                  </button>
                )}
              </div>

              {hreflangResult ? (
                <div>
                  <span style={{ fontSize: '12px', fontWeight: 700, color: '#334155' }}>HTML Link Tags (&lt;head&gt;):</span>
                  <pre style={{ ...codeBlockStyle, marginTop: '4px', marginBottom: '12px' }}>{hreflangResult.html}</pre>

                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '4px' }}>
                    <span style={{ fontSize: '12px', fontWeight: 700, color: '#334155' }}>XML Sitemap Snippet:</span>
                    <button onClick={() => handleCopy(hreflangResult.xml_snippet, 'hreflang_xml')} style={copyBtnStyle}>
                      {copiedKey === 'hreflang_xml' ? '✓ Copied!' : 'Copy XML'}
                    </button>
                  </div>
                  <pre style={{ ...codeBlockStyle, marginBottom: '12px' }}>{hreflangResult.xml_snippet}</pre>

                  {hreflangResult.warnings && hreflangResult.warnings.length > 0 && (
                    <div>
                      <span style={{ fontSize: '12px', fontWeight: 700, color: '#b45309' }}>Recommendations:</span>
                      <ul style={{ margin: '4px 0 0 0', paddingLeft: '20px', fontSize: '12px', color: '#d97706' }}>
                        {hreflangResult.warnings.map((w, i) => <li key={i}>{w}</li>)}
                      </ul>
                    </div>
                  )}
                </div>
              ) : (
                <div style={placeholderBoxStyle}>
                  <p style={{ margin: 0, color: '#94a3b8', fontSize: '13px' }}>
                    Add English, Amharic, and Afaan Oromo variants to generate reciprocal hreflang annotations.
                  </p>
                </div>
              )}
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
  gap: '12px',
  borderBottom: '1px solid #e2e8f0',
  paddingBottom: '2px',
  flexWrap: 'wrap',
};

const tabButtonStyle: React.CSSProperties = {
  background: 'none',
  border: 'none',
  padding: '8px 12px',
  fontSize: '13px',
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

const presetBtnStyle: React.CSSProperties = {
  backgroundColor: '#f1f5f9',
  border: '1px solid #cbd5e1',
  borderRadius: '12px',
  padding: '2px 8px',
  fontSize: '11px',
  fontWeight: 600,
  color: '#1e293b',
  cursor: 'pointer',
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
