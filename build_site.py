"""
[ML Study] 2주차 노트 -> GitHub Pages용 단일 HTML 생성기

- Markdown 을 직접 파싱해 HTML 로 변환합니다 (외부 의존성 없음)
- 이미지는 리사이즈 후 base64 로 인라인 임베딩 (standalone HTML / PDF 변환 가능)
- 결과물: ml-week2.html

사용법:
    python build_site.py
"""

import base64
import html
import io
import os
import re

from PIL import Image

ROOT = os.path.dirname(os.path.abspath(__file__))
SOURCE_MD = os.path.join(ROOT, "ML_Study_Week02.md")
OUTPUT_HTML = os.path.join(ROOT, "ml-week2.html")

MAX_WIDTH = 1400
JPEG_QUALITY = 82


# --------------------------------------------------------------------------
# 이미지 처리
# --------------------------------------------------------------------------

_image_cache = {}


def embed_image(rel_path):
    """이미지를 리사이즈 후 base64 data URI 로 반환한다."""
    if rel_path in _image_cache:
        return _image_cache[rel_path]

    full_path = os.path.join(ROOT, rel_path)
    if not os.path.exists(full_path):
        return None

    with Image.open(full_path) as im:
        im = im.convert("RGB")
        if im.width > MAX_WIDTH:
            height = round(im.height * MAX_WIDTH / im.width)
            im = im.resize((MAX_WIDTH, height), Image.LANCZOS)

        buf = io.BytesIO()
        im.save(buf, format="JPEG", quality=JPEG_QUALITY, optimize=True)
        data = base64.b64encode(buf.getvalue()).decode("ascii")

    uri = f"data:image/jpeg;base64,{data}"
    _image_cache[rel_path] = uri
    return uri


# --------------------------------------------------------------------------
# 인라인 요소 파싱
# --------------------------------------------------------------------------

_INLINE_CODE = re.compile(r"`([^`]+)`")
_BOLD = re.compile(r"\*\*([^*]+)\*\*")
_ITALIC = re.compile(r"(?<![\*\w])\*([^*\n]+)\*(?!\*)")
_IMAGE = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)")
_LINK = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")


def render_inline(text):
    """코드/굵게/기울임/링크를 HTML 로 변환한다. (이미지는 별도 처리)"""
    placeholders = {}

    def stash_image(match):
        key = f"\x00IMG{len(placeholders)}\x00"
        placeholders[key] = embed_image(match.group(2)) or ""
        return key

    text = _IMAGE.sub(stash_image, text)

    text = html.escape(text, quote=False)
    text = _INLINE_CODE.sub(r"<code>\1</code>", text)
    text = _BOLD.sub(r"<strong>\1</strong>", text)
    text = _ITALIC.sub(r"<em>\1</em>", text)
    text = _LINK.sub(r'<a href="\2" target="_blank" rel="noopener">\1</a>', text)

    for key, uri in placeholders.items():
        text = text.replace(key, uri)

    return text


def is_standalone_image(line):
    return bool(re.fullmatch(r"!\[[^\]]*\]\([^)]+\)", line.strip()))


# --------------------------------------------------------------------------
# 블록 단위 파싱
# --------------------------------------------------------------------------


def slugify(text):
    cleaned = re.sub(r"[^\w가-힣\s-]", "", text).strip()
    return re.sub(r"\s+", "-", cleaned)


def convert(md_text):
    lines = md_text.splitlines()
    out = []
    toc = []
    i = 0
    total = len(lines)

    while i < total:
        line = lines[i]
        stripped = line.strip()

        # 빈 줄
        if not stripped:
            i += 1
            continue

        # 수식 블록 ($$ ... $$)
        if stripped.startswith("$$"):
            body = [stripped]
            if not (len(stripped) > 3 and stripped.endswith("$$")):
                i += 1
                while i < total and not lines[i].strip().endswith("$$"):
                    body.append(lines[i].strip())
                    i += 1
                if i < total:
                    body.append(lines[i].strip())
            i += 1
            formula = " ".join(b[2:-2].strip() if b.endswith("$$") else b.lstrip("$").strip()
                               for b in body if b.strip("$ ").strip())
            out.append(f'<div class="formula">{html.escape(formula)}</div>')
            continue

        # 코드 블록
        if stripped.startswith("```"):
            lang = stripped[3:].strip()
            body = []
            i += 1
            while i < total and not lines[i].strip().startswith("```"):
                body.append(lines[i])
                i += 1
            i += 1
            cls = f' class="language-{html.escape(lang)}"' if lang else ""
            code = html.escape("\n".join(body))
            out.append(f"<pre><code{cls}>{code}</code></pre>")
            continue

        # 수평선
        if re.fullmatch(r"-{3,}", stripped):
            out.append("<hr>")
            i += 1
            continue

        # 표
        if stripped.startswith("|") and i + 1 < total and re.fullmatch(
            r"\|[\s:\-|]+\|", lines[i + 1].strip()
        ):
            header = [c.strip() for c in stripped.strip("|").split("|")]
            i += 2
            rows = []
            while i < total and lines[i].strip().startswith("|"):
                rows.append([c.strip() for c in lines[i].strip().strip("|").split("|")])
                i += 1
            out.append("<div class=\"table-wrap\"><table><thead><tr>")
            out += [f"<th>{render_inline(c)}</th>" for c in header]
            out.append("</tr></thead><tbody>")
            for row in rows:
                out.append("<tr>" + "".join(f"<td>{render_inline(c)}</td>" for c in row) + "</tr>")
            out.append("</tbody></table></div>")
            continue

        # 인용문
        if stripped.startswith(">"):
            body = []
            while i < total and lines[i].strip().startswith(">"):
                body.append(re.sub(r"^\s*>\s?", "", lines[i]))
                i += 1
            inner, _ = convert("\n".join(body))
            out.append(f"<blockquote>{inner}</blockquote>")
            continue

        # 헤딩
        heading = re.match(r"^(#{1,6})\s+(.*)$", stripped)
        if heading:
            level = len(heading.group(1))
            text = heading.group(2).strip()
            anchor = slugify(text)
            if level <= 3:
                toc.append((level, text, anchor))
            out.append(f'<h{level} id="{anchor}">{render_inline(text)}</h{level}>')
            i += 1
            continue

        # 단독 이미지
        if is_standalone_image(stripped):
            match = _IMAGE.fullmatch(stripped)
            alt, src = match.group(1), match.group(2)
            uri = embed_image(src)
            if uri:
                out.append(
                    f'<figure><img src="{uri}" alt="{html.escape(alt, quote=True)}" '
                    f'loading="lazy" decoding="async">'
                    f"<figcaption>{html.escape(alt)}</figcaption></figure>"
                )
            i += 1
            continue

        # 목록
        if re.match(r"^([-*]|\d+\.)\s+", stripped):
            block, i = collect_list(lines, i)
            out.append(block)
            continue

        # 문단
        para = []
        while i < total:
            cur = lines[i].strip()
            if (
                not cur
                or cur.startswith("#")
                or cur.startswith("```")
                or cur.startswith(">")
                or re.fullmatch(r"-{3,}", cur)
                or re.match(r"^([-*]|\d+\.)\s+", cur)
                or is_standalone_image(cur)
                or cur.startswith("|")
            ):
                break
            para.append(cur)
            i += 1
        if para:
            out.append(f"<p>{render_inline(' '.join(para))}</p>")

    return "\n".join(out), toc


def collect_list(lines, start):
    """들여쓰기 깊이를 반영해 목록을 하나의 HTML 블록으로 만든다."""
    items = []
    i = start
    total = len(lines)

    while i < total:
        line = lines[i]
        if not line.strip():
            # 목록 뒤에 빈 줄이 있고, 다음 줄이 같은 깊이의 항목이면 계속
            if i + 1 < total and re.match(r"^\s*([-*]|\d+\.)\s+", lines[i + 1]):
                i += 1
                continue
            break

        match = re.match(r"^(\s*)([-*]|\d+\.)\s+(.*)$", line)
        if match:
            depth = len(match.group(1)) // 2
            items.append([depth, match.group(2), match.group(3).strip()])
            i += 1
            continue

        # 마커 없이 들여쓰기만 된 줄은 직전 항목의 줄바꿈 continuation 이다.
        if items and line[:1].isspace():
            items[-1][2] += " " + line.strip()
            i += 1
            continue

        break

    out = []
    stack = []  # 현재 열려 있는 ol/ul 태그
    in_item = False

    for depth, marker, text in items:
        tag = "ol" if marker[0].isdigit() else "ul"
        # 부모 목록 없이 깊이만 깊게 시작하는 경우를 방어한다.
        depth = min(depth, len(stack))

        while len(stack) > depth:
            if in_item:
                out.append("</li>")
                in_item = False
            out.append(f"</{stack.pop()}>")

        if len(stack) == depth:
            if in_item:
                out.append("</li>")
                in_item = False
            out.append(f"<{tag}>")
            stack.append(tag)
        elif stack[-1] != tag:
            if in_item:
                out.append("</li>")
                in_item = False
            out.append(f"</{stack.pop()}>")
            out.append(f"<{tag}>")
            stack.append(tag)

        out.append(f"<li>{render_inline(text)}")
        in_item = True

    while stack:
        if in_item:
            out.append("</li>")
            in_item = False
        out.append(f"</{stack.pop()}>")

    return "\n".join(out), i


# --------------------------------------------------------------------------
# 페이지 템플릿
# --------------------------------------------------------------------------

CSS = """
:root {
  --primary: #0f766e;
  --primary-light: #f0fdfa;
  --primary-dark: #115e59;
  --accent: #f59e0b;
  --bg: #f8fafc;
  --card: #ffffff;
  --text: #0f172a;
  --muted: #64748b;
  --border: #e2e8f0;
  --code-bg: #0f172a;
  --code-inline: #e2e8f0;
  --quote-bg: #fffbeb;
  --quote-border: #f59e0b;
}
* { box-sizing: border-box; margin: 0; padding: 0; }
html { scroll-behavior: smooth; scroll-padding-top: 88px; }
body {
  font-family: "Pretendard", -apple-system, BlinkMacSystemFont, system-ui, "Malgun Gothic", sans-serif;
  background: var(--bg);
  color: var(--text);
  line-height: 1.75;
  -webkit-font-smoothing: antialiased;
}

/* ---------- 상단 바 ---------- */
#progress {
  position: fixed; top: 0; left: 0; height: 3px; width: 0;
  background: linear-gradient(90deg, var(--primary), var(--accent));
  z-index: 100;
}
header {
  position: sticky; top: 0; z-index: 50;
  background: rgba(255,255,255,.88);
  backdrop-filter: blur(10px);
  border-bottom: 1px solid var(--border);
  padding: 14px 20px;
  display: flex; align-items: center; justify-content: space-between; gap: 16px;
}
header .brand { font-size: 15px; font-weight: 700; letter-spacing: -.01em; }
header .brand span { color: var(--primary); }
#navToggle {
  display: none; border: 1px solid var(--border); background: #fff;
  border-radius: 8px; padding: 7px 12px; font-size: 13px; cursor: pointer; font-family: inherit;
}

/* ---------- 레이아웃 ---------- */
.layout { display: flex; max-width: 1180px; margin: 0 auto; gap: 34px; padding: 34px 20px 90px; }
#toc {
  width: 250px; flex: 0 0 250px; position: sticky; top: 88px; align-self: flex-start;
  max-height: calc(100vh - 120px); overflow-y: auto;
  font-size: 13px; line-height: 1.6; border-right: 1px solid var(--border); padding-right: 16px;
}
#toc .toc-title {
  font-size: 11px; font-weight: 700; letter-spacing: .08em; color: var(--muted);
  text-transform: uppercase; margin-bottom: 10px;
}
#toc a {
  display: block; color: var(--muted); text-decoration: none;
  padding: 4px 8px; border-radius: 6px; transition: all .15s;
}
#toc a:hover { color: var(--primary); background: var(--primary-light); }
#toc a.lv2 { font-weight: 700; color: var(--text); margin-top: 8px; }
#toc a.lv3 { padding-left: 20px; }
main {
  flex: 1; min-width: 0; background: var(--card);
  border: 1px solid var(--border); border-radius: 16px;
  padding: 44px 48px 56px; box-shadow: 0 1px 3px rgba(0,0,0,.04);
}

/* ---------- 본문 ---------- */
h1 { font-size: 30px; line-height: 1.35; letter-spacing: -.02em; margin-bottom: 6px; }
h2 {
  font-size: 22px; letter-spacing: -.01em; margin: 52px 0 16px;
  padding-bottom: 10px; border-bottom: 2px solid var(--primary-light);
}
h2:first-of-type { margin-top: 40px; }
h3 { font-size: 17px; margin: 32px 0 10px; color: var(--primary-dark); }
h4 { font-size: 15px; margin: 24px 0 8px; color: var(--primary); }
p { margin: 12px 0; }
ul, ol { margin: 12px 0 12px 22px; }
li { margin: 6px 0; }
li > ul, li > ol { margin: 4px 0; }
hr { border: 0; border-top: 1px solid var(--border); margin: 34px 0; }
a { color: var(--primary); }
strong { font-weight: 700; }

code {
  font-family: "JetBrains Mono", ui-monospace, SFMono-Regular, Consolas, monospace;
  background: var(--code-inline); color: #0f172a;
  padding: 2px 6px; border-radius: 5px; font-size: .88em;
}
pre {
  background: var(--code-bg); border-radius: 12px;
  padding: 18px 20px; overflow-x: auto; margin: 16px 0;
  border: 1px solid #1e293b;
}
pre code {
  background: none; color: #e2e8f0; padding: 0; font-size: 13.5px;
  line-height: 1.7; display: block;
}

blockquote {
  background: var(--quote-bg); border-left: 4px solid var(--quote-border);
  border-radius: 0 10px 10px 0; padding: 14px 18px; margin: 16px 0;
}
blockquote p { margin: 6px 0; }
blockquote p:first-child { margin-top: 0; }
blockquote p:last-child { margin-bottom: 0; }
blockquote strong { color: #92400e; }
blockquote code { background: #fef3c7; }

.formula {
  background: var(--primary-light); border: 1px dashed var(--primary);
  border-radius: 10px; padding: 16px 20px; margin: 16px 0;
  text-align: center; font-size: 16px; color: var(--primary-dark);
  font-family: "JetBrains Mono", ui-monospace, Consolas, monospace;
}

.table-wrap { overflow-x: auto; margin: 18px 0; }
table { border-collapse: collapse; width: 100%; font-size: 14.5px; }
th, td { border: 1px solid var(--border); padding: 10px 13px; text-align: left; }
th { background: var(--primary-light); font-weight: 700; color: var(--primary-dark); }
tbody tr:nth-child(even) { background: #fbfdfd; }

figure { margin: 22px 0; }
figure img {
  width: 100%; height: auto; display: block;
  border: 1px solid var(--border); border-radius: 12px; background: #fff;
}
figcaption {
  text-align: center; font-size: 13px; color: var(--muted);
  margin-top: 9px; line-height: 1.5;
}

footer {
  text-align: center; color: var(--muted); font-size: 13px;
  padding: 26px 20px 46px;
}

@media (max-width: 900px) {
  .layout { flex-direction: column; padding: 20px 14px 70px; }
  #toc {
    display: none; width: auto; flex: none; position: static; max-height: none;
    border-right: 0; border-bottom: 1px solid var(--border); padding: 0 0 14px;
  }
  #toc.open { display: block; }
  #navToggle { display: block; }
  main { padding: 28px 20px 40px; }
  h1 { font-size: 24px; }
  h2 { font-size: 19px; }
  pre { padding: 14px 15px; }
  pre code { font-size: 12.5px; }
}
"""

JS = """
const bar = document.getElementById('progress');
const onScroll = () => {
  const h = document.documentElement;
  const p = h.scrollTop / (h.scrollHeight - h.clientHeight);
  bar.style.width = (p * 100) + '%';
};
document.addEventListener('scroll', onScroll, { passive: true });
onScroll();

document.getElementById('navToggle').addEventListener('click', function () {
  document.getElementById('toc').classList.toggle('open');
});
"""


def build_toc(entries):
    parts = ['<div class="toc-title">목차</div>']
    for level, text, anchor in entries:
        label = re.sub(r"[`*]", "", text)
        parts.append(f'<a class="lv{level}" href="#{anchor}">{html.escape(label)}</a>')
    return "\n".join(parts)


def main():
    with open(SOURCE_MD, encoding="utf-8") as f:
        md_text = f.read()

    body, toc = convert(md_text)

    doc = f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>[ML Study] 2주차 머신러닝 기초 탐구 노트</title>
<meta name="description" content="갈라파고스 핀치 데이터를:k-최근접 이웃, AI 질의응답으로 정리한 2주차 스터디 노트">
<link rel="stylesheet" as="style" crossorigin
  href="https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/static/pretendard.min.css">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;600&display=swap" rel="stylesheet">
<link rel="stylesheet"
  href="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/styles/github-dark-dimmed.min.css">
<script src="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/highlight.min.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/languages/python.min.js"></script>
<script>document.addEventListener('DOMContentLoaded', () => hljs.highlightAll());</script>
<style>{CSS}</style>
</head>
<body>
<div id="progress"></div>
<header>
  <div class="brand"><span>ML</span> Study · 2주차 노트</div>
  <button id="navToggle">목차</button>
</header>
<div class="layout">
  <nav id="toc">
{build_toc(toc)}
  </nav>
  <main>
{body}
  </main>
</div>
<footer>GitHub Pages로 공유한 스터디 기록입니다.</footer>
<script>{JS}</script>
</body>
</html>
"""

    with open(OUTPUT_HTML, "w", encoding="utf-8") as f:
        f.write(doc)

    size_mb = os.path.getsize(OUTPUT_HTML) / 1024 / 1024
    print(f"OK -> {OUTPUT_HTML}  ({size_mb:.2f} MB, 목차 {len(toc)}개)")


if __name__ == "__main__":
    main()
