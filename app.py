import asyncio

from google.adk.agents import Agent
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types
from tool import create_polars_tools
import config

from dotenv import load_dotenv
load_dotenv()

SYSTEM_PROMPT = """You are a data analytics agent for a sales dataset. Answer with numbers you computed, never estimates.

Tool:
- execute_polars_code: runs Python with `pl` (Polars 2.0) and `csv_path` predefined. Only printed output comes back.

How to write the code:
1. Start lazy: `lf = pl.scan_csv(csv_path, try_parse_dates=True)`. Never use read_csv or pandas.
2. On your first call, `print(lf.collect_schema())` to learn the column names, dtypes, and confirm date parsing before doing anything else. This reads no data.
3. Select only the columns the question needs, and filter early.
4. Before collecting the answer, run `print(q.collect_schema())` on the final query to check column names and types without reading the data. Fix any error there first.
5. Then `print(q.collect())`. Sort explicitly when order matters: group_by and join output order is not guaranteed.
6. Keep output small: aggregate, or use .head(20). Never print the full table.

Polars 2.0 rules:
- Parse strings with .str.to_date() or .str.to_datetime(), not .cast(pl.Date).
- is_in() needs matching types. Cast first.
- Use .unpivot(), not .melt(). Use nulls_equal=, not join_nulls=.

If the code fails, read the error, fix it, and retry. Stop after 3 attempts and say what blocked you.

Answer format: the direct answer first, with the key numbers. Then at most 2 short observations. Mention nulls or filters that changed the result.
"""

APP_NAME = "polars_sales_analytics"
USER_ID = "local_user"
MODEL = config.LLM_MODEL


def create_agent() -> Agent:
    """Create and configure the data analytics agent."""
    agent = Agent(
        name="sales_analytics_agent",
        model=MODEL,
        instruction=SYSTEM_PROMPT,
        tools=create_polars_tools(),
    )
    return agent


async def _run_query(agent: Agent, question: str) -> tuple[str, list[dict]]:
    session_service = InMemorySessionService()
    runner = Runner(agent=agent, app_name=APP_NAME, session_service=session_service)
    session = await session_service.create_session(app_name=APP_NAME, user_id=USER_ID)
    content = types.Content(role="user", parts=[types.Part(text=question)])
    response_parts: list[str] = []
    trace_by_id: dict[str, dict] = {}
    trace_order: list[str] = []

    async for event in runner.run_async(
        user_id=USER_ID, session_id=session.id, new_message=content
    ):
        for part in event.content.parts if event.content else []:
            if part.function_call:
                call = part.function_call
                call_id = call.id or f"{call.name}-{len(trace_order)}"
                trace_by_id[call_id] = {
                    "tool": call.name,
                    "arguments": dict(call.args or {}),
                    "result": None,
                    "error": False,
                }
                trace_order.append(call_id)
            elif part.function_response:
                result = part.function_response
                call_id = result.id
                entry = trace_by_id.get(call_id)
                if entry is None:
                    call_id = f"orphan-{len(trace_order)}"
                    entry = {"tool": result.name or "tool", "arguments": {}, "result": None, "error": False}
                    trace_by_id[call_id] = entry
                    trace_order.append(call_id)
                entry["result"] = result.response
                entry["error"] = bool((result.response or {}).get("error")) if isinstance(result.response, dict) else False
            elif part.text and event.is_final_response():
                response_parts.append(part.text)

    return "\n".join(response_parts), [trace_by_id[key] for key in trace_order]


def run_query_with_trace(agent: Agent, question: str) -> tuple[str, list[dict]]:
    return asyncio.run(_run_query(agent, question))


def run_query(agent: Agent, question: str) -> str:
    """
    Run a query against the agent and return the response.

    Args:
        agent: The configured Google ADK agent
        question: User's question about the data

    Returns:
        Agent's response as a string
    """
    return run_query_with_trace(agent, question)[0]


def interactive_mode():
    """Run the agent in interactive mode."""
    agent = create_agent()

    while True:
        try:
            question = input("\n📊 Your question: ").strip()

            if not question:
                continue

            if question.lower() in ["quit", "exit", "q"]:
                print("\nGoodbye!")
                break

            print("\nAnalyzing...\n")
            response = run_query(agent, question)
            print("\nAnswer:")
            print("-" * 40)
            print(response)
            print("-" * 40)

        except KeyboardInterrupt:
            print("\n\nGoodbye!")
            break
        except Exception as e:
            print(f"\Try again later...")


def main():
    """Main entry point."""
    import sys

    if len(sys.argv) > 1:
        question = " ".join(sys.argv[1:])
        agent = create_agent()
        response = run_query(agent, question)
        print(response)
    else:
        interactive_mode()


if __name__ == "__main__":
    main()
