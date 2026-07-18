import os
import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Literal

import uvicorn
from agents import Agent, Runner
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = Path(os.getenv("FILM_OS_DB", BASE_DIR / "film_os.db"))

for env_file in (BASE_DIR / ".env.local", BASE_DIR.parent / ".env.local"):
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            if line.startswith("OPENAI_API_KEY="):
                os.environ.setdefault("OPENAI_API_KEY", line.split("=", 1)[1].strip())

SHOT_TITLES = [
    "מרום בלילה", "הרכבת הלבנה", "עיר שמזהה הכול", "ליאורה באטלס",
    "אי־התאמת שכבה", "הדלת מסרבת", "כתובת אפס", "דלת השירות",
    "יורדות מתחת לעיר", "חשיפת רובע הדרום", "נוכחות אפס", "ברכה סופרת",
    "הילה לא משויכת", "תמר והציר הלבן", "06:00", "פינוי בטיחותי",
    "מיכל רצה", "שלוש חזיתות", "הרכבת הריקה", "לא מחכה לזה"
]

STATUSES = [
    "מתוכנן", "רפרנס", "פרומפט מוכן", "תמונה מאושרת",
    "וידאו מוכן", "וידאו מאושר", "אודיו", "סופי"
]

PROMPT = """את מנהלת ההפקה הראשית של הסרט 'כתובת אפס'. עבדי בעברית ובצורה מוכנה לביצוע.
מקור האמת: מותחן עתידני־ריאליסטי נשי בשנת 2194 בעיר מרום. תסריט 1.4, 55 סצנות.
הטריילר כולל 20 שוטים וכ־72 שניות.
האסתטיקה עתידנית מאופקת: מרום לבן־כחול, קר וסטרילי; רובע הדרום חם, צפוף ואנושי.
נשים ונערות בלבד, לבוש צנוע, בלי רומנטיקה ובלי אלימות גרפית.
סדר העבודה: רפרנסים; מפת שוטים; דף הפקה; פרומפט; רציפות; אישור; וידאו; אודיו; עריכה.
בכל דף הפקה כללי: מטרה ורגש; קומפוזיציה ועדשה; דמויות ופעולה; לוקיישן, תאורה וצבע;
פרומפט Magnific באנגלית; negative prompt; תנועת וידאו; אודיו; QA ורציפות.
העדיפי שוטים בני 2.5–5 שניות, פעולה אחת ותנועת מצלמה אחת.
רשימת השוטים: """ + ", ".join(f"{i+1}. {name}" for i, name in enumerate(SHOT_TITLES))

agent = Agent(name="מנהלת ההפקה — כתובת אפס", model="gpt-4.1", instructions=PROMPT)
app = FastAPI(title="AI Film OS — כתובת אפס")


def db():
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def init_db() -> None:
    with closing(db()) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS shots (
                id INTEGER PRIMARY KEY,
                title TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'מתוכנן',
                notes TEXT NOT NULL DEFAULT '',
                prompt TEXT NOT NULL DEFAULT '',
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)
        for shot_id, title in enumerate(SHOT_TITLES, start=1):
            conn.execute(
                "INSERT OR IGNORE INTO shots (id, title) VALUES (?, ?)",
                (shot_id, title),
            )
        conn.commit()


@app.on_event("startup")
def startup() -> None:
    init_db()


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=12000)


class ShotUpdate(BaseModel):
    status: Literal[
        "מתוכנן", "רפרנס", "פרומפט מוכן", "תמונה מאושרת",
        "וידאו מוכן", "וידאו מאושר", "אודיו", "סופי"
    ] | None = None
    notes: str | None = Field(default=None, max_length=10000)
    prompt: str | None = Field(default=None, max_length=30000)


def shot_to_dict(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "title": row["title"],
        "status": row["status"],
        "notes": row["notes"],
        "prompt": row["prompt"],
        "updated_at": row["updated_at"],
    }


@app.get("/health")
def health():
    return {
        "status": "ok",
        "app": "AI Film OS",
        "project": "כתובת אפס",
        "api_key_configured": bool(os.getenv("OPENAI_API_KEY")),
        "database": str(DB_PATH),
    }


@app.get("/api/shots")
def list_shots():
    with closing(db()) as conn:
        rows = conn.execute("SELECT * FROM shots ORDER BY id").fetchall()
    return [shot_to_dict(row) for row in rows]


@app.get("/api/shots/{shot_id}")
def get_shot(shot_id: int):
    with closing(db()) as conn:
        row = conn.execute("SELECT * FROM shots WHERE id = ?", (shot_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="השוט לא נמצא.")
    return shot_to_dict(row)


@app.patch("/api/shots/{shot_id}")
def update_shot(shot_id: int, update: ShotUpdate):
    fields = update.model_dump(exclude_none=True)
    if not fields:
        raise HTTPException(status_code=400, detail="לא התקבלו שדות לעדכון.")

    assignments = ", ".join(f"{field} = ?" for field in fields)
    values = list(fields.values()) + [shot_id]

    with closing(db()) as conn:
        exists = conn.execute("SELECT 1 FROM shots WHERE id = ?", (shot_id,)).fetchone()
        if not exists:
            raise HTTPException(status_code=404, detail="השוט לא נמצא.")
        conn.execute(
            f"UPDATE shots SET {assignments}, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            values,
        )
        conn.commit()
        row = conn.execute("SELECT * FROM shots WHERE id = ?", (shot_id,)).fetchone()
    return shot_to_dict(row)


@app.post("/api/shots/{shot_id}/generate")
async def generate_shot_sheet(shot_id: int):
    with closing(db()) as conn:
        row = conn.execute("SELECT * FROM shots WHERE id = ?", (shot_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="השוט לא נמצא.")
    if not os.getenv("OPENAI_API_KEY"):
        raise HTTPException(status_code=503, detail="מפתח OpenAI API אינו מוגדר בשרת.")

    request = (
        f"הכיני דף הפקה מלא לשוט {shot_id}: {row['title']}. "
        f"הערות קיימות: {row['notes'] or 'אין'}. "
        "החזירי מסמך מוכן להפקה, כולל פרומפט באנגלית ו-negative prompt."
    )
    try:
        result = await Runner.run(agent, request)
    except Exception as exc:
        raise HTTPException(status_code=502, detail="הסוכן לא הצליח ליצור דף הפקה.") from exc

    output = result.final_output
    with closing(db()) as conn:
        conn.execute(
            """UPDATE shots
               SET prompt = ?, status = 'פרומפט מוכן', updated_at = CURRENT_TIMESTAMP
               WHERE id = ?""",
            (output, shot_id),
        )
        conn.commit()
    return {"shot_id": shot_id, "answer": output, "status": "פרומפט מוכן"}


@app.post("/api/chat")
async def chat(request: ChatRequest):
    if not os.getenv("OPENAI_API_KEY"):
        raise HTTPException(status_code=503, detail="מפתח OpenAI API אינו מוגדר בשרת.")
    try:
        result = await Runner.run(agent, request.message)
        return {"answer": result.final_output}
    except Exception as exc:
        raise HTTPException(status_code=502, detail="הסוכן לא הצליח להשיב כרגע.") from exc


HTML = r"""<!doctype html>
<html lang="he" dir="rtl">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>AI Film OS — כתובת אפס</title>
<style>
:root{font-family:Arial,sans-serif;color:#eef7fb;background:#071019}
*{box-sizing:border-box}body{margin:0;background:radial-gradient(circle at 90% 0,#163449,#071019 42%)}
header{padding:24px 28px;border-bottom:1px solid #284252;position:sticky;top:0;background:#071019e8;backdrop-filter:blur(10px)}
h1{margin:0;color:#bceeff;font-size:26px}.sub{margin-top:7px;color:#9fb8c6}
main{max-width:1250px;margin:auto;padding:24px}.toolbar{display:flex;gap:10px;flex-wrap:wrap;margin-bottom:18px}
button,select,textarea{font:inherit}button{border:0;border-radius:10px;padding:10px 14px;font-weight:700;cursor:pointer;background:#bceeff;color:#071019}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:14px}
.card{background:#0d1822;border:1px solid #233746;border-radius:16px;padding:16px}
.num{color:#72a8c4;font-size:13px}.title{font-weight:700;font-size:18px;margin:7px 0 12px}
select,textarea{width:100%;background:#102431;color:#fff;border:1px solid #315267;border-radius:10px;padding:10px}
textarea{min-height:82px;resize:vertical;margin-top:10px}.actions{display:flex;gap:8px;margin-top:10px}
.actions button{flex:1;padding:9px}.muted{color:#8fa6b3;font-size:12px;margin-top:8px}
#modal{display:none;position:fixed;inset:0;background:#000b;align-items:center;justify-content:center;padding:20px}
.dialog{max-width:850px;width:100%;max-height:88vh;overflow:auto;background:#0d1822;border:1px solid #315267;border-radius:18px;padding:20px}
pre{white-space:pre-wrap;line-height:1.55}.close{float:left}
</style>
</head>
<body>
<header><h1>AI Film OS — כתובת אפס</h1><div class="sub">Pipeline שוטים נשמר · יצירת דפי הפקה · סטטוס רציף</div></header>
<main>
<div class="toolbar"><button onclick="loadShots()">רענון</button><span id="summary"></span></div>
<div id="grid" class="grid"></div>
</main>
<div id="modal"><div class="dialog"><button class="close" onclick="closeModal()">סגירה</button><h2 id="modalTitle"></h2><pre id="modalBody"></pre></div></div>
<script>
const statuses = ["מתוכנן","רפרנס","פרומפט מוכן","תמונה מאושרת","וידאו מוכן","וידאו מאושר","אודיו","סופי"];
async function api(url, options={}) {
  const response = await fetch(url, {headers:{"Content-Type":"application/json"}, ...options});
  const data = await response.json();
  if(!response.ok) throw new Error(data.detail || "שגיאה");
  return data;
}
async function loadShots(){
  const shots = await api("/api/shots");
  document.getElementById("summary").textContent = `${shots.filter(s=>s.status==="סופי").length}/${shots.length} שוטים סופיים`;
  document.getElementById("grid").innerHTML = shots.map(s => `
    <article class="card">
      <div class="num">שוט ${s.id}</div>
      <div class="title">${escapeHtml(s.title)}</div>
      <select onchange="saveStatus(${s.id},this.value)">
        ${statuses.map(st=>`<option ${st===s.status?"selected":""}>${st}</option>`).join("")}
      </select>
      <textarea id="notes-${s.id}" placeholder="הערות הפקה…">${escapeHtml(s.notes)}</textarea>
      <div class="actions">
        <button onclick="saveNotes(${s.id})">שמירה</button>
        <button onclick="generate(${s.id})">יצירת דף</button>
      </div>
      ${s.prompt ? `<div class="muted"><button onclick="showPrompt(${s.id})">הצגת דף ההפקה</button></div>` : ""}
    </article>`).join("");
}
async function saveStatus(id,status){await api(`/api/shots/${id}`,{method:"PATCH",body:JSON.stringify({status})});}
async function saveNotes(id){
  await api(`/api/shots/${id}`,{method:"PATCH",body:JSON.stringify({notes:document.getElementById(`notes-${id}`).value})});
}
async function generate(id){
  const data = await api(`/api/shots/${id}/generate`,{method:"POST"});
  show(data.answer, `דף הפקה — שוט ${id}`);
  await loadShots();
}
async function showPrompt(id){
  const shot=await api(`/api/shots/${id}`);
  show(shot.prompt, `דף הפקה — שוט ${id}`);
}
function show(body,title){modal.style.display="flex";modalTitle.textContent=title;modalBody.textContent=body}
function closeModal(){modal.style.display="none"}
function escapeHtml(value){return String(value||"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#39;"}[c]))}
loadShots().catch(e=>alert(e.message));
</script>
</body></html>"""


@app.get("/", response_class=HTMLResponse)
def home():
    return HTML


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "8000")))
