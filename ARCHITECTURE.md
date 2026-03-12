# sample_mcp_agents — Architecture & Code Flow

This document explains how the **sample_mcp_agents** project is structured and how control flows from the user query to the MCP server and back.

---

## 1. Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                              ENTRY: app.py                                       │
│                         asyncio.run(main())                                      │
└─────────────────────────────────────────────────────────────────────────────────┘
                                          │
                                          ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                              main() (async)                                      │
│  1. Enter MCPServerManager([demo_mcp_server])  →  start MCP subprocess           │
│  2. Build MainAgent with manager.active_servers (connected MCP)                   │
│  3. Runner.run(main_agent, input=user_query)                                      │
│  4. Exit manager  →  stop MCP subprocess                                         │
└─────────────────────────────────────────────────────────────────────────────────┘
          │                                    │
          │                                    │ Runner.run
          ▼                                    ▼
┌──────────────────────┐            ┌─────────────────────────────────────────────┐
│  MCPServerManager    │            │              MainAgent                       │
│  - Connects to       │            │  - instructions (orchestrator)                │
│    demo_mcp_server   │            │  - tools: [merchandiser_tool]                 │
│  - Spawns:           │◄───────────│  - mcp_servers: manager.active_servers       │
│    python            │   stdio    │     → tools from MCP (get_product_specs,      │
│    mcp_server.py     │   (IPC)    │       check_inventory)                       │
│  - Exposes            │            │  - LLM decides: call MCP tools and/or       │
│    active_servers     │            │    merchandise_recommendation                │
└──────────────────────┘            └─────────────────────────────────────────────┘
          │                                        │
          │ stdio (stdin/stdout)                    │ tool calls
          ▼                                        ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                         mcp_server.py (subprocess)                               │
│  FastMCP("demo-mcp-server")  →  mcp.run(transport="stdio")                        │
│                                                                                   │
│  Tools exposed over MCP:                                                          │
│    • get_product_specs(sku)  →  returns product catalog entry                    │
│    • check_inventory(sku)    →  returns inventory + ETA                           │
└─────────────────────────────────────────────────────────────────────────────────┘
          │
          │ when MainAgent calls "merchandiser_recommendation"
          ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                    MerchandiserAgent (as tool)                                    │
│  - Wrapped by merchandiser_agent.as_tool(...)                                     │
│  - Receives product specs + inventory from MainAgent                              │
│  - Returns sales recommendation (target customer, positioning, selling points)    │
└─────────────────────────────────────────────────────────────────────────────────┘
          │
          ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│  result.final_output  →  printed to console                                       │
└─────────────────────────────────────────────────────────────────────────────────┘
```

**Summary of boxes:**

| Component | File / Location | Role |
|-----------|------------------|------|
| **Entry** | `app.py` | Starts the app with `asyncio.run(main())`. |
| **main()** | `app.py` | Creates MCP manager, builds MainAgent, runs Runner, cleans up. |
| **MCPServerManager** | `agents.mcp` | Starts/stops the MCP subprocess and exposes connected servers. |
| **MainAgent** | `app.py` | Orchestrator agent: has MCP tools + merchandiser tool; calls LLM and tools. |
| **MCP subprocess** | `mcp_server.py` | FastMCP server; exposes `get_product_specs` and `check_inventory` over stdio. |
| **MerchandiserAgent** | `app.py` (as tool) | Specialist agent used as a tool to generate the sales pitch. |

---

## 2. Code Flow (Step-by-Step)

Below is the order in which things happen when you run `python app.py`.

### Phase 1: Startup (before any user query)

1. **Python runs `app.py`**
   - Imports: `Agent`, `Runner`, `MCPServerManager`, `MCPServerStdio`.
   - Defines `merchandiser_agent` (specialist agent).
   - Wraps it as a tool: `merchandiser_tool = merchandiser_agent.as_tool(...)`.
   - Defines the MCP server config: `demo_mcp_server = MCPServerStdio(params={"command": "python", "args": ["mcp_server.py"]}, name="demo")`.
   - No process is started yet; this is only configuration.

2. **`if __name__ == "__main__"`**
   - Calls `asyncio.run(main())`, so control enters the async `main()`.

### Phase 2: Entering the MCP manager and building the agent

3. **`async with MCPServerManager([demo_mcp_server]) as manager:`**
   - The context manager starts the MCP server process:
     - Runs: `python mcp_server.py`.
     - `mcp_server.py` runs `mcp.run(transport="stdio")` and listens on stdin/stdout for MCP messages.
   - The agents SDK connects to this process over stdio (stdin/stdout).
   - After connection, `manager.active_servers` is a list of connected MCP server objects (with a `.name` attribute, etc.).

4. **Building MainAgent inside the `async with`**
   - `main_agent = Agent(name="MainAgent", instructions="...", tools=[merchandiser_tool], mcp_servers=manager.active_servers)`.
   - So MainAgent has:
     - One function tool: `merchandise_recommendation` (the MerchandiserAgent).
     - All tools from the MCP server: `get_product_specs`, `check_inventory`.

### Phase 3: Running the agent (where control moves around)

5. **`result = await Runner.run(main_agent, input=user_query)`**
   - Control goes into the **agents SDK** (Runner).
   - Runner sends the user message to the **LLM** (MainAgent’s model).
   - The LLM returns a response that may include **tool calls**.

6. **Tool calls (control leaves the Runner and goes to tools)**
   - If the LLM calls **MCP tools** (e.g. `get_product_specs("SKU-999")` or `check_inventory("SKU-999")`):
     - Runner uses the **MCPServerStdio** connection to send the tool call over **stdio** to the subprocess.
     - Control is effectively in **mcp_server.py**: the corresponding `@mcp.tool()` function runs (`get_product_specs` or `check_inventory`).
     - The return value (dict) is sent back over stdio to the Runner.
   - If the LLM calls **merchandise_recommendation**:
     - Runner invokes the **MerchandiserAgent** (the agent-as-tool).
     - Control is in the **agents SDK** again, running MerchandiserAgent with the given inputs (e.g. specs + inventory).
     - MerchandiserAgent’s output is returned as the tool result to the Runner.

7. **Loop until the agent is done**
   - Runner gives the **tool results** back to the LLM.
   - The LLM may issue more tool calls or produce a final text answer.
   - This repeats until the LLM returns a final answer with no more tool calls (or the run otherwise completes).

8. **`result` and `result.final_output`**
   - When the run is finished, `result` holds the final output.
   - Control returns to your code: `print(result.final_output)`.

### Phase 4: Cleanup

9. **Exiting `async with MCPServerManager(...)`**
   - The context manager exits.
   - The MCP subprocess (`python mcp_server.py`) is stopped; stdio connection is closed.

10. **Program ends**
    - `main()` returns; `asyncio.run(main())` finishes; process exits.

---

## 3. How Control Moves (Simple Explanation)

### Who is in charge of what?

- **Your code (app.py)**  
  - Decides: “Run this query with this agent.”  
  - Hands over control to **Runner.run(...)** and gets it back when the run is done.

- **Runner (agents SDK)**  
  - In charge of the **conversation loop**: send user/tool messages to the LLM, get back responses and tool calls.  
  - When the LLM requests a tool call, the Runner **temporarily gives control** to the right place (MCP server or MerchandiserAgent), then takes it back and continues the loop.

- **MCP server (mcp_server.py)**  
  - Only in control when the Runner calls an **MCP tool** (`get_product_specs` or `check_inventory`).  
  - It receives a request over stdio, runs the matching Python function, and sends the result back. It does not run the LLM or decide what to do next.

- **MerchandiserAgent**  
  - Only in control when the Runner calls the **merchandise_recommendation** tool.  
  - It behaves like a small agent (with its own LLM call) that returns a sales pitch. Control returns to the Runner when that tool call completes.

### Flow in one sentence

**Control starts in `app.py` → goes to Runner → Runner talks to the LLM and, when the LLM asks for a tool, hands control to either the MCP subprocess (mcp_server.py) or the MerchandiserAgent tool → results come back to Runner → Runner continues until the LLM is done → control returns to `app.py`, which prints the result.**

### Picture of control flow (simplified)

```
app.py (main)
    │
    ├─► MCPServerManager  ──► starts subprocess: mcp_server.py (stdio)
    │
    ├─► Runner.run(main_agent, input=user_query)
    │       │
    │       ├─► LLM (MainAgent)  ──► “I’ll call get_product_specs(SKU-999)”
    │       │         │
    │       │         └─► Runner calls MCP  ──► mcp_server.py: get_product_specs()  ──► result back to Runner
    │       │
    │       ├─► LLM  ──► “I’ll call check_inventory(SKU-999)”
    │       │         │
    │       │         └─► Runner calls MCP  ──► mcp_server.py: check_inventory()  ──► result back to Runner
    │       │
    │       ├─► LLM  ──► “I’ll call merchandise_recommendation(specs, inventory)”
    │       │         │
    │       │         └─► Runner runs MerchandiserAgent  ──► result back to Runner
    │       │
    │       └─► LLM  ──► final answer  ──► result.final_output
    │
    └─► print(result.final_output)  ──► exit manager (stop mcp_server.py)
```

---

## 4. File Roles (Quick Reference)

| File | Purpose |
|------|--------|
| **app.py** | Entry point. Defines agents, MCP server config, and `main()`: manager, MainAgent, Runner.run, print result. |
| **mcp_server.py** | MCP server subprocess. Exposes `get_product_specs` and `check_inventory` over stdio. |
| **mcp_agent.config.yaml** | Optional config for MCP server (command/args). app.py currently builds `MCPServerStdio` directly in code instead of loading this file. |

---

## 5. Data Flow (What Flows Where)

- **User query**  
  `"Give me details and a sales pitch for SKU-999"` → `Runner.run(..., input=user_query)` → LLM.

- **LLM → MCP (stdio)**  
  Tool name + arguments (e.g. `get_product_specs`, `{"sku": "SKU-999"}`) → subprocess stdin.  
  Result (e.g. `{"name": "AP Z9", "wifi": "Wi-Fi 7", ...}`) → subprocess stdout → Runner.

- **LLM → MerchandiserAgent tool**  
  Tool name `merchandise_recommendation` + arguments (specs, inventory) → Runner runs MerchandiserAgent → tool result (sales pitch text) → Runner → LLM.

- **Final answer**  
  LLM’s last message (text) → `result.final_output` → your code prints it.

This architecture and code flow document should give a clear, detailed picture of how control moves from app.py to the MCP server and the merchandiser tool and back.
