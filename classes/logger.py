class Logger:
    ERROR = "\033[91m"
    RESET = "\033[0m" # is this necessary?

    @classmethod
    def error(cls, message):
        print(f"{cls.ERROR}[ERROR] {message}")