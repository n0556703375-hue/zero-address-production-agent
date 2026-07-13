import json
from pathlib import Path

from agents import Agent, Runner, function_tool


ROOT = Path(__file__).parent
SHOTS_PATH = ROOT / "data" / "trailer_shots.json"


def _shots() -> list[dict]:
    return json.loads(SHOTS_PATH.read_text(encoding="utf-8"))


@function_tool
def get_project_bible() -> str:
    """Return the binding world, story, visual, and production rules for Zero Address."""
    return (ROOT / "knowledge" / "world_bible.md").read_text(encoding="utf-8")


@function_tool
def get_trailer_shot(shot_number: int) -> str:
    """Return the approved source data for one trailer shot, numbered 1 through 20."""
    shot = next((item for item in _shots() if item["shot"] == shot_number), None)
    if not shot:
        return "לא נמצא שוט כזה. המספר חייב להיות בין 1 ל־20."
    return json.dumps(shot, ensure_ascii=False, indent=2)


@function_tool
def list_trailer_shots() -> str:
    """Return a compact list of all 20 trailer shots and their current status."""
    rows = [
        {"shot": s["shot"], "duration": s["duration"], "title": s["title"], "status": s["status"]}
        for s in _shots()
    ]
    return json.dumps(rows, ensure_ascii=False, indent=2)


production_agent = Agent(
    name="מנהלת ההפקה — כתובת אפס",
    model="gpt-4.1",
    instructions=(ROOT / "docs" / "prompt.md").read_text(encoding="utf-8"),
    tools=[get_project_bible, get_trailer_shot, list_trailer_shots],
)


async def ask_agent(message: str) -> str:
    result = await Runner.run(production_agent, message)
    return result.final_output
