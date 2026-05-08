"""
PDF Generator - Putusan MK Simulasi
=====================================
Generate dokumen PDF putusan Mahkamah Konstitusi dari hasil simulasi.
"""

import io
import json
import logging
import re
from datetime import datetime
from typing import Dict, Any

logger = logging.getLogger(__name__)

try:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import cm, mm
    from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT, TA_RIGHT
    from reportlab.lib.colors import HexColor
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
        PageBreak, HRFlowable
    )
    REPORTLAB_AVAILABLE = True
except ImportError:
    REPORTLAB_AVAILABLE = False


def _escape_xml(text: str) -> str:
    """Escape XML special characters for ReportLab Paragraph."""
    return (text
            .replace('&', '&amp;')
            .replace('<', '&lt;')
            .replace('>', '&gt;')
            .replace('"', '&quot;')
            .replace("'", '&apos;'))


def _clean_cot(text: str) -> str:
    """Hapus chain-of-thought, self-correction, dan planning notes dari konten LLM."""
    from .utils import strip_cot
    return strip_cot(text)


def _clean_for_pdf(text: str) -> str:
    """Strip markdown and clean text for PDF rendering."""
    text = re.sub(r'\*\*\*(.+?)\*\*\*', r'\1', text)  # ***bold italic***
    text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)       # **bold**
    text = re.sub(r'\*(.+?)\*', r'\1', text)            # *italic*
    text = re.sub(r'__(.+?)__', r'\1', text)            # __underline__
    text = re.sub(r'~~(.+?)~~', r'\1', text)            # ~~strikethrough~~
    text = re.sub(r'`(.+?)`', r'\1', text)              # `code`
    text = re.sub(r'#{1,6}\s+', '', text)               # # headings
    text = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', text)  # [text](url)
    return text.strip()


def generate_putusan_pdf(result: Dict[str, Any]) -> bytes:
    """
    Generate PDF putusan MK dari hasil simulasi.

    Args:
        result: Dict dengan keys: transcript, scores, individual_scores,
                dissenting_opinions, feedback, draft

    Returns:
        bytes: PDF content
    """
    if not REPORTLAB_AVAILABLE:
        raise RuntimeError("reportlab belum diinstal. Jalankan: pip install reportlab")

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        topMargin=2.5 * cm,
        bottomMargin=2.5 * cm,
        leftMargin=3 * cm,
        rightMargin=2.5 * cm,
    )

    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(
        'JudulUtama',
        parent=styles['Title'],
        fontSize=14,
        leading=18,
        alignment=TA_CENTER,
        spaceAfter=6,
        fontName='Helvetica-Bold',
    ))
    styles.add(ParagraphStyle(
        'SubJudul',
        parent=styles['Heading2'],
        fontSize=12,
        leading=15,
        alignment=TA_CENTER,
        spaceAfter=12,
        fontName='Helvetica',
    ))
    styles.add(ParagraphStyle(
        'BabTitle',
        parent=styles['Heading2'],
        fontSize=12,
        leading=15,
        fontName='Helvetica-Bold',
        spaceBefore=18,
        spaceAfter=8,
    ))
    styles.add(ParagraphStyle(
        'IsiText',
        parent=styles['Normal'],
        fontSize=11,
        leading=15,
        alignment=TA_LEFT,
        spaceAfter=6,
        fontName='Helvetica',
        wordWrap='CJK',
    ))
    styles.add(ParagraphStyle(
        'IsiTextBold',
        parent=styles['Normal'],
        fontSize=11,
        leading=15,
        alignment=TA_LEFT,
        spaceAfter=6,
        fontName='Helvetica-Bold',
        wordWrap='CJK',
    ))
    styles.add(ParagraphStyle(
        'Speaker',
        parent=styles['Normal'],
        fontSize=10,
        leading=13,
        fontName='Helvetica-Bold',
        spaceBefore=8,
        spaceAfter=2,
        textColor=HexColor('#444444'),
    ))
    styles.add(ParagraphStyle(
        'TranscriptText',
        parent=styles['Normal'],
        fontSize=10,
        leading=13,
        alignment=TA_LEFT,
        spaceAfter=4,
        fontName='Helvetica',
        leftIndent=1 * cm,
        wordWrap='CJK',
    ))
    styles.add(ParagraphStyle(
        'ScoreLabel',
        parent=styles['Normal'],
        fontSize=10,
        leading=13,
        fontName='Helvetica',
    ))
    styles.add(ParagraphStyle(
        'ScoreValue',
        parent=styles['Normal'],
        fontSize=10,
        leading=13,
        fontName='Helvetica-Bold',
        alignment=TA_RIGHT,
    ))
    styles.add(ParagraphStyle(
        'Footer',
        parent=styles['Normal'],
        fontSize=9,
        alignment=TA_CENTER,
        textColor=HexColor('#888888'),
    ))

    story = []

    # === HEADER ===
    story.append(Paragraph("REPUBLIK INDONESIA", styles['JudulUtama']))
    story.append(Spacer(1, 4 * mm))
    story.append(Paragraph("PUTUSAN MAHKAMAH KONSTITUSI", styles['JudulUtama']))
    story.append(Spacer(1, 2 * mm))
    story.append(HRFlowable(width="60%", thickness=2, color=HexColor('#333333')))
    story.append(Spacer(1, 4 * mm))

    # Info ringkas
    scores = result.get("scores", {})
    amar = scores.get("amar", "tidak_diketahui")
    total = scores.get("total", 0)
    simulation_id = result.get("simulation_id", "-")

    info_text = f"Tentang: Pengujian Undang-Undang<br/>"
    info_text += f"Nomor: Sim/{simulation_id}/{datetime.now().year}<br/>"
    info_text += f"Tanggal: {datetime.now().strftime('%d %B %Y')}"
    story.append(Paragraph(info_text, styles['SubJudul']))
    story.append(Spacer(1, 6 * mm))

    # === I. POKOK PERMOHONAN ===
    story.append(Paragraph("I. POKOK PERMOHONAN", styles['BabTitle']))
    draft = result.get("draft", "")
    if draft:
        for line in draft.split('\n')[:20]:
            line = _clean_for_pdf(line.strip())
            if line:
                story.append(Paragraph(_escape_xml(line), styles['IsiText']))
    else:
        story.append(Paragraph("(Draft permohonan tidak tersedia)", styles['IsiText']))

    # === II. RISALAH SIDANG ===
    story.append(Paragraph("II. RISALAH SIDANG", styles['BabTitle']))
    transcript = result.get("transcript", [])
    if transcript:
        current_round = ""
        for entry in transcript:
            rnd = entry.get("round", "")
            speaker = entry.get("speaker", "")
            content = entry.get("content", "")
            if not str(content or "").strip():
                continue

            if rnd != current_round:
                current_round = rnd
                story.append(Spacer(1, 4 * mm))
                story.append(Paragraph(f"<b>{rnd}</b>", styles['IsiTextBold']))
                story.append(HRFlowable(width="100%", thickness=0.5, color=HexColor('#cccccc')))

            story.append(Paragraph(_escape_xml(speaker), styles['Speaker']))
            # Clean chain-of-thought without truncating the transcript.
            cleaned = _clean_cot(content)
            display_content = _clean_for_pdf(cleaned)
            if not display_content:
                continue
            for paragraph in re.split(r'\n\s*\n', display_content):
                paragraph = paragraph.strip()
                if paragraph:
                    story.append(Paragraph(_escape_xml(paragraph), styles['TranscriptText']))
    else:
        story.append(Paragraph("(Transkrip tidak tersedia)", styles['IsiText']))

    # === III. AMAR PUTUSAN ===
    story.append(PageBreak())
    story.append(Paragraph("III. AMAR PUTUSAN", styles['BabTitle']))

    amar_text = {
        "dikabulkan": "MENGABULKAN permohonan Pemohon untuk seluruhnya.",
        "ditolak": "MENOLAK permohonan Pemohon untuk seluruhnya.",
        "tidak_dapat_diterima": "MENYATAKAN permohonan TIDAK DAPAT DITERIMA.",
    }.get(amar, f"Amar: {amar}")

    story.append(Paragraph(amar_text, styles['IsiTextBold']))
    story.append(Spacer(1, 4 * mm))

    # Voting detail
    voting_detail = scores.get("voting_detail", {})
    if voting_detail:
        story.append(Paragraph("<b>Voting Panel Hakim:</b>", styles['IsiText']))
        for amar_key, count in voting_detail.items():
            story.append(Paragraph(f"- {amar_key}: {count} suara", styles['IsiText']))

    # === IV. SKOR KUALITAS ===
    story.append(Spacer(1, 6 * mm))
    story.append(Paragraph("IV. PENILAIAN KUALITAS PERMOHONAN", styles['BabTitle']))

    dimensions = [
        ("Legal Standing", "legal_standing", 25),
        ("Kerugian Konstitusional", "kerugian_konstitusional", 20),
        ("Substansi Argumen", "substansi_argumen", 30),
        ("Konsistensi Putusan", "konsistensi_putusan", 15),
        ("Kelengkapan Formil", "kelengkapan_formil", 10),
    ]

    score_data = []
    for label, key, max_val in dimensions:
        val = scores.get(key, 0)
        score_data.append([
            Paragraph(label, styles['ScoreLabel']),
            Paragraph(f"{val} / {max_val}", styles['ScoreValue']),
        ])
    score_data.append([
        Paragraph("<b>TOTAL</b>", styles['ScoreLabel']),
        Paragraph(f"<b>{total} / 100</b>", styles['ScoreValue']),
    ])

    score_table = Table(score_data, colWidths=[10 * cm, 4 * cm])
    score_table.setStyle(TableStyle([
        ('GRID', (0, 0), (-1, -1), 0.5, HexColor('#cccccc')),
        ('BACKGROUND', (0, 0), (0, -1), HexColor('#f8f8f8')),
        ('BACKGROUND', (0, -1), (-1, -1), HexColor('#f0f0f0')),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('LEFTPADDING', (0, 0), (-1, -1), 8),
        ('RIGHTPADDING', (0, 0), (-1, -1), 8),
    ]))
    story.append(score_table)

    # === V. DISSENTING OPINION ===
    dissenting = result.get("dissenting_opinions", [])
    if dissenting:
        story.append(Spacer(1, 6 * mm))
        story.append(Paragraph("V. DISSENTING / CONCURRING OPINION", styles['BabTitle']))
        for op in dissenting:
            hakim = _escape_xml(op.get("hakim", "-"))
            op_type = _escape_xml(op.get("type", "Dissenting Opinion"))
            opinion = _escape_xml(op.get("opinion", ""))
            story.append(Paragraph(f"<b>{op_type} - {hakim}</b>", styles['Speaker']))
            story.append(Paragraph(opinion, styles['TranscriptText']))
            story.append(Spacer(1, 3 * mm))

    # === VI. CATATAN HAKIM ===
    catatan = [c for c in scores.get("catatan_hakim", []) if c and str(c).strip() and str(c).strip() != '-']
    if catatan:
        story.append(Spacer(1, 6 * mm))
        story.append(Paragraph("VI. PERTIMBANGAN HAKIM", styles['BabTitle']))
        for c in catatan:
            story.append(Paragraph(f"- {_escape_xml(str(c))}", styles['IsiText']))

    # === VII. REKOMENDASI ===
    feedback = result.get("feedback", {})
    if feedback and feedback.get("rekomendasi"):
        story.append(Spacer(1, 6 * mm))
        story.append(Paragraph("VII. REKOMENDASI PERBAIKAN", styles['BabTitle']))
        for rec in feedback.get("rekomendasi", []):
            aspek = _escape_xml(rec.get("aspek", "-"))
            masalah = _escape_xml(rec.get("masalah", "-"))
            saran = _escape_xml(rec.get("saran_konkret", "-"))
            story.append(Paragraph(f"<b>{aspek}</b>: {masalah}", styles['IsiText']))
            story.append(Paragraph(f"Saran: {saran}", styles['TranscriptText']))

    # === FOOTER ===
    story.append(Spacer(1, 15 * mm))
    story.append(HRFlowable(width="100%", thickness=1, color=HexColor('#333333')))
    story.append(Spacer(1, 3 * mm))
    story.append(Paragraph(
        "Dokumen ini dihasilkan oleh sistem Simulasi Sidang MK (AI vs AI) "
        "dan BUKAN merupakan putusan resmi Mahkamah Konstitusi Republik Indonesia.",
        styles['Footer']
    ))

    doc.build(story)
    return buffer.getvalue()
