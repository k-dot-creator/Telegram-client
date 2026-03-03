import os
import time
import sys
import json
import requests
import re
import random
from typing import List
from colorama import init, Fore, Back, Style, just_fix_windows_console

# Initialize colorama for cross-platform color support
init(autoreset=True)

# ASCII Art Banners with colors
BANNER = Fore.CYAN + r"""
  _____                     _ _   ___
 / ____|                   (_) | |__ \
| |  __  ___ _ __ ___ _ __  _| |_   ) |
| | |_ |/ _ \ '__/ _ \ '_ \| | __| / /
| |__| |  __/ | |  __/ | | | | |_ / /_
 \_____|\___|_|  \___|_| |_|_|\__|____|
""" + Style.RESET_ALL

NAME_BANNER = Fore.GREEN + r"""
 _   _  _____  _____  _    _ ______ _______
| \ | |/ ____|/ ____|| |  | |  ____|__   __|
|  \| | (___ | |  __ | |__| | |__     | |
| . ` |\___ \| | |_ ||  __  |  __|    | |
| |\  |____) | |__| || |  | | |____   | |
|_| \_|_____/ \_____||_|  |_|______|  |_|
""" + Style.RESET_ALL

os.system("clear")
def print_colored(text, color=Fore.WHITE, style=Style.NORMAL):
    """Print colored text"""
    print(f"{style}{color}{text}{Style.RESET_ALL}")

def print_header(text):
    """Print header text"""
    print(f"\n{Fore.YELLOW}{Style.BRIGHT}{'='*60}")
    print(f"{text}")
    print(f"{'='*60}{Style.RESET_ALL}")

def print_success(text):
    """Print success message"""
    print(f"{Fore.GREEN}[✓] {text}{Style.RESET_ALL}")

def print_error(text):
    """Print error message"""
    print(f"{Fore.RED}[✗] {text}{Style.RESET_ALL}")

def print_info(text):
    """Print info message"""
    print(f"{Fore.CYAN}[i] {text}{Style.RESET_ALL}")

def print_warning(text):
    """Print warning message"""
    print(f"{Fore.YELLOW}[!] {text}{Style.RESET_ALL}")

def print_prompt(text):
    """Print prompt message"""
    print(f"{Fore.MAGENTA}[?] {text}{Style.RESET_ALL}")

# Simulated loading animation with colors
def loading_animation(duration=2, message="Loading"):
    animation = "|/-\\"
    idx = 0
    start_time = time.time()
    while time.time() - start_time < duration:
        print(f"\r{Fore.CYAN}[{animation[idx % len(animation)]}] {message}...{Style.RESET_ALL}", end="")
        sys.stdout.flush()
        time.sleep(0.1)
        idx += 1
    print()

# Parse markdown-like formatting in AI responses
def parse_markdown_response(text):
    """Parse markdown-like formatting and apply colors"""
    if not text:
        return text

    # Handle bold text **bold**
    text = re.sub(r'\*\*(.*?)\*\*', f'{Style.BRIGHT}{Fore.YELLOW}\\1{Style.RESET_ALL}', text)

    # Handle headers (lines starting with #)
    def header_replacer(match):
        level = len(match.group(1))
        text = match.group(2).strip()
        if level == 1:
            return f"\n{Fore.CYAN}{Style.BRIGHT}{'='*60}\n{text}\n{'='*60}{Style.RESET_ALL}\n"
        elif level == 2:
            return f"\n{Fore.GREEN}{Style.BRIGHT}{text}\n{'-'*len(text)}{Style.RESET_ALL}\n"
        else:
            return f"\n{Fore.BLUE}{Style.BRIGHT}{text}{Style.RESET_ALL}\n"

    text = re.sub(r'^(#{1,3})\s+(.+)$', header_replacer, text, flags=re.MULTILINE)

    # Handle code blocks ``` with re.DOTALL (corrected from DOTLINE)
    text = re.sub(r'```(.*?)```', f'{Fore.GREEN}\\1{Style.RESET_ALL}', text, flags=re.DOTALL)

    # Handle inline code `code`
    text = re.sub(r'`([^`]+)`', f'{Fore.GREEN}\\1{Style.RESET_ALL}', text)

    # Handle lists starting with - or *
    lines = text.split('\n')
    for i, line in enumerate(lines):
        stripped_line = line.lstrip()
        if stripped_line.startswith('- ') or stripped_line.startswith('* '):
            indent = len(line) - len(stripped_line)
            lines[i] = ' ' * indent + f"{Fore.MAGENTA}• {Fore.WHITE}{stripped_line[2:]}{Style.RESET_ALL}"
        elif re.match(r'^\s*\d+\.\s+', line):
            lines[i] = f"{Fore.CYAN}{line}{Style.RESET_ALL}"

    text = '\n'.join(lines)

    # Handle quotes (lines starting with >)
    text = re.sub(r'^>\s+(.+)$', f'{Fore.BLUE}│ \\1{Style.RESET_ALL}', text, flags=re.MULTILINE)

    return text

# Main Gemini AI tool using direct HTTP requests
class GeminiAITool:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.history = []
        self.model_name = None
        self.base_url = "https://generativelanguage.googleapis.com/v1beta"

    def list_models(self):
        """List available models to find the correct one"""
        url = f"{self.base_url}/models?key={self.api_key}"
        try:
            response = requests.get(url)
            if response.status_code == 200:
                models = response.json().get('models', [])
                # Find a suitable gemini model
                for model in models:
                    if 'gemini' in model['name'].lower() and 'generateContent' in model.get('supportedGenerationMethods', []):
                        self.model_name = model['name'].split('/')[-1]  # Extract model name
                        print_success(f"Using model: {self.model_name}")
                        return True
                # Fallback to first gemini model
                for model in models:
                    if 'gemini' in model['name'].lower():
                        self.model_name = model['name'].split('/')[-1]
                        print_success(f"Using model: {self.model_name}")
                        return True
                print_error("No suitable Gemini model found")
                return False
            else:
                print_error(f"Failed to list models: {response.status_code}")
                return False
        except Exception as e:
            print_error(f"Exception while listing models: {str(e)}")
            return False

    def send_prompt(self, prompt: str) -> str:
        if not self.model_name:
            if not self.list_models():
                return "[ERROR] Could not determine model to use"

        url = f"{self.base_url}/models/{self.model_name}:generateContent?key={self.api_key}"

        headers = {
            "Content-Type": "application/json"
        }

        data = {
            "contents": [{
                "parts": [{
                    "text": prompt
                }]
            }]
        }

        try:
            print_info("Sending request to Gemini API...")
            response = requests.post(url, headers=headers, json=data, timeout=30)

            if response.status_code == 200:
                result = response.json()
                # Parse JSON response
                if 'candidates' in result and result['candidates']:
                    candidate = result['candidates'][0]
                    if 'content' in candidate and 'parts' in candidate['content']:
                        parts = candidate['content']['parts']
                        if parts:
                            ai_response = parts[0].get('text', '')

                            # Store in history
                            self.history.append({
                                "prompt": prompt,
                                "response": ai_response,
                                "timestamp": time.time()
                            })

                            return ai_response

                print_warning("Unexpected response structure")
                return json.dumps(result, indent=2)

            else:
                error_msg = f"API Error: {response.status_code}"
                try:
                    error_json = response.json()
                    if 'error' in error_json:
                        error_msg += f" - {error_json['error'].get('message', 'Unknown error')}"
                except:
                    error_msg += f" - {response.text[:100]}"

                return f"[ERROR] {error_msg}"

        except requests.exceptions.ConnectionError:
            return "[ERROR] Connection failed. Check your internet connection."
        except requests.exceptions.Timeout:
            return "[ERROR] Request timeout. The server took too long to respond."
        except Exception as e:
            return f"[ERROR] Failed to generate response: {str(e)}"

    def show_history(self):
        if not self.history:
            print_info("No conversation history")
            return

        print_header("CONVERSATION HISTORY")
        for i, entry in enumerate(self.history, 1):
            print(f"\n{Fore.YELLOW}{'-'*40} Prompt {i} {'-'*40}{Style.RESET_ALL}")
            print(f"{Fore.CYAN}Q:{Style.RESET_ALL} {entry['prompt'][:150]}{'...' if len(entry['prompt']) > 150 else ''}")
            print(f"{Fore.GREEN}A:{Style.RESET_ALL} {entry['response'][:150]}{'...' if len(entry['response']) > 150 else ''}")
            print(f"{Fore.BLUE}Time:{Style.RESET_ALL} {time.strftime('%H:%M:%S', time.localtime(entry['timestamp']))}")

    def clear_history(self):
        self.history = []
        print_success("Conversation history cleared")

# Encoder/Decoder section
def encode_string(text: str) -> str:
    """Simple encoding function to make it difficult to decode"""
    encoded = ""
    for char in text:
        encoded += str(ord(char) * 3 + 7) + " "
    return encoded.strip()

def decode_string(encoded: str) -> str:
    """Decoder function"""
    try:
        numbers = encoded.split(" ")
        decoded = ""
        for num in numbers:
            if num:
                decoded += chr(int((int(num) - 7) / 3))
        return decoded
    except:
        return "[ERROR] Decoding failed"

def display_response_menu():
    """Display menu after getting a response"""
    print(f"\n{Fore.CYAN}{Style.BRIGHT}{'*'*60}")
    print("RESPONSE MENU")
    print(f"{'*'*60}{Style.RESET_ALL}")
    print(f"{Fore.GREEN}[1]{Style.RESET_ALL} Ask follow-up question")
    print(f"{Fore.YELLOW}[2]{Style.RESET_ALL} Start new conversation")
    print(f"{Fore.BLUE}[3]{Style.RESET_ALL} View conversation history")
    print(f"{Fore.MAGENTA}[4]{Style.RESET_ALL} Main menu")
    print(f"{Fore.RED}[5]{Style.RESET_ALL} Exit")
    print(f"{Fore.CYAN}{Style.BRIGHT}{'*'*60}{Style.RESET_ALL}")

# Main execution
def main():
    # Display banners
    print(BANNER)
    print(NAME_BANNER)
    print_header("TOOL MADE BY ROBBIEJR")
    print_success("Join @ROBBIEJRTECH")

    # Get API key from user
    print_prompt("Enter your Gemini API key (press Enter to skip): ")
    api_key = input(f"{Fore.GREEN}>>> {Style.RESET_ALL}").strip()

    if not api_key:
        print_warning("No API key provided. Using demo mode (responses will be simulated).")
        demo_mode = True
    else:
        demo_mode = False

    # Initialize tool
    print_info("Initializing Gemini AI Tool...")
    loading_animation(2, "Initializing")

    if demo_mode:
        tool = None
        print_success("Demo mode initialized successfully!")
    else:
        tool = GeminiAITool(api_key)
        if not tool.list_models():
            print_error("Failed to initialize. Check your API key and network connection.")
            return
        print_success("Gemini AI Tool initialized successfully!")

    current_prompt = None
    follow_up_mode = False

    # Main interaction loop
    while True:
        if not follow_up_mode:
            print_header("MAIN MENU")
            print(f"{Fore.GREEN}[1]{Style.RESET_ALL} Send Prompt to Gemini")
            print(f"{Fore.YELLOW}[2]{Style.RESET_ALL} View Conversation History")
            print(f"{Fore.BLUE}[3]{Style.RESET_ALL} Clear History")
            print(f"{Fore.MAGENTA}[4]{Style.RESET_ALL} Encode Text")
            print(f"{Fore.CYAN}[5]{Style.RESET_ALL} Decode Text")
            print(f"{Fore.RED}[6]{Style.RESET_ALL} Exit")

            choice = input(f"\n{Fore.GREEN}[+] Select an option (1-6): {Style.RESET_ALL}").strip()
        else:
            display_response_menu()
            choice = input(f"\n{Fore.GREEN}[+] Select option (1-5): {Style.RESET_ALL}").strip()

        if choice == "1" or (follow_up_mode and choice == "1"):
            if follow_up_mode:
                prompt = input(f"\n{Fore.MAGENTA}[+] Follow-up question: {Style.RESET_ALL}")
                if not prompt:
                    print_warning("Empty prompt ignored")
                    continue
                # Combine with previous context for better follow-up
                if current_prompt:
                    enhanced_prompt = f"Previous question: {current_prompt}\n\nFollow-up: {prompt}"
                else:
                    enhanced_prompt = prompt
            else:
                prompt = input(f"\n{Fore.MAGENTA}[+] Enter your prompt: {Style.RESET_ALL}")
                if not prompt:
                    print_warning("Empty prompt ignored")
                    continue
                enhanced_prompt = prompt
                current_prompt = prompt

            if demo_mode:
                print_info("Processing in demo mode...")
                time.sleep(1)
                # Demo response
                demo_responses = [
                    f"This is a demo response to: **{prompt}**\n\nI can help you with various topics including:\n- Programming\n- Science\n- Mathematics\n- Creative writing\n\n*Try with a real API key for full Gemini AI capabilities!*",
                    f"**Demo Answer:**\n\nFor '{prompt}', I would typically provide a detailed response.\n\n```python\n# Example code snippet\nprint('Hello from Gemini AI!')\n```\n\n> Note: This is demo mode. Get an API key from Google AI Studio."
                ]
                response = random.choice(demo_responses)
            else:
                print_info("Processing your request...")
                response = tool.send_prompt(enhanced_prompt)

            # Display response with formatting
            print_header("GEMINI RESPONSE")
            formatted_response = parse_markdown_response(response)
            print(formatted_response)
            print_header("END OF RESPONSE")

            follow_up_mode = True

        elif choice == "2" or (follow_up_mode and choice == "3"):
            if tool:
                tool.show_history()
            elif demo_mode:
                print_info("History not available in demo mode")
            follow_up_mode = False

        elif choice == "3" and not follow_up_mode:
            if tool:
                confirm = input(f"{Fore.YELLOW}[!] Clear all history? (y/N): {Style.RESET_ALL}").strip().lower()
                if confirm == "y":
                    tool.clear_history()
                else:
                    print_info("History not cleared")
            else:
                print_info("History not available in demo mode")
            follow_up_mode = False

        elif choice == "4" and not follow_up_mode:
            text = input(f"\n{Fore.MAGENTA}[+] Enter text to encode: {Style.RESET_ALL}")
            if text:
                encoded = encode_string(text)
                print(f"{Fore.CYAN}[ENCODED]{Style.RESET_ALL} {encoded}")
            else:
                print_warning("Empty text ignored")
            follow_up_mode = False

        elif choice == "5" and not follow_up_mode:
            encoded_text = input(f"\n{Fore.MAGENTA}[+] Enter encoded text to decode: {Style.RESET_ALL}")
            if encoded_text:
                decoded = decode_string(encoded_text)
                print(f"{Fore.GREEN}[DECODED]{Style.RESET_ALL} {decoded}")
            else:
                print_warning("Empty text ignored")
            follow_up_mode = False

        elif choice == "6" or (follow_up_mode and choice == "5"):
            print_success("Exiting Gemini AI Tool. Goodbye!")
            break

        elif follow_up_mode and choice == "2":
            # Start new conversation
            current_prompt = None
            follow_up_mode = False
            print_success("Starting new conversation...")

        elif follow_up_mode and choice == "4":
            # Return to main menu
            follow_up_mode = False
            current_prompt = None
            print_success("Returning to main menu...")

        else:
            print_error("Invalid option selected")
            follow_up_mode = False

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(f"\n{Fore.YELLOW}\n[!] Program interrupted by user{Style.RESET_ALL}")
        sys.exit(0)
    except Exception as e:
        print_error(f"Unexpected error: {str(e)}")
        sys.exit(1)
