from mainframe_orchestra import Agent, OpenaiModels
from chat.tools.task_tools import TaskTools

TaskTools()

task_management_agent = Agent(
    agent_id="task_management_agent",
    role="Task Management Agent",
    goal="Use your tools to manage tasks, try to be context-aware and date-aware.",
    attributes="time-aware, context-aware, can assist with task tasks. Currently, you can save, delete, and update tasks.",
    temperature=0.4,
    llm=OpenaiModels.gpt_4o_mini,
    tools=[TaskTools.save_task, TaskTools.search_tasks, TaskTools.delete_task, TaskTools.update_task]
)