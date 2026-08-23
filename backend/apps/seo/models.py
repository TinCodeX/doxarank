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
