from rest_framework import exceptions, status


class PlanLimitReachedException(exceptions.APIException):
    """
    Raised when a user attempts to create a resource (project, keyword, tool call)
    that exceeds the quota permitted by their active subscription plan.
    """
    status_code = status.HTTP_403_FORBIDDEN
    default_code = 'PLAN_LIMIT_REACHED'

    def __init__(self, resource: str, current: int, limit: int, plan_code: str, message: str = None):
        detail_msg = message or (
            f"You have reached the maximum allowed {resource} ({limit}) for your {plan_code} plan. "
            "Please upgrade your subscription to increase limits."
        )
        self.detail = {
            'code': 'PLAN_LIMIT_REACHED',
            'resource': resource,
            'current': current,
            'limit': limit,
            'plan': plan_code,
            'upgrade_required': True,
            'detail': detail_msg,
        }


class FeatureNotEntitledException(exceptions.APIException):
    """
    Raised when a user attempts to access a premium feature that is not included
    in their active subscription plan tier.
    """
    status_code = status.HTTP_403_FORBIDDEN
    default_code = 'FEATURE_NOT_ENTITLED'

    def __init__(self, feature: str, plan_code: str, message: str = None):
        detail_msg = message or (
            f"The '{feature}' feature is not included in your {plan_code} plan. "
            "Please upgrade your subscription to access this feature."
        )
        self.detail = {
            'code': 'FEATURE_NOT_ENTITLED',
            'feature': feature,
            'plan': plan_code,
            'upgrade_required': True,
            'detail': detail_msg,
        }
