class Logger:
    ERROR = "\033[91m"
    INVALID = "\033[91m"
    VALID = "\033[92m"
    RESET = "\033[0m"

    @classmethod
    def info(cls, message):
        print(f"[INFO] {message} {cls.RESET}")

    @classmethod
    def error(cls, message):
        print(f"{cls.ERROR}[ERROR] {message} {cls.RESET}")

    @classmethod
    def invalid(cls, message):
        print(f"{cls.INVALID}[INVALID] {message} {cls.RESET}")

    @classmethod
    def valid(cls, message):
        print(f"{cls.VALID}[VALID] {message} {cls.RESET}")