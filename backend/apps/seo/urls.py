from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import KeywordViewSet

app_name = 'seo'

router = DefaultRouter()
router.register('keywords', KeywordViewSet, basename='keyword')

urlpatterns = [
    path('', include(router.urls)),
]
