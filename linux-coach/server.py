from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import json
import os
import tempfile
from threading import Lock
from course import advance, course_state, public_lessons

ROOT = Path(__file__).resolve().parent
PAGES = ROOT / "pages"
DATA = ROOT / "progress.json"
HOST = "127.0.0.1"
PORT = int(os.environ.get("LINUX_COACH_PORT", "8765"))
CORRECT = {
    "pwd": "مسیر پوشه‌ای که الان داخلش هستم",
    "path": "report.txt",
    "ls": "ls",
    "identity": "whoami",
}
CHALLENGES = {"service": 1, "permission": 2, "disk": 1, "network": 2}
LAB_ANSWERS = {
    "status": "systemctl status nginx",
    "log": "journalctl -u nginx -n 20",
    "interpret_log": "port_busy",
    "dns": "getent hosts api.example.com",
    "interpret_dns": "dns_failure",
}
REFLECTION_STEPS = {"read_mode", "explain_denial", "safe_fix"}
IDENTITY_ANSWERS = {"owner": 1, "identity": 0, "sudo_u": 2, "membership": 1, "transfer": 2}
PORT_ANSWERS = {"listen": 1, "process": 2, "inspect": 0, "transfer": 2}
INCIDENT_STEPS = {"map_502", "test_upstream", "read_app_log", "recovery_plan"}
LIVE_STEPS = {"two_outputs", "pipe", "merge"}
GUIDED_ANSWERS = {
    "redirect": {"ترمینال", "صفحه", "روی صفحه", "روی ترمینال", "terminal"},
    "pipe": {"2", "۲", "٢", "دو"},
    "merge": {"yes", "بله", "آره", "اره", "آری"},
    "input": {"1", "۱", "١", "یک"},
    "tee": {"hello"},
    "arguments": {"2", "۲", "٢", "دو"},
    "combine": {"هر دو", "هردو", "both"},
}
PROGRESS_LOCK = Lock()


def read_data():
    if not DATA.exists():
        return {"answers": {}, "history": []}
    return json.loads(DATA.read_text(encoding="utf-8"))


def write_data(data):
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=DATA.parent, delete=False) as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
        temp = handle.name
    os.replace(temp, DATA)


class Handler(BaseHTTPRequestHandler):
    def send_json(self, status, obj):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/api/course":
            data = read_data()
            self.send_json(200, {
                "lessons": public_lessons(),
                "state": course_state(data),
            })
            return
        if self.path == "/api/progress":
            self.send_json(200, read_data())
            return
        if self.path not in ("/", "/index.html", "/challenge.html", "/lab.html", "/permissions.html", "/identity.html", "/port.html", "/incident.html", "/live.html", "/roadmap.html"):
            self.send_error(404)
            return
        if self.path not in ("/", "/index.html"):
            self.send_response(302)
            self.send_header("Location", "/")
            self.end_headers()
            return
        body = (PAGES / "index.html").read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        with PROGRESS_LOCK:
            self.save_answer()

    def save_answer(self):
        if self.path not in ("/api/answer", "/api/challenge", "/api/lab", "/api/reflection", "/api/identity", "/api/port", "/api/incident", "/api/live", "/api/guided", "/api/course"):
            self.send_error(404)
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length < 1 or length > 4096:
                raise ValueError("Invalid request size")
            payload = json.loads(self.rfile.read(length))
            if not isinstance(payload, dict):
                raise ValueError("Expected a JSON object")
            data = read_data()
            if self.path == "/api/course":
                state = advance(data, payload)
                write_data(data)
                self.send_json(200, state)
                return
            from datetime import datetime, timezone
            now = datetime.now(timezone.utc).isoformat()
            if self.path == "/api/answer":
                question = payload.get("question")
                answer = payload.get("answer")
                if not isinstance(question, str) or not isinstance(answer, str):
                    raise ValueError("Invalid answer")
                if question not in {"setup", "pwd", "path", "ls", "identity", "diagnosis", "confidence"}:
                    raise ValueError("Unknown question")
                if len(answer) > 600:
                    raise ValueError("Answer too long")
                data["answers"][question] = answer
                data["history"].append({"at": now, "question": question, "answer": answer})
            elif self.path == "/api/challenge":
                question = payload.get("question")
                choice = payload.get("choice")
                reason = payload.get("reason")
                if question not in CHALLENGES or type(choice) is not int or choice not in range(4):
                    raise ValueError("Invalid challenge choice")
                if not isinstance(reason, str) or not 8 <= len(reason.strip()) <= 600:
                    raise ValueError("Explain your reason in at least 8 characters")
                item = {"at": now, "question": question, "choice": choice, "reason": reason.strip(), "decision_correct": choice == CHALLENGES[question]}
                data.setdefault("challenges", {})[question] = item
                data["history"].append({"type": "challenge", **item})
                data["challenge_assessment"] = {
                    "answered": len(data["challenges"]),
                    "total": len(CHALLENGES),
                    "decisions_correct": sum(x["decision_correct"] for x in data["challenges"].values()),
                    "needs_review": [q for q, x in data["challenges"].items() if not x["decision_correct"]],
                    "reasoning_status": "Needs human review; choice score does not grade written reasoning",
                }
            elif self.path == "/api/lab":
                step = payload.get("step")
                answer = payload.get("answer")
                if step not in LAB_ANSWERS or not isinstance(answer, str) or len(answer) > 200:
                    raise ValueError("Invalid lab answer")
                correct = " ".join(answer.strip().split()) == LAB_ANSWERS[step]
                entry = {"type": "lab", "at": now, "step": step, "answer": answer.strip(), "correct": correct}
                data["history"].append(entry)
                data.setdefault("lab", {}).setdefault("attempts", []).append(entry)
                if correct:
                    data["lab"].setdefault("completed", {})[step] = now
                data["lab"]["assessment"] = {
                    "completed": len(data["lab"].get("completed", {})),
                    "total": len(LAB_ANSWERS),
                    "wrong_attempts": sum(not x["correct"] for x in data["lab"]["attempts"]),
                }
            elif self.path == "/api/reflection":
                step = payload.get("step")
                answer = payload.get("answer")
                if step not in REFLECTION_STEPS or not isinstance(answer, str) or not 12 <= len(answer.strip()) <= 1200:
                    raise ValueError("Write a reason of at least 12 characters")
                entry = {"type": "reflection", "at": now, "step": step, "answer": answer.strip()}
                data["history"].append(entry)
                data.setdefault("reflections", {}).setdefault("attempts", []).append(entry)
                data["reflections"].setdefault("latest", {})[step] = entry
                data["reflections"]["assessment"] = {
                    "answered": len(data["reflections"]["latest"]),
                    "total": len(REFLECTION_STEPS),
                    "reasoning_status": "Awaiting tutor review; no automatic correctness claim",
                }
            elif self.path == "/api/identity":
                step = payload.get("step")
                choice = payload.get("choice")
                reason = payload.get("reason")
                if step not in IDENTITY_ANSWERS or type(choice) is not int or choice not in range(4):
                    raise ValueError("Invalid identity choice")
                if not isinstance(reason, str) or not 12 <= len(reason.strip()) <= 800:
                    raise ValueError("Explain your choice in at least 12 characters")
                correct = choice == IDENTITY_ANSWERS[step]
                entry = {"type": "identity", "at": now, "step": step, "choice": choice, "reason": reason.strip(), "decision_correct": correct}
                data["history"].append(entry)
                data.setdefault("identity", {}).setdefault("attempts", []).append(entry)
                if correct:
                    data["identity"].setdefault("completed", {})[step] = now
                data["identity"]["assessment"] = {
                    "completed": len(data["identity"].get("completed", {})),
                    "total": len(IDENTITY_ANSWERS),
                    "wrong_attempts": sum(not x["decision_correct"] for x in data["identity"]["attempts"]),
                    "reasoning_status": "Awaiting tutor review",
                }
            elif self.path == "/api/port":
                step = payload.get("step")
                choice = payload.get("choice")
                reason = payload.get("reason")
                if step not in PORT_ANSWERS or type(choice) is not int or choice not in range(4):
                    raise ValueError("Invalid port choice")
                if not isinstance(reason, str) or not 10 <= len(reason.strip()) <= 800:
                    raise ValueError("Explain your choice in at least 10 characters")
                correct = choice == PORT_ANSWERS[step]
                entry = {"type": "port", "at": now, "step": step, "choice": choice, "reason": reason.strip(), "decision_correct": correct}
                data["history"].append(entry)
                data.setdefault("port", {}).setdefault("attempts", []).append(entry)
                if correct:
                    data["port"].setdefault("completed", {})[step] = now
                data["port"]["assessment"] = {
                    "completed": len(data["port"].get("completed", {})),
                    "total": len(PORT_ANSWERS),
                    "wrong_attempts": sum(not x["decision_correct"] for x in data["port"]["attempts"]),
                    "reasoning_status": "Awaiting tutor review",
                }
            elif self.path == "/api/guided":
                step, answer = payload.get("step"), payload.get("answer")
                if not isinstance(step, str) or step not in GUIDED_ANSWERS or not isinstance(answer, str) or not 1 <= len(answer.strip()) <= 80:
                    raise ValueError("Invalid guided lesson answer")
                normalized = " ".join(answer.strip().casefold().split()).rstrip(".!؟?")
                correct = normalized in GUIDED_ANSWERS[step]
                entry = {"type": "guided", "at": now, "step": step, "answer": answer.strip(), "correct": correct}
                data["history"].append(entry)
                guided = data.setdefault("guided", {"attempts": [], "completed": {}})
                guided["attempts"].append(entry)
                if correct:
                    guided["completed"][step] = now
            else:
                track, steps = ("live", LIVE_STEPS) if self.path == "/api/live" else ("incident", INCIDENT_STEPS)
                step = payload.get("step")
                answer = payload.get("answer")
                minimum = 1 if track == "live" else 20
                if not isinstance(step, str) or step not in steps or not isinstance(answer, str) or not minimum <= len(answer.strip()) <= 1500:
                    raise ValueError("Invalid step or answer length")
                entry = {"type": track, "at": now, "step": step, "answer": answer.strip()}
                data["history"].append(entry)
                record = data.setdefault(track, {})
                record.setdefault("attempts", []).append(entry)
                record.setdefault("latest", {})[step] = entry
                record["assessment"] = {
                    "answered": len(record["latest"]),
                    "total": len(steps),
                    "reasoning_status": "Awaiting tutor review; free text is not automatically graded",
                }
            data["assessment"] = {
                "technical_correct": sum(data["answers"].get(q) == expected for q, expected in CORRECT.items()),
                "technical_total": len(CORRECT),
                "answered": len(data["answers"]),
                "total": 7,
                "needs_review": [q for q, expected in CORRECT.items() if q in data["answers"] and data["answers"][q] != expected],
            }
            write_data(data)
            if self.path in ("/api/lab", "/api/identity", "/api/port", "/api/guided"):
                data["last_correct"] = correct
            self.send_json(200, data)
        except (ValueError, json.JSONDecodeError) as exc:
            self.send_json(400, {"error": str(exc)})


if __name__ == "__main__":
    print(f"Linux Coach: http://{HOST}:{PORT}", flush=True)
    print(f"Progress file: {DATA}", flush=True)
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()
