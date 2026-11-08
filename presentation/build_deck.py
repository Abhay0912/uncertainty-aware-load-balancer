"""Build the project presentation.

Usage:
    .venv/bin/python presentation/build_deck.py .
"""

from __future__ import annotations

import sys
from pathlib import Path

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.util import Inches, Pt

REPO = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(".")
OUT = REPO / "presentation" / "uncertainty_aware_lb.pptx"

NAVY = "14253D"
BLUE = "2B78D6"
ORANGE = "E8643A"
TEAL = "2E9E8F"
INK = "1B2A41"
MUTED = "5B6575"
LIGHT = "EEF2F7"
LINE = "D5DBE3"
WHITE = "FFFFFF"
FONT = "Aptos"
HEAD = "Aptos Display"
W, H = 13.333, 7.5
M = 0.6

prs = Presentation()
prs.slide_width = Inches(W)
prs.slide_height = Inches(H)
blank = prs.slide_layouts[6]
slide_no = 0


def color(value: str) -> RGBColor:
    return RGBColor.from_string(value)


def add_text(slide, x, y, w, h, value, size=16, fill=INK, bold=False,
             align=PP_ALIGN.LEFT, font=FONT, italic=False):
    shape = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = shape.text_frame
    tf.clear()
    tf.word_wrap = True
    tf.vertical_anchor = MSO_ANCHOR.TOP
    for margin in ("margin_left", "margin_right", "margin_top", "margin_bottom"):
        setattr(tf, margin, 0)
    lines = value if isinstance(value, list) else [value]
    for i, line in enumerate(lines):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.text = line
        p.alignment = align
        p.space_after = Pt(5)
        for run in p.runs:
            run.font.name = font
            run.font.size = Pt(size)
            run.font.bold = bold
            run.font.italic = italic
            run.font.color.rgb = color(fill)
    return shape


def rect(slide, x, y, w, h, fill=LIGHT, line=None, radius=True):
    kind = MSO_SHAPE.ROUNDED_RECTANGLE if radius else MSO_SHAPE.RECTANGLE
    shape = slide.shapes.add_shape(kind, Inches(x), Inches(y), Inches(w), Inches(h))
    shape.fill.solid()
    shape.fill.fore_color.rgb = color(fill)
    if line:
        shape.line.color.rgb = color(line)
        shape.line.width = Pt(1)
    else:
        shape.line.fill.background()
    return shape


def slide(title, dark=False, notes=""):
    global slide_no
    slide_no += 1
    s = prs.slides.add_slide(blank)
    s.background.fill.solid()
    s.background.fill.fore_color.rgb = color(NAVY if dark else WHITE)
    add_text(s, M, 0.42, 11.6, 0.55, title, 30, WHITE if dark else INK, True, font=HEAD)
    if slide_no > 1:
        add_text(s, 11.9, 7.12, 0.8, 0.2, f"{slide_no} / 15", 10,
                 "AEB7C4" if dark else MUTED, align=PP_ALIGN.RIGHT)
    if notes:
        s.notes_slide.notes_text_frame.text = notes
    return s


def bullet_list(s, x, y, w, items, size=17, fill=MUTED, gap=0.55):
    for i, item in enumerate(items):
        yy = y + i * gap
        add_text(s, x, yy, 0.2, 0.25, "•", size, ORANGE, True)
        add_text(s, x + 0.28, yy, w - 0.28, 0.42, item, size, fill)


def stat(s, x, y, w, value, label, fill=ORANGE):
    add_text(s, x, y, w, 0.55, value, 38, fill, True, font=HEAD)
    add_text(s, x, y + 0.62, w, 0.5, label, 13, MUTED)


def bar_chart(s, x, y, w, h, labels, values, maximum, fill=BLUE, value_suffix=""):
    row_h = h / len(labels)
    for i, (label, value) in enumerate(zip(labels, values)):
        yy = y + i * row_h
        add_text(s, x, yy, 1.65, 0.28, label, 12, INK, True)
        rect(s, x + 1.75, yy + 0.03, w - 2.3, 0.25, "E5EAF1", radius=False)
        bw = max(0.03, (w - 2.3) * min(value / maximum, 1))
        rect(s, x + 1.75, yy + 0.03, bw, 0.25, fill, radius=False)
        add_text(s, x + w - 0.5, yy - 0.01, 0.5, 0.3,
                 f"{value:g}{value_suffix}", 11, INK, True, align=PP_ALIGN.RIGHT)


def metric_table(s, x, y, widths, headers, rows, row_h=0.42, font_size=11):
    xx = x
    for head, width in zip(headers, widths):
        rect(s, xx, y, width, row_h, NAVY, radius=False)
        add_text(s, xx + 0.06, y + 0.08, width - 0.12, 0.25, head, font_size, WHITE, True)
        xx += width
    for r, row in enumerate(rows):
        xx = x
        fill = WHITE if r % 2 == 0 else LIGHT
        for value, width in zip(row, widths):
            rect(s, xx, y + row_h * (r + 1), width, row_h, fill, LINE, radius=False)
            add_text(s, xx + 0.06, y + row_h * (r + 1) + 0.08, width - 0.12,
                     0.25, str(value), font_size, INK, value == row[0])
            xx += width


# 1 ---------------------------------------------------------------------------
s = slide("Uncertainty-Aware Predictive Task Placement", dark=True, notes=(
    "This presentation focuses on practical task-aware completion-time prediction. "
    "The method is evaluated against conventional load-balancing baselines."))
add_text(s, M, 2.0, 11.5, 0.9, "From server-level overload scores to task-specific completion forecasts",
         27, WHITE, True, font=HEAD)
add_text(s, M, 3.2, 10.5, 0.5, "A seeded simulation study of heterogeneous cloud servers", 19, "CBD5E1")
rect(s, M, 4.65, 5.3, 1.0, "203650")
add_text(s, M + 0.3, 4.88, 4.7, 0.45, "ECT-only is the primary policy", 20, WHITE, True)
add_text(s, M + 0.3, 5.35, 4.7, 0.25, "Uncertainty-aware ECT is the ablation", 14, "CBD5E1")
add_text(s, M, 6.55, 9.5, 0.35, "Abhay Nagesh Rao  ·  M.Tech (CSE), Cloud Computing  ·  NIT Warangal",
         14, "CBD5E1")

# 2 ---------------------------------------------------------------------------
s = slide("Why task-aware placement?", notes=(
    "A server-level score treats every incoming task alike. But a short memory-heavy task and a long CPU-heavy "
    "task can have different best servers even when aggregate load is similar. ECT answers the task-specific question."))
rect(s, M, 1.55, 5.7, 4.55, LIGHT)
add_text(s, M + 0.35, 1.85, 5.0, 0.4, "Aggregate load scoring", 21, INK, True, font=HEAD)
add_text(s, M + 0.35, 2.45, 4.9, 0.65, "Which server has the lowest current CPU, memory and response-time score?",
         18, MUTED)
for i, line in enumerate(["Task-independent", "Backward-looking", "Risk may be equal across servers"]):
    add_text(s, M + 0.35, 3.55 + i * 0.55, 4.7, 0.35, "• " + line, 16, ORANGE)
rect(s, 6.9, 1.55, 5.8, 4.55, NAVY)
add_text(s, 7.25, 1.85, 5.1, 0.4, "Completion-time prediction", 21, WHITE, True, font=HEAD)
add_text(s, 7.25, 2.45, 5.0, 0.65, "On which feasible server will this particular task finish soonest?",
         18, "CBD5E1")
for i, line in enumerate(["Task-specific", "Includes FIFO wait and resource fit", "Uses public duration estimates"]):
    add_text(s, 7.25, 3.55 + i * 0.55, 5.0, 0.35, "• " + line, 16, "F4A582")
add_text(s, M, 6.45, 11.8, 0.4, "ECT does not know the exact future finish time; it predicts it from scheduler-visible information.",
         16, MUTED, italic=True)

# 3 ---------------------------------------------------------------------------
s = slide("Architecture: predict, then select", notes=(
    "The practical policy receives immutable scheduler views. The duration estimator uses task classes, public "
    "hints and completed-task history. The shadow queue projection is local and pure, so evaluating candidates "
    "cannot mutate the real simulator. The uncertainty variant samples plausible service durations from history."))
boxes = [
    ("1", "Scheduler-visible state", "Task class / duration hint\nCPU, memory, queue, running work"),
    ("2", "Duration estimator", "Class prior + completed service history\nNo hidden actual work"),
    ("3", "Shadow FIFO projection", "Resource reservations\nHead-of-line blocking\nServer speed and tick order"),
    ("4", "ECT objective", "Mean completion time\nOptional q90 tail premium"),
]
for i, (n, head, body) in enumerate(boxes):
    x = M + i * 3.05
    rect(s, x, 2.0, 2.65, 2.65, NAVY if i == 3 else LIGHT)
    add_text(s, x + 0.25, 2.25, 0.4, 0.35, n, 18, ORANGE, True)
    add_text(s, x + 0.25, 2.8, 2.15, 0.55, head, 18, WHITE if i == 3 else INK, True, font=HEAD)
    add_text(s, x + 0.25, 3.65, 2.15, 0.8, body, 14, "CBD5E1" if i == 3 else MUTED)
    if i < 3:
        add_text(s, x + 2.72, 3.05, 0.3, 0.3, "→", 22, ORANGE, True, align=PP_ALIGN.CENTER)
add_text(s, M, 5.45, 11.8, 0.6,
         "Select argmin [ predicted mean + β × max(0, q90 − predicted mean) ]",
         23, ORANGE, True, align=PP_ALIGN.CENTER, font=HEAD)
add_text(s, M, 6.35, 11.8, 0.35, "β = 0 gives the ECT-only ablation; β > 0 gives uncertainty-aware ECT.",
         15, MUTED, align=PP_ALIGN.CENTER)

# 4 ---------------------------------------------------------------------------
s = slide("The shadow queue matches the simulator", notes=(
    "This is the correctness-critical component. The projection preserves FIFO order and head-of-line blocking. "
    "A candidate that fits immediately starts in the current dispatch tick. Completed tasks release resources, "
    "and queued tasks start at the next tick, exactly like the real server."))
steps = [
    ("Append", "Place the candidate after all existing FIFO work."),
    ("Fit", "Start only the queue head when CPU and memory fit."),
    ("Advance", "Reduce every running task by server speed for one tick."),
    ("Release", "Finish tasks, release reservations, start queue at next tick."),
]
for i, (head, body) in enumerate(steps):
    x = M + i * 3.05
    rect(s, x, 1.9, 2.65, 2.35, LIGHT)
    add_text(s, x + 0.25, 2.18, 2.1, 0.4, f"{i + 1}. {head}", 18, INK, True, font=HEAD)
    add_text(s, x + 0.25, 2.85, 2.1, 0.85, body, 15, MUTED)
    if i < 3:
        add_text(s, x + 2.72, 2.75, 0.3, 0.3, "→", 22, ORANGE, True, align=PP_ALIGN.CENTER)
rect(s, M, 4.9, 11.8, 1.2, NAVY)
add_text(s, M + 0.35, 5.17, 11.1, 0.65,
         "Tests cover immediate start, FIFO blocking, CPU/memory limits, concurrent tasks, simultaneous completion, "
         "infeasibility and horizon exhaustion.",
         16, WHITE, align=PP_ALIGN.CENTER)

# 5 ---------------------------------------------------------------------------
s = slide("Practical information contract", notes=(
    "The simulator needs hidden actual work to execute tasks, but a deployable scheduler cannot see it. "
    "The scheduler separates execution state from scheduling-visible state."))
rect(s, M, 1.65, 5.65, 4.5, NAVY)
add_text(s, M + 0.35, 1.95, 4.9, 0.4, "Scheduler may see", 21, WHITE, True, font=HEAD)
bullet_list(s, M + 0.35, 2.65, 4.8, [
    "CPU and memory demand",
    "Task class or duration estimate",
    "Server capacity and speed",
    "Running reservations and FIFO queue",
    "Completed-task history",
], 16, "CBD5E1", 0.58)
rect(s, 6.95, 1.65, 5.45, 4.5, LIGHT)
add_text(s, 7.3, 1.95, 4.8, 0.4, "Scheduler must not see", 21, INK, True, font=HEAD)
bullet_list(s, 7.3, 2.65, 4.7, [
    "Actual generated task work",
    "Exact remaining work",
    "Future completion tick",
    "Counterfactual outcomes",
], 16, MUTED, 0.72)
add_text(s, M, 6.5, 11.8, 0.35,
         "Practical ECT is an estimate based on information available at dispatch time.",
         15, ORANGE, True, align=PP_ALIGN.CENTER)

# 6 ---------------------------------------------------------------------------
s = slide("Matched experimental design", notes=(
    "Both pipelines use the same five seeds, the same stable and bursty traces, and the same first 1,000 tasks "
    "per trace for this compiled comparison. Each policy gets fresh servers and reset state."))
stat(s, M, 1.7, 2.7, "5", "seeds: 0–4", BLUE)
stat(s, 3.55, 1.7, 2.7, "2", "workloads", ORANGE)
stat(s, 6.4, 1.7, 2.7, "1,000", "matched tasks / trace", TEAL)
stat(s, 9.25, 1.7, 2.7, "18 s", "frozen SLA", INK)
cards = [
    ("Same trace", "Every policy sees the identical task sequence."),
    ("Fresh state", "Servers and policy state reset for every run."),
    ("Same baselines", "The method is compared with six conventional policies."),
    ("Paired metrics", "Differences are computed seed by seed."),
]
for i, (head, body) in enumerate(cards):
    x = M + (i % 2) * 6.0
    y = 3.35 + (i // 2) * 1.35
    rect(s, x, y, 5.55, 1.05, LIGHT)
    add_text(s, x + 0.25, y + 0.2, 2.0, 0.3, head, 17, INK, True)
    add_text(s, x + 2.05, y + 0.2, 3.15, 0.6, body, 14, MUTED)

# 7 ---------------------------------------------------------------------------
s = slide("Policies compared", notes=(
    "The six conventional policies are unchanged. The method includes ECT-only and uncertainty-aware ECT. The key scientific "
    "comparison is uncertainty-aware ECT versus ECT-only; comparing only against Weighted Metric would not isolate "
    "the value of uncertainty."))
policies = [
    ("Round Robin", "Cyclic order", MUTED),
    ("Random", "Uniform choice", MUTED),
    ("Weighted RR", "Capacity weights", BLUE),
    ("Least CPU", "Lowest CPU load", BLUE),
    ("Weighted Metric", "CPU + memory + response", BLUE),
    ("ECT-only", "Lowest predicted finish", TEAL),
    ("Uncertainty ECT", "Mean + tail premium", NAVY),
]
for i, (name, rule, fill) in enumerate(policies):
    row, col = divmod(i, 3)
    x = M + col * 4.1
    y = 1.55 + row * 1.65
    rect(s, x, y, 3.7, 1.25, fill)
    add_text(s, x + 0.25, y + 0.23, 3.2, 0.3, name, 17, WHITE, True, font=HEAD)
    add_text(s, x + 0.25, y + 0.7, 3.2, 0.3, rule, 13, "EAF0F6")
add_text(s, M, 6.65, 11.8, 0.3, "All practical policies use the same scheduler-visible interface.", 15, MUTED,
         align=PP_ALIGN.CENTER)

# 8 ---------------------------------------------------------------------------
s = slide("Stable workload: ECT reduces tail latency", notes=(
    "These are means over five seeds and the first 1,000 tasks per trace. ECT-only has the lowest p95 and SLA "
    "violation rate. Its mean response is close to Weighted Metric but throughput is higher. The uncertainty "
    "penalty is worse than ECT-only on this workload."))
labels = ["Round Robin", "Random", "Weighted RR", "P2C", "Least CPU", "Weighted Metric", "ECT-only", "Uncertainty"]
bar_chart(s, M, 1.45, 7.0, 4.9, labels,
          [231.3, 243.8, 8.8, 15.6, 7.0, 7.1, 7.7, 9.1], 260, BLUE, "s")
rect(s, 8.2, 1.65, 4.5, 1.1, TEAL)
add_text(s, 8.45, 1.9, 4.0, 0.35, "ECT-only p95: 14.21 s", 20, WHITE, True)
add_text(s, 8.45, 2.35, 4.0, 0.25, "Best among compared policies", 13, "EAF0F6")
rect(s, 8.2, 3.05, 4.5, 1.1, LIGHT)
add_text(s, 8.45, 3.28, 4.0, 0.35, "ECT-only SLA: 1.6%", 20, INK, True)
add_text(s, 8.45, 3.73, 4.0, 0.25, "Weighted Metric: 3.7%", 13, MUTED)
rect(s, 8.2, 4.45, 4.5, 1.1, LIGHT)
add_text(s, 8.45, 4.68, 4.0, 0.35, "ECT-only throughput: 4.329/s", 20, INK, True)
add_text(s, 8.45, 5.13, 4.0, 0.25, "Weighted Metric: 3.809/s", 13, MUTED)

# 9 ---------------------------------------------------------------------------
s = slide("Bursty workload: ECT improves latency and throughput", notes=(
    "Bursts create unavoidable overload, but ECT-only still has the best mean response and p95 among practical "
    "policies in this matched run. SLA violations remain high because offered demand exceeds capacity."))
bar_chart(s, M, 1.45, 7.0, 4.9, labels,
          [256.4, 273.7, 32.9, 37.5, 32.7, 32.9, 30.8, 31.6], 290, ORANGE, "s")
rect(s, 8.2, 1.65, 4.5, 1.1, ORANGE)
add_text(s, 8.45, 1.9, 4.0, 0.35, "ECT-only mean: 30.79 s", 20, WHITE, True)
add_text(s, 8.45, 2.35, 4.0, 0.25, "Weighted Metric: 32.87 s", 13, "EAF0F6")
rect(s, 8.2, 3.05, 4.5, 1.1, LIGHT)
add_text(s, 8.45, 3.28, 4.0, 0.35, "ECT-only p95: 67.41 s", 20, INK, True)
add_text(s, 8.45, 3.73, 4.0, 0.25, "Weighted Metric: 87.03 s", 13, MUTED)
rect(s, 8.2, 4.45, 4.5, 1.1, LIGHT)
add_text(s, 8.45, 4.68, 4.0, 0.35, "ECT-only throughput: 3.607/s", 20, INK, True)
add_text(s, 8.45, 5.13, 4.0, 0.25, "Weighted Metric: 2.830/s", 13, MUTED)

# 10 --------------------------------------------------------------------------
s = slide("All policies: baselines and ECT", notes=(
    "This table shows every policy in the matched evaluation. The method preserves the simulator, workloads and "
    "conventional baselines. ECT changes the decision signal, not the execution model."))
headers = ["Policy", "Stable mean", "Stable p95", "Stable SLA", "Bursty mean", "Bursty p95", "Bursty SLA"]
rows = [
    ["Round Robin", "231.27", "1414.63", "56.6%", "256.44", "1536.55", "56.6%"],
    ["Random", "243.82", "1471.71", "57.3%", "273.73", "1628.88", "56.8%"],
    ["Weighted RR", "8.77", "23.80", "8.9%", "32.85", "71.22", "64.3%"],
    ["P2C", "15.64", "52.41", "24.2%", "37.53", "101.60", "58.7%"],
    ["Least CPU", "6.99", "16.80", "3.9%", "32.70", "81.83", "61.5%"],
    ["Weighted Metric", "7.11", "16.00", "3.7%", "32.87", "87.03", "60.9%"],
    ["ECT-only", "7.70", "14.21", "1.6%", "30.79", "67.41", "62.5%"],
    ["Uncertainty ECT", "9.15", "16.00", "3.0%", "31.59", "68.01", "63.2%"],
]
metric_table(s, M, 1.25, [2.4, 1.45, 1.35, 1.25, 1.45, 1.35, 1.25], headers, rows, 0.52, 10)
add_text(s, M, 6.05, 11.8, 0.55,
         "Lower is better for latency and SLA violation rate. ECT improves the completion-time tail, but its "
         "uncertainty penalty is not yet a consistent gain.",
         17, ORANGE, True, align=PP_ALIGN.CENTER)

# 11 --------------------------------------------------------------------------
s = slide("Uncertainty adds no consistent benefit yet", notes=(
    "The important ablation is uncertainty-aware ECT versus ECT-only. Across five seeds, adding the tail "
    "premium worsens mean response, p95 and SLA violation rate on both workloads. It slightly improves bursty "
    "throughput, but not enough to establish a general benefit."))
metric_table(s, M, 1.65, [2.6, 3.0, 3.0, 2.7], ["Workload", "Metric", "Δ: uncertainty − ECT", "Wins / 5"],
             [
                 ["Stable", "Mean response", "+1.454 s", "0"],
                 ["Stable", "p95 response", "+1.790 s", "0"],
                 ["Stable", "SLA violations", "+1.42 pp", "0"],
                 ["Bursty", "Mean response", "+0.807 s", "0"],
                 ["Bursty", "p95 response", "+0.600 s", "0 (2 ties)"],
                 ["Bursty", "Throughput", "+0.0217/s", "3"],
             ], 0.55, 12)
rect(s, M, 5.75, 11.8, 0.8, NAVY)
add_text(s, M + 0.25, 5.97, 11.3, 0.35,
         "Current evidence supports ECT; it does not yet support claiming that uncertainty improves ECT.",
         18, WHITE, True, align=PP_ALIGN.CENTER)

# 12 --------------------------------------------------------------------------
s = slide("Why ECT is practical — and where it is limited", notes=(
    "ECT is practical because it predicts from information available at dispatch. Its quality depends on duration "
    "hints, task classes and historical service observations. On the "
    "original workloads, work is independent of CPU and memory, so a global prior is weak."))
rect(s, M, 1.55, 5.7, 4.75, NAVY)
add_text(s, M + 0.35, 1.85, 4.9, 0.35, "Practical assumptions", 21, WHITE, True, font=HEAD)
bullet_list(s, M + 0.35, 2.55, 4.8, [
    "Task class or public duration estimate exists",
    "Queue and resource reservations are observable",
    "Completed service history updates prequentially",
    "Forecast remains read-only",
], 16, "CBD5E1", 0.73)
rect(s, 6.95, 1.55, 5.45, 4.75, LIGHT)
add_text(s, 7.3, 1.85, 4.7, 0.35, "Limitations", 21, INK, True, font=HEAD)
bullet_list(s, 7.3, 2.55, 4.6, [
    "Synthetic workloads and only five seeds",
    "Duration estimates may be biased",
    "No shared-CPU contention model",
    "Bursts above capacity remain infeasible",
], 16, MUTED, 0.73)

# 13 --------------------------------------------------------------------------
s = slide("What the evaluation supports", dark=True, notes=(
    "State the claim narrowly. The project demonstrates that task-aware completion-time prediction is promising "
    "in this simulator. It does not demonstrate universal superiority or production readiness."))
add_text(s, M, 1.6, 6.7, 0.5, "Supported conclusion", 16, "F4A582", True)
add_text(s, M, 2.15, 6.6, 1.3,
         "Practical ECT improves the decision signal by modelling the incoming task’s predicted completion time, "
         "including queue wait and resource fit.",
         24, WHITE, True, font=HEAD)
add_text(s, M, 4.05, 6.5, 0.45, "Not yet supported", 16, "F4A582", True)
add_text(s, M, 4.55, 6.5, 1.0,
         "That the uncertainty penalty consistently improves ECT or that the method generalises to production systems.",
         20, "CBD5E1")
rect(s, 8.1, 1.75, 4.3, 3.8, "203650")
add_text(s, 8.45, 2.05, 3.6, 0.35, "Next experiments", 19, WHITE, True, font=HEAD)
bullet_list(s, 8.45, 2.75, 3.45, [
    "30–50 held-out seeds",
    "Noisy duration estimates",
    "Different server volatility",
    "Stale telemetry",
    "Background workloads",
], 15, "CBD5E1", 0.52)

# 14 --------------------------------------------------------------------------
s = slide("Takeaways", notes=(
    "Close with three points: the simulator and baselines remain fair; ECT is the new practical decision "
    "signal; and uncertainty is an open empirical question rather than a guaranteed improvement."))
takeaways = [
    ("1", "Load-aware baselines beat blind assignment", "Queues and heterogeneous capacity dominate the outcome."),
    ("2", "ECT improves task placement", "It forecasts completion rather than scoring servers in isolation."),
    ("3", "Uncertainty remains a hypothesis", "The current five-seed ablation is mixed-to-negative."),
]
for i, (n, head, body) in enumerate(takeaways):
    y = 1.65 + i * 1.45
    rect(s, M, y, 11.8, 1.05, LIGHT)
    rect(s, M + 0.2, y + 0.2, 0.6, 0.6, ORANGE)
    add_text(s, M + 0.2, y + 0.34, 0.6, 0.25, n, 16, WHITE, True, align=PP_ALIGN.CENTER)
    add_text(s, M + 1.05, y + 0.2, 4.2, 0.35, head, 20, INK, True, font=HEAD)
    add_text(s, M + 5.25, y + 0.25, 6.0, 0.35, body, 16, MUTED)

# 15 --------------------------------------------------------------------------
s = slide("Thank you — questions?", dark=True, notes=(
    "Invite questions about the information contract, shadow queue semantics, the ECT objective, or the "
    "evaluation design."))
add_text(s, M, 2.2, 10.8, 0.85, "Task-aware prediction from dispatch-time information.", 31, WHITE, True, font=HEAD)
add_text(s, M, 3.35, 9.5, 0.55,
         "Uncertainty-Aware Predictive Task Placement", 21, "CBD5E1")
add_text(s, M, 5.75, 10.0, 0.35,
         "github.com/Abhay0912/uncertainty-aware-load-balancer", 15, "9FB3CC")

prs.save(OUT)
print(f"Wrote {OUT} ({len(prs.slides)} slides)")
