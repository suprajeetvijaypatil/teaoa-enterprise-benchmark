import os

from dotenv import load_dotenv
from openai import OpenAI


def main() -> None:
    load_dotenv()

    api_key = os.getenv("OPENAI_API_KEY")
    model_id = os.getenv("MODEL_ID")

    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is missing from the .env file.")

    if not model_id:
        raise RuntimeError("MODEL_ID is missing from the .env file.")

    client = OpenAI(api_key=api_key)

    response = client.responses.create(
        model=model_id,
        input="Reply with exactly: CONNECTION SUCCESSFUL",
    )

    print(response.output_text)


if __name__ == "__main__":
    main()