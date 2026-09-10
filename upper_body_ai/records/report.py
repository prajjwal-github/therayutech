"""
Patient progress report for the treating clinician.

One PDF per patient: who they are, what they are being treated for, how each
prescribed movement has changed from their first session to their most recent,
and anything that has gone backwards.

Charts are drawn with reportlab's own graphics primitives rather than matplotlib
so the report has no plotting dependency and renders identically on a clinic PC
that has never had a scientific stack installed.
"""

from __future__ import annotations

import os
from datetime import datetime
from typing import Any, Dict, List, Optional

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    Flowable, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
)

# Brand palette, matching the app.
TEAL = colors.HexColor("#0E3A46")
CYAN = colors.HexColor("#34AFAF")
GOLD = colors.HexColor("#D9A32B")
GOOD = colors.HexColor("#2E9E6B")
BAD = colors.HexColor("#C2452C")
MUTED = colors.HexColor("#6B7B80")
RULE = colors.HexColor("#D7E0E2")


# ============================================================ chart flowable ==

class TrendChart(Flowable):
    """
    A small line chart of one exercise's values across sessions.

    Deliberately minimal: day number along the bottom, degrees up the side, the
    target as a dashed reference line. A clinician reading this wants to see the
    shape of the trend and whether it crosses the target, not a data-visualation
    showpiece.
    """

    def __init__(self, points: List[Dict[str, Any]], target: Optional[float],
                 goal: str = "INCREASE", width: float = 165 * mm, height: float = 42 * mm):
        super().__init__()
        self.points = [p for p in points if p.get("value") is not None]
        self.target = target
        self.goal = goal
        self.width = width
        self.height = height

    def draw(self):
        c = self.canv
        w, h = self.width, self.height
        pad_l, pad_r, pad_t, pad_b = 13 * mm, 4 * mm, 5 * mm, 8 * mm
        plot_w = w - pad_l - pad_r
        plot_h = h - pad_t - pad_b

        if not self.points:
            c.setFillColor(MUTED)
            c.setFont("Helvetica-Oblique", 8)
            c.drawString(pad_l, h / 2, "no completed sessions yet")
            return

        values = [p["value"] for p in self.points]
        candidates = values + ([self.target] if self.target else [])
        v_max = max(candidates) * 1.15
        v_min = min(min(values) * 0.85, 0)
        if v_max - v_min < 1:
            v_max = v_min + 1

        def x_at(i: int) -> float:
            if len(self.points) == 1:
                return pad_l + plot_w / 2
            return pad_l + plot_w * i / (len(self.points) - 1)

        def y_at(v: float) -> float:
            return pad_b + plot_h * (v - v_min) / (v_max - v_min)

        # axes
        c.setStrokeColor(RULE)
        c.setLineWidth(0.6)
        c.line(pad_l, pad_b, pad_l + plot_w, pad_b)
        c.line(pad_l, pad_b, pad_l, pad_b + plot_h)

        # y labels
        c.setFont("Helvetica", 6.5)
        c.setFillColor(MUTED)
        for frac in (0.0, 0.5, 1.0):
            v = v_min + (v_max - v_min) * frac
            y = y_at(v)
            c.drawRightString(pad_l - 2 * mm, y - 1.6, f"{v:.0f}")
            if frac > 0:
                c.setStrokeColor(RULE)
                c.setDash(1, 3)
                c.line(pad_l, y, pad_l + plot_w, y)
                c.setDash()

        # target reference
        if self.target:
            ty = y_at(self.target)
            c.setStrokeColor(GOLD)
            c.setLineWidth(1)
            c.setDash(3, 2)
            c.line(pad_l, ty, pad_l + plot_w, ty)
            c.setDash()
            c.setFillColor(GOLD)
            c.setFont("Helvetica-Bold", 6.5)
            c.drawString(pad_l + plot_w - 22 * mm, ty + 1.5 * mm,
                         f"target {self.target:.0f}")

        # the line
        c.setStrokeColor(CYAN)
        c.setLineWidth(1.6)
        path = c.beginPath()
        for i, p in enumerate(self.points):
            x, y = x_at(i), y_at(p["value"])
            path.moveTo(x, y) if i == 0 else path.lineTo(x, y)
        c.drawPath(path)

        # markers, first and last emphasised
        for i, p in enumerate(self.points):
            x, y = x_at(i), y_at(p["value"])
            edge = i in (0, len(self.points) - 1)
            c.setFillColor(TEAL if edge else CYAN)
            c.circle(x, y, 2.1 if edge else 1.4, stroke=0, fill=1)
            if edge:
                c.setFont("Helvetica-Bold", 6.5)
                c.drawCentredString(x, y + 3.2 * mm, f"{p['value']:.0f}")
            c.setFillColor(MUTED)
            c.setFont("Helvetica", 6)
            c.drawCentredString(x, pad_b - 4.5 * mm, f"d{p['day_index']}")


# =================================================================== report ==

def _styles():
    ss = getSampleStyleSheet()
    return {
        "h1": ParagraphStyle("h1", parent=ss["Title"], fontName="Helvetica-Bold",
                             fontSize=19, textColor=TEAL, spaceAfter=2),
        "sub": ParagraphStyle("sub", parent=ss["Normal"], fontSize=9,
                              textColor=MUTED, alignment=TA_CENTER, spaceAfter=10),
        "h2": ParagraphStyle("h2", parent=ss["Heading2"], fontName="Helvetica-Bold",
                             fontSize=12, textColor=TEAL, spaceBefore=11, spaceAfter=5),
        "h3": ParagraphStyle("h3", parent=ss["Heading3"], fontName="Helvetica-Bold",
                             fontSize=10, textColor=TEAL, spaceBefore=8, spaceAfter=3),
        "body": ParagraphStyle("body", parent=ss["Normal"], fontSize=9,
                               leading=13, spaceAfter=5),
        "small": ParagraphStyle("small", parent=ss["Normal"], fontSize=7.5,
                                textColor=MUTED, leading=10),
    }


def _fmt_date(iso: Optional[str]) -> str:
    if not iso:
        return "—"
    try:
        return datetime.fromisoformat(iso).strftime("%d %b %Y")
    except ValueError:
        return iso


def _table(data, widths, align_right=()):
    t = Table(data, colWidths=widths, hAlign="LEFT")
    style = [
        ("BACKGROUND", (0, 0), (-1, 0), TEAL),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("GRID", (0, 0), (-1, -1), 0.4, RULE),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F4F8F9")]),
    ]
    for col in align_right:
        style.append(("ALIGN", (col, 0), (col, -1), "RIGHT"))
    t.setStyle(TableStyle(style))
    return t


def build_progress_report(repo, patient_id: int,
                          output_dir: Optional[str] = None) -> str:
    """Renders the PDF and returns its absolute path."""
    data = repo.progress_summary(patient_id)
    patient = data["patient"]

    output_dir = output_dir or os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "output", "reports")
    os.makedirs(output_dir, exist_ok=True)

    safe = "".join(ch if ch.isalnum() else "_" for ch in patient["full_name"])[:40]
    path = os.path.join(
        output_dir,
        f"{patient['code']}_{safe}_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf")

    st = _styles()
    doc = SimpleDocTemplate(path, pagesize=A4,
                            leftMargin=18 * mm, rightMargin=18 * mm,
                            topMargin=16 * mm, bottomMargin=16 * mm,
                            title=f"Therayu progress report — {patient['full_name']}")
    story: List[Any] = []

    # ---- header -------------------------------------------------------------
    story.append(Paragraph("Therayu — Rehabilitation Progress Report", st["h1"]))
    story.append(Paragraph(
        f"Generated {datetime.now().strftime('%d %B %Y, %H:%M')}", st["sub"]))

    assignment = data.get("assignment") or {}
    story.append(_table(
        [["Patient", patient["full_name"], "Patient ID", patient["code"]],
         ["Condition", assignment.get("condition_name", "—"),
          "Sex", patient.get("sex") or "—"],
         ["Programme start", _fmt_date(data["first_session_at"]),
          "Date of birth", _fmt_date(patient.get("date_of_birth"))],
         ["Latest session", _fmt_date(data["latest_session_at"]),
          "Sessions", str(data["session_count"])]],
        [26 * mm, 60 * mm, 26 * mm, 62 * mm]))

    # ---- headline -----------------------------------------------------------
    story.append(Paragraph("Summary", st["h2"]))
    items = data["exercises"]
    improved = [i for i in items if i["improved"] is True]
    regressed = data["regressions"]

    if not items:
        story.append(Paragraph(
            "No completed exercises recorded yet for this patient.", st["body"]))
    else:
        story.append(Paragraph(
            f"Across {data['session_count']} session(s) spanning "
            f"{data['days_in_programme']} day(s), <b>{len(improved)} of {len(items)}</b> "
            f"prescribed movements improved on their first recorded value."
            + (f" <font color='#C2452C'><b>{len(regressed)} moved backwards and are "
               f"flagged below.</b></font>" if regressed else ""),
            st["body"]))

        rows = [["Movement", "Metric", "Day 1", "Latest", "Change", "% of target"]]
        for i in items:
            arrow = "—"
            if i["change_deg"] is not None:
                arrow = f"{i['change_deg']:+.1f}°"
            rows.append([
                Paragraph(i["name"], st["small"]),
                "ROM" if i["movement_type"] == "REP" else "Peak",
                f"{i['first_value']:.1f}°" if i["first_value"] is not None else "—",
                f"{i['latest_value']:.1f}°" if i["latest_value"] is not None else "—",
                arrow,
                f"{i['rom_pct_of_target']:.0f}%" if i.get("rom_pct_of_target") else "—",
            ])
        tbl = _table(rows, [52 * mm, 17 * mm, 20 * mm, 20 * mm, 22 * mm, 23 * mm],
                     align_right=(2, 3, 4, 5))
        # colour the change column by whether it was an improvement
        for r, i in enumerate(items, start=1):
            if i["improved"] is True:
                tbl.setStyle(TableStyle([("TEXTCOLOR", (4, r), (4, r), GOOD)]))
            elif i["improved"] is False:
                tbl.setStyle(TableStyle([("TEXTCOLOR", (4, r), (4, r), BAD),
                                         ("FONTNAME", (4, r), (4, r), "Helvetica-Bold")]))
        story.append(tbl)

    if regressed:
        story.append(Paragraph("Flagged for review", st["h2"]))
        for i in regressed:
            story.append(Paragraph(
                f"<b>{i['name']}</b> — {i['first_value']:.1f}° on day {i['first_day']} "
                f"to {i['latest_value']:.1f}° on day {i['latest_day']} "
                f"({i['change_deg']:+.1f}°). "
                + ("Range of motion has decreased." if i["goal"] == "INCREASE"
                   else "Deviation from neutral has increased."),
                st["body"]))

    # ---- per-exercise detail ------------------------------------------------
    if items:
        story.append(PageBreak())
        story.append(Paragraph("Movement detail", st["h2"]))
        for i in items:
            story.append(Paragraph(i["name"], st["h3"]))
            direction = ("higher is better" if i["goal"] == "INCREASE"
                         else "lower is better")
            story.append(Paragraph(
                f"Joint <b>{i['primary_joint']}</b> &nbsp;·&nbsp; {direction} "
                f"&nbsp;·&nbsp; {i['sessions']} session(s) "
                f"&nbsp;·&nbsp; best {i['best_value']:.1f}°"
                if i.get("best_value") is not None else
                f"Joint <b>{i['primary_joint']}</b> &nbsp;·&nbsp; {direction}",
                st["small"]))
            story.append(Spacer(1, 3))
            story.append(TrendChart(i["trend"], i.get("target_rom_deg"), i["goal"]))
            story.append(Spacer(1, 5))

    # ---- session log --------------------------------------------------------
    sessions = repo.list_sessions(patient_id)
    if sessions:
        story.append(PageBreak())
        story.append(Paragraph("Session log", st["h2"]))
        rows = [["Day", "Date", "Condition", "Exercises", "Notes"]]
        for s in sessions:
            rows.append([str(s["day_index"]), _fmt_date(s["started_at"]),
                         Paragraph(s.get("condition_name") or "—", st["small"]),
                         str(s["exercise_count"]),
                         Paragraph(s.get("notes") or "", st["small"])])
        story.append(_table(rows, [12 * mm, 26 * mm, 48 * mm, 20 * mm, 48 * mm],
                            align_right=(0, 3)))

        story.append(Paragraph("Exercise detail by session", st["h2"]))
        for s in sessions:
            results = repo.results_for_session(s["id"])
            if not results:
                continue
            story.append(Paragraph(
                f"Day {s['day_index']} — {_fmt_date(s['started_at'])}", st["h3"]))
            rows = [["Movement", "ROM", "Peak", "Reps", "Hold", "Quality", "In band", "Pain"]]
            for r in results:
                rows.append([
                    Paragraph(r["exercise_name"], st["small"]),
                    f"{r['rom_range_deg']:.1f}°" if r["rom_range_deg"] is not None else "—",
                    f"{r['rom_max_deg']:.1f}°" if r["rom_max_deg"] is not None else "—",
                    f"{r['reps_completed']}/{r['target_reps']}" if r["target_reps"] else str(r["reps_completed"]),
                    f"{r['hold_sec_total']:.0f}s" if r["hold_sec_total"] else "—",
                    f"{r['mean_quality_pct']:.0f}%" if r["mean_quality_pct"] is not None else "—",
                    f"{r['in_target_pct']:.0f}%" if r["in_target_pct"] is not None else "—",
                    str(r["pain_score"]) if r.get("pain_score") is not None else "—",
                ])
            story.append(_table(
                rows, [44 * mm, 17 * mm, 17 * mm, 16 * mm, 15 * mm, 18 * mm, 17 * mm, 12 * mm],
                align_right=(1, 2, 3, 4, 5, 6, 7)))
            story.append(Spacer(1, 4))

    # ---- footer -------------------------------------------------------------
    story.append(Spacer(1, 8))
    story.append(Paragraph(
        "Angles are measured in the image plane from a single camera and are "
        "intended to support, not replace, clinical assessment. Sagittal-plane "
        "movements such as shoulder flexion cannot be measured from a "
        "front-facing view and are therefore not reported. Left and right labels "
        "follow the mirrored on-screen preview.",
        st["small"]))

    doc.build(story)
    return os.path.abspath(path)
