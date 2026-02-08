"""Pre-filter posts using Haiku to quickly identify non-events before full analysis."""

from anthropic import Anthropic

from .models import RssPost

# Haiku pricing per million tokens
HAIKU_INPUT_COST_PER_M = 0.80
HAIKU_OUTPUT_COST_PER_M = 4.00
HAIKU_MODEL = "claude-3-5-haiku-latest"

PREFILTER_PROMPT = """You are a binary classifier. Given an RSS post from a cycling community Instagram account, determine if the post could plausibly be announcing an event (a ride, meetup, race, social gathering, etc. with a date/time).

Answer with exactly one word: YES or NO.

- YES means the post could be announcing an event and needs further analysis.
- NO means the post is clearly not an event announcement (e.g., a motivational quote, a photo recap, a meme, a personal reflection, general community chatter).

When in doubt, answer YES."""


class PrefilterResult:
    """Result from the Haiku pre-filter."""

    def __init__(self, is_likely_event: bool, input_tokens: int, output_tokens: int):
        self.is_likely_event = is_likely_event
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens

    @property
    def cost_usd(self) -> float:
        return (
            self.input_tokens * HAIKU_INPUT_COST_PER_M / 1_000_000
            + self.output_tokens * HAIKU_OUTPUT_COST_PER_M / 1_000_000
        )


def prefilter_post(post: RssPost) -> PrefilterResult:
    """Run a cheap Haiku check to see if a post is plausibly an event.

    Returns a PrefilterResult. If is_likely_event is False, the post can be
    short-circuited to "ignore" without running the full Sonnet analysis.
    """
    client = Anthropic()

    user_text = f"""Post title: {post.title}
Post author: {post.author or 'Unknown'}

Post content:
{post.content}"""

    response = client.messages.create(
        model=HAIKU_MODEL,
        max_tokens=8,
        system=PREFILTER_PROMPT,
        messages=[{"role": "user", "content": user_text}],
    )

    answer = response.content[0].text.strip().upper()
    is_likely_event = answer != "NO"

    return PrefilterResult(
        is_likely_event=is_likely_event,
        input_tokens=response.usage.input_tokens,
        output_tokens=response.usage.output_tokens,
    )
