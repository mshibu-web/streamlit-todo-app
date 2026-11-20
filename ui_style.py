"""見た目（色・形・配置）をまとめたモジュール。

- CSS：Streamlit の標準部品の見た目を整える（ベージュ・ホワイト・ブラウン基調）
- 小さな HTML の部品：カレンダーの色ラベルや、カードの文字

利用者が入力した文字（タイトルなど）は、必ず html.escape で「ただの文字」に変えてから
HTML に入れる。こうすると、入力に <script> などが含まれていても実行されない。
"""

import html

from todo_repository import Todo

# 優先度 → CSS で使う名前
PRIORITY_CODES = {"高": "high", "中": "mid", "低": "low"}


def priority_code(todo: Todo) -> str:
    """色分けに使う名前。完了済みは優先度に関係なく done（落ち着いた色）。"""
    return "done" if todo.is_completed else PRIORITY_CODES[todo.priority]


def chip_html(todo: Todo) -> str:
    """カレンダーの各日に表示する、色付きの小さなラベル。"""
    title = html.escape(todo.title)
    mark = "✓ " if todo.is_completed else ""
    return (
        f'<div class="todo-chip p-{priority_code(todo)}" title="{title}">'
        f'<span class="chip-dot"></span><span class="chip-text">{mark}{title}</span></div>'
    )


def more_chip_html(count: int) -> str:
    return f'<div class="todo-chip p-more"><span class="chip-text">他{count}件</span></div>'


def badge_html(todo: Todo) -> str:
    """優先度のバッジ（完了済みは「完了」）。"""
    text = "完了" if todo.is_completed else f"優先度 {todo.priority}"
    return f'<span class="badge p-{priority_code(todo)}">{text}</span>'


# 完了済みタイトルの先頭の印（絵文字の ✅ は緑色になるため、グレーになじむ文字の ✓ を使う）
DONE_MARK = '<span class="done-mark">✓</span>'


def card_text_html(todo: Todo, due_text: str, overdue: bool, show_date: bool = True) -> str:
    """カードの中身。左にタイトル、右に優先度・期限（狭い画面では折り返す）。"""
    title = html.escape(todo.title)
    title_class = "card-title done" if todo.is_completed else "card-title"
    due_class = "due overdue" if overdue and not todo.is_completed else "due"
    date_part = f'<span class="date">📅 {todo.due_date:%Y/%m/%d}</span>' if show_date else ""
    due_part = "" if todo.is_completed else f'<span class="{due_class}">{due_text}</span>'
    return (
        f'<div class="card-body">'
        f'<div class="{title_class}">{DONE_MARK if todo.is_completed else ""}<span class="title-text">{title}</span></div>'
        f'<div class="card-meta">{badge_html(todo)}{date_part}{due_part}</div>'
        f"</div>"
    )


# ページを「日本語・翻訳しない」と指定する（ブラウザの自動翻訳で「ToDo」が「トド」などになるのを防ぐ）
NO_TRANSLATE_SCRIPT = """
<script>
  const root = document.documentElement;
  root.setAttribute("lang", "ja");
  root.setAttribute("translate", "no");
  root.classList.add("notranslate");
  if (!document.querySelector('meta[name="google"]')) {
    const meta = document.createElement("meta");
    meta.name = "google";
    meta.content = "notranslate";
    document.head.appendChild(meta);
  }
</script>
"""

# ---------- CSS ----------

COLORS = {
    "bg": "#F7F2EA",  # やわらかいベージュ（背景）
    "surface": "#FFFFFF",  # ホワイト（カード）
    "text": "#3E3127",  # 濃いブラウン（文字）
    "muted": "#8C7B6B",  # うすいブラウン（補足の文字）
    "brand": "#8B6B4E",  # ブラウン（ボタン）
    "brand_dark": "#71553C",
    "line": "#E8DFD3",  # 線
    "today": "#F3E6D3",  # 今日のマス
    "selected": "#E9D6BC",  # 選択中のマス
}

CSS = """
<style>
:root {
  --bg: %(bg)s; --surface: %(surface)s; --text: %(text)s; --muted: %(muted)s;
  --brand: %(brand)s; --brand-dark: %(brand_dark)s; --line: %(line)s;
  --today: %(today)s; --selected: %(selected)s;
  --high-bg: #FCE4E1; --high-fg: #B5402F; --high-dot: #E06A5A;
  --mid-bg:  #FFF2C7; --mid-fg:  #8A6A00; --mid-dot:  #E8B923;
  --low-bg:  #DFEBF8; --low-fg:  #2F5F93; --low-dot:  #5B8FCB;
  --done-bg: #ECEBE9; --done-fg: #77736E; --done-dot: #A9A49E;  /* 完了済み：優先度に関係なくグレー */
}

/* ---- 全体 ---- */
.stApp { background: var(--bg); color: var(--text); }
[data-testid="stHeader"] { background: transparent; }
[data-testid="stMainBlockContainer"] { padding-top: 2rem; padding-bottom: 8rem; max-width: 1100px; }
h1, h2, h3 { color: var(--text); letter-spacing: .02em; }
button[kind="primary"], button[kind="primaryFormSubmit"] {
  background: var(--brand) !important; border-color: var(--brand) !important; color: #fff !important;
}
button[kind="primary"]:hover, button[kind="primaryFormSubmit"]:hover {
  background: var(--brand-dark) !important; border-color: var(--brand-dark) !important;
}
button[kind="secondary"] { border-radius: 10px; border-color: var(--line); background: var(--surface); color: var(--text); }
/* 標準の赤（テーマの色）をブラウンに置き換える：切り替えボタン・チェックボックス・ラジオボタン */
button[data-variant="segmented_control"] { background: var(--surface); }
button[data-variant="segmented_control"][aria-checked="true"] {
  background: var(--brand) !important; border-color: var(--brand) !important; color: #fff !important;
}
[data-testid="stCheckbox"] label:has(input:checked) > div:first-of-type {
  background: var(--brand) !important; border-color: var(--brand) !important;
}
[data-testid="stCheckbox"] label > div:first-of-type { width: 1.35rem; height: 1.35rem; border-radius: 6px; }
/* ラジオボタン：選ばれている丸だけをブラウンにする */
[data-testid="stRadioOption"][data-selected="true"] > div > div:first-child {
  background: var(--brand) !important; border-color: var(--brand) !important;
}
[data-testid="stRadioOption"][data-selected="true"] > div > div:first-child > div { background: #fff !important; }
/* カードの完了チェック：見えないラベルの分の余白をなくす */
[class*="st-key-row-"] [data-testid="stCheckbox"] [data-testid="stWidgetLabel"] { display: none; }

/* ---- ダッシュボード ---- */
.st-key-dashboard [data-testid="stMetric"] {
  background: var(--surface); border-radius: 16px; padding: 14px 18px;
  box-shadow: 0 1px 3px rgba(62,49,39,.08);
}
.st-key-dashboard [data-testid="stMetricLabel"] { color: var(--muted); }
.st-key-dashboard [data-testid="stMetricValue"] { color: var(--text); font-weight: 700; }

/* ---- カレンダー ---- */
.st-key-calendar {
  background: var(--surface); border-radius: 18px; padding: 14px;
  box-shadow: 0 1px 3px rgba(62,49,39,.08);
}
/* スマートフォンでも列を横に並べたままにする */
.st-key-calendar [data-testid="stHorizontalBlock"] { flex-wrap: nowrap !important; gap: 4px !important; }
.st-key-calendar [data-testid="stColumn"] { min-width: 0 !important; width: auto !important; }
.cal-title { text-align: center; margin: 0; font-size: 1.35rem; font-weight: 700; white-space: nowrap; }
.weekday { text-align: center; font-size: .8rem; color: var(--muted); padding: 4px 0; }
.weekday.sun { color: #C0574A; } .weekday.sat { color: #4A74A8; }

/* 日付のマス。キーは cell-(sel|no)-(td|no)-日付（sel=選択中、td=今日） */
[class*="st-key-cell-"] {
  position: relative; min-height: 96px; border-radius: 12px;
  padding: 30px 4px 6px !important; gap: 2px !important; transition: background .15s;
}
[class*="st-key-cell-"]:hover { background: #FAF5EE; }
[class*="st-key-cell-"][class*="-td-"] { background: var(--today); }
[class*="st-key-cell-sel-"], [class*="st-key-cell-sel-"]:hover {
  background: var(--selected); box-shadow: inset 0 0 0 2px var(--brand);
}
/* 日付ボタンをマス全体に広げる（マスのどこを押しても、その日が選ばれる）
   外側の箱 → stButton → 中の箱 → button の、すべての段を 100%% の大きさにする */
[class*="st-key-day_"] {
  position: absolute !important; inset: 0; z-index: 2; margin: 0 !important;
  width: 100%% !important; height: 100%% !important; max-width: none !important;
}
[class*="st-key-day_"] .stButton,
[class*="st-key-day_"] .stButton > div,
[class*="st-key-day_"] button { width: 100%% !important; height: 100%% !important; max-width: none !important; }
[class*="st-key-day_"] button {
  display: flex !important; justify-content: flex-start !important; align-items: flex-start !important;
  padding: 6px 8px !important; border: none !important; border-radius: 12px !important;
  background: transparent !important; color: var(--text) !important; font-weight: 600; cursor: pointer;
}
[class*="st-key-day_"] button:focus-visible { box-shadow: inset 0 0 0 2px var(--brand) !important; }
[class*="st-key-cell-"][class*="-td-"] [class*="st-key-day_"] button p {
  background: var(--brand); color: #fff; border-radius: 999px; padding: 0 7px;
}
/* マスの中のラベル：Streamlit 標準の「下側の負の余白」を消し、ラベルがマスの下にはみ出さないようにする */
[class*="st-key-cell-"] [data-testid="stMarkdown"],
[class*="st-key-cell-"] [data-testid="stMarkdownContainer"] { margin-bottom: 0 !important; }
.todo-chip {
  display: flex; align-items: center; gap: 4px; border-radius: 6px; padding: 1px 6px;
  font-size: .72rem; line-height: 1.5; margin: 1px 0; overflow: hidden; white-space: nowrap;
}
.todo-chip .chip-text { overflow: hidden; text-overflow: ellipsis; }
.todo-chip .chip-dot { width: 6px; height: 6px; border-radius: 50%%; flex: none; }
.p-high { background: var(--high-bg); color: var(--high-fg); } .p-high .chip-dot { background: var(--high-dot); }
.p-mid  { background: var(--mid-bg);  color: var(--mid-fg);  } .p-mid  .chip-dot { background: var(--mid-dot); }
.p-low  { background: var(--low-bg);  color: var(--low-fg);  } .p-low  .chip-dot { background: var(--low-dot); }
.p-done { background: var(--done-bg); color: var(--done-fg); } .p-done .chip-dot { background: var(--done-dot); }
.p-more { background: transparent; color: var(--muted); }

/* ---- カード（横幅いっぱい） ---- */
[class*="st-key-card-"] {
  width: 100%% !important; background: var(--surface); border-radius: 14px;
  border: 1px solid var(--line) !important; border-left: 6px solid var(--line) !important;
  padding: 12px 16px !important; box-shadow: 0 1px 2px rgba(62,49,39,.06);
}
[class*="st-key-card-high-"] { border-left-color: var(--high-dot) !important; }
[class*="st-key-card-mid-"]  { border-left-color: var(--mid-dot) !important; }
[class*="st-key-card-low-"]  { border-left-color: var(--low-dot) !important; }
[class*="st-key-card-done-"] { border-left-color: var(--done-dot) !important; background: #F4F3F1; }
[class*="st-key-card-done-"] .card-meta { color: var(--done-fg); }
[class*="st-key-row-"] { flex-wrap: nowrap !important; }
.card-body { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 4px 16px; width: 100%%; }
.card-title { flex: 1 1 240px; min-width: 0; font-weight: 600; font-size: 1.02rem; color: var(--text); overflow-wrap: anywhere; }
/* 完了済み：取り消し線は付けず、グレーの文字と先頭の ✓ で区別する */
.card-title.done { color: var(--done-fg); }
.done-mark { color: var(--done-fg); font-weight: 700; margin-right: .4em; }
.card-meta { display: flex; flex-wrap: wrap; align-items: center; gap: 10px; font-size: .82rem; color: var(--muted); }
.badge { border-radius: 999px; padding: 1px 10px; font-size: .75rem; font-weight: 600; white-space: nowrap; }
.due { white-space: nowrap; } .date { white-space: nowrap; }
.due.overdue { color: #B5402F; font-weight: 600; }

/* ---- 左下の＋ボタン（大きく目立つ） ---- */
.st-key-fab { position: fixed; left: 28px; bottom: 28px; z-index: 1000; width: auto !important; }
.st-key-fab button {
  width: 68px; height: 68px; border-radius: 50%% !important; padding: 0 !important;
  box-shadow: 0 8px 20px rgba(62,49,39,.30);
}
.st-key-fab button p { font-size: 2.2rem !important; line-height: 1; font-weight: 300; }

/* ---- スマートフォン ---- */
@media (max-width: 640px) {
  [data-testid="stMainBlockContainer"] { padding-left: 12px; padding-right: 12px; }
  .st-key-dashboard [data-testid="stHorizontalBlock"] { flex-wrap: wrap !important; gap: 8px !important; }
  .st-key-dashboard [data-testid="stColumn"] { min-width: calc(50%% - 8px) !important; flex: 1 1 calc(50%% - 8px) !important; }
  .st-key-calendar { padding: 8px 4px; }
  .cal-title { font-size: 1.05rem; }
  .st-key-cal_prev button, .st-key-cal_next button { min-width: 34px; padding: 0 6px !important; }
  .st-key-cal_today button { padding: 0 8px !important; }
  [class*="st-key-cell-"] { min-height: 62px; padding: 28px 1px 4px !important; }
  [class*="st-key-day_"] button { padding: 4px !important; font-size: .8rem; }
  .todo-chip { padding: 0; background: transparent !important; justify-content: center; }
  .todo-chip .chip-text { display: none; }
  .p-more .chip-text { display: inline; font-size: .6rem; }
  .st-key-fab { left: 18px; bottom: 18px; }
  .st-key-fab button { width: 64px; height: 64px; }
}
</style>
""" % COLORS
