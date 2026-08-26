from django.db import models
from django.utils import timezone
from apps.projects.models import Project


class SearchEngine(models.TextChoices):
    GOOGLE = 'google', 'Google'


class Country(models.TextChoices):
    ET = 'ET', 'Ethiopia'


class Language(models.TextChoices):
    EN = 'en', 'English'
    AM = 'am', 'Amharic'


class Device(models.TextChoices):
    DESKTOP = 'desktop', 'Desktop'
    MOBILE = 'mobile', 'Mobile'


class Keyword(models.Model):
    """
    Keyword model representing a search term tracked for a specific project.
    Relationship: Project 1 ─────── * Keyword
    """
    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        related_name='keywords',
        help_text='The project/website this keyword belongs to.'
    )
    keyword = models.CharField(
        max_length=255,
        help_text='The search query to track (e.g. "seo agency ethiopia").'
    )
    search_engine = models.CharField(
        max_length=50,
        choices=SearchEngine.choices,
        default=SearchEngine.GOOGLE,
        help_text='Target search engine.'
    )
    country = models.CharField(
        max_length=10,
        choices=Country.choices,
        default=Country.ET,
        help_text='Target country code (e.g. "ET" for Ethiopia).'
    )
    language = models.CharField(
        max_length=10,
        choices=Language.choices,
        default=Language.EN,
        help_text='Target search language code (e.g. "en", "am").'
    )
    device = models.CharField(
        max_length=20,
        choices=Device.choices,
        default=Device.DESKTOP,
        help_text='Target device type (desktop or mobile).'
    )
    is_active = models.BooleanField(
        default=True,
        help_text='Whether rank tracking is active for this keyword.'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'seo_keywords'
        verbose_name = 'keyword'
        verbose_name_plural = 'keywords'
        ordering = ['-created_at']
        constraints = [
            models.UniqueConstraint(
                fields=['project', 'keyword', 'search_engine', 'country', 'language', 'device'],
                name='unique_keyword_configuration_per_project'
            )
        ]

    def __str__(self):
        return f"{self.keyword} ({self.project.name} - {self.country}/{self.language})"


class KeywordRanking(models.Model):
    """
    KeywordRanking model representing a single ranking observation in search results.
    Relationship: Keyword 1 ─────── * KeywordRanking
    Ownership follows: ranking.keyword -> keyword.project -> project.owner
    """
    keyword = models.ForeignKey(
        Keyword,
        on_delete=models.CASCADE,
        related_name='rankings',
        help_text='The tracked keyword this ranking observation belongs to.'
    )
    position = models.PositiveIntegerField(
        help_text='Observed ranking position in search results (e.g. 1 for rank #1).'
    )
    ranking_url = models.URLField(
        max_length=500,
        blank=True,
        null=True,
        help_text='The exact landing page URL found ranking on the search engine.'
    )
    search_engine = models.CharField(
        max_length=50,
        choices=SearchEngine.choices,
        default=SearchEngine.GOOGLE,
        help_text='Target search engine.'
    )
    country = models.CharField(
        max_length=10,
        choices=Country.choices,
        default=Country.ET,
        help_text='Target country code.'
    )
    language = models.CharField(
        max_length=10,
        choices=Language.choices,
        default=Language.EN,
        help_text='Target search language code.'
    )
    device = models.CharField(
        max_length=20,
        choices=Device.choices,
        default=Device.DESKTOP,
        help_text='Target device type.'
    )
    recorded_at = models.DateTimeField(
        help_text='Timestamp when the ranking observation occurred.'
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'seo_keyword_rankings'
        verbose_name = 'keyword ranking'
        verbose_name_plural = 'keyword rankings'
        ordering = ['-recorded_at']
        constraints = [
            models.UniqueConstraint(
                fields=['keyword', 'search_engine', 'country', 'language', 'device', 'recorded_at'],
                name='unique_ranking_observation_per_time'
            )
        ]

    def __str__(self):
        return f"{self.keyword.keyword} - Pos #{self.position} ({self.recorded_at})"


class AuditStatus(models.TextChoices):
    PENDING = 'pending', 'Pending'
    RUNNING = 'running', 'Running'
    COMPLETED = 'completed', 'Completed'
    FAILED = 'failed', 'Failed'


class IssueSeverity(models.TextChoices):
    CRITICAL = 'critical', 'Critical'
    WARNING = 'warning', 'Warning'
    NOTICE = 'notice', 'Notice'


class SiteAudit(models.Model):
    """
    SiteAudit model representing an SEO audit run for a specific project.
    Relationship: Project 1 ─────── * SiteAudit
    Ownership follows: audit.project -> project.owner
    """
    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        related_name='audits',
        help_text='The project/website this site audit belongs to.'
    )
    status = models.CharField(
        max_length=20,
        choices=AuditStatus.choices,
        default=AuditStatus.PENDING,
        db_index=True,
        help_text='Current status of the audit job.'
    )
    score = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text='Overall SEO health score from 0 to 100.'
    )
    started_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text='Timestamp when the audit execution began.'
    )
    completed_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text='Timestamp when the audit execution concluded.'
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        help_text='Timestamp when the audit was created.'
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        help_text='Timestamp when the audit was last updated.'
    )
    error_message = models.TextField(
        blank=True,
        null=True,
        help_text='Error details if the audit failed.'
    )

    class Meta:
        db_table = 'seo_site_audits'
        verbose_name = 'site audit'
        verbose_name_plural = 'site audits'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['project', '-created_at'], name='seo_site_au_project_bd7594_idx'),
            models.Index(fields=['status'], name='seo_site_au_status_59ac12_idx'),
        ]

    def __str__(self):
        return f"Audit #{self.id} - {self.project.name} ({self.status})"


class AuditIssue(models.Model):
    """
    AuditIssue model representing a specific issue identified during a site audit.
    Relationship: SiteAudit 1 ─────── * AuditIssue
    Ownership follows: issue.audit -> audit.project -> project.owner
    """
    audit = models.ForeignKey(
        SiteAudit,
        on_delete=models.CASCADE,
        related_name='issues',
        help_text='The site audit this issue belongs to.'
    )
    issue_type = models.CharField(
        max_length=100,
        db_index=True,
        help_text='Category identifier of the issue (e.g. missing_title, slow_load, 404_link).'
    )
    severity = models.CharField(
        max_length=20,
        choices=IssueSeverity.choices,
        default=IssueSeverity.WARNING,
        db_index=True,
        help_text='Severity level of the issue.'
    )
    title = models.CharField(
        max_length=255,
        help_text='Short summary title of the issue.'
    )
    description = models.TextField(
        help_text='Detailed explanation of what was found.'
    )
    page_url = models.URLField(
        max_length=500,
        blank=True,
        null=True,
        help_text='URL of the affected page if applicable.'
    )
    recommendation = models.TextField(
        blank=True,
        null=True,
        help_text='Recommended action steps to resolve the issue.'
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        help_text='Timestamp when the issue record was created.'
    )

    class Meta:
        db_table = 'seo_audit_issues'
        verbose_name = 'audit issue'
        verbose_name_plural = 'audit issues'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['audit', '-created_at'], name='seo_audit_i_audit_i_1512b0_idx'),
            models.Index(fields=['severity'], name='seo_audit_i_severit_7437cc_idx'),
        ]

    def __str__(self):
        return f"[{self.severity.upper()}] {self.title} (Audit #{self.audit_id})"


class SearchConsoleSyncStatus(models.TextChoices):
    IDLE = 'idle', 'Idle'
    SYNCING = 'syncing', 'Syncing'
    SUCCESS = 'success', 'Success'
    FAILED = 'failed', 'Failed'


class SearchConsolePermission(models.TextChoices):
    SITE_OWNER = 'siteOwner', 'Site Owner'
    SITE_FULL_USER = 'siteFullUser', 'Full User'
    SITE_RESTRICTED_USER = 'siteRestrictedUser', 'Restricted User'
    SITE_UNVERIFIED_USER = 'siteUnverifiedUser', 'Unverified User'


class SearchConsoleConnection(models.Model):
    """
    SearchConsoleConnection model representing a link between a DoxaRank Project
    and a Google Search Console verified property.
    Relationship: Project 1 ─────── 1 SearchConsoleConnection (OneToOne)
    Ownership follows: connection.project -> project.owner
    """
    project = models.OneToOneField(
        Project,
        on_delete=models.CASCADE,
        related_name='search_console_connection',
        help_text='The project linked to this Search Console property.'
    )
    property_url = models.CharField(
        max_length=500,
        help_text='The Search Console site URL or domain property (e.g. "sc-domain:example.com" or "https://example.com/").'
    )
    permission_level = models.CharField(
        max_length=50,
        choices=SearchConsolePermission.choices,
        default=SearchConsolePermission.SITE_OWNER,
        help_text='Permission level of the authenticated user on this Search Console property.'
    )
    is_connected = models.BooleanField(
        default=True,
        help_text='Whether this project is actively connected to Google Search Console.'
    )
    connected_at = models.DateTimeField(
        auto_now_add=True,
        help_text='Timestamp when the Search Console connection was established.'
    )
    last_synced_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text='Timestamp of the most recent data sync from Search Console.'
    )
    sync_status = models.CharField(
        max_length=20,
        choices=SearchConsoleSyncStatus.choices,
        default=SearchConsoleSyncStatus.IDLE,
        help_text='Current data synchronization status.'
    )
    error_message = models.TextField(
        null=True,
        blank=True,
        help_text='Error details if the connection or last sync failed.'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'seo_search_console_connections'
        verbose_name = 'Search Console connection'
        verbose_name_plural = 'Search Console connections'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['project', 'is_connected'], name='seo_gsc_proj_conn_idx'),
            models.Index(fields=['sync_status'], name='seo_gsc_sync_status_idx'),
        ]

    def __str__(self):
        return f"GSC: {self.property_url} ({self.project.name})"


class SearchAnalyticsData(models.Model):
    """
    SearchAnalyticsData model representing historical Google Search Console performance data
    (queries, pages, clicks, impressions, CTR, position, country, device by date).
    Relationship: SearchConsoleConnection 1 ─────── * SearchAnalyticsData
    Ownership follows: analytics.connection -> connection.project -> project.owner
    """
    connection = models.ForeignKey(
        SearchConsoleConnection,
        on_delete=models.CASCADE,
        related_name='search_analytics',
        help_text='The Search Console connection this analytics record belongs to.'
    )
    date = models.DateField(
        db_index=True,
        help_text='Observation date for this analytics row.'
    )
    query = models.CharField(
        max_length=500,
        blank=True,
        default='',
        db_index=True,
        help_text='Search query / keyword string from Google Search Console.'
    )
    page = models.CharField(
        max_length=500,
        blank=True,
        default='',
        db_index=True,
        help_text='Landing page URL from Google Search Console.'
    )
    country = models.CharField(
        max_length=10,
        blank=True,
        default='',
        help_text='Country code (e.g. "eth", "usa", "ET").'
    )
    device = models.CharField(
        max_length=20,
        blank=True,
        default='',
        help_text='Device category (e.g. "desktop", "mobile", "tablet").'
    )
    search_appearance = models.CharField(
        max_length=100,
        blank=True,
        default='',
        help_text='Search appearance dimension (e.g. "AMP_ARTICLE", "RICHDATA").'
    )
    clicks = models.PositiveIntegerField(
        default=0,
        help_text='Total number of clicks from organic search results.'
    )
    impressions = models.PositiveIntegerField(
        default=0,
        help_text='Total number of impressions in organic search results.'
    )
    ctr = models.DecimalField(
        max_digits=7,
        decimal_places=4,
        default=0.0000,
        help_text='Click-through rate (e.g. 0.0543 for 5.43% or raw decimal).'
    )
    position = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        default=0.00,
        help_text='Average ranking position in organic search results.'
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        help_text='Timestamp when this record was created.'
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        help_text='Timestamp when this record was last updated.'
    )

    class Meta:
        db_table = 'seo_search_analytics_data'
        verbose_name = 'Search Analytics record'
        verbose_name_plural = 'Search Analytics data'
        ordering = ['-date', '-clicks']
        constraints = [
            models.UniqueConstraint(
                fields=['connection', 'date', 'query', 'page', 'country', 'device', 'search_appearance'],
                name='unique_search_analytics_observation'
            )
        ]
        indexes = [
            models.Index(fields=['connection', '-date'], name='seo_analytics_conn_date_idx'),
            models.Index(fields=['connection', 'date'], name='seo_analytics_c_d_asc_idx'),
            models.Index(fields=['date'], name='seo_analytics_date_idx'),
            models.Index(fields=['query'], name='seo_analytics_query_idx'),
            models.Index(fields=['page'], name='seo_analytics_page_idx'),
        ]

    def __str__(self):
        query_display = f"'{self.query}'" if self.query else "[all queries]"
        return f"{query_display} on {self.date} ({self.clicks} clicks, pos {self.position})"


class InsightSeverity(models.TextChoices):
    CRITICAL = 'critical', 'Critical'
    WARNING = 'warning', 'Warning'
    OPPORTUNITY = 'opportunity', 'Opportunity'
    INFO = 'info', 'Info'


class InsightStatus(models.TextChoices):
    OPEN = 'open', 'Open'
    DISMISSED = 'dismissed', 'Dismissed'
    RESOLVED = 'resolved', 'Resolved'


class InsightSource(models.TextChoices):
    RANKING = 'ranking', 'Ranking'
    SEARCH_CONSOLE = 'search_console', 'Search Console'
    SITE_AUDIT = 'site_audit', 'Site Audit'
    COMBINED = 'combined', 'Combined'


class InsightType(models.TextChoices):
    RANKING_DROP = 'ranking_drop', 'Ranking Drop'
    RANKING_IMPROVEMENT = 'ranking_improvement', 'Ranking Improvement'
    PAGE_TWO_KEYWORD = 'page_two_keyword', 'Page Two Opportunity'
    HIGH_IMPRESSIONS_LOW_CTR = 'high_impressions_low_ctr', 'High Impressions Low CTR'
    DECLINING_CLICKS = 'declining_clicks', 'Declining Clicks'
    DECLINING_IMPRESSIONS = 'declining_impressions', 'Declining Impressions'
    LOW_CTR = 'low_ctr', 'Low CTR'
    HIGH_POSITION_OPPORTUNITY = 'high_position_opportunity', 'High Position Opportunity'
    TECHNICAL_SEO_ISSUE = 'technical_seo_issue', 'Technical SEO Issue'
    KEYWORD_CANNIBALIZATION = 'keyword_cannibalization', 'Keyword Cannibalization'
    CONTENT_OPPORTUNITY = 'content_opportunity', 'Content Opportunity'


class SEOInsight(models.Model):
    """
    SEOInsight model representing actionable, structured insights generated
    from raw SEO data (rankings, Google Search Console, site audits).
    Relationship: Project 1 ─────── * SEOInsight
    Ownership follows: insight.project -> project.owner
    """
    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        related_name='insights',
        help_text='The project this SEO insight belongs to.'
    )
    fingerprint = models.CharField(
        max_length=255,
        db_index=True,
        help_text='Deterministic unique fingerprint for deduplication across analysis runs.'
    )
    insight_type = models.CharField(
        max_length=50,
        choices=InsightType.choices,
        db_index=True,
        help_text='Category / rule type of the insight.'
    )
    severity = models.CharField(
        max_length=20,
        choices=InsightSeverity.choices,
        default=InsightSeverity.INFO,
        db_index=True,
        help_text='Severity level of the insight.'
    )
    title = models.CharField(
        max_length=255,
        help_text='Concise summary of the insight.'
    )
    description = models.TextField(
        help_text='Detailed explanation of observed SEO behavior or metric change.'
    )
    recommendation = models.TextField(
        blank=True,
        default='',
        help_text='Actionable recommendation to address or capitalize on this insight.'
    )
    status = models.CharField(
        max_length=20,
        choices=InsightStatus.choices,
        default=InsightStatus.OPEN,
        db_index=True,
        help_text='Workflow status of this insight.'
    )
    source = models.CharField(
        max_length=30,
        choices=InsightSource.choices,
        default=InsightSource.RANKING,
        db_index=True,
        help_text='Data source where this insight was derived from.'
    )
    related_keyword = models.ForeignKey(
        Keyword,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='insights',
        help_text='Specific keyword tracked in DoxaRank associated with this insight.'
    )
    related_url = models.CharField(
        max_length=500,
        blank=True,
        default='',
        help_text='Landing page URL associated with this insight.'
    )
    metadata = models.JSONField(
        default=dict,
        blank=True,
        help_text='Arbitrary structured metadata (metrics, comparisons, delta values).'
    )
    detected_at = models.DateTimeField(
        default=timezone.now,
        db_index=True,
        help_text='Timestamp when the insight condition was first or most recently detected.'
    )
    resolved_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text='Timestamp when this insight was marked resolved.'
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        help_text='Timestamp when this insight record was created.'
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        help_text='Timestamp when this insight record was last updated.'
    )

    class Meta:
        db_table = 'seo_insights'
        verbose_name = 'SEO insight'
        verbose_name_plural = 'SEO insights'
        ordering = ['-detected_at']
        constraints = [
            models.UniqueConstraint(
                fields=['project', 'fingerprint'],
                name='unique_project_insight_fingerprint'
            )
        ]
        indexes = [
            models.Index(fields=['project', 'status'], name='seo_ins_proj_stat_idx'),
            models.Index(fields=['project', 'severity'], name='seo_ins_proj_sev_idx'),
            models.Index(fields=['project', 'insight_type'], name='seo_ins_proj_type_idx'),
            models.Index(fields=['project', '-detected_at'], name='seo_ins_proj_date_idx'),
        ]

    def __str__(self):
        return f"[{self.severity.upper()}] {self.title} ({self.project.name})"


class RecommendationType(models.TextChoices):
    META_TITLE = 'meta_title', 'Meta Title'
    META_DESCRIPTION = 'meta_description', 'Meta Description'
    CONTENT_UPDATE = 'content_update', 'Content Update'
    KEYWORD_OPTIMIZATION = 'keyword_optimization', 'Keyword Optimization'
    INTERNAL_LINKING = 'internal_linking', 'Internal Linking'
    TECHNICAL_SEO = 'technical_seo', 'Technical SEO'
    RANKING_RECOVERY = 'ranking_recovery', 'Ranking Recovery'
    CTR_OPTIMIZATION = 'ctr_optimization', 'CTR Optimization'
    PAGE_TWO_OPPORTUNITY = 'page_two_opportunity', 'Page Two Opportunity'
    GENERAL_SEO = 'general_seo', 'General SEO'


class RecommendationPriority(models.TextChoices):
    CRITICAL = 'critical', 'Critical'
    HIGH = 'high', 'High'
    MEDIUM = 'medium', 'Medium'
    LOW = 'low', 'Low'


class RecommendationStatus(models.TextChoices):
    PENDING_REVIEW = 'pending_review', 'Pending Review'
    REVIEWED = 'reviewed', 'Reviewed'
    APPLIED = 'applied', 'Applied'
    DISMISSED = 'dismissed', 'Dismissed'


class SEORecommendation(models.Model):
    """
    SEORecommendation model representing an AI-generated, explainable,
    and structured action proposal based on an originating SEOInsight.
    Relationship: Project 1 ─────── * SEORecommendation
                  SEOInsight 1 ─────── * SEORecommendation
    Ownership follows: rec.project -> project.owner
    """
    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        related_name='recommendations',
        help_text='The project this AI recommendation belongs to.'
    )
    insight = models.ForeignKey(
        SEOInsight,
        on_delete=models.CASCADE,
        related_name='recommendations',
        help_text='The originating SEO insight this recommendation addresses.'
    )
    recommendation_type = models.CharField(
        max_length=50,
        choices=RecommendationType.choices,
        default=RecommendationType.GENERAL_SEO,
        db_index=True,
        help_text='Type of SEO optimization recommended.'
    )
    title = models.CharField(
        max_length=255,
        help_text='Concise title summarizing the recommendation.'
    )
    summary = models.TextField(
        help_text='High-level summary of the issue and rationale.'
    )
    explanation = models.TextField(
        help_text='In-depth explanation of the observed SEO evidence and causal factors.'
    )
    priority = models.CharField(
        max_length=20,
        choices=RecommendationPriority.choices,
        default=RecommendationPriority.HIGH,
        db_index=True,
        help_text='Execution priority.'
    )
    recommended_action = models.TextField(
        help_text='Concrete step-by-step instructions for the user/developer.'
    )
    expected_impact = models.TextField(
        help_text='Estimated realistic SEO impact without false certainty.'
    )
    affected_url = models.CharField(
        max_length=500,
        blank=True,
        default='',
        help_text='Target URL for applying the recommendation.'
    )
    affected_keyword = models.CharField(
        max_length=255,
        blank=True,
        default='',
        help_text='Target keyword query associated with this recommendation.'
    )
    generated_content = models.JSONField(
        default=dict,
        blank=True,
        help_text='Structured copy proposals (e.g. proposed title, meta description, copy outlines).'
    )
    status = models.CharField(
        max_length=30,
        choices=RecommendationStatus.choices,
        default=RecommendationStatus.PENDING_REVIEW,
        db_index=True,
        help_text='Workflow approval status of this recommendation.'
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        help_text='Timestamp when the recommendation was generated.'
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        help_text='Timestamp when the recommendation was last modified.'
    )

    class Meta:
        db_table = 'seo_recommendations'
        verbose_name = 'SEO recommendation'
        verbose_name_plural = 'SEO recommendations'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['project', 'status'], name='seo_rec_proj_stat_idx'),
            models.Index(fields=['project', 'priority'], name='seo_rec_proj_prio_idx'),
            models.Index(fields=['insight', 'status'], name='seo_rec_ins_stat_idx'),
            models.Index(fields=['project', '-created_at'], name='seo_rec_proj_date_idx'),
        ]

    def __str__(self):
        return f"[{self.priority.upper()}] {self.title} ({self.project.name})"


class BriefContentType(models.TextChoices):
    BLOG_POST = 'blog_post', 'Blog / Article'
    LANDING_PAGE = 'landing_page', 'Landing Page'
    PAGE_OPTIMIZATION = 'page_optimization', 'Existing-Page Optimization'
    TECHNICAL_IMPLEMENTATION = 'technical_implementation', 'Technical SEO Implementation'


class BriefSearchIntent(models.TextChoices):
    INFORMATIONAL = 'informational', 'Informational'
    TRANSACTIONAL = 'transactional', 'Transactional'
    COMMERCIAL = 'commercial', 'Commercial Investigation'
    NAVIGATIONAL = 'navigational', 'Navigational'


class BriefStatus(models.TextChoices):
    DRAFT = 'draft', 'Draft'
    IN_PROGRESS = 'in_progress', 'In Progress'
    COMPLETED = 'completed', 'Completed'
    ARCHIVED = 'archived', 'Archived'


class SEOContentBrief(models.Model):
    """
    SEOContentBrief model representing an actionable, highly-structured SEO content brief
    generated from an AI recommendation and grounded in real SEO/GSC metrics.
    Relationship: Project 1 ─────── * SEOContentBrief
                  SEORecommendation 1 ─────── * SEOContentBrief
    Ownership follows: brief.project -> project.owner
    """
    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        related_name='content_briefs',
        help_text='The project this content brief belongs to.'
    )
    recommendation = models.ForeignKey(
        SEORecommendation,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='content_briefs',
        help_text='The originating SEO recommendation this brief was synthesized from.'
    )
    title = models.CharField(
        max_length=255,
        help_text='Working title for the content brief.'
    )
    target_keyword = models.CharField(
        max_length=255,
        blank=True,
        default='',
        help_text='Primary target search keyword.'
    )
    secondary_keywords = models.JSONField(
        default=list,
        blank=True,
        help_text='List of supporting / secondary keywords.'
    )
    search_intent = models.CharField(
        max_length=50,
        choices=BriefSearchIntent.choices,
        default=BriefSearchIntent.INFORMATIONAL,
        db_index=True,
        help_text='Dominant search intent category.'
    )
    target_url = models.CharField(
        max_length=500,
        blank=True,
        default='',
        help_text='Target URL / existing URL to optimize or create.'
    )
    content_type = models.CharField(
        max_length=50,
        choices=BriefContentType.choices,
        default=BriefContentType.BLOG_POST,
        db_index=True,
        help_text='Type of content asset (blog, landing page, page optimization, technical).'
    )
    recommended_title = models.CharField(
        max_length=255,
        blank=True,
        default='',
        help_text='Optimized meta / H1 title proposition.'
    )
    meta_description = models.TextField(
        blank=True,
        default='',
        help_text='Recommended meta description (140-160 characters).'
    )
    suggested_slug = models.CharField(
        max_length=255,
        blank=True,
        default='',
        help_text='Recommended URL slug hierarchy.'
    )
    content_angle = models.TextField(
        blank=True,
        default='',
        help_text='Unique value proposition, editorial angle, or competitive differentiation.'
    )
    audience = models.CharField(
        max_length=255,
        blank=True,
        default='',
        help_text='Target reader or buyer persona.'
    )
    outline = models.JSONField(
        default=list,
        blank=True,
        help_text='Structured outline items with heading levels, section titles, and talking points.'
    )
    key_points = models.JSONField(
        default=list,
        blank=True,
        help_text='Essential arguments, facts, or concepts that must be included.'
    )
    internal_link_suggestions = models.JSONField(
        default=list,
        blank=True,
        help_text='Recommended internal link targets and anchor texts.'
    )
    external_link_suggestions = models.JSONField(
        default=list,
        blank=True,
        help_text='Authoritative external reference suggestions.'
    )
    faq_questions = models.JSONField(
        default=list,
        blank=True,
        help_text='Frequently asked questions to target SERP features (PPA/FAQ schema).'
    )
    entities_topics = models.JSONField(
        default=list,
        blank=True,
        help_text='Topical entities and semantic concepts to establish topical authority.'
    )
    content_length_target = models.PositiveIntegerField(
        null=True,
        blank=True,
        default=1500,
        help_text='Recommended word count target.'
    )
    generated_content = models.JSONField(
        default=dict,
        blank=True,
        help_text='Full structured brief JSON as returned by the AI provider.'
    )
    status = models.CharField(
        max_length=30,
        choices=BriefStatus.choices,
        default=BriefStatus.DRAFT,
        db_index=True,
        help_text='Workflow status of this brief.'
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        help_text='Timestamp when the brief was created.'
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        help_text='Timestamp when the brief was last updated.'
    )

    class Meta:
        db_table = 'seo_content_briefs'
        verbose_name = 'SEO content brief'
        verbose_name_plural = 'SEO content briefs'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['project', 'status'], name='seo_brief_proj_stat_idx'),
            models.Index(fields=['project', 'content_type'], name='seo_brief_proj_type_idx'),
            models.Index(fields=['recommendation', 'status'], name='seo_brief_rec_stat_idx'),
            models.Index(fields=['project', '-created_at'], name='seo_brief_proj_date_idx'),
        ]

    def __str__(self):
        return f"[{self.get_content_type_display()}] {self.title} ({self.project.name})"






