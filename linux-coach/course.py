"""Curriculum and saved state for the single-page Linux coach."""

from datetime import datetime, timezone
from pathlib import Path
import shlex
import unicodedata


def load_lessons():
    lessons = {}
    occurrences = {}
    for line in Path(__file__).with_name("curriculum.txt").read_text(encoding="utf-8").splitlines():
        if not line or line.startswith("#"):
            continue
        objective, title, rest = line.split("|", 2)
        explanation, question, answers = rest.rsplit("|", 2)
        occurrences[objective] = occurrences.get(objective, 0) + 1
        key = f"{objective}-{occurrences[objective]}"
        lessons[key] = {
            "id": key, "objective": objective, "title": title,
            "explanation": explanation, "question": question, "answers": answers.split(";"),
        }
    return lessons


LESSONS = load_lessons()
LS_BASICS, LS_OPTIONS = "103.3-1", "103.3-2"
LS_INTRO = (
    LS_BASICS, "103.3-5", LS_OPTIONS, "103.3-7", "103.3-8",
    "103.3-9", "103.3-3", "103.3-6",
)
LS_IDS = LS_INTRO + tuple(
    key for key in LESSONS if key.startswith("103.3-") and key not in (*LS_INTRO, "103.3-4")
)
LESSON_IDS = LS_IDS + tuple(key for key in LESSONS if key not in LS_IDS)
EXTRA_EXAMPLES = {
    LS_BASICS: "فرض کن در پوشهٔ پروژهٔ یک بازی هستی. pwd آدرس آن پوشه را می‌گوید. ls چیزهایی مثل maps و README را که داخلش هستند فهرست می‌کند.",
    LS_OPTIONS: "تصور کن ls فقط app.py را نشان می‌دهد. با ls -a، فایل .env هم پیدا می‌شود. ls -l ستون‌های اندازه و مالک را اضافه می‌کند. ls -la هر دو کار را یک‌جا انجام می‌دهد.",
    "103.3-3": "عدد 1048576 بایت را تصور کن. -l ستون اندازه می‌دهد و -h نمایش آن را به 1.0M تبدیل می‌کند. ترکیبشان می‌شود ls -lh.",
    "103.4-1": "شل دو مسیر خروجی دارد. لوله فقط شمارهٔ ۱ را به tee می‌دهد. بدون 2>&1، شمارهٔ ۲ مستقیم به ترمینال می‌رود.",
    "103.3-15": "مسیر پیوند و مقصدش را جدا در نظر بگیر. یکی ورودی فهرست است و دیگری فایلی که پس از دنبال کردن پیوند به آن می‌رسی. بزرگی و کوچکی حروف گزینه‌ها مهم است.",
}


def comparable(text, *, ignore_case=True):
    text = unicodedata.normalize("NFKC", text).translate(str.maketrans(
        "يكة٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "یکه01234567890123456789"
    ))
    text = " ".join(text.replace("\u200c", " ").split())
    if ignore_case:
        text = text.casefold()
    return text.strip("`").rstrip(".…؟?! ").strip("`")


def ls_signature(text):
    """Match equivalent forms of the independent short flags taught here."""
    try:
        parts = shlex.split(text)
    except ValueError:
        return None
    if not parts or parts[0] != "ls" or "--" in parts:
        return None
    flags, names = [], []
    for part in parts[1:]:
        if part.startswith("--"):
            return None
        if part.startswith("-") and len(part) > 1:
            flags.extend(part[1:])
        else:
            names.append(part)
    return sorted(flags), names


def matches_answer(answer, expected):
    is_ls = expected.startswith("ls ") or expected == "ls" or expected.startswith("-")
    case_sensitive = is_ls or expected.startswith("LC_ALL=") or (
        len(expected) == 1 and expected.isascii() and expected.isalpha()
    )
    value = comparable(answer, ignore_case=not case_sensitive)
    target = comparable(expected, ignore_case=not case_sensitive)
    if value == target:
        return True
    signature = ls_signature(target) if is_ls else None
    return signature is not None and signature == ls_signature(value)


def course_state(data):
    course = data.get("course", {})
    return {
        "current": course.get("current", LS_BASICS),
        "records": course.get("records", {}),
        "last_feedback": course.get("last_feedback"),
        "previous_feedback": course.get("previous_feedback"),
        "attempt_count": len(course.get("events", [])),
    }


def next_lesson(current, records):
    index = LESSON_IDS.index(current)
    remaining = LESSON_IDS[index + 1:] + LESSON_IDS[:index + 1]
    return next((key for key in remaining if not records.get(key, {}).get("status")), None)


def advance(data, payload):
    action = payload.get("action")
    key = payload.get("lesson")
    if not isinstance(key, str) or key not in LESSONS or action not in (
        "open", "next", "skip", "known", "hint", "answer",
    ):
        raise ValueError("Invalid lesson action")
    answer = payload.get("answer", "")
    note = payload.get("note", "")
    if not isinstance(answer, str) or not isinstance(note, str):
        raise ValueError("Invalid answer or note")
    if action == "answer" and not answer.strip():
        action = "skip"

    course = data.setdefault("course", {})
    records = course.setdefault("records", {})
    active = course.get("current", LS_BASICS)
    if action != "open" and key != active:
        raise ValueError("Lesson changed; reload progress")

    lesson = LESSONS[key]
    record = records.setdefault(key, {})
    feedback = course.get("last_feedback")
    outcome = None
    if action == "hint":
        record["help"] = True
        outcome = "hint"
        message = EXTRA_EXAMPLES.get(key) or f"نمونهٔ یک جواب «{lesson['answers'][0]}» است. {lesson['explanation']}"
    elif action == "answer":
        correct = any(matches_answer(answer, value) for value in lesson["answers"])
        if correct:
            record.update(status="passed", level=max(record.get("level", 0), 1))
            outcome = "correct"
            message = f"درست است. {lesson['explanation']}"
        else:
            record["incorrect"] = record.get("incorrect", 0) + 1
            if record.get("status") != "passed":
                record["status"] = "deferred"
            outcome = "retry"
            message = f"نمونهٔ جواب «{lesson['answers'][0]}» است. {lesson['explanation']} این مرحله برای مرور در نقشه می‌ماند."
    if note.strip():
        record["note"] = note.strip()

    if action == "answer":
        course["previous_feedback"] = {"lesson": key, "title": lesson["title"], "kind": outcome, "text": message}
        course["last_feedback"] = None
        course["current"] = next_lesson(key, records)
    elif outcome:
        course["last_feedback"] = {"lesson": key, "title": lesson["title"], "kind": outcome, "text": message}
        course["current"] = key
    else:
        if action == "known":
            record.update(status=record.get("status") or "reported", level=max(1, record.get("level", 0)))
            course["previous_feedback"] = {
                "title": lesson["title"], "text": "گفتی این بخش را بلدی و می‌خواهی جلوتر بروی. آشنایی‌ات ثبت شد؛ سنجش این مرحله برای مرور می‌ماند.",
            }
        elif action == "skip":
            if record.get("status") != "passed":
                record["status"] = "deferred"
            course["previous_feedback"] = {"title": lesson["title"], "text": "این تمرین برای مرور بعدی در نقشه نشانه‌گذاری شد."}
        elif feedback:
            course["previous_feedback"] = feedback
        if action == "next" and record.get("status") != "passed":
            raise ValueError("Complete or defer this lesson first")
        destination = key if action == "open" else next_lesson(key, records)
        if action == "known" and key == LS_BASICS and records.get(LS_OPTIONS, {}).get("status") != "passed":
            destination = LS_OPTIONS
            if any(word in comparable(note) for word in ("اندازه", "حجم", "-h")):
                destination = "103.3-3"
        course["current"] = destination
        course["last_feedback"] = None
    course.setdefault("events", []).append({
        "at": datetime.now(timezone.utc).isoformat(), "lesson": key, "action": action,
        "answer": answer.strip(), "note": note.strip(), "outcome": outcome,
    })
    return course_state(data)


def public_lessons():
    return [
        {
            **{k: v for k, v in LESSONS[key].items() if k != "answers"},
            "series": "ls" if key in LS_IDS else None,
            "guide": EXTRA_EXAMPLES.get(
                key, "از مثال بالا شروع کن. ببین سؤال دنبال نام یک مفهوم، معنی بخشی از خروجی یا خود فرمان است و همان بخش را پیدا کن."
            ),
        }
        for key in LESSON_IDS
    ]
