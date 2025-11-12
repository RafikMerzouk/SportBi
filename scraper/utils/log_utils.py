# scraper/log_utils.py

RESET = "\033[0m"
BOLD = "\033[1m"
BLINK = "\033[5m"

FG_RED = "\033[31m"
FG_GREEN = "\033[32m"
FG_YELLOW = "\033[33m"
FG_BLUE = "\033[34m"
FG_MAGENTA = "\033[35m"
FG_CYAN = "\033[36m"
FG_WHITE = "\033[37m"

TAG_INFO = f"{BOLD}{FG_CYAN}[INFO]{RESET}"
TAG_OK = f"{BOLD}{FG_GREEN}[OK]{RESET}"
TAG_WARN = f"{BOLD}{FG_YELLOW}[WARN]{RESET}"
TAG_ERR = f"{BOLD}{FG_RED}[ERR]{RESET}"
TAG_START = f"{BOLD}{FG_MAGENTA}{BLINK}[START]{RESET}"
TAG_DONE = f"{BOLD}{FG_GREEN}{BLINK}[DONE]{RESET}"


def log_info(msg: str):
    print(f"{TAG_INFO} {msg}{RESET}")


def log_ok(msg: str):
    print(f"{TAG_OK} {msg}{RESET}")


def log_warn(msg: str):
    print(f"{TAG_WARN} {msg}{RESET}")


def log_err(msg: str):
    print(f"{TAG_ERR} {msg}{RESET}")


def log_start(msg: str):
    print(f"{TAG_START} {BOLD}{msg}{RESET}")


def log_done(msg: str):
    print(f"{TAG_DONE} {BOLD}{msg}{RESET}")
