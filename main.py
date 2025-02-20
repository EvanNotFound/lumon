# main.py
import sys
from langchain.schema import HumanMessage, SystemMessage
from chat.chain import pretty_print_stream_chunk, graph

def main():
    print("\n" + "="*50)
    print("Initializing J.A.R.V.I.S. - Personal AI Assistant")
    print("All systems are online and operational.")
    print("="*50 + "\n")
    
    try:
        
        while True:
            user_input = input("\nYou: ").strip()
            
            if user_input.lower() in ["exit", "quit", "bye", "goodbye"]:
                print("\nJ.A.R.V.I.S.: Goodbye, Sir!")
                break
                
            if not user_input:
                print("Please say something!")
                continue
                
            try:
                # NOTE: we're specifying `user_id` to save memories for a given user
                config = {"configurable": {"user_id": "1", "thread_id": "1"}}

                for chunk in graph.stream({"messages": [("user", user_input)]}, config=config):
                    pretty_print_stream_chunk(chunk)
                # print(f"\nJ.A.R.V.I.S.: {response['output']}")
                
            except Exception as e:
                import traceback
                print("\nError occurred while processing your request:")
                print(f"Type: {type(e).__name__}")
                print(f"Details: {str(e)}")
                print("\nTraceback:")
                print(''.join(traceback.format_tb(e.__traceback__)))
                print("If this issue persists, please contact support.")
                
    except KeyboardInterrupt:
        print("\n\nGoodbye! Have a great day!")
    except Exception as e:
        print("\nA critical error occurred:")
        print(f"Type: {type(e).__name__}")
        print(f"Details: {str(e)}")
        print("\nTraceback:")
        print(''.join(traceback.format_tb(e.__traceback__)))
        return 1
        
    return 0

if __name__ == "__main__":
    sys.exit(main())
