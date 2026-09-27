"""
Cadastro local de médicos, pacientes e farmácias autorizados.

Faz o papel do "banco de dados confiável" que, num sistema real, seriam as
bases do CFM (CRM) e da Receita Federal (CPF/CNPJ). Como o projeto não
integra com APIs do governo, esses dados são mantidos pela aba "Cadastro
(Admin)" e, opcionalmente, persistidos num JSON simples.

É o *estado* que o PrescriptionContract consulta.
"""
import datetime
import json
import os

from .documents import (
    normalize_crm, is_crm_format,
    normalize_cpf, is_cpf_format, is_cpf_checksum_valid,
    normalize_cnpj, is_cnpj_format, is_cnpj_checksum_valid,
)


class RegistryError(ValueError):
    """Erro ao cadastrar (dado inválido ou duplicado)."""


class Registry:
    DOCTORS = "medicos"
    PATIENTS = "pacientes"
    PHARMACIES = "farmacias"
    CATEGORIES = (DOCTORS, PATIENTS, PHARMACIES)

    # nome do campo-chave de cada categoria
    KEY_FIELD = {DOCTORS: "crm", PATIENTS: "cpf", PHARMACIES: "cnpj"}

    def __init__(self, path: str | None = None):
        """
        path: arquivo JSON para persistir os cadastros entre sessões.
              Se None, os cadastros vivem só em memória.
        """
        self.__path = path
        self.__data: dict[str, dict[str, dict]] = {c: {} for c in self.CATEGORIES}
        if path and os.path.isfile(path):
            self.load()

    # ------------------------------------------------------------------
    # Persistência
    # ------------------------------------------------------------------
    def get_path(self):
        return self.__path

    def load(self):
        with open(self.__path, "r", encoding="utf-8") as f:
            raw = json.load(f)
        self.__data = {c: dict(raw.get(c, {})) for c in self.CATEGORIES}

    def save(self):
        if not self.__path:
            return
        os.makedirs(os.path.dirname(os.path.abspath(self.__path)), exist_ok=True)
        with open(self.__path, "w", encoding="utf-8") as f:
            json.dump(self.__data, f, ensure_ascii=False, indent=2)

    # ------------------------------------------------------------------
    # Escrita
    # ------------------------------------------------------------------
    def __add(self, category: str, name: str, key: str):
        name = (name or "").strip()
        if not name:
            raise RegistryError("Informe o nome.")
        if key in self.__data[category]:
            existing = self.__data[category][key]["nome"]
            raise RegistryError(f"{self.KEY_FIELD[category].upper()} {key} já está cadastrado ({existing}).")

        self.__data[category][key] = {
            "nome": name,
            self.KEY_FIELD[category]: key,
            "cadastrado_em": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        self.save()
        return key

    def add_doctor(self, name: str, crm: str) -> str:
        if not is_crm_format(crm):
            raise RegistryError("CRM inválido: use apenas letras/números (ex.: 12345/AM).")
        return self.__add(self.DOCTORS, name, normalize_crm(crm))

    def add_patient(self, name: str, cpf: str) -> str:
        if not is_cpf_format(cpf):
            raise RegistryError("CPF inválido: precisa ter 11 dígitos.")
        if not is_cpf_checksum_valid(cpf):
            raise RegistryError("CPF inválido: dígito verificador não confere.")
        return self.__add(self.PATIENTS, name, normalize_cpf(cpf))

    def add_pharmacy(self, name: str, cnpj: str) -> str:
        if not is_cnpj_format(cnpj):
            raise RegistryError("CNPJ inválido: precisa ter 14 caracteres (12 + 2 dígitos verificadores).")
        if not is_cnpj_checksum_valid(cnpj):
            raise RegistryError("CNPJ inválido: dígito verificador não confere.")
        return self.__add(self.PHARMACIES, name, normalize_cnpj(cnpj))

    def remove(self, category: str, key: str) -> bool:
        """Revoga a autorização (remove do cadastro). Retorna True se existia."""
        removed = self.__data[category].pop(key, None) is not None
        if removed:
            self.save()
        return removed

    def clear(self):
        self.__data = {c: {} for c in self.CATEGORIES}
        self.save()

    # ------------------------------------------------------------------
    # Leitura
    # ------------------------------------------------------------------
    def has_doctor(self, crm) -> bool:
        return normalize_crm(crm) in self.__data[self.DOCTORS]

    def has_patient(self, cpf) -> bool:
        return normalize_cpf(cpf) in self.__data[self.PATIENTS]

    def has_pharmacy(self, cnpj) -> bool:
        return normalize_cnpj(cnpj) in self.__data[self.PHARMACIES]

    def get(self, category: str, key: str) -> dict | None:
        return self.__data[category].get(key)

    def list(self, category: str) -> list[dict]:
        return sorted(self.__data[category].values(), key=lambda r: r["nome"].lower())

    def count(self, category: str) -> int:
        return len(self.__data[category])
