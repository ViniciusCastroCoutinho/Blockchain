import datetime
from .transactions import Transaction, Validate, Prescription
from .logger import Logger
from hashlib import sha256

class Block:
    def __init__(self, index, previous_hash, difficulty_target, transaction=None):
        self.__index = index
        self.__timestamp = str(datetime.datetime.now())
        self.__transaction = transaction if transaction else Transaction("EMPTY TRANSACTION")
        self.__previous_hash = previous_hash
        self.__nonce = 0
        self.__hash = self.calculate_hash()
        self.__pow(difficulty_target)

        self.validate_hash()

    def __str__(self):
        return f"Bloco #{self.__index}: hash='{self.__hash}' previous_hash='{self.__previous_hash}' nonce='{self.__nonce}' timestamp='{self.__timestamp}' transaction='{self.__transaction.get_transaction_type()}'"

    def get_hash(self):
        return self.__hash

    def get_index(self):
        return self.__index

    def get_previous_hash(self):
        return self.__previous_hash

    def get_transaction(self) -> Transaction|Validate|Prescription:
        return self.__transaction

    def calculate_hash(self):
        input_string = str(self.__index) + self.__timestamp + self.__previous_hash + str(self.__nonce) + str(self.__transaction.to_dict())

        return sha256(input_string.encode("utf-8")).hexdigest()

    def __pow(self, difficulty_target: int):
        # proof of work
        while self.__hash[:difficulty_target].count("0") != difficulty_target:
            self.__nonce += 1
            self.__hash = self.calculate_hash()

    def validate_hash(self):
        if not self.calculate_hash() == self.__hash:
            Logger.error(f"Hash calculado '{self.calculate_hash()}' não foi igual ao hash armazenado no bloco '{self.__hash}'")
            return False
        return True