#!/usr/bin/env python3

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.chat.interface import AzureChatInterface


def main():
    api_key = os.environ.get("FHIR_CHAT_OPENAI_API_KEY")
    if not api_key:
        print("Error: FHIR_CHAT_OPENAI_API_KEY environment variable not set")
        print("Please set it with: export FHIR_CHAT_OPENAI_API_KEY='your-api-key'")
        sys.exit(1)

    api_endpoint = os.environ.get("FHIR_CHAT_OPENAI_ENDPOINT")
    if not api_endpoint:
        print("Error: FHIR_CHAT_OPENAI_ENDPOINT environment variable not set")
        print("Please set it with: export FHIR_CHAT_OPENAI_ENDPOINT='your-api-endpoint'")
        sys.exit(1)

    chat = AzureChatInterface(
        api_key=api_key,
        azure_endpoint=api_endpoint,
        deployment_name="gpt-5-mini",
        model="gpt-5-mini",
        temperature=1.0 # temp isn't supported with gpt-5-mini
    )

    chat.start_with_system_message("You are a helpful assistant.")

    print("Chat Interface Demo")
    print("=" * 50)
    print("Type 'quit' or 'exit' to end the conversation\n")

    while True:
        try:
            user_input = input("You: ").strip()

            if user_input.lower() in ["quit", "exit", "q"]:
                print("Goodbye!")
                break

            if not user_input:
                continue

            print("\nAssistant: ", end="", flush=True)
            response = chat.send_message(user_input)
            print(response)
            print()

        except KeyboardInterrupt:
            print("\n\nGoodbye!")
            break
        except Exception as e:
            print(f"\nError: {e}")
            break


if __name__ == "__main__":
    main()
