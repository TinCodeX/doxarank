import React, { createContext, useContext, useState, useEffect } from 'react';

export type SupportedLanguage = 'en' | 'am' | 'om';

export interface LanguageContextType {
  language: SupportedLanguage;
  setLanguage: (lang: SupportedLanguage) => void;
  t: (key: string, defaultText?: string) => string;
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

    // Auth
    'auth.sign_in': 'Sign in to your account',
    'auth.sign_in_desc': 'Sign in to access your Google Ethiopia SEO intelligence',
    'auth.email': 'Email Address',
    'auth.password': 'Password',
    'auth.first_name': 'First Name',
    'auth.last_name': 'Last Name',
    'auth.create_account': 'Create your DoxaRank account',
    'auth.dont_have_account': "Don't have an account?",
    'auth.already_have_account': 'Already have an account?',
    'auth.start_free': 'Start Free',
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

    // Auth
    'auth.sign_in': 'ወደ መለያዎ ይግቡ',
    'auth.sign_in_desc': 'የኢትዮጵያ SEO መረጃዎን ለማግኘት ይግቡ',
    'auth.email': 'የኢሜይል አድራሻ',
    'auth.password': 'የይለፍ ቃል',
    'auth.first_name': 'ስም',
    'auth.last_name': 'የአባት ስም',
    'auth.create_account': 'የዶክሳራንክ መለያ ይፍጠሩ',
    'auth.dont_have_account': 'መለያ የለዎትም?',
    'auth.already_have_account': 'አስቀድመው መለያ አለዎት?',
    'auth.start_free': 'በነጻ ይጀምሩ',
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

    // Auth
    'auth.sign_in': 'Gara herrega keetti seeni',
    'auth.sign_in_desc': 'Odeeffannoo SEO Google Itoophiyaa argachuuf seenaa',
    'auth.email': 'Teessoo Imeelii',
    'auth.password': 'Jecha Iccitii',
    'auth.first_name': 'Maqaa',
    'auth.last_name': 'Maqaa Abbaa',
    'auth.create_account': 'Herrega DoxaRank Uumi',
    'auth.dont_have_account': 'Herrega hin qabduu?',
    'auth.already_have_account': 'Duraan herrega qabdaa?',
    'auth.start_free': 'Bilisaan Jalqabi',
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
    const langDict = translations[language];
    if (langDict && langDict[key]) {
      return langDict[key];
    }
    // Fallback to English
    if (translations.en[key]) {
      return translations.en[key];
    }
    return defaultText ?? key;
  };

  return (
    <LanguageContext.Provider value={{ language, setLanguage, t }}>
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
