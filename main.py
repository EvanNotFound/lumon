# main.py
import sys
import click
import os

# Check for production mode from command line arguments
if "--prod" in sys.argv or "-p" in sys.argv:
    # Set environment variable for modules that might be imported before main() runs
    os.environ["LUMON_PROD_MODE"] = "true"

from rich.console import Console
from rich.panel import Panel
import traceback
from rich.markdown import Markdown
from mainframe_orchestra import set_verbosity
from utils.logger import set_production_mode
from chat.orchestra import load_prompt_sections, process_message
from chat.tools.memory_tools import MemoryTools
from chat.tools.task_tools import TaskTools

console = Console()

@click.command()
@click.option('--prod', '-p', is_flag=True, help='Run in production mode with enhanced UI')
def main(prod):
    # Set production mode in the logger if --prod flag is used
    if prod:
        set_production_mode(True)
        
    sections = load_prompt_sections()
    memory_context = MemoryTools.search_memories("relevant memories", limit=10)
    task_context = TaskTools.search_tasks("relevant tasks", limit=10)
    
    # Define the warning message separately to avoid deep nesting in format string
    tool_warning = """
⚠️ CRITICAL WARNING ⚠️: When you need to use an agent (web_research_agent, memory_management_agent, or task_management_agent), 
you must ALWAYS use the conduct_tool to delegate tasks. NEVER try to call these agents directly as tools themselves.

INCORRECT (DO NOT DO THIS):
{"tool_calls":[{"tool":"task_management_agent","params":{"task_id":"search_upcoming_tests","instruction":"List all upcoming tests"}}]}

CORRECT (ALWAYS DO THIS):
{"tool_calls":[{"tool":"conduct_tool","params":{"tasks":[{"task_id":"search_upcoming_tests","agent_id":"task_management_agent","instruction":"List all upcoming tests"}]}}]}

If you need to search the web, use the web_research_agent through the conduct_tool.
"""
    
    system_prompt = f"""
    {sections['base']}

    {sections['memory_guidelines']}

    Relevant Memories (These are only partial memories, you must search for more memories):
    {memory_context}

    {sections['task_guidelines']}

    Relevant Tasks (These are only partial information, you must search for more tasks):
    {task_context}
    
    {sections['response_guidelines']}

    {tool_warning}
    """
    
    conversation_history = []

    conversation_history.append({
        "role": "system",
        "content": system_prompt
    })

    if prod:
        console.print(Panel.fit(
            "[bold cyan]L.U.M.O.N.[/bold cyan] - Personal AI Assistant\n[dim]All systems are online and operational.[/dim]",
            border_style="cyan",
            padding=(1, 2)
        ))
    else:
        print("\n" + "="*50)
        print("Initializing L.U.M.O.N. - Personal AI Assistant")
        print("All systems are online and operational.")
        print("="*50 + "\n")
    
    try:
        while True:
            user_input = input("\nYou: ").strip()

            conversation_history.append({"role": "user", "content": user_input})
        
            try:
                if prod:
                    set_verbosity(0)
                response = process_message(user_input, conversation_history)

                conversation_history.append({"role": "assistant", "content": response})
                if prod:
                    console.print("\nL.U.M.O.N.:", style="cyan bold")
                    md = Markdown(response)
                    console.print(Panel.fit(
                        md,
                        border_style="cyan",
                        padding=(1, 2)
                    ))
                else:
                    print("\nL.U.M.O.N.:")
                    md = Markdown(response)
                    console.print(md)
                
            except Exception as e:
                if prod:
                    console.print("\n[red]Error occurred while processing your request:[/red]")
                    console.print(f"[red]Type: {type(e).__name__}[/red]")
                    console.print(f"[red]Details: {str(e)}[/red]")
                    console.print("\n[red]Traceback:[/red]")
                    console.print(traceback.format_exc(), style="red")
                else:
                    print("\nError occurred while processing your request:")
                    print(f"Type: {type(e).__name__}")
                    print(f"Details: {str(e)}")
                    print("\nTraceback:")
                    print(''.join(traceback.format_tb(e.__traceback__)))
                    
    except KeyboardInterrupt:
        if prod:
            console.print("\n\n[cyan]Goodbye! Have a great day![/cyan]")
        else:
            print("\n\nGoodbye! Have a great day!")
    except Exception as e:
        if prod:
            console.print("\n[red]A critical error occurred:[/red]")
            console.print(f"[red]Type: {type(e).__name__}[/red]")
            console.print(f"[red]Details: {str(e)}[/red]")
            console.print("\n[red]Traceback:[/red]")
            console.print(traceback.format_exc(), style="red")
        else:
            print("\nA critical error occurred:")
            print(f"Type: {type(e).__name__}")
            print(f"Details: {str(e)}")
            print("\nTraceback:")
            print(''.join(traceback.format_tb(e.__traceback__)))
        return 1
        
    return 0

if __name__ == "__main__":
    sys.exit(main())
