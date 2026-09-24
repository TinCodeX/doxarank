from rest_framework import permissions
from .models import FeatureCode
from .services import PlanEntitlementService, UsageLimitService


def require_feature(feature_code: str):
    """
    Factory creating a DRF Permission class that verifies the user's active plan
    includes the specified feature entitlement.
    """
    class FeaturePermission(permissions.BasePermission):
        message = f"Feature '{feature_code}' requires an upgraded plan."

        def has_permission(self, request, view):
            if not request.user or not request.user.is_authenticated:
                return False
            # check_can_use_feature raises FeatureNotEntitledException on failure
            PlanEntitlementService.check_can_use_feature(request.user, feature_code)
            return True

    return FeaturePermission


# Pre-constructed standard feature permission classes
CanAccessBasicSEOTools = require_feature(FeatureCode.BASIC_SEO_TOOLS)
CanAccessRankTracking = require_feature(FeatureCode.RANK_TRACKING)
CanAccessTechnicalCrawler = require_feature(FeatureCode.TECHNICAL_CRAWLER)
CanAccessCompetitorSnapshots = require_feature(FeatureCode.COMPETITOR_SNAPSHOTS)
CanAccessWhiteLabelReports = require_feature(FeatureCode.WHITE_LABEL_REPORTS)
CanAccessGSC = require_feature(FeatureCode.GSC)
CanAccessGA4 = require_feature(FeatureCode.GA4)
CanAccessClarity = require_feature(FeatureCode.CLARITY)
CanAccessGTM = require_feature(FeatureCode.GTM)
