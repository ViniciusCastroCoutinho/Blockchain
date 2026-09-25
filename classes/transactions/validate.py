from .transaction import Transaction

class Validate(Transaction):
    def __init__(self, transaction_type: str):
        super().__init__(transaction_type)

    # TODO everything