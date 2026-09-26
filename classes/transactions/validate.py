from .transaction import Transaction

class Validate(Transaction):
    def __init__(self, prescription_id):
        super().__init__("Validate")
        self.__prescription_id = prescription_id
        self.__valid = None

    def to_dict(self):
        return {
            "transaction":self.__transaction,
            "prescription_id":self.__prescription_id,
            "valid":self.__valid
        }

    def get_prescription_id(self):
        return self.__prescription_id

    def get_validation(self):
        return self.__valid

    def set_validation(self, value:bool):
        self.__valid = value