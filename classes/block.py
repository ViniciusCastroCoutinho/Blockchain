import datetime
from .transactions.transaction import Transaction
from .logger import Logger
from hashlib import sha256

class Block:
    def __init__(self, index, previous_hash, difficulty_target, transaction=None):
        self.index = index
        self.timestamp = str(datetime.datetime.now())
        self.transaction = transaction if transaction else Transaction("EMPTY TRANSACTION")
        self.previous_hash = previous_hash
        self.nonce = 0
        self.hash = self.calculate_hash()
        self.__pow(difficulty_target)

        self.validate_hash()

    def __str__(self):
        return f"Bloco #{self.index}: hash='{self.hash}' previous_hash='{self.previous_hash}' nonce='{self.nonce}' timestamp='{self.timestamp}' transaction='{self.transaction.transaction}'"


    def calculate_hash(self):
        input_string = str(self.index) + self.timestamp + self.previous_hash + str(self.nonce) + str(self.transaction.to_dict())

        return sha256(input_string.encode("utf-8")).hexdigest()


    def __pow(self, difficulty_target: int):
        # proof of work
        while self.hash[:difficulty_target].count("0") != difficulty_target:
            self.nonce += 1
            self.hash = self.calculate_hash()

    def validate_hash(self):
        if not self.calculate_hash() == self.hash:
            Logger.error(f"Hash calculado '{self.calculate_hash()}' não foi igual ao hash armazenado no bloco '{self.hash}'")
            return False
        return True