"""
Camada de SMART CONTRACT (regra de negócio / aplicação).

Separação de responsabilidades:

    | Camada                 | Onde                      | O que faz                                  |
    |------------------------|---------------------------|--------------------------------------------|
    | Blockchain (consenso)  | block.py / blockchain.py  | hash, PoW, sequência e integridade da cadeia|
    | Smart contract         | contract.py (este módulo) | valida CRM, CPF e CNPJ ANTES de minerar     |

O contrato tem duas "portas de entrada" que compartilham o mesmo estado
(o Registry com os cadastros autorizados):

    1. Médico   -> authorize_prescription(crm, cpf)      -> só então minera o bloco Prescription
    2. Farmácia -> authorize_validation(cnpj, ...)       -> só então minera o bloco Validate

Se alguma regra falha, a chamada é recusada ANTES do proof-of-work — nenhum
bloco é criado, nada muda na cadeia. É o equivalente ao require() do Solidity,
que reverte a transação sem gastar gas e sem alterar estado.

A regra "prescrição existe / ainda não foi validada" continua morando em
BlockChain.validate_prescription() (enforcement on-chain). O contrato apenas
faz uma checagem read-only dela antes de minerar (como um eth_call), para
que essa recusa também não gere bloco.
"""
import datetime

from .registry import Registry
from .documents import (
    normalize_crm, is_crm_format,
    normalize_cpf, is_cpf_format, is_cpf_checksum_valid,
    normalize_cnpj, is_cnpj_format, is_cnpj_checksum_valid,
)
from .transactions import Prescription, Validate


class ContractViolation(Exception):
    """Lançada por require() quando uma regra do contrato não é satisfeita (revert)."""

    def __init__(self, code: str, reason: str):
        super().__init__(reason)
        self.code = code
        self.reason = reason


# Códigos de recusa -> mensagem exibida na interface
REASONS = {
    "CRM_EMPTY": "CRM não informado",
    "CRM_FORMAT": "CRM com formato inválido",
    "CRM_NOT_REGISTERED": "CRM não cadastrado",
    "CPF_EMPTY": "CPF não informado",
    "CPF_FORMAT": "CPF com formato inválido (precisa de 11 dígitos)",
    "CPF_CHECKSUM": "CPF com dígito verificador inválido",
    "CPF_NOT_REGISTERED": "CPF não cadastrado",
    "CNPJ_EMPTY": "CNPJ não informado",
    "CNPJ_FORMAT": "CNPJ com formato inválido (precisa de 14 caracteres)",
    "CNPJ_CHECKSUM": "CNPJ com dígito verificador inválido",
    "CNPJ_NOT_AUTHORIZED": "CNPJ não autorizado",
    "BODY_EMPTY": "Texto da receita vazio",
    "PRESCRIPTION_NOT_FOUND": "Prescrição não existe",
    "PRESCRIPTION_ALREADY_VALIDATED": "Prescrição já foi validada",
}


class PrescriptionContract:
    def __init__(self, registry: Registry):
        self.__registry = registry
        self.last_error: ContractViolation | None = None
        # "recibos" das transações aceitas, por índice de bloco (como um tx receipt)
        self.__receipts: dict[int, dict] = {}
        # chamadas recusadas (revertidas) — não viraram bloco
        self.__rejections: list[dict] = []

    # ------------------------------------------------------------------
    # Infra
    # ------------------------------------------------------------------
    def get_registry(self) -> Registry:
        return self.__registry

    @staticmethod
    def require(condition: bool, code: str):
        """Igual ao require() do Solidity: se a condição falha, reverte."""
        if not condition:
            raise ContractViolation(code, REASONS[code])

    def __run(self, checks) -> bool:
        """Executa uma função de checagem; guarda o motivo em last_error se falhar."""
        try:
            checks()
            self.last_error = None
            return True
        except ContractViolation as e:
            self.last_error = e
            return False

    def last_reason(self) -> str | None:
        return self.last_error.reason if self.last_error else None

    # ------------------------------------------------------------------
    # Regras individuais (lançam ContractViolation)
    # ------------------------------------------------------------------
    def _require_crm(self, crm):
        self.require(bool(str(crm or "").strip()), "CRM_EMPTY")
        self.require(is_crm_format(crm), "CRM_FORMAT")
        # CRM não tem checksum público: a única validação possível é o cadastro
        self.require(self.__registry.has_doctor(crm), "CRM_NOT_REGISTERED")

    def _require_cpf(self, cpf):
        self.require(bool(str(cpf or "").strip()), "CPF_EMPTY")
        self.require(is_cpf_format(cpf), "CPF_FORMAT")
        self.require(is_cpf_checksum_valid(cpf), "CPF_CHECKSUM")
        self.require(self.__registry.has_patient(cpf), "CPF_NOT_REGISTERED")

    def _require_cnpj(self, cnpj):
        self.require(bool(str(cnpj or "").strip()), "CNPJ_EMPTY")
        self.require(is_cnpj_format(cnpj), "CNPJ_FORMAT")
        self.require(is_cnpj_checksum_valid(cnpj), "CNPJ_CHECKSUM")
        self.require(self.__registry.has_pharmacy(cnpj), "CNPJ_NOT_AUTHORIZED")

    def _require_prescription_can_be_validated(self, blockchain, prescription_id):
        exists, validated = self.prescription_state(blockchain, prescription_id)
        self.require(exists, "PRESCRIPTION_NOT_FOUND")
        self.require(not validated, "PRESCRIPTION_ALREADY_VALIDATED")

    # ------------------------------------------------------------------
    # API pública pedida: validate_* -> bool
    # ------------------------------------------------------------------
    def validate_crm(self, crm) -> bool:
        return self.__run(lambda: self._require_crm(crm))

    def validate_cpf(self, cpf) -> bool:
        """Formato (11 dígitos) + dígito verificador + cadastro local."""
        return self.__run(lambda: self._require_cpf(cpf))

    def validate_cnpj(self, cnpj) -> bool:
        """Formato (14 caracteres) + dígito verificador + cadastro local."""
        return self.__run(lambda: self._require_cnpj(cnpj))

    # ------------------------------------------------------------------
    # Portas de entrada: authorize_* -> bool (chamadas ANTES de minerar)
    # ------------------------------------------------------------------
    def authorize_prescription(self, crm, cpf, body: str | None = None) -> bool:
        """
        Porta do médico. Chamar antes de blockchain.create_block(Prescription).
        Se retornar False, NÃO minerar; o motivo fica em last_reason().
        """
        def checks():
            self._require_crm(crm)
            self._require_cpf(cpf)
            if body is not None:
                self.require(bool(body.strip()), "BODY_EMPTY")

        ok = self.__run(checks)
        if not ok:
            self.__log_rejection("Prescription", {"crm": crm, "cpf": cpf})
        return ok

    def authorize_validation(self, cnpj, prescription_id=None, blockchain=None) -> bool:
        """
        Porta da farmácia. Chamar antes de blockchain.create_block(Validate).

        1ª regra: CNPJ autorizado (formato + DV + cadastro).
        2ª regra (se blockchain e prescription_id forem passados): checagem
        read-only de que a prescrição existe e ainda não foi validada — a mesma
        regra que BlockChain.validate_prescription() aplica on-chain.
        """
        def checks():
            self._require_cnpj(cnpj)
            if blockchain is not None and prescription_id is not None:
                self._require_prescription_can_be_validated(blockchain, prescription_id)

        ok = self.__run(checks)
        if not ok:
            self.__log_rejection("Validate", {"cnpj": cnpj, "prescription_id": prescription_id})
        return ok

    # ------------------------------------------------------------------
    # Execução completa (autoriza -> minera -> adiciona). Lança ContractViolation.
    # ------------------------------------------------------------------
    def submit_prescription(self, blockchain, prescription_id, crm, cpf, pdf_link, body: str | None = None):
        if not self.authorize_prescription(crm, cpf, body):
            raise self.last_error
        transaction = Prescription(prescription_id, normalize_crm(crm), normalize_cpf(cpf), pdf_link)
        block = blockchain.create_block(transaction)   # PoW só acontece aqui, depois do require
        blockchain.add(block)
        self.record_receipt(block)
        return block

    def submit_validation(self, blockchain, prescription_id, cnpj):
        if not self.authorize_validation(cnpj, prescription_id, blockchain):
            raise self.last_error
        transaction = Validate(prescription_id, normalize_cnpj(cnpj))
        block = blockchain.create_block(transaction)
        blockchain.add(block)                           # validate_prescription() roda aqui (regra on-chain)
        self.record_receipt(block)
        return block

    # ------------------------------------------------------------------
    # Consultas read-only sobre a cadeia
    # ------------------------------------------------------------------
    @staticmethod
    def prescription_state(blockchain, prescription_id) -> tuple[bool, bool]:
        """(existe?, já validada?) — lê a cadeia sem alterar nada."""
        exists = validated = False
        for block in blockchain.get_blocks():
            tx = block.get_transaction()
            kind = tx.get_transaction_type()
            if kind not in ("Prescription", "Validate") or tx.get_prescription_id() != prescription_id:
                continue
            if kind == "Prescription":
                exists = True
            elif exists and tx.get_validation():
                validated = True
        return exists, validated

    # ------------------------------------------------------------------
    # Recibos e histórico de recusas (para a visualização)
    # ------------------------------------------------------------------
    def record_receipt(self, block):
        tx = block.get_transaction()
        accepted = not (tx.get_transaction_type() == "Validate" and not tx.get_validation())
        self.__receipts[block.get_index()] = {
            "status": "accepted" if accepted else "rejected",
            "reason": None if accepted else "Recusada pela regra on-chain (validate_prescription)",
        }

    def __log_rejection(self, operation: str, data: dict):
        self.__rejections.append({
            "horario": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "operacao": operation,
            "dados": ", ".join(f"{k}={v}" for k, v in data.items() if v not in (None, "")),
            "codigo": self.last_error.code,
            "motivo": self.last_error.reason,
        })

    def get_rejections(self) -> list[dict]:
        return list(self.__rejections)

    def reset_history(self):
        self.__receipts.clear()
        self.__rejections.clear()

    def describe_block(self, block, blockchain=None) -> dict:
        """
        Resultado do contrato para um bloco já na cadeia, usado nos badges da UI:
            status:   "genesis" | "accepted" | "rejected" | "unchecked"
            reason:   motivo da recusa (se houver)
            warnings: identidades que foram revogadas DEPOIS do bloco ser aceito
        """
        tx = block.get_transaction()
        kind = tx.get_transaction_type()
        receipt = self.__receipts.get(block.get_index())

        if block.get_index() == 0:
            return {"status": "genesis", "reason": None, "warnings": []}

        if kind == "Validate" and not tx.get_validation():
            reason = receipt["reason"] if receipt and receipt.get("reason") else "Prescrição inexistente ou já validada"
            return {"status": "rejected", "reason": reason, "warnings": []}

        if kind not in ("Prescription", "Validate"):
            return {"status": "unchecked", "reason": "Transação fora do contrato", "warnings": []}

        warnings = []
        if kind == "Prescription":
            if not self.__registry.has_doctor(tx.get_crm()):
                warnings.append("CRM revogado/ausente no cadastro atual")
            if not self.__registry.has_patient(tx.get_cpf()):
                warnings.append("CPF ausente no cadastro atual")
        else:
            if not self.__registry.has_pharmacy(tx.get_drugstore_id()):
                warnings.append("CNPJ revogado/ausente no cadastro atual")

        if receipt is None:
            # bloco que entrou sem passar pelo contrato (ex.: [TESTE] do CLI)
            return {"status": "unchecked", "reason": "Não passou pelo contrato", "warnings": warnings}
        return {"status": receipt["status"], "reason": receipt["reason"], "warnings": warnings}
