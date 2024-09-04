import argparse
import textwrap
import sys
from .get_screen import get_screen_context

from openai import OpenAI
client = OpenAI()


def chat(message, interactive=True):
    system_content = textwrap.dedent("""
        You are a shell assistant that analyzes shell screen context and provides help.
        Keep your response concise.
        If the most recent commands failed, provide a one-line summary of the error message if the error is not obvious. And then provide a fix or debugging hints.
        If there is no error and you are not sure what to do, wait for the next prompt.
        Note: the lastest command in the context is the command that triggered this conversation. Ignore it.
    """).strip()

    messages=[
        {"role": "system", "content": system_content},
        {"role": "user", "content": message},
    ]
    while True:
        completion = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages
        )
        assistant_response = completion.choices[0].message.content
        print(assistant_response)
        if not interactive:
            break
        messages.append({"role": "assistant", "content": assistant_response})
        try:
            next_prompt = input("> ")
            messages.append({"role": "user", "content": next_prompt})
        except (EOFError, KeyboardInterrupt):
            print("\nExiting chat...")
            break


def main():
    """
    Look at shell context and provide a fix
    """
    parser = argparse.ArgumentParser(description="Analyze AIShell screen context and provide help")
    parser.add_argument("--lines", type=int, default=20,
                        help="Last N lines to feed to the AI. Default: 20. Set <=0 to disable.\n"
                        "Aishell only has context up till the most recent ctrl+L (clear screen).")
    parser.add_argument("--interactive", "-i", action="store_true", help="Interactive mode. Default: False.")
    args = parser.parse_args()


    try:
        context = get_screen_context(args.lines)
        chat(f'command to that triggered this conversation: {" ".join(sys.argv)} Shell context:\n{context}', args.interactive)
    except Exception as e:
        print(f"Error: {e}")

def quick_help():
    """
    quick helper to answer a shell related question

    Usage: aishell-quick-help [<question>]

    Limitation:
    shell might complain if you have quotes or double quotes in your question.
    You can avoid this by running this command without a <question> argument to start a session.
    """
    message = " ".join(sys.argv[1:])
    if not message:
        message = input("Enter your message: ")
    chat(message, interactive=False)

if __name__ == "__main__":
    main()