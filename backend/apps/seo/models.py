from typing import Optional, List, Dict, Any
from django.db import models
from django.conf import settings
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

    @property
    def normalized_keyword(self) -> str:
        """Return canonicalized keyword form for matching (with Amharic homophone collapsing)."""
        if self.language == Language.AM:
            from apps.seo.services.amharic_normalizer import normalize_amharic_query
            return normalize_amharic_query(self.keyword)
        return self.keyword.strip().lower()



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
    # OAuth2 Credentials & Token Metadata
    encrypted_refresh_token = models.TextField(
        null=True,
        blank=True,
        help_text='AES-encrypted OAuth2 refresh token.'
    )
    token_expires_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text='Expiration timestamp of the active access token.'
    )
    google_account_email = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        help_text='Google user account email used for OAuth authorization.'
    )
    scopes = models.JSONField(
        default=list,
        blank=True,
        help_text='OAuth2 scopes granted by the user.'
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

    def set_refresh_token(self, raw_token: Optional[str]) -> None:
        """Encrypt and store OAuth2 refresh token."""
        from apps.seo.services.encryption import encrypt_token
        self.encrypted_refresh_token = encrypt_token(raw_token)

    def get_refresh_token(self) -> Optional[str]:
        """Decrypt and return plaintext OAuth2 refresh token."""
        from apps.seo.services.encryption import decrypt_token
        return decrypt_token(self.encrypted_refresh_token)

    @property
    def has_oauth_token(self) -> bool:
        """Check if connection has an encrypted refresh token present."""
        return bool(self.encrypted_refresh_token and self.encrypted_refresh_token.strip())

    def has_valid_credentials(self) -> bool:
        """Check if connection is active with verified property and stored refresh token."""
        return bool(self.is_connected and self.property_url and self.has_oauth_token)



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


class DraftStatus(models.TextChoices):
    DRAFT = 'draft', 'Draft'
    GENERATING = 'generating', 'Generating'
    GENERATED = 'generated', 'Generated'
    REVIEWED = 'reviewed', 'Reviewed'
    APPROVED = 'approved', 'Approved'
    PUBLISHED = 'published', 'Published'
    ARCHIVED = 'archived', 'Archived'


class SEOContentDraft(models.Model):
    """
    SEOContentDraft model representing a fully articulated, publish-ready SEO content draft
    synthesized from an SEOContentBrief and grounded in real ranking, GSC, and audit metrics.
    Relationship: Project 1 ─────── * SEOContentDraft
                  SEOContentBrief 1 ─────── * SEOContentDraft
                  SEORecommendation 1 ─────── * SEOContentDraft (optional)
                  SEOInsight 1 ─────── * SEOContentDraft (optional)
    Ownership follows: draft.project -> project.owner
    """
    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        related_name='content_drafts',
        help_text='The project this content draft belongs to.'
    )
    brief = models.ForeignKey(
        SEOContentBrief,
        on_delete=models.CASCADE,
        related_name='content_drafts',
        help_text='The source SEO content brief used to generate this draft.'
    )
    recommendation = models.ForeignKey(
        SEORecommendation,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='content_drafts',
        help_text='Optional originating SEO recommendation.'
    )
    insight = models.ForeignKey(
        SEOInsight,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='content_drafts',
        help_text='Optional originating SEO insight.'
    )
    title = models.CharField(
        max_length=255,
        help_text='Working title for the generated content draft.'
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
        help_text='List of supporting / secondary keywords incorporated.'
    )
    search_intent = models.CharField(
        max_length=50,
        choices=BriefSearchIntent.choices,
        default=BriefSearchIntent.INFORMATIONAL,
        db_index=True,
        help_text='Search intent category targeted by the draft.'
    )
    target_url = models.CharField(
        max_length=500,
        blank=True,
        default='',
        help_text='Target canonical URL for the draft.'
    )
    content_type = models.CharField(
        max_length=50,
        choices=BriefContentType.choices,
        default=BriefContentType.BLOG_POST,
        db_index=True,
        help_text='Content archetype (blog post, landing page, page optimization, technical implementation).'
    )
    introduction = models.TextField(
        blank=True,
        default='',
        help_text='Engaging opening paragraph answering user search intent.'
    )
    content_body = models.TextField(
        blank=True,
        default='',
        help_text='Complete articulated Markdown content body of the draft.'
    )
    outline_structure = models.JSONField(
        default=list,
        blank=True,
        help_text='Structured outline sections with headings, levels, paragraphs, and key points.'
    )
    word_count = models.PositiveIntegerField(
        default=0,
        help_text='Exact word count of the generated draft.'
    )
    keyword_usage = models.JSONField(
        default=dict,
        blank=True,
        help_text='Deterministic keyword density and occurrences tracking map.'
    )
    internal_links = models.JSONField(
        default=list,
        blank=True,
        help_text='Internal links with anchor texts, URLs, and target section context.'
    )
    external_links = models.JSONField(
        default=list,
        blank=True,
        help_text='Authoritative external reference citations.'
    )
    faq_section = models.JSONField(
        default=list,
        blank=True,
        help_text='List of FAQ items (question and answer) designed for FAQ schema.'
    )
    meta_title = models.CharField(
        max_length=255,
        blank=True,
        default='',
        help_text='Recommended title tag for search engines.'
    )
    meta_description = models.TextField(
        blank=True,
        default='',
        help_text='Recommended meta description snippet.'
    )
    suggested_slug = models.CharField(
        max_length=255,
        blank=True,
        default='',
        help_text='Optimized URL slug path.'
    )
    schema_json_ld = models.JSONField(
        default=dict,
        blank=True,
        help_text='Structured JSON-LD schema markup (Article, FAQPage, WebPage, etc.).'
    )
    generated_content = models.JSONField(
        default=dict,
        blank=True,
        help_text='Raw structured response payload from the AI writer.'
    )
    generation_metadata = models.JSONField(
        default=dict,
        blank=True,
        help_text='Model name, grounded sources, and generation parameters.'
    )
    status = models.CharField(
        max_length=30,
        choices=DraftStatus.choices,
        default=DraftStatus.GENERATED,
        db_index=True,
        help_text='Editorial workflow status (draft, generating, generated, reviewed, approved, published, archived).'
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        help_text='Timestamp when the draft was created.'
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        help_text='Timestamp when the draft was last updated.'
    )

    class Meta:
        db_table = 'seo_content_drafts'
        verbose_name = 'SEO content draft'
        verbose_name_plural = 'SEO content drafts'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['project', 'status'], name='seo_draft_proj_stat_idx'),
            models.Index(fields=['project', 'content_type'], name='seo_draft_proj_type_idx'),
            models.Index(fields=['brief', 'status'], name='seo_draft_brief_stat_idx'),
            models.Index(fields=['project', '-created_at'], name='seo_draft_proj_date_idx'),
        ]

    def __str__(self):
        return f"[{self.get_status_display()}] {self.title} ({self.project.name})"


class ActionType(models.TextChoices):
    UPDATE_TITLE = 'update_title', 'Update Title'
    UPDATE_META_DESCRIPTION = 'update_meta_description', 'Update Meta Description'
    UPDATE_SLUG = 'update_slug', 'Update Slug'
    OPTIMIZE_EXISTING_CONTENT = 'optimize_existing_content', 'Optimize Existing Content'
    PUBLISH_NEW_CONTENT = 'publish_new_content', 'Publish New Content'
    ADD_INTERNAL_LINKS = 'add_internal_links', 'Add Internal Links'
    ADD_STRUCTURED_DATA = 'add_structured_data', 'Add Structured Data'
    TECHNICAL_SEO_FIX = 'technical_seo_fix', 'Technical SEO Fix'
    CONTENT_REFRESH = 'content_refresh', 'Content Refresh'
    # Investigation Action Types
    OPTIMIZE_TITLE = 'optimize_title', 'Optimize Title'
    OPTIMIZE_META_DESCRIPTION = 'optimize_meta_description', 'Optimize Meta Description'
    FIX_MISSING_H1 = 'fix_missing_h1', 'Fix Missing H1'
    FIX_CANONICAL = 'fix_canonical', 'Fix Canonical'
    FIX_IMAGE_ALT = 'fix_image_alt', 'Fix Image Alt'
    FIX_BROKEN_LINK = 'fix_broken_link', 'Fix Broken Link'
    IMPROVE_CONTENT = 'improve_content', 'Improve Content'
    INVESTIGATE_PERFORMANCE = 'investigate_performance', 'Investigate Performance'
    MONITOR = 'monitor', 'Monitor'
    NO_ACTION = 'no_action', 'No Action'
    # Autonomous Action Planning Types
    FIX_BROKEN_INTERNAL_LINK = 'fix_broken_internal_link', 'Fix Broken Internal Link'
    REMOVE_REDIRECT_CHAIN = 'remove_redirect_chain', 'Remove Redirect Chain'
    IMPROVE_INTERNAL_LINKING = 'improve_internal_linking', 'Improve Internal Linking'
    INVESTIGATE_RANKING_DROP = 'investigate_ranking_drop', 'Investigate Ranking Drop'


class ActionStatus(models.TextChoices):
    PROPOSED = 'proposed', 'Proposed'
    PENDING_APPROVAL = 'pending_approval', 'Pending Approval'
    REVIEWED = 'reviewed', 'Reviewed'
    APPROVED = 'approved', 'Approved'
    READY_TO_EXECUTE = 'ready_to_execute', 'Ready to Execute'
    AUTHORIZED = 'authorized', 'Authorized'
    EXECUTING = 'executing', 'Executing'
    COMPLETED = 'completed', 'Completed'
    VERIFYING = 'verifying', 'Verifying'
    VERIFIED = 'verified', 'Verified'
    REJECTED = 'rejected', 'Rejected'
    FAILED = 'failed', 'Failed'
    BLOCKED = 'blocked', 'Blocked'
    ROLLED_BACK = 'rolled_back', 'Rolled Back'
    CANCELLED = 'cancelled', 'Cancelled'


class ActionPriority(models.TextChoices):
    CRITICAL = 'critical', 'Critical'
    HIGH = 'high', 'High'
    MEDIUM = 'medium', 'Medium'
    LOW = 'low', 'Low'


class ActionRiskLevel(models.TextChoices):
    LOW = 'low', 'Low'
    MEDIUM = 'medium', 'Medium'
    HIGH = 'high', 'High'
    CRITICAL = 'critical', 'Critical'


class ActionPlanStatus(models.TextChoices):
    DRAFT = 'draft', 'Draft'
    PROPOSED = 'proposed', 'Proposed'
    AWAITING_APPROVAL = 'awaiting_approval', 'Awaiting Approval'
    APPROVED = 'approved', 'Approved'
    EXECUTING = 'executing', 'Executing'
    COMPLETED = 'completed', 'Completed'
    PARTIALLY_COMPLETED = 'partially_completed', 'Partially Completed'
    FAILED = 'failed', 'Failed'
    REJECTED = 'rejected', 'Rejected'
    CANCELLED = 'cancelled', 'Cancelled'


class VerificationStatus(models.TextChoices):
    PENDING = 'pending', 'Pending'
    VERIFYING = 'verifying', 'Verifying'
    VERIFIED = 'verified', 'Verified'
    FAILED = 'failed', 'Failed'
    PARTIALLY_VERIFIED = 'partially_verified', 'Partially Verified'


class SEOOutcome(models.TextChoices):
    IMPROVED = 'improved', 'Improved'
    NO_CHANGE = 'no_change', 'No Change'
    DECLINED = 'declined', 'Declined'
    UNKNOWN = 'unknown', 'Unknown'
    INSUFFICIENT_DATA = 'insufficient_data', 'Insufficient Data'


class PlanSEOOutcome(models.TextChoices):
    EFFECTIVE = 'effective', 'Effective'
    PARTIALLY_EFFECTIVE = 'partially_effective', 'Partially Effective'
    INEFFECTIVE = 'ineffective', 'Ineffective'
    DECLINED = 'declined', 'Declined'
    UNKNOWN = 'unknown', 'Unknown'
    INSUFFICIENT_DATA = 'insufficient_data', 'Insufficient Data'


class EvidenceQuality(models.TextChoices):
    HIGH = 'high', 'High'
    MEDIUM = 'medium', 'Medium'
    LOW = 'low', 'Low'
    INSUFFICIENT = 'insufficient', 'Insufficient'


class SEOActionPlan(models.Model):
    """
    SEOActionPlan model representing a structured, cohesive SEO action plan
    composed of multiple atomic SEO actions generated by the autonomous agent.
    Maintains project ownership, evidence provenance, risk classification,
    human approval lifecycle, execution progress, real-world verification status,
    and post-execution SEO outcome learning.
    Relationship: Project 1 ─────── * SEOActionPlan
                  AgentRun 1 ────── * SEOActionPlan (optional)
                  SEOActionPlan 1 ── * SEOAction
    Ownership follows: plan.project -> project.owner
    """
    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        related_name='action_plans',
        help_text='The project this action plan belongs to.'
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_seo_action_plans',
        help_text='Authenticated user who generated or requested this action plan.'
    )
    agent_run = models.ForeignKey(
        'AgentRun',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='action_plans',
        help_text='Optional autonomous agent execution run that produced this plan.'
    )
    title = models.CharField(
        max_length=255,
        help_text='Concise title for the cohesive SEO action plan.'
    )
    summary = models.TextField(
        blank=True,
        default='',
        help_text='Executive summary of detected opportunities, root causes, and expected impact.'
    )
    source_evidence = models.JSONField(
        default=dict,
        blank=True,
        help_text='Aggregated source evidence (audit issues, GSC anomalies, insights, investigation IDs).'
    )
    status = models.CharField(
        max_length=30,
        choices=ActionPlanStatus.choices,
        default=ActionPlanStatus.DRAFT,
        db_index=True,
        help_text='Plan workflow and approval status.'
    )
    risk_level = models.CharField(
        max_length=20,
        choices=ActionRiskLevel.choices,
        default=ActionRiskLevel.LOW,
        db_index=True,
        help_text='Aggregate deterministic risk classification for this action plan.'
    )
    confidence_score = models.FloatField(
        default=0.0,
        help_text='Deterministic confidence score (0.0 to 1.0) derived from supporting empirical evidence.'
    )
    requires_human_approval = models.BooleanField(
        default=True,
        db_index=True,
        help_text='Whether any mutation action in this plan requires explicit human approval.'
    )
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='approved_seo_action_plans',
        help_text='Authenticated user who approved this plan.'
    )
    approved_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text='Timestamp of human approval.'
    )
    rejected_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='rejected_seo_action_plans',
        help_text='Authenticated user who rejected this plan.'
    )
    rejected_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text='Timestamp of plan rejection.'
    )
    rejection_reason = models.TextField(
        blank=True,
        default='',
        help_text='Mandatory explanation provided when rejecting the plan.'
    )
    execution_started_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text='Timestamp when plan execution began.'
    )
    completed_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text='Timestamp when all plan actions completed.'
    )
    failure_reason = models.TextField(
        blank=True,
        default='',
        help_text='Detailed error message if plan execution failed.'
    )
    verification_status = models.CharField(
        max_length=30,
        choices=VerificationStatus.choices,
        default=VerificationStatus.PENDING,
        db_index=True,
        help_text='Aggregated real-world verification status after applying plan actions.'
    )
    verification_results = models.JSONField(
        default=dict,
        blank=True,
        help_text='Aggregated verification evidence, before/after diffs, and crawler observations.'
    )
    seo_outcome = models.CharField(
        max_length=30,
        choices=SEOOutcome.choices,
        default=SEOOutcome.UNKNOWN,
        db_index=True,
        help_text='Measured post-execution SEO outcome (improved, no_change, declined, unknown, insufficient_data).'
    )
    outcome_confidence = models.FloatField(
        default=0.0,
        help_text='Bounded confidence score (0.0 to 1.0) in the measured SEO outcome.'
    )
    outcome_summary = models.JSONField(
        default=dict,
        blank=True,
        help_text='Aggregated post-execution outcome breakdown, statistical trends, and effectiveness.'
    )
    outcome_measured_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text='Timestamp when the SEO outcome was measured.'
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        help_text='Timestamp when the action plan was created.'
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        help_text='Timestamp when the action plan was last updated.'
    )

    class Meta:
        db_table = 'seo_action_plans'
        verbose_name = 'SEO action plan'
        verbose_name_plural = 'SEO action plans'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['project', 'status'], name='seo_plan_proj_stat_idx'),
            models.Index(fields=['project', 'risk_level'], name='seo_plan_proj_risk_idx'),
            models.Index(fields=['project', '-created_at'], name='seo_plan_proj_date_idx'),
            models.Index(fields=['verification_status'], name='seo_plan_verif_stat_idx'),
            models.Index(fields=['seo_outcome'], name='seo_plan_outcome_idx'),
        ]

    def __str__(self):
        return f"Plan #{self.id}: {self.title} [{self.get_status_display()}] ({self.project.name})"


class SEOAction(models.Model):
    """
    SEOAction model representing an actionable, executable SEO task derived from
    an investigation, recommendation, content brief, content draft, or action plan.
    Includes a strict human-in-the-loop approval lifecycle, safe mutation execution gating,
    and post-execution verification tracking.
    Relationship: Project 1 ─────── * SEOAction
                  SEOActionPlan 1 ─── * SEOAction (optional)
                  SEORecommendation 1 ─── * SEOAction (optional)
                  SEOContentBrief 1 ─── * SEOAction (optional)
                  SEOContentDraft 1 ─── * SEOAction (optional)
    Ownership follows: action.project -> project.owner
    """
    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        related_name='actions',
        help_text='The project this SEO action belongs to.'
    )
    plan = models.ForeignKey(
        SEOActionPlan,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='actions',
        help_text='Optional parent SEO action plan this action is part of.'
    )
    recommendation = models.ForeignKey(
        SEORecommendation,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='actions',
        help_text='Optional originating SEO recommendation.'
    )
    brief = models.ForeignKey(
        SEOContentBrief,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='actions',
        help_text='Optional originating SEO content brief.'
    )
    draft = models.ForeignKey(
        SEOContentDraft,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='actions',
        help_text='Optional originating SEO content draft.'
    )
    investigation_id = models.CharField(
        max_length=100,
        blank=True,
        default='',
        db_index=True,
        help_text='Optional originating SEO investigation reference ID.'
    )
    opportunity_type = models.CharField(
        max_length=100,
        blank=True,
        default='',
        help_text='Originating SEO opportunity classification.'
    )
    title = models.CharField(
        max_length=255,
        help_text='Concise title for the executable SEO task.'
    )
    description = models.TextField(
        help_text='Detailed explanation of why this action is required and expected SEO impact.'
    )
    rationale = models.TextField(
        blank=True,
        default='',
        help_text='Detailed causal reasoning and justification for the proposed action.'
    )
    evidence_snapshot = models.JSONField(
        default=dict,
        blank=True,
        help_text='Structured evidence snapshot (GSC metrics, audit issues, observed facts, inferences, confidence).'
    )
    action_type = models.CharField(
        max_length=50,
        choices=ActionType.choices,
        default=ActionType.OPTIMIZE_EXISTING_CONTENT,
        db_index=True,
        help_text='Type of SEO task (title, meta description, publishing, structured data, etc.).'
    )
    target_url = models.CharField(
        max_length=500,
        blank=True,
        default='',
        help_text='Target URL on the project website where the action will be applied.'
    )
    target_keyword = models.CharField(
        max_length=255,
        blank=True,
        default='',
        help_text='Primary target search keyword query.'
    )
    current_state = models.JSONField(
        default=dict,
        blank=True,
        help_text='Snapshot of existing website metadata, metrics, or content before applying the action.'
    )
    proposed_change = models.JSONField(
        default=dict,
        blank=True,
        help_text='Structured proposal of changes to apply (e.g. new title, meta description, publishing package, schema markup).'
    )
    implementation_instructions = models.TextField(
        help_text='Step-by-step instructions for marketers, SEO specialists, or developers.'
    )
    priority = models.CharField(
        max_length=20,
        choices=ActionPriority.choices,
        default=ActionPriority.HIGH,
        db_index=True,
        help_text='Execution priority level.'
    )
    risk_level = models.CharField(
        max_length=20,
        default='low',
        db_index=True,
        help_text='Evaluated risk level (low, medium, high, critical).'
    )
    impact_estimate = models.CharField(
        max_length=20,
        default='medium',
        help_text='Estimated impact (low, medium, high).'
    )
    effort_estimate = models.CharField(
        max_length=20,
        default='low',
        help_text='Estimated effort (low, medium, high).'
    )
    requires_human_approval = models.BooleanField(
        default=True,
        db_index=True,
        help_text='Whether this action mutates state and requires explicit human sign-off.'
    )
    status = models.CharField(
        max_length=30,
        choices=ActionStatus.choices,
        default=ActionStatus.PENDING_APPROVAL,
        db_index=True,
        help_text='Human approval workflow status.'
    )
    assigned_to = models.CharField(
        max_length=100,
        blank=True,
        default='',
        help_text='Person or team responsible for executing or reviewing this action.'
    )
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='approved_seo_actions',
        help_text='Authenticated user who explicitly approved this action.'
    )
    approved_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text='Timestamp of human approval.'
    )
    rejected_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='rejected_seo_actions',
        help_text='Authenticated user who rejected this action.'
    )
    rejected_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text='Timestamp of rejection.'
    )
    rejection_reason = models.TextField(
        blank=True,
        default='',
        help_text='Mandatory explanation given by human reviewer when rejecting.'
    )
    execution_started_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text='Timestamp when executor began applying the action.'
    )
    completed_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text='Timestamp when the action was completed or executed.'
    )
    failure_reason = models.TextField(
        blank=True,
        default='',
        help_text='Detailed error message if execution failed.'
    )
    execution_metadata = models.JSONField(
        default=dict,
        blank=True,
        help_text='Safe execution logs, timestamps, target endpoints, monitoring baselines, and results.'
    )
    verification_status = models.CharField(
        max_length=30,
        choices=VerificationStatus.choices,
        default=VerificationStatus.PENDING,
        db_index=True,
        help_text='Real-world verification status after applying the action.'
    )
    verification_result = models.JSONField(
        default=dict,
        blank=True,
        help_text='Structured verification results, before/after HTML snapshot diffs, and crawler evidence.'
    )
    seo_outcome = models.CharField(
        max_length=30,
        choices=SEOOutcome.choices,
        default=SEOOutcome.UNKNOWN,
        db_index=True,
        help_text='Measured post-execution SEO outcome (improved, no_change, declined, unknown, insufficient_data).'
    )
    outcome_confidence = models.FloatField(
        default=0.0,
        help_text='Bounded confidence score (0.0 to 1.0) in the measured SEO outcome.'
    )
    outcome_evidence = models.JSONField(
        default=dict,
        blank=True,
        help_text='Empirical evidence, baseline vs post-execution metrics, issue resolution state, and explanation.'
    )
    outcome_measured_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text='Timestamp when the SEO outcome was measured.'
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        help_text='Timestamp when the action was created.'
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        help_text='Timestamp when the action was last modified.'
    )

    class Meta:
        db_table = 'seo_actions'
        verbose_name = 'SEO action'
        verbose_name_plural = 'SEO actions'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['project', 'status'], name='seo_act_proj_stat_idx'),
            models.Index(fields=['project', 'action_type'], name='seo_act_proj_type_idx'),
            models.Index(fields=['project', 'priority'], name='seo_act_proj_prio_idx'),
            models.Index(fields=['recommendation', 'status'], name='seo_act_rec_stat_idx'),
            models.Index(fields=['draft', 'status'], name='seo_act_draft_stat_idx'),
            models.Index(fields=['project', '-created_at'], name='seo_act_proj_date_idx'),
            models.Index(fields=['investigation_id'], name='seo_act_inv_id_idx'),
            models.Index(fields=['plan', 'status'], name='seo_act_plan_stat_idx'),
            models.Index(fields=['verification_status'], name='seo_act_verif_stat_idx'),
            models.Index(fields=['seo_outcome'], name='seo_act_outcome_idx'),
        ]

    def __str__(self):
        return f"[{self.get_action_type_display()}] {self.title} ({self.get_status_display()})"


class ContinuousOperationStatus(models.TextChoices):
    INACTIVE = 'inactive', 'Inactive'
    ACTIVE = 'active', 'Active'
    RUNNING = 'running', 'Running'
    PAUSED = 'paused', 'Paused'
    WAITING = 'waiting', 'Waiting'
    FAILED = 'failed', 'Failed'
    COMPLETED = 'completed', 'Completed'


class ContinuousOperationScheduleType(models.TextChoices):
    INTERVAL_MINUTES = 'interval_minutes', 'Every N Minutes'
    INTERVAL_HOURS = 'interval_hours', 'Every N Hours'
    DAILY = 'daily', 'Daily'


class ContinuousOperation(models.Model):
    """
    ContinuousOperation model representing a persistent, scheduled agent operational lifecycle
    for a specific Project.
    Milestone 6.1: Continuous Agent Operations.
    Relationship: Project 1 ─────── * ContinuousOperation
                  ContinuousOperation 1 ─────── * AgentRun
    Ownership follows: operation.project -> project.owner
    """
    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        related_name='continuous_operations',
        help_text='The project this continuous agent operation belongs to.'
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='continuous_operations',
        help_text='The user who created/initiated this continuous operation.'
    )
    goal = models.TextField(
        help_text='High-level operational SEO objective or ongoing monitoring goal.'
    )
    status = models.CharField(
        max_length=30,
        choices=ContinuousOperationStatus.choices,
        default=ContinuousOperationStatus.ACTIVE,
        db_index=True,
        help_text='Current operational state of the continuous operation.'
    )
    schedule_type = models.CharField(
        max_length=30,
        choices=ContinuousOperationScheduleType.choices,
        default=ContinuousOperationScheduleType.INTERVAL_MINUTES,
        help_text='Recurrence schedule type: interval_minutes, interval_hours, or daily.'
    )
    interval_value = models.PositiveIntegerField(
        default=30,
        help_text='Frequency interval unit (e.g. 30 for 30 min, 2 for 2 hours, 1 for daily).'
    )
    schedule_config = models.JSONField(
        default=dict,
        blank=True,
        help_text='Structured execution parameters (workflow, target_url, target_query, max_steps, etc.).'
    )
    current_run = models.ForeignKey(
        'AgentRun',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='active_continuous_operation',
        help_text='The currently executing AgentRun, if any (enforces at most one active run).'
    )
    last_run = models.ForeignKey(
        'AgentRun',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='last_continuous_operation',
        help_text='The most recently completed or attempted AgentRun.'
    )
    last_successful_run = models.ForeignKey(
        'AgentRun',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='successful_continuous_operations',
        help_text='The most recently succeeded AgentRun.'
    )
    next_run_at = models.DateTimeField(
        null=True,
        blank=True,
        db_index=True,
        help_text='Calculated timestamp when the next AgentRun should be triggered by the scheduler.'
    )
    last_run_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text='Timestamp when the most recent run was initiated.'
    )
    consecutive_failures = models.PositiveIntegerField(
        default=0,
        help_text='Number of consecutive failed runs since last success (for circuit breaking / backoff).'
    )
    max_consecutive_failures = models.PositiveIntegerField(
        default=5,
        help_text='Maximum consecutive failures allowed before transitioning to terminal FAILED status.'
    )
    failed_run_id = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text='Identifier of the most recently failed AgentRun.'
    )
    failure_category = models.CharField(
        max_length=50,
        blank=True,
        default='',
        help_text='Categorization of recent failure (e.g. execution_failure, timeout, circuit_breaker).'
    )
    failure_reason = models.TextField(
        blank=True,
        default='',
        help_text='Sanitized summary of the failure reason from the failed run.'
    )
    total_runs = models.PositiveIntegerField(
        default=0,
        help_text='Total number of AgentRuns launched under this continuous operation.'
    )
    successful_runs = models.PositiveIntegerField(
        default=0,
        help_text='Total count of successfully completed AgentRuns.'
    )
    failed_runs = models.PositiveIntegerField(
        default=0,
        help_text='Total count of failed AgentRuns.'
    )
    metrics = models.JSONField(
        default=dict,
        blank=True,
        help_text='Persisted operational runtime statistics (duplicate_prevention_count, avg_duration, etc.).'
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        help_text='Timestamp when the continuous operation was created.'
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        help_text='Timestamp when the continuous operation was last updated.'
    )
    paused_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text='Timestamp when the operation was paused.'
    )
    resumed_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text='Timestamp when the operation was resumed.'
    )

    class Meta:
        db_table = 'seo_continuous_operations'
        verbose_name = 'Continuous operation'
        verbose_name_plural = 'Continuous operations'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['project', 'status'], name='seo_cont_op_proj_stat_idx'),
            models.Index(fields=['status', 'next_run_at'], name='seo_cont_op_stat_next_idx'),
            models.Index(fields=['project', '-created_at'], name='seo_cont_op_proj_date_idx'),
        ]

    def __str__(self):
        return f"Operation #{self.id} [{self.project.name}]: {self.goal[:40]} ({self.get_status_display()})"


class AgentRunStatus(models.TextChoices):
    PENDING = 'pending', 'Pending'
    RUNNING = 'running', 'Running'
    WAITING_FOR_APPROVAL = 'waiting_for_approval', 'Waiting for Approval'
    COMPLETED = 'completed', 'Completed'
    FAILED = 'failed', 'Failed'
    CANCELLED = 'cancelled', 'Cancelled'


class AgentActionType(models.TextChoices):
    PLAN = 'plan', 'Plan'
    TOOL_CALL = 'tool_call', 'Tool Call'
    OBSERVATION = 'observation', 'Observation'
    DECISION = 'decision', 'Decision'
    FINAL = 'final', 'Final'
    APPROVAL = 'approval', 'Approval'


class AgentStepStatus(models.TextChoices):
    PENDING = 'pending', 'Pending'
    RUNNING = 'running', 'Running'
    COMPLETED = 'completed', 'Completed'
    FAILED = 'failed', 'Failed'
    WAITING = 'waiting', 'Waiting'


class AgentRun(models.Model):
    """
    AgentRun model representing an autonomous agent execution session initiated by a user
    for a specific Project with a defined high-level SEO goal.
    Relationship: Project 1 ─────── * AgentRun
                  User 1 ────────── * AgentRun
                  ContinuousOperation 1 ──── * AgentRun
    Ownership follows: run.project -> project.owner
    """
    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        related_name='agent_runs',
        help_text='The project this agent execution run belongs to.'
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='agent_runs',
        help_text='The user who initiated this agent run.'
    )
    continuous_operation = models.ForeignKey(
        ContinuousOperation,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='runs',
        help_text='The continuous operational lifecycle session this run was scheduled under, if any.'
    )
    goal = models.TextField(
        help_text='The high-level SEO objective or task for the agent.'
    )
    status = models.CharField(
        max_length=30,
        choices=AgentRunStatus.choices,
        default=AgentRunStatus.PENDING,
        db_index=True,
        help_text='Current execution status of the agent run.'
    )
    plan = models.JSONField(
        default=list,
        blank=True,
        help_text='Structured list of planned sub-tasks or milestones.'
    )
    context_snapshot = models.JSONField(
        default=dict,
        blank=True,
        help_text='Snapshot of project SEO state and baseline metrics when run started.'
    )
    max_steps = models.PositiveIntegerField(
        default=15,
        help_text='Maximum allowed reasoning/execution steps to prevent unbounded execution loops.'
    )
    total_steps = models.PositiveIntegerField(
        default=0,
        help_text='Total steps executed so far during this run.'
    )
    summary = models.TextField(
        blank=True,
        default='',
        help_text='Final executive summary or conclusion of the agent run.'
    )
    # Milestone 6.7: Production Agent Platform Fields
    worker_id = models.CharField(
        max_length=128,
        null=True,
        blank=True,
        db_index=True,
        help_text='Identifier of the Celery worker currently executing this run.'
    )
    lease_expires_at = models.DateTimeField(
        null=True,
        blank=True,
        db_index=True,
        help_text='Timestamp when worker execution lease expires.'
    )
    last_heartbeat_at = models.DateTimeField(
        null=True,
        blank=True,
        db_index=True,
        help_text='Timestamp of the most recent worker heartbeat.'
    )
    correlation_id = models.CharField(
        max_length=128,
        null=True,
        blank=True,
        db_index=True,
        help_text='Distributed tracing correlation ID linking requests, runs, tasks, and tools.'
    )
    retry_count = models.PositiveIntegerField(
        default=0,
        help_text='Number of retries attempted for this agent run session.'
    )
    max_retries = models.PositiveIntegerField(
        default=3,
        help_text='Maximum allowed retry attempts before marking run as permanently failed.'
    )
    recovery_status = models.CharField(
        max_length=32,
        default='none',
        db_index=True,
        help_text='Current recovery state: none, recovered, reconciling, failed, blocked.'
    )
    execution_metadata = models.JSONField(
        default=dict,
        blank=True,
        help_text='Resource consumption telemetry: llm_calls, tool_calls, duration_ms, external_ops.'
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        help_text='Timestamp when the agent run was created.'
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        help_text='Timestamp when the agent run was last modified.'
    )
    completed_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text='Timestamp when the agent run reached a terminal state (completed, failed, cancelled).'
    )

    class Meta:
        db_table = 'seo_agent_runs'
        verbose_name = 'Agent run'
        verbose_name_plural = 'Agent runs'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['project', 'status'], name='seo_agent_run_proj_stat_idx'),
            models.Index(fields=['user', 'status'], name='seo_agent_run_user_stat_idx'),
            models.Index(fields=['project', '-created_at'], name='seo_agent_run_proj_date_idx'),
            models.Index(fields=['continuous_operation', '-created_at'], name='seo_agent_run_cont_date_idx'),
            models.Index(fields=['status', 'lease_expires_at'], name='seo_agent_run_lease_idx'),
            models.Index(fields=['correlation_id'], name='seo_agent_run_correl_idx'),
        ]

    def __str__(self):
        return f"Run #{self.id}: {self.goal[:50]} ({self.get_status_display()})"


class AgentStep(models.Model):
    """
    AgentStep model representing one discrete reasoning, decision, or tool-execution step
    within an AgentRun session.
    Relationship: AgentRun 1 ─────── * AgentStep
    """
    run = models.ForeignKey(
        AgentRun,
        on_delete=models.CASCADE,
        related_name='steps',
        help_text='The agent run session this step belongs to.'
    )
    step_number = models.PositiveIntegerField(
        help_text='Sequential 1-indexed step number within the run.'
    )
    thought = models.TextField(
        blank=True,
        default='',
        help_text='Internal reasoning or thought process of the agent at this step.'
    )
    action_type = models.CharField(
        max_length=30,
        choices=AgentActionType.choices,
        default=AgentActionType.PLAN,
        db_index=True,
        help_text='Type of action taken in this step (plan, tool_call, observation, decision, final, approval).'
    )
    status = models.CharField(
        max_length=30,
        choices=AgentStepStatus.choices,
        default=AgentStepStatus.PENDING,
        db_index=True,
        help_text='Execution status of this step.'
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        help_text='Timestamp when this step was created.'
    )
    completed_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text='Timestamp when this step completed execution.'
    )

    class Meta:
        db_table = 'seo_agent_steps'
        verbose_name = 'Agent step'
        verbose_name_plural = 'Agent steps'
        ordering = ['run', 'step_number']
        constraints = [
            models.UniqueConstraint(
                fields=['run', 'step_number'],
                name='unique_agent_run_step_number'
            )
        ]
        indexes = [
            models.Index(fields=['run', 'step_number'], name='seo_agent_step_run_num_idx'),
            models.Index(fields=['run', 'status'], name='seo_agent_step_run_stat_idx'),
        ]

    def __str__(self):
        return f"Run #{self.run_id} Step {self.step_number} [{self.get_action_type_display()}]"


class AgentToolCall(models.Model):
    """
    AgentToolCall model representing a specific tool invocation made during an AgentStep.
    Relationship: AgentStep 1 ─────── * AgentToolCall
    """
    step = models.ForeignKey(
        AgentStep,
        on_delete=models.CASCADE,
        related_name='tool_calls',
        help_text='The agent step in which this tool was invoked.'
    )
    tool_name = models.CharField(
        max_length=150,
        db_index=True,
        help_text='The identifier/name of the invoked tool.'
    )
    tool_input = models.JSONField(
        default=dict,
        blank=True,
        help_text='Structured JSON arguments passed to the tool.'
    )
    tool_output = models.JSONField(
        default=dict,
        blank=True,
        help_text='Structured JSON output or observation returned by the tool.'
    )
    error_message = models.TextField(
        blank=True,
        default='',
        help_text='Error message or stack summary if tool execution failed.'
    )
    duration_ms = models.PositiveIntegerField(
        default=0,
        help_text='Execution latency of the tool call in milliseconds.'
    )
    is_mutating = models.BooleanField(
        default=False,
        help_text='Whether this tool invocation changes external or persistent database state.'
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        help_text='Timestamp when the tool call was initiated.'
    )
    completed_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text='Timestamp when the tool call finished execution.'
    )

    class Meta:
        db_table = 'seo_agent_tool_calls'
        verbose_name = 'Agent tool call'
        verbose_name_plural = 'Agent tool calls'
        ordering = ['created_at']
        indexes = [
            models.Index(fields=['step', 'tool_name'], name='seo_agent_tc_step_name_idx'),
            models.Index(fields=['tool_name'], name='seo_agent_tc_name_idx'),
        ]

    def __str__(self):
        status_str = "Error" if self.error_message else "OK"
        return f"{self.tool_name} on Step #{self.step_id} ({status_str}, {self.duration_ms}ms)"


class SEOEventType(models.TextChoices):
    RANKING_CHANGE = 'ranking_change', 'Ranking Change'
    PAGE_STATUS_CHANGE = 'page_status_change', 'Page Status Change'
    SEO_AUDIT_CHANGE = 'seo_audit_change', 'SEO Audit Change'
    GSC_CHANGE = 'gsc_change', 'Google Search Console Performance Change'
    CRAWL_ISSUE = 'crawl_issue', 'Crawl Issue Detected'
    KEYWORD_VISIBILITY_CHANGE = 'keyword_visibility_change', 'Keyword Visibility Change'
    CONTENT_CHANGE = 'content_change', 'Content Change Detected'


class SEOEventSeverity(models.TextChoices):
    LOW = 'low', 'Low'
    MEDIUM = 'medium', 'Medium'
    HIGH = 'high', 'High'
    CRITICAL = 'critical', 'Critical'


class SEOEventStatus(models.TextChoices):
    RECEIVED = 'received', 'Received'
    ACCEPTED = 'accepted', 'Accepted'
    PROCESSED = 'processed', 'Processed'
    SUPPRESSED = 'suppressed', 'Suppressed'
    DEDUPLICATED = 'deduplicated', 'Deduplicated'
    REJECTED = 'rejected', 'Rejected'
    FAILED = 'failed', 'Failed'


class SEOEvent(models.Model):
    """
    SEOEvent model representing a persistent, meaningful SEO event that can trigger
    specialized agent workflows (Milestone 6.2: Event-Driven Agents).
    """
    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        related_name='seo_events',
        help_text='The project this SEO event belongs to.'
    )
    event_type = models.CharField(
        max_length=64,
        choices=SEOEventType.choices,
        db_index=True,
        help_text='Controlled classification of the SEO event.'
    )
    source = models.CharField(
        max_length=128,
        db_index=True,
        help_text='Originating system or component that generated this event.'
    )
    severity = models.CharField(
        max_length=32,
        choices=SEOEventSeverity.choices,
        default=SEOEventSeverity.MEDIUM,
        db_index=True,
        help_text='Severity level determining priority and trigger eligibility.'
    )
    status = models.CharField(
        max_length=32,
        choices=SEOEventStatus.choices,
        default=SEOEventStatus.RECEIVED,
        db_index=True,
        help_text='Current lifecycle state of the event.'
    )
    payload = models.JSONField(
        default=dict,
        blank=True,
        help_text='Structured JSON payload containing event metrics and context.'
    )
    correlation_id = models.CharField(
        max_length=128,
        db_index=True,
        help_text='Unique identifier linking this event across workflows and runs.'
    )
    idempotency_key = models.CharField(
        max_length=255,
        db_index=True,
        help_text='Deterministic deduplication key to prevent duplicate runs.'
    )
    occurred_at = models.DateTimeField(
        default=timezone.now,
        db_index=True,
        help_text='Timestamp when the underlying event actually occurred.'
    )
    received_at = models.DateTimeField(
        default=timezone.now,
        help_text='Timestamp when the event was ingested by DoxaRank.'
    )
    processed_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text='Timestamp when event trigger processing completed.'
    )
    suppression_reason = models.CharField(
        max_length=255,
        blank=True,
        default='',
        help_text='Explanation if event was suppressed by cooldown or storm policy.'
    )
    agent_run = models.ForeignKey(
        AgentRun,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='triggering_events',
        help_text='The AgentRun triggered by this event, if any.'
    )
    continuous_operation = models.ForeignKey(
        ContinuousOperation,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='triggered_events',
        help_text='Optional continuous operation session linked to this event.'
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        help_text='Timestamp when this event record was persisted.'
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        help_text='Timestamp when this event record was last updated.'
    )

    class Meta:
        db_table = 'seo_events'
        verbose_name = 'SEO event'
        verbose_name_plural = 'SEO events'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['project', 'event_type', 'created_at'], name='seo_ev_proj_type_idx'),
            models.Index(fields=['project', 'idempotency_key'], name='seo_ev_proj_idemp_idx'),
            models.Index(fields=['status', 'created_at'], name='seo_ev_status_idx'),
            models.Index(fields=['occurred_at'], name='seo_ev_occurred_idx'),
        ]

    def __str__(self):
        return f"SEOEvent #{self.id} [{self.event_type}] ({self.status}, {self.severity}) for Project #{self.project_id}"


class MonitorType(models.TextChoices):
    RANKING = 'ranking', 'Ranking Monitor'
    PAGE_STATUS = 'page_status', 'Page Status Monitor'
    SEO_AUDIT = 'seo_audit', 'SEO Audit Monitor'
    KEYWORD_VISIBILITY = 'keyword_visibility', 'Keyword Visibility Monitor'


class MonitorStatus(models.TextChoices):
    HEALTHY = 'healthy', 'Healthy'
    WARNING = 'warning', 'Warning'
    ANOMALY = 'anomaly', 'Anomaly Detected'
    RECOVERED = 'recovered', 'Recovered'


class MonitoringState(models.Model):
    """
    MonitoringState model representing the persistent, authoritative state of a monitored
    metric or target for an SEO project (Milestone 6.3: Autonomous SEO Monitoring).
    Enables explainable baselines, change detection, and suppression of unchanged problems.
    """
    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        related_name='monitoring_states',
        help_text='The project this monitoring state belongs to.'
    )
    monitor_type = models.CharField(
        max_length=32,
        choices=MonitorType.choices,
        db_index=True,
        help_text='Specialized monitor type responsible for this metric.'
    )
    metric_key = models.CharField(
        max_length=128,
        db_index=True,
        help_text='Unique identifier of the entity or metric being monitored.'
    )
    current_value = models.JSONField(
        default=dict,
        help_text='Latest observation payload for this metric.'
    )
    previous_value = models.JSONField(
        default=dict,
        blank=True,
        help_text='Observation from the preceding monitoring cycle.'
    )
    baseline_value = models.JSONField(
        default=dict,
        blank=True,
        help_text='Established baseline value used as reference for change detection.'
    )
    status = models.CharField(
        max_length=32,
        choices=MonitorStatus.choices,
        default=MonitorStatus.HEALTHY,
        db_index=True,
        help_text='Current health classification of this monitored target.'
    )
    consecutive_anomalies = models.PositiveIntegerField(
        default=0,
        help_text='Number of consecutive cycles this metric remained in an anomaly state.'
    )
    snapshot_timestamp = models.DateTimeField(
        default=timezone.now,
        help_text='Timestamp of the active snapshot observation.'
    )
    last_checked_at = models.DateTimeField(
        default=timezone.now,
        db_index=True,
        help_text='When this target was last inspected by the monitoring service.'
    )
    last_changed_at = models.DateTimeField(
        default=timezone.now,
        help_text='When the observed value meaningfully changed.'
    )
    last_event_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text='When an SEOEvent was last generated for this target.'
    )
    last_event = models.ForeignKey(
        'SEOEvent',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='monitoring_states',
        help_text='Most recent SEOEvent triggered from this monitoring state.'
    )
    metadata = models.JSONField(
        default=dict,
        blank=True,
        help_text='Contextual metadata, e.g. configured thresholds, targets, and notes.'
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        help_text='Timestamp when this monitoring state was first established.'
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        help_text='Timestamp when this monitoring state was last updated.'
    )

    class Meta:
        db_table = 'seo_monitoring_states'
        verbose_name = 'monitoring state'
        verbose_name_plural = 'monitoring states'
        ordering = ['-last_checked_at']
        constraints = [
            models.UniqueConstraint(
                fields=['project', 'monitor_type', 'metric_key'],
                name='seo_mon_proj_type_key_uniq'
            )
        ]
        indexes = [
            models.Index(fields=['project', 'monitor_type'], name='seo_mon_proj_type_idx'),
            models.Index(fields=['project', 'last_checked_at'], name='seo_mon_proj_checked_idx'),
            models.Index(fields=['status', 'last_checked_at'], name='seo_mon_status_checked_idx'),
        ]

    def __str__(self):
        return f"MonitoringState [{self.monitor_type}] '{self.metric_key}' ({self.status}) for Project #{self.project_id}"


class MonitoringSnapshot(models.Model):
    """
    MonitoringSnapshot model representing an individual historical observation captured
    during a monitoring cycle (Milestone 6.3: Autonomous SEO Monitoring).
    """
    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        related_name='monitoring_snapshots',
        help_text='The project this snapshot belongs to.'
    )
    monitor_type = models.CharField(
        max_length=32,
        choices=MonitorType.choices,
        db_index=True,
        help_text='Monitor type that captured this snapshot.'
    )
    metric_key = models.CharField(
        max_length=128,
        db_index=True,
        help_text='Identifier of the entity or metric being monitored.'
    )
    value = models.JSONField(
        default=dict,
        help_text='Observed snapshot value payload.'
    )
    baseline_value = models.JSONField(
        default=dict,
        blank=True,
        help_text='Baseline reference at the time of snapshot.'
    )
    delta = models.JSONField(
        default=dict,
        blank=True,
        help_text='Computed difference relative to baseline.'
    )
    status = models.CharField(
        max_length=32,
        choices=MonitorStatus.choices,
        default=MonitorStatus.HEALTHY,
        db_index=True,
        help_text='Health status classification at snapshot time.'
    )
    is_anomaly = models.BooleanField(
        default=False,
        db_index=True,
        help_text='Whether this snapshot exceeded threshold and represented an anomaly.'
    )
    is_recovery = models.BooleanField(
        default=False,
        help_text='Whether this snapshot marked a transition back to healthy from anomaly.'
    )
    created_at = models.DateTimeField(
        default=timezone.now,
        db_index=True,
        help_text='Timestamp when this snapshot observation was recorded.'
    )

    class Meta:
        db_table = 'seo_monitoring_snapshots'
        verbose_name = 'monitoring snapshot'
        verbose_name_plural = 'monitoring snapshots'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['project', 'monitor_type', '-created_at'], name='seo_snap_proj_type_idx'),
            models.Index(fields=['project', '-created_at'], name='seo_snap_proj_created_idx'),
        ]

    def __str__(self):
        anomaly_str = " (ANOMALY)" if self.is_anomaly else (" (RECOVERY)" if self.is_recovery else "")
        return f"Snapshot #{self.id} [{self.monitor_type}] '{self.metric_key}'{anomaly_str} for Project #{self.project_id}"


class RemediationRiskLevel(models.TextChoices):
    LOW = 'low', 'Low'
    MEDIUM = 'medium', 'Medium'
    HIGH = 'high', 'High'
    CRITICAL = 'critical', 'Critical'


class RemediationPolicyDecision(models.TextChoices):
    AUTONOMOUS_ALLOWED = 'autonomous_allowed', 'Autonomous Allowed'
    HUMAN_APPROVAL_REQUIRED = 'human_approval_required', 'Human Approval Required'
    BLOCKED = 'blocked', 'Blocked'


class RemediationErrorCategory(models.TextChoices):
    TOOL_FAILURE = 'tool_failure', 'Tool Failure'
    AUTHORIZATION_FAILURE = 'authorization_failure', 'Authorization Failure'
    HUMAN_REJECTION = 'human_rejection', 'Human Rejection'
    EXECUTION_TIMEOUT = 'execution_timeout', 'Execution Timeout'
    VERIFICATION_FAILURE = 'verification_failure', 'Verification Failure'
    TENANT_ISOLATION_FAILURE = 'tenant_isolation_failure', 'Tenant Isolation Failure'
    POLICY_BLOCK = 'policy_block', 'Policy Block'
    IDEMPOTENCY_CONFLICT = 'idempotency_conflict', 'Idempotency Conflict'


class ProjectRemediationPolicy(models.Model):
    """
    Project-level configuration and bounds for autonomous remediation (Milestone 6.4).
    Controls whether autonomous execution is enabled, daily quotas, confidence thresholds,
    and allowed action types.
    """
    project = models.OneToOneField(
        Project,
        on_delete=models.CASCADE,
        related_name='remediation_policy',
        help_text='The project this remediation policy applies to.'
    )
    is_autonomous_enabled = models.BooleanField(
        default=True,
        help_text='Whether autonomous remediation for authorized low-risk actions is permitted.'
    )
    max_daily_autonomous_actions = models.PositiveIntegerField(
        default=10,
        help_text='Maximum number of autonomous remediations allowed per calendar day.'
    )
    min_confidence_threshold = models.FloatField(
        default=0.85,
        help_text='Minimum confidence score required for an action to execute autonomously.'
    )
    allowed_autonomous_types = models.JSONField(
        default=list,
        blank=True,
        help_text='List of ActionType string values explicitly permitted for autonomous execution.'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'seo_project_remediation_policies'
        verbose_name = 'project remediation policy'
        verbose_name_plural = 'project remediation policies'

    def __str__(self):
        return f"RemediationPolicy(Project #{self.project_id}, Enabled={self.is_autonomous_enabled})"


class RemediationRecord(models.Model):
    """
    Persistent audit and execution record for an autonomous or human-approved SEO remediation (Milestone 6.4).
    Enforces deterministic idempotency, state snapshots for rollback, verification evidence,
    and failure categorization.
    """
    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        related_name='remediation_records',
        help_text='The project this remediation belongs to.'
    )
    action = models.ForeignKey(
        SEOAction,
        on_delete=models.CASCADE,
        related_name='remediation_records',
        help_text='The underlying SEO action being remediated.'
    )
    event = models.ForeignKey(
        'SEOEvent',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='remediation_records',
        help_text='The originating SEO event triggering this remediation.'
    )
    agent_run = models.ForeignKey(
        'AgentRun',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='remediation_records',
        help_text='The multi-agent run orchestrating this remediation.'
    )
    idempotency_key = models.CharField(
        max_length=64,
        db_index=True,
        help_text='SHA-256 fingerprint guaranteeing idempotency across workers and retries.'
    )
    risk_level = models.CharField(
        max_length=20,
        choices=RemediationRiskLevel.choices,
        default=RemediationRiskLevel.LOW,
        db_index=True,
        help_text='Assessed risk classification for this remediation.'
    )
    policy_decision = models.CharField(
        max_length=30,
        choices=RemediationPolicyDecision.choices,
        default=RemediationPolicyDecision.HUMAN_APPROVAL_REQUIRED,
        db_index=True,
        help_text='Centralized policy determination.'
    )
    policy_explanation = models.TextField(
        blank=True,
        default='',
        help_text='Detailed justification of the policy decision.'
    )
    is_autonomous = models.BooleanField(
        default=False,
        db_index=True,
        help_text='Whether this remediation was executed autonomously without human intervention.'
    )
    status = models.CharField(
        max_length=30,
        choices=ActionStatus.choices,
        default=ActionStatus.PROPOSED,
        db_index=True,
        help_text='Remediation execution & verification lifecycle status.'
    )
    rollback_data = models.JSONField(
        default=dict,
        blank=True,
        help_text='Snapshot of pre-remediation state to enable deterministic rollback.'
    )
    verification_data = models.JSONField(
        default=dict,
        blank=True,
        help_text='Empirical verification evidence collected post-execution.'
    )
    error_category = models.CharField(
        max_length=50,
        choices=RemediationErrorCategory.choices,
        blank=True,
        default='',
        db_index=True,
        help_text='Deterministic failure category if execution or verification fails.'
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'seo_remediation_records'
        verbose_name = 'remediation record'
        verbose_name_plural = 'remediation records'
        ordering = ['-created_at']
        unique_together = [('project', 'idempotency_key')]
        indexes = [
            models.Index(fields=['project', 'status'], name='seo_rem_proj_stat_idx'),
            models.Index(fields=['action', 'status'], name='seo_rem_act_stat_idx'),
            models.Index(fields=['project', '-created_at'], name='seo_rem_proj_created_idx'),
            models.Index(fields=['policy_decision'], name='seo_rem_decision_idx'),
        ]

    def __str__(self):
        return f"Remediation #{self.id} for Action #{self.action_id} [{self.status}] ({self.project.name})"


# ==============================================================================
# MILESTONE 6.5: MULTI-SYSTEM AGENT INTEGRATION MODELS
# ==============================================================================

class ExternalSystemType(models.TextChoices):
    CMS = 'cms', 'CMS'
    GIT = 'git', 'Git'
    WEBHOOK = 'webhook', 'Webhook/API'


class ExternalConnectionStatus(models.TextChoices):
    ACTIVE = 'active', 'Active'
    INACTIVE = 'inactive', 'Inactive'
    ERROR = 'error', 'Error'
    TEST_STAGING = 'test_staging', 'Test/Staging'


class ExternalOperationStatus(models.TextChoices):
    PENDING = 'pending', 'Pending'
    AUTHORIZED = 'authorized', 'Authorized'
    EXECUTING = 'executing', 'Executing'
    COMPLETED = 'completed', 'Completed'
    VERIFIED = 'verified', 'Verified'
    FAILED = 'failed', 'Failed'
    RATE_LIMITED = 'rate_limited', 'Rate Limited'
    REJECTED = 'rejected', 'Rejected'


class ExternalConnection(models.Model):
    """
    Represents an authorized external system integration (CMS, Git, Webhook)
    scoped strictly to a Project. Never stores plaintext credentials or exposes secrets.
    """
    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        related_name='external_connections',
        help_text='The project this external connection belongs to.'
    )
    system_type = models.CharField(
        max_length=30,
        choices=ExternalSystemType.choices,
        db_index=True,
        help_text='External system category: cms, git, or webhook.'
    )
    provider = models.CharField(
        max_length=60,
        help_text='Provider identifier (e.g. wordpress, shopify, github, gitlab, generic_webhook).'
    )
    name = models.CharField(
        max_length=200,
        help_text='Human-readable name for this external connection.'
    )
    status = models.CharField(
        max_length=30,
        choices=ExternalConnectionStatus.choices,
        default=ExternalConnectionStatus.TEST_STAGING,
        db_index=True,
        help_text='Connection operational status.'
    )
    configuration = models.JSONField(
        default=dict,
        blank=True,
        help_text='Non-secret configuration: baseUrl, allowlisted_domains, branch_prefix, repo name, etc.'
    )
    encrypted_credentials = models.TextField(
        blank=True,
        default='',
        help_text='AES-Fernet encrypted JSON string storing tokens/credentials.'
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'seo_external_connections'
        verbose_name = 'external connection'
        verbose_name_plural = 'external connections'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['project', 'system_type'], name='seo_extconn_proj_sys_idx'),
            models.Index(fields=['project', 'status'], name='seo_extconn_proj_stat_idx'),
        ]

    def __str__(self):
        return f"{self.name} ({self.get_system_type_display()} - {self.provider}) [#{self.project_id}]"

    def set_credentials(self, creds: Dict[str, Any]) -> None:
        """Securely encrypt dictionary of credentials using Fernet cipher."""
        import json
        from apps.seo.services.encryption import encrypt_token
        raw = json.dumps(creds)
        self.encrypted_credentials = encrypt_token(raw) or ''

    def get_credentials(self) -> Dict[str, Any]:
        """Decrypt credentials in memory only. Never log or return in API."""
        import json
        from apps.seo.services.encryption import decrypt_token
        if not self.encrypted_credentials:
            return {}
        try:
            raw = decrypt_token(self.encrypted_credentials)
            return json.loads(raw) if raw else {}
        except Exception:
            return {}

    def get_declared_capabilities(self) -> List[str]:
        """Discover declared capabilities for this connection's system type."""
        try:
            from apps.seo.services.external_adapters.registry import get_external_adapter_registry
            registry = get_external_adapter_registry()
            adapter = registry.get_adapter(self.system_type, self.provider)
            return adapter.get_capabilities()
        except Exception:
            return []

    def clean_for_api(self) -> Dict[str, Any]:
        """Return safe, non-sensitive dictionary strictly excluding credentials."""
        return {
            "id": self.id,
            "project_id": self.project_id,
            "system_type": self.system_type,
            "provider": self.provider,
            "name": self.name,
            "status": self.status,
            "configuration": self.configuration or {},
            "capabilities": self.get_declared_capabilities(),
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class ExternalOperationRecord(models.Model):
    """
    Persistent audit and execution record for an external system operation (Milestone 6.5).
    Guarantees deterministic idempotency, verification tracking, before/after states for rollback,
    and failure categorization.
    """
    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        related_name='external_operations',
        help_text='The project this external operation belongs to.'
    )
    connection = models.ForeignKey(
        ExternalConnection,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='operations',
        help_text='The external connection used for this operation.'
    )
    action = models.ForeignKey(
        SEOAction,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='external_operations',
        help_text='Optional SEOAction associated with this external operation.'
    )
    remediation_record = models.ForeignKey(
        RemediationRecord,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='external_operations',
        help_text='Optional RemediationRecord associated with this external operation.'
    )
    agent_run = models.ForeignKey(
        AgentRun,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='external_operations',
        help_text='The agent run executing or orchestrating this external operation.'
    )
    task_id = models.CharField(
        max_length=64,
        blank=True,
        default='',
        db_index=True,
        help_text='Correlation ID with AgentTask in DynamicTaskPlanner DAG.'
    )
    correlation_id = models.CharField(
        max_length=64,
        db_index=True,
        help_text='Unique request/trace correlation ID across agents and adapters.'
    )
    idempotency_key = models.CharField(
        max_length=64,
        db_index=True,
        help_text='SHA-256 fingerprint guaranteeing idempotency across workers and retries.'
    )
    system_type = models.CharField(
        max_length=30,
        db_index=True,
        help_text='External system type (cms, git, webhook).'
    )
    provider = models.CharField(
        max_length=60,
        help_text='Provider identifier (wordpress, shopify, github, generic_webhook, etc.).'
    )
    operation = models.CharField(
        max_length=100,
        db_index=True,
        help_text='Specific operation (e.g. read_metadata, update_metadata, create_branch, write_file, send_webhook).'
    )
    required_capability = models.CharField(
        max_length=100,
        help_text='Explicit capability required (e.g. CMS.UPDATE_METADATA, GIT.WRITE_FILE).'
    )
    target = models.CharField(
        max_length=500,
        help_text='Target URL, repo/branch, or endpoint.'
    )
    status = models.CharField(
        max_length=40,
        choices=ExternalOperationStatus.choices,
        default=ExternalOperationStatus.PENDING,
        db_index=True,
        help_text='Lifecycle status of the external operation.'
    )
    risk_level = models.CharField(
        max_length=20,
        default='low',
        db_index=True,
        help_text='Assessed risk level (low, medium, high, critical).'
    )
    is_autonomous = models.BooleanField(
        default=False,
        db_index=True,
        help_text='Whether operation was executed autonomously under policy.'
    )
    request_summary = models.JSONField(
        default=dict,
        blank=True,
        help_text='Sanitized summary of request parameters (secrets stripped).'
    )
    before_state = models.JSONField(
        default=dict,
        blank=True,
        help_text='Captured pre-operation state for verification and rollback.'
    )
    after_state = models.JSONField(
        default=dict,
        blank=True,
        help_text='Resulting state captured post-operation.'
    )
    response_summary = models.JSONField(
        default=dict,
        blank=True,
        help_text='Sanitized response metadata, status code, and duration.'
    )
    status_code = models.IntegerField(
        null=True,
        blank=True,
        help_text='HTTP or adapter execution status code.'
    )
    changed = models.BooleanField(
        default=False,
        help_text='Whether external system state was actually modified.'
    )
    error_category = models.CharField(
        max_length=60,
        blank=True,
        default='',
        db_index=True,
        help_text='Categorized error code on failure.'
    )
    error_message = models.TextField(
        blank=True,
        default='',
        help_text='Sanitized error description.'
    )
    retry_count = models.IntegerField(
        default=0,
        help_text='Number of bounded retries attempted.'
    )
    duration_ms = models.IntegerField(
        default=0,
        help_text='Operation duration in milliseconds.'
    )
    verification_status = models.CharField(
        max_length=30,
        default='pending',
        db_index=True,
        help_text='Post-operation empirical verification status: pending, verified, failed.'
    )
    verification_data = models.JSONField(
        default=dict,
        blank=True,
        help_text='Empirical verification evidence collected post-execution.'
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'seo_external_operations'
        verbose_name = 'external operation'
        verbose_name_plural = 'external operations'
        ordering = ['-created_at']
        unique_together = [('project', 'idempotency_key')]
        indexes = [
            models.Index(fields=['project', 'system_type'], name='seo_extop_proj_sys_idx'),
            models.Index(fields=['project', 'status'], name='seo_extop_proj_stat_idx'),
            models.Index(fields=['correlation_id'], name='seo_extop_corr_idx'),
            models.Index(fields=['project', '-created_at'], name='seo_extop_proj_created_idx'),
        ]

    def __str__(self):
        return f"ExternalOp #{self.id} [{self.system_type}:{self.operation}] on {self.target} ({self.status})"


# ==============================================================================
# MILESTONE 6, PHASE 6.6: LONG-TERM SEO STRATEGY MODELS
# ==============================================================================

class StrategicHorizon(models.TextChoices):
    SHORT_TERM = 'short_term', 'Short-Term (Days to Weeks)'
    MEDIUM_TERM = 'medium_term', 'Medium-Term (Weeks to Months)'
    LONG_TERM = 'long_term', 'Long-Term (Months to Year)'


class StrategicPriority(models.TextChoices):
    CRITICAL = 'critical', 'Critical'
    HIGH = 'high', 'High'
    MEDIUM = 'medium', 'Medium'
    LOW = 'low', 'Low'


class ObjectiveStatus(models.TextChoices):
    DRAFT = 'draft', 'Draft'
    ACTIVE = 'active', 'Active'
    AT_RISK = 'at_risk', 'At Risk'
    ACHIEVED = 'achieved', 'Achieved'
    PAUSED = 'paused', 'Paused'
    CANCELLED = 'cancelled', 'Cancelled'
    EXPIRED = 'expired', 'Expired'


class TargetDirection(models.TextChoices):
    INCREASING = 'increasing', 'Increasing (Higher is Better)'
    DECREASING = 'decreasing', 'Decreasing (Lower is Better, e.g. Rank)'


class InitiativeStatus(models.TextChoices):
    PLANNED = 'planned', 'Planned'
    ACTIVE = 'active', 'Active'
    AT_RISK = 'at_risk', 'At Risk'
    COMPLETED = 'completed', 'Completed'
    PAUSED = 'paused', 'Paused'
    CANCELLED = 'cancelled', 'Cancelled'


class StrategyStatus(models.TextChoices):
    DRAFT = 'draft', 'Draft'
    PROPOSED = 'proposed', 'Proposed (Awaiting HITL Approval)'
    ACTIVE = 'active', 'Active'
    SUPERSEDED = 'superseded', 'Superseded by Newer Version'
    PAUSED = 'paused', 'Paused'
    CANCELLED = 'cancelled', 'Cancelled'


class StrategyHealth(models.TextChoices):
    ON_TRACK = 'on_track', 'On Track'
    AT_RISK = 'at_risk', 'At Risk'
    OFF_TRACK = 'off_track', 'Off Track'
    NO_DATA = 'no_data', 'No Data'


class ReviewDecision(models.TextChoices):
    KEEP = 'keep', 'Keep Current Strategy'
    ADJUST = 'adjust', 'Adjust Initiatives / Objectives'
    PAUSE = 'pause', 'Pause Strategy Execution'
    COMPLETE = 'complete', 'Complete Strategy (All Goals Achieved)'
    REPLACE = 'replace', 'Replace with New Strategic Direction'


class ReviewApprovalStatus(models.TextChoices):
    NOT_REQUIRED = 'not_required', 'Not Required (Low Impact / Keep)'
    PENDING_APPROVAL = 'pending_approval', 'Pending Human Approval'
    APPROVED = 'approved', 'Approved'
    REJECTED = 'rejected', 'Rejected'


class ReviewRecordStatus(models.TextChoices):
    IN_PROGRESS = 'in_progress', 'In Progress'
    COMPLETED = 'completed', 'Completed'
    FAILED = 'failed', 'Failed'
    CANCELLED = 'cancelled', 'Cancelled'


class StrategicObjective(models.Model):
    """
    Persistent strategic SEO objective for a project over weeks/months.
    Tracks quantitative targets, direction, progress, priority, and horizons.
    """
    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        related_name='strategic_objectives',
        db_index=True,
        help_text='Associated project for this strategic objective.'
    )
    name = models.CharField(
        max_length=255,
        help_text='Descriptive title of the strategic objective.'
    )
    description = models.TextField(
        blank=True,
        default='',
        help_text='Detailed context, rationale, and strategic intent.'
    )
    metric = models.CharField(
        max_length=100,
        db_index=True,
        help_text='Target metric (e.g. organic_traffic, average_position, indexed_pages, technical_health_score, amharic_keyword_growth).'
    )
    baseline = models.FloatField(
        default=0.0,
        help_text='Initial baseline metric value at start of objective.'
    )
    target = models.FloatField(
        default=0.0,
        help_text='Target metric value to achieve.'
    )
    target_direction = models.CharField(
        max_length=20,
        choices=TargetDirection.choices,
        default=TargetDirection.INCREASING,
        help_text='Direction: increasing (higher is better) or decreasing (lower is better, e.g. rank).'
    )
    current_value = models.FloatField(
        default=0.0,
        help_text='Latest observed or computed metric value.'
    )
    start_date = models.DateTimeField(
        default=timezone.now,
        help_text='Objective inception date.'
    )
    target_date = models.DateTimeField(
        help_text='Target deadline for objective completion.'
    )
    priority = models.CharField(
        max_length=20,
        choices=StrategicPriority.choices,
        default=StrategicPriority.MEDIUM,
        db_index=True,
        help_text='Strategic priority rank.'
    )
    horizon = models.CharField(
        max_length=20,
        choices=StrategicHorizon.choices,
        default=StrategicHorizon.MEDIUM_TERM,
        db_index=True,
        help_text='Strategic horizon (short_term, medium_term, long_term).'
    )
    status = models.CharField(
        max_length=20,
        choices=ObjectiveStatus.choices,
        default=ObjectiveStatus.ACTIVE,
        db_index=True,
        help_text='Lifecycle status of the objective.'
    )
    progress = models.FloatField(
        default=0.0,
        help_text='Derived progress score normalized between 0.0 and 1.0 (or >1.0 if exceeded).'
    )
    evidence = models.JSONField(
        default=dict,
        blank=True,
        help_text='Supporting empirical evidence, baseline observations, and provenance references.'
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'seo_strategic_objectives'
        verbose_name = 'strategic objective'
        verbose_name_plural = 'strategic objectives'
        ordering = ['-priority', '-created_at']
        indexes = [
            models.Index(fields=['project', 'status'], name='seo_obj_proj_stat_idx'),
            models.Index(fields=['project', 'metric'], name='seo_obj_proj_met_idx'),
            models.Index(fields=['project', '-created_at'], name='seo_obj_proj_created_idx'),
        ]

    def __str__(self):
        return f"StrategicObjective #{self.id}: {self.name} ({self.status}, {round(self.progress*100, 1)}%)"


class LongTermSEOStrategy(models.Model):
    """
    Persistent, versioned SEO strategy document for a project over weeks/months.
    Preserves historical strategy versions, rationale, assumptions, risks, and expected outcomes.
    """
    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        related_name='long_term_strategies',
        db_index=True,
        help_text='Associated project for this strategy.'
    )
    title = models.CharField(
        max_length=255,
        help_text='Title of the long-term SEO strategy.'
    )
    version = models.PositiveIntegerField(
        default=1,
        db_index=True,
        help_text='Strategy version number (1, 2, 3...).'
    )
    status = models.CharField(
        max_length=20,
        choices=StrategyStatus.choices,
        default=StrategyStatus.ACTIVE,
        db_index=True,
        help_text='Status of this strategy version.'
    )
    health = models.CharField(
        max_length=20,
        choices=StrategyHealth.choices,
        default=StrategyHealth.ON_TRACK,
        db_index=True,
        help_text='Derived strategic health: on_track, at_risk, off_track, no_data.'
    )
    effective_from = models.DateTimeField(
        default=timezone.now,
        help_text='Start of the effective strategic period.'
    )
    effective_until = models.DateTimeField(
        null=True,
        blank=True,
        help_text='End of the effective strategic period.'
    )
    rationale = models.TextField(
        blank=True,
        default='',
        help_text='Structured strategic rationale explaining priorities and approach.'
    )
    assumptions = models.JSONField(
        default=list,
        blank=True,
        help_text='Explicit operating baseline assumptions.'
    )
    risks = models.JSONField(
        default=list,
        blank=True,
        help_text='Identified strategic risks and mitigation paths.'
    )
    expected_outcomes = models.JSONField(
        default=list,
        blank=True,
        help_text='Measurable expected outcomes over the planning horizon.'
    )
    evidence = models.JSONField(
        default=dict,
        blank=True,
        help_text='Supporting historical GSC, ranking, audit, and monitoring evidence.'
    )
    adjustment_reason = models.TextField(
        blank=True,
        default='',
        help_text='Explanation of why this strategy version was created or adjusted.'
    )
    previous_version = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='next_versions',
        help_text='Previous strategy version this version adjusted or superseded.'
    )
    created_by_agent = models.CharField(
        max_length=100,
        default='seo_strategist',
        help_text='Agent or system component that generated this strategy.'
    )
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        help_text='User who authorized this strategy version under HITL.'
    )
    approved_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text='Timestamp of human authorization.'
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'seo_long_term_strategies'
        verbose_name = 'long-term SEO strategy'
        verbose_name_plural = 'long-term SEO strategies'
        ordering = ['-version']
        unique_together = [('project', 'version')]
        indexes = [
            models.Index(fields=['project', 'status'], name='seo_strat_proj_stat_idx'),
            models.Index(fields=['project', 'version'], name='seo_strat_proj_ver_idx'),
            models.Index(fields=['project', '-created_at'], name='seo_strat_proj_created_idx'),
        ]

    def __str__(self):
        return f"SEOStrategy v{self.version} for Project #{self.project_id}: {self.title} ({self.status}, {self.health})"


class StrategicInitiative(models.Model):
    """
    A meaningful strategic body of work supporting one or more strategic objectives.
    Decomposes down into concrete tasks in the TaskPlanner DAG and remediation actions.
    """
    objective = models.ForeignKey(
        StrategicObjective,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='initiatives',
        help_text='Optional primary objective this initiative advances.'
    )
    strategy = models.ForeignKey(
        LongTermSEOStrategy,
        on_delete=models.CASCADE,
        related_name='initiatives',
        db_index=True,
        help_text='Associated long-term strategy.'
    )
    name = models.CharField(
        max_length=255,
        help_text='Title of the strategic initiative.'
    )
    description = models.TextField(
        blank=True,
        default='',
        help_text='Scope and methodology for this body of work.'
    )
    priority = models.CharField(
        max_length=20,
        choices=StrategicPriority.choices,
        default=StrategicPriority.MEDIUM,
        db_index=True,
        help_text='Execution priority.'
    )
    status = models.CharField(
        max_length=20,
        choices=InitiativeStatus.choices,
        default=InitiativeStatus.PLANNED,
        db_index=True,
        help_text='Lifecycle status of the initiative.'
    )
    horizon = models.CharField(
        max_length=20,
        choices=StrategicHorizon.choices,
        default=StrategicHorizon.MEDIUM_TERM,
        db_index=True,
        help_text='Strategic planning horizon.'
    )
    start_date = models.DateTimeField(
        default=timezone.now,
        help_text='Target initiative start date.'
    )
    target_date = models.DateTimeField(
        null=True,
        blank=True,
        help_text='Target completion date.'
    )
    progress = models.FloatField(
        default=0.0,
        help_text='Completion progress normalized between 0.0 and 1.0.'
    )
    risk_level = models.CharField(
        max_length=20,
        default='low',
        help_text='Assessed risk level: low, medium, high, critical.'
    )
    owner = models.CharField(
        max_length=100,
        default='seo_action_planner',
        help_text='Agent role or user responsible for executing this initiative.'
    )
    target_action_types = models.JSONField(
        default=list,
        blank=True,
        help_text='List of ActionType names targeted by this initiative (e.g. meta_tags, content, technical).'
    )
    action_plan = models.ForeignKey(
        SEOActionPlan,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='strategic_initiatives',
        help_text='Concrete execution action plan linked to this initiative.'
    )
    evidence = models.JSONField(
        default=dict,
        blank=True,
        help_text='Supporting evidence and progress audit trails.'
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'seo_strategic_initiatives'
        verbose_name = 'strategic initiative'
        verbose_name_plural = 'strategic initiatives'
        ordering = ['priority', '-created_at']
        indexes = [
            models.Index(fields=['strategy', 'status'], name='seo_init_strat_stat_idx'),
            models.Index(fields=['objective', 'status'], name='seo_init_obj_stat_idx'),
        ]

    def __str__(self):
        return f"Initiative #{self.id}: {self.name} [{self.priority}] ({self.status}, {round(self.progress*100, 1)}%)"


class StrategyReviewRecord(models.Model):
    """
    Audit record of an explicit, bounded strategic review cycle.
    Records evaluation summary, decision, proposed changes, HITL approval, and SHA-256 fingerprint.
    """
    strategy = models.ForeignKey(
        LongTermSEOStrategy,
        on_delete=models.CASCADE,
        related_name='reviews',
        db_index=True,
        help_text='Strategy being evaluated in this review cycle.'
    )
    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        related_name='strategy_reviews',
        db_index=True,
        help_text='Associated project.'
    )
    review_cycle = models.PositiveIntegerField(
        default=1,
        help_text='Sequential review cycle number.'
    )
    status = models.CharField(
        max_length=20,
        choices=ReviewRecordStatus.choices,
        default=ReviewRecordStatus.COMPLETED,
        db_index=True,
        help_text='Status of the review evaluation execution.'
    )
    evaluation_summary = models.JSONField(
        default=dict,
        help_text='Calculated objectives progress, initiative status, detected risks, and trends.'
    )
    decision = models.CharField(
        max_length=20,
        choices=ReviewDecision.choices,
        default=ReviewDecision.KEEP,
        db_index=True,
        help_text='Strategic decision reached (keep, adjust, pause, complete, replace).'
    )
    proposed_changes = models.JSONField(
        default=dict,
        blank=True,
        help_text='Proposed adjustments to strategy, objectives, or initiatives.'
    )
    approval_status = models.CharField(
        max_length=30,
        choices=ReviewApprovalStatus.choices,
        default=ReviewApprovalStatus.NOT_REQUIRED,
        db_index=True,
        help_text='HITL governance status: not_required, pending_approval, approved, rejected.'
    )
    fingerprint = models.CharField(
        max_length=64,
        db_index=True,
        help_text='Deterministic SHA-256 fingerprint of review parameters preventing duplicate execution.'
    )
    reviewed_at = models.DateTimeField(
        default=timezone.now,
        db_index=True,
        help_text='Timestamp when review was performed.'
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'seo_strategy_reviews'
        verbose_name = 'strategy review record'
        verbose_name_plural = 'strategy review records'
        ordering = ['-reviewed_at']
        indexes = [
            models.Index(fields=['project', 'fingerprint'], name='seo_rev_proj_fp_idx'),
            models.Index(fields=['strategy', 'review_cycle'], name='seo_rev_strat_cyc_idx'),
            models.Index(fields=['project', '-reviewed_at'], name='seo_rev_proj_rev_idx'),
        ]

    def __str__(self):
        return f"StrategyReview #{self.id} [Cycle {self.review_cycle}] -> {self.decision} ({self.approval_status})"


# ==============================================================================
# Milestone 6.7: Production Agent Platform Models
# ==============================================================================

class CircuitBreakerState(models.TextChoices):
    CLOSED = 'closed', 'Closed (Healthy)'
    OPEN = 'open', 'Open (Tripped)'
    HALF_OPEN = 'half_open', 'Half-Open (Testing Recovery)'


class PlatformCircuitBreaker(models.Model):
    """
    PlatformCircuitBreaker model tracking operational availability and failure thresholds
    for external systems (CMS, Git, Webhook, SERP, GSC, LLM) to protect downstream providers
    and fast-fail repeated dependent errors.
    """
    service_name = models.CharField(
        max_length=64,
        unique=True,
        db_index=True,
        help_text='Unique identifier of the external dependency or provider (e.g. cms, git, webhook, serp, gsc, llm).'
    )
    state = models.CharField(
        max_length=32,
        choices=CircuitBreakerState.choices,
        default=CircuitBreakerState.CLOSED,
        db_index=True,
        help_text='Current circuit state (closed=normal, open=fast-fail, half_open=probing).'
    )
    failure_count = models.PositiveIntegerField(
        default=0,
        help_text='Consecutive failure count within current window.'
    )
    failure_threshold = models.PositiveIntegerField(
        default=5,
        help_text='Number of consecutive failures before tripping to OPEN.'
    )
    cooldown_seconds = models.PositiveIntegerField(
        default=60,
        help_text='Seconds to wait in OPEN state before transitioning to HALF_OPEN probe.'
    )
    last_failure_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text='Timestamp of the most recent registered failure.'
    )
    last_state_change_at = models.DateTimeField(
        auto_now=True,
        help_text='Timestamp when circuit state last transitioned.'
    )
    opened_reason = models.TextField(
        blank=True,
        default='',
        help_text='Diagnostic summary of why the circuit breaker opened.'
    )
    trip_count = models.PositiveIntegerField(
        default=0,
        help_text='Lifetime count of times this circuit breaker has tripped to OPEN.'
    )
    metadata = models.JSONField(
        default=dict,
        blank=True,
        help_text='Provider-specific diagnostic state, error samples, or operator notes.'
    )

    class Meta:
        db_table = 'seo_platform_circuit_breakers'
        verbose_name = 'Platform circuit breaker'
        verbose_name_plural = 'Platform circuit breakers'
        ordering = ['service_name']

    def __str__(self):
        return f"CircuitBreaker [{self.service_name}]: {self.state.upper()} (failures: {self.failure_count}/{self.failure_threshold})"


class IdempotencyStatus(models.TextChoices):
    PENDING = 'pending', 'Pending'
    COMPLETED = 'completed', 'Completed'
    FAILED = 'failed', 'Failed'


class PlatformIdempotencyRecord(models.Model):
    """
    PlatformIdempotencyRecord model guaranteeing that repeated requests, worker retries,
    or duplicate triggers produce deterministic results without duplicate execution or mutation.
    """
    idempotency_key = models.CharField(
        max_length=255,
        unique=True,
        db_index=True,
        help_text='Unique idempotency key identifying the logical operation.'
    )
    scope = models.CharField(
        max_length=64,
        db_index=True,
        help_text='Classification scope (e.g. run_creation, task_execution, remediation, external_op).'
    )
    project = models.ForeignKey(
        Project,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name='idempotency_records',
        help_text='The project context for this idempotent operation, if scoped.'
    )
    status = models.CharField(
        max_length=32,
        choices=IdempotencyStatus.choices,
        default=IdempotencyStatus.PENDING,
        db_index=True,
        help_text='Execution state of the idempotent operation.'
    )
    request_hash = models.CharField(
        max_length=64,
        blank=True,
        default='',
        help_text='SHA-256 hash of payload/arguments to verify payload consistency on duplicate calls.'
    )
    response_data = models.JSONField(
        default=dict,
        blank=True,
        help_text='Cached structured response payload returned on subsequent duplicate requests.'
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    expires_at = models.DateTimeField(
        null=True,
        blank=True,
        db_index=True,
        help_text='Timestamp when idempotency record expires and can be compacted.'
    )

    class Meta:
        db_table = 'seo_platform_idempotency_records'
        verbose_name = 'Platform idempotency record'
        verbose_name_plural = 'Platform idempotency records'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['scope', 'status'], name='seo_idemp_scope_stat_idx'),
            models.Index(fields=['project', 'scope'], name='seo_idemp_proj_scope_idx'),
        ]

    def __str__(self):
        return f"Idempotency [{self.scope}]: {self.idempotency_key[:32]}... ({self.status})"


class OperatorAuditLog(models.Model):
    """
    OperatorAuditLog model maintaining an immutable audit log of administrative actions,
    lifecycle overrides, and operational interventions for complete governance compliance.
    """
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='operator_audit_logs',
        help_text='The authenticated operator or user who performed the administrative action.'
    )
    project = models.ForeignKey(
        Project,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name='operator_audit_logs',
        help_text='Project context if the operator action was project-scoped.'
    )
    action = models.CharField(
        max_length=128,
        db_index=True,
        help_text='Audited action identifier (e.g. run.retried, continuous_ops.paused, circuit_breaker.reset).'
    )
    target_type = models.CharField(
        max_length=64,
        db_index=True,
        help_text='Entity type affected by operator action (e.g. agent_run, circuit_breaker, continuous_operation).'
    )
    target_id = models.CharField(
        max_length=128,
        db_index=True,
        help_text='Identifier of the entity affected.'
    )
    rationale = models.TextField(
        blank=True,
        default='',
        help_text='Operator-provided justification for manual intervention.'
    )
    details = models.JSONField(
        default=dict,
        blank=True,
        help_text='Structured metadata describing state changes before and after operator action.'
    )
    ip_address = models.CharField(
        max_length=45,
        blank=True,
        default='',
        help_text='Client IP address from which operator request originated.'
    )
    timestamp = models.DateTimeField(
        default=timezone.now,
        db_index=True,
        help_text='Timestamp when administrative action was committed.'
    )

    class Meta:
        db_table = 'seo_operator_audit_logs'
        verbose_name = 'Operator audit log'
        verbose_name_plural = 'Operator audit logs'
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['action', '-timestamp'], name='seo_op_audit_act_ts_idx'),
            models.Index(fields=['target_type', 'target_id'], name='seo_op_audit_tgt_idx'),
            models.Index(fields=['project', '-timestamp'], name='seo_op_audit_proj_ts_idx'),
        ]

    def __str__(self):
        user_email = self.user.email if self.user else "System"
        return f"AuditLog [{self.action}] by {user_email} on {self.target_type}#{self.target_id} at {self.timestamp}"


class AlertSeverity(models.TextChoices):
    LOW = 'low', 'Low'
    MEDIUM = 'medium', 'Medium'
    HIGH = 'high', 'High'
    CRITICAL = 'critical', 'Critical'


class PlatformAlertRecord(models.Model):
    """
    PlatformAlertRecord model storing deterministic operational alerts triggered by
    runtime anomalies, high failure rates, circuit breaker trips, or backlog build-up.
    """
    alert_type = models.CharField(
        max_length=64,
        db_index=True,
        help_text='Classification of alert (e.g. high_failure_rate, circuit_breaker_opened, stale_run_detected).'
    )
    severity = models.CharField(
        max_length=32,
        choices=AlertSeverity.choices,
        default=AlertSeverity.MEDIUM,
        db_index=True,
        help_text='Alert priority level.'
    )
    project = models.ForeignKey(
        Project,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name='platform_alerts',
        help_text='Project context if alert is tenant-scoped.'
    )
    message = models.TextField(
        help_text='Human-readable description of alert condition.'
    )
    details = models.JSONField(
        default=dict,
        blank=True,
        help_text='Diagnostic runtime evidence and metrics at time of alert generation.'
    )
    is_resolved = models.BooleanField(
        default=False,
        db_index=True,
        help_text='Whether alert condition has been cleared or acknowledged.'
    )
    resolved_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text='Timestamp when alert was resolved.'
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = 'seo_platform_alerts'
        verbose_name = 'Platform alert record'
        verbose_name_plural = 'Platform alert records'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['alert_type', 'is_resolved'], name='seo_alert_type_res_idx'),
            models.Index(fields=['severity', 'is_resolved'], name='seo_alert_sev_res_idx'),
            models.Index(fields=['project', '-created_at'], name='seo_alert_proj_ts_idx'),
        ]

    def __str__(self):
        status_str = "RESOLVED" if self.is_resolved else "ACTIVE"
        return f"Alert [{self.severity.upper()} - {self.alert_type}] ({status_str}): {self.message[:60]}"

