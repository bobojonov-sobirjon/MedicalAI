from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import dataclass
from typing import Any, Callable, Optional

import requests


@dataclass
class StepResult:
    name: str
    method: str
    url: str
    status_code: int
    ok: bool
    elapsed_ms: int
    response_json: Any | None
    response_text_preview: str


def _preview_text(text: str, limit: int = 400) -> str:
    t = (text or "").strip()
    if len(t) <= limit:
        return t
    return t[:limit] + " …"


def _safe_json(resp: requests.Response) -> Any | None:
    try:
        return resp.json()
    except Exception:
        return None


def _request(
    *,
    session: requests.Session,
    name: str,
    method: str,
    base_url: str,
    path: str,
    token: str | None,
    expected: set[int] | None = None,
    params: dict[str, Any] | None = None,
    json_body: Any | None = None,
    data: dict[str, Any] | None = None,
    files: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    timeout_s: int = 25,
) -> StepResult:
    url = base_url.rstrip("/") + "/" + path.lstrip("/")
    h: dict[str, str] = {}
    if headers:
        h.update(headers)
    if token:
        h["Authorization"] = f"Bearer {token}"
    # optional API key (TZ §3.3)
    api_key = os.getenv("BACKEND_API_KEY", "").strip()
    if api_key:
        h.setdefault("X-Backend-Key", api_key)

    t0 = time.time()
    if json_body is not None:
        resp = session.request(
            method=method.upper(),
            url=url,
            params=params,
            json=json_body,
            headers=h,
            timeout=timeout_s,
        )
    else:
        resp = session.request(
            method=method.upper(),
            url=url,
            params=params,
            data=data,
            files=files,
            headers=h,
            timeout=timeout_s,
        )
    elapsed_ms = int((time.time() - t0) * 1000)
    body_json = _safe_json(resp)
    ok = resp.ok if expected is None else resp.status_code in expected
    return StepResult(
        name=name,
        method=method.upper(),
        url=url,
        status_code=resp.status_code,
        ok=ok,
        elapsed_ms=elapsed_ms,
        response_json=body_json,
        response_text_preview=_preview_text(resp.text),
    )


def _print_result(r: StepResult) -> None:
    mark = "OK " if r.ok else "ERR"
    print(f"[{mark}] {r.method} {r.url} -> {r.status_code} ({r.elapsed_ms} ms) :: {r.name}")
    if not r.ok:
        if r.response_json is not None:
            try:
                print("      json:", json.dumps(r.response_json, ensure_ascii=False)[:800])
            except Exception:
                print("      json:", str(r.response_json)[:800])
        else:
            if r.response_text_preview:
                print("      body:", r.response_text_preview)


def _pick_first_id(items: Any) -> int | None:
    if isinstance(items, list) and items:
        x = items[0]
        if isinstance(x, dict) and isinstance(x.get("id"), int):
            return x["id"]
    return None


def run_smoke(*, base_url: str, token: str) -> int:
    session = requests.Session()
    results: list[StepResult] = []

    def do(
        name: str,
        method: str,
        path: str,
        *,
        expected: set[int] | None = None,
        params: dict[str, Any] | None = None,
        json_body: Any | None = None,
        data: dict[str, Any] | None = None,
        files: dict[str, Any] | None = None,
        auth: bool = True,
    ) -> StepResult:
        r = _request(
            session=session,
            name=name,
            method=method,
            base_url=base_url,
            path=path,
            token=token if auth else None,
            expected=expected,
            params=params,
            json_body=json_body,
            data=data,
            files=files,
        )
        results.append(r)
        _print_result(r)
        return r

    print(f"Base URL: {base_url}")
    print("Note: WS excluded; auth endpoints excluded; using provided JWT for protected endpoints.\n")

    # --- Public content / geo (AllowAny) ---
    do("Public config", "GET", "/api/content/config/", auth=False)
    do("Static page (about)", "GET", "/api/content/pages/about/", auth=False, expected={200, 404})
    do("Static page (privacy)", "GET", "/api/content/pages/privacy/", auth=False, expected={200, 404})
    cities = do("Cities list", "GET", "/api/geo/cities/", auth=False)
    city_id = _pick_first_id(cities.response_json)
    do(
        "Facilities list (pharmacy, optional city)",
        "GET",
        "/api/geo/facilities/",
        auth=False,
        params={k: v for k, v in {"kind": "pharmacy", "city_id": city_id}.items() if v is not None},
        expected={200},
    )

    # --- Catalog (AllowAny) ---
    diseases = do("Diseases search", "GET", "/api/catalog/diseases/", auth=False, params={"q": "а"}, expected={200})
    disease_id = _pick_first_id(diseases.response_json)
    if disease_id:
        do("Disease detail", "GET", f"/api/catalog/diseases/{disease_id}/", auth=False, expected={200})

    drugs = do("Drugs search", "GET", "/api/catalog/drugs/", auth=False, params={"q": "а"}, expected={200})
    drug_id = _pick_first_id(drugs.response_json)
    if drug_id:
        do("Drug detail", "GET", f"/api/catalog/drugs/{drug_id}/", auth=False, expected={200})

    # --- Assistant / FAQ ---
    do("FAQ search", "GET", "/api/faq/", auth=False, params={"q": "боль"}, expected={200})
    do(
        "Body parts list",
        "GET",
        "/api/catalog/body-parts/",
        auth=False,
        expected={200},
    )
    do(
        "Symptoms autocomplete",
        "GET",
        "/api/catalog/symptoms/",
        auth=False,
        params={"q": "бо"},
        expected={200},
    )
    do(
        "Assistant diagnose",
        "POST",
        "/api/assistant/diagnose/",
        json_body={"symptoms": "головная боль", "body_parts": [], "temperature_c": 37.1, "blood_pressure": "120/80"},
        expected={200, 503},
    )

    # --- Notifications / events (JWT) ---
    ev_created = do(
        "Create reminder event",
        "POST",
        "/api/me/notifications/events/",
        json_body={"title": "Тест", "body": "smoke", "event_at": None, "subject_user_label": ""},
        expected={201, 400},
    )
    ev_id = None
    if isinstance(ev_created.response_json, dict):
        ev_id = ev_created.response_json.get("id")
    do("Events list", "GET", "/api/me/notifications/events/", expected={200})
    if isinstance(ev_id, int):
        do("Mark event read", "POST", f"/api/me/notifications/events/{ev_id}/read/", json_body={}, expected={200, 404})
    do("Useful feed", "GET", "/api/me/notifications/useful/", expected={200})
    do("Tip settings get", "GET", "/api/me/tip-settings/", expected={200})
    do("Tip settings patch", "PATCH", "/api/me/tip-settings/", json_body={"tips_per_day": 3, "useful_subscribed": True}, expected={200})
    if isinstance(disease_id, int):
        do("Subscribe tips by disease", "POST", f"/api/me/disease-tip-subscribe/{disease_id}/", json_body={}, expected={200})
        do("Unsubscribe tips by disease", "DELETE", f"/api/me/disease-tip-subscribe/{disease_id}/", expected={204})

    # --- Cabinet (JWT) ---
    cab_item = do(
        "Create cabinet item (custom_name)",
        "POST",
        "/api/me/cabinet/items/",
        json_body={"custom_name": "Тестовое лекарство", "expires_at": None, "note": "smoke"},
        expected={201, 400},
    )
    cab_id = None
    if isinstance(cab_item.response_json, dict):
        cab_id = cab_item.response_json.get("id")
    do("Cabinet items list", "GET", "/api/me/cabinet/items/", expected={200})
    if isinstance(cab_id, int):
        do("Cabinet item detail", "GET", f"/api/me/cabinet/items/{cab_id}/", expected={200})
        do("Cabinet item patch", "PATCH", f"/api/me/cabinet/items/{cab_id}/", json_body={"note": "smoke2"}, expected={200})
        do("Cabinet item delete", "DELETE", f"/api/me/cabinet/items/{cab_id}/", expected={204})

    # recognize endpoint requires real image file
    image_path = os.getenv("CABINET_TEST_IMAGE", "").strip()
    if image_path and os.path.exists(image_path):
        with open(image_path, "rb") as f:
            do(
                "Cabinet recognize (image)",
                "POST",
                "/api/me/cabinet/recognize/",
                files={"image": (os.path.basename(image_path), f, "image/jpeg")},
                expected={200, 400, 503},
            )
    else:
        print("[SKIP] Cabinet recognize: set CABINET_TEST_IMAGE env var to a local image path\n")

    # --- Drug view log + social blocks (JWT) ---
    do("Recent drugs", "GET", "/api/me/recent-drugs/", expected={200})
    if isinstance(drug_id, int):
        do("Record drug view", "POST", f"/api/catalog/drugs/{drug_id}/view/", json_body={}, expected={200})
        do("Drug reviews list", "GET", f"/api/catalog/drugs/{drug_id}/reviews/", auth=False, expected={200})
        do("Drug add review", "POST", f"/api/catalog/drugs/{drug_id}/reviews/", json_body={"rating": 5, "text": "smoke test"}, expected={201, 400, 401})
        do("Drug star rating", "POST", f"/api/catalog/drugs/{drug_id}/star-rating/", json_body={"stars": 5}, expected={200, 400})
        do("Drug analogs", "GET", f"/api/catalog/drugs/{drug_id}/analogs/", auth=False, expected={200})
        disc = do("Drug discussion list", "GET", f"/api/catalog/drugs/{drug_id}/discussion/", expected={200, 404})
        # post message only if endpoint exists (200 on GET means thread ok)
        if disc.status_code == 200:
            do("Drug discussion post", "POST", f"/api/catalog/drugs/{drug_id}/discussion/", json_body={"body": "smoke msg"}, expected={201, 400})

    # --- Support (JWT) ---
    do("Feedback ticket", "POST", "/api/support/feedback/", json_body={"message": "smoke feedback", "subject": "smoke", "email": ""}, expected={201, 400})
    do("Psychology inquiry", "POST", "/api/support/psychology/", json_body={"message": "smoke psychology"}, expected={201, 400})

    # --- Chat (JWT) ---
    th = do("Chat threads list", "GET", "/api/me/chat/threads/", expected={200})
    th_created = do("Chat thread create", "POST", "/api/me/chat/threads/", json_body={"title": "smoke"}, expected={201, 400})
    thread_id = None
    if isinstance(th_created.response_json, dict):
        thread_id = th_created.response_json.get("id")
    if isinstance(thread_id, int):
        do("Chat messages list", "GET", f"/api/me/chat/threads/{thread_id}/messages/", expected={200})
        do("Chat message post", "POST", f"/api/me/chat/threads/{thread_id}/messages/", json_body={"body": "smoke msg"}, expected={201, 400})

    # --- Relax (AllowAny) ---
    do("Relax feed gif", "GET", "/api/relax/feed/", auth=False, params={"category": "gif"}, expected={200})
    do("Relax feed video", "GET", "/api/relax/feed/", auth=False, params={"category": "video"}, expected={200})

    # --- Survey (JWT) ---
    do("Survey submit", "POST", "/api/me/survey/", json_body={"slug": "smoke", "answers": {"q1": "a"}, "comment": ""}, expected={201, 400})

    # --- History (JWT) ---
    rec = do(
        "Disease record create (minimal)",
        "POST",
        "/api/me/disease-records/",
        json_body={"date_of_illness": "2026-01-01", "title": "smoke", "symptoms": "кашель"},
        expected={201, 400},
    )
    record_id = None
    if isinstance(rec.response_json, dict):
        record_id = rec.response_json.get("id")
    do("Disease records list", "GET", "/api/me/disease-records/", expected={200})
    if isinstance(record_id, int):
        do("Disease record detail", "GET", f"/api/me/disease-records/{record_id}/", expected={200})
        do("Disease record patch", "PATCH", f"/api/me/disease-records/{record_id}/", json_body={"symptoms": "кашель, температура"}, expected={200})
        # doctor visit create
        v = do(
            "Doctor visit create",
            "POST",
            "/api/me/disease-records/doctor-visits/",
            data={
                "record_id": str(record_id),
                "visit_date": "2026-01-02",
                "specialty": "Терапевт",
                "doctor_full_name": "smoke",
                "diagnosis": "",
                "medicines_text": "",
                "procedures_text": "",
            },
            expected={201, 400},
        )
        visit_id = v.response_json.get("id") if isinstance(v.response_json, dict) else None
        if isinstance(visit_id, int):
            do("Doctor visit patch", "PATCH", f"/api/me/doctor-visits/{visit_id}/", json_body={"diagnosis": "smoke"}, expected={200})
            do("Doctor visit delete", "DELETE", f"/api/me/doctor-visits/{visit_id}/", expected={204})
        # analysis create (no photo)
        a = do(
            "Analysis create",
            "POST",
            "/api/me/disease-records/analyses/",
            data={
                "record_id": str(record_id),
                "taken_date": "2026-01-03",
                "name": "smoke",
                "result_text": "ok",
            },
            expected={201, 400},
        )
        analysis_id = a.response_json.get("id") if isinstance(a.response_json, dict) else None
        if isinstance(analysis_id, int):
            # OCR should 400 because no photo (this is still a useful smoke check)
            do(
                "Analysis OCR (expected fail if no photo)",
                "POST",
                "/api/me/disease-records/analyses/ocr/",
                data={
                    "record_id": str(record_id),
                    "analysis_id": str(analysis_id),
                    "mode": "append",
                },
                expected={400, 503, 502},
            )
            do("Analysis delete", "DELETE", f"/api/me/analyses/{analysis_id}/", expected={204})
        # prescription create
        p = do(
            "Prescription create",
            "POST",
            "/api/me/disease-records/prescriptions/",
            data={"record_id": str(record_id), "note": "smoke"},
            expected={201, 400},
        )
        pres_id = p.response_json.get("id") if isinstance(p.response_json, dict) else None
        if isinstance(pres_id, int):
            do("Prescription patch", "PATCH", f"/api/me/prescriptions/{pres_id}/", json_body={"note": "smoke2"}, expected={200})
            do("Prescription delete", "DELETE", f"/api/me/prescriptions/{pres_id}/", expected={204})
        # cleanup record
        do("Disease record delete", "DELETE", f"/api/me/disease-records/{record_id}/", expected={204})

    # --- Admin (JWT staff only) ---
    do("Admin summary (may be 403 for non-staff)", "GET", "/api/admin/metrics/summary/", expected={200, 403})

    # summary
    total = len(results)
    failed = [r for r in results if not r.ok]
    print("\n--- Summary ---")
    print(f"Total steps: {total}")
    print(f"Failed: {len(failed)}")
    if failed:
        print("\nFailed steps:")
        for r in failed:
            print(f"- {r.method} {r.url} -> {r.status_code} :: {r.name}")
        return 1
    return 0


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(description="Smoke-test MedicAI REST API (exclude WS and auth endpoints).")
    p.add_argument("--base-url", default="http://127.0.0.1:8000", help="API host, e.g. http://127.0.0.1:8000")
    p.add_argument("--token", required=True, help="JWT access token (Bearer)")
    args = p.parse_args(argv)
    return run_smoke(base_url=args.base_url, token=args.token)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

