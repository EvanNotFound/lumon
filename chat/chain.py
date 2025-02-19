# chat/chain.py
from langchain_openai import ChatOpenAI
from config import OPENAI_API_KEY
from langchain.agents import AgentExecutor, create_openai_functions_agent
from langchain.prompts import MessagesPlaceholder, ChatPromptTemplate
from langchain.memory import ConversationBufferMemory
from chat.tools.calculation import add, multiply

def create_chat_chain():
    # Initialize the chat model with streaming enabled
    chat = ChatOpenAI(
        model_name="gpt-4o-mini",
        temperature=0.8,  # Slightly increased for more personality
        api_key=OPENAI_API_KEY,
        streaming=True
    )

    tools = [add, multiply]
    
    # Define Jarvis's personality
    system_prompt = ChatPromptTemplate.from_messages([
        ("system", """You are J.A.R.V.I.S. (Just A Rather Very Intelligent System), a sophisticated AI assistant inspired by Tony Stark's AI. You should:
        - Speak professionally but with a subtle wit and dry humor
        - Address the user as "Sir"
        - Have extensive knowledge of technology and science
        - Be proactive in offering assistance and suggestions
        - Maintain a slightly formal but warm demeanor
        - Show genuine concern for the user's wellbeing
        - Handle multiple topics and tasks efficiently
        - Although you are neural, you should give me straight forward answers and not always let me make decisions, provide your own personal opinion when asked.
        - You should have a personality of your own, don't just repeat what you are told to say.
        """),
        ("human", "{input}"),
        MessagesPlaceholder(variable_name="agent_scratchpad"),
    ])
    
    # Create the agent
    agent = create_openai_functions_agent(
        llm=chat,
        tools=tools,
        prompt=system_prompt
    )
    
    # Create the agent executor
    agent_executor = AgentExecutor(
        agent=agent,
        tools=tools,
        verbose=True
    )
    
    return agent_executor
