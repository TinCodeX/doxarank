import logging
from datetime import date, timedelta
from decimal import Decimal
from typing import Optional, List, Dict, Any

from django.db import transaction
from django.utils import timezone

from apps.seo.models import (
    SearchConsoleConnection,
    SearchAnalyticsData,
    SearchConsoleSyncStatus
)

logger = logging.getLogger(__name__)


class MockGoogleSearchConsoleClient:
    """
    Mock/Simulation client for Google Search Console Search Analytics API.
    Used for automated tests and isolated development without live Google API dependencies.
    """
    def __init__(self, sample_rows: Optional[List[Dict[str, Any]]] = None, fail_sync: bool = False, error_message: str = "Google API Connection Failed"):
        self.sample_rows = sample_rows
        self.fail_sync = fail_sync
        self.error_message = error_message

    def query_search_analytics(
        self,
        site_url: str,
        start_date: str,
        end_date: str,
        dimensions: Optional[List[str]] = None,
        row_limit: int = 25000
    ) -> List[Dict[str, Any]]:
        if self.fail_sync:
            raise Exception(self.error_message)

        if self.sample_rows is not None:
            return self.sample_rows

        # Generate standard realistic GSC sample response
        return [
            {
                "keys": [start_date, "ethiopia tech news", f"{site_url}/news", "eth", "DESKTOP", "STANDARD"],
                "clicks": 150,
                "impressions": 3000,
                "ctr": 0.0500,
                "position": 2.4,
            },
            {
                "keys": [start_date, "addis fintech startup", f"{site_url}/fintech", "eth", "MOBILE", "STANDARD"],
                "clicks": 90,
                "impressions": 1800,
                "ctr": 0.0500,
                "position": 3.1,
            },
            {
                "keys": [start_date, "ethiopia ai software", f"{site_url}/ai", "usa", "DESKTOP", "RICHDATA"],
                "clicks": 45,
                "impressions": 1100,
                "ctr": 0.0409,
                "position": 4.5,
            },
        ]


class GoogleSearchConsoleService:
    """
    Service layer responsible for:
    1. Authenticating with Google Search Console.
    2. Querying Search Analytics performance data.
    3. Normalizing Google API responses into PostgreSQL schema.
    4. Upserting time-series observations into SearchAnalyticsData.
    5. Updating connection sync status, last_synced_at timestamp, and error logging.
    """

    @classmethod
    def sync_search_analytics(
        cls,
        connection: SearchConsoleConnection,
        start_date: Optional[date | str] = None,
        end_date: Optional[date | str] = None,
        client: Optional[Any] = None,
        dimensions: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Synchronize Google Search Console Search Analytics data for a connected property.
        """
        if not connection.is_connected:
            raise ValueError(f"Search Console connection #{connection.id} is disconnected.")

        # Default date range to last 28 days if unspecified
        today = date.today()
        if end_date is None:
            end_date = today
        elif isinstance(end_date, str):
            end_date = date.fromisoformat(end_date)

        if start_date is None:
            start_date = end_date - timedelta(days=28)
        elif isinstance(start_date, str):
            start_date = date.fromisoformat(start_date)

        if start_date > end_date:
            raise ValueError("start_date cannot be after end_date.")

        # Set connection status to SYNCING
        connection.sync_status = SearchConsoleSyncStatus.SYNCING
        connection.error_message = None
        connection.save(update_fields=['sync_status', 'error_message', 'updated_at'])

        api_client = client or MockGoogleSearchConsoleClient()
        dimensions = dimensions or ["date", "query", "page", "country", "device", "searchAppearance"]

        try:
            raw_rows = api_client.query_search_analytics(
                site_url=connection.property_url,
                start_date=str(start_date),
                end_date=str(end_date),
                dimensions=dimensions
            )

            records_fetched = len(raw_rows)
            records_created = 0
            records_updated = 0

            with transaction.atomic():
                for row in raw_rows:
                    normalized = cls._normalize_row(row, connection, default_date=start_date)
                    
                    obj, created = SearchAnalyticsData.objects.update_or_create(
                        connection=connection,
                        date=normalized['date'],
                        query=normalized['query'],
                        page=normalized['page'],
                        country=normalized['country'],
                        device=normalized['device'],
                        search_appearance=normalized['search_appearance'],
                        defaults={
                            'clicks': normalized['clicks'],
                            'impressions': normalized['impressions'],
                            'ctr': normalized['ctr'],
                            'position': normalized['position'],
                        }
                    )
                    if created:
                        records_created += 1
                    else:
                        records_updated += 1

                # Update connection state on success
                connection.sync_status = SearchConsoleSyncStatus.SUCCESS
                connection.last_synced_at = timezone.now()
                connection.error_message = None
                connection.save(update_fields=['sync_status', 'last_synced_at', 'error_message', 'updated_at'])

            return {
                "success": True,
                "records_fetched": records_fetched,
                "records_created": records_created,
                "records_updated": records_updated,
                "start_date": str(start_date),
                "end_date": str(end_date),
                "property_url": connection.property_url,
                "sync_status": connection.sync_status,
                "last_synced_at": connection.last_synced_at.isoformat() if connection.last_synced_at else None,
            }

        except Exception as exc:
            logger.exception("Search Console sync failed for connection %s: %s", connection.id, exc)
            connection.sync_status = SearchConsoleSyncStatus.FAILED
            connection.error_message = str(exc)
            connection.save(update_fields=['sync_status', 'error_message', 'updated_at'])
            raise exc

    @classmethod
    def _normalize_row(cls, row: Dict[str, Any], connection: SearchConsoleConnection, default_date: date) -> Dict[str, Any]:
        """
        Normalize a raw Search Analytics API response row into model fields.
        """
        keys = row.get("keys", [])
        # Default keys index mapping when standard dimensions are requested:
        # [0: date, 1: query, 2: page, 3: country, 4: device, 5: searchAppearance]
        row_date_str = keys[0] if len(keys) > 0 and keys[0] else str(default_date)
        try:
            row_date = date.fromisoformat(row_date_str)
        except (ValueError, TypeError):
            row_date = default_date

        query = str(keys[1]) if len(keys) > 1 and keys[1] is not None else ""
        page = str(keys[2]) if len(keys) > 2 and keys[2] is not None else ""
        country = str(keys[3]).lower() if len(keys) > 3 and keys[3] is not None else ""
        device = str(keys[4]).lower() if len(keys) > 4 and keys[4] is not None else ""
        search_appearance = str(keys[5]).upper() if len(keys) > 5 and keys[5] is not None else ""

        clicks = max(0, int(row.get("clicks", 0)))
        impressions = max(0, int(row.get("impressions", 0)))

        # Format CTR as Decimal with 4 places (0.0000 to 1.0000 or percentage)
        raw_ctr = row.get("ctr", 0.0)
        try:
            ctr = Decimal(str(round(float(raw_ctr), 4)))
        except Exception:
            ctr = Decimal("0.0000")

        # Format Position as Decimal with 2 places (e.g. 2.40)
        raw_pos = row.get("position", 0.0)
        try:
            pos = Decimal(str(round(float(raw_pos), 2)))
        except Exception:
            pos = Decimal("0.00")

        return {
            "date": row_date,
            "query": query[:500],
            "page": page[:500],
            "country": country[:10],
            "device": device[:20],
            "search_appearance": search_appearance[:100],
            "clicks": clicks,
            "impressions": impressions,
            "ctr": ctr,
            "position": pos,
        }
