import os
from pathlib import Path

import uvicorn
from agents import Agent, Runner
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field


for env_file in (Path(".env.local"), Path("../.env.local")):
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            if line.startswith("OPENAI_API_KEY="):
                os.environ.setdefault("OPENAI_API_KEY", line.split("=", 1)[1].strip())


SHOTS = [
    "מרום בלילה", "הרכבת הלבנה", "עיר שמזהה הכול", "ליאורה באטלס",
    "אי־התאמת שכבה", "הדלת מסרבת", "כתובת אפס", "דלת השירות",
    "יורדות מתחת לעיר", "חשיפת רובע הדרום", "נוכחות אפס", "ברכה סופרת",
    "הילה לא משויכת", "תמר והציר הלבן", "06:00", "פינוי בטיחותי",
    "מיכל רצה", "שלוש חזיתות", "הרכבת הריקה", "לא מחכה לזה"
]

PROMPT = """את מנהלת ההפקה הראשית של הסרט 'כתובת אפס'. עבדי בעברית ובצורה מוכנה לביצוע.
מקור האמת: מותחן עתידני־ריאליסטי נשי בשנת 2194 בעיר מרום. תסריט 1.4, 55 סצנות. הטריילר כולל 20 שוטים וכ־72 שניות.
האטלס קובע כתובות, דלתות, תחבורה ושירותים. המיפוי הלילי מסתיים לפני הציר הלבן ב־06:00. כתובת אפס היא כתובת שהמערכת הפסיקה להכיר בה. רובע הדרום חי פיזית אך המערכת רואה אותו כאזור שירות ריק. מנגנון החזרה חד־פעמי בלבד. הפתרון נשען על אימות אנושי, עדויות ורשימות קהילה.
דמויות: ליאורה שחר, 26, חוקרת מפות; מיכל שחר, 17, אחותה; תמר ארבל, מתכננת הציר; דבורה; רוחמה; ברכה; הילה; נטע; וקול האטלס הנשי והרגוע.
אסתטיקה: עתיד מאופק וריאליסטי. מרום לבן־כחול, נקי, קר וסטרילי. רובע הדרום חם, אנושי, צפוף וחי. לא סייברפאנק, לא ניאון כבד ולא עומס רובוטים. נשים ונערות בלבד, לבוש צנוע, בלי רומנטיקה ובלי אלימות גרפית.
סדר העבודה: רפרנסים לדמויות וללוקיישנים; מפת שוטים; דף הפקה; פרומפט Magnific; רציפות; אישור; וידאו; אודיו; עריכה. אל תדלגי שלב ואל תשני עלילה בלי אישור.
בדף הפקה כללי: מטרה ורגש; קומפוזיציה, עדשה וזווית; דמויות ופעולה; לוקיישן, תאורה וצבע; פרומפט Magnific באנגלית; negative prompt; תנועת וידאו; אודיו וליפסינק; QA ורציפות.
העדיפי שוטים בני 2.5–5 שניות, פעולה אחת ותנועת מצלמה אחת. שמרי על זהות פנים, לבוש, לוקיישן, אור ואביזרים. אסרי מריחות, שינויי פנים, כפילויות, אצבעות פגומות וטקסט משובש. ליפסינק מלא בעיקר בשוטים 8, 12, 13, 14 ו־20.
רשימת השוטים לפי הסדר: """ + ", ".join(f"{i+1}. {name}" for i, name in enumerate(SHOTS))

agent = Agent(name="מנהלת ההפקה — כתובת אפס", model="gpt-4.1", instructions=PROMPT)
app = FastAPI(title="כתובת אפס — מנהלת ההפקה")


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=12000)


HTML = """<!doctype html><html lang='he' dir='rtl'><meta charset='utf-8'><meta name='viewport' content='width=device-width'><title>כתובת אפס</title><style>body{margin:0;background:radial-gradient(circle at 90% 0,#163449,#071019 40%);color:#edf6fa;font-family:Arial}.app{max-width:920px;margin:auto;padding:32px}h1{color:#bceeff}.box{background:#0d1822;border:1px solid #233746;border-radius:16px;padding:18px;margin:15px 0;white-space:pre-wrap;line-height:1.6}textarea{width:100%;height:90px;background:#102431;color:white;border:1px solid #315267;border-radius:14px;padding:14px;box-sizing:border-box;font:inherit}button{background:#bceeff;color:#071019;border:0;border-radius:12px;padding:12px 18px;font-weight:bold;margin:5px;cursor:pointer}</style><div class='app'><h1>כתובת אפס — מנהלת ההפקה</h1><p>סוכן הפקת AI · תסריט 1.4 · טריילר 20 שוטים</p><button onclick="ask('בני תוכנית מסודרת ליצירת רפרנסים לדמויות וללוקיישנים לפני השוטים.')">ערכת רפרנסים</button><button onclick="ask('הכיני דף הפקה מלא לשוט 1.')">שוט 1</button><button onclick="ask('הציגי את 20 שוטי הטריילר.')">כל השוטים</button><div id='chat'></div><textarea id='q' placeholder='כתבי משימה לסוכן…'></textarea><button onclick='ask(q.value)'>שליחה</button></div><script>async function ask(t){if(!t)return;chat.innerHTML+=`<div class=box><b>את:</b> ${t}</div>`;q.value='';let d=document.createElement('div');d.className='box';d.textContent='עובדת על המשימה…';chat.appendChild(d);try{let r=await fetch('/api/chat',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({message:t})});let j=await r.json();d.textContent=j.answer||j.detail}catch(e){d.textContent='שגיאת חיבור'}}</script></html>"""


@app.get("/", response_class=HTMLResponse)
async def home():
    return HTML


@app.get("/health")
async def health():
    return {"status": "ok", "agent": "כתובת אפס", "api_key_configured": bool(os.getenv("OPENAI_API_KEY"))}


@app.get("/api/shots")
async def shots():
    return [{"shot": i + 1, "title": title, "status": "ממתין"} for i, title in enumerate(SHOTS)]


@app.post("/api/chat")
async def chat(request: ChatRequest):
    if not os.getenv("OPENAI_API_KEY"):
        raise HTTPException(status_code=503, detail="מפתח OpenAI API אינו מוגדר בשרת.")
    try:
        result = await Runner.run(agent, request.message)
        return {"answer": result.final_output}
    except Exception as exc:
        raise HTTPException(status_code=502, detail="הסוכן לא הצליח להשיב כרגע.") from exc


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "8000")))
