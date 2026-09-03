"""What every Greenhouse module agrees on.

Held apart so the validator, the normalizer, the provider, and the client can
all import it without importing each other.
"""

SOURCE_KEY = "greenhouse"
DISPLAY_NAME = "Greenhouse"
DEFAULT_BASE_URL = "https://boards-api.greenhouse.io/v1/boards"

# Above the aggregator. An employer's own board is the better account of its own
# posting, which is what source precedence exists to express.
PRECEDENCE = 20

# Boards are listed rather than discovered. A guessed board name that resolves
# to a different company would ingest its postings under the wrong employer, so
# adding one is a deliberate act. Discovery finds and verifies candidates; a
# deployment decides which of them to read, through configuration.
DEFAULT_BOARDS = (
    "anthropic",
    "datadog",
    "hudl",
)
