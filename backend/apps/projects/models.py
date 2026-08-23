from django.db import models
from django.conf import settings


class Project(models.Model):
    """
    Project model representing a website tracked in DoxaRank.
    Owned by a single custom User (one-to-many relationship).
    """
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='projects',
        help_text='The user who owns and manages this SEO project.'
    )
    name = models.CharField(
        max_length=200,
        help_text='Display name for the website/project (e.g. "Addis Ababa News").'
    )
    website_url = models.URLField(
        max_length=500,
        help_text='The canonical website URL (e.g. "https://example.com").'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'projects_project'
        verbose_name = 'project'
        verbose_name_plural = 'projects'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.name} ({self.website_url})"
