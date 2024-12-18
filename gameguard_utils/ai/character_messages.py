from enum import Enum
import discord
from typing import Optional, List
from datetime import datetime, timedelta
from gameguard_utils import get_specific_files


MAX_MESSAGES = 30
MAX_USER_MESSAGES = 20
MAX_ASSISTANT_MESSAGES = 10


class CharacterRole(Enum):
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


class PollStatus(Enum):
    NO_VOTE = 0
    NEW_VOTE = 1
    CHANGE_VOTE = 2


class CharacterMessages:
    def __init__(self):
        self.messages: List[Message] = []

        self.poll_members_busy: dict[int, datetime] = {}
        self.busy: bool = False

    def add_message(
        self,
        input_message: discord.Message,
        content: str,
        role: CharacterRole,
        interacts: Optional[bool] = False,
        ignore_filter: Optional[bool] = False,
    ):
        author = input_message.author
        message = Message(
            author=f"{author.display_name}, {author.id}",
            role=role,
            content=content,
            reference_message=input_message,
            interacts=interacts,
            ignore_filter=ignore_filter,
        )
        self.messages.append(message)

        if len(self.messages) > MAX_MESSAGES:
            self.messages.pop(0)

    def add_manually_message(
        self, author: str, content: str, role: CharacterRole, ignore_filter: Optional[bool] = True
    ):
        message = Message(author=author, role=role, content=content, ignore_filter=ignore_filter)
        self.messages.append(message)

    def add_tool_message(self, tool_name: str, content: str):
        message = Message(author=tool_name, role=CharacterRole.TOOL, content=content, ignore_filter=True)
        self.messages.append(message)

    def delete_last_user_messages(self):
        for message in reversed(self.messages):
            if message.role == CharacterRole.USER:
                self.messages.remove(message)
            else:
                return

    def is_character_mentioned(self, input_message: discord.Message) -> bool:
        if not input_message.reference:
            return False

        return any(
            message.role == CharacterRole.ASSISTANT
            and message.reference_message.id == input_message.reference.message_id
            for message in reversed(self.messages)
        )

    def is_last_user_message(
        self, input_message: Optional[discord.Message] = None, member: Optional[discord.Member] = None
    ) -> bool:
        if not input_message and not member:
            return False

        assistant_interacted = False
        user_interacted = False
        for message in reversed(self.messages):
            if not message.reference_message:
                continue

            if message.role == CharacterRole.ASSISTANT:
                if (
                    (input_message.created_at if input_message else discord.utils.utcnow())
                    - message.reference_message.created_at
                ).total_seconds() <= 300:
                    assistant_interacted = True
                else:
                    return False

            if (
                message.reference_message.author.id == input_message.author.id
                if input_message
                else member.id and message.interacts
            ):
                user_interacted = True

            if assistant_interacted and user_interacted:
                return True

        return False

    def get_message(self, message: discord.Message) -> Optional["Message"]:
        return next((i for i in self.messages if i.reference_message and i.reference_message.id == message.id), None)

    def get_messages(
        self,
        system_message: Optional[str] = None,
        user_messages: Optional[int] = MAX_USER_MESSAGES,
        assistant_messages: Optional[int] = MAX_ASSISTANT_MESSAGES,
        image_vision_limit: Optional[int] = None,
        nsfw_allowed: Optional[bool] = False,
    ) -> tuple[List[dict], bool]:
        result = []
        user_count = 0
        assistant_count = 0
        tool_count = 0

        vision = False
        for message in reversed(self.messages):
            if message.role == CharacterRole.USER and user_count >= user_messages:
                continue
            if message.role == CharacterRole.ASSISTANT and assistant_count >= assistant_messages:
                continue
            if message.role == CharacterRole.TOOL and user_count + assistant_count + tool_count >= 5:
                continue

            message_content = (f"[{message.author}]: " if message.role == CharacterRole.USER else "") + (
                message.content if message.content else ""
            )
            if (
                image_vision_limit is not None
                and assistant_count <= image_vision_limit
                and message.reference_message
                and get_specific_files(
                    message.reference_message.attachments,
                    extensions=["png", "jpg", "jpeg", "webp", "gif"],
                    max_files=None,
                )
                and not nsfw_allowed
            ):
                result.insert(
                    0,
                    {
                        "role": message.role.value,
                        "content": [
                            {"type": "text", "text": message_content},
                            {
                                "type": "image_url",
                                "image_url": {"url": message.reference_message.attachments[0].url, "detail": "low"},
                            },
                        ],
                    },
                )
                vision = True
                break
            elif message.content:
                if message.role == CharacterRole.TOOL:
                    result.insert(
                        0,
                        {"role": "user", "content": message_content},
                    )
                else:
                    result.insert(0, {"role": message.role.value, "content": message_content})

                if message.role == CharacterRole.USER:
                    user_count += 1
                elif message.role == CharacterRole.ASSISTANT:
                    assistant_count += 1
                elif message.role == CharacterRole.TOOL:
                    tool_count += 1

        if system_message:
            result.insert(0, {"role": "system", "content": system_message})
        return result, vision

    def filter_messages(self, author: discord.Member, system_message: Optional[str] = None) -> List[dict]:
        result = [{"role": "system", "content": system_message}] if system_message else []
        for message in self.messages:
            if (
                message.ignore_filter
                or message.role == CharacterRole.USER
                and message.reference_message
                and message.reference_message.author.id != author.id
            ):
                continue

            if message.role == CharacterRole.USER:
                result.append({"role": str(message.role.value), "content": message.content})
            elif message.role == CharacterRole.ASSISTANT:
                result.append({"role": str(message.role.value), "content": f"[Assistant]: {message.content}"})

        return result

    def update_content(self, input_message: discord.Message, content: str):
        for message in self.messages:
            if message.reference_message and message.reference_message.id == input_message.id:
                message.update_content(content)
                return

    async def reject_request(self, message: discord.Message):
        self.delete_last_user_messages()
        self.busy = False
        embed = discord.Embed(
            title="Antwort nicht möglich",
            description="Die von dir eingegebene Nachricht verstößt möglicherweise gegen unsere Nutzungsbedingugen.",
            colour=discord.Color.orange(),
        )
        await message.edit(content=None, embed=embed)

    def on_poll_vote_add(self, member: discord.Member, answer: discord.PollAnswer) -> PollStatus:
        message = self.get_message(answer.poll.message)
        if not message or not message.poll:
            return PollStatus.NO_VOTE

        return message.poll.add_vote(member, answer)

    def on_poll_vote_remove(self, member: discord.Member, answer: discord.PollAnswer) -> PollStatus:
        message = self.get_message(answer.poll.message)
        if not message or not message.poll:
            return PollStatus.NO_VOTE

        return message.poll.remove_vote(member, answer)

    def member_filled_poll(self, member: discord.Member) -> bool:
        now = discord.utils.utcnow()
        self.poll_members_busy = {
            mid: timestamp
            for mid, timestamp in self.poll_members_busy.items()
            if now - timestamp <= timedelta(seconds=1)
        }

        if member.id in self.poll_members_busy and now - self.poll_members_busy[member.id] <= timedelta(seconds=1):
            return True

        self.poll_members_busy[member.id] = now
        return False


class Message:
    def __init__(
        self,
        author: str,
        role: CharacterRole,
        content: Optional[str] = None,
        reference_message: Optional[discord.Message] = None,
        interacts: Optional[bool] = False,
        ignore_filter: Optional[bool] = False,
    ):
        self.author: str = author
        self.role: CharacterRole = role

        self._content: str = content
        self.reference_message: Optional[discord.Message] = reference_message

        self.interacts: Optional[bool] = interacts
        self.ignore_filter: Optional[bool] = ignore_filter

        self.poll: Optional[AIPoll] = (
            AIPoll(reference_message.poll) if reference_message and reference_message.poll else None
        )

    def update_content(self, content: str):
        self._content = content

    @property
    def content(self) -> str:
        if self.poll:
            return f"{self._content} {self.poll.content}"

        return self._content


class AIPoll:
    def __init__(self, poll: discord.Poll):
        self.answers: dict[int, AIPollAnswer] = {i.id: AIPollAnswer(i.text) for i in poll.answers}

    def add_vote(self, member: discord.Member, answer: discord.PollAnswer) -> PollStatus:
        answer = self.answers.get(answer.id)
        if answer:
            return answer.add_vote(member)

        return PollStatus.NO_VOTE

    def remove_vote(self, member: discord.Member, answer: discord.PollAnswer) -> PollStatus:
        answer = self.answers.get(answer.id)
        if answer:
            return answer.remove_vote(member)

        return PollStatus.NO_VOTE

    @property
    def content(self) -> str:
        result = "Die aktuellen Ergebnisse, hinter jeder Antwort die abgestimmten User: "
        for answer in list(self.answers.values()):
            result += f"== {answer.text}: {answer.voters} =="
        return result


class AIPollAnswer:
    def __init__(self, text: str):
        self.text: str = text

        self.removed_members: List[int] = []
        self.members: dict[int, discord.Member] = {}

    def add_vote(self, member: discord.Member) -> PollStatus:
        if member.id not in self.members:
            self.members[member.id] = member
            return PollStatus.CHANGE_VOTE if member.id in self.removed_members else PollStatus.NEW_VOTE

        return PollStatus.NO_VOTE

    def remove_vote(self, member: discord.Member) -> PollStatus:
        if member.id in self.members:
            del self.members[member.id]
            self.removed_members.append(member.id)
            return PollStatus.CHANGE_VOTE

        return PollStatus.NO_VOTE

    @property
    def voters(self) -> str:
        result = ""
        for member in list(self.members.values()):
            result += f"[{member.display_name}, {member.id}] "
        return result
