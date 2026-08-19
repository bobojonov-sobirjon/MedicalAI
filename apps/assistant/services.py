from __future__ import annotations

import json
import logging
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout
from typing import Any

from django.contrib.auth import get_user_model
from django.conf import settings
from django.db.models import Q

from apps.assistant.region_match import (
    distinctive_terms,
    filter_condition_names,
    region_name_hints,
    region_score,
    regions_from_body_parts,
)
from apps.catalog.models import BodyPart, Disease, Symptom
from apps.core.gemini import GeminiConfigError, generate_json
from apps.medic.models import FaqItem

User = get_user_model()
logger = logging.getLogger(__name__)

_SYSTEM = """Ты медицинский информационный помощник в приложении MedicAI (не врач).
Правила:
- Не ставь окончательный диагноз. Используй формулировки «возможно», «стоит исключить».
- Обязательно укажи, что нужна очная консультация врача.
- Ответ строго JSON-объект на русском по схеме из запроса пользователя.
- Учитывай только переданный контекст справочника и симптомы; не выдумывай редкие болезни без оснований.
- Локализация обязательна: если указана часть тела (например «правая рука»),
  предлагай только состояния этой области. Не предлагай боль в горле, груди, лице,
  животе, если жалобы про руку, ногу или другой конкретный сегмент.
- Не используй в ответе заболевания только потому что в названии есть слово «боль».
- Пиши кратко.
"""

DEFAULT_DISCLAIMER = (
    "This information is for educational purposes only and is not medical advice. "
    "Информация носит справочный характер и не является медицинской консультацией или диагнозом. "
    "При ухудшении состояния обратитесь к врачу."
)

MEDICAL_SOURCES: list[dict[str, str]] = [
    {"title": "World Health Organization", "url": "https://www.who.int"},
    {"title": "CDC", "url": "https://www.cdc.gov"},
    {"title": "Mayo Clinic", "url": "https://www.mayoclinic.org"},
]


def format_condition_line(item: Any) -> str:
    """Human-readable line — never dump dict keys (Flutter Map.toString() fix)."""
    if isinstance(item, str):
        return item.strip()
    if not isinstance(item, dict):
        return str(item).strip()
    name = (item.get("name") or item.get("title") or "").strip()
    rationale = (item.get("rationale") or item.get("description") or "").strip()
    if name and rationale:
        return f"{name} — {rationale}"
    return name or rationale


def format_possible_conditions(conditions: Any, *, limit: int = 8) -> list[str]:
    """List of plain strings for UI «Возможные состояния»."""
    if not isinstance(conditions, list):
        return []
    out: list[str] = []
    for item in conditions:
        line = format_condition_line(item)
        if line:
            out.append(line)
        if len(out) >= limit:
            break
    return out


def build_medical_answer(ai: dict[str, Any], matched: list[dict[str, Any]]) -> str:
    """Собрать единый текст ответа для Flutter (поле answer)."""
    parts: list[str] = []
    summary = (ai.get("summary") or "").strip()
    if summary:
        parts.append(summary)

    condition_lines = format_possible_conditions(ai.get("possible_conditions") or [], limit=6)
    if condition_lines:
        parts.append("Возможные варианты:\n" + "\n".join(f"• {line}" for line in condition_lines))
    elif matched:
        lines = [f"• {c['name']}" for c in matched[:6] if c.get("name")]
        if lines:
            parts.append("Возможные варианты из справочника:\n" + "\n".join(lines))

    steps = ai.get("suggested_next_steps") or []
    if isinstance(steps, list) and steps:
        step_lines = [f"• {s}" for s in steps if isinstance(s, str) and s.strip()]
        if step_lines:
            parts.append("Что можно сделать:\n" + "\n".join(step_lines))

    if not parts:
        parts.append(
            "По введённым симптомам не удалось сформировать подробный ответ. "
            "Обратитесь к врачу при ухудшении самочувствия."
        )
    return "\n\n".join(parts)


def build_medical_payload(ai: dict[str, Any], matched: list[dict[str, Any]]) -> dict[str, Any]:
    """Flutter Variant 1: answer + disclaimer + sources."""
    disclaimer = (ai.get("disclaimer") or "").strip() or DEFAULT_DISCLAIMER
    return {
        "answer": build_medical_answer(ai, matched),
        "disclaimer": disclaimer,
        "sources": list(MEDICAL_SOURCES),
    }


def _soft_ai_timeout_s() -> float:
    """
    Flutter often aborts around 15–20s («Response timeout»).
    Soft-timeout must finish earlier and return catalog fallback.
    """
    configured = float(getattr(settings, "ASSISTANT_AI_SOFT_TIMEOUT_S", 10) or 10)
    return max(5.0, min(configured, 14.0))


def _catalog_slice(
    symptoms: str,
    *,
    body_parts_resolved: list[dict[str, Any]] | None = None,
    body_parts_s: str = "",
    limit: int = 8,
) -> list[dict[str, Any]]:
    """Match by distinctive phrases + body region. Never search by bare «боль»."""
    terms = distinctive_terms(symptoms, body_parts_s)
    regions = regions_from_body_parts(body_parts_resolved, body_parts_s)
    if not terms and not regions:
        return []

    qs = Disease.objects.all().only("id", "name", "description")
    cond = Q()
    for term in terms[:12]:
        cond |= Q(name__icontains=term)
        if " " not in term and len(term) >= 5:
            cond |= Q(description__icontains=term)
    if regions:
        for hint in region_name_hints(regions):
            cond |= Q(name__icontains=hint)
    if not cond:
        return []

    # Pull a wider pool, then rank/filter so «Боль в горле» cannot beat «Боль в руке».
    pool = list(qs.filter(cond).distinct()[:80])
    scored: list[tuple[int, Any]] = []
    for d in pool:
        sc = region_score(d.name, d.description or "", regions, terms)
        if sc is None:
            continue
        scored.append((sc, d))
    scored.sort(key=lambda item: (-item[0], item[1].name))
    rows = [d for _sc, d in scored[:limit]]
    return [{"id": d.id, "name": d.name, "description": (d.description or "")[:280]} for d in rows]


def _faq_slice(symptoms: str, *, limit: int = 3) -> list[dict[str, Any]]:
    q = symptoms.strip()
    if len(q) < 2:
        return []
    rows = list(
        FaqItem.objects.filter(is_active=True)
        .filter(Q(question__icontains=q) | Q(answer__icontains=q))[:limit]
    )
    return [{"id": f.id, "question": f.question, "answer": (f.answer or "")[:280]} for f in rows]


def _symptoms_text_from_ids(symptom_ids: list[int]) -> tuple[str, list[dict[str, Any]]]:
    ids = [int(x) for x in symptom_ids if isinstance(x, int) or str(x).isdigit()]
    ids = [x for x in ids if x > 0][:60]
    if not ids:
        return "", []
    rows = list(Symptom.objects.filter(id__in=ids).order_by("name"))
    by_id = {s.id: s for s in rows}
    ordered = [by_id[i] for i in ids if i in by_id]
    names = [s.name for s in ordered]
    payload = [{"id": s.id, "name": s.name, "aliases": s.aliases} for s in ordered]
    return ", ".join(names), payload


def _body_parts_from_ids(body_part_ids: list[int]) -> tuple[str, list[dict[str, Any]]]:
    ids = [int(x) for x in body_part_ids if isinstance(x, int) or str(x).isdigit()]
    ids = [x for x in ids if x > 0][:40]
    if not ids:
        return "не указано", []
    rows = list(BodyPart.objects.filter(id__in=ids).order_by("sort_order", "label"))
    by_id = {b.id: b for b in rows}
    ordered = [by_id[i] for i in ids if i in by_id]
    labels = [b.label for b in ordered]
    payload = [{"id": b.id, "code": b.code, "label": b.label} for b in ordered]
    return (", ".join(labels) if labels else "не указано"), payload


def _user_context_line(user: User) -> str:
    parts: list[str] = []
    if user.get_full_name():
        parts.append(f"Имя: {user.get_full_name()}")
    if getattr(user, "gender", None):
        parts.append(f"Пол: {user.get_gender_display() if hasattr(user, 'get_gender_display') else user.gender}")
    if getattr(user, "date_of_birth", None):
        parts.append(f"Дата рождения: {user.date_of_birth}")
    if getattr(user, "city", None):
        parts.append(f"Город: {user.city}")
    return "; ".join(parts) if parts else "Профиль без дополнительных полей."


def _fallback_ai(catalog: list[dict[str, Any]], *, reason: str) -> dict[str, Any]:
    # Store as strings immediately — UI «Возможные состояния» must not show Map keys.
    conditions = [c["name"] for c in catalog[:5] if c.get("name")]
    return {
        "summary": (
            "Ниже — возможные варианты из справочника по вашим симптомам. "
            "Это не диагноз; при ухудшении обратитесь к врачу."
        ),
        "possible_conditions": conditions,
        "match_catalog_ids": [c["id"] for c in catalog[:8]],
        "suggested_next_steps": [
            "Обратитесь к врачу при ухудшении состояния.",
            "При высокой температуре, одышке или сильной боли — срочная помощь.",
        ],
        "disclaimer": "Информация не является медицинской консультацией.",
        "_fallback_reason": reason,
    }


def run_diagnosis(
    *,
    user: User,
    profile_user: User | None = None,
    symptom_ids: list[int],
    symptoms_text: str,
    body_part_ids: list[int],
    temperature_c: float | None,
    blood_pressure: str,
) -> dict[str, Any]:
    profile_user = profile_user or user
    symptoms_from_ids, symptoms_resolved = _symptoms_text_from_ids(symptom_ids)
    body_parts_s, body_parts_resolved = _body_parts_from_ids(body_part_ids)
    combined_symptoms = "\n".join([s for s in [symptoms_from_ids.strip(), (symptoms_text or "").strip()] if s])
    match_terms = distinctive_terms(combined_symptoms, body_parts_s)
    match_regions = regions_from_body_parts(body_parts_resolved, body_parts_s)

    catalog = _catalog_slice(
        combined_symptoms,
        body_parts_resolved=body_parts_resolved,
        body_parts_s=body_parts_s,
    )
    faq = _faq_slice(combined_symptoms)
    catalog_json = json.dumps(catalog, ensure_ascii=False)
    faq_json = json.dumps(faq, ensure_ascii=False)
    temp_s = f"{temperature_c} °C" if temperature_c is not None else "не указано"
    bp_s = blood_pressure or "не указано"

    schema_hint = """Верни JSON:
{
  "summary": "краткое резюме (2-4 предложения)",
  "possible_conditions": [{"name": "строка", "rationale": "почему возможно", "urgency": "routine|soon|urgent"}],
  "match_catalog_ids": [id из справочника],
  "suggested_next_steps": ["шаги"],
  "disclaimer": "не диагноз, нужен врач"
}"""

    user_prompt = f"""Профиль: {_user_context_line(profile_user)}
Части тела (обязательная локализация): {body_parts_s}
Температура: {temp_s}
Давление: {bp_s}
Симптомы: {symptoms_from_ids or "не указано"}
Уточнения: {(symptoms_text or "").strip() or "не указано"}
Справочник (уже отфильтрован по локализации): {catalog_json}
FAQ: {faq_json}

Запрещено предлагать заболевания другой области тела.
Если часть тела — рука, нельзя возвращать «боль в горле», «боль в груди», «лицевая боль».
{schema_hint}"""

    soft_timeout = _soft_ai_timeout_s()
    ai_error: str | None = None

    def _call_ai() -> dict[str, Any]:
        return generate_json(_SYSTEM, user_prompt, temperature=0.2)

    # If AI provider is not configured — skip wait, answer from catalog immediately.
    from apps.core.rutronix import rutronix_configured
    from apps.core.gemini import gemini_configured, gemini_fallback_enabled

    ai_ready = rutronix_configured() or (gemini_fallback_enabled() and gemini_configured())
    if not ai_ready:
        ai_error = "AI provider not configured"
        ai = _fallback_ai(catalog, reason=ai_error)
    else:
        # CRITICAL: do not use `with ThreadPoolExecutor` — on exit it waits for the hung
        # AI HTTP call (shutdown(wait=True)), and Flutter already timed out.
        pool = ThreadPoolExecutor(max_workers=1)
        try:
            future = pool.submit(_call_ai)
            ai = future.result(timeout=soft_timeout)
        except FuturesTimeout:
            logger.warning("AI diagnose soft-timeout after %.1fs — catalog fallback", soft_timeout)
            ai_error = f"Timeout after {soft_timeout:.0f}s"
            ai = _fallback_ai(catalog, reason=ai_error)
        except (GeminiConfigError, RuntimeError, OSError, ValueError, Exception) as e:
            logger.exception("AI diagnose failed: %s", e)
            ai_error = f"{type(e).__name__}: {e}"
            ai = _fallback_ai(catalog, reason=ai_error)
        finally:
            pool.shutdown(wait=False, cancel_futures=True)

    match_ids = ai.get("match_catalog_ids") or []
    if not isinstance(match_ids, list):
        match_ids = []
    match_ids = [int(x) for x in match_ids if str(x).isdigit()][:20]
    matched = [c for c in catalog if c["id"] in match_ids]
    if not matched and catalog:
        matched = catalog[:5]

    if not ai.get("possible_conditions") and catalog:
        ai["possible_conditions"] = _fallback_ai(catalog, reason="empty_ai").get("possible_conditions")

    conditions_raw = ai.get("possible_conditions") or []
    conditions_text = format_possible_conditions(conditions_raw, limit=8)
    if match_regions:
        filtered = filter_condition_names(conditions_text, regions=match_regions, terms=match_terms)
        conditions_text = filtered or [c["name"] for c in catalog[:8] if c.get("name")]
    if not conditions_text and matched:
        conditions_text = [c["name"] for c in matched[:8] if c.get("name")]
    if not conditions_text and catalog:
        conditions_text = [c["name"] for c in catalog[:8] if c.get("name")]
    ai["possible_conditions"] = conditions_text
    medical = build_medical_payload(ai, matched)

    return {
        "symptoms_resolved": symptoms_resolved,
        "body_parts_resolved": body_parts_resolved,
        "catalog_candidates": [
            {"id": c["id"], "name": c["name"], "description": c.get("description", "")} for c in catalog
        ],
        "faq_hits": faq,
        "catalog_matched": [
            {"id": c["id"], "name": c["name"], "description": c.get("description", "")} for c in matched
        ],
        # Top-level for Flutter «Возможные состояния» — только читаемые строки.
        "possible_conditions": conditions_text,
        "answer": medical["answer"],
        "disclaimer": medical["disclaimer"],
        "sources": medical["sources"],
        "ai": {
            "summary": ai.get("summary", ""),
            # IMPORTANT: strings only — Flutter must not render Map.toString().
            "possible_conditions": conditions_text,
            "suggested_next_steps": [
                s for s in (ai.get("suggested_next_steps") or []) if isinstance(s, str) and s.strip()
            ][:8],
            "disclaimer": medical["disclaimer"],
            "answer": medical["answer"],
            "sources": medical["sources"],
        },
        **({"ai_error": ai_error} if getattr(settings, "DEBUG", False) and ai_error else {}),
    }
