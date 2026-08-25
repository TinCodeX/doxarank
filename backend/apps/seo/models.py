from django.db import models
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



