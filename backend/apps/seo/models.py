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

