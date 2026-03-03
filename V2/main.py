#!/usr/bin/env python3
"""
Telegram Terminal Client – Full-featured TUI for Telegram
Author: RobbieJr (adapted)
"""

import asyncio
import os
import sys
from datetime import datetime
from pathlib import Path

from colorama import init, Fore, Back, Style
from telethon import TelegramClient, functions, types
from telethon.errors import SessionPasswordNeededError, RPCError
from telethon.tl.types import (
    User, Chat, Channel,
    MessageEntityBold, MessageEntityItalic, MessageEntityCode,
    MessageEntityStrike, MessageEntityUnderline, MessageEntityUrl,
    MessageEntityTextUrl, MessageEntityMention, MessageEntityHashtag,
    MessageEntityCashtag, MessageEntityBotCommand, MessageEntityEmail,
    MessageEntityPhone, MessageEntityPre, MessageEntityBlockquote
)

# ----------------------------- Configuration -----------------------------
API_ID = 
API_HASH = ''
SESSION_FILE = 'tg_client_session'

# ----------------------------- Initialise colorama -----------------------
init(autoreset=True)

# ----------------------------- Helper Functions -------------------------
def clear_screen():
    """Clear terminal."""
    os.system('cls' if os.name == 'nt' else 'clear')

def print_header(title):
    """Print a styled header with borders."""
    width = 70
    print(Fore.CYAN + Style.BRIGHT + '┌' + '─' * (width - 2) + '┐')
    print(Fore.CYAN + Style.BRIGHT + '│' + title.center(width - 2) + '│')
    print(Fore.CYAN + Style.BRIGHT + '└' + '─' * (width - 2) + '┘' + Style.RESET_ALL)

def safe_str(value):
    """Convert None to empty string."""
    return str(value) if value is not None else ""

# ----------------------------- Message Formatting -----------------------
def format_entities(text, entities):
    """Apply Telegram entities to text and return ANSI-styled string."""
    if not entities:
        return text

    entities = sorted(entities, key=lambda e: (e.offset, -e.length))
    segments = []
    pos = 0
    style_stack = []

    def entity_to_ansi(entity):
        styles = []
        if isinstance(entity, MessageEntityBold):
            styles.append(Style.BRIGHT)
        elif isinstance(entity, MessageEntityItalic):
            styles.append('\x1b[3m')
        elif isinstance(entity, MessageEntityUnderline):
            styles.append('\x1b[4m')
        elif isinstance(entity, MessageEntityStrike):
            styles.append('\x1b[9m')
        elif isinstance(entity, MessageEntityCode):
            styles.append(Back.BLACK + Fore.GREEN)
        elif isinstance(entity, MessageEntityPre):
            styles.append(Back.BLACK + Fore.CYAN)
        elif isinstance(entity, MessageEntityBlockquote):
            styles.append(Fore.YELLOW + '\x1b[3m')
        elif isinstance(entity, (MessageEntityUrl, MessageEntityTextUrl, MessageEntityMention)):
            styles.append(Fore.BLUE + '\x1b[4m')
        elif isinstance(entity, (MessageEntityHashtag, MessageEntityCashtag, MessageEntityBotCommand)):
            styles.append(Fore.MAGENTA)
        elif isinstance(entity, (MessageEntityEmail, MessageEntityPhone)):
            styles.append(Fore.CYAN)
        return ''.join(styles)

    for ent in entities:
        if ent.offset > pos:
            segments.append((text[pos:ent.offset], style_stack.copy()))
        style_stack.append(entity_to_ansi(ent))
        seg_text = text[ent.offset:ent.offset + ent.length]
        segments.append((seg_text, style_stack.copy()))
        pos = ent.offset + ent.length

    if pos < len(text):
        segments.append((text[pos:], style_stack.copy()))

    result = ''
    for seg_text, styles in segments:
        if styles:
            result += ''.join(styles) + seg_text + Style.RESET_ALL
        else:
            result += seg_text
    return result

# ----------------------------- Chat / Message Display -------------------
def format_message(msg, index, own_id, show_sender=True):
    """Return a formatted message line with index, time, sender, and styled text."""
    date_str = msg.date.strftime('%H:%M') if msg.date else '??:??'

    # Determine sender name
    sender = msg.sender
    if sender:
        if isinstance(sender, User):
            first = safe_str(getattr(sender, 'first_name', None))
            last = safe_str(getattr(sender, 'last_name', None))
            sender_name = f"{first} {last}".strip() or "Deleted Account"
        else:
            sender_name = safe_str(getattr(sender, 'title', 'Unknown'))
    else:
        sender_name = "Unknown"

    # Truncate long names
    if len(sender_name) > 15:
        sender_name = sender_name[:12] + "..."

    # Determine if this message is from us
    is_own = (sender and hasattr(sender, 'id') and sender.id == own_id)

    # Message content
    if msg.text:
        styled_text = format_entities(msg.text, msg.entities or [])
    elif msg.media:
        media_type = type(msg.media).__name__.replace('MessageMedia', '')
        styled_text = f"[{media_type}]"
    else:
        styled_text = "[No text]"

    # Build line: [index] time sender message
    # Own messages aligned to the right
    prefix = f"[{index:2}] {date_str} "
    if is_own:
        # Right-align the whole line except the index+time part? Better: push message to right.
        # We'll put sender on right too? Actually own messages show "You" as sender.
        # We'll just put the whole line after prefix right-aligned.
        # But simpler: we can pad the line to terminal width.
        # We'll compute available width for message.
        # For simplicity, we'll just use a fixed width and align with spaces.
        # Here we do a basic right alignment for the message part.
        line = f"{prefix}{Fore.GREEN}You{Fore.RESET} {styled_text}"
        # Get terminal width
        try:
            term_width = os.get_terminal_size().columns
        except OSError:
            term_width = 80
        # Calculate visible length without ANSI codes
        plain_line = f"{prefix}You {msg.text if msg.text else ''}"
        visible_len = len(plain_line)
        if visible_len < term_width:
            line = ' ' * (term_width - visible_len) + line
    else:
        line = f"{prefix}{Fore.CYAN}{sender_name:15}{Fore.RESET} {styled_text}"

    return line

# ----------------------------- Async Input ------------------------------
async def ainput(prompt):
    """Async input using executor to not block event loop."""
    return await asyncio.get_event_loop().run_in_executor(None, input, prompt)

# ----------------------------- Main Client Logic -----------------------
class TelegramTUI:
    def __init__(self):
        self.client = TelegramClient(SESSION_FILE, API_ID, API_HASH)
        self.me = None
        self.dialogs = []
        self.current_chat = None
        self.messages = []          # list of (index, message) for current chat
        self.msg_id_map = {}         # index -> message_id

    async def login(self):
        """Authenticate the user."""
        clear_screen()
        print_header("LOGIN")
        if not await self.client.is_user_authorized():
            phone = await ainput(Fore.YELLOW + "Phone number (with country code): " + Fore.RESET)
            await self.client.send_code_request(phone)
            code = await ainput(Fore.YELLOW + "Code: " + Fore.RESET)
            try:
                await self.client.sign_in(phone, code)
            except SessionPasswordNeededError:
                password = await ainput(Fore.YELLOW + "2FA password: " + Fore.RESET)
                await self.client.sign_in(password=password)
            print(Fore.GREEN + "Login successful!")
        else:
            print(Fore.GREEN + "Already logged in.")
        self.me = await self.client.get_me()
        await asyncio.sleep(1)

    async def main_menu(self):
        """Display main menu and handle choices."""
        while True:
            clear_screen()
            print_header("TELEGRAM TERMINAL")
            print(Fore.WHITE + "1. List chats")
            print("2. Create new group")
            print("3. Create new channel")
            print("4. Exit")
            choice = await ainput(Fore.BLUE + "\nChoose option (1-4): " + Fore.RESET)

            if choice == '1':
                await self.list_chats()
            elif choice == '2':
                await self.create_group()
            elif choice == '3':
                await self.create_channel()
            elif choice == '4':
                print(Fore.GREEN + "Goodbye!")
                break
            else:
                print(Fore.RED + "Invalid choice.")
                await asyncio.sleep(1)

    async def list_chats(self):
        """Fetch and display all dialogs, then prompt for action."""
        clear_screen()
        print_header("YOUR CHATS")
        try:
            self.dialogs = await self.client.get_dialogs()
            if not self.dialogs:
                print(Fore.YELLOW + "No chats found.")
                await ainput(Fore.MAGENTA + "\nPress Enter to return...")
                return

            for i, d in enumerate(self.dialogs, 1):
                entity = d.entity
                # Determine type icon
                if isinstance(entity, User):
                    icon = "[U]"
                elif isinstance(entity, Chat):
                    icon = "[G]"
                elif isinstance(entity, Channel):
                    icon = "[C]" if getattr(entity, 'broadcast', False) else "[S]"  # S for supergroup
                else:
                    icon = "[?]"

                # Name
                if hasattr(entity, 'title') and entity.title:
                    name = entity.title
                else:
                    first = safe_str(getattr(entity, 'first_name', ''))
                    last = safe_str(getattr(entity, 'last_name', ''))
                    name = f"{first} {last}".strip() or "Unknown"
                if len(name) > 40:
                    name = name[:37] + "..."

                unread = d.unread_count
                unread_str = f" ({unread} new)" if unread > 0 else ""
                print(f"{Fore.WHITE}[{i:2}] {icon} {name:40}{Fore.YELLOW}{unread_str}{Fore.RESET}")

            print(Fore.CYAN + "\nActions:")
            print("  <number>   – open chat")
            print("  d<number>  – delete chat")
            print("  a<number>  – archive chat")
            print("  n          – new group")
            print("  c          – new channel")
            print("  b          – back")

            cmd = await ainput(Fore.BLUE + "\nEnter command: " + Fore.RESET)
            cmd = cmd.strip().lower()

            if cmd == 'b':
                return
            elif cmd == 'n':
                await self.create_group()
            elif cmd == 'c':
                await self.create_channel()
            elif cmd.startswith('d'):
                try:
                    num = int(cmd[1:])
                    await self.delete_chat(num)
                except ValueError:
                    print(Fore.RED + "Invalid number.")
                    await asyncio.sleep(1)
            elif cmd.startswith('a'):
                try:
                    num = int(cmd[1:])
                    await self.archive_chat(num)
                except ValueError:
                    print(Fore.RED + "Invalid number.")
                    await asyncio.sleep(1)
            else:
                try:
                    num = int(cmd)
                    await self.open_chat(num)
                except ValueError:
                    print(Fore.RED + "Invalid command.")
                    await asyncio.sleep(1)
        except Exception as e:
            print(Fore.RED + f"Error: {e}")
            await ainput(Fore.MAGENTA + "\nPress Enter...")

    async def delete_chat(self, index):
        """Delete a dialog."""
        if 1 <= index <= len(self.dialogs):
            dialog = self.dialogs[index - 1]
            confirm = await ainput(Fore.RED + f"Delete chat '{dialog.name}'? (y/n): ")
            if confirm.lower() == 'y':
                try:
                    await self.client.delete_dialog(dialog.entity)
                    print(Fore.GREEN + "Chat deleted.")
                except Exception as e:
                    print(Fore.RED + f"Error: {e}")
            await asyncio.sleep(1)
        else:
            print(Fore.RED + "Invalid index.")

    async def archive_chat(self, index):
        """Archive a chat (move to folder 1)."""
        if 1 <= index <= len(self.dialogs):
            dialog = self.dialogs[index - 1]
            try:
                # Archive = move to folder 1
                await self.client(functions.folders.EditPeerFoldersRequest(
                    folder_peers=[types.InputFolderPeer(dialog.entity, 1)]
                ))
                print(Fore.GREEN + "Chat archived.")
            except Exception as e:
                print(Fore.RED + f"Error: {e}")
            await asyncio.sleep(1)
        else:
            print(Fore.RED + "Invalid index.")

    async def open_chat(self, index):
        """Open a chat and enter its message loop."""
        if 1 <= index <= len(self.dialogs):
            self.current_chat = self.dialogs[index - 1].entity
            await self.chat_loop()
        else:
            print(Fore.RED + "Invalid index.")
            await asyncio.sleep(1)

    async def chat_loop(self):
        """Inside a chat: display messages and handle commands."""
        while True:
            clear_screen()
            # Get chat name
            if hasattr(self.current_chat, 'title') and self.current_chat.title:
                chat_name = self.current_chat.title
            else:
                first = safe_str(getattr(self.current_chat, 'first_name', ''))
                last = safe_str(getattr(self.current_chat, 'last_name', ''))
                chat_name = f"{first} {last}".strip() or "Unknown"
            print_header(f"CHAT: {chat_name[:50]}")

            # Fetch last 30 messages (or use stored)
            try:
                msgs = await self.client.get_messages(self.current_chat, limit=30)
                self.messages = list(enumerate(reversed(msgs), 1))  # 1..N, oldest first
                self.msg_id_map = {idx: msg.id for idx, msg in self.messages}
            except Exception as e:
                print(Fore.RED + f"Error loading messages: {e}")
                await ainput(Fore.MAGENTA + "\nPress Enter to go back...")
                return

            # Display messages
            for idx, msg in self.messages:
                line = format_message(msg, idx, self.me.id, show_sender=True)
                print(line)

            print(Fore.CYAN + "\n" + "─" * 70)
            print("Commands: send <text> | attach <file> | edit <num> <new> | del <num>")
            print("          forward <num> to <chat> | save <num> | more | back")
            cmd = await ainput(Fore.BLUE + "> " + Fore.RESET)
            cmd = cmd.strip()

            if cmd == 'back':
                break
            elif cmd == 'more':
                # Load more messages (simple: get older than first)
                if self.messages:
                    oldest = self.messages[0][1]
                    try:
                        older = await self.client.get_messages(self.current_chat, limit=30, offset_id=oldest.id)
                        if older:
                            # Prepend to messages
                            new_msgs = list(enumerate(reversed(older), start=len(self.messages)+1))
                            self.messages = new_msgs + self.messages
                            self.msg_id_map.update({idx: msg.id for idx, msg in new_msgs})
                        else:
                            print(Fore.YELLOW + "No more messages.")
                            await asyncio.sleep(1)
                    except Exception as e:
                        print(Fore.RED + f"Error: {e}")
                        await asyncio.sleep(1)
                continue
            elif cmd.startswith('send '):
                text = cmd[5:]
                if text:
                    try:
                        await self.client.send_message(self.current_chat, text)
                        print(Fore.GREEN + "Message sent.")
                    except Exception as e:
                        print(Fore.RED + f"Error: {e}")
                    await asyncio.sleep(1)
            elif cmd.startswith('attach '):
                path = cmd[7:].strip()
                if os.path.isfile(path):
                    try:
                        await self.client.send_file(self.current_chat, path)
                        print(Fore.GREEN + "File sent.")
                    except Exception as e:
                        print(Fore.RED + f"Error: {e}")
                else:
                    print(Fore.RED + "File not found.")
                await asyncio.sleep(1)
            elif cmd.startswith('edit '):
                parts = cmd.split(maxsplit=2)
                if len(parts) >= 3:
                    try:
                        idx = int(parts[1])
                        new_text = parts[2]
                        if idx in self.msg_id_map:
                            msg_id = self.msg_id_map[idx]
                            msg = await self.client.get_messages(self.current_chat, ids=msg_id)
                            if msg and msg[0].out:
                                await self.client.edit_message(self.current_chat, msg_id, new_text)
                                print(Fore.GREEN + "Message edited.")
                            else:
                                print(Fore.RED + "Cannot edit others' messages.")
                        else:
                            print(Fore.RED + "Invalid message index.")
                    except ValueError:
                        print(Fore.RED + "Invalid number.")
                else:
                    print(Fore.RED + "Usage: edit <num> <new text>")
                await asyncio.sleep(1)
            elif cmd.startswith('del '):
                parts = cmd.split()
                if len(parts) == 2:
                    try:
                        idx = int(parts[1])
                        if idx in self.msg_id_map:
                            msg_id = self.msg_id_map[idx]
                            msg = await self.client.get_messages(self.current_chat, ids=msg_id)
                            if msg:
                                # Ask for revocation (delete for everyone)
                                rev = await ainput(Fore.YELLOW + "Delete for everyone? (y/n): ")
                                revoke = rev.lower() == 'y'
                                await self.client.delete_messages(self.current_chat, [msg_id], revoke=revoke)
                                print(Fore.GREEN + "Message deleted.")
                            else:
                                print(Fore.RED + "Message not found.")
                        else:
                            print(Fore.RED + "Invalid index.")
                    except ValueError:
                        print(Fore.RED + "Invalid number.")
                await asyncio.sleep(1)
            elif cmd.startswith('forward '):
                # forward <num> to <target>
                parts = cmd.split(maxsplit=4)
                if len(parts) >= 4 and parts[2] == 'to':
                    try:
                        idx = int(parts[1])
                        target = parts[3]
                        if idx in self.msg_id_map:
                            msg_id = self.msg_id_map[idx]
                            # Resolve target entity
                            try:
                                target_entity = await self.client.get_entity(target)
                                await self.client.forward_messages(target_entity, [msg_id], self.current_chat)
                                print(Fore.GREEN + "Message forwarded.")
                            except Exception as e:
                                print(Fore.RED + f"Target error: {e}")
                        else:
                            print(Fore.RED + "Invalid index.")
                    except ValueError:
                        print(Fore.RED + "Invalid number.")
                else:
                    print(Fore.RED + "Usage: forward <num> to <chat>")
                await asyncio.sleep(1)
            elif cmd.startswith('save '):
                parts = cmd.split()
                if len(parts) == 2:
                    try:
                        idx = int(parts[1])
                        if idx in self.msg_id_map:
                            msg_id = self.msg_id_map[idx]
                            # Forward to Saved Messages (self)
                            await self.client.forward_messages('me', [msg_id], self.current_chat)
                            print(Fore.GREEN + "Message saved.")
                        else:
                            print(Fore.RED + "Invalid index.")
                    except ValueError:
                        print(Fore.RED + "Invalid number.")
                await asyncio.sleep(1)
            else:
                print(Fore.RED + "Unknown command.")
                await asyncio.sleep(1)

    async def create_group(self):
        """Create a new group."""
        clear_screen()
        print_header("CREATE GROUP")
        title = await ainput("Group title: ")
        if not title:
            return
        users_input = await ainput("Usernames to add (comma-separated, without @): ")
        usernames = [u.strip() for u in users_input.split(',') if u.strip()]
        try:
            # Resolve users to InputUser
            users = []
            for u in usernames:
                entity = await self.client.get_entity(u)
                users.append(entity)
            # Create group
            group = await self.client(functions.messages.CreateChatRequest(users, title))
            print(Fore.GREEN + "Group created successfully!")
        except Exception as e:
            print(Fore.RED + f"Error: {e}")
        await ainput(Fore.MAGENTA + "\nPress Enter...")

    async def create_channel(self):
        """Create a new channel."""
        clear_screen()
        print_header("CREATE CHANNEL")
        title = await ainput("Channel title: ")
        if not title:
            return
        desc = await ainput("Description (optional): ")
        public = await ainput("Public channel? (y/n): ")
        public = public.lower() == 'y'
        username = None
        if public:
            username = await ainput("Username (without @): ")
        try:
            # Create channel
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
        await ainput(Fore.MAGENTA + "\nPress Enter...")

    async def run(self):
        """Start the client and run the main loop."""
        await self.client.start()
        await self.login()
        await self.main_menu()

# ----------------------------- Entry Point ------------------------------
async def main():
    app = TelegramTUI()
    try:
        await app.run()
    except KeyboardInterrupt:
        print(f"\n{Fore.RED}Interrupted. Exiting.{Fore.RESET}")
    finally:
        await app.client.disconnect()

if __name__ == '__main__':
    asyncio.run(main())
