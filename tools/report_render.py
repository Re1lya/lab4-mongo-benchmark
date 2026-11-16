"""报告渲染：同一份内容（块列表）输出为 Word（沿用实验三的论文模板版式）和 HTML（再由 Chrome 打印为 PDF）。

块的格式（元组）：
  ("title", 文本)  ("subtitle", 文本)  ("author", 文本)  ("abstract", 文本)  ("keywords", 文本)
  ("h1"/"h2"/"h3", 文本)  ("p", 文本)  ("note", 文本)
  ("table", 表题, 表头列表, 行列表, 列宽cm列表或None)
  ("figure", 图片路径, 图题, 宽度cm)
  ("pagebreak",)
"""
import html
import os
import subprocess

from docx import Document
from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT, WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"


# ---------------------------------------------------------------- Word
def _set_font(run, size=None, bold=None, east_asia="宋体"):
    if size:
        run.font.size = Pt(size)
    if bold is not None:
        run.bold = bold
    run.font.name = "Times New Roman"
    run._element.get_or_add_rPr().get_or_add_rFonts().set(qn("w:eastAsia"), east_asia)


def _prepare_template(template, header_text, meta):
    d = Document(template)
    body = d._element.body
    for child in list(body):
        if child.tag != qn("w:sectPr"):
            body.remove(child)
    for s in d.styles:
        if s.type != 1:
            continue
        s.font.color.rgb = RGBColor(0, 0, 0)
        rpr = s.element.get_or_add_rPr()
        rf = rpr.find(qn("w:rFonts"))
        if rf is None:
            rf = OxmlElement("w:rFonts")
            rpr.append(rf)
        for attr in list(rf.attrib):
            if "Theme" in attr:
                del rf.attrib[attr]
        rf.set(qn("w:eastAsia"), "黑体" if s.name in ("Title", "Heading 1", "Heading 2", "Heading 3") else "宋体")
        rf.set(qn("w:ascii"), "Times New Roman")
        rf.set(qn("w:hAnsi"), "Times New Roman")
    for name in ("Normal", "Body Text"):
        st = d.styles[name]
        st.font.size = Pt(10.5)
        pf = st.paragraph_format
        pf.line_spacing = Pt(15)
        pf.space_after = Pt(4)
        pf.first_line_indent = Pt(21)
    for name in ("Heading 1", "Heading 2", "Heading 3"):
        st = d.styles[name]
        st.font.size = Pt({"Heading 1": 12, "Heading 2": 11, "Heading 3": 10.5}[name])
        st.font.bold = True
        pf = st.paragraph_format
        pf.space_before = Pt(10 if name == "Heading 1" else 7)
        pf.space_after = Pt(5)
        pf.keep_with_next = True
        pf.first_line_indent = Pt(0)
    d.styles["Title"].font.size = Pt(18)
    d.styles["Title"].font.bold = True
    for sect in d.sections:
        for hdr in (sect.header, sect.first_page_header, sect.even_page_header):
            for p in hdr.paragraphs:
                p.clear()
            p = hdr.paragraphs[0]
            p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
            r = p.add_run(header_text)
            _set_font(r, size=8)
        for ftr in (sect.footer, sect.first_page_footer, sect.even_page_footer):
            for p in ftr.paragraphs:
                p.clear()
            p = ftr.paragraphs[0]
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            run = p.add_run()
            fld = OxmlElement("w:fldSimple")
            fld.set(qn("w:instr"), "PAGE")
            run._r.addnext(fld)
    cp = d.core_properties
    cp.author = meta.get("author", "")
    cp.title = meta.get("title", "")
    cp.subject = meta.get("subject", "")
    cp.last_modified_by = ""
    return d


def _style_or(d, name, fallback="Body Text"):
    try:
        d.styles[name]
        return name
    except KeyError:
        return fallback


def _para(d, text, style="Body Text", size=None, indent=True, bold=False, align=None, east_asia="宋体"):
    p = d.add_paragraph(style=_style_or(d, style))
    p.paragraph_format.space_before = Pt(0)
    if not indent:
        p.paragraph_format.first_line_indent = Pt(0)
    if align:
        p.alignment = align
    r = p.add_run(text)
    _set_font(r, size=size, bold=bold, east_asia=east_asia)
    return p


def _caption(d, text, keep=False):
    p = _para(d, text, size=9, indent=False, align=WD_ALIGN_PARAGRAPH.CENTER)
    p.paragraph_format.space_after = Pt(4)
    p.paragraph_format.keep_with_next = keep
    return p


def _table(d, headers, rows, widths):
    widths = widths or [15.0 / len(headers)] * len(headers)
    t = d.add_table(rows=1, cols=len(headers))
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    t.autofit = False
    pr = t._tbl.tblPr
    tw = pr.find(qn("w:tblW"))
    tw.set(qn("w:type"), "dxa")
    tw.set(qn("w:w"), str(round(sum(widths) * 567)))
    borders = OxmlElement("w:tblBorders")
    for side in ("top", "bottom", "left", "right", "insideH", "insideV"):
        x = OxmlElement("w:" + side)
        x.set(qn("w:val"), "single" if side in ("top", "bottom") else "nil")
        x.set(qn("w:sz"), "8")
        x.set(qn("w:color"), "000000")
        borders.append(x)
    pr.append(borders)
    for i, vals in enumerate([headers] + rows):
        row = t.rows[0] if i == 0 else t.add_row()
        for c, w, txt in zip(row.cells, widths, vals):
            c.width = Cm(w)
            c.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
            p = c.paragraphs[0]
            pf = p.paragraph_format
            pf.first_line_indent = Pt(0)
            pf.line_spacing = 1.05
            pf.space_before = Pt(2)
            pf.space_after = Pt(2)
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            r = p.add_run(str(txt))
            _set_font(r, size=8.5, bold=(i == 0))
            if i == 0:
                b = OxmlElement("w:tcBorders")
                bottom = OxmlElement("w:bottom")
                bottom.set(qn("w:val"), "single")
                bottom.set(qn("w:sz"), "5")
                b.append(bottom)
                c._tc.get_or_add_tcPr().append(b)
        trpr = row._tr.get_or_add_trPr()
        trpr.append(OxmlElement("w:cantSplit"))
        if i == 0:
            trpr.append(OxmlElement("w:tblHeader"))
    spacer = d.add_paragraph()
    spacer.paragraph_format.space_after = Pt(2)
    spacer.paragraph_format.line_spacing = Pt(2)


def render_docx(blocks, template, out_path, header_text, meta):
    d = _prepare_template(template, header_text, meta)
    for b in blocks:
        kind = b[0]
        if kind == "title":
            _para(d, b[1], "Title", indent=False, align=WD_ALIGN_PARAGRAPH.CENTER, east_asia="黑体")
        elif kind == "subtitle":
            _para(d, b[1], "Title", size=12, indent=False, align=WD_ALIGN_PARAGRAPH.CENTER)
        elif kind == "author":
            _para(d, b[1], "作者", size=11, indent=False, align=WD_ALIGN_PARAGRAPH.CENTER)
        elif kind == "abstract":
            _para(d, b[1], "摘要", size=9, indent=False)
        elif kind == "keywords":
            _para(d, b[1], "关键词", size=9, indent=False)
        elif kind in ("h1", "h2", "h3"):
            d.add_paragraph(b[1], "Heading " + kind[1])
        elif kind == "p":
            _para(d, b[1])
        elif kind == "note":
            _para(d, b[1], size=9, indent=False)
        elif kind == "table":
            _caption(d, b[1], keep=True)
            _table(d, b[2], b[3], b[4])
        elif kind == "figure":
            p = d.add_paragraph()
            pf = p.paragraph_format
            pf.first_line_indent = Pt(0)
            pf.space_before = Pt(2)
            pf.space_after = Pt(2)
            pf.keep_with_next = True
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            p.add_run().add_picture(b[1], width=Cm(b[3]))
            _caption(d, b[2])
        elif kind == "pagebreak":
            d.add_page_break()
    d.save(out_path)


# ---------------------------------------------------------------- HTML / PDF
CSS = """
@page { size: 184mm 260mm; margin: 14mm 14.5mm 16mm 14.5mm;
        @top-right { content: "%(header)s"; font: 7.5pt "Songti SC", serif; color: #333; }
        @bottom-center { content: counter(page); font: 8pt "Times New Roman", serif; } }
html { -webkit-print-color-adjust: exact; print-color-adjust: exact; }
body { font: 10.5pt/1.62 "Times New Roman", "Songti SC", "STSong", serif; color: #000; margin: 0; }
h1.title { font: bold 18pt/1.3 "Times New Roman", "Heiti SC", "PingFang SC", sans-serif; text-align: center; margin: 6mm 0 3mm; }
h1.subtitle { font: bold 12pt/1.3 "Times New Roman", serif; text-align: center; margin: 5mm 0 2mm; }
.author { text-align: center; font-size: 11pt; margin: 0 0 4mm; }
.abstract, .keywords { font-size: 9pt; line-height: 1.55; margin: 1.5mm 0; text-align: justify; }
h2, h3, h4 { font-family: "Times New Roman", "Heiti SC", "PingFang SC", sans-serif; font-weight: bold; break-after: avoid; }
h2 { font-size: 12pt; margin: 6mm 0 2.5mm; }
h3 { font-size: 11pt; margin: 4.5mm 0 2mm; }
h4 { font-size: 10.5pt; margin: 3.5mm 0 1.5mm; }
p { margin: 0 0 1.6mm; text-indent: 2em; text-align: justify; }
p.note { text-indent: 0; font-size: 9pt; }
.caption { text-align: center; font-size: 9pt; margin: 2mm 0 1.5mm; text-indent: 0; break-after: avoid; page-break-after: avoid; }
figure { margin: 2mm 0 3mm; text-align: center; break-inside: avoid; }
figure img { max-width: 100%; }
table { border-collapse: collapse; margin: 0 auto 3mm; font-size: 8.5pt; line-height: 1.35; break-inside: avoid; }
thead th { border-top: 1.2pt solid #000; border-bottom: 0.6pt solid #000; padding: 1.2mm 2mm; font-weight: bold; }
tbody td { padding: 0.9mm 2mm; text-align: center; }
tbody tr:last-child td { border-bottom: 1.2pt solid #000; }
.tbl { break-inside: avoid; page-break-inside: avoid; display: block; }  /* 表题与表格不分页 */
.pagebreak { break-after: page; }
"""


def render_html(blocks, out_path, header_text, title):
    base = os.path.dirname(os.path.abspath(out_path))
    parts = ["<!doctype html><html lang='zh-CN'><head><meta charset='utf-8'><title>%s</title><style>%s</style></head><body>"
             % (html.escape(title), CSS.replace("%(header)s", header_text.replace('"', "'")))]
    for b in blocks:
        kind = b[0]
        e = html.escape
        if kind == "title":
            parts.append("<h1 class='title'>%s</h1>" % e(b[1]))
        elif kind == "subtitle":
            parts.append("<h1 class='subtitle'>%s</h1>" % e(b[1]))
        elif kind == "author":
            parts.append("<div class='author'>%s</div>" % e(b[1]))
        elif kind == "abstract":
            parts.append("<div class='abstract'>%s</div>" % e(b[1]))
        elif kind == "keywords":
            parts.append("<div class='keywords'>%s</div>" % e(b[1]))
        elif kind in ("h1", "h2", "h3"):
            tag = {"h1": "h2", "h2": "h3", "h3": "h4"}[kind]
            parts.append("<%s>%s</%s>" % (tag, e(b[1]), tag))
        elif kind == "p":
            parts.append("<p>%s</p>" % e(b[1]))
        elif kind == "note":
            parts.append("<p class='note'>%s</p>" % e(b[1]))
        elif kind == "table":
            widths = b[4]
            cols = "".join("<col style='width:%.1fcm'>" % w for w in widths) if widths else ""
            head = "".join("<th>%s</th>" % e(str(h)) for h in b[2])
            body = "".join("<tr>%s</tr>" % "".join("<td>%s</td>" % e(str(c)) for c in r) for r in b[3])
            parts.append("<div class='tbl'><div class='caption'>%s</div><table><colgroup>%s</colgroup><thead><tr>%s</tr></thead>"
                         "<tbody>%s</tbody></table></div>" % (e(b[1]), cols, head, body))
        elif kind == "figure":
            rel = os.path.relpath(b[1], base)
            parts.append("<figure><img src='%s' style='width:%.1fcm'><div class='caption'>%s</div></figure>" % (e(rel), b[3], e(b[2])))
        elif kind == "pagebreak":
            parts.append("<div class='pagebreak'></div>")
    parts.append("</body></html>")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(parts))


def html_to_pdf(html_path, pdf_path):
    subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--no-pdf-header-footer",
                    "--print-to-pdf=" + os.path.abspath(pdf_path), "file://" + os.path.abspath(html_path)],
                   check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
