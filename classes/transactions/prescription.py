from .transaction import Transaction

class Prescription(Transaction):
    """Transaction that stores that a prescription was written by a doctor"""
    def __init__(self, prescription_id, crm, cpf, pdf_link="https://drive.google.com/file/d/1gpGXopy8nISsZKmDW-l5ERmCJ5SVyUUX/view?usp=sharing"):
        super().__init__("Prescription")
        self.__prescription_id = prescription_id
        self.__crm = crm
        self.__cpf = cpf
        self.__pdf = pdf_link

    def to_dict(self):
        return {
            "transaction":self.__transaction,
            "prescription_id":self.__prescription_id,
            "crm":self.__crm,
            "cpf":self.__cpf,
            "pdf":self.__pdf,
        }

    def get_prescription_id(self):
        return self.__prescription_id

    def get_crm(self):
        return self.__crm

    def get_cpf(self):
        return self.__cpf

    def get_pdf(self):
        return self.__pdf
