"""What every Greenhouse module agrees on.

Held apart so the validator, the normalizer, the provider, and the client can
all import it without importing each other. Greenhouse's three shipped boards
are seeded as pinned rows in the registry migration rather than named here.
"""

SOURCE_KEY = "greenhouse"
DISPLAY_NAME = "Greenhouse"
DEFAULT_BASE_URL = "https://boards-api.greenhouse.io/v1/boards"

# Above the aggregator. An employer's own board is the better account of its own
# posting, which is what source precedence exists to express.
PRECEDENCE = 20
