from __future__ import annotations

import html
import re

_PREVIEW_SENTENCE_RE = re.compile(r"(?<=[.!?…])\s+")
_HTML_TAG_RE = re.compile(r"<[^>]+>")
_SCRIPT_RE = re.compile(r"(?is)<script[^>]*>.*?</script>")
_STYLE_RE = re.compile(r"(?is)<style[^>]*>.*?</style>")
_NOSCRIPT_RE = re.compile(r"(?is)<noscript[^>]*>.*?</noscript>")
_EMOJI_RE = re.compile(
    "["
    "\U0001F300-\U0001F6FF"
    "\U0001F900-\U0001FAFF"
    "\U00002700-\U000027BF"
    "]+",
)
_JUNK_TOKENS = (
    "vidalReady",
    "vidalComplete",
    "yaContextCb",
    "Ya.Context",
    "querySelector",
    "querySelectorAll",
    "AdvManager",
    "innerHTML",
    "getAttribute",
    "addEventListener",
    "classList.add",
    "!important",
    "#fixed-right",
    "btn-buy-hidden",
    "no-hover",
    "color-black",
    "yandex_rtb",
    "gaSend",
    "isPartOf",
    '"about"',
    "banner-render",
    "ProductID=",
    "mkb-11-link",
    "data-code",
    ".yad",
    "#yad_article",
    "yatag",
    "window.yaContextCb",
    "banner-comment",
    "flex-direction",
    "banners_group",
    "vidalSendBanner",
    "vidalOnBanner",
    "yandexGoal",
    "isLogged=",
)
_JUNK_LINE_RE = re.compile(
    r"(?i)(?:vidalready|vidalcomplete|yacontext|queryselector|advmanager|"
    r"yandex_rtb|!important|ispartof|banner-render|gaSend|flex-direction|"
    r"getattribute|addeventlistener|innerhtml|mkb-11-link|classlist|"
    r"banners_group|vidalsend|vidalonbanner|yandexgoal|islogged|"
    r"document\.|window\.|function\s*\(|=>\s*\{|"
    r"margin-(?:top|bottom|left|right)\s*:|display\s*:\s*flex|"
    r"#fixed-right|\.color-black|\.no-hover|\.btn-buy|"
    r"\(\s*'#|\(\s*'data-|\(\s*'send'|banner\.|if\s*\(\s*code|"
    r"el\.class|selector\)|&from|64822&|/11/0/0)"
)
_CSS_LINE_RE = re.compile(
    r"(?m)^\s*[.#]?[A-Za-z_][\w\-]*\s*\{[^}\n]{0,240}\}\s*$"
)
_JSONISH_RE = re.compile(r'(?i)"(?:about|isPartOf|@type|@context)"\s*:')
_MKB_HEADER_RE = re.compile(
    r"(?i)(?:открыть список кодов\s+)?(?:коды?\s+)?мкб-1[01]\s*:?\s*(?:код(?:ы)?\s+мкб-1[01]\s*)?(?:показание)?"
)
_ICD10_PAIR_RE = re.compile(
    r"\b[A-TV-Z]\d{2}(?:\.\d+[A-Z]?)?\s+(?=[А-ЯЁа-яё])"
)
_ICD11_PAIR_RE = re.compile(
    r"\b\d[A-Z][A-Z0-9]{1,3}(?:\.\d+)?\s+(?=[А-ЯЁа-яё])"
)
_SENTENCE_BREAK_RE = re.compile(
    r"(?<=[.!?])\s+(?=[А-ЯЁA-Z«\"0-9])"
)
def _is_junk_line(line: str) -> bool:
    s = line.strip()
    if not s:
        return False
    if _JUNK_LINE_RE.search(s) or _JSONISH_RE.search(s) or _CSS_LINE_RE.match(s):
        return True
    cyr = len(re.findall(r"[А-Яа-яЁё]", s))
    if cyr < 8 and re.search(r"[{};]|!important|=>", s):
        return True
    if cyr < 6 and re.fullmatch(r"[\w.\-#{}();:,'\"=<>/\s]+", s) and re.search(r"[{};=]", s):
        return True
    return False


def _strip_mkb_dumps(raw: str) -> str:
    text = _MKB_HEADER_RE.sub(" ", raw)
    text = re.sub(r"(?i)код диагноза по международной классификации болезней\.?", " ", text)
    text = _ICD10_PAIR_RE.sub(" ", text)
    text = _ICD11_PAIR_RE.sub(" ", text)
    return text


def sanitize_scraped_text(text: str) -> str:
    """Strip Vidal page junk: scripts, CSS, ads, JSON-LD, MKB dumps, emoji headers."""
    raw = text or ""
    raw = _SCRIPT_RE.sub("\n", raw)
    raw = _STYLE_RE.sub("\n", raw)
    raw = _NOSCRIPT_RE.sub("\n", raw)
    raw = _EMOJI_RE.sub(" ", raw)
    for tok in _JUNK_TOKENS:
        if tok in raw:
            raw = raw.replace(tok, "\n")
    raw = re.sub(r"\{[^{}\u0400-\u04FF]{0,240}\}", " ", raw)
    raw = re.sub(r"(?i)\.?(?:push|render|forEach)\s*\(\s*\(?\s*\)?\s*=>", " ", raw)
    raw = re.sub(r"(?i)\.render\s*\(\s*\)", " ", raw)
    raw = re.sub(r"\bAll\(\s*['\"][^'\"]{0,80}['\"]\s*\)", " ", raw)
    raw = re.sub(r'["\']\s*:\s*\[\s*["\'][^"\']{0,80}["\']\s*\]', " ", raw)
    raw = re.sub(r"\}\s*;?", " ", raw)
    raw = re.sub(r"[{};]{2,}", " ", raw)
    raw = re.sub(r"\);+\s*", " ", raw)
    raw = re.sub(r"(?m)^\s*[);.]+\s*", "", raw)
    raw = re.sub(
        r"(?i)справочник препаратов и лекарств|–\s*описание\s+\S+|описание\s+[A-Za-z][\w()\- ]{0,40}капсулы\.?",
        " ",
        raw,
    )
    raw = _strip_mkb_dumps(raw)
    kept: list[str] = []
    for line in re.split(r"\n+", raw):
        if _is_junk_line(line):
            continue
        kept.append(line)
    raw = "\n".join(kept)
    raw = re.sub(r"(?i)открыть список кодов мкб(?:-1[01])?", " ", raw)
    raw = re.sub(r"(?i)\bпродукта\s+", " ", raw)
    raw = re.sub(r"(?i)(и кормлении грудью\s*){2,}", "и кормлении грудью ", raw)
    raw = re.sub(r"(?i)(при беременности\s*){2,}", "при беременности ", raw)
    raw = re.sub(r"(?i)^\s*(?:и кормлении грудью\s*)+", "", raw.strip())
    return raw


def is_junk_scraped_text(text: str) -> bool:
    """True if a section is mostly CSS/JS leftover, not medical copy."""
    raw = (text or "").strip()
    if not raw:
        return True
    low = raw.casefold()
    if any(
        x in low
        for x in (
            "vidalready",
            "yacontext",
            "queryselector",
            "!important",
            "advmanager",
            "#fixed-right",
            "yandex_rtb",
            "flex-direction",
            "banners_group",
            "classlist",
            "vidalsend",
            "islogged",
            "banner.",
            "el.class",
        )
    ):
        return True
    cyr = len(re.findall(r"[А-Яа-яЁё]", raw))
    codeish = len(re.findall(r"[{};]|function\s*\(|=>|:\s*\[", raw))
    if codeish >= 2 and cyr < 80:
        return True
    if re.search(r':\s*\[', raw) or (raw.count('"') >= 2 and cyr < 40):
        return True
    if re.search(r"(?i)описание\s+[A-Za-z].{0,40}капсул", raw) and cyr < 100:
        return True
    if re.fullmatch(r"(?i)[\s.]*справочник\.?[\s.]*", raw):
        return True
    if cyr < 6 and not re.search(r"[A-Za-z]{3,}", raw):
        return True
    return False


def clean_display_text(text: str) -> str:
    """Decode HTML entities, strip tags/scripts/CSS. Keep paragraph breaks."""
    raw = sanitize_scraped_text(text or "")
    raw = html.unescape(raw.replace("\xa0", " "))
    raw = (
        raw.replace("\\t", " ")
        .replace("\\n", "\n")
        .replace("\\r", " ")
        .replace("\\u0009", " ")
        .replace("\t", " ")
        .replace("\r", " ")
    )
    raw = _HTML_TAG_RE.sub("", raw)
    raw = re.sub(r"[ \t\f\v]+", " ", raw)
    raw = re.sub(r" *\n *", "\n", raw)
    raw = "\n".join(
        ln for ln in raw.split("\n") if re.search(r"[0-9A-Za-zА-Яа-яЁё]", ln or "")
    )
    raw = re.sub(r"\n{3,}", "\n\n", raw)
    return raw.strip()


def flatten_display_text(text: str) -> str:
    """Single-line variant for names/previews."""
    return re.sub(r"\s+", " ", clean_display_text(text or "")).strip()


def is_registry_meta_text(text: str) -> bool:
    """True if text is GRLS registry labels, not a patient instruction."""
    raw = flatten_display_text(text or "")
    if not raw:
        return True
    low = raw.casefold()
    has_grls = (
        "грлс" in low
        or "держатель ру" in low
        or "государственный реестр" in low
        or "источник:" in low
    )
    has_medical = any(
        tok in low
        for tok in (
            "показан",
            "дозир",
            "противопоказ",
            "побочн",
            "фармаколог",
            "принимать",
            "капс",
            "таблет",
            "раствор",
            "состав",
            "фармакокинет",
        )
    )
    if has_grls and not has_medical:
        return True
    if re.search(r"мнн:\s*[-—.]?\s*", low) and (
        has_grls or "держатель ру" in low or "источник:" in low
    ):
        return True
    if "держатель ру" in low and re.search(r"мнн:\s*[-—.]?\s*", low) and not has_medical:
        return True
    return False


def normalize_catalog_quotes(text: str) -> str:
    """Fix GRLS/Vidal quote glitches: \"\"АЛКОЙ\"\", nested quotes."""
    raw = text or ""
    raw = re.sub(r'""([^"]{1,120})""', r"«\1»", raw)
    raw = re.sub(r'"\s*«([^»]+)»\s*"', r"«\1»", raw)
    raw = re.sub(r'(?<=\s)"{2,}(?=[А-ЯA-Z])', "«", raw)
    raw = re.sub(r'(?<=[а-яa-z0-9»])"{2,}(?=\s|[.,;]|$)', "»", raw)
    raw = re.sub(r'"{3,}', '"', raw)
    raw = re.sub(r"\s+«\s+", " «", raw)
    raw = re.sub(r"\s+»\s+", "» ", raw)
    return raw.strip()


def strip_markdown_bold_for_plain(text: str) -> str:
    """Remove raw ** so Flutter plain Text does not show asterisks."""
    raw = text or ""
    raw = re.sub(r"\*\*([^*\n]+?)\*\*", r"\1", raw)
    raw = raw.replace("**", "")
    return raw.strip()


def clean_drug_plain_text(text: str) -> str:
    """Patient-facing plain description: no junk, no raw **, normalized quotes."""
    raw = clean_display_text(text or "")
    if not raw or is_junk_scraped_text(raw) or is_registry_meta_text(raw):
        return ""
    raw = normalize_catalog_quotes(raw)
    raw = strip_markdown_bold_for_plain(raw)
    raw = re.sub(r"\s+", " ", raw).strip(" .;—–-")
    return raw


def format_section_markdown(text: str) -> str:
    """Readable spoiler text (paragraphs, lists). No raw ** — Flutter shows plain Text."""
    raw = clean_display_text(text or "")
    if not raw:
        return ""
    if is_junk_scraped_text(raw) or is_registry_meta_text(raw):
        return ""
    raw = normalize_catalog_quotes(raw)
    raw = strip_markdown_bold_for_plain(raw)
    if "\n" not in raw:
        raw = _SENTENCE_BREAK_RE.sub("\n\n", raw)
    paras: list[str] = []
    for block in re.split(r"\n{2,}", raw):
        block = block.strip(" \n-•")
        if not block:
            continue
        lines = [re.sub(r"\s+", " ", ln).strip(" •") for ln in block.split("\n") if ln.strip()]
        if not lines:
            continue
        chunk = "\n".join(lines)
        # Keep "Label: value" plain — do not wrap in ** (FE does not render Markdown).
        chunk = re.sub(
            r"^([А-ЯЁA-Z][^:\n]{2,48}):\s+",
            r"\1: ",
            chunk,
        )
        # Comma-lists of 4+ short clauses → bullets (contraindications etc.)
        if "\n" not in chunk and chunk.count(",") >= 3 and len(chunk) < 400 and not re.search(r"\d{5}", chunk):
            parts = [p.strip(" .;") for p in chunk.split(",") if p.strip()]
            if parts and all(3 <= len(p) <= 80 for p in parts):
                chunk = "\n".join(f"- {p}" for p in parts)
        paras.append(chunk)
    uniq: list[str] = []
    seen: set[str] = set()
    for p in paras:
        key = re.sub(r"\s+", " ", p).strip().casefold()
        if len(key) < 4 or key in seen:
            continue
        seen.add(key)
        uniq.append(p)
    return strip_markdown_bold_for_plain("\n\n".join(uniq).strip())


_LATIN_BRACKET_RE = re.compile(r"\s*\[[^\[\]]*[A-Za-z][^\[\]]*\]")
_PAREN_RE = re.compile(r"\s*\(([^)]*)\)")
_MNN_RE = re.compile(r"МНН:\s*([^.\n;]+)", re.IGNORECASE)
_LATIN_ONLY_RE = re.compile(r"^[A-Za-z][A-Za-z0-9\s\-/',.+]*$")


def clean_disease_display_name(name: str) -> str:
    """Убрать английские пояснения вида [herpes simplex], оставить коды МКБ (G05.1*)."""
    raw = re.sub(r"\s+", " ", (name or "").strip())
    if not raw:
        return ""
    cleaned = _LATIN_BRACKET_RE.sub("", raw)

    def _keep_or_drop_paren(match: re.Match[str]) -> str:
        inner = (match.group(1) or "").strip()
        if not inner:
            return ""
        # Коды МКБ / с цифрами — оставляем.
        if re.search(r"\d", inner):
            return match.group(0)
        if re.search(r"[А-Яа-яЁё]", inner):
            return match.group(0)
        if _LATIN_ONLY_RE.match(inner):
            return ""
        return match.group(0)

    cleaned = _PAREN_RE.sub(_keep_or_drop_paren, cleaned)
    cleaned = re.sub(r"\s{2,}", " ", cleaned).strip(" ,;—–-")
    return cleaned if cleaned else raw


def extract_drug_mnn(description: str) -> str:
    """Достать МНН из описания ГРЛС: 'МНН: Валацикловир. ...'."""
    match = _MNN_RE.search(description or "")
    if not match:
        return ""
    value = re.sub(r"\s+", " ", match.group(1)).strip(" .;:—–-")
    if not value or value in {"-", "—", ".", "нет", "н/д", "n/a"}:
        return ""
    return value.casefold()


def split_mnn_parts(mnn: str) -> list[str]:
    """Разбить комбо-МНН: 'метформин+глибенкламид' → ['метформин', 'глибенкламид']."""
    raw = (mnn or "").casefold().strip()
    if not raw:
        return []
    parts = re.split(r"[+/;,|]+|\s+и\s+", raw)
    out: list[str] = []
    for part in parts:
        part = re.sub(r"\s+", " ", part).strip(" .")
        if len(part) < 3:
            continue
        # Убрать дозировки вида «500 мг»
        part = re.sub(r"\b\d+[.,]?\d*\s*(мг|г|мл|%|ме)\b", "", part, flags=re.I).strip()
        if len(part) >= 3:
            out.append(part)
    return out or ([raw] if len(raw) >= 3 else [])


_MKB_LINE_RE = re.compile(
    r"(?i)(?:^|\s)МКБ-10:\s*[A-ZА-Я]\d[\w.\-]*\.?(?:\s*Код диагноза по Международной классификации болезней\.?)?",
)


def strip_mkb_public_text(text: str) -> str:
    """Remove ICD/MKB codes from patient-facing text. Keeps paragraph breaks."""
    raw = _strip_mkb_dumps(clean_display_text(text or ""))
    raw = _MKB_LINE_RE.sub(" ", raw)
    raw = re.sub(
        r"(?i)\.?\s*Код диагноза по Международной классификации болезней\.?\s*",
        "",
        raw,
    )
    raw = re.sub(r"(?i)\bМКБ-10\b[:\s]*[A-ZА-Я]?\d[\w.\-]*", "", raw)
    raw = re.sub(r"[ \t]+", " ", raw)
    raw = re.sub(r"\n{3,}", "\n\n", raw)
    return raw.strip(" .;—–-\n")


def disease_card_text(obj) -> str:
    """Patient-facing disease text: full overview, never MKB codes."""
    from apps.catalog.disease_sections import (
        build_disease_sections,
        fallback_disease_overview,
    )

    instr = getattr(obj, "instructions", "") or ""
    desc = obj.description or ""
    name = getattr(obj, "name", "") or ""
    if instr and len(instr.strip()) >= 80:
        sections = build_disease_sections(description=desc, instructions=instr)
        for row in sections:
            if row.get("key") == "overview" and row.get("text"):
                text = strip_mkb_public_text(row["text"])
                return text if len(text) >= 60 else fallback_disease_overview(name)
        if sections and sections[0].get("text"):
            text = strip_mkb_public_text(sections[0]["text"])
            return text if len(text) >= 60 else fallback_disease_overview(name)
        text = strip_mkb_public_text(instr)
        return text if len(text) >= 60 else fallback_disease_overview(name)
    text = strip_mkb_public_text(desc)
    return text if len(text) >= 60 else fallback_disease_overview(name)


def description_preview(text: str, *, max_chars: int = 320) -> str:
    """First ~3 lines for mobile cards («Подробнее» opens full description)."""
    raw = flatten_display_text(text)
    if not raw:
        return ""
    if len(raw) <= max_chars:
        return raw

    sentences = _PREVIEW_SENTENCE_RE.split(raw)
    preview = ""
    for sentence in sentences:
        candidate = f"{preview} {sentence}".strip() if preview else sentence.strip()
        if len(candidate) > max_chars and preview:
            break
        preview = candidate
        if len(preview) >= max_chars * 0.55 and preview.count(".") + preview.count("!") + preview.count("?") >= 2:
            break

    if not preview:
        preview = raw[: max_chars - 1].rstrip() + "…"
    elif len(raw) > len(preview):
        preview = preview.rstrip(".,;:!? ") + "…"
    return preview
