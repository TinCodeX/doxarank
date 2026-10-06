import React, { createContext, useContext, useState, useEffect } from 'react';

export type SupportedLanguage = 'en' | 'am' | 'om';

export interface LanguageContextType {
  language: SupportedLanguage;
  setLanguage: (lang: SupportedLanguage) => void;
  t: (key: string, defaultText?: string) => string;
  formatStatus: (status?: string | null) => string;
  formatSeverity: (severity?: string | null) => string;
  formatDevice: (device?: string | null) => string;
  formatDate: (date: string | number | Date | null | undefined) => string;
  formatNumber: (num: number | null | undefined) => string;
}

const STORAGE_KEY = 'doxarank_app_language';

// Comprehensive dictionary for English, Amharic (አማርኛ), and Afaan Oromoo
export const translations: Record<SupportedLanguage, Record<string, string>> = {
  en: {
    // Brand & Header
    'brand.title': 'DoxaRank',
    'brand.subtitle': 'Ethiopia SEO Intelligence',
    'header.current_project': 'Current Project',
    'header.no_project': 'No active project selected',
    'header.tools': 'Tools',
    'header.check_serp': 'Check SERP',
    'header.checking': 'Checking...',
    'header.track_keyword': 'Track Keyword',
    'header.upgrade': 'Upgrade',
    'header.manage': 'Manage',
    'header.sign_out': 'Sign Out',
    'header.select_language': 'Language',

    // Navigation Tabs
    'nav.overview': 'Overview',
    'nav.keywords': 'Target Keywords',
    'nav.audits': 'Site Audits',
    'nav.competitors': 'Competitors',
    'nav.recommendations': 'Recommendations',
    'nav.content': 'Content AI & Drafts',
    'nav.analytics': 'Search Analytics',
    'nav.reports': 'White-Label Reports',
    'nav.tools': 'Free SEO Tools',
    'nav.operations': 'Autonomous Operations',
    'nav.projects': 'Projects Manager',

    // Project Selector
    'projects.new': '+ New',
    'projects.loading': 'Loading projects...',
    'projects.create_first': '+ Create first website',
    'projects.all_projects': 'All Website Projects',
    'projects.manage_desc': 'Manage monitored web properties across Google Ethiopia.',
    'projects.add_new': '+ Add New Project',
    'projects.no_projects': 'No projects created yet.',
    'projects.create_first_btn': 'Create First Project',
    'projects.created': 'Created',
    'projects.active': 'Active',

    // KPI Cards & Metrics
    'kpi.total_keywords': 'Total Keywords',
    'kpi.tracking_et': 'Tracking on google.com.et',
    'kpi.avg_position': 'Avg SERP Position',
    'kpi.et_weighted': 'Ethiopia weighted ranking',
    'kpi.top_3': 'Top 3 Rankings',
    'kpi.prime_visibility': 'Prime search visibility',
    'kpi.top_10': 'Top 10 Rankings',
    'kpi.first_page': 'Google ET Page 1 dominance',
    'kpi.in_top_100': 'In Top 100',
    'kpi.indexed': 'Indexed on google.com.et',
    'kpi.search_demand': 'Local Search Demand',
    'kpi.multilingual_demand': 'Amharic, Afaan Oromoo & English',

    // Actions & Buttons
    'action.refresh': 'Refresh',
    'action.refreshing': 'Refreshing...',
    'action.save': 'Save',
    'action.cancel': 'Cancel',
    'action.delete': 'Delete',
    'action.edit': 'Edit',
    'action.close': 'Close',
    'action.export_csv': 'Export CSV',
    'action.filter': 'Filter',
    'action.search': 'Search',
    'action.add': 'Add',
    'action.view': 'View',
    'action.submit': 'Submit',
    'action.confirm': 'Confirm',
    'action.apply': 'Apply',
    'action.retry': 'Retry',
    'action.run_now': 'Run Now',

    // Table Headers
    'table.keyword': 'Keyword Query',
    'table.position': 'Position',
    'table.previous': 'Previous',
    'table.change': 'Change',
    'table.url': 'Ranked URL',
    'table.engine': 'Search Engine',
    'table.device': 'Device',
    'table.volume': 'Search Volume',
    'table.cpc': 'Est. CPC',
    'table.intent': 'Intent',
    'table.language': 'Language',
    'table.last_checked': 'Last Checked',
    'table.actions': 'Actions',
    'table.status': 'Status',
    'table.severity': 'Severity',
    'table.issue': 'Issue Description',
    'table.query': 'Query',
    'table.rank': 'Rank',
    'table.delta': 'Delta',
    'table.search_vol': 'Search Vol',
    'table.target_et': 'Target (ET)',
    'table.indexed_title': 'Indexed Title & URL',
    'table.recorded_at': 'Recorded At',

    // Empty States
    'empty.no_keywords': 'No keywords tracked yet.',
    'empty.no_keywords_desc': 'Add target search terms in English, Amharic, or Afaan Oromoo to monitor daily positions on Google Ethiopia.',
    'empty.add_first_keyword': 'Track First Keyword',
    'empty.no_rankings': 'No ranking data recorded yet.',
    'empty.no_rankings_desc': 'Trigger SERP check or wait for the automated crawler to record live ranking history.',
    'empty.no_audits': 'No technical audit performed yet.',
    'empty.run_audit_btn': 'Run Technical Audit',
    'empty.no_competitors': 'No competitors configured yet.',
    'empty.add_competitor_btn': 'Add Competitor Domain',

    // Sub-Tabs
    'subtab.all_views': 'All Views',
    'subtab.audit_feed': 'Audit Feed',
    'subtab.action_plan': 'Action Plan & Tasks',
    'subtab.serp_insights': 'SERP Insights',
    'subtab.ai_strategy': 'AI Strategy Generator',
    'subtab.all_content': 'All Content',
    'subtab.content_briefs': 'Content Briefs & Outlines',
    'subtab.content_drafts': 'Drafts & Generated Articles',
    'subtab.all_operations': 'All Operations',
    'subtab.specialized_agents': 'Specialized Agents',
    'subtab.continuous_ops': 'Continuous Ops',
    'subtab.event_logs': 'Event Logs',
    'subtab.live_monitoring': 'Live Monitoring',
    'subtab.auto_remediation': 'Auto-Remediation',
    'subtab.observability': 'Platform Observability',
    'subtab.long_term_strategy': 'Long-Term Strategy',
    'subtab.feed': 'Recommendations Feed',
    'subtab.actions': 'Action Tracker',
    'subtab.insights': 'Strategic Insights',
    'subtab.generator': 'AI Recommendations',
    'subtab.briefs': 'Content Briefs',
    'subtab.drafts': 'Content Drafts',
    'subtab.agents': 'Specialized Agents',
    'subtab.monitoring': 'Autonomous Monitoring',
    'subtab.remediation': 'Remediation Engine',
    'subtab.continuous': 'Recurring Operations',
    'subtab.events': 'Live Events',
    'subtab.strategy': 'Long-Term Strategy',
    'subtab.health': 'Platform Health',

    // Dynamic Statuses
    'status.active': 'Active',
    'status.paused': 'Paused',
    'status.running': 'Running',
    'status.completed': 'Completed',
    'status.failed': 'Failed',
    'status.pending': 'Pending',
    'status.found': 'Found',
    'status.not_found': 'Not in Top 100',
    'status.not_in_top_100': 'Not in top 100',
    'status.check_failed': 'Check failed',
    'status.not_checked': 'Not checked',
    'status.success': 'Success',
    'status.error': 'Check Failed',
    'status.warning': 'Warning',
    'status.passed': 'Passed',

    // Dynamic Severities
    'severity.critical': 'Critical',
    'severity.high': 'High',
    'severity.medium': 'Medium',
    'severity.low': 'Low',
    'severity.info': 'Info',

    // Devices
    'device.desktop': 'Desktop',
    'device.mobile': 'Mobile',
    'device.tablet': 'Tablet',

    // Auth
    'auth.sign_in': 'Sign in to your account',
    'auth.sign_in_desc': 'Sign in to access your Google Ethiopia SEO intelligence',
    'auth.login_subtitle': 'Sign in to access your Google Ethiopia SEO intelligence',
    'auth.email': 'Email Address',
    'auth.password': 'Password',
    'auth.first_name': 'First Name',
    'auth.last_name': 'Last Name',
    'auth.create_account': 'Create one now',
    'auth.dont_have_account': "Don't have an account?",
    'auth.already_have_account': 'Already have an account?',
    'auth.start_free': 'Start Free',
    'auth.signing_in': 'Authenticating...',
    'auth.no_account': "Don't have an account yet?",
    'auth.register_subtitle': 'Start tracking rankings on Google Ethiopia and optimizing technical SEO',
    'auth.creating_account': 'Creating account...',
    'auth.create_account_btn': 'Create Account & Start Free',
    'auth.already_account': 'Already have an account?',
    'auth.sign_in_link': 'Sign in',
  },

  am: {
    // Brand & Header
    'brand.title': 'ዶክሳራንክ',
    'brand.subtitle': 'የኢትዮጵያ የፍለጋ ሞተር መረጃ',
    'header.current_project': 'የአሁኑ ፕሮጀክት',
    'header.no_project': 'ምንም ንቁ ፕሮጀክት አልተመረጠም',
    'header.tools': 'መሳሪያዎች',
    'header.check_serp': 'ደረጃ ፈትሽ',
    'header.checking': 'በመፈተሽ ላይ...',
    'header.track_keyword': 'ቁልፍ ቃል መዝግብ',
    'header.upgrade': 'ዕቅድ አሻሽል',
    'header.manage': 'አስተዳድር',
    'header.sign_out': 'ውጣ',
    'header.select_language': 'ቋንቋ',

    // Navigation Tabs
    'nav.overview': 'አጠቃላይ እይታ',
    'nav.keywords': 'የታለሙ ቁልፍ ቃላት',
    'nav.audits': 'የድረ-ገጽ ኦዲት',
    'nav.competitors': 'ተፎካካሪዎች',
    'nav.recommendations': 'የማሻሻያ ሃሳቦች',
    'nav.content': 'የይዘት ረቂቅ እና አዘጋጅ',
    'nav.analytics': 'የፍለጋ ትንታኔ',
    'nav.reports': 'የሪፖርት ዝግጅት',
    'nav.tools': 'ነፃ የSEO መሳሪያዎች',
    'nav.operations': 'አውቶሜትድ ክትትል',
    'nav.projects': 'የፕሮጀክቶች አስተዳዳሪ',

    // Project Selector
    'projects.new': '+ አዲስ',
    'projects.loading': 'ፕሮጀክቶች በመጫን ላይ...',
    'projects.create_first': '+ የመጀመሪያውን ድረ-ገጽ ይፍጠሩ',
    'projects.all_projects': 'ሁሉም የድረ-ገጽ ፕሮጀክቶች',
    'projects.manage_desc': 'በጉግል ኢትዮጵያ የሚከታተሉትን ድረ-ገጾች ያስተዳድሩ።',
    'projects.add_new': '+ አዲስ ፕሮጀክት ጨምር',
    'projects.no_projects': 'እስካሁን ምንም ፕሮጀክት አልተፈጠረም።',
    'projects.create_first_btn': 'የመጀመሪያውን ፕሮጀክት ይፍጠሩ',
    'projects.created': 'የተፈጠረበት',
    'projects.active': 'ንቁ',

    // KPI Cards & Metrics
    'kpi.total_keywords': 'ጠቅላላ ቁልፍ ቃላት',
    'kpi.tracking_et': 'በgoogle.com.et ላይ ክትትል',
    'kpi.avg_position': 'አማካይ የደረጃ አቀማመጥ',
    'kpi.et_weighted': 'የኢትዮጵያ የፍለጋ ክብደት',
    'kpi.top_3': 'ከከፍተኛ 3 ውስጥ',
    'kpi.prime_visibility': 'ቀዳሚ የፍለጋ ታይነት',
    'kpi.top_10': 'ከከፍተኛ 10 ውስጥ',
    'kpi.first_page': 'የጉግል ገጽ 1 የበላይነት',
    'kpi.in_top_100': 'ከከፍተኛ 100 ውስጥ',
    'kpi.indexed': 'በጉግል የተመዘገቡ ገጾች',
    'kpi.search_demand': 'የአካባቢ ፍለጋ ፍላጎት',
    'kpi.multilingual_demand': 'አማርኛ፣ አፋን ኦሮሞ እና እንግሊዝኛ',

    // Actions & Buttons
    'action.refresh': 'አድስ',
    'action.refreshing': 'በማደስ ላይ...',
    'action.save': 'አስቀምጥ',
    'action.cancel': 'ይቅር',
    'action.delete': 'አጥፋ',
    'action.edit': 'አስተካክል',
    'action.close': 'ዝጋ',
    'action.export_csv': 'በCSV አውርድ',
    'action.filter': 'አጣራ',
    'action.search': 'ፈልግ',
    'action.add': 'ጨምር',
    'action.view': 'ተመልከት',
    'action.submit': 'አስገባ',
    'action.confirm': 'አረጋግጥ',
    'action.apply': 'ተግብር',
    'action.retry': 'እንደገና ሞክር',
    'action.run_now': 'አሁን አስጀምር',

    // Table Headers
    'table.keyword': 'የፍለጋ ቃል',
    'table.position': 'የአሁኑ ደረጃ',
    'table.previous': 'ያለፈው ደረጃ',
    'table.change': 'ለውጥ',
    'table.url': 'የገጹ አድራሻ (URL)',
    'table.engine': 'የፍለጋ ሞተር',
    'table.device': 'መሳሪያ',
    'table.volume': 'የፍለጋ መጠን',
    'table.cpc': 'ግምታዊ ዋጋ (CPC)',
    'table.intent': 'የፍለጋ ዓላማ',
    'table.language': 'ቋንቋ',
    'table.last_checked': 'መጨረሻ የተፈተሸበት',
    'table.actions': 'ተግባራት',
    'table.status': 'ሁኔታ',
    'table.severity': 'ክብደት',
    'table.issue': 'የችግሩ ዝርዝር',
    'table.query': 'የፍለጋ ቃል',
    'table.rank': 'ደረጃ',
    'table.delta': 'ልዩነት',
    'table.search_vol': 'የፍለጋ መጠን',
    'table.target_et': 'ኢላማ (ኢትዮጵያ)',
    'table.indexed_title': 'የተመዘገበ ርዕስ እና URL',
    'table.recorded_at': 'የተመዘገበበት ጊዜ',

    // Empty States
    'empty.no_keywords': 'እስካሁን ምንም ቁልፍ ቃል አልተመዘገበም።',
    'empty.no_keywords_desc': 'በጉግል ኢትዮጵያ ላይ ያለውን የደረጃ ሁኔታ ለመከታተል በአማርኛ፣ አፋን ኦሮሞ ወይም እንግሊዝኛ ቁልፍ ቃላትን ያስገቡ።',
    'empty.add_first_keyword': 'የመጀመሪያውን ቁልፍ ቃል መዝግብ',
    'empty.no_rankings': 'እስካሁን ምንም የደረጃ መረጃ አልተገኘም።',
    'empty.no_rankings_desc': 'የደረጃ ፍተሻን ያስጀምሩ ወይም ራስ-ሰር ፈላጊው መረጃ እስኪያሰባስብ ይጠብቁ።',
    'empty.no_audits': 'እስካሁን ምንም ቴክኒካል ኦዲት አልተከናወነም።',
    'empty.run_audit_btn': 'ቴክኒካል ኦዲት አስጀምር',
    'empty.no_competitors': 'ምንም ተፎካካሪ ድረ-ገጽ አልተመዘገበም።',
    'empty.add_competitor_btn': 'ተፎካካሪ ጨምር',

    // Sub-Tabs
    'subtab.all_views': 'ሁሉም እይታዎች',
    'subtab.audit_feed': 'የምክሮች ዝርዝር',
    'subtab.action_plan': 'የተግባር እቅድ እና ስራዎች',
    'subtab.serp_insights': 'የSERP ግንዛቤዎች',
    'subtab.ai_strategy': 'የAI ስትራቴጂ ማመንጫ',
    'subtab.all_content': 'ሁሉም ይዘቶች',
    'subtab.content_briefs': 'የይዘት መመሪያዎች',
    'subtab.content_drafts': 'የተዘጋጁ ረቂቆች',
    'subtab.all_operations': 'ሁሉም ስራዎች',
    'subtab.specialized_agents': 'ልዩ ረዳቶች',
    'subtab.continuous_ops': 'ተከታታይ ስራዎች',
    'subtab.event_logs': 'የክስተቶች መዝገብ',
    'subtab.live_monitoring': 'የቀጥታ ክትትል',
    'subtab.auto_remediation': 'ራስ-ሰር ማስተካከያ',
    'subtab.observability': 'ክትትል እና ስህተት መመርመሪያ',
    'subtab.long_term_strategy': 'የረጅም ጊዜ ስትራቴጂ',
    'subtab.feed': 'የምክሮች ዝርዝር',
    'subtab.actions': 'የተግባራት መከታተያ',
    'subtab.insights': 'ስትራቴጂካዊ ግንዛቤዎች',
    'subtab.generator': 'የAI ምክሮች ማመንጫ',
    'subtab.briefs': 'የይዘት መመሪያዎች',
    'subtab.drafts': 'የተዘጋጁ ረቂቆች',
    'subtab.agents': 'ልዩ ረዳቶች',
    'subtab.monitoring': 'አውቶሜትድ ክትትል',
    'subtab.remediation': 'የችግር ማስተካከያ',
    'subtab.continuous': 'ተከታታይ ስራዎች',
    'subtab.events': 'የቀጥታ ክስተቶች',
    'subtab.strategy': 'የረጅም ጊዜ እቅድ',
    'subtab.health': 'የስርዓት ጤንነት',

    // Dynamic Statuses
    'status.active': 'ንቁ',
    'status.paused': 'የቆመ',
    'status.running': 'በመስራት ላይ',
    'status.completed': 'የተጠናቀቀ',
    'status.failed': 'አልተሳካም',
    'status.pending': 'በመጠባበቅ ላይ',
    'status.found': 'ተገኝቷል',
    'status.not_found': 'ከ100 ውስጥ አልተገኘም',
    'status.not_in_top_100': 'ከ100 ውስጥ አልተገኘም',
    'status.check_failed': 'ምርመራው አልተሳካም',
    'status.not_checked': 'አልተመረመረም',
    'status.success': 'ተሳክቷል',
    'status.error': 'ምርመራው አልተሳካም',
    'status.warning': 'ማስጠንቀቂያ',
    'status.passed': 'አልፏል',

    // Dynamic Severities
    'severity.critical': 'ወሳኝ',
    'severity.high': 'ከፍተኛ',
    'severity.medium': 'መካከለኛ',
    'severity.low': 'ዝቅተኛ',
    'severity.info': 'መረጃ',

    // Devices
    'device.desktop': 'ኮምፒውተር',
    'device.mobile': 'ሞባይል',
    'device.tablet': 'ታብሌት',

    // Auth
    'auth.sign_in': 'ወደ መለያዎ ይግቡ',
    'auth.sign_in_desc': 'የኢትዮጵያ SEO መረጃዎን ለማግኘት ይግቡ',
    'auth.login_subtitle': 'የጉግል ኢትዮጵያ SEO መረጃዎን ለማግኘት ይግቡ',
    'auth.email': 'የኢሜይል አድራሻ',
    'auth.password': 'የይለፍ ቃል',
    'auth.first_name': 'ስም',
    'auth.last_name': 'የአባት ስም',
    'auth.create_account': 'አሁን ይመዝገቡ',
    'auth.dont_have_account': 'መለያ የለዎትም?',
    'auth.already_have_account': 'አስቀድመው መለያ አለዎት?',
    'auth.start_free': 'በነጻ ይጀምሩ',
    'auth.signing_in': 'በማረጋገጥ ላይ...',
    'auth.no_account': 'እስካሁን መለያ የለዎትም?',
    'auth.register_subtitle': 'በጉግል ኢትዮጵያ ላይ ደረጃዎችን መከታተል እና የቴክኒክ SEOን ማሻሻል ይጀምሩ',
    'auth.creating_account': 'መለያ በመፍጠር ላይ...',
    'auth.create_account_btn': 'መለያ ይፍጠሩ እና በነፃ ይጀምሩ',
    'auth.already_account': 'አስቀድመው መለያ አለዎት?',
    'auth.sign_in_link': 'ግባ',
  },

  om: {
    // Brand & Header
    'brand.title': 'DoxaRank',
    'brand.subtitle': 'Odeeffannoo SEO Itoophiyaa',
    'header.current_project': 'Pirojektii Ammaa',
    'header.no_project': 'Pirojektiin filatame hin jiru',
    'header.tools': 'Meeshaalee',
    'header.check_serp': 'Sadarkaa Sakatta\'i',
    'header.checking': 'Sakatta\'aa jira...',
    'header.track_keyword': 'Jechoota Ijoo Galchi',
    'header.upgrade': 'Fooyyessi',
    'header.manage': 'Bulchi',
    'header.sign_out': 'Bahi',
    'header.select_language': 'Afaan',

    // Navigation Tabs
    'nav.overview': 'Ilaalcha Waliigalaa',
    'nav.keywords': 'Jechoota Ijoo',
    'nav.audits': 'Sakatta\'a Weebsaayitii',
    'nav.competitors': 'Dorgomtoota',
    'nav.recommendations': 'Gorsa Fooyyessaa',
    'nav.content': 'Qophii Qabiyyee',
    'nav.analytics': 'Xiinxala Barbaadaa',
    'nav.reports': 'Gabaasaalee',
    'nav.tools': 'Meeshaalee SEO Bilisaa',
    'nav.operations': 'Hojiiwwan Ofiin Hojjetan',
    'nav.projects': 'Bulchaa Pirojektootaa',

    // Project Selector
    'projects.new': '+ Haaraa',
    'projects.loading': 'Pirojektoonni fe\'amaa jiru...',
    'projects.create_first': '+ Weebsaayitii jalqabaa uumaa',
    'projects.all_projects': 'Pirojektoota Weebsaayitii Hundaa',
    'projects.manage_desc': 'Weebsaayitoota Google Itoophiyaa irratti hordofaman bulchi.',
    'projects.add_new': '+ Pirojektii Haaraa Dabali',
    'projects.no_projects': 'Hamma ammaatti pirojektiin uumame hin jiru.',
    'projects.create_first_btn': 'Pirojektii Jalqabaa Uumi',
    'projects.created': 'Kan Uumame',
    'projects.active': 'Hojirra Jira',

    // KPI Cards & Metrics
    'kpi.total_keywords': 'Jechoota Ijoo Hundaa',
    'kpi.tracking_et': 'google.com.et irratti kan hordofamu',
    'kpi.avg_position': 'Giddu-galeessa Sadarkaa',
    'kpi.et_weighted': 'Madaallii barbaacha Itoophiyaa',
    'kpi.top_3': 'Sadarkaa 3 Ol',
    'kpi.prime_visibility': 'Mul\'achuu olaanaa',
    'kpi.top_10': 'Sadarkaa 10 Ol',
    'kpi.first_page': 'Fuula 1ffaa Google irratti',
    'kpi.in_top_100': 'Sadarkaa 100 Keessa',
    'kpi.indexed': 'Google irratti kan galmaa\'an',
    'kpi.search_demand': 'Fedhii Barbaacha Naannoo',
    'kpi.multilingual_demand': 'Afaan Oromoo, Amaaraa fi Ingiliffaan',

    // Actions & Buttons
    'action.refresh': 'Haaromsi',
    'action.refreshing': 'Haaromaa jira...',
    'action.save': 'Olkaayi',
    'action.cancel': 'Dhiisi',
    'action.delete': 'Haqi',
    'action.edit': 'Gulaali',
    'action.close': 'Cufi',
    'action.export_csv': 'CSV Baasi',
    'action.filter': 'Gingilchi',
    'action.search': 'Barbaadi',
    'action.add': 'Dabali',
    'action.view': 'Ilaali',
    'action.submit': 'Galchi',
    'action.confirm': 'Mirkaneessi',
    'action.apply': 'Hojiirra Oolchi',
    'action.retry': 'Irra Deebi\'i',
    'action.run_now': 'Amma Hojjedhu',

    // Table Headers
    'table.keyword': 'Jecha Barbaadaa',
    'table.position': 'Sadarkaa Ammaa',
    'table.previous': 'Sadarkaa Duraa',
    'table.change': 'Jijjiirama',
    'table.url': 'URL Weebsaayitii',
    'table.engine': 'Mootora Barbaadaa',
    'table.device': 'Meeshaa',
    'table.volume': 'Baay\'ina Barbaadaa',
    'table.cpc': 'Gatii Tilmaamaa (CPC)',
    'table.intent': 'Kaayyoo Barbaadaa',
    'table.language': 'Afaan',
    'table.last_checked': 'Yeroo Dhuma Sakatta\'ame',
    'table.actions': 'Tarkaanfiiwwan',
    'table.status': 'Haala',
    'table.severity': 'Cimina',
    'table.issue': 'Ibsa Rakkoo',
    'table.query': 'Jecha Barbaadaa',
    'table.rank': 'Sadarkaa',
    'table.delta': 'Garaagarummaa',
    'table.search_vol': 'Baay\'ina Barbaadaa',
    'table.target_et': 'Qiyyaafannoo (Itoophiyaa)',
    'table.indexed_title': 'Mata-duree fi URL',
    'table.recorded_at': 'Yeroo Galmaa\'e',

    // Empty States
    'empty.no_keywords': 'Hamma ammaatti jechi ijoo hin galmoofne.',
    'empty.no_keywords_desc': 'Google Itoophiyaa irratti sadarkaa hordofuuf jechoota Afaan Oromoo, Amaaraa ykn Ingiliffaa galchaa.',
    'empty.add_first_keyword': 'Jecha Ijoo Jalqabaa Galchi',
    'empty.no_rankings': 'Ragaan sadarkaa hamma ammaatti hin jiru.',
    'empty.no_rankings_desc': 'Sakatta\'iinsa jalqabaa ykn hamma sirni ofiin ragaa walitti qabutti eegaa.',
    'empty.no_audits': 'Sakatta\'iinsi teeknikaa hin geggeeffamne.',
    'empty.run_audit_btn': 'Sakatta\'a Teeknikaa Hojiirra Oolchi',
    'empty.no_competitors': 'Weebsaayitiin dorgomaa hin galmoofne.',
    'empty.add_competitor_btn': 'Dorgomaa Dabali',

    // Sub-Tabs
    'subtab.all_views': 'Ilaalcha Hundaa',
    'subtab.audit_feed': 'Tarree Qorannoo',
    'subtab.action_plan': 'Karoora Tarkaanfii',
    'subtab.serp_insights': 'Hubannoo SERP',
    'subtab.ai_strategy': 'Uumaa Tarsiimoo AI',
    'subtab.all_content': 'Qabiyyee Hundaa',
    'subtab.content_briefs': 'Qajeelfama Qabiyyee',
    'subtab.content_drafts': 'Wixinee Qophaa\'e',
    'subtab.all_operations': 'Hojiiwwan Hundaa',
    'subtab.specialized_agents': 'Gargaartota Addaa',
    'subtab.continuous_ops': 'Hojii Walitti Fufaa',
    'subtab.event_logs': 'Galmee Taatee',
    'subtab.live_monitoring': 'Hordoffii Kallattii',
    'subtab.auto_remediation': 'Ofiin Sirreessuu',
    'subtab.observability': 'Qorannoo fi To\'annoo',
    'subtab.long_term_strategy': 'Tarsiimoo Yeroo Dheeraa',
    'subtab.feed': 'Tarree Gorsaalee',
    'subtab.actions': 'Hordoffii Tarkaanfii',
    'subtab.insights': 'Hubannoo Qajeelchaa',
    'subtab.generator': 'Uumaa Gorsa AI',
    'subtab.briefs': 'Qajeelfama Qabiyyee',
    'subtab.drafts': 'Wixinee Qophaa\'e',
    'subtab.agents': 'Gargaartota Addaa',
    'subtab.monitoring': 'Hordoffii Ofiin Hojjetu',
    'subtab.remediation': 'Sirreessa Rakkoo',
    'subtab.continuous': 'Hojii Walitti Fufaa',
    'subtab.events': 'Taateewwan Yeroo Ammaa',
    'subtab.strategy': 'Tarsiimoo Yeroo Dheeraa',
    'subtab.health': 'Fayyaa Sirnaa',

    // Dynamic Statuses
    'status.active': 'Hojirra Jira',
    'status.paused': 'Dhaabbateera',
    'status.running': 'Hojjechaa Jira',
    'status.completed': 'Xumurameera',
    'status.failed': 'Hin Milkoofne',
    'status.pending': 'Eeggachaa Jira',
    'status.found': 'Argameera',
    'status.not_found': '100 keessatti hin argamne',
    'status.not_in_top_100': '100 keessatti hin argamne',
    'status.check_failed': 'Kormannaan hin milkoofne',
    'status.not_checked': 'Hin sakatta\'amne',
    'status.success': 'Milkaa\'ina',
    'status.error': 'Kormannaan hin milkoofne',
    'status.warning': 'Akeekkachiisa',
    'status.passed': 'Darbeera',

    // Dynamic Severities
    'severity.critical': 'Baay\'ee Cimaa',
    'severity.high': 'Cimaa',
    'severity.medium': 'Giddu-galeessa',
    'severity.low': 'Gadi-aanaa',
    'severity.info': 'Odeeffannoo',

    // Devices
    'device.desktop': 'Kompiitara',
    'device.mobile': 'Moobaayila',
    'device.tablet': 'Taableetii',

    // Auth
    'auth.sign_in': 'Gara herrega keetti seeni',
    'auth.sign_in_desc': 'Odeeffannoo SEO Google Itoophiyaa argachuuf seenaa',
    'auth.login_subtitle': 'Odeeffannoo SEO Google Itoophiyaa argachuuf seenaa',
    'auth.email': 'Teessoo Imeelii',
    'auth.password': 'Jecha Iccitii',
    'auth.first_name': 'Maqaa',
    'auth.last_name': 'Maqaa Abbaa',
    'auth.create_account': 'Amma Uumi',
    'auth.dont_have_account': 'Herrega hin qabduu?',
    'auth.already_have_account': 'Duraan herrega qabdaa?',
    'auth.start_free': 'Bilisaan Jalqabi',
    'auth.signing_in': 'Mirkaneessaa jira...',
    'auth.no_account': 'Hamma ammaatti herrega hin qabduu?',
    'auth.register_subtitle': 'Google Itoophiyaa irratti sadarkaa hordofuu fi SEO fooyyessuu jalqabaa',
    'auth.creating_account': 'Herrega uumaa jira...',
    'auth.create_account_btn': 'Herrega Uumaa Bilisaan Jalqabaa',
    'auth.already_account': 'Duraan herrega qabdaa?',
    'auth.sign_in_link': 'Seeni',
  },
};

const LanguageContext = createContext<LanguageContextType | undefined>(undefined);

export const LanguageProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [language, setLanguageState] = useState<SupportedLanguage>(() => {
    try {
      const saved = localStorage.getItem(STORAGE_KEY);
      if (saved === 'am' || saved === 'om' || saved === 'en') {
        return saved;
      }
    } catch {
      // Fallback
    }
    return 'en';
  });

  const setLanguage = (lang: SupportedLanguage) => {
    setLanguageState(lang);
    try {
      localStorage.setItem(STORAGE_KEY, lang);
    } catch (e) {
      console.warn('Failed to save language to localStorage', e);
    }
  };

  useEffect(() => {
    document.documentElement.lang = language;
  }, [language]);

  const t = (key: string, defaultText?: string): string => {
    const isDev = Boolean(import.meta.env?.DEV);
    const langDict = translations[language];
    if (langDict && langDict[key]) {
      return langDict[key];
    }
    // Fallback to English
    if (translations.en[key]) {
      if (isDev && language !== 'en') {
        console.warn(`[i18n] Fallback to English for key: "${key}" in language "${language}"`);
      }
      return translations.en[key];
    }
    if (isDev) {
      console.warn(`[i18n] Missing translation key: "${key}" across all locales!`);
    }
    return defaultText ?? key;
  };

  const formatStatus = (status?: string | null): string => {
    if (!status) return '—';
    const key = `status.${status.toLowerCase().trim()}`;
    return t(key, status);
  };

  const formatSeverity = (severity?: string | null): string => {
    if (!severity) return '—';
    const key = `severity.${severity.toLowerCase().trim()}`;
    return t(key, severity);
  };

  const formatDevice = (device?: string | null): string => {
    if (!device) return '—';
    const key = `device.${device.toLowerCase().trim()}`;
    return t(key, device);
  };

  const formatDate = (date: string | number | Date | null | undefined): string => {
    if (!date) return '—';
    try {
      const d = new Date(date);
      if (isNaN(d.getTime())) return String(date);
      const localeMap: Record<SupportedLanguage, string> = {
        en: 'en-US',
        am: 'am-ET',
        om: 'om-ET',
      };
      const locale = localeMap[language] || 'en-US';
      return d.toLocaleDateString(locale, {
        year: 'numeric',
        month: 'short',
        day: 'numeric',
      });
    } catch {
      return String(date);
    }
  };

  const formatNumber = (num: number | null | undefined): string => {
    if (num === null || num === undefined) return '—';
    try {
      const localeMap: Record<SupportedLanguage, string> = {
        en: 'en-US',
        am: 'am-ET',
        om: 'om-ET',
      };
      const locale = localeMap[language] || 'en-US';
      return num.toLocaleString(locale);
    } catch {
      return String(num);
    }
  };

  return (
    <LanguageContext.Provider
      value={{
        language,
        setLanguage,
        t,
        formatStatus,
        formatSeverity,
        formatDevice,
        formatDate,
        formatNumber,
      }}
    >
      {children}
    </LanguageContext.Provider>
  );
};

export const useLanguage = (): LanguageContextType => {
  const context = useContext(LanguageContext);
  if (!context) {
    throw new Error('useLanguage must be used within a LanguageProvider');
  }
  return context;
};
