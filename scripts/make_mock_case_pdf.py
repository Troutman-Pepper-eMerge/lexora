"""Generate a realistic mock litigation complaint as a PDF.

The content is crafted so LEXORA's intake extractor can populate every field
on the New Case form (title, client, practice area, case type, jurisdiction,
court, judge, opposing counsel, estimated value, filed date, priority, summary)
and so the same document is useful for RAG Q&A after upload.

Output: data/Nexora_v_Meridian_Complaint.pdf
"""
from __future__ import annotations

from pathlib import Path

from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (Paragraph, SimpleDocTemplate, Spacer,
                                Table, TableStyle)
from reportlab.lib import colors

OUT = Path(__file__).resolve().parents[1] / "data" / "Nexora_v_Meridian_Complaint.pdf"


def build_styles():
    ss = getSampleStyleSheet()
    styles = {
        "court": ParagraphStyle("court", parent=ss["Normal"], alignment=TA_CENTER,
                                fontName="Times-Bold", fontSize=11, leading=14),
        "caption": ParagraphStyle("caption", parent=ss["Normal"], alignment=TA_CENTER,
                                  fontName="Times-Bold", fontSize=12, leading=16,
                                  spaceBefore=10, spaceAfter=10),
        "h": ParagraphStyle("h", parent=ss["Normal"], fontName="Times-Bold",
                            fontSize=11, leading=14, spaceBefore=12, spaceAfter=4),
        "body": ParagraphStyle("body", parent=ss["Normal"], alignment=TA_JUSTIFY,
                               fontName="Times-Roman", fontSize=10.5, leading=15,
                               spaceAfter=6, firstLineIndent=0.3 * inch),
        "flat": ParagraphStyle("flat", parent=ss["Normal"], alignment=TA_JUSTIFY,
                               fontName="Times-Roman", fontSize=10.5, leading=15,
                               spaceAfter=6),
        "small": ParagraphStyle("small", parent=ss["Normal"], fontName="Times-Roman",
                                fontSize=9.5, leading=12),
    }
    return styles


def main():
    OUT.parent.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(
        str(OUT), pagesize=LETTER,
        leftMargin=1 * inch, rightMargin=1 * inch,
        topMargin=0.9 * inch, bottomMargin=0.9 * inch,
        title="Nexora Robotics, Inc. v. Meridian Dynamics, LLC — Complaint",
        author="Harwell, Voss & Reyes LLP",
    )
    S = build_styles()
    E = []

    # ---- Caption block --------------------------------------------------- #
    E.append(Paragraph("UNITED STATES DISTRICT COURT", S["court"]))
    E.append(Paragraph("NORTHERN DISTRICT OF CALIFORNIA", S["court"]))
    E.append(Paragraph("SAN FRANCISCO DIVISION", S["court"]))
    E.append(Spacer(1, 8))

    cap = [
        [Paragraph("NEXORA ROBOTICS, INC., a Delaware corporation,",
                   S["small"]),
         Paragraph("Case No. 3:26-cv-01847-PMA", S["small"])],
        [Paragraph("&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;Plaintiff,", S["small"]),
         Paragraph("<b>COMPLAINT FOR:</b>", S["small"])],
        [Paragraph("v.", S["small"]),
         Paragraph("(1) Misappropriation of Trade Secrets<br/>"
                   "(2) Breach of Contract<br/>"
                   "(3) Tortious Interference", S["small"])],
        [Paragraph("MERIDIAN DYNAMICS, LLC, a California limited "
                   "liability company; and DOES 1&ndash;10, inclusive,",
                   S["small"]),
         Paragraph("<b>DEMAND FOR JURY TRIAL</b>", S["small"])],
        [Paragraph("&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;Defendants.", S["small"]),
         Paragraph("", S["small"])],
    ]
    t = Table(cap, colWidths=[3.6 * inch, 2.9 * inch])
    t.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LINEAFTER", (0, 0), (0, -1), 1, colors.black),
        ("LINEBELOW", (0, -1), (0, -1), 1, colors.black),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ]))
    E.append(t)
    E.append(Spacer(1, 10))

    E.append(Paragraph(
        "Plaintiff Nexora Robotics, Inc. (&ldquo;Nexora&rdquo; or "
        "&ldquo;Plaintiff&rdquo;), by and through its undersigned counsel, "
        "brings this action against Defendant Meridian Dynamics, LLC "
        "(&ldquo;Meridian&rdquo; or &ldquo;Defendant&rdquo;), and alleges "
        "as follows:", S["flat"]))

    # ---- Nature of the action ------------------------------------------- #
    E.append(Paragraph("I. NATURE OF THE ACTION", S["h"]))
    E.append(Paragraph(
        "1. This is an action for the willful and malicious misappropriation "
        "of Nexora&rsquo;s trade secrets relating to its proprietary "
        "autonomous warehouse-navigation stack, known internally as "
        "&ldquo;Project Lodestar.&rdquo; Between January and February 2026, "
        "three senior Nexora engineers resigned and immediately joined "
        "Meridian, taking with them confidential source code, sensor-fusion "
        "calibration data, and customer pricing models in violation of their "
        "written confidentiality and non-solicitation agreements.", S["body"]))
    E.append(Paragraph(
        "2. Within nine weeks of those departures, Meridian announced a "
        "competing navigation product&mdash;&ldquo;MeridianPath&rdquo;&mdash;"
        "that replicated Nexora&rsquo;s distinctive obstacle-prediction "
        "architecture in a manner that could not have been independently "
        "developed in that timeframe. Plaintiff seeks injunctive relief, "
        "compensatory damages of not less than $18,500,000, exemplary "
        "damages, and attorneys&rsquo; fees.", S["body"]))

    # ---- Parties --------------------------------------------------------- #
    E.append(Paragraph("II. PARTIES", S["h"]))
    E.append(Paragraph(
        "3. Plaintiff Nexora Robotics, Inc. is a corporation organized under "
        "the laws of the State of Delaware, with its principal place of "
        "business at 2200 Bayfront Parkway, Palo Alto, California. Nexora "
        "designs autonomous material-handling robots for large-scale "
        "distribution centers.", S["body"]))
    E.append(Paragraph(
        "4. Defendant Meridian Dynamics, LLC is a limited liability company "
        "organized under the laws of the State of California, with its "
        "principal place of business at 815 Harbor Way, Oakland, California. "
        "Meridian is a direct competitor of Nexora in the warehouse-robotics "
        "market.", S["body"]))

    # ---- Jurisdiction and venue ----------------------------------------- #
    E.append(Paragraph("III. JURISDICTION AND VENUE", S["h"]))
    E.append(Paragraph(
        "5. This Court has subject-matter jurisdiction under 28 U.S.C. "
        "&sect; 1331 and 18 U.S.C. &sect; 1836(c) because Plaintiff asserts "
        "claims under the federal Defend Trade Secrets Act. The Court has "
        "supplemental jurisdiction over the related state-law claims under "
        "28 U.S.C. &sect; 1367.", S["body"]))
    E.append(Paragraph(
        "6. Venue is proper in the Northern District of California under "
        "28 U.S.C. &sect; 1391(b) because a substantial part of the events "
        "giving rise to these claims occurred in this District and Defendant "
        "resides in this District. This action has been assigned to the "
        "Honorable Patricia M. Alvarez, United States District Judge.", S["body"]))

    # ---- Factual background --------------------------------------------- #
    E.append(Paragraph("IV. FACTUAL BACKGROUND", S["h"]))
    for para in [
        "7. Nexora invested more than four years and approximately "
        "$42 million developing Project Lodestar, a real-time navigation "
        "stack that fuses LiDAR, stereo-vision, and inertial data to route "
        "fleets of autonomous robots through dynamic warehouse environments.",
        "8. Nexora protects Lodestar through role-based access controls, "
        "encrypted repositories, mandatory confidentiality agreements, and a "
        "&ldquo;clean-desk&rdquo; policy. Fewer than fifteen employees had "
        "full access to the Lodestar source repository.",
        "9. Defendants Aaron Whitfield, Priya Ramaswamy, and Devon Clarke "
        "(the &ldquo;Departing Engineers&rdquo;) each executed Nexora&rsquo;s "
        "Proprietary Information and Inventions Agreement, which prohibits "
        "disclosure of confidential information and solicitation of Nexora "
        "employees for twelve months following separation.",
        "10. Forensic analysis of Nexora&rsquo;s systems revealed that, in "
        "the seventy-two hours before their resignations, the Departing "
        "Engineers collectively downloaded 6,214 files from the Lodestar "
        "repository to personal USB devices, including the complete "
        "sensor-fusion calibration dataset and the obstacle-prediction "
        "model weights.",
        "11. On March 2, 2026, Meridian publicly demonstrated MeridianPath "
        "at the North American Logistics Expo. Independent benchmarking "
        "showed a path-planning latency profile statistically "
        "indistinguishable from Lodestar&rsquo;s, a result Nexora contends "
        "is only explicable by the use of its misappropriated trade secrets.",
    ]:
        E.append(Paragraph(para, S["body"]))

    # ---- Claims ---------------------------------------------------------- #
    E.append(Paragraph("V. FIRST CLAIM FOR RELIEF", S["h"]))
    E.append(Paragraph(
        "(Misappropriation of Trade Secrets &mdash; 18 U.S.C. &sect; 1836)",
        S["flat"]))
    E.append(Paragraph(
        "12. Plaintiff realleges and incorporates each preceding paragraph. "
        "The Lodestar source code, calibration data, and pricing models "
        "constitute trade secrets that derive independent economic value "
        "from not being generally known. Defendant acquired and used those "
        "trade secrets by improper means, causing Nexora damages in an "
        "amount not less than $18,500,000.", S["body"]))

    E.append(Paragraph("VI. SECOND CLAIM FOR RELIEF", S["h"]))
    E.append(Paragraph("(Breach of Contract)", S["flat"]))
    E.append(Paragraph(
        "13. The Departing Engineers breached their written agreements with "
        "Nexora, and Meridian induced and benefited from those breaches. "
        "Nexora has been damaged as a direct and proximate result.", S["body"]))

    # ---- Prayer ---------------------------------------------------------- #
    E.append(Paragraph("VII. PRAYER FOR RELIEF", S["h"]))
    E.append(Paragraph(
        "WHEREFORE, Plaintiff respectfully requests that the Court: "
        "(a) enter a preliminary and permanent injunction restraining "
        "Defendant&rsquo;s use of Nexora&rsquo;s trade secrets; "
        "(b) award compensatory damages of not less than $18,500,000; "
        "(c) award exemplary damages and reasonable attorneys&rsquo; fees; "
        "and (d) grant such other relief as the Court deems just and proper.",
        S["flat"]))

    # ---- Signature block ------------------------------------------------- #
    E.append(Spacer(1, 14))
    E.append(Paragraph("Dated: March 12, 2026", S["flat"]))
    E.append(Paragraph("Respectfully submitted,", S["flat"]))
    E.append(Spacer(1, 6))
    E.append(Paragraph("<b>HARWELL, VOSS &amp; REYES LLP</b>", S["flat"]))
    E.append(Paragraph("By: /s/ Miriam T. Voss", S["flat"]))
    E.append(Paragraph("Miriam T. Voss (SBN 214559)", S["small"]))
    E.append(Paragraph("Counsel for Plaintiff Nexora Robotics, Inc.", S["small"]))
    E.append(Spacer(1, 10))
    E.append(Paragraph(
        "Counsel for Defendant Meridian Dynamics, LLC: "
        "Beckett &amp; Crane LLP, 500 Montgomery Street, San Francisco, CA.",
        S["small"]))

    doc.build(E)
    print(f"Wrote {OUT} ({OUT.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
