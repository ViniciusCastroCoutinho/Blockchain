from .transaction import Transaction

class Validate(Transaction):
    def __init__(self, prescription_id, drugstore_id, valid=False):
        super().__init__("Validate")
        self.__prescription_id = prescription_id
        self.__drugstore_id = drugstore_id
        self.__valid = valid

    def to_dict(self):
        return {
            "transaction":self.get_transaction_type(),
            "prescription_id":self.__prescription_id,
            "drugstore_id":self.__drugstore_id,
            "valid":self.__valid
        }

    def get_prescription_id(self):
        return self.__prescription_id

    def get_drugstore_id(self):
        return self.__drugstore_id

    def get_validation(self):
        return self.__valid

    def set_validation(self, value:bool):
        self.__valid = value
