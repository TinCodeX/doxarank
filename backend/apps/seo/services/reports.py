"""
White-Label SEO Report Generation Service for DoxaRank (FeatureCode.WHITE_LABEL_REPORTS).

Production-grade, server-side PDF reporting service strictly for Agency tier subscribers.
Collects and normalizes live project data across:
1. Project & Client Metadata (White-label branding)
2. Executive Summary (derived from factual observations)
3. Technical SEO Crawler Results (CrawlJob / CrawlPage)
4. Rank Tracking on google.com.et (Keyword / KeywordRanking history & movement)
5. Competitor SERP Snapshots & Visibility Comparison (Competitor / CompetitorSnapshot)
6. Actionable SEO Recommendations (SEORecommendation / Recommendation)
7. Deterministic Phased Action Plan (No LLM, rule-based prioritization)

White-label guarantee:
Generated PDF reports contain ZERO DoxaRank branding, logos, promotional text, or marketing language.
Supports client/company branding and website information exclusively.
"""

import os
import io
import html
import logging
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime

from django.conf import settings
from django.utils import timezone
from django.utils.text import slugify
from django.db.models import Q

from apps.projects.models import Project
from apps.seo.models import (
    SEOReport, ReportStatus,
    Keyword, KeywordRanking, RankingResultStatus,
    Competitor, CompetitorSnapshot,
    CrawlJob, CrawlJobStatus, CrawlPage,
    SEORecommendation, Recommendation, RecommendationStatus
)
from apps.subscriptions.services import PlanEntitlementService
from apps.subscriptions.models import FeatureCode

# ReportLab imports
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, KeepTogether, HRFlowable
)
from reportlab.pdfgen import canvas

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Numbered Canvas for Dynamic "Page X of Y" and Running Headers/Footers
# ---------------------------------------------------------------------------

class NumberedCanvas(canvas.Canvas):
    """
    Two-pass canvas that computes the total page count dynamically
    and draws client-branded running headers and footers with "Page X of Y".
    Guaranteed white-label: NO DoxaRank branding.
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_page_decorations(num_pages)
            super().showPage()
        super().save()

    def draw_page_decorations(self, page_count: int):
        self.saveState()
        self.setFont("Helvetica", 8)
        self.setFillColor(colors.HexColor('#64748B'))

        # Suppress running header on cover page (Page 1)
        if self._pageNumber > 1:
            header_text = getattr(self, 'report_client_label', 'SEO Performance & Audit Report')
            doc_title = getattr(self, 'report_title_label', 'Executive SEO Report')
            
            # Header top rule
            self.setStrokeColor(colors.HexColor('#E2E8F0'))
            self.setLineWidth(0.75)
            self.line(40, 755, 572, 755)
            
            # Running header text
            self.drawString(40, 760, header_text[:50])
            self.drawRightString(572, 760, doc_title[:45])

        # Running Footer on all pages
        self.setStrokeColor(colors.HexColor('#E2E8F0'))
        self.setLineWidth(0.75)
        self.line(40, 45, 572, 45)

        footer_left = "Confidential SEO Audit & Performance Report"
        footer_date = getattr(self, 'report_date_label', timezone.now().strftime('%Y-%m-%d'))
        page_str = f"Page {self._pageNumber} of {page_count}"

        self.drawString(40, 32, footer_left)
        self.drawCentredString(306, 32, f"Date: {footer_date}")
        self.drawRightString(572, 32, page_str)

        self.restoreState()


# ---------------------------------------------------------------------------
# Core SEO Report Service
# ---------------------------------------------------------------------------

class SEOReportService:
    """
    Centralized service for generating white-label SEO reports.
    """

    @classmethod
    def collect_report_context(cls, project: Project, client_name: str = '') -> Dict[str, Any]:
        """
        Collect and normalize factual project data across all SEO subsystems.
        Does NOT invent data: unavailable sections are explicitly flagged.
        """
        effective_client = client_name.strip() or project.name
        now = timezone.now()

        context: Dict[str, Any] = {
            'project_id': project.id,
            'project_name': project.name,
            'website_url': project.website_url,
            'client_name': effective_client,
            'report_date': now.strftime('%B %d, %Y'),
            'report_date_iso': now.strftime('%Y-%m-%d'),
            'reporting_period': 'Current Audit Snapshot',
        }

        # 1. Technical Crawler Findings
        latest_crawl = (
            CrawlJob.objects.filter(project=project, status=CrawlJobStatus.COMPLETED)
            .order_by('-completed_at')
            .first()
        )

        if latest_crawl:
            # Query up to 10 sample pages with issues
            issue_pages = (
                CrawlPage.objects.filter(crawl_job=latest_crawl)
                .filter(Q(is_broken=True) | Q(is_slow=True) | Q(h1_count=0) | Q(title__isnull=True) | Q(title=''))
                .order_by('depth', 'url')[:10]
            )
            sample_issues = []
            for p in issue_pages:
                problems = []
                if p.is_broken:
                    problems.append(f"HTTP {p.status_code}")
                if p.is_slow:
                    problems.append(f"Slow ({int(p.response_time_ms)}ms)")
                if not p.title:
                    problems.append("Missing Title")
                if p.h1_count == 0:
                    problems.append("Missing H1")
                if p.images_missing_alt_count > 0:
                    problems.append(f"{p.images_missing_alt_count} Missing Alt")
                
                sample_issues.append({
                    'url': p.url,
                    'status_code': p.status_code,
                    'response_time_ms': round(p.response_time_ms, 1),
                    'issues': ", ".join(problems) if problems else "None"
                })

            context['crawler'] = {
                'available': True,
                'crawl_id': latest_crawl.id,
                'completed_at': latest_crawl.completed_at.strftime('%Y-%m-%d %H:%M UTC') if latest_crawl.completed_at else 'N/A',
                'pages_crawled': latest_crawl.pages_crawled,
                'pages_discovered': latest_crawl.pages_discovered,
                'broken_links_count': latest_crawl.broken_links_count,
                'missing_titles_count': latest_crawl.missing_titles_count,
                'missing_descriptions_count': latest_crawl.missing_descriptions_count,
                'duplicate_titles_count': latest_crawl.duplicate_titles_count,
                'missing_h1_count': latest_crawl.missing_h1_count,
                'redirect_chains_count': latest_crawl.redirect_chains_count,
                'slow_pages_count': latest_crawl.slow_pages_count,
                'sample_issues': sample_issues,
            }
        else:
            context['crawler'] = {
                'available': False,
                'message': 'No completed technical crawl available for this project.'
            }

        # 2. Rank Tracking Findings
        keywords_qs = (
            Keyword.objects.filter(project=project, is_active=True)
            .prefetch_related('rankings')
            .order_by('keyword')
        )
        total_keywords = keywords_qs.count()

        if total_keywords > 0:
            found_count = 0
            not_found_count = 0
            top_3_count = 0
            top_10_count = 0
            top_50_count = 0
            keyword_items = []

            for kw in keywords_qs:
                # Latest and previous ranking observations
                recent_rankings = list(kw.rankings.order_by('-created_at')[:2])
                latest_rank = recent_rankings[0] if len(recent_rankings) > 0 else None
                prev_rank = recent_rankings[1] if len(recent_rankings) > 1 else None

                current_pos = latest_rank.position if latest_rank else None
                res_status = latest_rank.result_status if latest_rank else 'not_checked'
                rank_url = latest_rank.ranking_url if latest_rank else ''

                if current_pos is not None and res_status == RankingResultStatus.FOUND:
                    found_count += 1
                    if current_pos <= 3:
                        top_3_count += 1
                    if current_pos <= 10:
                        top_10_count += 1
                    if current_pos <= 50:
                        top_50_count += 1
                else:
                    not_found_count += 1

                # Movement calculation
                if latest_rank and prev_rank and latest_rank.position and prev_rank.position:
                    # Positive movement means rank improved (e.g. 5 -> 3 is +2)
                    diff = prev_rank.position - latest_rank.position
                    if diff > 0:
                        movement = f"+{diff}"
                    elif diff < 0:
                        movement = f"{diff}"
                    else:
                        movement = "="
                elif latest_rank and latest_rank.position:
                    movement = "New"
                else:
                    movement = "—"

                keyword_items.append({
                    'keyword': kw.keyword,
                    'search_domain': kw.search_domain,
                    'country_lang': f"{kw.country}/{kw.language}",
                    'device': kw.device.capitalize(),
                    'position': f"#{current_pos}" if current_pos else "> 100",
                    'movement': movement,
                    'url': rank_url or 'N/A',
                })

            context['rank_tracking'] = {
                'available': True,
                'total_keywords': total_keywords,
                'found_count': found_count,
                'not_found_count': not_found_count,
                'top_3_count': top_3_count,
                'top_10_count': top_10_count,
                'top_50_count': top_50_count,
                'keywords': keyword_items[:30],  # cap table display to 30 keywords
            }
        else:
            context['rank_tracking'] = {
                'available': False,
                'message': 'No tracked keywords configured for this project.'
            }

        # 3. Competitor Snapshots Findings
        competitors_qs = Competitor.objects.filter(project=project, is_active=True).order_by('name')
        comp_count = competitors_qs.count()

        if comp_count > 0:
            comp_list = [{'name': c.name, 'domain': c.domain} for c in competitors_qs]
            
            # Compare project vs competitors on shared keywords
            comparison_rows = []
            for kw in keywords_qs[:15]:
                latest_project_rank = kw.rankings.order_by('-created_at').first()
                proj_pos_str = f"#{latest_project_rank.position}" if (latest_project_rank and latest_project_rank.position) else "> 100"
                
                comp_positions = {}
                for comp in competitors_qs[:4]:  # limit to top 4 competitors for table layout
                    snap = (
                        CompetitorSnapshot.objects.filter(project=project, competitor=comp, keyword=kw)
                        .order_by('-recorded_at')
                        .first()
                    )
                    pos_str = f"#{snap.position}" if (snap and snap.position) else "> 100"
                    comp_positions[comp.name] = pos_str

                comparison_rows.append({
                    'keyword': kw.keyword,
                    'project_rank': proj_pos_str,
                    'competitor_ranks': comp_positions
                })

            context['competitors'] = {
                'available': True,
                'total_competitors': comp_count,
                'competitor_list': comp_list,
                'comparison': comparison_rows,
            }
        else:
            context['competitors'] = {
                'available': False,
                'message': 'No competitor domains configured for this project.'
            }

        # 4. SEO Recommendations
        recs_data = []
        # Check SEORecommendation first
        ai_recs = (
            SEORecommendation.objects.filter(project=project)
            .exclude(status=RecommendationStatus.DISMISSED)
            .select_related('insight')
            .order_by('-created_at')[:20]
        )
        for r in ai_recs:
            recs_data.append({
                'title': r.title,
                'category': r.get_recommendation_type_display() if hasattr(r, 'get_recommendation_type_display') else str(r.recommendation_type),
                'priority': r.priority.upper(),
                'severity': getattr(r.insight, 'severity', 'MEDIUM').upper(),
                'affected_target': r.affected_url or r.affected_keyword or 'Site-wide',
                'recommended_action': r.recommended_action,
                'impact': r.expected_impact or 'Improves SEO health',
            })

        # Fallback to Recommendation model if SEORecommendation has few
        if len(recs_data) < 5:
            proj_recs = (
                Recommendation.objects.filter(project=project)
                .exclude(status='dismissed')
                .order_by('-priority')[:15]
            )
            for pr in proj_recs:
                if not any(x['title'] == pr.title for x in recs_data):
                    recs_data.append({
                        'title': pr.title,
                        'category': pr.get_category_display() if hasattr(pr, 'get_category_display') else pr.category,
                        'priority': 'HIGH' if pr.priority >= 70 else 'MEDIUM' if pr.priority >= 40 else 'LOW',
                        'severity': pr.severity.upper(),
                        'affected_target': pr.affected_url or pr.affected_keyword or 'Site-wide',
                        'recommended_action': pr.recommended_action,
                        'impact': pr.description or 'SEO performance enhancement',
                    })

        context['recommendations'] = {
            'available': len(recs_data) > 0,
            'count': len(recs_data),
            'items': recs_data[:15],
            'message': 'No pending recommendations found.' if len(recs_data) == 0 else ''
        }

        # 5. Deterministic Phased Action Plan (Rule-based, NO LLM)
        phase_1_critical = []
        phase_2_onpage = []
        phase_3_growth = []

        # From crawler issues:
        if latest_crawl:
            if latest_crawl.broken_links_count > 0:
                phase_1_critical.append({
                    'action': f"Resolve {latest_crawl.broken_links_count} broken links (4xx/5xx HTTP errors)",
                    'impact': "Prevents search bots from encountering dead ends and preserves link equity."
                })
            if latest_crawl.missing_titles_count > 0:
                phase_1_critical.append({
                    'action': f"Add missing <title> tags across {latest_crawl.missing_titles_count} pages",
                    'impact': "Enables primary relevance indexing in Google search engine snippets."
                })
            if latest_crawl.missing_descriptions_count > 0:
                phase_2_onpage.append({
                    'action': f"Write engaging meta descriptions for {latest_crawl.missing_descriptions_count} pages",
                    'impact': "Improves organic search snippet CTR without requiring page copy changes."
                })
            if latest_crawl.missing_h1_count > 0:
                phase_2_onpage.append({
                    'action': f"Assign single semantic <h1> headings to {latest_crawl.missing_h1_count} pages",
                    'impact': "Clarifies primary topical relevance for search crawlers."
                })
            if latest_crawl.slow_pages_count > 0:
                phase_2_onpage.append({
                    'action': f"Optimize page speed for {latest_crawl.slow_pages_count} slow pages (>3s load time)",
                    'impact': "Improves Core Web Vitals and user conversion rates."
                })

        # From recommendations:
        for r in recs_data:
            item = {'action': r['recommended_action'], 'impact': r['impact']}
            if r['severity'] in ('CRITICAL', 'HIGH') or r['priority'] == 'HIGH':
                if len(phase_1_critical) < 4 and item not in phase_1_critical:
                    phase_1_critical.append(item)
            elif 'content' in r['category'].lower() or 'on_page' in r['category'].lower() or 'technical' in r['category'].lower():
                if len(phase_2_onpage) < 4 and item not in phase_2_onpage:
                    phase_2_onpage.append(item)
            else:
                if len(phase_3_growth) < 4 and item not in phase_3_growth:
                    phase_3_growth.append(item)

        # From rank tracking gaps:
        if total_keywords > 0 and context['rank_tracking']['not_found_count'] > 0:
            phase_3_growth.append({
                'action': f"Target {context['rank_tracking']['not_found_count']} tracked keywords not currently in Top 100",
                'impact': "Build dedicated content clusters to capture organic search share on Google Ethiopia."
            })

        context['action_plan'] = {
            'phase_1_critical': phase_1_critical or [{'action': 'No immediate critical issues detected. Maintain regular crawl monitoring.', 'impact': 'System health preserved.'}],
            'phase_2_onpage': phase_2_onpage or [{'action': 'Review and refresh on-page keyword density and header tags.', 'impact': 'Consistent snippet relevance.'}],
            'phase_3_growth': phase_3_growth or [{'action': 'Expand keyword portfolio and benchmark against emerging competitor queries.', 'impact': 'Long-term organic growth.'}],
        }

        # 6. Executive Summary Synthesizer
        key_findings = []
        if latest_crawl:
            total_p = latest_crawl.pages_crawled
            broken = latest_crawl.broken_links_count
            key_findings.append(f"Technical site audit crawled {total_p} pages with {broken} broken links detected.")
        if total_keywords > 0:
            top_10 = context['rank_tracking']['top_10_count']
            key_findings.append(f"Rank tracking monitors {total_keywords} queries on google.com.et ({top_10} currently in Top 10).")
        if comp_count > 0:
            key_findings.append(f"Competitive intelligence actively benchmarks {comp_count} industry competitors.")
        if len(recs_data) > 0:
            key_findings.append(f"{len(recs_data)} prioritized optimization recommendations identified.")

        if not key_findings:
            key_findings.append("Initial baseline audit established. Configure additional keywords and crawler jobs for deeper insights.")

        # Overall Status
        has_critical = (latest_crawl and latest_crawl.broken_links_count > 0) or any(r['severity'] == 'CRITICAL' for r in recs_data)
        if has_critical:
            overall_status = "Attention Required"
            status_color = "#DC2626"
        elif total_keywords > 0 and context['rank_tracking']['top_10_count'] > 0:
            overall_status = "Performing Well"
            status_color = "#059669"
        else:
            overall_status = "Baseline Established"
            status_color = "#2563EB"

        context['executive_summary'] = {
            'overall_status': overall_status,
            'status_color': status_color,
            'key_findings': key_findings,
        }

        return context

    @classmethod
    def generate_pdf(cls, report: SEOReport, context: Dict[str, Any]) -> Tuple[str, int]:
        """
        Render a beautiful, multi-page white-label PDF report using ReportLab.
        Returns (relative_file_path, file_size_bytes).
        """
        # Ensure media directory exists
        reports_dir = os.path.join(settings.MEDIA_ROOT, 'reports', f"project_{report.project.id}")
        os.makedirs(reports_dir, exist_ok=True)

        safe_slug = slugify(report.project.name)[:30] or "project"
        filename = f"report_{report.id}_{safe_slug}.pdf"
        full_filepath = os.path.join(reports_dir, filename)
        relative_path = os.path.relpath(full_filepath, settings.MEDIA_ROOT).replace('\\', '/')

        # Setup Document with 40pt margins
        doc = SimpleDocTemplate(
            full_filepath,
            pagesize=letter,
            leftMargin=40,
            rightMargin=40,
            topMargin=45,
            bottomMargin=55,
            title=report.title,
            author=report.client_name or report.project.name,
            subject="White-Label SEO Performance & Audit Report"
        )

        styles = getSampleStyleSheet()

        # Custom Corporate Styles (Zero DoxaRank branding)
        primary_color = colors.HexColor('#0F172A')
        accent_color = colors.HexColor('#1E3A8A')
        text_dark = colors.HexColor('#1E293B')
        text_muted = colors.HexColor('#64748B')
        card_bg = colors.HexColor('#F8FAFC')
        border_color = colors.HexColor('#E2E8F0')

        title_style = ParagraphStyle(
            'CoverTitle',
            parent=styles['Normal'],
            fontName='Helvetica-Bold',
            fontSize=26,
            leading=32,
            textColor=primary_color,
            spaceAfter=12
        )
        subtitle_style = ParagraphStyle(
            'CoverSubtitle',
            parent=styles['Normal'],
            fontName='Helvetica',
            fontSize=13,
            leading=18,
            textColor=accent_color,
            spaceAfter=24
        )
        h1_style = ParagraphStyle(
            'SectionH1',
            parent=styles['Normal'],
            fontName='Helvetica-Bold',
            fontSize=16,
            leading=20,
            textColor=primary_color,
            spaceBefore=14,
            spaceAfter=8,
            keepWithNext=True
        )
        h2_style = ParagraphStyle(
            'SectionH2',
            parent=styles['Normal'],
            fontName='Helvetica-Bold',
            fontSize=12,
            leading=16,
            textColor=accent_color,
            spaceBefore=10,
            spaceAfter=6,
            keepWithNext=True
        )
        body_style = ParagraphStyle(
            'ReportBody',
            parent=styles['Normal'],
            fontName='Helvetica',
            fontSize=9.5,
            leading=14,
            textColor=text_dark,
            spaceAfter=6
        )
        body_bold = ParagraphStyle(
            'ReportBodyBold',
            parent=body_style,
            fontName='Helvetica-Bold',
        )
        muted_style = ParagraphStyle(
            'ReportMuted',
            parent=styles['Normal'],
            fontName='Helvetica',
            fontSize=8.5,
            leading=12,
            textColor=text_muted
        )
        table_cell = ParagraphStyle(
            'TableCell',
            parent=styles['Normal'],
            fontName='Helvetica',
            fontSize=8.5,
            leading=11,
            textColor=text_dark
        )
        table_cell_bold = ParagraphStyle(
            'TableCellBold',
            parent=table_cell,
            fontName='Helvetica-Bold',
        )
        table_header = ParagraphStyle(
            'TableHeader',
            parent=styles['Normal'],
            fontName='Helvetica-Bold',
            fontSize=8.5,
            leading=11,
            textColor=colors.white
        )

        story: List[Any] = []

        # =====================================================================
        # 1. COVER PAGE
        # =====================================================================
        story.append(Spacer(1, 0.4 * inch))
        
        # Decorative top accent band
        band_table = Table([['']], colWidths=[532], rowHeights=[6])
        band_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), accent_color),
            ('TOPPADDING', (0, 0), (-1, -1), 0),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
        ]))
        story.append(band_table)
        story.append(Spacer(1, 0.4 * inch))

        # Title & Subtitle
        safe_title = html.escape(report.title)
        safe_project_name = html.escape(context['project_name'])
        safe_client_name = html.escape(context['client_name'])
        safe_url = html.escape(context['website_url'])

        story.append(Paragraph(safe_title, title_style))
        story.append(Paragraph(f"SEO Performance & Technical Audit · {safe_project_name}", subtitle_style))
        story.append(Spacer(1, 0.5 * inch))

        # Metadata Card
        meta_data = [
            [Paragraph("Prepared For:", table_cell_bold), Paragraph(safe_client_name, table_cell)],
            [Paragraph("Website Target:", table_cell_bold), Paragraph(safe_url, table_cell)],
            [Paragraph("Report Date:", table_cell_bold), Paragraph(context['report_date'], table_cell)],
            [Paragraph("Reporting Period:", table_cell_bold), Paragraph(context['reporting_period'], table_cell)],
            [Paragraph("Audit Scope:", table_cell_bold), Paragraph("Technical Crawl, Google Ethiopia Rank Tracker, Competitor Benchmarking, Action Plan", table_cell)],
        ]
        meta_table = Table(meta_data, colWidths=[130, 402])
        meta_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), card_bg),
            ('BOX', (0, 0), (-1, -1), 1, border_color),
            ('INNERGRID', (0, 0), (-1, -1), 0.5, border_color),
            ('TOPPADDING', (0, 0), (-1, -1), 8),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
            ('LEFTPADDING', (0, 0), (-1, -1), 12),
            ('RIGHTPADDING', (0, 0), (-1, -1), 12),
        ]))
        story.append(meta_table)

        story.append(Spacer(1, 1.2 * inch))

        # Executive Notice Box
        exec_notice = [
            [Paragraph("<b>CONFIDENTIALITY NOTICE & CLIENT BRIEF</b>", table_cell_bold)],
            [Paragraph(
                f"This document is an unbranded executive SEO audit prepared specifically for <b>{safe_client_name}</b>. "
                "The findings, metrics, and recommendations contained herein are derived from automated technical analysis "
                "and live search engine results on Google Ethiopia (google.com.et). "
                "All findings reflect the state of the domain at the time of report compilation.",
                muted_style
            )]
        ]
        notice_table = Table(exec_notice, colWidths=[532])
        notice_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#F1F5F9')),
            ('BOX', (0, 0), (-1, -1), 1, colors.HexColor('#CBD5E1')),
            ('TOPPADDING', (0, 0), (-1, -1), 10),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
            ('LEFTPADDING', (0, 0), (-1, -1), 14),
            ('RIGHTPADDING', (0, 0), (-1, -1), 14),
        ]))
        story.append(notice_table)

        # Page break after cover
        story.append(PageBreak())

        # =====================================================================
        # 2. EXECUTIVE SUMMARY
        # =====================================================================
        story.append(Paragraph("1. Executive Summary", h1_style))
        story.append(HRFlowable(width="100%", thickness=1, color=border_color, spaceAfter=10))

        exec_summary = context['executive_summary']
        status_hex = exec_summary['status_color']
        status_label = exec_summary['overall_status']

        status_box = [
            [
                Paragraph("<b>Audit Status:</b>", table_cell_bold),
                Paragraph(f"<font color='{status_hex}'><b>{status_label}</b></font>", table_cell_bold),
                Paragraph("<b>Domain:</b>", table_cell_bold),
                Paragraph(safe_url, table_cell)
            ]
        ]
        status_table = Table(status_box, colWidths=[90, 160, 60, 222])
        status_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), card_bg),
            ('BOX', (0, 0), (-1, -1), 1, border_color),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('TOPPADDING', (0, 0), (-1, -1), 8),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
            ('LEFTPADDING', (0, 0), (-1, -1), 10),
            ('RIGHTPADDING', (0, 0), (-1, -1), 10),
        ]))
        story.append(status_table)
        story.append(Spacer(1, 10))

        story.append(Paragraph("<b>Key Audit Findings:</b>", h2_style))
        for finding in exec_summary['key_findings']:
            bullet_html = f"• {html.escape(finding)}"
            story.append(Paragraph(bullet_html, body_style))
        story.append(Spacer(1, 12))

        # =====================================================================
        # 3. TECHNICAL SEO CRAWLER FINDINGS
        # =====================================================================
        story.append(Paragraph("2. Technical SEO Audit", h1_style))
        story.append(HRFlowable(width="100%", thickness=1, color=border_color, spaceAfter=10))

        crawler = context['crawler']
        if crawler['available']:
            # Technical Metrics Summary Grid
            metric_data = [
                [
                    Paragraph("<b>Pages Crawled</b>", table_cell_bold),
                    Paragraph(str(crawler['pages_crawled']), table_cell),
                    Paragraph("<b>Broken Links (4xx/5xx)</b>", table_cell_bold),
                    Paragraph(f"<font color='#DC2626'><b>{crawler['broken_links_count']}</b></font>" if crawler['broken_links_count'] > 0 else "0", table_cell)
                ],
                [
                    Paragraph("<b>Missing Titles</b>", table_cell_bold),
                    Paragraph(f"<font color='#DC2626'><b>{crawler['missing_titles_count']}</b></font>" if crawler['missing_titles_count'] > 0 else "0", table_cell),
                    Paragraph("<b>Duplicate Titles</b>", table_cell_bold),
                    Paragraph(str(crawler['duplicate_titles_count']), table_cell)
                ],
                [
                    Paragraph("<b>Missing Meta Descr.</b>", table_cell_bold),
                    Paragraph(str(crawler['missing_descriptions_count']), table_cell),
                    Paragraph("<b>Missing H1 Headings</b>", table_cell_bold),
                    Paragraph(str(crawler['missing_h1_count']), table_cell)
                ],
                [
                    Paragraph("<b>Redirect Chains</b>", table_cell_bold),
                    Paragraph(str(crawler['redirect_chains_count']), table_cell),
                    Paragraph("<b>Slow Pages (>3s)</b>", table_cell_bold),
                    Paragraph(str(crawler['slow_pages_count']), table_cell)
                ],
            ]
            tech_table = Table(metric_data, colWidths=[150, 116, 150, 116])
            tech_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, -1), card_bg),
                ('BOX', (0, 0), (-1, -1), 1, border_color),
                ('INNERGRID', (0, 0), (-1, -1), 0.5, border_color),
                ('TOPPADDING', (0, 0), (-1, -1), 6),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
                ('LEFTPADDING', (0, 0), (-1, -1), 8),
                ('RIGHTPADDING', (0, 0), (-1, -1), 8),
            ]))
            story.append(tech_table)
            story.append(Spacer(1, 10))

            # Sample Technical Issues Table
            if crawler.get('sample_issues'):
                story.append(Paragraph("<b>Notable Crawl Findings (Sampled URLs):</b>", h2_style))
                sample_headers = [
                    Paragraph("URL Path", table_header),
                    Paragraph("HTTP", table_header),
                    Paragraph("Load Time", table_header),
                    Paragraph("Detected Issues", table_header)
                ]
                sample_rows = [sample_headers]
                for si in crawler['sample_issues'][:8]:
                    path_str = si['url'].replace('https://', '').replace('http://', '')
                    sample_rows.append([
                        Paragraph(html.escape(path_str[:42]), table_cell),
                        Paragraph(str(si['status_code']), table_cell),
                        Paragraph(f"{si['response_time_ms']}ms", table_cell),
                        Paragraph(html.escape(si['issues'][:45]), table_cell)
                    ])

                issues_tbl = Table(sample_rows, colWidths=[200, 45, 65, 222])
                issues_tbl.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (-1, 0), primary_color),
                    ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, card_bg]),
                    ('BOX', (0, 0), (-1, -1), 1, border_color),
                    ('INNERGRID', (0, 0), (-1, -1), 0.5, border_color),
                    ('TOPPADDING', (0, 0), (-1, -1), 5),
                    ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
                    ('LEFTPADDING', (0, 0), (-1, -1), 6),
                    ('RIGHTPADDING', (0, 0), (-1, -1), 6),
                ]))
                story.append(issues_tbl)
        else:
            story.append(Paragraph(crawler['message'], muted_style))

        story.append(Spacer(1, 14))

        # =====================================================================
        # 4. RANK TRACKING (google.com.et)
        # =====================================================================
        story.append(Paragraph("3. Search Engine Rank Tracking (google.com.et)", h1_style))
        story.append(HRFlowable(width="100%", thickness=1, color=border_color, spaceAfter=10))

        rt = context['rank_tracking']
        if rt['available']:
            # Rankings summary row
            rank_summary_data = [
                [
                    Paragraph("<b>Tracked Keywords</b>", table_cell_bold),
                    Paragraph(str(rt['total_keywords']), table_cell),
                    Paragraph("<b>Top 3 Positions</b>", table_cell_bold),
                    Paragraph(f"<font color='#059669'><b>{rt['top_3_count']}</b></font>", table_cell),
                    Paragraph("<b>Top 10 Positions</b>", table_cell_bold),
                    Paragraph(f"<font color='#2563EB'><b>{rt['top_10_count']}</b></font>", table_cell),
                    Paragraph("<b>Not Found (>100)</b>", table_cell_bold),
                    Paragraph(str(rt['not_found_count']), table_cell),
                ]
            ]
            rt_sum_table = Table(rank_summary_data, colWidths=[90, 43, 90, 43, 90, 43, 90, 43])
            rt_sum_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, -1), card_bg),
                ('BOX', (0, 0), (-1, -1), 1, border_color),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('TOPPADDING', (0, 0), (-1, -1), 6),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
                ('LEFTPADDING', (0, 0), (-1, -1), 4),
                ('RIGHTPADDING', (0, 0), (-1, -1), 4),
            ]))
            story.append(rt_sum_table)
            story.append(Spacer(1, 10))

            # Keywords detail table
            kw_headers = [
                Paragraph("Target Search Keyword", table_header),
                Paragraph("Market / Device", table_header),
                Paragraph("Position", table_header),
                Paragraph("Movement", table_header),
                Paragraph("Ranking Landing URL", table_header)
            ]
            kw_rows = [kw_headers]
            for kw_item in rt['keywords'][:20]:
                url_display = kw_item['url'].replace('https://', '').replace('http://', '')
                kw_rows.append([
                    Paragraph(html.escape(kw_item['keyword'][:32]), table_cell_bold),
                    Paragraph(f"{kw_item['country_lang']} · {kw_item['device']}", table_cell),
                    Paragraph(kw_item['position'], table_cell),
                    Paragraph(kw_item['movement'], table_cell),
                    Paragraph(html.escape(url_display[:38]), table_cell)
                ])

            kw_table = Table(kw_rows, colWidths=[150, 95, 55, 55, 177])
            kw_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), primary_color),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, card_bg]),
                ('BOX', (0, 0), (-1, -1), 1, border_color),
                ('INNERGRID', (0, 0), (-1, -1), 0.5, border_color),
                ('TOPPADDING', (0, 0), (-1, -1), 5),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
                ('LEFTPADDING', (0, 0), (-1, -1), 6),
                ('RIGHTPADDING', (0, 0), (-1, -1), 6),
            ]))
            story.append(kw_table)
        else:
            story.append(Paragraph(rt['message'], muted_style))

        story.append(Spacer(1, 14))

        # =====================================================================
        # 5. COMPETITOR SERP SNAPSHOTS
        # =====================================================================
        story.append(Paragraph("4. Competitor Visibility Benchmarks", h1_style))
        story.append(HRFlowable(width="100%", thickness=1, color=border_color, spaceAfter=10))

        comps = context['competitors']
        if comps['available']:
            comp_names = [c['name'] for c in comps['competitor_list'][:3]]
            story.append(Paragraph(
                f"Benchmarked against <b>{len(comps['competitor_list'])}</b> competitor domains: " +
                ", ".join([f"{c['name']} ({c['domain']})" for c in comps['competitor_list']]),
                body_style
            ))
            story.append(Spacer(1, 6))

            if comps.get('comparison'):
                comp_headers = [
                    Paragraph("Keyword Query", table_header),
                    Paragraph(f"<b>{safe_project_name}</b>", table_header)
                ]
                for cn in comp_names:
                    comp_headers.append(Paragraph(html.escape(cn[:18]), table_header))

                comp_table_rows = [comp_headers]
                col_w = [172, 90] + [90] * len(comp_names)

                for row in comps['comparison'][:12]:
                    r_cells = [
                        Paragraph(html.escape(row['keyword'][:32]), table_cell_bold),
                        Paragraph(row['project_rank'], table_cell)
                    ]
                    for cn in comp_names:
                        r_cells.append(Paragraph(row['competitor_ranks'].get(cn, '—'), table_cell))
                    comp_table_rows.append(r_cells)

                comp_tbl = Table(comp_table_rows, colWidths=col_w)
                comp_tbl.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (-1, 0), primary_color),
                    ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, card_bg]),
                    ('BOX', (0, 0), (-1, -1), 1, border_color),
                    ('INNERGRID', (0, 0), (-1, -1), 0.5, border_color),
                    ('TOPPADDING', (0, 0), (-1, -1), 5),
                    ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
                    ('LEFTPADDING', (0, 0), (-1, -1), 6),
                    ('RIGHTPADDING', (0, 0), (-1, -1), 6),
                ]))
                story.append(comp_tbl)
        else:
            story.append(Paragraph(comps['message'], muted_style))

        story.append(Spacer(1, 14))

        # =====================================================================
        # 6. ACTIONABLE SEO RECOMMENDATIONS
        # =====================================================================
        story.append(Paragraph("5. Prioritized SEO Recommendations", h1_style))
        story.append(HRFlowable(width="100%", thickness=1, color=border_color, spaceAfter=10))

        recs = context['recommendations']
        if recs['available']:
            rec_headers = [
                Paragraph("Priority", table_header),
                Paragraph("Category", table_header),
                Paragraph("Recommendation & Target", table_header),
                Paragraph("Action Guidance", table_header)
            ]
            rec_rows = [rec_headers]
            for r in recs['items'][:10]:
                prio_color = '#DC2626' if r['priority'] == 'HIGH' else '#D97706' if r['priority'] == 'MEDIUM' else '#2563EB'
                prio_cell = Paragraph(f"<font color='{prio_color}'><b>{r['priority']}</b></font>", table_cell_bold)
                rec_cell = Paragraph(f"<b>{html.escape(r['title'])}</b><br/><font color='#64748B'>{html.escape(r['affected_target'][:40])}</font>", table_cell)
                action_cell = Paragraph(html.escape(r['recommended_action'][:120]), table_cell)
                
                rec_rows.append([
                    prio_cell,
                    Paragraph(html.escape(r['category']), table_cell),
                    rec_cell,
                    action_cell
                ])

            recs_tbl = Table(rec_rows, colWidths=[60, 90, 182, 200])
            recs_tbl.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), primary_color),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, card_bg]),
                ('BOX', (0, 0), (-1, -1), 1, border_color),
                ('INNERGRID', (0, 0), (-1, -1), 0.5, border_color),
                ('TOPPADDING', (0, 0), (-1, -1), 6),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
                ('LEFTPADDING', (0, 0), (-1, -1), 6),
                ('RIGHTPADDING', (0, 0), (-1, -1), 6),
            ]))
            story.append(recs_tbl)
        else:
            story.append(Paragraph(recs['message'], muted_style))

        story.append(Spacer(1, 14))

        # =====================================================================
        # 7. DETERMINISTIC PHASED ACTION PLAN
        # =====================================================================
        story.append(Paragraph("6. Phased Implementation Roadmap", h1_style))
        story.append(HRFlowable(width="100%", thickness=1, color=border_color, spaceAfter=10))

        action_plan = context['action_plan']

        # Phase 1
        story.append(Paragraph("<b>Phase 1: Immediate Critical Fixes (Week 1–2)</b>", h2_style))
        for item in action_plan['phase_1_critical']:
            story.append(Paragraph(f"• <b>Action:</b> {html.escape(item['action'])}", body_style))
            story.append(Paragraph(f"  <i>Impact:</i> {html.escape(item['impact'])}", muted_style))
        story.append(Spacer(1, 8))

        # Phase 2
        story.append(Paragraph("<b>Phase 2: On-Page & Technical Optimization (Week 3–4)</b>", h2_style))
        for item in action_plan['phase_2_onpage']:
            story.append(Paragraph(f"• <b>Action:</b> {html.escape(item['action'])}", body_style))
            story.append(Paragraph(f"  <i>Impact:</i> {html.escape(item['impact'])}", muted_style))
        story.append(Spacer(1, 8))

        # Phase 3
        story.append(Paragraph("<b>Phase 3: Search Visibility & Content Expansion (Month 2+)</b>", h2_style))
        for item in action_plan['phase_3_growth']:
            story.append(Paragraph(f"• <b>Action:</b> {html.escape(item['action'])}", body_style))
            story.append(Paragraph(f"  <i>Impact:</i> {html.escape(item['impact'])}", muted_style))

        story.append(Spacer(1, 16))

        # White-label closing note
        story.append(Paragraph(
            f"<i>Report compiled exclusively for {safe_client_name}. "
            "Data verified from search engine observations on google.com.et.</i>",
            muted_style
        ))

        # Build PDF using NumberedCanvas
        def page_canvas_factory(*args, **kwargs):
            canv = NumberedCanvas(*args, **kwargs)
            canv.report_client_label = safe_client_name
            canv.report_title_label = safe_title
            canv.report_date_label = context['report_date_iso']
            return canv

        doc.build(story, canvasmaker=page_canvas_factory)

        file_size = os.path.getsize(full_filepath)
        logger.info(f"Generated white-label PDF report #{report.id} ({file_size} bytes) at {relative_path}")
        return relative_path, file_size

    @classmethod
    def create_report(
        cls,
        project: Project,
        user,
        client_name: str = '',
        title: str = ''
    ) -> SEOReport:
        """
        Validate plan entitlement and project ownership, then create and dispatch an SEOReport.
        """
        # Validate project ownership
        if project.owner_id != user.id:
            raise PermissionError("Access denied: You do not own this project.")

        # Validate subscription entitlement
        PlanEntitlementService.check_can_use_feature(user, FeatureCode.WHITE_LABEL_REPORTS)

        clean_client = client_name.strip() if client_name else ''
        clean_title = title.strip() or 'SEO Performance & Technical Audit Report'

        report = SEOReport.objects.create(
            project=project,
            generated_by=user,
            title=clean_title[:255],
            client_name=clean_client[:255],
            status=ReportStatus.PENDING
        )

        return report

    @classmethod
    def execute_report_generation(cls, report_id: int) -> SEOReport:
        """
        Idempotent runtime execution worker for an SEOReport.
        Transitions PENDING -> RUNNING -> COMPLETED (or FAILED on error).
        """
        try:
            report = SEOReport.objects.select_related('project', 'project__owner').get(id=report_id)
        except SEOReport.DoesNotExist:
            logger.error(f"[ReportService] Report #{report_id} does not exist.")
            raise ValueError(f"Report #{report_id} not found.")

        # Update status to RUNNING
        report.status = ReportStatus.RUNNING
        report.error_message = ''
        report.save(update_fields=['status', 'error_message'])

        try:
            # Collect normalized data
            context = cls.collect_report_context(report.project, client_name=report.client_name)
            
            # Render PDF
            rel_path, file_size = cls.generate_pdf(report, context)

            # Mark completed
            report.status = ReportStatus.COMPLETED
            report.file_path = rel_path
            report.file_size_bytes = file_size
            report.summary_data = {
                'crawler_available': context['crawler']['available'],
                'total_keywords': context['rank_tracking'].get('total_keywords', 0) if context['rank_tracking']['available'] else 0,
                'top_10_count': context['rank_tracking'].get('top_10_count', 0) if context['rank_tracking']['available'] else 0,
                'competitors_count': context['competitors'].get('total_competitors', 0) if context['competitors']['available'] else 0,
                'recommendations_count': context['recommendations'].get('count', 0),
                'overall_status': context['executive_summary']['overall_status'],
            }
            report.completed_at = timezone.now()
            report.save(update_fields=['status', 'file_path', 'file_size_bytes', 'summary_data', 'completed_at'])

            logger.info(f"[ReportService] SEOReport #{report.id} completed successfully.")
            return report

        except Exception as exc:
            logger.exception(f"[ReportService] Error generating SEOReport #{report_id}: {exc}")
            report.status = ReportStatus.FAILED
            report.error_message = str(exc)[:2000]
            report.save(update_fields=['status', 'error_message'])
            raise exc
