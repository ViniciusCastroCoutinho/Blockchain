class Transaction:
    def __init__(self, transaction_type):
        self.transaction = transaction_type

    def to_dict(self):
        return {
            "transaction": self.transaction
        }