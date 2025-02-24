from mainframe_orchestra import Task, Agent, OpenaiModels, Conduct
from chat.agents.web_research import web_research_agent
from chat.agents.memory_management import memory_management_agent
import asyncio

lumon_agent = Agent(
    agent_id="lumon_agent",
    role="Conductor",
    goal="To chat with and help the human user by coordinating your team of agents to carry out tasks.",
    attributes="You know that you can delegate tasks to your team of agents, and you can take outputs of agents and use them for subsequent tasks if needed. Your team includes a web research agent and a memory management agent.",
    llm=OpenaiModels.gpt_4o_mini,  # Or your preferred model
    tools=[
        Conduct.conduct_tool(web_research_agent, memory_management_agent)
    ]
)

async def create_lumon_task(user_input: str, conversation_history: list):
    
    # Simplified system prompt
    context = f"""
You are L.U.M.O.N., an AI assistant focused on being helpful and efficient in your responses.
Keep your responses clear and concise while maintaining a professional tone.
"""

    return await Task.create(
        agent=lumon_agent,
        context=context,
        messages=conversation_history,
        instruction=user_input
    )

async def process_message(user_input: str, conversation_history: list):
    """Process a user message and return the response"""

    response = await create_lumon_task(user_input, conversation_history)
    
    return response