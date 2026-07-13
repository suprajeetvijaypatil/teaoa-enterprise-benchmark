import os

from dotenv import load_dotenv

load_dotenv()

MODEL_ID = os.getenv("MODEL_ID", "gpt-5.6-luna")

# Budget protection
MAX_MODEL_CALLS_PER_RUN = 3
MAX_OUTPUT_TOKENS = 400
MAX_RETRIES = 1
LOCAL_EXPERIMENT_BUDGET_USD = 8.00

# Current standard GPT-5.6 Luna pricing
INPUT_PRICE_PER_MILLION = 1.00
OUTPUT_PRICE_PER_MILLION = 6.00


def calculate_cost(input_tokens: int, output_tokens: int) -> float:
    """Estimate API cost for one model response."""
    input_cost = (
        input_tokens / 1_000_000
    ) * INPUT_PRICE_PER_MILLION

    output_cost = (
        output_tokens / 1_000_000
    ) * OUTPUT_PRICE_PER_MILLION

    return input_cost + output_cost