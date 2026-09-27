class Transaction:
    """Base Transaction class. Not really used for anything"""
    def __init__(self, transaction_type):
        self.__transaction = transaction_type

    def to_dict(self):
        return {
            "transaction": self.__transaction
        }

    def get_transaction_type(self):
        return self.__transaction
