#!/usr/bin/env python3
"""
Telegram Terminal Client – Ultimate Edition
Author: RobbieJr
"""

import asyncio
import os
import sys
import re
import tempfile
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv, set_key

# Core Telegram
from telethon import TelegramClient, functions, types
from telethon.errors import SessionPasswordNeededError
from telethon.tl.types import (
    User, Chat, Channel,
    MessageEntityBold, MessageEntityItalic, MessageEntityCode,
    MessageEntityStrike, MessageEntityUnderline, MessageEntityUrl,
    MessageEntityTextUrl, MessageEntityMention, MessageEntityHashtag,
    MessageEntityCashtag, MessageEntityBotCommand, MessageEntityEmail,
    MessageEntityPhone, MessageEntityPre, MessageEntityBlockquote,
    MessageEntitySpoiler
)

# Terminal UI
from colorama import init, Fore, Back, Style
init(autoreset=True)

# Advanced input
from prompt_toolkit import PromptSession
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.keys import Keys
from prompt_toolkit.shortcuts import clear as ptk_clear

# Optional audio
try:
    import sounddevice as sd
    import numpy as np
    HAS_AUDIO = True
    AUDIO_ERROR_MSG = ""
except ImportError:
    HAS_AUDIO = False
    AUDIO_ERROR_MSG = "sounddevice or numpy not installed. Install with: pip install sounddevice numpy"
except OSError as e:
    HAS_AUDIO = False
    if "PortAudio" in str(e):
        AUDIO_ERROR_MSG = "PortAudio library not found. On Termux: pkg install portaudio"
    else:
        AUDIO_ERROR_MSG = f"Audio error: {e}"

# Load environment variables
load_dotenv()
DOWNLOAD_PATH = os.getenv('DOWNLOAD_PATH', str(Path.home() / 'Downloads'))

# ----------------------------------------------------------------------
# Configuration
API_ID = 
API_HASH = ''
SESSION_FILE = 'tg_ultimate'

# ----------------------------------------------------------------------
# Helper functions
def safe_str(val):
    return str(val) if val is not None else ''

def get_term_width():
    try:
        return os.get_terminal_size().columns
    except OSError:
        return 80

def clear_screen():
    """Force clear screen using system command (works everywhere)."""
    os.system('cls' if os.name == 'nt' else 'clear')

# ----------------------------------------------------------------------
# Tag parsing for sending messages
def parse_formatting_tags(text):
    """
    Convert custom tags to Telegram entities.
    Supported tags: <b>, <i>, <u>, <st>, <sp>, <m>, <link="url">
    Returns (clean_text, entities)
    """
    entities = []
    clean_parts = []
    pos = 0
    # We'll use a stack for nested tags
    stack = []  # each element: (tag, start_index, url?)
    i = 0
    n = len(text)
    while i < n:
        if text[i] == '<':
            # Check for closing tag
            if i + 1 < n and text[i+1] == '/':
                # Closing tag
                j = text.find('>', i)
                if j == -1:
                    # Malformed, treat as plain
                    clean_parts.append(text[i])
                    i += 1
                    continue
                tag_name = text[i+2:j].strip()
                # Find matching opening in stack
                for k in range(len(stack)-1, -1, -1):
                    if stack[k][0] == tag_name:
                        # Found match
                        start = stack[k][1]
                        url = stack[k][2] if len(stack[k]) > 2 else None
                        # Create entity
                        if tag_name == 'b':
                            entities.append(MessageEntityBold(offset=start, length=pos - start))
                        elif tag_name == 'i':
                            entities.append(MessageEntityItalic(offset=start, length=pos - start))
                        elif tag_name == 'u':
                            entities.append(MessageEntityUnderline(offset=start, length=pos - start))
                        elif tag_name == 'st':
                            entities.append(MessageEntityStrike(offset=start, length=pos - start))
                        elif tag_name == 'sp':
                            entities.append(MessageEntitySpoiler(offset=start, length=pos - start))
                        elif tag_name == 'm':
                            entities.append(MessageEntityCode(offset=start, length=pos - start))
                        elif tag_name == 'link' and url:
                            entities.append(MessageEntityTextUrl(offset=start, length=pos - start, url=url))
                        # Remove from stack
                        stack.pop(k)
                        break
                else:
                    # No matching opening, treat as plain
                    clean_parts.append(text[i:j+1])
                i = j + 1
            else:
                # Opening tag
                j = text.find('>', i)
                if j == -1:
                    clean_parts.append(text[i])
                    i += 1
                    continue
                tag_content = text[i+1:j]
                # Check if it's a link with url
                if tag_content.startswith('link='):
                    # Extract url
                    url_match = re.match(r'link="([^"]+)"', tag_content)
                    if url_match:
                        url = url_match.group(1)
                        stack.append(('link', pos, url))
                    else:
                        # Malformed, treat as plain
                        clean_parts.append(text[i:j+1])
                else:
                    # Simple tag
                    tag_name = tag_content.strip()
                    if tag_name in ('b', 'i', 'u', 'st', 'sp', 'm'):
                        stack.append((tag_name, pos))
                    else:
                        # Unknown tag, treat as plain
                        clean_parts.append(text[i:j+1])
                i = j + 1
        else:
            clean_parts.append(text[i])
            pos += 1
            i += 1
    # Any unclosed tags are ignored (they remain as plain text)
    clean_text = ''.join(clean_parts)
    return clean_text, entities

# ----------------------------------------------------------------------
# Message formatting for display
def apply_entities(text, entities):
    """Convert Telegram entities to ANSI codes."""
    if not entities:
        return text
    entities = sorted(entities, key=lambda e: (e.offset, -e.length))
    pos = 0
    out = ''
    for ent in entities:
        if ent.offset > pos:
            out += text[pos:ent.offset]
        segment = text[ent.offset:ent.offset+ent.length]
        style = ''
        if isinstance(ent, MessageEntityBold):
            style = Style.BRIGHT
        elif isinstance(ent, MessageEntityItalic):
            style = '\x1b[3m'
        elif isinstance(ent, MessageEntityUnderline):
            style = '\x1b[4m'
        elif isinstance(ent, MessageEntityStrike):
            style = '\x1b[9m'
        elif isinstance(ent, MessageEntitySpoiler):
            style = Back.BLACK + Fore.BLACK  # hidden
        elif isinstance(ent, MessageEntityCode):
            style = Back.BLACK + Fore.GREEN
        elif isinstance(ent, MessageEntityPre):
            style = Back.BLACK + Fore.CYAN
        elif isinstance(ent, (MessageEntityUrl, MessageEntityTextUrl, MessageEntityMention)):
            style = Fore.BLUE + '\x1b[4m'
        elif isinstance(ent, (MessageEntityHashtag, MessageEntityCashtag, MessageEntityBotCommand)):
            style = Fore.MAGENTA
        elif isinstance(ent, (MessageEntityEmail, MessageEntityPhone)):
            style = Fore.CYAN
        out += style + segment + Style.RESET_ALL
        pos = ent.offset + ent.length
    if pos < len(text):
        out += text[pos:]
    return out

def format_code_block(text, lang):
    """Render a code block with language header."""
    lines = text.split('\n')
    header = f"[ {lang} ]" if lang else "[ Code ]"
    header = header.center(get_term_width() - 4)
    result = []
    width = get_term_width()
    result.append(Fore.WHITE + '┌' + '─' * (width - 2) + '┐')
    result.append(Fore.WHITE + '│' + Fore.YELLOW + Style.BRIGHT + header + Fore.WHITE + '│')
    result.append(Fore.WHITE + '├' + '─' * (width - 2) + '┤')
    for line in lines:
        result.append(Back.BLACK + Fore.GREEN + line + Back.RESET + Fore.WHITE)
    result.append(Fore.WHITE + '└' + '─' * (width - 2) + '┘')
    return result

def format_message(msg, idx, own_id, is_channel=False):
    """Return a list of lines representing the message in a box."""
    date_str = msg.date.strftime('%H:%M') if msg.date else '??:??'

    # Determine sender
    sender = msg.sender
    if sender:
        if isinstance(sender, User):
            first = safe_str(getattr(sender, 'first_name', ''))
            last = safe_str(getattr(sender, 'last_name', ''))
            sender_name = f"{first} {last}".strip() or "Deleted Account"
        else:
            sender_name = safe_str(getattr(sender, 'title', 'Unknown'))
    else:
        sender_name = "Unknown"

    is_own = (sender and hasattr(sender, 'id') and sender.id == own_id)

    # In channels, omit sender column if it's the channel itself
    if is_channel and not is_own:
        show_sender = False
    else:
        show_sender = True

    # Message content
    if msg.text:
        raw_text = msg.text
        # Check for code block (anywhere in message)
        code_pattern = r'```(\w*)\n(.*?)```'
        match = re.search(code_pattern, raw_text, re.DOTALL)
        if match:
            lang = match.group(1) or "text"
            code_content = match.group(2)
            return format_code_block(code_content, lang)
        else:
            # Normal message with entities
            styled_text = apply_entities(raw_text, msg.entities or [])
            # Split by newline to preserve intentional line breaks
            content_lines = styled_text.split('\n')
    elif msg.media:
        media_type = type(msg.media).__name__.replace('MessageMedia', '')
        content_lines = [f"[{media_type}]"]
    else:
        content_lines = ["[No text]"]

    # Determine box color
    box_color = Fore.GREEN if is_own else Fore.CYAN
    # Build header
    header = f"{box_color}[{idx:2}] {date_str}"
    if show_sender:
        disp_sender = sender_name[:15] + ('…' if len(sender_name) > 15 else '')
        header += f" {disp_sender:15}"

    # Build box lines
    result = []
    width = get_term_width()
    result.append(Fore.WHITE + '┌' + '─' * (width - 2) + '┐')
    header_line = f"│ {header}{' ' * (width - len(header) - 4)} │"
    result.append(Fore.WHITE + header_line)
    result.append(Fore.WHITE + '├' + '─' * (width - 2) + '┤')
    for line in content_lines:
        result.append(f"{Fore.WHITE}│ {line} │")
    result.append(Fore.WHITE + '└' + '─' * (width - 2) + '┘')
    return result

# ----------------------------------------------------------------------
# Custom input with hotkeys
bindings = KeyBindings()

@bindings.add(Keys.ControlS)
def _(event):
    event.app.exit(result=event.app.current_buffer.text)

@bindings.add(Keys.ControlB)
def _(event):
    event.app.exit(result='__BACK__')

async def ainput_multiline(prompt="> "):
    session = PromptSession(key_bindings=bindings, multiline=True)
    try:
        return await session.prompt_async(prompt)
    except KeyboardInterrupt:
        return '__BACK__'

# ----------------------------------------------------------------------
# Main Application Class
class TelegramUltimate:
    def __init__(self):
        self.client = TelegramClient(SESSION_FILE, API_ID, API_HASH)
        self.me = None
        self.dialogs = []
        self.current_chat = None
        self.messages = []          # list of (index, message)
        self.msg_id_map = {}         # index -> message_id
        self.in_chat = False

    async def login(self):
        clear_screen()
        self._print_header("LOGIN")
        if not await self.client.is_user_authorized():
            phone = input(Fore.YELLOW + "Phone (with country code): " + Fore.RESET)
            await self.client.send_code_request(phone)
            code = input(Fore.YELLOW + "Code: " + Fore.RESET)
            try:
                await self.client.sign_in(phone, code)
            except SessionPasswordNeededError:
                pwd = input(Fore.YELLOW + "2FA password: " + Fore.RESET)
                await self.client.sign_in(password=pwd)
            print(Fore.GREEN + "Login successful!")
        else:
            print(Fore.GREEN + "Already logged in.")
        self.me = await self.client.get_me()
        await asyncio.sleep(1)

    def _print_header(self, title):
        width = get_term_width()
        print(Fore.CYAN + Style.BRIGHT + '┌' + '─' * (width-2) + '┐')
        print(Fore.CYAN + Style.BRIGHT + '│' + title.center(width-2) + '│')
        print(Fore.CYAN + Style.BRIGHT + '└' + '─' * (width-2) + '┘' + Style.RESET_ALL)

    async def main_menu(self):
        while True:
            clear_screen()
            self._print_header("TELEGRAM ULTIMATE")
            print(Fore.WHITE + "1. List chats")
            print("2. Create new group")
            print("3. Create new channel")
            print("4. Search users/groups/channels")
            print("5. Settings")
            print("6. Exit")
            choice = input(Fore.BLUE + "\nChoose option (1-6): " + Fore.RESET)

            if choice == '1':
                await self.list_chats()
            elif choice == '2':
                await self.create_group()
            elif choice == '3':
                await self.create_channel()
            elif choice == '4':
                await self.search()
            elif choice == '5':
                await self.settings()
            elif choice == '6':
                print(Fore.GREEN + "Goodbye!")
                break
            else:
                print(Fore.RED + "Invalid choice.")
                await asyncio.sleep(1)

    async def list_chats(self):
        clear_screen()
        self._print_header("YOUR CHATS")
        try:
            self.dialogs = await self.client.get_dialogs()
            if not self.dialogs:
                print(Fore.YELLOW + "No chats.")
                input(Fore.MAGENTA + "\nPress Enter...")
                return

            for i, d in enumerate(self.dialogs, 1):
                e = d.entity
                icon = "[U]" if isinstance(e, User) else "[G]" if isinstance(e, Chat) else "[C]"
                name = getattr(e, 'title', None) or f"{safe_str(getattr(e,'first_name',''))} {safe_str(getattr(e,'last_name',''))}".strip() or "Unknown"
                if len(name) > 40:
                    name = name[:37] + "..."
                unread = d.unread_count
                unread_str = f" ({unread} new)" if unread > 0 else ""
                print(f"{Fore.WHITE}[{i:2}] {icon} {name:40}{Fore.YELLOW}{unread_str}{Fore.RESET}")

            print(Fore.CYAN + "\nActions: <num> open | d<num> delete | a<num> archive | s search | n new group | c new channel | b back")
            cmd = input(Fore.BLUE + "> " + Fore.RESET).strip().lower()
            if cmd == 'b':
                return
            elif cmd == 's':
                await self.search()
            elif cmd == 'n':
                await self.create_group()
            elif cmd == 'c':
                await self.create_channel()
            elif cmd.startswith('d'):
                try:
                    await self.delete_chat(int(cmd[1:]))
                except:
                    print(Fore.RED + "Invalid number")
                    await asyncio.sleep(1)
            elif cmd.startswith('a'):
                try:
                    await self.archive_chat(int(cmd[1:]))
                except:
                    print(Fore.RED + "Invalid number")
                    await asyncio.sleep(1)
            else:
                try:
                    await self.open_chat(int(cmd))
                except:
                    print(Fore.RED + "Invalid command")
                    await asyncio.sleep(1)
        except Exception as e:
            print(Fore.RED + f"Error: {e}")
            input(Fore.MAGENTA + "\nPress Enter...")

    async def delete_chat(self, index):
        if 1 <= index <= len(self.dialogs):
            d = self.dialogs[index-1]
            conf = input(Fore.RED + f"Delete chat? (y/n): ")
            if conf.lower() == 'y':
                await self.client.delete_dialog(d.entity)
                print(Fore.GREEN + "Deleted.")
            await asyncio.sleep(1)

    async def archive_chat(self, index):
        if 1 <= index <= len(self.dialogs):
            d = self.dialogs[index-1]
            await self.client(functions.folders.EditPeerFoldersRequest(
                folder_peers=[types.InputFolderPeer(d.entity, 1)]
            ))
            print(Fore.GREEN + "Archived.")
            await asyncio.sleep(1)

    async def open_chat(self, index):
        if 1 <= index <= len(self.dialogs):
            self.current_chat = self.dialogs[index-1].entity
            await self.chat_loop()

    async def chat_loop(self):
        self.in_chat = True
        while self.in_chat:
            clear_screen()
            # Header
            name = getattr(self.current_chat, 'title', None) or f"{safe_str(getattr(self.current_chat,'first_name',''))} {safe_str(getattr(self.current_chat,'last_name',''))}".strip() or "Unknown"
            self._print_header(f"CHAT: {name[:50]}")

            # Fetch messages
            try:
                msgs = await self.client.get_messages(self.current_chat, limit=30)
                self.messages = list(enumerate(reversed(msgs), 1))
                self.msg_id_map = {idx: m.id for idx, m in self.messages}
            except Exception as e:
                print(Fore.RED + f"Error: {e}")
                input(Fore.MAGENTA + "Press Enter to go back...")
                break

            # Determine if current chat is a channel
            is_channel = isinstance(self.current_chat, Channel) and self.current_chat.broadcast

            # Display messages with boxes
            for idx, msg in self.messages:
                for line in format_message(msg, idx, self.me.id, is_channel):
                    print(line)

            # Command bar
            print(Fore.CYAN + "─" * get_term_width())
            print("Commands: send | edit | attach | del | forward | save | help")
            print("Hotkeys: Ctrl+S send | Ctrl+B back")

            cmd = await ainput_multiline("> ")
            if cmd == '__BACK__':
                self.in_chat = False
                break
            cmd = cmd.strip()
            if not cmd:
                continue

            if cmd == 'back':
                self.in_chat = False
                break
            elif cmd == 'help':
                self.show_help()
            elif cmd == 'more':
                await self.load_more_messages()
            elif cmd.startswith('send '):
                await self.send_message(cmd[5:])
            elif cmd.startswith('attach '):
                await self.send_file(cmd[7:].strip())
            elif cmd.startswith('edit '):
                parts = cmd.split(maxsplit=2)
                if len(parts) >= 3:
                    try:
                        idx = int(parts[1])
                        await self.edit_message(idx, parts[2])
                    except:
                        print(Fore.RED + "Invalid format")
                else:
                    print(Fore.RED + "Usage: edit <num> <new text>")
                await asyncio.sleep(1)
            elif cmd.startswith('del '):
                parts = cmd.split()
                if len(parts) == 2:
                    try:
                        await self.delete_message(int(parts[1]))
                    except:
                        print(Fore.RED + "Invalid number")
                await asyncio.sleep(1)
            elif cmd.startswith('forward '):
                m = re.match(r'forward\s+(\d+)\s+to\s+(.+)', cmd)
                if m:
                    await self.forward_message(int(m.group(1)), m.group(2))
                else:
                    print(Fore.RED + "Usage: forward <num> to <target>")
                await asyncio.sleep(1)
            elif cmd.startswith('save '):
                parts = cmd.split()
                if len(parts) == 2:
                    try:
                        await self.save_message(int(parts[1]))
                    except:
                        print(Fore.RED + "Invalid number")
                await asyncio.sleep(1)
            elif cmd.startswith('download '):
                parts = cmd.split()
                if len(parts) == 2:
                    try:
                        await self.download_media(int(parts[1]))
                    except:
                        print(Fore.RED + "Invalid number")
                await asyncio.sleep(1)
            elif cmd.startswith('pin '):
                parts = cmd.split()
                if len(parts) == 2:
                    try:
                        await self.pin_message(int(parts[1]))
                    except:
                        print(Fore.RED + "Invalid number")
                await asyncio.sleep(1)
            elif cmd.startswith('unpin '):
                parts = cmd.split()
                if len(parts) == 2:
                    try:
                        await self.unpin_message(int(parts[1]))
                    except:
                        print(Fore.RED + "Invalid number")
                await asyncio.sleep(1)
            elif cmd == 'pinned':
                await self.view_pinned()
            elif cmd.startswith('poll '):
                await self.create_poll(cmd[5:])
            elif cmd == 'mute':
                await self.toggle_mute()
            elif cmd == 'voice':
                await self.record_voice()
            else:
                await self.send_message(cmd)

    def show_help(self):
        clear_screen()
        self._print_header("COMMAND HELP")
        help_text = """
Available commands inside a chat:

send <text>          – Send a message (supports <b>, <i>, <u>, <st>, <sp>, <m>, <link="url">)
attach <path>        – Send a file
edit <num> <new>     – Edit your message number <num>
del <num>            – Delete message <num> (optionally for everyone)
forward <num> to <target> – Forward message <num> to another chat
save <num>           – Save message <num> to Saved Messages
download <num>       – Download media from message <num>
pin <num>            – Pin message <num>
unpin <num>          – Unpin message <num>
pinned               – Show pinned messages
poll "Q" "A" "B"...  – Create a poll
mute                 – Mute/unmute current chat
voice                – Record and send a voice note (if available)
more                 – Load 30 more messages
back                 – Return to chat list
help                 – Show this help

Hotkeys:
Ctrl+S – send
Ctrl+B – go back
"""
        print(help_text)
        input(Fore.MAGENTA + "Press Enter to continue..." + Fore.RESET)

    async def send_message(self, text):
        if not text:
            return
        # Parse custom tags
        clean_text, entities = parse_formatting_tags(text)
        try:
            await self.client.send_message(self.current_chat, clean_text, formatting_entities=entities)
            print(Fore.GREEN + "Message sent.")
        except Exception as e:
            print(Fore.RED + f"Error: {e}")
        await asyncio.sleep(0.5)

    async def send_file(self, path):
        if os.path.isfile(path):
            try:
                await self.client.send_file(self.current_chat, path)
                print(Fore.GREEN + "File sent.")
            except Exception as e:
                print(Fore.RED + f"Error: {e}")
        else:
            print(Fore.RED + "File not found.")
        await asyncio.sleep(1)

    async def edit_message(self, idx, new_text):
        if idx in self.msg_id_map:
            msg_id = self.msg_id_map[idx]
            msg = await self.client.get_messages(self.current_chat, ids=msg_id)
            if msg and msg[0].out:
                # Parse tags for edit as well
                clean_text, entities = parse_formatting_tags(new_text)
                await self.client.edit_message(self.current_chat, msg_id, clean_text, formatting_entities=entities)
                print(Fore.GREEN + "Edited.")
            else:
                print(Fore.RED + "Cannot edit others' messages.")
        else:
            print(Fore.RED + "Invalid index.")

    async def delete_message(self, idx):
        if idx in self.msg_id_map:
            msg_id = self.msg_id_map[idx]
            rev = input(Fore.YELLOW + "Delete for everyone? (y/n): ")
            revoke = rev.lower() == 'y'
            await self.client.delete_messages(self.current_chat, [msg_id], revoke=revoke)
            print(Fore.GREEN + "Deleted.")
        else:
            print(Fore.RED + "Invalid index.")

    async def forward_message(self, idx, target):
        if idx in self.msg_id_map:
            msg_id = self.msg_id_map[idx]
            try:
                target_entity = await self.client.get_entity(target)
                await self.client.forward_messages(target_entity, [msg_id], self.current_chat)
                print(Fore.GREEN + "Forwarded.")
            except Exception as e:
                print(Fore.RED + f"Target error: {e}")
        else:
            print(Fore.RED + "Invalid index.")

    async def save_message(self, idx):
        if idx in self.msg_id_map:
            msg_id = self.msg_id_map[idx]
            await self.client.forward_messages('me', [msg_id], self.current_chat)
            print(Fore.GREEN + "Saved.")
        else:
            print(Fore.RED + "Invalid index.")

    async def download_media(self, idx):
        if idx in self.msg_id_map:
            msg_id = self.msg_id_map[idx]
            msg = await self.client.get_messages(self.current_chat, ids=msg_id)
            if msg and msg[0].media:
                path = await msg[0].download_media(file=DOWNLOAD_PATH)
                print(Fore.GREEN + f"Downloaded to {path}")
            else:
                print(Fore.RED + "No media in that message.")
        else:
            print(Fore.RED + "Invalid index.")

    async def pin_message(self, idx):
        if idx in self.msg_id_map:
            msg_id = self.msg_id_map[idx]
            await self.client.pin_message(self.current_chat, msg_id)
            print(Fore.GREEN + "Pinned.")
        else:
            print(Fore.RED + "Invalid index.")

    async def unpin_message(self, idx):
        if idx in self.msg_id_map:
            msg_id = self.msg_id_map[idx]
            await self.client.unpin_message(self.current_chat, msg_id)
            print(Fore.GREEN + "Unpinned.")
        else:
            print(Fore.RED + "Invalid index.")

    async def view_pinned(self):
        try:
            pinned = await self.client.get_messages(self.current_chat, pinned=True)
            if pinned:
                print(Fore.CYAN + "Pinned messages:")
                for msg in pinned:
                    print(f"  {msg.id}: {msg.text[:50]}")
            else:
                print(Fore.YELLOW + "No pinned messages.")
        except Exception as e:
            print(Fore.RED + f"Error: {e}")
        input(Fore.MAGENTA + "Press Enter...")

    async def create_poll(self, arg_str):
        import shlex
        try:
            args = shlex.split(arg_str)
            if len(args) < 3:
                print(Fore.RED + "Usage: poll \"Question\" \"Option1\" \"Option2\" ...")
                return
            question = args[0]
            options = args[1:]
            await self.client.send_message(self.current_chat, question, file=types.InputMediaPoll(
                poll=types.Poll(
                    id=0,
                    question=question,
                    answers=[types.PollAnswer(text=opt, option=str(i).encode()) for i, opt in enumerate(options)],
                    multiple_choice=False
                )
            ))
            print(Fore.GREEN + "Poll created.")
        except Exception as e:
            print(Fore.RED + f"Error: {e}")
        await asyncio.sleep(1)

    async def toggle_mute(self):
        try:
            settings = await self.client(functions.account.GetNotifySettingsRequest(peer=self.current_chat))
            mute_until = 2**31 - 1 if not settings.mute_until else 0
            await self.client(functions.account.UpdateNotifySettingsRequest(
                peer=self.current_chat,
                settings=types.InputPeerNotifySettings(
                    show_previews=settings.show_previews,
                    silent=settings.silent,
                    mute_until=mute_until
                )
            ))
            print(Fore.GREEN + "Mute toggled.")
        except Exception as e:
            print(Fore.RED + f"Error: {e}")
        await asyncio.sleep(1)

    async def record_voice(self):
        if not HAS_AUDIO:
            print(Fore.RED + AUDIO_ERROR_MSG)
            print(Fore.YELLOW + "Voice recording disabled.")
            await asyncio.sleep(2)
            return
        print(Fore.YELLOW + "Recording... Press Ctrl+C to stop.")
        fs = 44100
        try:
            recording = sd.rec(int(5 * fs), samplerate=fs, channels=1, dtype='int16')
            sd.wait()
            with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as f:
                # In a real implementation, use soundfile to write
                pass
            print(Fore.GREEN + "Voice recorded (demo). To actually send, implement audio encoding.")
        except Exception as e:
            print(Fore.RED + f"Error: {e}")
        await asyncio.sleep(1)

    async def load_more_messages(self):
        if self.messages:
            oldest = self.messages[0][1]
            try:
                older = await self.client.get_messages(self.current_chat, limit=30, offset_id=oldest.id)
                if older:
                    new_msgs = list(enumerate(reversed(older), start=len(self.messages)+1))
                    self.messages = new_msgs + self.messages
                    self.msg_id_map.update({idx: m.id for idx, m in new_msgs})
                else:
                    print(Fore.YELLOW + "No more messages.")
                    await asyncio.sleep(1)
            except Exception as e:
                print(Fore.RED + f"Error: {e}")
                await asyncio.sleep(1)

    async def create_group(self):
        clear_screen()
        self._print_header("CREATE GROUP")
        title = input("Group title: ").strip()
        if not title:
            return
        users_input = input("Usernames to add (comma-separated): ")
        usernames = [u.strip() for u in users_input.split(',') if u.strip()]
        try:
            users = [await self.client.get_entity(u) for u in usernames]
            await self.client(functions.messages.CreateChatRequest(users, title))
            print(Fore.GREEN + "Group created!")
        except Exception as e:
            print(Fore.RED + f"Error: {e}")
        input(Fore.MAGENTA + "Press Enter...")

    async def create_channel(self):
        clear_screen()
        self._print_header("CREATE CHANNEL")
        title = input("Channel title: ").strip()
        if not title:
            return
        desc = input("Description (optional): ")
        public = input("Public? (y/n): ").lower() == 'y'
        username = None
        if public:
            username = input("Username (without @): ").strip()
        try:
            result = await self.client(functions.channels.CreateChannelRequest(
                title=title,
                about=desc,
                broadcast=True,
                megagroup=False
            ))
            channel = result.chats[0]
            if public and username:
                await self.client(functions.channels.UpdateUsernameRequest(channel, username))
            print(Fore.GREEN + "Channel created!")
        except Exception as e:
            print(Fore.RED + f"Error: {e}")
        input(Fore.MAGENTA + "Press Enter...")

    async def search(self):
        clear_screen()
        self._print_header("SEARCH")
        query = input("Search for username or name: ").strip()
        if not query:
            return
        try:
            try:
                entity = await self.client.get_entity(query)
                print(Fore.GREEN + f"Found: {entity.first_name if hasattr(entity,'first_name') else entity.title} (@{entity.username if hasattr(entity,'username') else 'no username'})")
            except:
                found = []
                for d in self.dialogs:
                    e = d.entity
                    name = getattr(e, 'title', None) or f"{safe_str(getattr(e,'first_name',''))} {safe_str(getattr(e,'last_name',''))}".strip()
                    if query.lower() in name.lower():
                        found.append(e)
                if found:
                    print(Fore.GREEN + "Found in your chats:")
                    for e in found:
                        print(f"  {getattr(e,'title',None) or e.first_name}")
                else:
                    print(Fore.YELLOW + "No results.")
        except Exception as e:
            print(Fore.RED + f"Error: {e}")
        input(Fore.MAGENTA + "Press Enter...")

    async def settings(self):
        clear_screen()
        self._print_header("SETTINGS")
        global DOWNLOAD_PATH
        print(Fore.WHITE + f"Current download path: {DOWNLOAD_PATH}")
        print(Fore.CYAN + "Options:")
        print("1. Change download path")
        print("2. View all commands")
        print("3. Back")
        choice = input(Fore.BLUE + "Choose: " + Fore.RESET).strip()
        if choice == '1':
            new_path = input("Enter new path: ").strip()
            if new_path:
                if os.path.isdir(new_path):
                    DOWNLOAD_PATH = new_path
                    set_key('.env', 'DOWNLOAD_PATH', new_path)
                    print(Fore.GREEN + "Updated.")
                else:
                    print(Fore.RED + "Directory does not exist.")
        elif choice == '2':
            self.show_help()
        input(Fore.MAGENTA + "Press Enter to continue..." + Fore.RESET)

    async def run(self):
        await self.client.start()
        await self.login()
        await self.main_menu()

# ----------------------------------------------------------------------
async def main():
    app = TelegramUltimate()
    try:
        await app.run()
    except KeyboardInterrupt:
        print(f"\n{Fore.RED}Interrupted. Exiting.{Fore.RESET}")
    finally:
        await app.client.disconnect()

if __name__ == '__main__':
    asyncio.run(main())
