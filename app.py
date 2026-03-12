import asyncio
from agents import Agent, Runner
from agents.mcp import MCPServerManager, MCPServerStdio
from dotenv import load_dotenv
load_dotenv()

# ---------------------------------------------------------------------
# Specialist Agent (used as an Agent-as-Tool)
# ---------------------------------------------------------------------
merchandiser_agent = Agent(
    name="MerchandiserAgent",
    instructions="""
        You are a merchandising expert.
        Given product specs and inventory info,
        create a short sales recommendation with:
        - Target customer
        - Positioning
        - Two key selling points
    """
)

# Convert agent → tool
merchandiser_tool = merchandiser_agent.as_tool(
    tool_name="merchandise_recommendation",
    tool_description="Generate sales pitch using specs and inventory"
)

# MCP server (Agent expects MCPServer instances, not strings)
demo_mcp_server = MCPServerStdio(
    params={"command": "python", "args": ["mcp_server.py"]},
    name="demo",
)

# ---------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------
async def main():
    async with MCPServerManager([demo_mcp_server]) as manager:
        main_agent = Agent(
            name="MainAgent",
            instructions="""
                You are the main orchestrator.
                Flow:
                1. If a SKU is mentioned, fetch product specs using MCP.
                2. Fetch inventory details using MCP.
                3. Call the merchandise_recommendation tool.
                4. Return a structured final answer.
            """,
            tools=[merchandiser_tool],
            mcp_servers=manager.active_servers,
        )
        user_query = "Give me details and a sales pitch for SKU-123"
        result = await Runner.run(main_agent, input=user_query)
    print("\nFINAL OUTPUT:\n")
    print(result.final_output)


if __name__ == "__main__":
    asyncio.run(main())