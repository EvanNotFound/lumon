import sys
import click
from rich.console import Console
from rich.panel import Panel
from rich.markdown import Markdown

console = Console()

def pretty_print_stream_chunk(chunk, production=False):
    """Print stream chunks with either debug or production formatting.
    
    Args:
        chunk: The chunk data to print
        production: If True, uses production formatting, otherwise debug
    """
    if production:
        for node, updates in chunk.items():
            if "messages" in updates:
                message = updates["messages"][-1]
                if hasattr(message, 'content') and message.content.strip():  # Only print if content exists and isn't empty
                    # Format AI responses in a nice panel
                    md = Markdown(message.content)
                    console.print(Panel(
                        md,
                        title="J.A.R.V.I.S.",
                        border_style="cyan",
                        padding=(1, 2)
                    ))
    else:
        # Debug formatting - original implementation
        for node, updates in chunk.items():
            print(f"Update from node: {node}")
            if "messages" in updates:
                updates["messages"][-1].pretty_print()
            else:
                print(updates)
            print("\n")
