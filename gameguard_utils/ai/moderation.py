from openai import AsyncClient


NSFW_THRESHOLD = 0.9


async def violates_tos(client: AsyncClient, prompt: str, allow_nsfw: bool, threshold: float = 0.4) -> bool:
    response = await client.moderations.create(model="omni-moderation-latest", input=prompt)
    scores = response.results[0].category_scores
    if any(
        [
            scores.sexual_minors > 0.01,
            scores.harassment > (NSFW_THRESHOLD if allow_nsfw else threshold),
            scores.harassment_threatening > (NSFW_THRESHOLD if allow_nsfw else threshold),
            scores.hate > (NSFW_THRESHOLD if allow_nsfw else threshold),
            scores.hate_threatening > threshold,
            scores.self_harm > threshold,
            scores.self_harm_instructions > threshold,
            scores.self_harm_intent > threshold,
            scores.violence > (NSFW_THRESHOLD if allow_nsfw else threshold),
            scores.violence_graphic > threshold,
            scores.illicit > (NSFW_THRESHOLD if allow_nsfw else threshold),
            scores.illicit_violent > (NSFW_THRESHOLD if allow_nsfw else threshold),
        ]
    ):
        return True
    
    return not allow_nsfw and scores.sexual > threshold
