from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import KeywordViewSet, KeywordRankingViewSet

app_name = 'seo'

router = DefaultRouter()
router.register('keywords', KeywordViewSet, basename='keyword')
router.register('rankings', KeywordRankingViewSet, basename='ranking')

urlpatterns = [
    path('', include(router.urls)),
]
