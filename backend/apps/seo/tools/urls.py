from django.urls import path
from .views import (
    MetaTagGeneratorView,
    SchemaGeneratorView,
    SocialPreviewGeneratorView,
    SEOToolsQuotaStatusView,
)

urlpatterns = [
    path('meta/', MetaTagGeneratorView.as_view(), name='seo-tools-meta'),
    path('schema/', SchemaGeneratorView.as_view(), name='seo-tools-schema'),
    path('social-preview/', SocialPreviewGeneratorView.as_view(), name='seo-tools-social'),
    path('status/', SEOToolsQuotaStatusView.as_view(), name='seo-tools-status'),
]
