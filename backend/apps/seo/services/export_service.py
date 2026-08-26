import io
import csv
from typing import Dict, Any
from apps.seo.models import SEOContentBrief


class ContentBriefExportService:
    """
    Export Service for SEOContentBrief.
    Supports Markdown (.md), CSV (.csv), and PDF (.pdf) formats.
    """

    @classmethod
    def export_markdown(cls, brief: SEOContentBrief) -> str:
        """
        Generate clean, comprehensive GitHub-compatible Markdown documentation for the content brief.
        """
        lines = []
        lines.append(f"# SEO Content Brief: {brief.title}")
        lines.append("")
        lines.append(f"> **Project:** {brief.project.name} ({brief.project.website_url})  ")
        lines.append(f"> **Status:** {brief.get_status_display()} | **Content Type:** {brief.get_content_type_display()} | **Search Intent:** {brief.get_search_intent_display()}  ")
        lines.append(f"> **Generated:** {brief.created_at.strftime('%Y-%m-%d %H:%M UTC')}")
        lines.append("")
        lines.append("---")
        lines.append("")

        # 1. Brief Overview & Target Parameters
        lines.append("## 1. Brief Overview & Strategy")
        lines.append("")
        lines.append(f"* **Primary Target Keyword:** `{brief.target_keyword or 'N/A'}`")
        if brief.secondary_keywords:
            sec_formatted = ", ".join([f"`{k}`" for k in brief.secondary_keywords])
            lines.append(f"* **Secondary Keywords:** {sec_formatted}")
        lines.append(f"* **Target URL:** {brief.target_url or 'To be determined'}")
        lines.append(f"* **Suggested URL Slug:** `{brief.suggested_slug or '/'}`")
        lines.append(f"* **Target Audience:** {brief.audience or 'General audience'}")
        lines.append(f"* **Target Word Count:** {brief.content_length_target or 1500} words")
        lines.append("")
        if brief.content_angle:
            lines.append("### Editorial Angle & Value Proposition")
            lines.append(brief.content_angle)
            lines.append("")

        # 2. SEO Metadata
        lines.append("## 2. SEO Metadata Proposals")
        lines.append("")
        lines.append(f"**Recommended Title Tag (H1):**")
        lines.append(f"> {brief.recommended_title or brief.title}")
        lines.append("")
        lines.append(f"**Recommended Meta Description ({len(brief.meta_description)} chars):**")
        lines.append(f"> {brief.meta_description or 'N/A'}")
        lines.append("")

        # 3. Key Takeaways & Core Concepts
        if brief.key_points:
            lines.append("## 3. Mandatory Key Points & Arguments")
            lines.append("")
            for kp in brief.key_points:
                lines.append(f"- {kp}")
            lines.append("")

        # 4. Content Outline
        if brief.outline:
            lines.append("## 4. Structured Content Outline")
            lines.append("")
            for idx, sec in enumerate(brief.outline, start=1):
                level = sec.get('level', 'H2').upper()
                heading = sec.get('heading', f'Section {idx}')
                prefix = "#" if level == 'H1' else "##" if level == 'H2' else "###"
                lines.append(f"{prefix} {heading}")
                pts = sec.get('key_points', [])
                if pts:
                    for pt in pts:
                        lines.append(f"- {pt}")
                lines.append("")

        # 5. Internal & External Linking Guidance
        lines.append("## 5. Linking & Citations Guidance")
        lines.append("")
        if brief.internal_link_suggestions:
            lines.append("### Internal Links to Include")
            for link in brief.internal_link_suggestions:
                target = link.get('target_url', '')
                anchor = link.get('anchor_text', '')
                context = link.get('context', '')
                lines.append(f"- **Anchor:** `{anchor}` → **Target:** `{target}` ({context})")
            lines.append("")

        if brief.external_link_suggestions:
            lines.append("### External Citations & Authorities")
            for ext in brief.external_link_suggestions:
                src = ext.get('source', '')
                anchor = ext.get('anchor_text', '')
                context = ext.get('context', '')
                lines.append(f"- **Source:** {src} (Anchor: `{anchor}`) — *{context}*")
            lines.append("")

        # 6. FAQ & Schema Opportunities
        if brief.faq_questions:
            lines.append("## 6. FAQ Questions (Rich Snippet Target)")
            lines.append("")
            for f in brief.faq_questions:
                q = f.get('question', '')
                a = f.get('answer_guidance', '')
                lines.append(f"**Q: {q}**  ")
                lines.append(f"*{a}*  ")
                lines.append("")

        # 7. Semantic Entities & Topics
        if brief.entities_topics:
            lines.append("## 7. Topical Entities & Semantic Keywords")
            lines.append("")
            entities_str = ", ".join([f"`{e}`" for e in brief.entities_topics])
            lines.append(entities_str)
            lines.append("")

        lines.append("---")
        lines.append("*Generated automatically by DoxaRank AI SEO Agent.*")
        return "\n".join(lines)

    @classmethod
    def export_csv(cls, brief: SEOContentBrief) -> str:
        """
        Generate structured RFC-4180 CSV representing all brief sections in tabular rows.
        """
        output = io.StringIO()
        writer = csv.writer(output, quoting=csv.QUOTE_MINIMAL)

        # Header
        writer.writerow(["Section", "Property / Heading", "Value / Detail", "Additional Context / Sub-points"])

        # Metadata rows
        writer.writerow(["Metadata", "Brief Title", brief.title, ""])
        writer.writerow(["Metadata", "Project", brief.project.name, brief.project.website_url])
        writer.writerow(["Metadata", "Content Type", brief.get_content_type_display(), ""])
        writer.writerow(["Metadata", "Status", brief.get_status_display(), ""])
        writer.writerow(["Metadata", "Primary Keyword", brief.target_keyword, ""])
        writer.writerow(["Metadata", "Secondary Keywords", "; ".join(brief.secondary_keywords or []), ""])
        writer.writerow(["Metadata", "Search Intent", brief.get_search_intent_display(), ""])
        writer.writerow(["Metadata", "Target URL", brief.target_url, ""])
        writer.writerow(["Metadata", "Suggested Slug", brief.suggested_slug, ""])
        writer.writerow(["Metadata", "Target Audience", brief.audience, ""])
        writer.writerow(["Metadata", "Target Word Count", str(brief.content_length_target or 1500), ""])
        writer.writerow(["Metadata", "Recommended Title Tag", brief.recommended_title, ""])
        writer.writerow(["Metadata", "Meta Description", brief.meta_description, ""])
        writer.writerow(["Metadata", "Content Angle", brief.content_angle, ""])

        # Key Points
        for idx, kp in enumerate(brief.key_points or [], start=1):
            writer.writerow(["Key Points", f"Key Point #{idx}", kp, ""])

        # Outline
        for idx, item in enumerate(brief.outline or [], start=1):
            level = item.get('level', 'H2')
            heading = item.get('heading', '')
            pts = " | ".join(item.get('key_points', []))
            writer.writerow(["Outline", f"{level}: {heading}", pts, f"Section #{idx}"])

        # Internal Links
        for link in brief.internal_link_suggestions or []:
            writer.writerow([
                "Internal Links",
                link.get('anchor_text', ''),
                link.get('target_url', ''),
                link.get('context', '')
            ])

        # External Links
        for ext in brief.external_link_suggestions or []:
            writer.writerow([
                "External Links",
                ext.get('anchor_text', ''),
                ext.get('source', ''),
                ext.get('context', '')
            ])

        # FAQs
        for faq in brief.faq_questions or []:
            writer.writerow([
                "FAQ",
                faq.get('question', ''),
                faq.get('answer_guidance', ''),
                "SERP FAQ Schema"
            ])

        # Entities
        if brief.entities_topics:
            writer.writerow(["Entities & Topics", "Target Semantic Entities", ", ".join(brief.entities_topics), ""])

        return output.getvalue()

    @classmethod
    def export_pdf(cls, brief: SEOContentBrief) -> bytes:
        """
        Generate a clean, valid PDF 1.4 byte document containing the structured brief.
        Uses pure-Python standard PDF syntax stream generation for portable, dependency-free PDF delivery.
        """
        markdown_text = cls.export_markdown(brief)
        
        # Prepare text lines with line-wrapping
        lines_to_render = []
        for raw_line in markdown_text.splitlines():
            # Simple text wrap at ~85 chars
            if len(raw_line) <= 85:
                lines_to_render.append(raw_line)
            else:
                words = raw_line.split(' ')
                cur = ''
                for w in words:
                    if len(cur) + len(w) + 1 <= 85:
                        cur = f"{cur} {w}" if cur else w
                    else:
                        lines_to_render.append(cur)
                        cur = w
                if cur:
                    lines_to_render.append(cur)

        # Build PDF pages (approx 45 lines per page)
        lines_per_page = 45
        pages = [
            lines_to_render[i:i + lines_per_page]
            for i in range(0, max(1, len(lines_to_render)), lines_per_page)
        ]

        def escape_pdf(text: str) -> str:
            # Escape PDF special characters
            return text.replace('\\', '\\\\').replace('(', '\\(').replace(')', '\\)')

        # Construct pure PDF binary stream
        objects = []
        
        # Obj 1: Catalog
        objects.append(b"<< /Type /Catalog /Pages 2 0 R >>")
        
        # Obj 2: Pages root
        page_refs = [f"{4 + idx * 2} 0 R" for idx in range(len(pages))]
        pages_dict = f"<< /Type /Pages /Kids [{' '.join(page_refs)}] /Count {len(pages)} >>".encode('utf-8')
        objects.append(pages_dict)

        # Obj 3: Font
        objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")

        # Create Page & Content Stream objects
        for p_idx, page_lines in enumerate(pages):
            content_obj_num = 5 + p_idx * 2
            page_dict = f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 3 0 R >> >> /Contents {content_obj_num} 0 R >>".encode('utf-8')
            objects.append(page_dict)

            # Build text stream
            stream_parts = []
            stream_parts.append("BT")
            stream_parts.append("/F1 10 Tf")
            stream_parts.append("40 750 Td")
            stream_parts.append("14 TL")
            
            for line in page_lines:
                safe_line = escape_pdf(line)
                stream_parts.append(f"({safe_line}) '")
            
            stream_parts.append("ET")
            stream_str = "\n".join(stream_parts).encode('utf-8')
            stream_obj = f"<< /Length {len(stream_str)} >>\nstream\n".encode('utf-8') + stream_str + b"\nendstream"
            objects.append(stream_obj)

        # Assemble PDF file structure
        buf = io.BytesIO()
        buf.write(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
        
        offsets = []
        for i, obj in enumerate(objects, start=1):
            offsets.append(buf.tell())
            buf.write(f"{i} 0 obj\n".encode('utf-8'))
            buf.write(obj)
            buf.write(b"\nendobj\n")

        startxref = buf.tell()
        buf.write(b"xref\n")
        buf.write(f"0 {len(objects) + 1}\n".encode('utf-8'))
        buf.write(b"0000000000 65535 f \n")
        for off in offsets:
            buf.write(f"{off:010d} 00000 n \n".encode('utf-8'))

        buf.write(b"trailer\n")
        buf.write(f"<< /Size {len(objects) + 1} /Root 1 0 R >>\n".encode('utf-8'))
        buf.write(b"startxref\n")
        buf.write(f"{startxref}\n".encode('utf-8'))
        buf.write(b"%%EOF\n")

        return buf.getvalue()
