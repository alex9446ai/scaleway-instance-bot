from telegram import (BotCommand, BotCommandScopeChat, CallbackQuery,
                      InlineKeyboardButton, InlineKeyboardMarkup, Message,
                      Update)

from .scaleway import (ALLOWED_ACTIONS, AllowedActions, Scaleway,
                       is_allowed_action, try_redeploy)
from .telegram_decorators import (only_allowed_chats_callback,
                                  only_allowed_chats_message)
from .telegram_utils import DEFAULT_CONTEXT, escape, telegram_retry
from .utils import get_build_info

CHAT_ID = int

commands = [
    BotCommand('start', 'print list of commands'),
    BotCommand('help', 'print list of commands'),
    BotCommand('info', 'get build info (if any)'),
    BotCommand('redeploy', 'redeploy itself'),
    BotCommand('set_commands', 'set commands menu'),
    BotCommand('list_servers', 'list scaleway servers'),
    *[BotCommand(action, f'{action} scaleway server')
      for action in sorted(ALLOWED_ACTIONS)]
]
command_lines = [f'/{cmd.command} - {cmd.description}' for cmd in commands]


class Commands:
    def __init__(self, allowed_chats: set[int]):
        self.allowed_chats = allowed_chats
        self.build_info = get_build_info()

    def is_chat_allowed(self, update: Update) -> tuple[bool, CHAT_ID]:
        chat_id = update.effective_chat.id if update.effective_chat else 0
        return (chat_id in self.allowed_chats, chat_id)

    @only_allowed_chats_message
    async def start_or_help(self, message: Message, context: DEFAULT_CONTEXT):
        await telegram_retry(message.reply_text, '\n'.join(command_lines))

    @only_allowed_chats_message
    async def info(self, message: Message, context: DEFAULT_CONTEXT):
        await telegram_retry(message.reply_text, self.build_info)

    @only_allowed_chats_message
    async def redeploy(self, message: Message, context: DEFAULT_CONTEXT):
        _, resp = await try_redeploy()
        await telegram_retry(message.reply_text, resp)

    @only_allowed_chats_message
    async def set_commands(self, message: Message, context: DEFAULT_CONTEXT):
        scope = BotCommandScopeChat(message.chat.id)
        await telegram_retry(context.bot.set_my_commands, commands, scope)
        await telegram_retry(message.reply_text, 'The commands have been set')

    @only_allowed_chats_message
    async def list_servers(self, message: Message, context: DEFAULT_CONTEXT):
        servers = await Scaleway().list_servers()
        if not servers:
            await telegram_retry(message.reply_text, 'no servers to list')
            return
        servers_lines = [f'*{escape(s.name)}*: _{escape(s.state)}_'
                         for s in servers]
        await telegram_retry(
            message.reply_markdown_v2, '\n'.join(servers_lines)
        )

    @staticmethod
    async def ask_which_server(message: Message, action: AllowedActions):
        servers = await Scaleway().list_servers()
        if not servers:
            await telegram_retry(message.reply_text, 'no servers to list')
            return
        keyboard = [
            InlineKeyboardButton(s.name, callback_data=f'{action}:{s.id}')
            for s in servers
        ]
        await telegram_retry(
            message.reply_markdown_v2,
            f'Which server do you want to *{escape(action)}*?',
            reply_markup=InlineKeyboardMarkup.from_column(keyboard)
        )

    @staticmethod
    async def try_action(action: AllowedActions, server_name: str):
        try:
            await Scaleway().perform_raw_action(f'{action}:{server_name}')
            return f'sended {action} action'
        except ValueError as error:
            return str(error)

    @staticmethod
    def get_server_name(context: DEFAULT_CONTEXT):
        return context.args[0] if context.args else None

    @only_allowed_chats_message
    async def maybe_action(self, message: Message, context: DEFAULT_CONTEXT):
        if not message.text:
            await telegram_retry(message.reply_text, 'text is None')
            return
        action = message.text.split()[0].replace('/', '').split("@")[0]
        if not is_allowed_action(action):
            await telegram_retry(message.reply_text, 'action not valid')
            return
        if server_name := self.get_server_name(context):
            msg = await self.try_action(action, server_name)
            await telegram_retry(message.reply_text, msg)
        else:
            await self.ask_which_server(message, action)

    @only_allowed_chats_callback
    async def ask_callback(self, callback_query: CallbackQuery):
        await telegram_retry(callback_query.answer)
        data = callback_query.data
        if not data:
            await telegram_retry(
                callback_query.edit_message_text, 'no data in callback_query'
            )
            return
        try:
            action = await Scaleway().perform_raw_action(data)
            await telegram_retry(
                callback_query.edit_message_text, f'sended {action} action'
            )
        except ValueError as error:
            await telegram_retry(callback_query.edit_message_text, str(error))
