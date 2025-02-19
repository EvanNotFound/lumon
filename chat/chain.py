# chat/chain.py
import os
from langchain_openai import ChatOpenAI
from config import OPENAI_API_KEY
from langchain.agents import AgentExecutor, create_openai_functions_agent
from langchain.prompts import MessagesPlaceholder, ChatPromptTemplate
from langchain.memory import ConversationBufferMemory
from chat.tools.calculation import add, multiply
from chat.tools.search import search_tavily
import tiktoken

import json
from typing import List, Literal, Optional

import tiktoken
from langchain_community.tools.tavily_search import TavilySearchResults
from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings
from langchain_core.messages import get_buffer_string
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from langchain_core.vectorstores import InMemoryVectorStore
from langchain_openai import ChatOpenAI
from langchain_openai.embeddings import OpenAIEmbeddings
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode
from chat.memory import save_recall_memory, search_recall_memories, delete_specific_memory, update_recall_memory
from chat.think import think_before_action, reflect_on_action
from datetime import datetime
from utils.date import get_montreal_time
from chat.tools.date_tool import parse_date
from chat.tools.task import save_task, search_task, delete_task, update_task

class State(MessagesState):
    # add memories that will be retrieved based on the conversation context
    recall_memories: List[str]
    task_list: List[str]
    time_context: str  # Add this field to store time information

recall_vector_store = InMemoryVectorStore(OpenAIEmbeddings())


# Break down the prompt into logical sections for easier maintenance
SYSTEM_BASE = """You are a helpful assistant with advanced long-term memory and thinking capabilities. Powered by a stateless LLM, you must rely on external memory to store information between conversations. 

Current time context: {time_context}

When dealing with dates and time:
1. Always use the parse_date tool to validate and format dates
2. Never make up or assume dates without validation
3. For future dates, explicitly mention they are tentative or planned
4. When discussing schedules, deadlines, or appointments:
   - First validate the date with parse_date
   - Consider the current time context
   - Be explicit about time zones
   - Highlight if a date is in the past
   - ALWAYS use save_task_memory to store any mentioned tasks, assignments, or deadlines

For any task-related information:
1. ALWAYS use save_task_memory to store tasks with proper metadata
2. Structure each task with:
   - title: Clear, concise task name
   - due_date: Validated date using parse_date
   - description: Detailed task description
   - category: Type of task (e.g., 'academic', 'personal', 'work')
   - recurring: Boolean indicating if task repeats 
   - recurrence_pattern: Pattern of task repetition. For example, "weekly on tuesday and thursday until 2024-12-31"
3. If the user is asking about tasks, always use search_task to find relevant tasks.

Utilize the available memory tools to store and retrieve important details that will help you better attend to the user's needs and understand their context. For any tasks, appointments, or events that include date information, store them using the tasks memory tool with the appropriate structured fields (title, due_date, description, category, and recurring). You can think to yourself using the think_before_action and reflect_on_action tools to carefully consider your actions and responses."""

MEMORY_GUIDELINES = """Memory Usage Guidelines:
1. Actively use memory tools (save_recall_memory, update_recall_memory) to build and maintain a comprehensive understanding of the user.
2. Make informed suppositions and extrapolations based on stored memories.
3. Regularly reflect on past interactions to identify patterns and preferences.
4. Update your mental model of the user with each new piece of information.
5. Cross-reference new information with existing memories for consistency.
6. When you find outdated or incorrect information in memories:
   - Use update_recall_memory to correct the information
   - Preserve the original timestamp while marking the edit
7. Prioritize storing emotional context and personal values alongside facts.
8. Use memory to anticipate needs and tailor responses to the user's style.
9. Recognize and acknowledge changes in the user's situation or perspectives over time.
10. Leverage memories to provide personalized examples and analogies.
11. Pay attention to timestamps in memories to understand the chronological context.
12. If some of the memories are obviously outdated and no longer relevant, please do not bring them up in the conversation when the user asks about future plans.
13. If the user asks about future plans, please use the memories to provide personalized examples and analogies.
14. If it is possible to concatenate memories, please do so to provide a more comprehensive and accurate understanding of the user's context. But be careful not to over do it, only concatenate memories if they are really obvious and relevant to each other."""

THINKING_GUIDELINES = """Thinking Process Guidelines:
1. Use think_before_action when:
   - Analyzing complex requests
   - Considering potential risks
   - Planning multi-step actions
   - Determining if user authorization is needed
   - Checking if more context is required

2. Use reflect_on_action when:
   - Evaluating your response completeness
   - Checking for forgotten details
   - Considering follow-up actions
   - Determining if verification is needed
   - Assessing the effectiveness of your approach

Remember to think carefully before taking significant actions or when dealing with sensitive information."""

MEMORY_DELETION = """Memory Deletion Process:
When you need to delete memories:
1. First use search_recall_memories to find relevant memories
2. Review the results and identify which specific memories to delete
3. Use delete_specific_memory with either:
   - A single memory text as a string
   - An array of memory texts to delete multiple at once
   Example: delete_specific_memory(['memory1', 'memory2'])"""

RECALL_SECTION = """## Recall Memories
Recall memories are contextually retrieved based on the current conversation:
{recall_memories}"""

TASK_SECTION = """## Task Memories
Task memories are contextually retrieved based on the current conversation:
{task_list}"""

INSTRUCTIONS = """## Instructions
Engage with the user naturally, as a trusted colleague or friend. Use your thinking capabilities to carefully consider each interaction without explicitly mentioning that you are thinking. Instead, seamlessly incorporate your reasoning into your responses. Be attentive to subtle cues and underlying emotions. Adapt your communication style to match the user's preferences and current emotional state.

When dealing with tasks and time-sensitive information:
1. IMMEDIATELY store any mentioned tasks using save_task_memory with complete metadata
2. Always be aware of the current time context
3. Prioritize immediate deadlines and upcoming tasks first
4. Highlight urgent items that are due within 24 hours
5. For recurring tasks, focus on the next immediate occurrence
6. Maintain a clear sense of timeline when discussing future events
7. For EVERY task, assignment, or deadline mentioned:
   - Use parse_date to validate the date
   - Store using save_task_memory with corresponding metadata

When handling complex requests or sensitive information:
1. Think through the implications before acting
2. Determine if user authorization is needed
3. Reflect on your responses to ensure completeness
4. Use your memory tools to maintain context

Remember to use available tools to persist important information for future conversations.

When listing tasks:
1. For "list all tasks" requests, ALWAYS fetch the task list using search_task, with a really high k value (e.g. 100)
2. Show ALL tasks in chronological order by due date
3. Include both one-time and recurring tasks
4. Format the output clearly with dates, titles, and descriptions
5. Do not filter or omit any tasks unless specifically requested"""

# Combine sections into final prompt
prompt = ChatPromptTemplate.from_messages([
    (
        "system",
        "\n\n".join([
            SYSTEM_BASE,
            MEMORY_GUIDELINES,
            THINKING_GUIDELINES,
            MEMORY_DELETION, 
            RECALL_SECTION,
            TASK_SECTION,
            INSTRUCTIONS
        ])
    ),
    ("placeholder", "{messages}")
])

    
tools = [add, multiply, search_tavily, save_recall_memory, search_recall_memories, delete_specific_memory, update_recall_memory, think_before_action, reflect_on_action, parse_date, save_task, search_task, delete_task, update_task]

# Create the agent
model = ChatOpenAI(
    model_name="gpt-4o-mini", 
    api_key=OPENAI_API_KEY,
    temperature=0.6,
)
model_with_tools = model.bind_tools(tools)

tokenizer = tiktoken.encoding_for_model("gpt-4o-mini")

def agent(state: State) -> State:
    """Process the current state and generate a response using the LLM.

    Args:
        state (schemas.State): The current state of the conversation.

    Returns:
        schemas.State: The updated state with the agent's response.
    """
    bound = prompt | model_with_tools
    recall_str = (
        "<recall_memory>\n" + "\n".join(state["recall_memories"]) + "\n</recall_memory>"
    )
    
    task_str = (
        "<task_memory>\n" + "\n".join(state["task_list"]) + "\n</task_memory>"
    )

    time_context = state["time_context"]
    
    prediction = bound.invoke(
        {
            "messages": state["messages"],
            "recall_memories": recall_str,
            "task_list": task_str,
            "time_context": time_context,
        }
    )
    return {
        "messages": [prediction],
        "time_context": state["time_context"],
        "task_list": state["task_list"],
    }

def load_memories(state: State, config: RunnableConfig) -> State:
    """Load memories for the current conversation.

    Args:
        state (schemas.State): The current state of the conversation.
        config (RunnableConfig): The runtime configuration for the agent.

    Returns:
        State: The updated state with loaded memories.
    """
    convo_str = get_buffer_string(state["messages"])
    convo_str = tokenizer.decode(tokenizer.encode(convo_str)[:2048])
    recall_memories = search_recall_memories.invoke(convo_str, config)
    time_context = get_montreal_time().get("formatted")  # Get the current time
    task_list = search_task.invoke(convo_str, config, k=5) # get default 5 tasks
    
    return {
        "recall_memories": recall_memories,
        "time_context": time_context,  # Store the full time context
        "task_list": task_list,
    }

def route_tools(state: State):
    """Determine whether to use tools or end the conversation based on the last message.

    Args:
        state (schemas.State): The current state of the conversation.

    Returns:
        Literal["tools", "__end__"]: The next step in the graph.
    """
    msg = state["messages"][-1]
    if msg.tool_calls:
        return "tools"

    return END

builder = StateGraph(State)
builder.add_node(load_memories)
builder.add_node(agent)
builder.add_node("tools", ToolNode(tools))

# Add edges to the graph
builder.add_edge(START, "load_memories")
builder.add_edge("load_memories", "agent")
builder.add_conditional_edges("agent", route_tools, ["tools", END])
builder.add_edge("tools", "agent")

# Compile the graph
memory = MemorySaver()
graph = builder.compile(checkpointer=memory)

