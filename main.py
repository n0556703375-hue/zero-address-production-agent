import asyncio
import os
from pathlib import Path

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from agent import ROOT, ask_agent, _shots


def load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("OPENAI_API_KEY="):
            os.environ.setdefault("OPENAI_API_KEY", line.split("=", 1)[1].strip())


for candidate in (ROOT / ".env.local", ROOT.parent / ".env.local"):
    load_env_file(candidate)


app = FastAPI(title="מנהלת ההפקה — כתובת אפס")


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=12000)


@app.get("/")
async def home() -> FileResponse:
    return FileResponse(ROOT / "static" / "index.html")


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "agent": "כתובת אפס", "api_key_configured": bool(os.getenv("OPENAI_API_KEY"))}


@app.get("/api/shots")
async def shots() -> list[dict]:
    return _shots()


@app.post("/api/chat")
async def chat(request: ChatRequest) -> dict:
    if not os.getenv("OPENAI_API_KEY"):
        raise HTTPException(status_code=503, detail="מפתח OpenAI API אינו מוגדר בשרת.")
    try:
        answer = await ask_agent(request.message)
        return {"answer": answer}
    except Exception as exc:
        raise HTTPException(status_code=502, detail="הסוכן לא הצליח להשיב כרגע.") from exc


async def cli() -> None:
    print("מנהלת ההפקה של כתובת אפס מוכנה. כתבי 'יציאה' לסיום.")
    while True:
        message = input("את: ").strip()
        if message.lower() in {"יציאה", "exit", "quit"}:
            break
        if message:
            print("סוכן:", await ask_agent(message))


if __name__ == "__main__":
    port = os.getenv("PORT")
    if port:
        uvicorn.run(app, host="0.0.0.0", port=int(port))
    else:
        asyncio.run(cli())
