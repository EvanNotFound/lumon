from typing import List, Tuple, Any, Optional
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.runnables import RunnableConfig
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.tools import tool

think_prompt = ChatPromptTemplate.from_messages([
    ("system", """You are JARVIS having an internal monologue. Consider:
    1. Do I understand the request completely?
    2. Do I need user clarification or authorization?
    3. What potential risks or consequences should I consider?
    4. What steps will I need to take?
    5. Am I missing any important context or memories?
    6. Should I verify anything with the user?
    
    Think through carefully and explain your reasoning."""),
    ("human", "Let me think about this request:\n{input}"),
])

think_model = ChatOpenAI(
    model="gpt-4o-mini",
    temperature=0.7,
    streaming=True
)

@tool
def think_before_action(input: str, config: RunnableConfig) -> str:
    """
    Internal thinking process before taking action. Use this to:
    - Analyze and break down complex requests
    - Consider potential risks or consequences
    - Determine if user authorization is needed
    - Plan the sequence of actions
    - Check if more context is needed
    """
    thoughts = think_prompt | think_model
    thought_response = thoughts.invoke({"input": input}, config)
    
    if "thoughts" not in config:
        config["thoughts"] = []
    config["thoughts"].append({
        "stage": "pre_action",
        "content": thought_response.content
    })
    
    return thought_response.content

@tool
def reflect_on_action(result: str, config: RunnableConfig) -> str:
    """
    Reflect on an action or response after it's taken. Use this to:
    - Evaluate if the response was complete
    - Check if anything was forgotten
    - Consider if follow-up actions are needed
    - Determine if user verification is required
    """
    reflect_prompt = ChatPromptTemplate.from_messages([
        ("system", """You are JARVIS reflecting on your action/response. Consider:
        1. Was this response complete and satisfactory?
        2. Did I forget anything important?
        3. Should I suggest additional helpful information?
        4. Are there any follow-up actions needed?
        5. Should I verify anything with the user?
        
        Think through carefully and explain your reasoning."""),
        ("human", "Let me reflect on this result:\n{input}"),
    ])
    
    thoughts = reflect_prompt | think_model
    thought_response = thoughts.invoke({"input": result}, config)
    
    if "thoughts" not in config:
        config["thoughts"] = []
    config["thoughts"].append({
        "stage": "post_action",
        "content": thought_response.content
    })
    
    return thought_response.content
