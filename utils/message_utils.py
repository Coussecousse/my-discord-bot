import re
from discord import Message
import discord

async def send_split_message(self, response: str, message: Message, has_followed_up=False):
    char_limit = 1900
    # Helper to check if message is an interaction (has followup)
    is_interaction = hasattr(message, 'followup')
    async def safe_send(content):
        nonlocal has_followed_up
        if self.is_replying_all == "True" or has_followed_up or not is_interaction:
            await message.channel.send(content)
        else:
            try:
                await message.followup.send(content)
            except discord.errors.NotFound:
                await message.channel.send(content)
            has_followed_up = True

    if len(response) > char_limit:
        is_code_block = False
        parts = response.split("```")

        for i in range(len(parts)):
            if is_code_block:
                code_block_chunks = [parts[i][j:j+char_limit] for j in range(0, len(parts[i]), char_limit)]
                for chunk in code_block_chunks:
                    await safe_send(f"```{chunk}```")
                is_code_block = False
            else:
                non_code_chunks = [parts[i][j:j+char_limit] for j in range(0, len(parts[i]), char_limit)]
                for chunk in non_code_chunks:
                    await safe_send(chunk)
                is_code_block = True
    else:
        await safe_send(response)

    return has_followed_up


async def send_response_with_images(self, response: dict, message: Message):
    response_content = response.get("content")
    response_images = response.get("images")

    split_message_text = re.split(r'\[Image of.*?\]', response_content)

    for i in range(len(split_message_text)):
        if split_message_text[i].strip():
            await send_split_message(self, split_message_text[i].strip(), message, has_followed_up=True)

        if response_images and i < len(response_images):
            await send_split_message(self, response_images[i].strip(), message, has_followed_up=True)
