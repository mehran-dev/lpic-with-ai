"""Local assessment server; written answers are stored without automatic grading."""
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Lock
import json
import os
import tempfile
from assessment import QUESTIONS, public_sections
from lessons import LESSONS, LESSON_IDS

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "progress.json"
PAGE = ROOT / "pages" / "index.html"
HOST = "127.0.0.1"
PORT = int(os.environ.get("LINUX_COACH_PORT", "8765"))
LOCK = Lock()
RATINGS = {"unknown", "heard", "guided", "independent", "work"}


def read_data():
    if not DATA.exists():
        return {"version": 2, "responses": {}, "attempts": [], "profile": {}}
    return json.loads(DATA.read_text(encoding="utf-8"))


def write_data(data):
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=DATA.parent, delete=False) as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
        name = handle.name
    os.replace(name, DATA)


class Handler(BaseHTTPRequestHandler):
    def send_json(self, status, value):
        body = json.dumps(value, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/api/lessons":
            self.send_json(200, {"lessons": LESSONS, "state": read_data()})
            return
        if self.path == "/api/assessment":
            self.send_json(200, {"sections": public_sections(), "state": read_data()})
            return
        if self.path == "/api/export":
            self.send_json(200, read_data())
            return
        if self.path not in {"/", "/index.html", "/assessment.html", "/roadmap.html"}:
            self.send_error(404)
            return
        if self.path == "/assessment.html":
            page = ROOT / "pages" / "assessment.html"
        elif self.path == "/roadmap.html":
            page = ROOT / "pages" / "roadmap.html"
        else:
            page = PAGE
        body = page.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        if self.path not in {"/api/response", "/api/profile", "/api/mentor", "/api/lesson"}:
            self.send_error(404)
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 1 <= length <= 32768:
                raise ValueError("اندازهٔ درخواست نامعتبر است")
            payload = json.loads(self.rfile.read(length))
            if not isinstance(payload, dict):
                raise ValueError("دادهٔ نامعتبر")
            with LOCK:
                data = read_data()
                now = datetime.now(timezone.utc).isoformat()
                if self.path == "/api/lesson":
                    lesson_id = payload.get("id")
                    answer = payload.get("answer")
                    if not isinstance(lesson_id, str) or lesson_id not in LESSON_IDS or not isinstance(answer, str) or len(answer) > 12000:
                        raise ValueError("درس یا پاسخ نامعتبر است")
                    entry = {"at": now, "id": lesson_id, "answer": answer.strip(), "review": "pending" if answer.strip() else "not_requested"}
                    course = data.setdefault("lessons", {"records": {}, "events": []})
                    course["records"][lesson_id] = entry
                    course["events"].append(entry)
                elif self.path == "/api/mentor":
                    answer = payload.get("answer")
                    if payload.get("mission") != "mount-basics-1" or not isinstance(answer, str) or not 1 <= len(answer.strip()) <= 12000:
                        raise ValueError("پاسخ تمرین نامعتبر است")
                    entry = {"at": now, "mission": "mount-basics-1", "answer": answer.strip(), "review": "pending"}
                    mentor = data.setdefault("mentor", {"attempts": [], "latest": {}})
                    mentor["attempts"].append(entry)
                    mentor["latest"]["mount-basics-1"] = entry
                elif self.path == "/api/response":
                    question_id = payload.get("id")
                    rating = payload.get("rating")
                    answer = payload.get("answer")
                    if question_id not in QUESTIONS or rating not in RATINGS:
                        raise ValueError("سؤال یا سطح نامعتبر است")
                    if not isinstance(answer, str) or len(answer) > 12000:
                        raise ValueError("متن پاسخ باید حداکثر ۱۲۰۰۰ نویسه باشد")
                    if not answer.strip() and rating != "unknown":
                        raise ValueError("توضیحت را بنویس یا «هنوز بلد نیستم» را انتخاب کن")
                    entry = {"at": now, "id": question_id, "rating": rating,
                             "answer": answer.strip(), "review": "pending"}
                    data.setdefault("responses", {})[question_id] = entry
                    data.setdefault("attempts", []).append(entry)
                else:
                    for key in ("experience", "target", "preferences"):
                        value = payload.get(key, "")
                        if not isinstance(value, str) or len(value) > 4000:
                            raise ValueError("متن معرفی نامعتبر است")
                    data["profile"] = {key: payload.get(key, "").strip()
                                       for key in ("experience", "target", "preferences")}
                    data["profile"]["at"] = now
                write_data(data)
            self.send_json(200, {"state": data})
        except (ValueError, json.JSONDecodeError) as error:
            self.send_json(400, {"error": str(error)})


if __name__ == "__main__":
    print(f"ارزیابی لینوکس: http://{HOST}:{PORT}", flush=True)
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()
