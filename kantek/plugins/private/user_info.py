"""Plugin to get information about a user."""
import logging
from typing import Union

from telethon import events
from telethon.events import NewMessage
from telethon.tl.custom import Forward, Message
from telethon.tl.functions.channels import GetParticipantRequest
from telethon.tl.types import (Channel, ChannelParticipantAdmin,
                               ChannelParticipantSelf, MessageEntityMention,
                               MessageEntityMentionName, User)

from config import cmd_prefix
from database.mysql import MySQLDB
from utils import constants, helpers, parsers
from utils.client import KantekClient
from utils.mdtex import (Bold, Code, Italic, KeyValueItem, Link, MDTeXDocument,
                         Section, SubSection)

__version__ = '0.1.2'

tlog = logging.getLogger('kantek-channel-log')


@events.register(events.NewMessage(outgoing=True, pattern=f'{cmd_prefix}u(ser)?'))
async def user_info(event: NewMessage.Event) -> None:
    """Show information about a user.

    Args:
        event: The event of the command

    Returns: None

    """
    chat: Channel = await event.get_chat()
    client: KantekClient = event.client
    msg: Message = event.message
    # crude hack until I have a proper way to have commands with short options
    # without this ungban will always trigger user too
    if 'ungban' in msg.text:
        return
    _args = msg.raw_text.split()[1:]
    keyword_args, args = parsers.parse_arguments(' '.join(_args))
    response = ''
    if not args and msg.is_reply:
        response = await _info_from_reply(event, **keyword_args)
    elif args or 'search' in keyword_args:
        response = await _info_from_arguments(event)
    if response:
        await client.respond(event, response)


@events.register(events.NewMessage(outgoing=True, pattern=f'{cmd_prefix}add(ed)?'))
async def added(event: NewMessage.Event) -> None:
    client: KantekClient = event.client
    chat: Channel = await event.get_input_chat()
    me = await client(GetParticipantRequest(chat, 'me'))

    if isinstance(me.participant, (ChannelParticipantSelf, ChannelParticipantAdmin)):
        added_by_id = me.participant.inviter_id
        response = Link(str(added_by_id), f'tg://user?id={added_by_id}')
    else:
        response = Italic('None')

    response = MDTeXDocument(Section(Bold('Added by'), response))
    await client.respond(event, response)


async def _info_from_arguments(event) -> MDTeXDocument:
    msg: Message = event.message
    client: KantekClient = event.client
    keyword_args, args = await helpers.get_args(event)
    search_name = keyword_args.get('search', False)
    if search_name:
        entities = [search_name]
    else:
        entities = [entity[1] for entity in msg.get_entities_text()
                    if isinstance(entity[0], (MessageEntityMention, MessageEntityMentionName))]

    # append any user ids to the list
    for uid in args:
        if isinstance(uid, int):
            entities.append(uid)

    users = []
    errors = []
    for entity in entities:
        try:
            user: User = await client.get_entity(entity)
            users.append(await _collect_user_info(client, user, **keyword_args))
        except constants.GET_ENTITY_ERRORS as err:
            errors.append(str(entity))
    if users:
        return MDTeXDocument(*users, (Section(Bold('Errors for'), Code(', '.join(errors)))) if errors else '')


async def _info_from_reply(event, **kwargs) -> MDTeXDocument:
    msg: Message = event.message
    client: KantekClient = event.client
    get_forward = kwargs.get('forward', True)
    reply_msg: Message = await msg.get_reply_message()

    if get_forward and reply_msg.forward is not None:
        forward: Forward = reply_msg.forward
        user: User = await client.get_entity(forward.sender_id)
    else:
        user: User = await client.get_entity(reply_msg.sender_id)

    return MDTeXDocument(await _collect_user_info(client, user, **kwargs))


async def _collect_user_info(client, user, **kwargs) -> Union[Section, KeyValueItem]:
    db: MySQLDB = client.db    
    id_only = kwargs.get('id', False)
    bl_only = kwargs.get('bl', False)
    show_general = kwargs.get('general', True)
    show_bot = kwargs.get('bot', False)
    show_misc = kwargs.get('misc', False)
    show_all = kwargs.get('all', False)

    if show_all:
        show_general = True
        show_bot = True
        show_misc = True

    mention_name = kwargs.get('mention', False)

    full_name = await helpers.get_full_name(user)
    if mention_name:
        title = Link(full_name, f'tg://user?id={user.id}')
    else:
        title = Bold(full_name)

    ban_reason = await client.db.banlist.get_user(user.id)
    if ban_reason:
        ban_reason = ban_reason['ban_reason']

    if id_only:
        return KeyValueItem(title, Code(user.id))
    if bl_only:
        return KeyValueItem(title, Code(ban_reason) if ban_reason else Italic('False'))
    else:
        general = SubSection(
            Bold('general'),
            KeyValueItem('id', Code(user.id)),
            KeyValueItem('first_name', Code(user.first_name)),
            KeyValueItem('last_name', Code(user.last_name)),
            KeyValueItem('username', Code(user.username)),
            KeyValueItem('mutual_contact', Code(user.mutual_contact)),
            KeyValueItem('ban_reason', Code(ban_reason)) if ban_reason else KeyValueItem('gbanned', Code('False')))

        bot = SubSection(
            Bold('bot'),
            KeyValueItem('bot', Code(user.bot)),
            KeyValueItem('bot_chat_history', Code(user.bot_chat_history)),
            KeyValueItem('bot_info_version', Code(user.bot_info_version)),
            KeyValueItem('bot_inline_geo', Code(user.bot_inline_geo)),
            KeyValueItem('bot_inline_placeholder',
                         Code(user.bot_inline_placeholder)),
            KeyValueItem('bot_nochats', Code(user.bot_nochats)))
        misc = SubSection(
            Bold('misc'),
            KeyValueItem('restricted', Code(user.restricted)),
            KeyValueItem('restriction_reason', Code(user.restriction_reason)),
            KeyValueItem('deleted', Code(user.deleted)),
            KeyValueItem('verified', Code(user.verified)),
            KeyValueItem('scam', Code(user.scam)),
            KeyValueItem('min', Code(user.min)),
            KeyValueItem('lang_code', Code(user.lang_code)))

        return Section(title,
                       general if show_general else None,
                       misc if show_misc else None,
                       bot if show_bot else None)
