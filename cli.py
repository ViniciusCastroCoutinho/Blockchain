from classes import BlockChain, Block
from classes.transactions import Prescription, Validate, Transaction


def assure_answer(start_num, end_num):
    answer = input()

    choices = [str(number) for number in range(start_num, end_num + 1)]
    while answer not in choices:
        print("Invalid answer\n")
        answer = input()

    return answer

def blockchain_options(number, end_number):
    # print("Blockchain options")
    print()
    print(f"{number}. Show blockchain")
    print(f"{number + 1}. Is blockchain valid?")
    print(f"{number + 2}. [TEST] Add block to blockchain\n")

def blockchain_ifs(answer, number, end_number):
    if answer == str(number):
        print(blockchain, "\n")
    if answer == str(number + 1):
        blockchain.is_blockchain_valid()
    if answer == str(number + 2):
        add_block()

def add_block():
    global blockchain
    print("Block index:")
    index = int(input())
    print("Previous hash:")
    previous_hash = input()
    print("Difficulty target:")
    difficulty_target = int(input())
    print("Transaction type:")
    print("1. Prescription")
    print("2. Validate")
    print("3. Base transaction")
    answer = assure_answer(1, 3)

    if answer == "1":
        print("Prescription id:")
        prescription_id = int(input()) # NOTE change this if prescription_id type changes
        print("CRM:")
        crm = input()
        print("CPF:")
        cpf = input()
        print("PDF link:")
        pdf = input()
        transaction = Prescription(prescription_id, crm, cpf, pdf)
    elif answer == "2":
        print("Prescription id:")
        prescription_id = int(input())  # NOTE change this if prescription_id type changes
        print("Drugstore's CNPJ:")
        cnpj = input()
        print("Is valid (0 or 1):")
        valid = bool(int(input()))
        transaction = Validate(prescription_id, cnpj, valid)
    else:
        print("Write anything:")
        anything = input()
        transaction = Transaction(anything)

    block = Block(index, previous_hash, difficulty_target, transaction)
    blockchain.add(block)

def doctor_or_drugstore():
    true = True
    while true:
        print("Is user doctor or drugstore?")
        print("1. Doctor")
        print("2. Drugstore")
        blockchain_options(3, 5)
        print("6. Leave")

        answer = assure_answer(1, 6)

        if answer == "1":
            doctor()
        elif answer == "2":
            drugstore()
        elif answer == "6":
            true = False
        else:
            blockchain_ifs(answer, 3, 5)

def doctor():
    print("What is your CRM?")
    crm = input()

    true = True
    while true:
        print("What do you want to do?")
        print("1. Write prescription")
        blockchain_options(2, 4)
        print("5. Go back")
        answer = assure_answer(1, 5)

        if answer == "1":
            write_prescription(crm)
        elif answer == "5":
            true = False
        else:
            blockchain_ifs(answer, 2, 4)

def drugstore():
    print("What is your CNPJ?")
    cnpj = input()

    true = True
    while true:
        print("What do you want to do?")
        print("1. Validate prescription")
        blockchain_options(2, 4)
        print("5. Go back")
        answer = assure_answer(1, 5)

        if answer == "1":
            validate_prescription(cnpj)
        elif answer == "5":
            true = False
        else:
            blockchain_ifs(answer, 2, 4)

def write_prescription(crm):
    global auto_prescription_id, blockchain
    print("What is the CPF of pacient?")
    cpf = input()

    print("Write your prescription")
    prescription = input()
    # pdf_link = generate_pdf(crm, cpf, prescription) # TODO

    prescription = Prescription(auto_prescription_id, crm, cpf)
    auto_prescription_id += 1

    blockchain.add(blockchain.create_block(prescription))

def validate_prescription(cnpj):
    print("What is the id of the prescription to be validated?")
    prescription_id = int(input())  # NOTE change this if prescription_id type changes

    transaction = Validate(prescription_id, cnpj)
    blockchain.add(blockchain.create_block(transaction))

if __name__ == "__main__":
    auto_prescription_id = 0
    blockchain = BlockChain()

    doctor_or_drugstore()
