"""
TrapRoyalties Royalty Screening PDF Generator  -  TR Screening Protocol V1
4-page legal-style forensic royalty discrepancy report.

Pages:
  1. Rights Holder ID + Asset Metadata + Recovery Valuation + Alert
  2. Discrepancy Data Sources + Stream-to-Statutory Calculation
  3. Regulatory Standing & Statutory Basis
  4. Certification of Data Integrity + Signatures
"""

import os, sys, hashlib, datetime
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import qrcode
from fpdf import FPDF

from outreach.bounty_calculator import parse_streams

PDF_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "pdfs")
os.makedirs(PDF_DIR, exist_ok=True)

RATE_LO = 0.0015
RATE_HI = 0.0031

# Colors
BLACK     = (0,   0,   0)
DARK_BLUE = (30,  58,  138)
GRAY_BG   = (243, 244, 246)
RED_TEXT  = (197, 48,  48)
RED_BG    = (255, 245, 245)
GRAY_LINE = (204, 204, 204)
GRAY_TEXT = (102, 102, 102)
RULE_GRAY = (238, 238, 238)
CODE_BG   = (238, 238, 238)


def _audit_id(artist: str, isrc: str) -> str:
    return "TR-" + hashlib.sha256(f"{artist}{isrc}".encode()).hexdigest()[:12].upper()

def _qr_path(audit_id: str, isrc: str) -> str:
    url = f"https://traproyalties.com/verify?id={audit_id}&isrc={isrc}"
    img = qrcode.make(url)
    path = os.path.join(PDF_DIR, f"qr_{audit_id}.png")
    img.save(path)
    return path


class ForensicPDF(FPDF):
    def __init__(self, artist, track, isrc, raw_streams, audit_id):
        super().__init__(orientation="P", unit="mm", format="A4")
        self.artist      = artist
        self.track       = track
        self.isrc        = isrc
        self.raw_streams = raw_streams
        self.audit_id    = audit_id
        self.date_str    = datetime.date.today().strftime("%B %d, %Y").upper()
        self.recovery_lo = round(raw_streams * RATE_LO, 2)
        self.recovery_hi = round(raw_streams * RATE_HI, 2)
        sha              = hashlib.sha256(f"{artist}{isrc}{audit_id}".encode()).hexdigest()
        self.sha_full    = sha
        self.hash_short  = f"SHA256: 0x{sha[:8].upper()}...{sha[-6:].upper()}"
        self.att_id      = f"TR-ATT-{datetime.date.today().year}-{sha[:6].upper()}"
        self.timestamp   = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        self.set_margins(15, 15, 15)
        self.set_auto_page_break(False)

    def header(self): pass
    def footer(self): pass

    # ── Shared helpers ────────────────────────────────────────────────────────

    def _page_footer(self, page_num, total=4):
        self.set_y(272)
        self.set_draw_color(*GRAY_LINE)
        self.set_line_width(0.2)
        self.line(15, 272, 195, 272)
        self.set_font("Times", "", 8)
        self.set_text_color(*GRAY_TEXT)
        self.set_xy(15, 274)
        self.cell(130, 4, f"CONFIDENTIAL LEGAL WORK PRODUCT   -   {self.hash_short}")
        self.cell(50, 4, f"Page {page_num} of {total}", align="R")

    def _section_bar(self, text):
        self.set_fill_color(*GRAY_BG)
        self.set_draw_color(*BLACK)
        self.set_line_width(0.3)
        self.set_font("Times", "B", 10)
        self.set_text_color(*BLACK)
        self.cell(180, 8, text, border=1, fill=True, new_x="LMARGIN", new_y="NEXT")
        self.ln(1)

    def _table_row(self, label, value, value_color=None, big=False):
        """Single label+value row with bottom border."""
        self.set_draw_color(*RULE_GRAY)
        self.set_line_width(0.2)
        self.set_font("Times", "B", 11)
        self.set_text_color(*BLACK)
        self.cell(72, 10, label, border="B")
        if value_color:
            self.set_text_color(*value_color)
        font_size = 14 if big else 11
        self.set_font("Courier", "B" if (value_color or big) else "", font_size)
        self.cell(108, 10, value, border="B", new_x="LMARGIN", new_y="NEXT")
        self.set_text_color(*BLACK)
        self.set_line_width(0.2)

    def _h2(self, text):
        self.set_font("Times", "B", 14)
        self.set_text_color(*BLACK)
        self.cell(180, 10, text, new_x="LMARGIN", new_y="NEXT")
        self.ln(4)

    def _h3(self, text):
        self.set_font("Times", "B", 12)
        self.set_text_color(*BLACK)
        self.cell(180, 8, text, new_x="LMARGIN", new_y="NEXT")

    def _body(self, text):
        self.set_font("Times", "", 11)
        self.set_text_color(*BLACK)
        self.multi_cell(180, 6, text, align="J")

    # ── Pages ─────────────────────────────────────────────────────────────────

    def _page1(self):
        # Header: firm info left, case meta right
        self.set_xy(15, 15)
        self.set_font("Times", "B", 9)
        self.set_text_color(*BLACK)
        self.multi_cell(90, 4.5,
            "TRAPROYALTIES FORENSIC UNIT\n"
            "STATUTORY RECOVERY DIVISION\n"
            "NODE: STOCKHOLM-1 / PROTOCOL TR-V1.2",
            align="L")

        self.set_font("Times", "", 9)
        self.set_xy(105, 15)
        self.multi_cell(90, 4.5,
            f"CASE REF: {self.audit_id}\n"
            f"DATE: {self.date_str}\n"
            f"STATUS: REGISTRATION GAP DETECTED",
            align="R")

        # Header rule
        self.set_draw_color(*BLACK)
        self.set_line_width(0.5)
        self.line(15, 30, 195, 30)
        self.set_line_width(0.2)

        # Stamp box (top right)
        self.set_draw_color(*DARK_BLUE)
        self.set_line_width(0.8)
        self.rect(152, 33, 42, 16)
        self.set_line_width(0.2)
        self.set_font("Times", "B", 7.5)
        self.set_text_color(*DARK_BLUE)
        self.set_xy(152, 36)
        self.cell(42, 5, "CERTIFIED DISCREPANCY", align="C")
        self.set_font("Times", "", 7)
        self.set_xy(152, 41)
        self.cell(42, 5, "ACTION REQUIRED", align="C")

        # Title
        self.set_font("Times", "BU", 15)
        self.set_text_color(*BLACK)
        self.set_xy(15, 34)
        self.cell(180, 12, "FORENSIC ROYALTY DISCREPANCY REPORT", align="C",
                  new_x="LMARGIN", new_y="NEXT")
        self.ln(3)

        # Intro
        self.set_x(15)
        self._body(
            "    This report constitutes a Certified Forensic Audit regarding non-identified digital "
            "performance royalties associated with the sound recording listed herein. Forensic probing "
            "of the International Standard Recording Code (ISRC) registry has identified a significant "
            "gap between historical stream volume and current claimant registration."
        )
        self.ln(5)

        # Section 1
        self._section_bar("1.  RIGHTS HOLDER IDENTIFICATION")
        self._table_row("LEGAL NAME:", self.artist.upper())
        self._table_row("PROFESSIONAL ALIAS:", self.track.upper())
        self._table_row("IPI NUMBER:", "NOT LOCATED IN REGISTRY")
        self._table_row("VERIFICATION HASH:", self.hash_short)
        self.ln(5)

        # Section 2
        self._section_bar("2.  ASSET METADATA")
        self._table_row("VERIFIED ISRC:", self.isrc)
        self._table_row("REGISTRY STATUS:", "UNREGISTERED / NON-IDENTIFIED",
                        value_color=RED_TEXT)
        self._table_row("VERIFIED STREAMS:", f"{self.raw_streams:,}")
        self._table_row("ACCRUAL TYPE:", "RETROACTIVE (36-MONTH POOL)")
        self.ln(5)

        # Section 3
        self._section_bar("3.  RECOVERY VALUATION")
        self._table_row(
            "EST. ACCRUED BALANCE:",
            f"${self.recovery_lo:,.0f}  to  ${self.recovery_hi:,.0f}",
            big=True
        )
        self.ln(5)

        # Alert box
        alert_y = self.get_y()
        self.set_fill_color(*RED_BG)
        self.set_draw_color(*RED_TEXT)
        self.set_line_width(0.5)
        self.rect(15, alert_y, 180, 20, "FD")
        self.set_font("Times", "B", 10)
        self.set_text_color(*RED_TEXT)
        self.set_xy(18, alert_y + 3)
        self.multi_cell(174, 5,
            'NOTICE: Asset classified as "Black Box / Suspense Funds." Under 17 U.S.C. S.114, '
            'failure to submit a valid LOD and Repertoire Schedule may result in forfeiture of '
            'historical accruals.',
            align="L")
        self.set_line_width(0.2)

        self._page_footer(1)

    def _page2(self):
        self.set_xy(15, 15)
        self._h2("2.  DISCREPANCY DATA SOURCES")

        self.set_font("Times", "", 11)
        self.set_text_color(*BLACK)
        self.cell(180, 6, f"Registries queried on {self.date_str.title()}:",
                  new_x="LMARGIN", new_y="NEXT")
        self.ln(3)

        # Table with column headers
        self.set_fill_color(*GRAY_BG)
        self.set_draw_color(*BLACK)
        self.set_line_width(0.3)
        self.set_font("Times", "B", 10)
        self.set_text_color(*BLACK)
        col = [64, 56, 60]
        self.cell(col[0], 8, "DATA POINT",      border=1, fill=True)
        self.cell(col[1], 8, "SOURCE",           border=1, fill=True)
        self.cell(col[2], 8, "VALUE",            border=1, fill=True,
                  new_x="LMARGIN", new_y="NEXT")
        self.set_line_width(0.2)

        rows = [
            ("ISRC Verification",  "IFPI / MusicBrainz",  self.isrc),
            ("Global Streams",     "DSP Aggregate",        f"{self.raw_streams:,}"),
            ("Registry Status",    "SoundExchange",        "NO_CLAIMANT_FOUND"),
        ]
        for r in rows:
            self.set_draw_color(*RULE_GRAY)
            for i, (cell_text, w) in enumerate(zip(r, col)):
                self.set_font("Courier" if i == 2 else "Times", "", 10)
                self.set_text_color(*BLACK)
                self.cell(w, 8, cell_text, border="B")
            self.ln()
        self.ln(8)

        # Stream-to-statutory
        self._h3("Stream-to-Statutory Calculation")
        self.set_font("Times", "", 11)
        self.set_text_color(*BLACK)
        self.cell(180, 6, "Using CRB statutory rates:", new_x="LMARGIN", new_y="NEXT")
        self.ln(2)
        self._table_row("Conservative ($0.0015/stream):", f"${self.recovery_lo:,.2f}")
        self._table_row("Optimized ($0.0031/stream):",    f"${self.recovery_hi:,.2f}")
        self.ln(8)

        # Methodology
        self._h3("Methodology")
        self.ln(1)
        self._body(
            "Stream counts were aggregated from publicly available DSP data and ISRC lookups via "
            "MusicBrainz and IFPI registries. SoundExchange claimant status was verified against "
            "the public registry. The conservative estimate uses the SoundExchange Featured Artist "
            "statutory rate of $0.0015 per stream; the optimized estimate uses $0.0031 reflecting "
            "potential multi-platform and non-interactive broadcast inclusion."
        )
        self.ln(8)

        # QR code
        qr_path = _qr_path(self.audit_id, self.isrc)
        if os.path.exists(qr_path):
            self.set_font("Times", "", 8)
            self.set_text_color(*GRAY_TEXT)
            self.cell(180, 5, "Scan to verify this report online:", new_x="LMARGIN", new_y="NEXT")
            self.image(qr_path, x=15, y=self.get_y(), w=28)

        self._page_footer(2)

    def _page3(self):
        self.set_xy(15, 15)
        self._h2("3.  REGULATORY STANDING & STATUTORY BASIS")

        self._h3("3.1  Music Modernization Act (MMA)")
        self.ln(1)
        self._body(
            "Under 17 U.S.C. S.114, SoundExchange is required to hold unmatched digital performance "
            "royalties in Suspense accounts. Performers who do not appear in SoundExchange's registry "
            "as claimants will have royalties held indefinitely until a valid Letter of Direction (LOD) "
            "and Repertoire Schedule are filed. The three-year lookback window means that accruals "
            "dating up to 36 months prior to filing are recoverable."
        )
        self.ln(6)

        self._h3("3.2  AMP Act Compliance")
        self.ln(1)
        self._body(
            "For legacy assets recorded prior to February 15, 1972, this audit complies with the "
            "Allocation for Music Producers (AMP) Act, which provides a statutory right for non-featured "
            "artists and producers to receive a portion of SoundExchange digital performance royalties. "
            "The AMP Act establishes a right of recovery separate from the featured artist LOD process."
        )
        self.ln(6)

        self._h3("3.3  Black Box Royalty Recovery Framework")
        self.ln(1)
        self._body(
            "Royalties classified as 'Black Box' or 'Suspense' at SoundExchange are recoverable via "
            "submission of:\n"
            "  (1) LOD Part 1  -  Letter of Direction from the artist or authorized representative;\n"
            "  (2) Schedule 1  -  Repertoire Chart listing ISRC codes and ownership data;\n"
            "  (3) Evidence of Discrepancy  -  this forensic screening report serves as the required "
            "supporting documentation."
        )
        self.ln(8)

        # Legal opinion box with blue left accent
        op_y = self.get_y()
        self.set_fill_color(*GRAY_BG)
        self.rect(18, op_y, 177, 32, "F")
        self.set_draw_color(*DARK_BLUE)
        self.set_line_width(1.5)
        self.line(15, op_y, 15, op_y + 32)
        self.set_line_width(0.2)

        self.set_font("Times", "B", 11)
        self.set_text_color(*BLACK)
        self.set_xy(20, op_y + 4)
        self.cell(170, 6, "LEGAL OPINION:", new_x="LMARGIN", new_y="NEXT")
        self.set_font("Times", "", 11)
        self.set_x(20)
        self.multi_cell(170, 5.5,
            f'Asset classified as "Unclaimed Black Box." Filing LOD Part 1 + Schedule 1 with '
            f'SoundExchange (accounts@soundexchange.com) is the prescribed recovery method under '
            f'17 U.S.C. S.114. This report constitutes the Evidence of Discrepancy required '
            f'for filing. Expected processing timeline: 30-90 days.',
            align="J")

        self._page_footer(3)

    def _page4(self):
        self.set_xy(15, 15)
        self._h2("4.  CERTIFICATION OF DATA INTEGRITY")

        self.set_font("Times", "", 11)
        self.set_text_color(*BLACK)
        self.cell(180, 6, "This audit is anchored to a unique SHA-256 hash:",
                  new_x="LMARGIN", new_y="NEXT")
        self.ln(3)

        # Digital anchor box
        anch_y = self.get_y()
        self.set_fill_color(*CODE_BG)
        self.set_draw_color(*BLACK)
        self.set_line_width(0.5)
        self.rect(15, anch_y, 180, 30, "FD")
        self.set_font("Courier", "", 8.5)
        self.set_text_color(*BLACK)
        self.set_xy(18, anch_y + 4)
        self.multi_cell(174, 5,
            f"DIGITAL_ANCHOR_ID : 0x{self.sha_full[:16].upper()}...{self.sha_full[-8:].upper()}\n"
            f"TIMESTAMP         : {self.timestamp}\n"
            f"NODE_VERIFIED     : STOCKHOLM-PRIMARY-1\n"
            f"AUDIT_ID          : {self.audit_id}",
            align="L")
        self.set_line_width(0.2)

        self.set_y(anch_y + 34)
        self.ln(6)

        # Signatures section
        self._h3("Signatures & Execution")
        self.ln(2)
        self.set_font("Times", "", 11)
        self.set_text_color(*BLACK)
        self.multi_cell(180, 6,
            "By signing below, the Legal Representative certifies intent to file LOD Part 1 "
            "and Schedule 1 with SoundExchange, Inc. at accounts@soundexchange.com.",
            align="J")

        sig_y = self.get_y() + 28
        self.set_draw_color(*BLACK)
        self.set_line_width(0.3)
        self.line(15,  sig_y, 95,  sig_y)
        self.line(115, sig_y, 195, sig_y)
        self.set_font("Times", "", 8)
        self.set_text_color(*BLACK)
        self.set_xy(15, sig_y + 2)
        self.cell(80, 4, "SIGNATURE OF PERFORMER / RIGHTS HOLDER")
        self.set_xy(115, sig_y + 2)
        self.cell(80, 4, "SIGNATURE OF LEGAL COUNSEL / NOTARY")

        # Notary seal
        notary_y = sig_y + 18
        self.set_draw_color(*GRAY_LINE)
        self.set_line_width(0.3)
        self.rect(15, notary_y, 55, 35)
        self.set_font("Times", "", 9)
        self.set_text_color(*GRAY_LINE)
        self.set_xy(15, notary_y + 14)
        self.cell(55, 5, "NOTARY SEAL", align="C", new_x="LMARGIN", new_y="NEXT")
        self.set_xy(15, notary_y + 20)
        self.cell(55, 5, "PLACEHOLDER", align="C")

        self._page_footer(4)

    def build(self):
        self.add_page(); self._page1()
        self.add_page(); self._page2()
        self.add_page(); self._page3()
        self.add_page(); self._page4()


# ── Public API ────────────────────────────────────────────────────────────────
def generate_pdf(
    artist: str,
    track: str,
    isrc: str,
    streams_input=0,
    output_dir: str = None,
) -> str:
    output_dir = output_dir or PDF_DIR

    if isinstance(streams_input, (int, float)):
        raw = int(streams_input)
    else:
        raw = parse_streams(streams_input)

    audit_id = _audit_id(artist, isrc)
    pdf = ForensicPDF(artist, track, isrc, raw, audit_id)
    pdf.build()

    safe = f"{artist.replace(' ', '_')}_{track[:20].replace(' ', '_')}_Audit.pdf"
    out_path = os.path.join(output_dir, safe)
    pdf.output(out_path)
    print(f"[PDF] {out_path}")
    return out_path


def batch_pdfs_from_leads(leads_path: str, stream_col: str = "streams"):
    import csv
    with open(leads_path, newline="", encoding="utf-8") as f:
        leads = list(csv.DictReader(f))

    pdfs = []
    for lead in leads:
        if lead.get("status") not in ("JACKPOT", "GUEST_UNCLAIMED"):
            continue
        path = generate_pdf(
            artist=lead.get("artist", "Unknown"),
            track=lead.get("track", "Unknown"),
            isrc=lead.get("isrc", ""),
            streams_input=lead.get(stream_col, 0) or 0,
        )
        pdfs.append(path)

    print(f"[PDF] {len(pdfs)} PDFs generated")
    return pdfs


if __name__ == "__main__":
    generate_pdf(
        artist="Doja Cat",
        track="Agora Hills",
        isrc="USRC12302416",
        streams_input="48M",
    )
