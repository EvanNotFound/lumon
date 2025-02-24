# main.py
import sys
import click
from langchain_core.messages import HumanMessage, SystemMessage
from chat.chain import graph
from utils.pretty_print import pretty_print_stream_chunk
from rich.console import Console
from rich.panel import Panel
from chat.deprecated.memory import search_recall_memories
from chat.orchestra import process_message
from datetime import datetime
import traceback

console = Console()

@click.command()
@click.option('--prod', '-p', is_flag=True, help='Run in production mode with enhanced UI')
def main(prod):
    conversation_history = []

    if prod:
        console.print(Panel.fit(
            "[bold cyan]J.A.R.V.I.S.[/bold cyan] - Personal AI Assistant\n[dim]All systems are online and operational.[/dim]",
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
                response = process_message(user_input, conversation_history)

                conversation_history.append({"role": "assistant", "content": response})
                print("\nL.U.M.O.N.:", response)
                
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
