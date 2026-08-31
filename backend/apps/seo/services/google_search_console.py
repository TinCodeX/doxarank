"""
Google Search Console API Service for DoxaRank.

Provides authenticated, multi-tenant access to Google Search Console API capabilities.
Encapsulates:
1. Retrieval of project SearchConsoleConnection and verification of tenant boundaries.
2. In-memory decryption of stored OAuth refresh tokens via Fernet symmetric encryption.
3. Automatic OAuth2 credential construction and access token refresh.
4. Robust validation of Search Analytics date ranges, dimensions, and limits.
5. Normalized internal data structures for agent consumption with zero credential leakage.
"""

import logging
import re
from datetime import datetime, date, timedelta
from typing import Dict, Any, List, Optional, Tuple

from django.conf import settings
from django.utils import timezone
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request as GoogleAuthRequest
import googleapiclient.discovery
from googleapiclient.errors import HttpError

from apps.projects.models import Project
from apps.seo.models import SearchConsoleConnection, SearchConsoleSyncStatus
from apps.seo.services.google_oauth import GoogleOAuthService

logger = logging.getLogger(__name__)

# Valid dimensions supported by GSC Search Analytics API
VALID_DIMENSIONS = {"query", "page", "country", "device", "date"}
MAX_GSC_LOOKBACK_DAYS = 486  # ~16 months Google Search Console maximum history


class SearchConsoleError(Exception):
    """Base exception for Search Console service errors."""
    pass


class SearchConsoleNotConnectedError(SearchConsoleError):
    """Raised when a project has no active Google Search Console connection."""
    pass


class SearchConsoleCredentialsError(SearchConsoleError):
    """Raised when Google Search Console OAuth credentials are missing, revoked, or invalid."""
    pass


class SearchConsoleValidationError(SearchConsoleError):
    """Raised when invalid arguments (dates, dimensions, limits) are supplied."""
    pass


class SearchConsoleApiError(SearchConsoleError):
    """Raised when the Google Search Console API returns an error."""
    pass


class GoogleSearchConsoleService:
    """
    Service for interacting with Google Search Console API on behalf of a Project.
    Guarantees strict tenant isolation, credential encapsulation, and safe output structures.
    """

    def __init__(self, project: Project):
        if not project or not project.id:
            raise SearchConsoleValidationError("Valid Project context is required.")
        self.project = project
        self._connection: Optional[SearchConsoleConnection] = None
        self._credentials: Optional[Credentials] = None
        self._client: Optional[Any] = None

    def get_connection(self) -> SearchConsoleConnection:
        """
        Retrieve and validate the active SearchConsoleConnection for this project.
        Enforces tenant isolation and credential validity.
        """
        if self._connection:
            return self._connection

        connection = SearchConsoleConnection.objects.filter(project=self.project).first()
        if not connection or not connection.is_connected:
            raise SearchConsoleNotConnectedError(
                f"Google Search Console is not connected for project '{self.project.name}'. "
                "Please connect Search Console in project settings first."
            )

        if not connection.has_valid_credentials():
            raise SearchConsoleCredentialsError(
                f"Google Search Console connection for project '{self.project.name}' has missing or revoked credentials. "
                "Please reconnect your Google account."
            )

        self._connection = connection
        return self._connection

    def get_credentials(self) -> Credentials:
        """
        Decrypt stored refresh token and construct auto-refreshing Google OAuth2 credentials.
        Never exposes the plaintext token outside this service.
        """
        if self._credentials and self._credentials.valid:
            return self._credentials

        connection = self.get_connection()
        raw_refresh_token = connection.get_refresh_token()
        if not raw_refresh_token:
            raise SearchConsoleCredentialsError("Decrypted OAuth refresh token is empty or unavailable.")

        try:
            oauth_config = GoogleOAuthService.get_oauth_config()
        except ValueError as exc:
            raise SearchConsoleCredentialsError(f"Server OAuth configuration error: {str(exc)}")

        credentials = Credentials(
            token=None,
            refresh_token=raw_refresh_token,
            token_uri=GoogleOAuthService.GOOGLE_TOKEN_URL,
            client_id=oauth_config['client_id'],
            client_secret=oauth_config['client_secret'],
            scopes=oauth_config['scopes']
        )

        # Refresh token to verify validity and obtain initial access token
        try:
            auth_request = GoogleAuthRequest()
            credentials.refresh(auth_request)
        except Exception as exc:
            logger.warning(
                f"[GoogleSearchConsoleService] Failed to refresh Google credentials for project #{self.project.id}: {exc}"
            )
            # Update connection error state safely
            connection.sync_status = SearchConsoleSyncStatus.FAILED
            connection.error_message = "Google authorization expired or revoked."
            connection.save(update_fields=['sync_status', 'error_message'])
            raise SearchConsoleCredentialsError(
                "Google authorization has expired or been revoked. Please reconnect Google Search Console."
            )

        self._credentials = credentials
        return credentials

    def get_client(self, credentials: Optional[Credentials] = None) -> Any:
        """
        Construct and return the Google Search Console API client instance.
        """
        if self._client:
            return self._client

        creds = credentials or self.get_credentials()
        try:
            client = googleapiclient.discovery.build(
                'searchconsole',
                'v1',
                credentials=creds,
                cache_discovery=False
            )
            self._client = client
            return client
        except Exception as exc:
            logger.error(f"[GoogleSearchConsoleService] Failed to build Search Console API client: {exc}")
            raise SearchConsoleApiError(f"Failed to initialize Google Search Console client: {str(exc)}")

    # =========================================================================
    # VALIDATION HELPERS
    # =========================================================================

    @staticmethod
    def validate_date_string(date_str: str, param_name: str = "date") -> date:
        """
        Validate that a date string is in YYYY-MM-DD format and represents a valid calendar date.
        """
        if not date_str or not isinstance(date_str, str):
            raise SearchConsoleValidationError(f"Parameter '{param_name}' must be a non-empty string in YYYY-MM-DD format.")

        trimmed = date_str.strip()
        if not re.match(r'^\d{4}-\d{2}-\d{2}$', trimmed):
            raise SearchConsoleValidationError(f"Parameter '{param_name}' ('{date_str}') is not in YYYY-MM-DD format.")

        try:
            return datetime.strptime(trimmed, '%Y-%m-%d').date()
        except ValueError:
            raise SearchConsoleValidationError(f"Parameter '{param_name}' ('{date_str}') is not a valid calendar date.")

    def validate_date_range(self, start_date_str: str, end_date_str: str) -> Tuple[str, str]:
        """
        Validate start_date and end_date range bounds for Google Search Console.
        Returns validated (start_date_str, end_date_str) tuple.
        """
        start_d = self.validate_date_string(start_date_str, "start_date")
        end_d = self.validate_date_string(end_date_str, "end_date")

        today = timezone.now().date()

        if start_d > end_d:
            raise SearchConsoleValidationError(
                f"start_date ({start_date_str}) cannot be after end_date ({end_date_str})."
            )

        if start_d > today:
            raise SearchConsoleValidationError(
                f"start_date ({start_date_str}) cannot be in the future."
            )

        earliest_allowed = today - timedelta(days=MAX_GSC_LOOKBACK_DAYS)
        if start_d < earliest_allowed:
            raise SearchConsoleValidationError(
                f"start_date ({start_date_str}) exceeds Google Search Console maximum historical range (~16 months)."
            )

        return start_d.strftime('%Y-%m-%d'), end_d.strftime('%Y-%m-%d')

    @staticmethod
    def validate_dimensions(dimensions: Optional[List[str]]) -> List[str]:
        """
        Validate requested dimensions against allowed Google Search Console dimensions.
        """
        if dimensions is None:
            return ["query"]

        if not isinstance(dimensions, (list, tuple)):
            raise SearchConsoleValidationError("dimensions must be a list of strings.")

        cleaned = []
        for dim in dimensions:
            if not isinstance(dim, str) or not dim.strip():
                continue
            d = dim.strip().lower()
            if d not in VALID_DIMENSIONS:
                raise SearchConsoleValidationError(
                    f"Invalid dimension '{dim}'. Allowed dimensions are: {sorted(list(VALID_DIMENSIONS))}."
                )
            if d not in cleaned:
                cleaned.append(d)

        return cleaned if cleaned else ["query"]

    # =========================================================================
    # CORE SEARCH ANALYTICS QUERIES
    # =========================================================================

    def query_search_analytics(
        self,
        start_date: str,
        end_date: str,
        dimensions: Optional[List[str]] = None,
        row_limit: int = 25,
        dimension_filter_groups: Optional[List[Dict[str, Any]]] = None,
        site_url: Optional[str] = None,
        client: Optional[Any] = None
    ) -> Dict[str, Any]:
        """
        Query live Google Search Console Search Analytics data.
        Returns normalized internal structured metrics with summary aggregates.
        """
        # 1. Validate inputs
        valid_start, valid_end = self.validate_date_range(start_date, end_date)
        valid_dims = self.validate_dimensions(dimensions)
        clamped_limit = min(max(1, int(row_limit)), 250)

        # 2. Resolve property URL
        connection = self.get_connection()
        property_url = (site_url.strip() if site_url and isinstance(site_url, str) else connection.property_url).strip()

        # 3. Construct API request body
        request_body: Dict[str, Any] = {
            "startDate": valid_start,
            "endDate": valid_end,
            "dimensions": valid_dims,
            "rowLimit": clamped_limit,
            "startRow": 0,
        }

        if dimension_filter_groups and isinstance(dimension_filter_groups, list):
            request_body["dimensionFilterGroups"] = dimension_filter_groups

        # 4. Execute API call
        gsc_client = client or self.get_client()
        try:
            api_response = gsc_client.searchanalytics().query(
                siteUrl=property_url,
                body=request_body
            ).execute()
        except HttpError as exc:
            safe_msg = self._sanitize_google_api_error(exc)
            logger.warning(f"[GoogleSearchConsoleService] Search Analytics API HttpError: {safe_msg}")
            raise SearchConsoleApiError(safe_msg)
        except Exception as exc:
            safe_msg = self._sanitize_error_message(str(exc))
            logger.error(f"[GoogleSearchConsoleService] Search Analytics API error: {safe_msg}")
            raise SearchConsoleApiError(f"Failed to query Search Console performance data: {safe_msg}")

        # 5. Normalize response
        raw_rows = api_response.get("rows", []) if isinstance(api_response, dict) else []
        normalized_rows = []
        total_clicks = 0
        total_impressions = 0
        sum_weighted_position = 0.0

        for row in raw_rows:
            clicks = int(row.get("clicks", 0))
            impressions = int(row.get("impressions", 0))
            ctr = float(row.get("ctr", 0.0))
            position = float(row.get("position", 0.0))
            keys = row.get("keys", [])

            row_item: Dict[str, Any] = {
                "clicks": clicks,
                "impressions": impressions,
                "ctr": round(ctr, 4),
                "ctr_percent": round(ctr * 100, 2),
                "position": round(position, 1),
            }

            # Map keys to dimension names
            for i, dim_name in enumerate(valid_dims):
                if i < len(keys):
                    row_item[dim_name] = keys[i]

            normalized_rows.append(row_item)
            total_clicks += clicks
            total_impressions += impressions
            sum_weighted_position += (position * impressions) if impressions > 0 else (position * clicks)

        avg_ctr_percent = round((total_clicks / total_impressions * 100), 2) if total_impressions > 0 else 0.0
        avg_position = round((sum_weighted_position / total_impressions), 1) if total_impressions > 0 else (
            round(sum(r["position"] for r in normalized_rows) / len(normalized_rows), 1) if normalized_rows else 0.0
        )

        return {
            "project_id": self.project.id,
            "property_url": property_url,
            "start_date": valid_start,
            "end_date": valid_end,
            "dimensions": valid_dims,
            "total_rows": len(normalized_rows),
            "rows": normalized_rows,
            "summary": {
                "total_clicks": total_clicks,
                "total_impressions": total_impressions,
                "average_ctr_percent": avg_ctr_percent,
                "average_position": avg_position,
            }
        }

    # =========================================================================
    # CONVENIENCE QUERY METHODS
    # =========================================================================

    def get_top_queries(
        self,
        start_date: str,
        end_date: str,
        limit: int = 20,
        page_filter: Optional[str] = None,
        client: Optional[Any] = None
    ) -> Dict[str, Any]:
        """
        Retrieve top performing organic search queries for the project.
        Supports optional filtering by landing page URL.
        """
        filter_groups = None
        if page_filter and isinstance(page_filter, str) and page_filter.strip():
            filter_groups = [{
                "filters": [{
                    "dimension": "page",
                    "operator": "contains",
                    "expression": page_filter.strip()
                }]
            }]

        data = self.query_search_analytics(
            start_date=start_date,
            end_date=end_date,
            dimensions=["query"],
            row_limit=min(max(1, limit), 100),
            dimension_filter_groups=filter_groups,
            client=client
        )

        # Sort queries by impressions descending, then clicks descending
        sorted_rows = sorted(
            data.get("rows", []),
            key=lambda r: (r.get("impressions", 0), r.get("clicks", 0)),
            reverse=True
        )

        return {
            "project_id": self.project.id,
            "property_url": data["property_url"],
            "start_date": data["start_date"],
            "end_date": data["end_date"],
            "page_filter": page_filter.strip() if page_filter else None,
            "returned_count": len(sorted_rows),
            "top_queries": sorted_rows,
            "summary": data["summary"]
        }

    def get_top_pages(
        self,
        start_date: str,
        end_date: str,
        limit: int = 20,
        query_filter: Optional[str] = None,
        client: Optional[Any] = None
    ) -> Dict[str, Any]:
        """
        Retrieve top landing pages ordered by search traffic.
        Supports optional filtering by search query.
        """
        filter_groups = None
        if query_filter and isinstance(query_filter, str) and query_filter.strip():
            filter_groups = [{
                "filters": [{
                    "dimension": "query",
                    "operator": "contains",
                    "expression": query_filter.strip()
                }]
            }]

        data = self.query_search_analytics(
            start_date=start_date,
            end_date=end_date,
            dimensions=["page"],
            row_limit=min(max(1, limit), 100),
            dimension_filter_groups=filter_groups,
            client=client
        )

        # Sort pages by clicks descending, then impressions descending
        sorted_rows = sorted(
            data.get("rows", []),
            key=lambda r: (r.get("clicks", 0), r.get("impressions", 0)),
            reverse=True
        )

        return {
            "project_id": self.project.id,
            "property_url": data["property_url"],
            "start_date": data["start_date"],
            "end_date": data["end_date"],
            "query_filter": query_filter.strip() if query_filter else None,
            "returned_count": len(sorted_rows),
            "top_pages": sorted_rows,
            "summary": data["summary"]
        }

    # =========================================================================
    # SANITIZATION HELPERS
    # =========================================================================

    @staticmethod
    def _sanitize_google_api_error(exc: HttpError) -> str:
        """
        Sanitize Google API HttpError to provide actionable diagnostic details
        without leaking credentials or raw request headers.
        """
        status_code = getattr(exc, 'resp', {}).status if hasattr(exc, 'resp') else None

        if status_code == 401:
            return "Google Search Console authorization has expired or is invalid. Please reconnect your account."
        elif status_code == 403:
            return (
                "Google Search Console permission denied. Verify that the connected Google account has "
                "permission to view this property."
            )
        elif status_code == 404:
            return "The requested Google Search Console property was not found in the connected Google account."
        elif status_code == 429:
            return "Google Search Console API quota exceeded or rate limit reached. Please try again later."
        else:
            return f"Google Search Console API returned error (HTTP {status_code or 'Unknown'}): {GoogleSearchConsoleService._sanitize_error_message(str(exc))}"

    @staticmethod
    def _sanitize_error_message(message: str) -> str:
        """Mask potential tokens or client secrets from error strings."""
        if not message:
            return ""
        clean = re.sub(r'1//[a-zA-Z0-9_\-\.]{15,}', '1//[REDACTED_REFRESH_TOKEN]', message)
        clean = re.sub(r'ya29\.[a-zA-Z0-9_\-\.]{15,}', 'ya29.[REDACTED_ACCESS_TOKEN]', clean)
        clean = re.sub(r'Bearer\s+[a-zA-Z0-9_\-\.]{8,}', 'Bearer [REDACTED]', clean, flags=re.IGNORECASE)
        return clean[:400]
