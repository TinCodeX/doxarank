from django.urls import path
from .views import (
    MetaTagGeneratorView,
    SchemaGeneratorView,
    SocialPreviewGeneratorView,
    RobotsToolView,
    SitemapToolView,
    HreflangToolView,
    SerpSnippetToolView,
    PageSpeedToolView,
    BrokenLinksToolView,
    AmharicNormalizerToolView,
    SEOToolsQuotaStatusView,
)

urlpatterns = [
    path('meta/', MetaTagGeneratorView.as_view(), name='seo-tools-meta'),
    path('schema/', SchemaGeneratorView.as_view(), name='seo-tools-schema'),
    path('social-preview/', SocialPreviewGeneratorView.as_view(), name='seo-tools-social'),
    path('robots/', RobotsToolView.as_view(), name='seo-tools-robots'),
    path('sitemap/', SitemapToolView.as_view(), name='seo-tools-sitemap'),
    path('hreflang/', HreflangToolView.as_view(), name='seo-tools-hreflang'),
    path('serp-snippet/', SerpSnippetToolView.as_view(), name='seo-tools-serp-snippet'),
    path('pagespeed/', PageSpeedToolView.as_view(), name='seo-tools-pagespeed'),
    path('broken-links/', BrokenLinksToolView.as_view(), name='seo-tools-broken-links'),
    path('amharic-normalizer/', AmharicNormalizerToolView.as_view(), name='seo-tools-amharic-normalizer'),
    path('status/', SEOToolsQuotaStatusView.as_view(), name='seo-tools-status'),
]
