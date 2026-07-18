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
ASSET_TYPES = ["דמות", "לוקיישן", "אביזר", "לבוש"]

SEED_ASSETS = [
    ("דמות", "ליאורה שחר", "חוקרת מפות בת 26; מדויקת, ערנית ומאופקת.", "חליפת עבודה עתידנית צנועה בתכלת־לבן, צווארון גבוה.", ""),
    ("דמות", "מיכל שחר", "בת 17; מהירה, רגישה ונחושה.", "לבוש עתידני צנוע ופשוט יותר מליאורה.", ""),
    ("דמות", "תמר ארבל", "מתכננת הציר הלבן; סמכותית ושקולה.", "לבוש מקצועי נקי ומובנה.", ""),
    ("לוקיישן", "מרום", "עיר עתידנית ריאליסטית, מסודרת וסטרילית.", "לבן־כחול, כסף מאט, אור קר ונקי.", ""),
    ("לוקיישן", "רובע הדרום", "רובע חי שאינו מזוהה במערכת.", "חם, צפוף, אישי ואנושי.", ""),
    ("לוקיישן", "מרכז האטלס", "מרכז מיפוי ובקרה עתידני.", "משטחים לבנים, שכבות מידע עדינות, ללא ניאון.", ""),
    ("אביזר", "סורק פרק־יד", "כלי עבודה דק של ליאורה לבדיקת שכבות וכתובות.", "לבן־כסוף, מסך כחול עדין.", ""),
    ("אביזר", "העותק החתום", "מנגנון חד־פעמי שמעניק חלון פעולה קצר.", "אובייקט קטן, רשמי ומוגן.", ""),
]

PROMPT = """את מנהלת ההפקה הראשית של הסרט 'כתובת אפס'. עבדי בעברית ובצורה מוכנה לביצוע.
מקור האמת: מותחן עתידני־ריאליסטי נשי בשנת 2194 בעיר מרום. תסריט 1.4, 55 סצנות.
הטריילר כולל 20 שוטים וכ־72 שניות.
האסתטיקה עתידנית מאופקת: מרום לבן־כחול, קר וסטרילי; רובע הדרום חם, צפוף ואנושי.
נשים ונערות בלבד, לבוש צנוע, בלי רומנטיקה ובלי אלימות גרפית.
סדר העבודה: רפרנסים; מפת שוטים; דף הפקה; פרומפט; רציפות; אישור; וידאו; אודיו; עריכה.
בכל דף הפקה: מטרה ורגש; קומפוזיציה ועדשה; דמויות ופעולה; לוקיישן, תאורה וצבע;
פרומפט Magnific באנגלית; negative prompt; תנועת וידאו; אודיו; QA ורציפות.
העדיפי שוטים בני 2.5–5 שניות, פעולה אחת ותנועת מצלמה אחת."""

agent = Agent(name="מנהלת ההפקה — כתובת אפס", model="gpt-4.1", instructions=PROMPT)
app = FastAPI(title="AI Film OS — כתובת אפס", version="2.0")


def db():
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def init_db():
    with closing(db()) as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS shots (
            id INTEGER PRIMARY KEY,
            title TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'מתוכנן',
            notes TEXT NOT NULL DEFAULT '',
            prompt TEXT NOT NULL DEFAULT '',
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS assets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            asset_type TEXT NOT NULL,
            name TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            visual_rules TEXT NOT NULL DEFAULT '',
            reference_url TEXT NOT NULL DEFAULT '',
            approved INTEGER NOT NULL DEFAULT 0,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS shot_assets (
            shot_id INTEGER NOT NULL,
            asset_id INTEGER NOT NULL,
            PRIMARY KEY (shot_id, asset_id),
            FOREIGN KEY (shot_id) REFERENCES shots(id) ON DELETE CASCADE,
            FOREIGN KEY (asset_id) REFERENCES assets(id) ON DELETE CASCADE
        );
        """)
        for shot_id, title in enumerate(SHOT_TITLES, start=1):
            conn.execute("INSERT OR IGNORE INTO shots (id,title) VALUES (?,?)", (shot_id, title))
        count = conn.execute("SELECT COUNT(*) FROM assets").fetchone()[0]
        if count == 0:
            conn.executemany(
                """INSERT INTO assets
                (asset_type,name,description,visual_rules,reference_url)
                VALUES (?,?,?,?,?)""",
                SEED_ASSETS,
            )
        conn.commit()


@app.on_event("startup")
def startup():
    init_db()


class ShotUpdate(BaseModel):
    status: Literal[
        "מתוכנן", "רפרנס", "פרומפט מוכן", "תמונה מאושרת",
        "וידאו מוכן", "וידאו מאושר", "אודיו", "סופי"
    ] | None = None
    notes: str | None = Field(None, max_length=10000)
    prompt: str | None = Field(None, max_length=30000)


class AssetCreate(BaseModel):
    asset_type: Literal["דמות", "לוקיישן", "אביזר", "לבוש"]
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=10000)
    visual_rules: str = Field(default="", max_length=10000)
    reference_url: str = Field(default="", max_length=2000)
    approved: bool = False


class AssetUpdate(BaseModel):
    asset_type: Literal["דמות", "לוקיישן", "אביזר", "לבוש"] | None = None
    name: str | None = Field(None, min_length=1, max_length=200)
    description: str | None = Field(None, max_length=10000)
    visual_rules: str | None = Field(None, max_length=10000)
    reference_url: str | None = Field(None, max_length=2000)
    approved: bool | None = None


class AssetLinkRequest(BaseModel):
    asset_ids: list[int]


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=12000)


def rowdict(row):
    return dict(row)


@app.get("/health")
def health():
    return {
        "status": "ok",
        "version": "2.0",
        "project": "כתובת אפס",
        "api_key_configured": bool(os.getenv("OPENAI_API_KEY")),
    }


@app.get("/api/shots")
def list_shots():
    with closing(db()) as conn:
        rows = conn.execute("""
        SELECT s.*,
          (SELECT COUNT(*) FROM shot_assets sa WHERE sa.shot_id=s.id) AS asset_count
        FROM shots s ORDER BY s.id
        """).fetchall()
    return [rowdict(r) for r in rows]


@app.get("/api/shots/{shot_id}")
def get_shot(shot_id: int):
    with closing(db()) as conn:
        shot = conn.execute("SELECT * FROM shots WHERE id=?", (shot_id,)).fetchone()
        if not shot:
            raise HTTPException(404, "השוט לא נמצא.")
        assets = conn.execute("""
        SELECT a.* FROM assets a JOIN shot_assets sa ON sa.asset_id=a.id
        WHERE sa.shot_id=? ORDER BY a.asset_type,a.name
        """, (shot_id,)).fetchall()
    result = rowdict(shot)
    result["assets"] = [rowdict(a) for a in assets]
    return result


@app.patch("/api/shots/{shot_id}")
def update_shot(shot_id: int, update: ShotUpdate):
    fields = update.model_dump(exclude_none=True)
    if not fields:
        raise HTTPException(400, "לא התקבלו שדות לעדכון.")
    with closing(db()) as conn:
        if not conn.execute("SELECT 1 FROM shots WHERE id=?", (shot_id,)).fetchone():
            raise HTTPException(404, "השוט לא נמצא.")
        sets = ", ".join(f"{k}=?" for k in fields)
        conn.execute(
            f"UPDATE shots SET {sets},updated_at=CURRENT_TIMESTAMP WHERE id=?",
            [*fields.values(), shot_id],
        )
        conn.commit()
        row = conn.execute("SELECT * FROM shots WHERE id=?", (shot_id,)).fetchone()
    return rowdict(row)


@app.put("/api/shots/{shot_id}/assets")
def set_shot_assets(shot_id: int, request: AssetLinkRequest):
    with closing(db()) as conn:
        if not conn.execute("SELECT 1 FROM shots WHERE id=?", (shot_id,)).fetchone():
            raise HTTPException(404, "השוט לא נמצא.")
        valid = {
            r[0] for r in conn.execute(
                f"SELECT id FROM assets WHERE id IN ({','.join('?' * len(request.asset_ids))})",
                request.asset_ids,
            ).fetchall()
        } if request.asset_ids else set()
        if len(valid) != len(set(request.asset_ids)):
            raise HTTPException(400, "אחד הנכסים אינו קיים.")
        conn.execute("DELETE FROM shot_assets WHERE shot_id=?", (shot_id,))
        conn.executemany(
            "INSERT INTO shot_assets (shot_id,asset_id) VALUES (?,?)",
            [(shot_id, asset_id) for asset_id in request.asset_ids],
        )
        conn.commit()
    return {"shot_id": shot_id, "asset_ids": request.asset_ids}


@app.post("/api/shots/{shot_id}/generate")
async def generate_shot(shot_id: int):
    shot = get_shot(shot_id)
    if not os.getenv("OPENAI_API_KEY"):
        raise HTTPException(503, "מפתח OpenAI API אינו מוגדר בשרת.")
    asset_context = "\n".join(
        f"- {a['asset_type']}: {a['name']}. {a['description']} כללים: {a['visual_rules']}"
        for a in shot["assets"]
    ) or "לא שויכו נכסים; יש לציין שחסר מידע ולא להמציא זהות חזותית."
    request = f"""הכיני דף הפקה מלא לשוט {shot_id}: {shot['title']}.
הערות: {shot['notes'] or 'אין'}.
נכסים מאושרים/משויכים:
{asset_context}
השתמשי רק בנכסים המפורטים. החזירי מסמך מוכן להפקה כולל prompt באנגלית ו-negative prompt."""
    try:
        result = await Runner.run(agent, request)
    except Exception as exc:
        raise HTTPException(502, "הסוכן לא הצליח ליצור דף הפקה.") from exc
    with closing(db()) as conn:
        conn.execute(
            "UPDATE shots SET prompt=?,status='פרומפט מוכן',updated_at=CURRENT_TIMESTAMP WHERE id=?",
            (result.final_output, shot_id),
        )
        conn.commit()
    return {"answer": result.final_output}


@app.get("/api/assets")
def list_assets(asset_type: str | None = None):
    with closing(db()) as conn:
        if asset_type:
            rows = conn.execute(
                "SELECT * FROM assets WHERE asset_type=? ORDER BY name", (asset_type,)
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM assets ORDER BY asset_type,name").fetchall()
    return [rowdict(r) for r in rows]


@app.post("/api/assets")
def create_asset(asset: AssetCreate):
    with closing(db()) as conn:
        cur = conn.execute(
            """INSERT INTO assets
            (asset_type,name,description,visual_rules,reference_url,approved)
            VALUES (?,?,?,?,?,?)""",
            (
                asset.asset_type, asset.name, asset.description, asset.visual_rules,
                asset.reference_url, int(asset.approved),
            ),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM assets WHERE id=?", (cur.lastrowid,)).fetchone()
    return rowdict(row)


@app.patch("/api/assets/{asset_id}")
def update_asset(asset_id: int, update: AssetUpdate):
    fields = update.model_dump(exclude_none=True)
    if "approved" in fields:
        fields["approved"] = int(fields["approved"])
    if not fields:
        raise HTTPException(400, "לא התקבלו שדות לעדכון.")
    with closing(db()) as conn:
        if not conn.execute("SELECT 1 FROM assets WHERE id=?", (asset_id,)).fetchone():
            raise HTTPException(404, "הנכס לא נמצא.")
        sets = ", ".join(f"{k}=?" for k in fields)
        conn.execute(
            f"UPDATE assets SET {sets},updated_at=CURRENT_TIMESTAMP WHERE id=?",
            [*fields.values(), asset_id],
        )
        conn.commit()
        row = conn.execute("SELECT * FROM assets WHERE id=?", (asset_id,)).fetchone()
    return rowdict(row)


@app.delete("/api/assets/{asset_id}")
def delete_asset(asset_id: int):
    with closing(db()) as conn:
        cur = conn.execute("DELETE FROM assets WHERE id=?", (asset_id,))
        conn.commit()
    if cur.rowcount == 0:
        raise HTTPException(404, "הנכס לא נמצא.")
    return {"deleted": True}


@app.post("/api/chat")
async def chat(request: ChatRequest):
    if not os.getenv("OPENAI_API_KEY"):
        raise HTTPException(503, "מפתח OpenAI API אינו מוגדר בשרת.")
    result = await Runner.run(agent, request.message)
    return {"answer": result.final_output}


HTML = r"""<!doctype html><html lang="he" dir="rtl"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>AI Film OS</title>
<style>
:root{font-family:Arial;color:#eef7fb;background:#071019}*{box-sizing:border-box}
body{margin:0;background:radial-gradient(circle at 88% 0,#163449,#071019 43%)}
header{padding:22px 28px;border-bottom:1px solid #294352;background:#071019e8;position:sticky;top:0;z-index:2}
h1{margin:0;color:#bceeff}.sub{color:#9fb8c6;margin-top:7px}
main{max-width:1250px;margin:auto;padding:22px}.tabs{display:flex;gap:8px;margin-bottom:18px}
button{background:#bceeff;color:#071019;border:0;border-radius:10px;padding:10px 14px;font-weight:700;cursor:pointer}
button.secondary{background:#1b3443;color:#dff5ff;border:1px solid #315267}
.panel{display:none}.panel.active{display:block}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(270px,1fr));gap:14px}
.card{background:#0d1822;border:1px solid #233746;border-radius:15px;padding:15px}
.title{font-size:18px;font-weight:700;margin:7px 0 12px}.meta{color:#85a9bc;font-size:13px}
select,input,textarea{width:100%;background:#102431;color:white;border:1px solid #315267;border-radius:9px;padding:9px;font:inherit}
textarea{min-height:72px;resize:vertical;margin-top:8px}.row{display:flex;gap:8px;margin-top:9px}.row>*{flex:1}
.badge{display:inline-block;padding:4px 8px;border-radius:999px;background:#183748;color:#bceeff;font-size:12px}
.approved{background:#17452e;color:#b9f4d1}.form{max-width:720px;margin-bottom:18px}
#modal{display:none;position:fixed;inset:0;background:#000b;align-items:center;justify-content:center;padding:20px;z-index:4}
.dialog{width:min(900px,100%);max-height:90vh;overflow:auto;background:#0d1822;border:1px solid #315267;border-radius:17px;padding:20px}
pre{white-space:pre-wrap;line-height:1.55}.asset-checks{max-height:240px;overflow:auto;border:1px solid #315267;border-radius:10px;padding:10px}
.check{display:flex;gap:8px;align-items:center;padding:6px}.check input{width:auto}
</style></head><body>
<header><h1>AI Film OS — כתובת אפס</h1><div class="sub">גרסה 2 · Shot Pipeline + Asset Manager</div></header>
<main>
<div class="tabs"><button onclick="tab('shots')">שוטים</button><button onclick="tab('assets')">נכסים</button></div>
<section id="shots" class="panel active"><div id="shotSummary" class="sub"></div><div id="shotsGrid" class="grid"></div></section>
<section id="assets" class="panel">
<div class="card form">
<h2>נכס חדש</h2>
<div class="row"><select id="newType"><option>דמות</option><option>לוקיישן</option><option>אביזר</option><option>לבוש</option></select><input id="newName" placeholder="שם הנכס"></div>
<textarea id="newDesc" placeholder="תיאור וזהות"></textarea><textarea id="newRules" placeholder="כללים חזותיים ורציפות"></textarea>
<input id="newUrl" placeholder="קישור לתמונת רפרנס"><div class="row"><button onclick="createAsset()">הוספה</button></div>
</div><div id="assetsGrid" class="grid"></div></section>
</main>
<div id="modal"><div class="dialog"><button class="secondary" onclick="closeModal()">סגירה</button><h2 id="modalTitle"></h2><div id="modalBody"></div></div></div>
<script>
const statuses=["מתוכנן","רפרנס","פרומפט מוכן","תמונה מאושרת","וידאו מוכן","וידאו מאושר","אודיו","סופי"];
let allAssets=[];
const esc=v=>String(v??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#39;"}[c]));
async function api(url,opts={}){let r=await fetch(url,{headers:{"Content-Type":"application/json"},...opts});let d=await r.json();if(!r.ok)throw Error(d.detail||"שגיאה");return d}
function tab(id){document.querySelectorAll(".panel").forEach(x=>x.classList.remove("active"));document.getElementById(id).classList.add("active");if(id==="assets")loadAssets()}
async function loadShots(){let shots=await api("/api/shots");shotSummary.textContent=`${shots.filter(x=>x.status==="סופי").length}/${shots.length} שוטים סופיים`;shotsGrid.innerHTML=shots.map(s=>`<article class=card><div class=meta>שוט ${s.id} · ${s.asset_count} נכסים</div><div class=title>${esc(s.title)}</div><select onchange="saveShot(${s.id},{status:this.value})">${statuses.map(x=>`<option ${x===s.status?"selected":""}>${x}</option>`).join("")}</select><textarea id=n${s.id} placeholder="הערות">${esc(s.notes)}</textarea><div class=row><button onclick="saveShot(${s.id},{notes:n${s.id}.value})">שמירה</button><button onclick="chooseAssets(${s.id})">שיוך נכסים</button></div><div class=row><button onclick="generate(${s.id})">יצירת דף הפקה</button>${s.prompt?`<button class=secondary onclick="showPrompt(${s.id})">הצגה</button>`:""}</div></article>`).join("")}
async function saveShot(id,data){await api(`/api/shots/${id}`,{method:"PATCH",body:JSON.stringify(data)})}
async function loadAssets(){allAssets=await api("/api/assets");assetsGrid.innerHTML=allAssets.map(a=>`<article class=card><span class="badge ${a.approved?"approved":""}">${esc(a.asset_type)}${a.approved?" · מאושר":""}</span><div class=title>${esc(a.name)}</div><div>${esc(a.description)}</div><div class=meta style="margin-top:8px">${esc(a.visual_rules)}</div>${a.reference_url?`<div style="margin-top:8px"><a href="${esc(a.reference_url)}" target=_blank style="color:#bceeff">רפרנס</a></div>`:""}<div class=row><button onclick="approve(${a.id},${!a.approved})">${a.approved?"ביטול אישור":"אישור"}</button><button class=secondary onclick="removeAsset(${a.id})">מחיקה</button></div></article>`).join("")}
async function createAsset(){await api("/api/assets",{method:"POST",body:JSON.stringify({asset_type:newType.value,name:newName.value,description:newDesc.value,visual_rules:newRules.value,reference_url:newUrl.value})});newName.value=newDesc.value=newRules.value=newUrl.value="";loadAssets()}
async function approve(id,value){await api(`/api/assets/${id}`,{method:"PATCH",body:JSON.stringify({approved:value})});loadAssets()}
async function removeAsset(id){if(confirm("למחוק את הנכס?")){await api(`/api/assets/${id}`,{method:"DELETE"});loadAssets()}}
async function chooseAssets(id){allAssets=await api("/api/assets");let shot=await api(`/api/shots/${id}`);let selected=new Set(shot.assets.map(a=>a.id));modalTitle.textContent=`שיוך נכסים — שוט ${id}`;modalBody.innerHTML=`<div class=asset-checks>${allAssets.map(a=>`<label class=check><input type=checkbox value="${a.id}" ${selected.has(a.id)?"checked":""}><span>${esc(a.asset_type)} — ${esc(a.name)}</span></label>`).join("")}</div><div class=row><button onclick="saveLinks(${id})">שמירת שיוך</button></div>`;modal.style.display="flex"}
async function saveLinks(id){let ids=[...modalBody.querySelectorAll("input:checked")].map(x=>+x.value);await api(`/api/shots/${id}/assets`,{method:"PUT",body:JSON.stringify({asset_ids:ids})});closeModal();loadShots()}
async function generate(id){let d=await api(`/api/shots/${id}/generate`,{method:"POST"});showText(`דף הפקה — שוט ${id}`,d.answer);loadShots()}
async function showPrompt(id){let s=await api(`/api/shots/${id}`);showText(`דף הפקה — שוט ${id}`,s.prompt)}
function showText(t,b){modalTitle.textContent=t;modalBody.innerHTML=`<pre>${esc(b)}</pre>`;modal.style.display="flex"}
function closeModal(){modal.style.display="none"}
loadShots();
</script></body></html>"""


@app.get("/", response_class=HTMLResponse)
def home():
    return HTML


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "8000")))
