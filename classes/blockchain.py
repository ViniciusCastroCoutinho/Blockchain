from .block import Block
from .transactions.transaction import Transaction
from .logger import Logger

class BlockChain:
    def __init__(self, difficulty_target=1):
        self.blocks = []
        self.indexes = {}
        self.difficulty_target = difficulty_target

        self.__genesis_block()

    def __str__(self):
        output = ""
        for block in self.blocks:
            output += "\n" + block.__str__()
        return output


    def __genesis_block(self):
        genesis_transaction = Transaction("genesis_block")
        genesis_block = Block(0, "", self.difficulty_target, genesis_transaction)

        self.blocks.append(genesis_block)

        assert self.is_first_block_valid(), "Failed to create genesis block"

    def get_last_block_hash(self):
        return self.blocks[-1].hash

    def create_block(self, transaction:Transaction):
        """
        This method is the correct way of creating a block, as it gets correct previous block hash, creates correct
        index, and uses blockchain's difficulty target. You can still create (risky) blocks by using Block class
        constructor.
        """
        index = len(self.blocks)
        previous_hash = self.get_last_block_hash()
        return Block(index, previous_hash, self.difficulty_target, transaction)

    def add(self, block:Block):
        """This method does NOT validate if the block/blockchain is valid"""
        self.blocks.append(block)

    # TODO error messages
    def is_first_block_valid(self):
        first_block = self.blocks[0]

        if first_block.index != 0:
            Logger.error("Genesis block did not have 0 as index")
            return False

        if first_block.previous_hash != "":
            Logger.error('Genesis block did not have "" as previous hash')
            return False

        if not first_block.validate_hash():
            Logger.error('Genesis block did not have valid hash')
            return False

        return True

    # TODO error messages
    @staticmethod
    def is_block_valid(block:Block, previous_block:Block):
        """DON'T use this to check genesis block"""
        if block.previous_hash == "":
            return False

        if block.previous_hash != previous_block.hash:
            return False

        if block.index != previous_block.index + 1:
            Logger.error("Block index is not previous block index + 1")
            return False

        if not block.validate_hash():
            return False

        return True

    # TODO messages
    def is_blockchain_valid(self):
        if not self.is_first_block_valid():
            return False

        for i in range(1, len(self.blocks)):
            block = self.blocks[i]
            previous_block = self.blocks[i-1]

            if not self.is_block_valid(block, previous_block):
                return False

        return True