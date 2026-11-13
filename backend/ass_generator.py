"""
ass_generator.py — Advanced SubStation Alpha (.ass) generator.

Converts SRT transcripts into kinetic, viral ASS subtitles with:
  - Exact frame canvas resolution (PlayResX/Y = video dimensions)
  - Proportional word-level timestamps & short 1-3 word punchy chunks
  - Power word / keyword detection (English & Hinglish)
  - Word-by-word active highlight & scale pop animations
  - 7 viral creator style presets:
      1. hormozi-yellow  (Impact/Anton, huge yellow highlight, bold outline)
      2. tiktok-box      (Inter Bold, 60% translucent dark pill box, cyan pop)
      3. mrbeast-green   (Luckiest Guy, neon green highlight, thick comic stroke)
      4. cyber-neon      (Orbitron, neon cyan fill, magenta outline, violet shadow)
      5. minimal-apple   (Inter Bold, clean white text, subtle shadow, sentence case)
      6. comic-bold      (Bangers, punchy white text, heavy outline, pink drop shadow)
      7. veed-impact     (Anton hero word on solid box + Inter context, letter stagger)
"""

from __future__ import annotations
import re
from dataclasses import dataclass
from typing import Optional


# ---------------------------------------------------------------------------
# Color & Time Helpers
# ---------------------------------------------------------------------------
def hex_to_ass(hex_rgb: str, alpha: int = 0) -> str:
    """'#FFE600' -> '&H0000E6FF'. alpha: 0 = opaque, 255 = fully transparent."""
    h = hex_rgb.lstrip("#")
    if len(h) != 6:
        h = "FFFFFF"
    r, g, b = h[0:2], h[2:4], h[4:6]
    return f"&H{alpha:02X}{b}{g}{r}".upper()


def tag_color(hex_rgb: str) -> str:
    """For inline tags: '#FFE600' -> '&H00E6FF&'."""
    h = hex_rgb.lstrip("#")
    if len(h) != 6:
        h = "FFFFFF"
    return f"&H{h[4:6]}{h[2:4]}{h[0:2]}&".upper()


def opacity_to_alpha(opacity_pct: float) -> int:
    """CSS opacity (100 = solid) -> ASS alpha byte (0 = solid)."""
    return max(0, min(255, round((100.0 - opacity_pct) / 100.0 * 255)))


def ass_time(t: float) -> str:
    """Seconds -> H:MM:SS.cc (centiseconds)."""
    cs = int(round(max(0.0, t) * 100))
    h, rem = divmod(cs, 360000)
    m, rem = divmod(rem, 6000)
    s, cs = divmod(rem, 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def ass_escape(text: str) -> str:
    """Escape transcript text safely for ASS format."""
    text = text.replace("\\", "").replace("{", "(").replace("}", ")")
    return text.replace("\r", "").replace("\n", r"\N").strip()


# ---------------------------------------------------------------------------
# Data Models
# ---------------------------------------------------------------------------
@dataclass
class Word:
    text: str
    start: float
    end: float
    kw: bool = False


@dataclass
class StyleSpec:
    font: str
    size: float
    bold: bool = False
    primary: str = "#FFFFFF"
    highlight: str = "#FFE600"
    outline_color: str = "#000000"
    outline_alpha: int = 0
    back_color: str = "#000000"
    back_alpha: int = 128
    border_style: int = 1         # 1 = outline + shadow, 3 = opaque box
    outline: float = 0
    shadow: float = 0
    spacing: float = 0
    alignment: int = 2
    margin_v: int = 0
    margin_lr: int = 0
    uppercase: bool = False
    pop: bool = True
    highlight_mode: str = "active"  # "active" | "keywords" | "both" | "none"
    active_scale: int = 100


# ---------------------------------------------------------------------------
# Style Presets Definitions
# ---------------------------------------------------------------------------
PRESETS = {
    "hormozi-yellow": {
        "id": "hormozi-yellow",
        "name": "Hormozi Yellow",
        "description": "Bold, punchy, high-contrast yellow highlight (Hormozi style)",
        "font": "Anton",
        "bold": False,
        "primary": "#FFFFFF",
        "highlight": "#FFE600",
        "outline_color": "#000000",
        "outline_alpha": 0,
        "back_color": "#000000",
        "back_alpha": 128,
        "border_style": 1,
        "uppercase": True,
        "pop": True,
        "highlight_mode": "active",
        "active_scale": 110,
        "default_position": {"portrait": "center", "landscape": "bottom"},
        "layout": {
            "portrait":  {"fontSize": 100, "outline": 8,  "shadow": 4, "spacing": 0,   "boxPadding": 0},
            "landscape": {"fontSize": 64,  "outline": 5,  "shadow": 3, "spacing": 0,   "boxPadding": 0},
        },
    },
    "tiktok-box": {
        "id": "tiktok-box",
        "name": "TikTok Dark Box",
        "description": "Clean white text inside a sleek 60% translucent dark pill box",
        "font": "Inter",
        "bold": True,
        "primary": "#FFFFFF",
        "highlight": "#25F4EE",
        "outline_color": "#000000",
        "outline_alpha": opacity_to_alpha(60),
        "back_color": "#000000",
        "back_alpha": opacity_to_alpha(60),
        "border_style": 3,
        "uppercase": False,
        "pop": False,
        "highlight_mode": "active",
        "active_scale": 100,
        "default_position": {"portrait": "bottom", "landscape": "bottom"},
        "layout": {
            "portrait":  {"fontSize": 56,  "outline": 0,  "shadow": 0, "spacing": 0,   "boxPadding": 16},
            "landscape": {"fontSize": 42,  "outline": 0,  "shadow": 0, "spacing": 0,   "boxPadding": 12},
        },
    },
    "mrbeast-green": {
        "id": "mrbeast-green",
        "name": "MrBeast Pop Green",
        "description": "High-energy comic display font with neon green pop and deep stroke",
        "font": "Luckiest Guy",
        "bold": False,
        "primary": "#FFFFFF",
        "highlight": "#00FF66",
        "outline_color": "#000000",
        "outline_alpha": 0,
        "back_color": "#000000",
        "back_alpha": 0,
        "border_style": 1,
        "uppercase": True,
        "pop": True,
        "highlight_mode": "active",
        "active_scale": 112,
        "default_position": {"portrait": "center", "landscape": "bottom"},
        "layout": {
            "portrait":  {"fontSize": 96,  "outline": 10, "shadow": 6, "spacing": 0,   "boxPadding": 0},
            "landscape": {"fontSize": 60,  "outline": 7,  "shadow": 4, "spacing": 0,   "boxPadding": 0},
        },
    },
    "cyber-neon": {
        "id": "cyber-neon",
        "name": "Cyberpunk Neon",
        "description": "Futuristic cyan text with vivid magenta outline and violet shadow",
        "font": "Orbitron",
        "bold": True,
        "primary": "#00F0FF",
        "highlight": "#FFE600",
        "outline_color": "#FF2BD6",
        "outline_alpha": 0,
        "back_color": "#7A00FF",
        "back_alpha": 128,
        "border_style": 1,
        "uppercase": True,
        "pop": True,
        "highlight_mode": "active",
        "active_scale": 105,
        "default_position": {"portrait": "bottom", "landscape": "bottom"},
        "layout": {
            "portrait":  {"fontSize": 72,  "outline": 4,  "shadow": 6, "spacing": 2,   "boxPadding": 0},
            "landscape": {"fontSize": 48,  "outline": 3,  "shadow": 4, "spacing": 1.5, "boxPadding": 0},
        },
    },
    "minimal-apple": {
        "id": "minimal-apple",
        "name": "Minimal Apple",
        "description": "Elegant, understated white text with subtle shadow (ideal for tutorials)",
        "font": "Inter",
        "bold": True,
        "primary": "#FFFFFF",
        "highlight": "#FFD60A",
        "outline_color": "#000000",
        "outline_alpha": opacity_to_alpha(60),
        "back_color": "#000000",
        "back_alpha": opacity_to_alpha(50),
        "border_style": 1,
        "uppercase": False,
        "pop": False,
        "highlight_mode": "keywords",
        "active_scale": 100,
        "default_position": {"portrait": "bottom", "landscape": "bottom"},
        "layout": {
            "portrait":  {"fontSize": 52,  "outline": 3,  "shadow": 2, "spacing": 0,   "boxPadding": 0},
            "landscape": {"fontSize": 40,  "outline": 2,  "shadow": 1.5, "spacing": 0, "boxPadding": 0},
        },
    },
    "comic-bold": {
        "id": "comic-bold",
        "name": "Comic Bold",
        "description": "Meme & comic sticker style with thick black outline and hot pink shadow",
        "font": "Bangers",
        "bold": False,
        "primary": "#FFFFFF",
        "highlight": "#FFE600",
        "outline_color": "#000000",
        "outline_alpha": 0,
        "back_color": "#FF3D71",
        "back_alpha": 0,
        "border_style": 1,
        "uppercase": True,
        "pop": True,
        "highlight_mode": "active",
        "active_scale": 110,
        "default_position": {"portrait": "center", "landscape": "bottom"},
        "layout": {
            "portrait":  {"fontSize": 104, "outline": 12, "shadow": 8, "spacing": 1,   "boxPadding": 0},
            "landscape": {"fontSize": 66,  "outline": 8,  "shadow": 5, "spacing": 1,   "boxPadding": 0},
        },
    },
    "no-subs": {
        "id": "no-subs",
        "name": "No Subtitles (Audio Clean Only)",
        "description": "Clean audio export without burning captions onto the video",
        "font": "Inter",
        "bold": False,
        "primary": "#FFFFFF",
        "highlight": "#94A3B8",
        "outline_color": "#000000",
        "outline_alpha": 0,
        "back_color": "#000000",
        "back_alpha": 0,
        "border_style": 1,
        "uppercase": False,
        "pop": False,
        "highlight_mode": "static",
        "active_scale": 100,
        "default_position": {"portrait": "bottom", "landscape": "bottom"},
        "layout": {
            "portrait":  {"fontSize": 64, "outline": 0, "shadow": 0, "spacing": 0, "boxPadding": 0},
            "landscape": {"fontSize": 48, "outline": 0, "shadow": 0, "spacing": 0, "boxPadding": 0},
        },
    },
    "veed-impact": {
        "id": "veed-impact",
        "name": "VEED Hero Box",
        "description": "3-layer hero: giant keyword on a solid color box + tracked context lines with letter stagger",
        # hero word (Anton, opaque box)
        "font": "Anton",
        "bold": False,
        "primary": "#000000",          # hero text color (black on box)
        "highlight": "#FF1E1E",        # box fill color — user can override
        "outline_color": "#FF1E1E",    # same as box fill for BorderStyle=3
        "outline_alpha": 0,
        "back_color": "#FF1E1E",
        "back_alpha": 0,
        "border_style": 3,
        "uppercase": True,
        "pop": False,
        "highlight_mode": "none",
        "active_scale": 100,
        # context line (Inter Bold, no box)
        "ctx_font": "Inter",
        "ctx_bold": True,
        "ctx_color": "#FFFFFF",
        "ctx_outline_color": "#000000",
        "ctx_outline": 2.5,            # thin black outline for legibility
        "ctx_shadow": 1.5,
        "ctx_spacing": 1.5,
        "ctx_border_style": 1,
        "default_position": {"portrait": "center", "landscape": "center"},
        "layout": {
            "portrait":  {"heroSize": 110, "ctxSize": 44, "outline": 0, "shadow": 0, "spacing": 0, "boxPadding": 22},
            "landscape": {"heroSize": 72,  "ctxSize": 32, "outline": 0, "shadow": 0, "spacing": 0, "boxPadding": 16},
        },
    },
}


# ---------------------------------------------------------------------------
# SRT Parsing & Word Timing Distribution
# ---------------------------------------------------------------------------
SRT_BLOCK = re.compile(
    r"(\d+)\s*\n(\d\d):(\d\d):(\d\d)[,.](\d{3})\s*-->\s*(\d\d):(\d\d):(\d\d)[,.](\d{3})\s*\n(.*?)(?=\n\s*\n|\Z)",
    re.S,
)


def parse_srt(srt_content: str) -> list[tuple[float, float, str]]:
    """Parse SRT into (start_seconds, end_seconds, text) items."""
    results = []
    normalized = srt_content.replace("\r\n", "\n")
    for m in SRT_BLOCK.finditer(normalized):
        h1, m1, s1, ms1, h2, m2, s2, ms2 = map(int, m.groups()[1:9])
        start = h1 * 3600 + m1 * 60 + s1 + ms1 / 1000.0
        end = h2 * 3600 + m2 * 60 + s2 + ms2 / 1000.0
        text = re.sub(r"<[^>]+>", "", m.group(10)).replace("\n", " ").strip()
        if text:
            results.append((start, end, text))
    return results


def distribute_words(text: str, start: float, end: float) -> list[Word]:
    """Proportionally distribute timestamps across words in a segment."""
    tokens = text.split()
    if not tokens:
        return []
    weights = [max(len(re.sub(r"\W", "", t)), 1) + 1 for t in tokens]
    total_wt = sum(weights)
    dur = max(0.1, end - start)
    out: list[Word] = []
    t = start
    for tok, wt in zip(tokens, weights):
        d = dur * wt / total_wt
        out.append(Word(text=tok, start=t, end=t + d))
        t += d
    return out


def chunk_words(words: list[Word], max_words: int = 3, max_chars: int = 18, pause: float = 0.35) -> list[list[Word]]:
    """Group words into short punchy caption chunks (1 to 3 words)."""
    chunks: list[list[Word]] = []
    cur: list[Word] = []
    for w in words:
        if not w.text.strip():
            continue
        if cur:
            chars = sum(len(x.text) + 1 for x in cur) + len(w.text)
            last_ch = cur[-1].text[-1:]
            hard_break = (bool(last_ch) and last_ch in ".?!,;:") or (w.start - cur[-1].end > pause)
            if len(cur) >= max_words or chars > max_chars or hard_break:
                chunks.append(cur)
                cur = []
        cur.append(w)
    if cur:
        chunks.append(cur)
    return chunks


# ---------------------------------------------------------------------------
# Power Word / Keyword Detection
# ---------------------------------------------------------------------------
STOP_WORDS = set("""
a an the and or but if is are was were be been am do does did have has had to of in on at for with
it its this that these those you your i me my we our they their he she him her as by from so just very
ka ki ke ko se me mein hai hain tha thi the ho hoga hogi to toh ye yeh wo woh aur par pe ek bhi kya
""".split())

POWER_WORDS = set("""
money cash free secret million billion crore lakh rich broke profit loss mistake never always stop
best worst biggest easy fast instantly proven truth lie shocking insane crazy viral win lose growth fail
paisa paise rupaye ameer garib galti raaz sach jhooth kabhi sabse bahut zaroor khatarnak fayda nuksan
""".split())

NUM_RE = re.compile(r"^[^\w]*[$₹€£]?\d[\d,.]*(k|m|b|x|%|lakh|crore)?[^\w]*$", re.I)


def score_word(word: str, idx: int, total: int) -> float:
    w = re.sub(r"[^\w₹$%]", "", word).lower()
    if not w or w in STOP_WORDS:
        return -9.0
    s = 0.0
    if NUM_RE.match(word):
        s += 5.0
    if w in POWER_WORDS:
        s += 4.0
    if word.isupper() and len(w) > 2:
        s += 3.0
    s += min(len(w), 10) / 5.0
    if idx == total - 1:
        s += 0.5
    return s


def mark_keywords(words: list[Word], per_chunk: int = 1, min_score: float = 2.0) -> list[Word]:
    """Tag high-impact keywords with .kw = True."""
    for i, w in enumerate(words):
        if score_word(w.text, i, len(words)) >= min_score:
            w.kw = True
    return words


# ---------------------------------------------------------------------------
# ASS Construction & Formatting
# ---------------------------------------------------------------------------
POP_ANIM = r"{\fscx85\fscy85\t(0,90,\fscx104\fscy104)\t(90,170,\fscx100\fscy100)}"


def render_chunk_text(chunk: list[Word], active_idx: int, s: StyleSpec) -> str:
    """Format chunk text with active word or keyword color overrides."""
    out = []
    for j, w in enumerate(chunk):
        t = ass_escape(w.text.upper() if s.uppercase else w.text)
        is_active = (j == active_idx and s.highlight_mode in ("active", "both"))
        is_kw = (w.kw and s.highlight_mode in ("keywords", "both"))
        if is_active or is_kw:
            grow = f"\\fscx{s.active_scale}\\fscy{s.active_scale}" if s.active_scale != 100 else ""
            shrink = r"\fscx100\fscy100" if s.active_scale != 100 else ""
            out.append(f"{{\\1c{tag_color(s.highlight)}{grow}}}{t}{{\\1c{tag_color(s.primary)}{shrink}}}")
        else:
            out.append(t)
    return " ".join(out)


def chunk_to_events(chunk: list[Word], next_start: Optional[float], s: StyleSpec, tail: float = 0.15) -> list[tuple[float, float, str]]:
    """Build sequence of word-state events for one chunk."""
    last_end = chunk[-1].end + tail
    if next_start is not None:
        last_end = min(last_end, next_start)
    last_end = max(last_end, chunk[-1].end)

    events = []
    if s.highlight_mode in ("active", "both"):
        for i, w in enumerate(chunk):
            end_t = chunk[i + 1].start if i + 1 < len(chunk) else last_end
            events.append((w.start, max(end_t, w.start + 0.04), render_chunk_text(chunk, i, s)))
    else:
        events.append((chunk[0].start, max(last_end, chunk[0].start + 0.04), render_chunk_text(chunk, -1, s)))

    if s.pop and events:
        a, b, t = events[0]
        events[0] = (a, b, POP_ANIM + t)
    return events


# ---------------------------------------------------------------------------
# VEED Hero Box — Letter Stagger & Multi-layer ASS
# ---------------------------------------------------------------------------
STAGGER_MS_PER_CHAR = 28   # ms between each character fade-in
STAGGER_FADE_MS     = 110  # ms for each character to fade from transparent → opaque
MAX_STAGGER_CHARS   = 22   # characters beyond this appear instantly (no lag build-up)


def build_stagger_text(text: str, start_offset_ms: int = 0) -> str:
    """
    Wraps every character of *text* in ASS alpha-stagger tags so each letter
    fades in softly, one after another.

    Characters beyond MAX_STAGGER_CHARS are shown immediately (alpha 0 from start)
    to prevent long lines from feeling slow.
    """
    result = []
    for i, ch in enumerate(text):
        if i >= MAX_STAGGER_CHARS:
            # Show immediately — no stagger tag needed
            result.append(ch)
            continue
        t0 = start_offset_ms + i * STAGGER_MS_PER_CHAR
        t1 = t0 + STAGGER_FADE_MS
        # Start fully transparent (\alpha&HFF&), fade to fully opaque (\alpha&H00&)
        tag = "{\\alpha&HFF&\\t(" + str(t0) + "," + str(t1) + ",\\alpha&H00&)}"
        result.append(tag + ch)
    return "".join(result)


def _pick_hero_word(chunk: list[Word]) -> int:
    """
    Return the index of the single best hero keyword in a chunk.

    Strategy (always guarantees a hero word):
      1. Prefer highest-scoring power/impact word (score >= 0.5)
      2. If nothing scores, pick the longest non-stopword
      3. Last resort: pick the last word in the chunk
    """
    import re as _re

    best_idx   = -1
    best_score = 0.5   # very low threshold — almost any real word qualifies
    for i, w in enumerate(chunk):
        sc = score_word(w.text, i, len(chunk))
        if sc > best_score:
            best_score = sc
            best_idx   = i

    if best_idx != -1:
        return best_idx

    # Fallback 1: pick longest non-stopword
    longest_idx = -1
    longest_len = 0
    for i, w in enumerate(chunk):
        clean = _re.sub(r"[^\w]", "", w.text).lower()
        if clean and clean not in STOP_WORDS and len(clean) > longest_len:
            longest_len = len(clean)
            longest_idx = i
    if longest_idx != -1:
        return longest_idx

    # Fallback 2: last word
    return len(chunk) - 1


def build_hero_box_ass(
    chunks: list[list[Word]],
    preset: dict,
    width: int,
    height: int,
    highlight_color: Optional[str] = None,
) -> str:
    """
    Generate a multi-layer ASS document for the veed-impact preset.

    Layout (portrait, bottom-third anchor):
      ┌─────────────────────────────┐
      │                             │
      │   [context words before]    │  ← VeedCtx, stagger fade-in
      │   ████ HERO WORD ████       │  ← VeedHero, solid box, scale-pop
      │   [context words after]     │  ← VeedCtx, stagger fade-in (+60ms)
      └─────────────────────────────┘

    The 3-layer stack is anchored to the bottom-third of the frame
    (not dead center) so it doesn't cover the subject's face.
    """
    is_portrait = height >= width * 1.1
    orient = "portrait" if is_portrait else "landscape"
    lay = preset["layout"][orient]

    res_k = min(width, height) / 1080.0  # resolution scale factor

    hero_size = round(lay["heroSize"] * res_k, 1)
    ctx_size  = round(lay["ctxSize"]  * res_k, 1)

    # Box fill — user highlight_color overrides preset default
    box_color       = highlight_color or preset["highlight"]
    box_ass         = hex_to_ass(box_color, 0)         # opaque fill
    hero_txt_ass    = hex_to_ass(preset["primary"], 0)  # black text on box
    ctx_primary_ass = hex_to_ass(preset["ctx_color"], 0)
    ctx_outline_ass = hex_to_ass(preset["ctx_outline_color"], 0)

    ctx_outline_px = round(preset["ctx_outline"] * res_k, 1)
    ctx_shadow_px  = round(preset["ctx_shadow"]  * res_k, 1)
    ctx_spacing_px = round(preset["ctx_spacing"] * res_k, 1)
    box_padding_px = round(lay["boxPadding"] * res_k, 1)

    ctx_bold_flag = -1 if preset.get("ctx_bold") else 0

    # ── Style definitions ──
    # VeedHero: Anton, giant, border_style=3 (opaque box), \an5 (center)
    hero_style = (
        f"Style: VeedHero,{preset['font']},{hero_size:g},"
        f"{hero_txt_ass},{hero_txt_ass},"
        f"{box_ass},{box_ass},"
        f"0,0,0,0,100,100,0,0,3,"
        f"{box_padding_px:g},0,5,0,0,0,1"
    )

    # VeedCtx: Inter Bold, medium, border_style=1 (outline+shadow), \an5
    ctx_style = (
        f"Style: VeedCtx,{preset['ctx_font']},{ctx_size:g},"
        f"{ctx_primary_ass},{ctx_primary_ass},"
        f"{ctx_outline_ass},&H00000000,"
        f"{ctx_bold_flag},0,0,0,100,100,{ctx_spacing_px:g},0,1,"
        f"{ctx_outline_px:g},{ctx_shadow_px:g},5,0,0,0,1"
    )

    header = (
        "[Script Info]\n"
        "ScriptType: v4.00+\n"
        f"PlayResX: {width}\n"
        f"PlayResY: {height}\n"
        "WrapStyle: 0\n"
        "ScaledBorderAndShadow: yes\n\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, "
        "Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, "
        "Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
        f"{hero_style}\n"
        f"{ctx_style}\n\n"
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
    )

    cx = width // 2

    # ── Vertical anchor: bottom-third of frame (not dead center) ──
    # This keeps the 3-layer stack well below the subject's face.
    # Portrait: anchor at ~72% down; landscape: ~75% down.
    if is_portrait:
        anchor_y = int(height * 0.72)   # e.g. 922 for 1280px tall
    else:
        anchor_y = int(height * 0.75)   # e.g. 405 for 540px tall

    # Approximate pixel heights (font size ≈ line height)
    hero_half = int(hero_size * 0.70)
    ctx_half  = int(ctx_size  * 0.60)
    gap       = int(ctx_size  * 0.25)

    # hero sits at anchor_y; ctx lines float above/below it
    hero_y       = anchor_y
    top_ctx_y    = anchor_y - hero_half - gap - ctx_half
    bottom_ctx_y = anchor_y + hero_half + gap + ctx_half

    dialogue_lines: list[str] = []

    for k_idx, chunk in enumerate(chunks):
        nxt_start = chunks[k_idx + 1][0].start if k_idx + 1 < len(chunks) else None
        last_end  = chunk[-1].end + 0.15
        if nxt_start is not None:
            last_end = min(last_end, nxt_start)
        last_end = max(last_end, chunk[-1].end + 0.04)

        t_start = chunk[0].start
        t_end   = last_end

        # Always get a hero word (never -1 with new _pick_hero_word)
        hero_idx    = _pick_hero_word(chunk)
        before_words = chunk[:hero_idx]
        hero_word    = chunk[hero_idx]
        after_words  = chunk[hero_idx + 1:]

        # ── Hero line (Layer 1) ──
        hero_text = ass_escape(hero_word.text.upper())
        # Quick scale-pop: punch in then settle
        hero_anim = r"{\fscx78\fscy78\t(0,120,\fscx106\fscy106)\t(120,200,\fscx100\fscy100)}"
        hero_pos  = f"{{\\an5\\pos({cx},{hero_y})}}"
        dialogue_lines.append(
            f"Dialogue: 1,{ass_time(t_start)},{ass_time(t_end)},VeedHero,,0,0,0,,{hero_pos}{hero_anim}{hero_text}"
        )

        # ── Top context (Layer 0) — words before hero ──
        if before_words:
            before_text    = " ".join(ass_escape(w.text.upper()) for w in before_words)
            before_stagger = build_stagger_text(before_text, start_offset_ms=0)
            top_pos        = f"{{\\an5\\pos({cx},{top_ctx_y})}}"
            dialogue_lines.append(
                f"Dialogue: 0,{ass_time(t_start)},{ass_time(t_end)},VeedCtx,,0,0,0,,{top_pos}{before_stagger}"
            )

        # ── Bottom context (Layer 2) — words after hero ──
        if after_words:
            after_text    = " ".join(ass_escape(w.text.upper()) for w in after_words)
            after_stagger = build_stagger_text(after_text, start_offset_ms=60)
            bottom_pos    = f"{{\\an5\\pos({cx},{bottom_ctx_y})}}"
            dialogue_lines.append(
                f"Dialogue: 2,{ass_time(t_start)},{ass_time(t_end)},VeedCtx,,0,0,0,,{bottom_pos}{after_stagger}"
            )

    return header + "\n".join(dialogue_lines) + "\n"


def build_ass_content(chunks: list[list[Word]], s: StyleSpec, width: int, height: int, style_name: str = "ViralCap") -> str:
    """Generate complete ASS subtitle document matching video resolution."""
    bc = s.outline_color if s.border_style == 3 else s.back_color
    ba = s.outline_alpha if s.border_style == 3 else s.back_alpha

    style_line = (
        f"Style: {style_name},{s.font},{s.size:g},"
        f"{hex_to_ass(s.primary)},{hex_to_ass(s.primary)},"
        f"{hex_to_ass(s.outline_color, s.outline_alpha)},{hex_to_ass(bc, ba)},"
        f"{-1 if s.bold else 0},0,0,0,100,100,{s.spacing:g},0,{s.border_style},"
        f"{s.outline:g},{s.shadow:g},{s.alignment},{s.margin_lr},{s.margin_lr},{s.margin_v},1"
    )

    header = (
        "[Script Info]\n"
        "ScriptType: v4.00+\n"
        f"PlayResX: {width}\n"
        f"PlayResY: {height}\n"
        "WrapStyle: 0\n"
        "ScaledBorderAndShadow: yes\n\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, "
        "Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, "
        "Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
        f"{style_line}\n\n"
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
    )

    dialogue_lines = []
    for k, chunk in enumerate(chunks):
        nxt = chunks[k + 1][0].start if k + 1 < len(chunks) else None
        for a, b, text in chunk_to_events(chunk, nxt, s):
            dialogue_lines.append(f"Dialogue: 0,{ass_time(a)},{ass_time(b)},{style_name},,0,0,0,,{text}")

    return header + "\n".join(dialogue_lines) + "\n"


# ---------------------------------------------------------------------------
# High-Level Resolver
# ---------------------------------------------------------------------------
def resolve_style_spec(
    preset_id: str,
    width: int,
    height: int,
    position: str = "default",
    highlight_color: Optional[str] = None,
    size_scale: float = 1.0,
    uppercase: Optional[bool] = None,
    pop_anim: Optional[bool] = None,
) -> StyleSpec:
    """Resolve preset and overrides into a concrete StyleSpec at target video resolution."""
    p = PRESETS.get(preset_id, PRESETS["hormozi-yellow"])
    is_portrait = height >= width * 1.1
    orient = "portrait" if is_portrait else "landscape"

    lay = p["layout"][orient]
    k = min(width, height) / 1080.0

    # Safe-zone positions (design px at 1080 short-side)
    pos_tokens = {
        "portrait":  {"bottom": (2, 520, 140), "center": (5, 520, 140), "upper": (8, 420, 140)},
        "landscape": {"bottom": (2, 108, 240), "center": (5, 108, 240), "upper": (8, 150, 240)},
    }
    chosen_pos = position if position in ("bottom", "center", "upper") else p["default_position"][orient]
    align, margin_v, margin_side = pos_tokens[orient][chosen_pos]

    is_box = p["border_style"] == 3
    outline_val = lay["boxPadding"] if is_box else lay["outline"]
    shadow_val = 0 if is_box else lay["shadow"]

    return StyleSpec(
        font=p["font"],
        size=round(lay["fontSize"] * max(0.6, min(1.6, size_scale)) * k, 2),
        bold=p["bold"],
        primary=p["primary"],
        highlight=highlight_color or p["highlight"],
        outline_color=p["outline_color"],
        outline_alpha=p["outline_alpha"],
        back_color=p["back_color"],
        back_alpha=p["back_alpha"],
        border_style=p["border_style"],
        outline=round(outline_val * k, 2),
        shadow=round(shadow_val * k, 2),
        spacing=round(lay["spacing"] * k, 2),
        alignment=align,
        margin_v=round(margin_v * k),
        margin_lr=round(margin_side * k),
        uppercase=p["uppercase"] if uppercase is None else uppercase,
        pop=p["pop"] if pop_anim is None else pop_anim,
        highlight_mode=p["highlight_mode"],
        active_scale=p["active_scale"],
    )


def generate_ass_from_srt(
    srt_path: str,
    ass_path: str,
    width: int,
    height: int,
    preset_id: str = "hormozi-yellow",
    position: str = "default",
    highlight_color: Optional[str] = None,
    size_scale: float = 1.0,
    uppercase: Optional[bool] = None,
    pop_anim: Optional[bool] = None,
) -> None:
    """Read an SRT file, apply viral chunking and styling, and write an ASS file."""
    with open(srt_path, "r", encoding="utf-8") as f:
        srt_content = f.read()

    segments = parse_srt(srt_content)
    all_words: list[Word] = []
    for start, end, text in segments:
        all_words.extend(distribute_words(text, start, end))

    mark_keywords(all_words)
    chunks = chunk_words(all_words, max_words=3, max_chars=18)

    # ── veed-impact uses a completely different multi-layer builder ──
    if preset_id == "veed-impact":
        preset = PRESETS["veed-impact"]
        ass_text = build_hero_box_ass(
            chunks,
            preset=preset,
            width=width,
            height=height,
            highlight_color=highlight_color,
        )
        with open(ass_path, "w", encoding="utf-8") as f:
            f.write(ass_text)
        print(f"[ass_generator] veed-impact: {len(chunks)} chunks → {ass_path}")
        return

    spec = resolve_style_spec(
        preset_id=preset_id,
        width=width,
        height=height,
        position=position,
        highlight_color=highlight_color,
        size_scale=size_scale,
        uppercase=uppercase,
        pop_anim=pop_anim,
    )

    ass_text = build_ass_content(chunks, spec, width, height)
    with open(ass_path, "w", encoding="utf-8") as f:
        f.write(ass_text)

    print(f"[ass_generator] Generated {len(chunks)} chunks in {ass_path} using {preset_id}")