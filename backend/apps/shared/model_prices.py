"""The models one of bleqq's agents may run on, with their list prices, and the efforts a
model call may ask for (D-148). Kept apart from the model adapter, which only the logged
wrapper (`apps.shared.ai`) may import."""

from __future__ import annotations

# The models one of bleqq's agents may be set to run on in the console, with each one's list
# price in minor units per million tokens, input then output (Verification_Log, D-148). A
# list in code, never a variable: a new model is a reviewed change with its price.
AGENT_MODELS: dict[str, tuple[int, int]] = {
    "claude-opus-5-5": (400, 2000),
    "claude-sonnet-5-5": (200, 1000),
    "claude-haiku-5-5": (10, 50),
}
# How hard a model thinks: `output_config.effort`.
EFFORTS = ("low", "medium", "high", "xhigh", "max")
