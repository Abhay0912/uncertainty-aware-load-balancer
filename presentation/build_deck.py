"""Build presentation/uncertainty_aware_lb.pptx with python-pptx.

Usage (python-pptx and Pillow are not project dependencies):
    pip install python-pptx Pillow
    python presentation/build_deck.py .
"""
import math
import re
import sys
from pathlib import Path

from lxml import etree
from PIL import Image
from pptx import Presentation
from pptx.chart.data import CategoryChartData
from pptx.dml.color import RGBColor
from pptx.enum.chart import XL_CHART_TYPE, XL_LABEL_POSITION, XL_LEGEND_POSITION, XL_MARKER_STYLE
from pptx.enum.dml import MSO_LINE
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.opc.constants import RELATIONSHIP_TYPE as RT
from pptx.oxml.ns import qn
from pptx.util import Inches, Pt

REPO = Path(sys.argv[1])
OUT = REPO / "presentation" / "uncertainty_aware_lb.pptx"
FIG = REPO / "docs" / "figures"
URL = "github.com/Abhay0912/uncertainty-aware-load-balancer"

INK = "1B2A41"      # dominant: navy ink
BLUE = "2B78D6"     # stable workload (matches figures)
ORANGE = "E8643A"   # bursty workload / risk accent
MUTED = "5B6575"
TINT = "EEF2F7"
LINE = "D5DBE3"
WHITE = "FFFFFF"
HEAD, BODY = "Cambria", "Calibri"

W, H = 13.333, 7.5
M = 0.6


def rgb(h):
    return RGBColor.from_string(h)


# ---------------------------------------------------------------- theme
def apply_theme(prs):
    part = prs.slide_master.part.part_related_by(RT.THEME)
    root = etree.fromstring(part.blob)
    a = "http://schemas.openxmlformats.org/drawingml/2006/main"
    ns = {"a": a}
    root.set("name", "Uncertainty LB")
    for tag, face in (("majorFont", HEAD), ("minorFont", BODY)):
        root.find(f".//a:{tag}/a:latin", ns).set("typeface", face)
    colors = {"dk2": INK, "lt2": TINT, "accent1": BLUE, "accent2": ORANGE, "accent3": MUTED,
              "accent4": "2E9E8F", "accent5": "8A6FD1", "accent6": "C9A227"}
    scheme = root.find(".//a:clrScheme", ns)
    for name, hexv in colors.items():
        el = scheme.find(f"a:{name}", ns)
        for child in list(el):
            el.remove(child)
        etree.SubElement(el, f"{{{a}}}srgbClr", val=hexv)
    part._blob = etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)


# ---------------------------------------------------------------- text helpers
TOKEN = re.compile(r"(\*\*.+?\*\*|_\{.+?\})")


def add_runs(p, text, size, color, bold=False, italic=False, font=BODY):
    """`**bold**` and `_{subscript}` inline markup."""
    for part in TOKEN.split(text):
        if not part:
            continue
        r = p.add_run()
        b, sub = bold, False
        if part.startswith("**"):
            part, b = part[2:-2], True
        elif part.startswith("_{"):
            part, sub = part[2:-1], True
        r.text = part
        f = r.font
        f.size, f.bold, f.italic, f.name = Pt(size), b, italic, font
        f.color.rgb = rgb(color)
        if sub:
            r.font._rPr.set("baseline", "-25000")


def set_bullet(p, color):
    pPr = p._p.get_or_add_pPr()
    pPr.set("marL", str(int(Inches(0.28))))
    pPr.set("indent", str(int(-Inches(0.28))))
    for tag in ("a:buClr", "a:buFont", "a:buChar", "a:buNone"):
        for el in pPr.findall(qn(tag)):
            pPr.remove(el)
    clr = etree.SubElement(pPr, qn("a:buClr"))
    etree.SubElement(clr, qn("a:srgbClr"), val=color)
    etree.SubElement(pPr, qn("a:buFont"), typeface="Arial")
    etree.SubElement(pPr, qn("a:buChar"), char="•")


def text(slide, x, y, w, h, paras, size=16, color=INK, bold=False, align=PP_ALIGN.LEFT,
         anchor=MSO_ANCHOR.TOP, bullets=False, font=BODY, space=6, italic=False, name=None):
    tb = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    if name:
        tb.name = name
    tf = tb.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = anchor
    for side in ("margin_left", "margin_right", "margin_top", "margin_bottom"):
        setattr(tf, side, 0)
    if isinstance(paras, str):
        paras = [paras]
    for i, para in enumerate(paras):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = align
        p.space_after = Pt(space)
        add_runs(p, para, size, color, bold=bold, italic=italic, font=font)
        if bullets:
            set_bullet(p, ORANGE)
    return tb


def box(slide, x, y, w, h, fill=TINT, shape=MSO_SHAPE.ROUNDED_RECTANGLE, line=None, name=None):
    s = slide.shapes.add_shape(shape, Inches(x), Inches(y), Inches(w), Inches(h))
    if shape == MSO_SHAPE.ROUNDED_RECTANGLE:
        s.adjustments[0] = 0.08
    s.fill.solid()
    s.fill.fore_color.rgb = rgb(fill)
    if line:
        s.line.color.rgb = rgb(line)
        s.line.width = Pt(1.25)
    else:
        s.line.fill.background()
    s.shadow.inherit = False
    if name:
        s.name = name
    return s


def marker(slide, x, y, label, fill=ORANGE, d=0.5, size=16):
    c = box(slide, x, y, d, d, fill=fill, shape=MSO_SHAPE.OVAL)
    tf = c.text_frame
    for side in ("margin_left", "margin_right", "margin_top", "margin_bottom"):
        setattr(tf, side, 0)
    tf.vertical_anchor = MSO_ANCHOR.MIDDLE
    p = tf.paragraphs[0]
    p.alignment = PP_ALIGN.CENTER
    add_runs(p, label, size, WHITE, bold=True)
    return c


def stat(slide, x, y, w, value, label, color=ORANGE, vsize=48, lsize=14, lcolor=MUTED):
    text(slide, x, y, w, 0.85, value, size=vsize, color=color, bold=True, font=HEAD)
    text(slide, x, y + 0.9, w, 0.8, label, size=lsize, color=lcolor)


def picture(slide, path, x, y, max_w, max_h, align="center"):
    iw, ih = Image.open(path).size
    scale = min(max_w / iw, max_h / ih)
    w, h = iw * scale, ih * scale
    px = x + (max_w - w) / 2 if align == "center" else x
    pic = slide.shapes.add_picture(str(path), Inches(px), Inches(y), Inches(w), Inches(h))
    return pic, w, h


# ---------------------------------------------------------------- slide frame
prs = Presentation()
prs.slide_width, prs.slide_height = Inches(W), Inches(H)
apply_theme(prs)
TITLE_ONLY = prs.slide_layouts[5]
N_SLIDES = 17
counter = {"n": 0}


def new_slide(title, dark=False, notes=""):
    s = prs.slides.add_slide(TITLE_ONLY)
    counter["n"] += 1
    bg = s.background.fill
    bg.solid()
    bg.fore_color.rgb = rgb(INK if dark else WHITE)
    t = s.shapes.title
    t.left, t.top, t.width, t.height = Inches(M), Inches(0.4), Inches(W - 2 * M), Inches(0.9)
    tf = t.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = MSO_ANCHOR.MIDDLE
    for side in ("margin_left", "margin_right", "margin_top", "margin_bottom"):
        setattr(tf, side, 0)
    p = tf.paragraphs[0]
    p.alignment = PP_ALIGN.LEFT
    add_runs(p, title, 34, WHITE if dark else INK, bold=True, font=HEAD)
    if counter["n"] > 1:
        text(s, W - M - 1.0, H - 0.45, 1.0, 0.3, f"{counter['n']} / {N_SLIDES}", size=11,
             color="AEB7C4" if dark else MUTED, align=PP_ALIGN.RIGHT, name="Slide number")
    if notes:
        s.notes_slide.notes_text_frame.text = notes
    return s


def style_chart(chart, legend=True):
    chart.font.name = BODY
    chart.font.size = Pt(12)
    chart.font.color.rgb = rgb(MUTED)
    chart.has_legend = legend
    if legend:
        chart.legend.position = XL_LEGEND_POSITION.TOP
        chart.legend.include_in_layout = False
        chart.legend.font.size = Pt(13)
        chart.legend.font.color.rgb = rgb(INK)
    va = chart.value_axis
    va.has_major_gridlines = True
    va.major_gridlines.format.line.color.rgb = rgb(LINE)
    va.format.line.fill.background()
    va.tick_labels.font.size = Pt(12)
    va.tick_labels.font.color.rgb = rgb(MUTED)
    ca = chart.category_axis
    ca.format.line.color.rgb = rgb(LINE)
    ca.tick_labels.font.size = Pt(12)
    ca.tick_labels.font.color.rgb = rgb(INK)
    ca.has_major_gridlines = False


def axis_title(axis, label):
    axis.has_title = True
    tf = axis.axis_title.text_frame
    tf.text = label
    f = tf.paragraphs[0].runs[0].font
    f.size, f.bold, f.name = Pt(12), False, BODY
    f.color.rgb = rgb(MUTED)


def log_axis(axis):
    scaling = axis._element.find(qn("c:scaling"))
    lb = etree.SubElement(scaling, qn("c:logBase"), val="10")
    scaling.remove(lb)
    scaling.insert(0, lb)


def color_series(chart, colors):
    for series, c in zip(chart.plots[0].series, colors):
        series.format.fill.solid()
        series.format.fill.fore_color.rgb = rgb(c)


POLICIES = ["Round Robin", "Random", "Weighted RR", "P2C", "Least CPU", "Weighted metric", "Probabilistic"]

# ================================================================ 1 title
s = new_slide("Uncertainty-Aware Probabilistic Load Balancing", dark=True, notes=(
    "Introduce the project: an M.Tech Cloud Computing project. The question is whether the variability of "
    "recent server metrics, not just their current value, can predict overload and improve placement. "
    "Spoiler for the audience: the honest answer is 'not in this setting', and the talk explains why."))
s.shapes.title.top = Inches(2.0)
s.shapes.title.height = Inches(1.3)
text(s, M, 3.35, 11.5, 0.6, "Estimating overload risk from metric variability: a simulation study against six baselines",
     size=20, color="CBD5E1")
marker(s, M, 4.55, "", d=0.22)
text(s, M + 0.4, 4.45, 9, 0.45, "**Abhay Nagesh Rao**  ·  M.Tech (CSE), Cloud Computing", size=18, color=WHITE)
text(s, M + 0.4, 4.95, 9, 0.45, "National Institute of Technology Warangal  ·  November 2026", size=16, color="CBD5E1")
text(s, M + 0.4, 5.45, 9, 0.45, URL, size=14, color="9FB3CC")

# ================================================================ 2 motivation
s = new_slide("Same 60% CPU, very different risk", notes=(
    "Both servers average exactly 60% over the last 10 samples. A least-loaded balancer sees the same number. "
    "But the volatile one regularly crosses the 80% threshold. Under a normal approximation, the steady server "
    "has zero exceedance probability while the volatile one has about one in five. That gap is the idea this "
    "project tests."))
steady = [60.0] * 10
volatile = [32, 88, 45, 90, 30, 75, 28, 85, 47, 80]
mu = sum(volatile) / 10
sd = math.sqrt(sum((v - mu) ** 2 for v in volatile) / 10)
p_vol = 1 - 0.5 * (1 + math.erf(((80 - mu) / sd) / math.sqrt(2)))
cd = CategoryChartData()
cd.categories = [str(i) for i in range(1, 11)]
cd.add_series("Steady server", steady)
cd.add_series("Volatile server", volatile)
cd.add_series("Threshold θ = 80%", [80] * 10)
gf = s.shapes.add_chart(XL_CHART_TYPE.LINE_MARKERS, Inches(M), Inches(1.5), Inches(7.6), Inches(5.3), cd)
ch = gf.chart
style_chart(ch)
ch.value_axis.minimum_scale, ch.value_axis.maximum_scale = 0, 100
axis_title(ch.value_axis, "CPU %")
axis_title(ch.category_axis, "Last 10 samples")
for series, c, dash, mk in zip(ch.plots[0].series, [BLUE, ORANGE, MUTED],
                               [None, None, MSO_LINE.DASH], [True, True, False]):
    series.smooth = False
    series.format.line.color.rgb = rgb(c)
    series.format.line.width = Pt(2.75 if mk else 1.5)
    if dash:
        series.format.line.dash_style = dash
    series.marker.style = XL_MARKER_STYLE.CIRCLE if mk else XL_MARKER_STYLE.NONE
    if mk:
        series.marker.size = 7
        series.marker.format.fill.solid()
        series.marker.format.fill.fore_color.rgb = rgb(c)
        series.marker.format.line.color.rgb = rgb(c)
cx = 8.65
box(s, cx, 1.6, W - M - cx, 2.25)
text(s, cx + 0.3, 1.8, 3.6, 0.4, "Steady server", size=16, color=BLUE, bold=True)
text(s, cx + 0.3, 2.2, 3.6, 0.4, "μ = 60%,  σ = 0", size=15, color=MUTED)
text(s, cx + 0.3, 2.65, 3.6, 0.9, "P(> 80%) = 0.00", size=30, color=INK, bold=True, font=HEAD)
box(s, cx, 4.05, W - M - cx, 2.25)
text(s, cx + 0.3, 4.25, 3.6, 0.4, "Volatile server", size=16, color=ORANGE, bold=True)
text(s, cx + 0.3, 4.65, 3.6, 0.4, f"μ = {mu:.0f}%,  σ = {sd:.1f}", size=15, color=MUTED)
text(s, cx + 0.3, 5.1, 3.6, 0.9, f"P(> 80%) = {p_vol:.2f}", size=30, color=INK, bold=True, font=HEAD)
text(s, cx, 6.45, W - M - cx, 0.5, "A least-loaded rule sees the same 60% for both.", size=14, color=MUTED, italic=True)

# ================================================================ 3 question
s = new_slide("Research question", notes=(
    "The primary outcome was written down before any experiment ran: fewer SLA violations and less overload "
    "under bursty demand, without hurting throughput or response time. The scope is a simulation comparison, "
    "not a production scheduler, and no improvement was assumed."))
box(s, M, 1.55, W - 2 * M, 1.55, fill=INK)
text(s, M + 0.45, 1.7, W - 2 * M - 0.9, 1.25,
     "Can recent server metrics and their variability be used to estimate overload risk and improve task "
     "assignment compared with simple load-balancing policies?",
     size=22, color=WHITE, italic=True, font=HEAD, anchor=MSO_ANCHOR.MIDDLE)
rows = [
    ("1", "Primary outcome (fixed in advance)",
     "Fewer SLA violations and less overload under **bursty** demand, without losing throughput or response time."),
    ("2", "Decisive comparison",
     "Against the same policy **without** the risk term, paired seed by seed."),
    ("3", "Scope",
     "A seeded simulation study with 5 heterogeneous servers. No improvement assumed; results reported as measured."),
]
for i, (n, head, body) in enumerate(rows):
    y = 3.55 + i * 1.1
    marker(s, M, y, n)
    text(s, M + 0.8, y - 0.02, 4.0, 0.5, head, size=18, bold=True)
    text(s, M + 4.9, y + 0.02, W - M - (M + 4.9), 0.9, body, size=16, color=MUTED)

# ================================================================ 4 method
s = new_slide("The proposed policy in five steps", notes=(
    "Walk the pipeline left to right. Rolling mean and population standard deviation over 10 samples. "
    "Normal CDF turns them into exceedance probabilities for CPU and memory. Combine assuming independence. "
    "Score is 0.6 times current load plus 0.4 times risk. Filter out servers above 0.5 risk unless all are, "
    "which is logged as capacity pressure. Key point: removing the risk term gives exactly the weighted-metric "
    "baseline, and a test proves it decision for decision."))
steps = [
    ("Window", "Last W = 10 samples of CPU and memory load", "μ, σ (population)"),
    ("Exceedance", ["Normal approximation", "θ_{C} = 80%,  θ_{M} = 85%"],
     ["P_{C} = 1 − Φ(z_{C})", "z_{C} = (θ_{C} − μ_{C}) / σ_{C}"]),
    ("Combine", "CPU and memory assumed independent", ["P_{risk} = 1 −", "(1 − P_{C})(1 − P_{M})"]),
    ("Score", "L = weighted CPU, memory and response time", "S = 0.6 L + 0.4 P_{risk}"),
    ("Admit", "Drop servers with P_{risk} > 0.5 unless all exceed it", "choose lowest S"),
]
cw, gap = 2.2, (W - 2 * M - 5 * 2.2) / 4
for i, (head, desc, formula) in enumerate(steps):
    x = M + i * (cw + gap)
    box(s, x, 1.6, cw, 3.65)
    marker(s, x + 0.25, 1.82, str(i + 1))
    text(s, x + 0.25, 2.5, cw - 0.45, 0.45, head, size=19, bold=True, font=HEAD)
    text(s, x + 0.25, 3.0, cw - 0.45, 1.1, desc, size=14, color=MUTED)
    text(s, x + 0.25, 4.15, cw - 0.45, 1.0, formula, size=15, color=ORANGE, bold=True, space=2)
    if i < 4:
        a = s.shapes.add_shape(MSO_SHAPE.RIGHT_ARROW, Inches(x + cw + gap / 2 - 0.11), Inches(3.3),
                               Inches(0.22), Inches(0.3))
        a.fill.solid()
        a.fill.fore_color.rgb = rgb(LINE)
        a.line.fill.background()
box(s, M, 5.55, W - 2 * M, 1.2, fill=WHITE, line=LINE)
text(s, M + 0.35, 5.6, W - 2 * M - 0.7, 1.1,
     "**The ablation.** With weights (1, 0) and no admission filter, the policy is exactly the "
     "**weighted-metric** baseline, verified decision for decision by a unit test. Any difference "
     "between the two comes from the risk term alone.", size=16, anchor=MSO_ANCHOR.MIDDLE)

# ================================================================ 5 setup
s = new_slide("A heterogeneous cluster, two matched workloads", notes=(
    "Five servers with very different capacity. The fifth server is tiny: 2 cores at half speed, 1 of 37 "
    "capacity units. Keep it in mind, because it breaks the load-blind policies. The two workloads have the "
    "same mean load; only variability differs, so 'bursty is worse' cannot just mean 'more load'."))
cd = CategoryChartData()
cd.categories = ["S0\n4c × 1.0", "S1\n4c × 1.0", "S2\n8c × 1.5", "S3\n8c × 2.0", "S4\n2c × 0.5"]
cd.add_series("Capacity (cores × speed)", [4, 4, 12, 16, 1])
gf = s.shapes.add_chart(XL_CHART_TYPE.COLUMN_CLUSTERED, Inches(M), Inches(1.5), Inches(6.3), Inches(5.3), cd)
ch = gf.chart
style_chart(ch, legend=False)
ch.has_title = True
ch.chart_title.text_frame.text = "Capacity per server (cores × speed)"
tr = ch.chart_title.text_frame.paragraphs[0].runs[0].font
tr.size, tr.bold, tr.name = Pt(15), True, BODY
tr.color.rgb = rgb(INK)
pl = ch.plots[0]
pl.gap_width = 60
pl.has_data_labels = True
pl.data_labels.font.size = Pt(13)
pl.data_labels.font.color.rgb = rgb(INK)
pl.data_labels.position = XL_LABEL_POSITION.OUTSIDE_END
ser = pl.series[0]
ser.format.fill.solid()
ser.format.fill.fore_color.rgb = rgb(BLUE)
pt = ser.points[4]
pt.format.fill.solid()
pt.format.fill.fore_color.rgb = rgb(ORANGE)
ch.value_axis.visible = False
ch.value_axis.has_major_gridlines = False
rx = 7.35
rw = W - M - rx
box(s, rx, 1.6, rw, 1.65)
text(s, rx + 0.3, 1.75, rw - 0.6, 0.4, "Stable workload", size=17, bold=True, color=BLUE)
text(s, rx + 0.3, 2.2, rw - 0.6, 1.0, "Poisson arrivals ≈ 4 tasks/s, ±20% slow drift, ≈ 65% mean load",
     size=15, color=INK)
box(s, rx, 3.45, rw, 1.65)
text(s, rx + 0.3, 3.6, rw - 0.6, 0.4, "Bursty workload", size=17, bold=True, color=ORANGE)
text(s, rx + 0.3, 4.05, rw - 0.6, 1.0, "4 bursts of 50 s at 3× arrivals; **same mean load**: "
     "≈ 41% between bursts, ≈ 160% during", size=15, color=INK)
text(s, rx, 5.35, rw, 1.4, [
    "Tasks: CPU 0.5–1.5 cores, memory 0.5–3 GB, lognormal work (mean 6 s)",
    "Reservation model with a FIFO queue per server; run arrivals for 1000 s, then drain",
], size=14, color=MUTED, bullets=True)

# ================================================================ 6 fairness
s = new_slide("Designed so the comparison is fair", notes=(
    "Seventy runs in total. Fairness guarantees: one task list per workload and seed, shared by all policies; "
    "fresh servers every run; parameters frozen before any result; paired comparison against the ablation "
    "with win counts. 156 tests back this up, including edge cases like sigma equal to zero."))
stat(s, M, 1.75, 3.6, "70 runs", "7 policies × 2 workloads × 5 seeds", vsize=54, lsize=16)
stat(s, M, 3.6, 3.6, "156 tests", "σ = 0, all servers risky, determinism, ablation identity", color=BLUE,
     vsize=54, lsize=16)
cards = [
    ("Identical task stream", "Generated once per (workload, seed), passed unchanged to every policy"),
    ("Fresh state", "Servers rebuilt and policies reset for every run; seeded RNG streams only"),
    ("Frozen parameters", "θ, weights, W, admission and SLA = 18 s fixed before any result"),
    ("Paired by seed", "Per-seed difference vs. the ablation; report mean, std and seeds won"),
]
gx, gw, gh = 4.75, (W - M - 4.75 - 0.3) / 2, 2.35
for i, (head, body) in enumerate(cards):
    x = gx + (i % 2) * (gw + 0.3)
    y = 1.6 + (i // 2) * (gh + 0.3)
    box(s, x, y, gw, gh)
    marker(s, x + 0.3, y + 0.3, "✓", fill=INK, size=15)
    text(s, x + 0.3, y + 0.95, gw - 0.6, 0.45, head, size=18, bold=True)
    text(s, x + 0.3, y + 1.45, gw - 0.6, 0.85, body, size=15, color=MUTED)

# ================================================================ 7 policies
s = new_slide("Seven policies, one interface", notes=(
    "Static: Round Robin and Random ignore capacity and load. Weighted Round Robin knows capacity but not load. "
    "Load-aware: Least CPU, Power of Two Choices and the weighted-metric score. The weighted metric is the "
    "ablation. The proposed probabilistic policy is the one in orange."))
pol = [
    ("Round Robin", "Cyclic order", "load-blind"),
    ("Random", "Uniform choice", "load-blind"),
    ("Weighted RR", "Smooth WRR, weight = cores × speed", "capacity-aware"),
    ("Least CPU", "Lowest live CPU load", "load-aware"),
    ("Power of Two", "Sample 2, pick lower L", "load-aware"),
    ("Weighted metric", "Lowest L, no risk term", "ablation"),
    ("Probabilistic", "Lowest S among admissible servers", "proposed"),
]
cw4 = (W - 2 * M - 3 * 0.3) / 4
for i, (name, rule, tag) in enumerate(pol):
    row, col = divmod(i, 4)
    x = M + col * (cw4 + 0.3)
    y = 1.65 + row * 2.6
    hi = tag == "proposed"
    box(s, x, y, cw4, 2.3, fill=ORANGE if hi else TINT, line=INK if tag == "ablation" else None)
    text(s, x + 0.3, y + 0.3, cw4 - 0.6, 0.35, tag.upper(), size=12, bold=True,
         color=WHITE if hi else (ORANGE if tag != "load-blind" else MUTED))
    text(s, x + 0.3, y + 0.75, cw4 - 0.6, 0.5, name, size=20, bold=True, font=HEAD, color=WHITE if hi else INK)
    text(s, x + 0.3, y + 1.35, cw4 - 0.6, 0.8, rule, size=15, color=WHITE if hi else MUTED)
x = M + 3 * (cw4 + 0.3)
text(s, x, 4.45, cw4, 2.0, "Every policy only **reads** server state. A contract test compares full server "
     "state before and after each call.", size=14, color=MUTED)

# ================================================================ 8 backlog
s = new_slide("Finding 1: CPU % hid a 424-task backlog", notes=(
    "During development every load-aware policy lost to load-blind weighted round robin. Cause: fragmentation. "
    "The 2-core server had 424 queued tasks but showed only 62% CPU, because the next task could not fit beside "
    "the running one. The fix changed what the balancer observes, not the formulas: load includes queued demand. "
    "This is the same reason Linux load average counts waiting tasks."))
box(s, M, 1.6, 4.1, 4.0)
stat(s, M + 0.35, 1.85, 3.5, "424", "tasks queued on the 2-core server", vsize=60, lsize=16)
stat(s, M + 0.35, 3.6, 3.5, "62%", "CPU it reported at the same moment", color=BLUE, vsize=60, lsize=16)
a = s.shapes.add_shape(MSO_SHAPE.RIGHT_ARROW, Inches(M + 4.3), Inches(3.35), Inches(0.5), Inches(0.5))
a.fill.solid()
a.fill.fore_color.rgb = rgb(ORANGE)
a.line.fill.background()
fx = M + 5.0
box(s, fx, 1.6, 3.4, 4.0, fill=INK)
text(s, fx + 0.3, 1.85, 2.8, 0.4, "THE FIX", size=13, bold=True, color="F4A582")
text(s, fx + 0.3, 2.3, 2.8, 1.6, "Observe **load %** = (running + queued demand) ÷ capacity", size=20,
     color=WHITE, font=HEAD)
text(s, fx + 0.3, 4.15, 2.8, 1.3, "Equal to utilisation when there is no queue; load-blind results "
     "unchanged.", size=14, color="CBD5E1")
ox = fx + 3.7
text(s, ox, 1.65, W - M - ox, 0.4, "Stable mean response", size=15, bold=True, color=MUTED)
for i, (name, before, after) in enumerate([("Least CPU", "907 s", "6.5 s"), ("Weighted metric", "236 s", "6.4 s")]):
    y = 2.2 + i * 1.65
    text(s, ox, y, W - M - ox, 0.4, name, size=17, bold=True)
    text(s, ox, y + 0.45, 1.5, 0.7, before, size=26, color=MUTED, font=HEAD)
    text(s, ox + 1.45, y + 0.45, 0.5, 0.7, "→", size=26, color=MUTED)
    text(s, ox + 1.95, y + 0.45, 1.6, 0.7, after, size=26, color=ORANGE, bold=True, font=HEAD)
text(s, M, 5.9, W - 2 * M, 0.8, "Lesson: what the balancer **observes** matters as much as the rule it applies.",
     size=17, color=INK, italic=True)

# ================================================================ 9 response chart
s = new_slide("Load-awareness is worth about 100×", notes=(
    "Log scale. Round Robin and Random are around 850 seconds because they give the tiny server one fifth of "
    "the tasks. Every load-aware policy is near 6 seconds on stable. P2C is weaker with only five servers. "
    "Probabilistic and weighted metric are almost identical, which is the next slide's topic."))
resp = {"stable": [857.4, 846.7, 9.08, 24.8, 6.16, 6.15, 6.44],
        "bursty": [821.4, 822.9, 30.9, 46.4, 29.2, 29.3, 29.5]}
cd = CategoryChartData()
cd.categories = POLICIES
cd.add_series("Stable", resp["stable"])
cd.add_series("Bursty", resp["bursty"])
gf = s.shapes.add_chart(XL_CHART_TYPE.COLUMN_CLUSTERED, Inches(M), Inches(1.45), Inches(8.6), Inches(5.4), cd)
ch = gf.chart
style_chart(ch)
color_series(ch, [BLUE, ORANGE])
log_axis(ch.value_axis)
ch.value_axis.minimum_scale = 1
ch.value_axis.maximum_scale = 1000
ch.value_axis.tick_labels.number_format = "0"
ch.value_axis.tick_labels.number_format_is_linked = False
axis_title(ch.value_axis, "Mean response time (s, log scale)")
pl = ch.plots[0]
pl.gap_width, pl.overlap = 55, -5
pl.has_data_labels = True
pl.data_labels.number_format = "[<100]0.0;0"
pl.data_labels.number_format_is_linked = False
pl.data_labels.font.size = Pt(11)
pl.data_labels.font.color.rgb = rgb(INK)
pl.data_labels.position = XL_LABEL_POSITION.OUTSIDE_END
cx = 9.55
text(s, cx, 1.65, W - M - cx, 4.9, [
    "**Round Robin and Random** send a fifth of all tasks to the server with 1/37 of the capacity: ≈ 850 s",
    "**Load-aware policies** reach ≈ 6 s on stable",
    "**P2C** is weak with 5 servers: a two-server sample misses the fastest server 60% of the time",
], size=15, bullets=True, space=12)

# ================================================================ 10 SLA chart
s = new_slide("Bursts overwhelm every policy", notes=(
    "SLA is 18 seconds, fixed before the experiments. On stable, the load-aware policies violate it for about "
    "3% of tasks. Under bursts, every policy is above 50%, because a burst offers about 160% of cluster "
    "capacity. No placement rule can avoid queueing then; the question is only how much each one reduces it."))
sla = {"stable": [59.2, 58.7, 7.4, 28.2, 2.9, 2.7, 3.4], "bursty": [60.0, 59.2, 57.8, 58.2, 54.1, 53.5, 53.9]}
cd = CategoryChartData()
cd.categories = POLICIES
cd.add_series("Stable", sla["stable"])
cd.add_series("Bursty", sla["bursty"])
gf = s.shapes.add_chart(XL_CHART_TYPE.COLUMN_CLUSTERED, Inches(M), Inches(1.45), Inches(8.6), Inches(5.4), cd)
ch = gf.chart
style_chart(ch)
color_series(ch, [BLUE, ORANGE])
ch.value_axis.minimum_scale, ch.value_axis.maximum_scale = 0, 70
ch.value_axis.tick_labels.number_format = '0"%"'
ch.value_axis.tick_labels.number_format_is_linked = False
axis_title(ch.value_axis, "SLA violations (response > 18 s)")
pl = ch.plots[0]
pl.gap_width, pl.overlap = 55, -5
pl.has_data_labels = True
pl.data_labels.number_format = '0"%"'
pl.data_labels.number_format_is_linked = False
pl.data_labels.font.size = Pt(11)
pl.data_labels.font.color.rgb = rgb(INK)
pl.data_labels.position = XL_LABEL_POSITION.OUTSIDE_END
stat(s, cx, 1.7, W - M - cx, "≥ 53%", "SLA violations under bursts, for every policy", vsize=44, lsize=15)
stat(s, cx, 3.35, W - M - cx, "≈ 160%", "offered load during a burst: queueing is unavoidable", color=BLUE,
     vsize=44, lsize=15)
text(s, cx, 5.05, W - M - cx, 1.5, "So the test is how much a policy **reduces** violations, not whether it "
     "eliminates them.", size=15, color=MUTED)

# ================================================================ 11 ablation
s = new_slide("Finding 2: the risk term did not beat its ablation", notes=(
    "Each dot is one seed: probabilistic minus weighted metric, below zero means the risk term helped. On "
    "stable it is worse on all five seeds, small but consistent; a sign test gives p about 0.03. Under bursts "
    "the dots straddle zero. The one favourable number, overload down 1.1 points, is smaller than its own "
    "standard deviation. The primary outcome is not met."))
pic, pw, ph = picture(s, FIG / "fig2_paired_by_seed.png", M, 1.4, W - 2 * M, 3.55)
cy = 1.4 + ph + 0.3
cwid = (W - 2 * M - 2 * 0.3) / 3
items = [
    ("Stable", "+0.29 s", "worse on 5 of 5 seeds", BLUE, TINT),
    ("Bursty", "+0.18 ± 0.85 s", "inside seed noise (3/5 won)", ORANGE, TINT),
    ("Verdict", "Not met", "primary outcome, frozen parameters", WHITE, INK),
]
for i, (lab, val, sub, c, fill) in enumerate(items):
    x = M + i * (cwid + 0.3)
    box(s, x, cy, cwid, H - 0.65 - cy, fill=fill)
    dark = fill == INK
    text(s, x + 0.3, cy + 0.15, cwid - 0.6, 0.35, lab.upper(), size=12, bold=True, color="F4A582" if dark else c)
    text(s, x + 0.3, cy + 0.5, cwid - 0.6, 0.6, val, size=26, bold=True, font=HEAD, color=WHITE if dark else INK)
    text(s, x + 0.3, cy + 1.1, cwid - 0.6, 0.4, sub, size=14, color="CBD5E1" if dark else MUTED)

# ================================================================ 12 calibration
s = new_slide("The risk estimate was well calibrated", notes=(
    "So is the model broken? No. The predicted risk of the chosen server matches the observed frequency of "
    "overload almost exactly: 0.62 versus 0.62 on stable, 0.74 versus 0.72 on bursty. The points sit on the "
    "diagonal. The problem is elsewhere."))
pic, pw, ph = picture(s, FIG / "fig3_calibration.png", M, 1.45, 5.9, 5.4, align="left")
rx = M + pw + 0.6
rw = W - M - rx
text(s, rx, 1.7, rw, 0.4, "Predicted risk vs. observed overload frequency", size=15, color=MUTED, bold=True)
for i, (lab, pred, obs, c) in enumerate([("Stable", "0.62", "0.62", BLUE), ("Bursty", "0.74", "0.72", ORANGE)]):
    y = 2.3 + i * 1.6
    box(s, rx, y, rw, 1.35)
    text(s, rx + 0.3, y + 0.15, 1.6, 0.4, lab, size=17, bold=True, color=c)
    text(s, rx + 0.3, y + 0.55, rw - 0.6, 0.7, f"{pred} predicted  ·  {obs} observed", size=24, bold=True,
         font=HEAD)
text(s, rx, 5.6, rw, 1.2, "The model is **not wrong**. Its predictions match reality on average. "
     "So why didn't it help?", size=17, color=INK)

# ================================================================ 13 not discriminative
s = new_slide("...but it could not tell servers apart", notes=(
    "This is the mechanism. A load-aware balancer equalises the servers, so their load curves move together. "
    "During each burst all five reach 10 to 20 times capacity at once, far above the 80% line. Every server has "
    "risk close to 1, the admission filter finds nobody eligible, and the score ranks exactly like the plain "
    "load score. That happened in 57% of stable decisions and 73% of bursty ones. Calibrated, but not "
    "discriminative."))
iw, ih = Image.open(FIG / "fig4_load_timeseries.png").size
pic, pw, ph = picture(s, FIG / "fig4_load_timeseries.png", M, 1.45 + (5.4 - 8.9 * ih / iw) / 2, 8.9, 5.4, align="left")
rx = M + pw + 0.4
rw = W - M - rx
stat(s, rx, 1.6, rw, "73%", "of bursty decisions: every server had P_{risk} > 0.5 (57% on stable)", vsize=54,
     lsize=15)
text(s, rx, 3.45, rw, 3.3, [
    "Balancing makes servers move **together**",
    "Bursts push all five to 10–20× capacity at once",
    "P_{risk} ≈ 1 everywhere, so S ranks exactly like L",
], size=15, bullets=True, space=10)

# ================================================================ 14 sensitivity
s = new_slide("Robust: no setting rescues the risk term", notes=(
    "Four axes were declared in advance and swept one at a time, plus a threshold-by-admission grid: 44 "
    "points, each run on both workloads and five seeds, with the ablation rerun at every point and outcomes "
    "always scored at the frozen thresholds. Raising theta cuts stable capacity pressure, but bursty pressure "
    "stays near 70% whatever theta is. The only helpful settings weaken the risk machinery."))
cd = CategoryChartData()
cd.categories = ["60", "80", "100", "120", "150"]
cd.add_series("Stable", [86.4, 57.3, 36.5, 24.3, 10.1])
cd.add_series("Bursty", [79.9, 72.5, 70.5, 69.1, 66.8])
gf = s.shapes.add_chart(XL_CHART_TYPE.LINE_MARKERS, Inches(M), Inches(1.45), Inches(5.9), Inches(5.0), cd)
ch = gf.chart
style_chart(ch)
ch.value_axis.minimum_scale, ch.value_axis.maximum_scale = 0, 100
ch.value_axis.tick_labels.number_format = '0"%"'
ch.value_axis.tick_labels.number_format_is_linked = False
axis_title(ch.value_axis, "Decisions under capacity pressure")
axis_title(ch.category_axis, "CPU threshold θ on the load signal (%)")
for series, c in zip(ch.plots[0].series, [BLUE, ORANGE]):
    series.smooth = False
    series.format.line.color.rgb = rgb(c)
    series.format.line.width = Pt(2.75)
    series.marker.style = XL_MARKER_STYLE.CIRCLE
    series.marker.size = 8
    series.marker.format.fill.solid()
    series.marker.format.fill.fore_color.rgb = rgb(c)
    series.marker.format.line.color.rgb = rgb(c)
rx = 7.0
rw = W - M - rx
axes = [
    ("Threshold θ", "Bursty pressure stays near 70% at every θ; Δ shows no trend"),
    ("Admission filter", "Off is the only consistent gain (≈ 1%, 5/5 seeds)"),
    ("Risk weight", "Stable gets steadily worse as the weight grows"),
    ("Window W", "5 to 40 samples: changes stay inside the noise"),
]
for i, (head, body) in enumerate(axes):
    y = 1.55 + i * 1.02
    marker(s, rx, y + 0.05, str(i + 1), fill=INK, d=0.42, size=14)
    text(s, rx + 0.65, y, rw - 0.65, 0.4, head, size=16, bold=True)
    text(s, rx + 0.65, y + 0.38, rw - 0.65, 0.6, body, size=14, color=MUTED)
box(s, rx, 5.75, rw, 1.0, fill=INK)
text(s, rx + 0.3, 5.8, rw - 0.6, 0.9, "Every setting that helps **weakens** the risk machinery.", size=16,
     color=WHITE, anchor=MSO_ANCHOR.MIDDLE)

# ================================================================ 15 threats
s = new_slide("Threats to validity", notes=(
    "Be upfront about these. The normal approximation is applied to a skewed, autocorrelated signal over only "
    "ten samples. Independence of CPU and memory overstates joint risk. Risk is computed from the past. The "
    "workload is synthetic and bursts hit all servers equally. Five servers and five seeds cannot resolve 1% "
    "effects. Weights were set by hand, though the sweep covers them."))
threats = [
    ("Normality", "Skewed, autocorrelated load signal, only W = 10 samples"),
    ("Independence", "CPU and memory are coupled through the queue, so joint risk is overstated"),
    ("Backward-looking", "Risk from past samples, not the state after placing the task"),
    ("Synthetic workload", "Bursts hit every server equally; real traces are more varied"),
    ("Scale", "5 servers and 5 seeds cannot resolve effects below ≈ 1%"),
    ("Hand-set weights", "Swept one axis at a time, not jointly optimised"),
]
tw = (W - 2 * M - 2 * 0.3) / 3
for i, (head, body) in enumerate(threats):
    row, col = divmod(i, 3)
    x = M + col * (tw + 0.3)
    y = 1.6 + row * 2.6
    box(s, x, y, tw, 2.3)
    marker(s, x + 0.3, y + 0.3, "!", fill=ORANGE, d=0.45, size=16)
    text(s, x + 0.3, y + 0.95, tw - 0.6, 0.45, head, size=18, bold=True)
    text(s, x + 0.3, y + 1.45, tw - 0.6, 0.8, body, size=15, color=MUTED)

# ================================================================ 16 conclusions
s = new_slide("Conclusions and next steps", dark=True, notes=(
    "Three takeaways: observe queued load; the risk term did not help here, robustly; and the reason is "
    "calibration without discrimination. The work also predicts where variance should help: servers with "
    "different volatility, stale metrics, and risk computed after the assignment. Those are the next experiments."))
take = [
    ("Observe queued load", "Including queued demand made load-aware policies ≈ 100× better than load-blind ones."),
    ("Risk did not help here", "No gain over the ablation on either workload or at any swept setting."),
    ("Calibrated ≠ useful", "A forecast that is right on average cannot rank options it rates equally."),
]
for i, (head, body) in enumerate(take):
    y = 1.65 + i * 1.6
    marker(s, M, y, str(i + 1))
    text(s, M + 0.8, y - 0.03, 6.3, 0.45, head, size=20, bold=True, color=WHITE, font=HEAD)
    text(s, M + 0.8, y + 0.48, 6.3, 0.9, body, size=15, color="CBD5E1")
nx = 8.0
box(s, nx, 1.55, W - M - nx, 4.85, fill="263A57")
text(s, nx + 0.35, 1.8, W - M - nx - 0.7, 0.4, "WHERE VARIANCE SHOULD HELP", size=13, bold=True, color="F4A582")
text(s, nx + 0.35, 2.35, W - M - nx - 0.7, 3.9, [
    "Servers with **different** volatility (noisy neighbours)",
    "Stale or sampled metrics, as in real monitoring",
    "Risk computed **after** placing the candidate task",
    "Real cluster traces, more servers and seeds",
], size=16, color=WHITE, bullets=True, space=12)

# ================================================================ 17 thanks
s = new_slide("Thank you — questions?", dark=True, notes=(
    "Point to the repository: code, 156 tests, decision log, full report and figures. Invite questions; the "
    "interview notes contain prepared answers for the likely tough ones."))
s.shapes.title.top = Inches(2.3)
text(s, M, 3.45, 11, 0.6, "Code, tests, decision log, report and figures:", size=18, color="CBD5E1")
text(s, M, 4.0, 11, 0.6, URL, size=22, color=WHITE, bold=True)
text(s, M, 4.9, 11, 0.5, "Abhay Nagesh Rao  ·  M.Tech (CSE), NIT Warangal", size=16, color="9FB3CC")

assert counter["n"] == N_SLIDES, counter["n"]
prs.core_properties.title = "Uncertainty-Aware Probabilistic Load Balancing"
prs.core_properties.author = "Abhay Nagesh Rao"
OUT.parent.mkdir(exist_ok=True)
prs.save(OUT)
print("saved", OUT)
