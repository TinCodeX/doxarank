from decimal import Decimal
from django.db.models import Sum, Avg, Count, Min, Max
from django.utils import timezone
from apps.projects.models import Project
from apps.seo.models import (
    Keyword, KeywordRanking, SiteAudit, AuditIssue, AuditStatus, IssueSeverity,
    SearchConsoleConnection, SearchAnalyticsData,
    SEOInsight, InsightSeverity, InsightStatus, InsightSource, InsightType
)


class CandidateInsight:
    """Helper data container for insights produced by rules before persistence."""
    def __init__(
        self,
        fingerprint: str,
        insight_type: str,
        severity: str,
        title: str,
        description: str,
        recommendation: str,
        source: str,
        related_keyword=None,
        related_url: str = '',
        metadata: dict = None
    ):
        self.fingerprint = fingerprint
        self.insight_type = insight_type
        self.severity = severity
        self.title = title
        self.description = description
        self.recommendation = recommendation
        self.source = source
        self.related_keyword = related_keyword
        self.related_url = related_url or ''
        self.metadata = metadata or {}


class SEOIntelligenceService:
    """
    Deterministic, rule-based intelligence service for DoxaRank.
    Analyzes existing project data across:
    - Tracked keyword ranking observations
    - Google Search Console performance analytics
    - Site audit crawl issues
    
    Generates structured, actionable SEO insights with idempotent deduplication.
    """

    def __init__(self, project: Project):
        self.project = project

    def analyze(self) -> dict:
        """
        Execute all deterministic intelligence rules for the project,
        deduplicate results, persist new and updated insights, and return summary metrics.
        """
        candidates: list[CandidateInsight] = []

        # 1. Ranking movement rules (Drop, Improvement, Page 2)
        candidates.extend(self._evaluate_ranking_rules())

        # 2. Google Search Console analytics rules (High Imp/Low CTR, Performance Declines)
        candidates.extend(self._evaluate_search_console_rules())

        # 3. Technical SEO Audit rules (Critical / Warning audit issues)
        candidates.extend(self._evaluate_technical_audit_rules())

        # Persist and deduplicate candidate insights
        created_count = 0
        updated_count = 0

        for cand in candidates:
            existing = SEOInsight.objects.filter(
                project=self.project,
                fingerprint=cand.fingerprint
            ).first()

            if existing:
                # Update attributes while preserving user workflow status if dismissed/resolved
                existing.insight_type = cand.insight_type
                existing.severity = cand.severity
                existing.title = cand.title
                existing.description = cand.description
                existing.recommendation = cand.recommendation
                existing.source = cand.source
                existing.related_keyword = cand.related_keyword
                existing.related_url = cand.related_url
                existing.metadata = cand.metadata
                existing.save(update_fields=[
                    'insight_type', 'severity', 'title', 'description',
                    'recommendation', 'source', 'related_keyword', 'related_url',
                    'metadata', 'updated_at'
                ])
                updated_count += 1
            else:
                SEOInsight.objects.create(
                    project=self.project,
                    fingerprint=cand.fingerprint,
                    insight_type=cand.insight_type,
                    severity=cand.severity,
                    title=cand.title,
                    description=cand.description,
                    recommendation=cand.recommendation,
                    status=InsightStatus.OPEN,
                    source=cand.source,
                    related_keyword=cand.related_keyword,
                    related_url=cand.related_url,
                    metadata=cand.metadata,
                    detected_at=timezone.now()
                )
                created_count += 1

        total_open = SEOInsight.objects.filter(
            project=self.project,
            status=InsightStatus.OPEN
        ).count()

        return {
            'created': created_count,
            'updated': updated_count,
            'resolved': 0,
            'total_open': total_open
        }

    # =========================================================================
    # Rule Evaluators
    # =========================================================================

    def _evaluate_ranking_rules(self) -> list[CandidateInsight]:
        """
        Evaluates ranking observations for project keywords:
        - Rule A: Ranking Drop (>= 3 position decline)
        - Rule B: Ranking Improvement (>= 3 position gain)
        - Rule C: Page Two Keyword (Current position 11-20)
        """
        candidates: list[CandidateInsight] = []
        keywords = Keyword.objects.filter(project=self.project)

        for kw in keywords:
            rankings = list(KeywordRanking.objects.filter(keyword=kw).order_by('-recorded_at')[:2])
            if not rankings:
                continue

            latest = rankings[0]
            latest_pos = latest.position

            # Rule C: Page Two Opportunity (Positions 11–20)
            if 11 <= latest_pos <= 20:
                candidates.append(CandidateInsight(
                    fingerprint=f"page_two_keyword:kw_{kw.id}",
                    insight_type=InsightType.PAGE_TWO_KEYWORD,
                    severity=InsightSeverity.OPPORTUNITY,
                    title=f'Page 2 Opportunity: "{kw.keyword}" at #{latest_pos}',
                    description=(
                        f'"{kw.keyword}" is ranking at #{latest_pos} on page 2. '
                        f'Keywords on page 2 represent immediate high-leverage opportunities to push into page 1.'
                    ),
                    recommendation=(
                        'Optimize on-page headers (H1/H2), enrich topical depth, build targeted internal links '
                        'from high-authority pages, and target search intent snippets.'
                    ),
                    source=InsightSource.RANKING,
                    related_keyword=kw,
                    related_url=latest.ranking_url or '',
                    metadata={
                        'keyword_id': kw.id,
                        'keyword': kw.keyword,
                        'current_position': latest_pos,
                        'ranking_url': latest.ranking_url or '',
                        'recorded_at': latest.recorded_at.isoformat()
                    }
                ))

            # Rules A & B: Requires at least 2 historical ranking observations
            if len(rankings) >= 2:
                prev = rankings[1]
                prev_pos = prev.position

                # Rule A: Ranking Drop
                if latest_pos > prev_pos and (latest_pos - prev_pos) >= 3:
                    drop = latest_pos - prev_pos
                    is_critical = (drop >= 10) or (prev_pos <= 10 and latest_pos > 20)
                    severity = InsightSeverity.CRITICAL if is_critical else InsightSeverity.WARNING

                    candidates.append(CandidateInsight(
                        fingerprint=f"ranking_drop:kw_{kw.id}",
                        insight_type=InsightType.RANKING_DROP,
                        severity=severity,
                        title=f'Ranking Drop for "{kw.keyword}" (-{drop} positions)',
                        description=(
                            f'Ranking for "{kw.keyword}" dropped {drop} positions '
                            f'from #{prev_pos} to #{latest_pos}.'
                        ),
                        recommendation=(
                            'Inspect recent landing page changes, evaluate competitor SERP enhancements, '
                            'verify search intent alignment, and check for lost backlinks or technical crawl issues.'
                        ),
                        source=InsightSource.RANKING,
                        related_keyword=kw,
                        related_url=latest.ranking_url or '',
                        metadata={
                            'keyword_id': kw.id,
                            'keyword': kw.keyword,
                            'previous_position': prev_pos,
                            'current_position': latest_pos,
                            'position_drop': drop,
                            'recorded_at': latest.recorded_at.isoformat()
                        }
                    ))

                # Rule B: Ranking Improvement
                elif latest_pos < prev_pos and (prev_pos - latest_pos) >= 3:
                    gain = prev_pos - latest_pos
                    severity = InsightSeverity.OPPORTUNITY if latest_pos <= 10 else InsightSeverity.INFO

                    candidates.append(CandidateInsight(
                        fingerprint=f"ranking_improvement:kw_{kw.id}",
                        insight_type=InsightType.RANKING_IMPROVEMENT,
                        severity=severity,
                        title=f'Ranking Improvement for "{kw.keyword}" (+{gain} positions)',
                        description=(
                            f'Ranking for "{kw.keyword}" improved {gain} positions '
                            f'from #{prev_pos} to #{latest_pos}.'
                        ),
                        recommendation=(
                            'Maintain ranking momentum: reinforce internal links, optimize title tag CTR, '
                            'and update supporting content regularly.'
                        ),
                        source=InsightSource.RANKING,
                        related_keyword=kw,
                        related_url=latest.ranking_url or '',
                        metadata={
                            'keyword_id': kw.id,
                            'keyword': kw.keyword,
                            'previous_position': prev_pos,
                            'current_position': latest_pos,
                            'position_gain': gain,
                            'recorded_at': latest.recorded_at.isoformat()
                        }
                    ))

        return candidates

    def _evaluate_search_console_rules(self) -> list[CandidateInsight]:
        """
        Evaluates Google Search Console performance data:
        - Rule D: High Impressions + Low CTR
        - Rule E: Declining GSC Performance (Clicks or Impressions drop >= 15%)
        """
        candidates: list[CandidateInsight] = []
        gsc_conn = SearchConsoleConnection.objects.filter(
            project=self.project,
            is_connected=True
        ).first()

        if not gsc_conn:
            return candidates

        analytics_qs = SearchAnalyticsData.objects.filter(connection=gsc_conn)
        if not analytics_qs.exists():
            return candidates

        # --- Rule D: High Impressions + Low CTR per query ---
        query_aggregates = analytics_qs.exclude(query='').values('query').annotate(
            total_impressions=Sum('impressions'),
            total_clicks=Sum('clicks'),
            avg_pos=Avg('position')
        ).filter(total_impressions__gte=50)

        for item in query_aggregates:
            imp = item['total_impressions']
            clk = item['total_clicks']
            avg_pos = float(item['avg_pos']) if item['avg_pos'] is not None else 0.0
            ctr = (clk / imp) if imp > 0 else 0.0

            # Low CTR threshold: < 3.0% (0.03) for queries with >= 50 impressions
            if ctr < 0.03:
                ctr_pct = round(ctr * 100, 2)
                q_name = item['query']
                candidates.append(CandidateInsight(
                    fingerprint=f"high_impressions_low_ctr:query_{q_name}",
                    insight_type=InsightType.HIGH_IMPRESSIONS_LOW_CTR,
                    severity=InsightSeverity.OPPORTUNITY,
                    title=f'High Impressions, Low CTR: "{q_name}"',
                    description=(
                        f'Query "{q_name}" generated {imp:,} search impressions but only '
                        f'{clk:,} clicks ({ctr_pct}% CTR) with an average position of #{avg_pos:.1f}.'
                    ),
                    recommendation=(
                        'Rewrite title tags and meta descriptions to include compelling value hooks, '
                        'target featured snippets, and ensure strong search intent alignment.'
                    ),
                    source=InsightSource.SEARCH_CONSOLE,
                    metadata={
                        'query': q_name,
                        'impressions': imp,
                        'clicks': clk,
                        'ctr_percent': ctr_pct,
                        'avg_position': round(avg_pos, 1)
                    }
                ))

        # --- Rule E: Period-over-Period Performance Decline ---
        date_stats = analytics_qs.aggregate(min_date=Min('date'), max_date=Max('date'))
        min_d = date_stats.get('min_date')
        max_d = date_stats.get('max_date')

        if min_d and max_d and min_d != max_d:
            total_days = (max_d - min_d).days
            if total_days >= 2:
                mid_point = min_d + timezone.timedelta(days=total_days // 2)

                prior_agg = analytics_qs.filter(date__lte=mid_point).aggregate(
                    clicks=Sum('clicks'),
                    impressions=Sum('impressions')
                )
                recent_agg = analytics_qs.filter(date__gt=mid_point).aggregate(
                    clicks=Sum('clicks'),
                    impressions=Sum('impressions')
                )

                p_clicks = prior_agg.get('clicks') or 0
                r_clicks = recent_agg.get('clicks') or 0
                p_imp = prior_agg.get('impressions') or 0
                r_imp = recent_agg.get('impressions') or 0

                # Check clicks decline (>= 15%)
                if p_clicks >= 10 and r_clicks < p_clicks:
                    clicks_drop_ratio = (p_clicks - r_clicks) / p_clicks
                    if clicks_drop_ratio >= 0.15:
                        drop_pct = round(clicks_drop_ratio * 100, 1)
                        severity = InsightSeverity.CRITICAL if drop_pct >= 30 else InsightSeverity.WARNING
                        candidates.append(CandidateInsight(
                            fingerprint='declining_clicks:gsc_summary',
                            insight_type=InsightType.DECLINING_CLICKS,
                            severity=severity,
                            title=f'Search Traffic Decline: Organic Clicks Down {drop_pct}%',
                            description=(
                                f'Total organic search clicks decreased from {p_clicks:,} to {r_clicks:,} '
                                f'({drop_pct}% decline) across observation periods.'
                            ),
                            recommendation=(
                                'Review top lost queries and pages in Google Search Console, inspect recent site changes, '
                                'and check for indexing issues or Google algorithmic updates.'
                            ),
                            source=InsightSource.SEARCH_CONSOLE,
                            metadata={
                                'metric': 'clicks',
                                'previous_clicks': p_clicks,
                                'recent_clicks': r_clicks,
                                'decline_percent': drop_pct
                            }
                        ))

                # Check impressions decline (>= 15%)
                if p_imp >= 50 and r_imp < p_imp:
                    imp_drop_ratio = (p_imp - r_imp) / p_imp
                    if imp_drop_ratio >= 0.15:
                        drop_pct = round(imp_drop_ratio * 100, 1)
                        candidates.append(CandidateInsight(
                            fingerprint='declining_impressions:gsc_summary',
                            insight_type=InsightType.DECLINING_IMPRESSIONS,
                            severity=InsightSeverity.WARNING,
                            title=f'Search Visibility Decline: Impressions Down {drop_pct}%',
                            description=(
                                f'Total search impressions dropped from {p_imp:,} to {r_imp:,} '
                                f'({drop_pct}% decrease) across observation periods.'
                            ),
                            recommendation=(
                                'Verify sitemaps and indexation status in Google Search Console, check for technical errors, '
                                'and assess query visibility trends.'
                            ),
                            source=InsightSource.SEARCH_CONSOLE,
                            metadata={
                                'metric': 'impressions',
                                'previous_impressions': p_imp,
                                'recent_impressions': r_imp,
                                'decline_percent': drop_pct
                            }
                        ))

        return candidates

    def _evaluate_technical_audit_rules(self) -> list[CandidateInsight]:
        """
        Evaluates unresolved critical and warning issues from the latest site audit:
        - Rule F: Technical SEO Issues
        """
        candidates: list[CandidateInsight] = []
        latest_audit = SiteAudit.objects.filter(
            project=self.project,
            status=AuditStatus.COMPLETED
        ).order_by('-created_at').first()

        if not latest_audit:
            return candidates

        issues = AuditIssue.objects.filter(
            audit=latest_audit,
            severity__in=[IssueSeverity.CRITICAL, IssueSeverity.WARNING]
        )

        for issue in issues:
            severity = InsightSeverity.CRITICAL if issue.severity == IssueSeverity.CRITICAL else InsightSeverity.WARNING
            fingerprint = f"tech_seo_issue:{issue.issue_type}:{issue.page_url or 'site_wide'}"

            candidates.append(CandidateInsight(
                fingerprint=fingerprint,
                insight_type=InsightType.TECHNICAL_SEO_ISSUE,
                severity=severity,
                title=f'Technical SEO Issue: {issue.title}',
                description=f'Site audit identified {issue.severity.upper()} issue: {issue.description}',
                recommendation=issue.recommendation or 'Resolve this technical SEO issue to improve crawlability and search ranking performance.',
                source=InsightSource.SITE_AUDIT,
                related_url=issue.page_url or '',
                metadata={
                    'audit_id': latest_audit.id,
                    'issue_id': issue.id,
                    'issue_type': issue.issue_type,
                    'issue_severity': issue.severity,
                    'page_url': issue.page_url or ''
                }
            ))

        return candidates
