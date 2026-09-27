import contextlib
import html
import io
import os
import re
import tempfile

import streamlit as st

from classes import BlockChain, Block, Registry, RegistryError, PrescriptionContract
from classes.transactions import Prescription, Validate, Transaction
from classes.documents import (
    normalize_crm, normalize_cpf, normalize_cnpj,
    format_cpf, format_cnpj,
    complete_cpf, complete_cnpj, generate_cpf, generate_cnpj,
)
import pdf
import google_drive

ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
REGISTRY_PATH = os.path.join(BASE_DIR, "data", "registry.json")


def strip_ansi(text: str) -> str:
    return ANSI_RE.sub("", text)


def run_captured(func, *args, **kwargs):
    """Runs func, capturing anything it printed (Logger uses print()) so it can be shown in the UI."""
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        result = func(*args, **kwargs)
    return result, strip_ansi(buffer.getvalue()).strip()


def show_log(log_text: str):
    if log_text:
        st.code(log_text, language=None)


def init_state():
    if "blockchain" not in st.session_state:
        st.session_state.blockchain = BlockChain(difficulty_target=1)
    if "auto_prescription_id" not in st.session_state:
        st.session_state.auto_prescription_id = 0
    if "workdir" not in st.session_state:
        st.session_state.workdir = tempfile.mkdtemp(prefix="prescricoes_")
    if "registry" not in st.session_state:
        # cadastros persistidos em data/registry.json (sobrevivem entre sessões)
        st.session_state.registry = Registry(REGISTRY_PATH)
    if "contract" not in st.session_state:
        st.session_state.contract = PrescriptionContract(st.session_state.registry)


st.set_page_config(page_title="Blockchain de Prescrições", layout="wide")
init_state()

blockchain: BlockChain = st.session_state.blockchain
registry: Registry = st.session_state.registry
contract: PrescriptionContract = st.session_state.contract

st.title("💊 Blockchain de Prescrições")

tab_medico, tab_farmacia, tab_blockchain, tab_cadastro = st.tabs(
    ["🩺 Médico", "🏪 Farmácia", "⛓️ Blockchain (admin/teste)", "🗂️ Cadastro (Admin)"]
)


def reject(reason: str):
    st.error(f"❌ **Recusada pelo contrato:** {reason}. Nenhum bloco foi minerado nem adicionado à cadeia.")


# ----------------------------------------------------------------------
# Médico: escrever prescrição
# ----------------------------------------------------------------------
with tab_medico:
    st.subheader("Escrever prescrição")
    st.caption(
        f"Médicos cadastrados: **{registry.count(Registry.DOCTORS)}** · "
        f"Pacientes cadastrados: **{registry.count(Registry.PATIENTS)}** — gerencie na aba 🗂️ Cadastro."
    )

    with st.form("form_prescricao"):
        crm = st.text_input("CRM do médico", placeholder="ex.: 12345/AM")
        cpf = st.text_input("CPF do paciente", placeholder="ex.: 529.982.247-25")
        corpo = st.text_area(
            "Texto da prescrição",
            help="Use \\n para separar linhas, igual ao CLI original.",
        )
        enviar = st.form_submit_button("Emitir prescrição")

    if enviar:
        # 1) SMART CONTRACT: require(CRM cadastrado) + require(CPF válido e cadastrado)
        #    ANTES de gerar PDF, subir para o Drive ou minerar qualquer coisa.
        if not contract.authorize_prescription(crm, cpf, corpo):
            reject(contract.last_reason())
        else:
            crm_n, cpf_n = normalize_crm(crm), normalize_cpf(cpf)
            prescription_id = st.session_state.auto_prescription_id

            filepath = pdf.write_prescription(
                prescription_id, crm_n, format_cpf(cpf_n), corpo, output_dir=st.session_state.workdir
            )

            pdf_link = None
            upload_log = ""
            try:
                pdf_link, upload_log = run_captured(google_drive.upload, filepath)
            except Exception as e:
                st.warning(
                    f"Não foi possível subir o PDF para o Google Drive ({e}). "
                    "Configure credentials.env (veja credentials_template.env) para habilitar o upload. "
                    "O link da prescrição vai usar o caminho local do arquivo por enquanto."
                )
                pdf_link = filepath

            # 2) BLOCKCHAIN: só agora o bloco é criado (PoW) e adicionado
            prescription = Prescription(prescription_id, crm_n, cpf_n, pdf_link)
            new_block = blockchain.create_block(prescription)
            _, add_log = run_captured(blockchain.add, new_block)
            contract.record_receipt(new_block)

            st.session_state.auto_prescription_id += 1

            medico = registry.get(Registry.DOCTORS, crm_n)["nome"]
            paciente = registry.get(Registry.PATIENTS, cpf_n)["nome"]
            st.success(
                f"✅ Aceita pelo contrato. Prescrição #{prescription_id} ({medico} → {paciente}) "
                f"registrada no bloco #{new_block.get_index()}."
            )
            st.write(f"**Link/arquivo do PDF:** {pdf_link}")
            if os.path.isfile(filepath):
                with open(filepath, "rb") as f:
                    st.download_button(
                        "Baixar PDF gerado", f, file_name=os.path.basename(filepath)
                    )
            show_log(upload_log)
            show_log(add_log)

# ----------------------------------------------------------------------
# Farmácia: validar prescrição
# ----------------------------------------------------------------------
with tab_farmacia:
    st.subheader("Validar prescrição")
    st.caption(
        f"Farmácias autorizadas: **{registry.count(Registry.PHARMACIES)}** — gerencie na aba 🗂️ Cadastro."
    )

    with st.form("form_validacao"):
        cnpj = st.text_input("CNPJ da farmácia", placeholder="ex.: 11.222.333/0001-81")
        prescription_id_val = st.number_input(
            "Id da prescrição a validar", min_value=0, step=1, format="%d"
        )
        validar = st.form_submit_button("Validar prescrição")

    if validar:
        pid = int(prescription_id_val)
        # 1) SMART CONTRACT: require(CNPJ válido e autorizado), depois a regra
        #    "prescrição existe / ainda não validada" (checagem read-only da cadeia)
        if not contract.authorize_validation(cnpj, pid, blockchain):
            reject(contract.last_reason())
        else:
            # 2) BLOCKCHAIN: minera; validate_prescription() continua rodando on-chain no add()
            transaction = Validate(pid, normalize_cnpj(cnpj))
            new_block = blockchain.create_block(transaction)
            _, add_log = run_captured(blockchain.add, new_block)
            contract.record_receipt(new_block)

            if new_block.get_transaction().get_validation():
                farmacia = registry.get(Registry.PHARMACIES, normalize_cnpj(cnpj))["nome"]
                st.success(
                    f"✅ Prescrição #{pid} validada por {farmacia} (bloco #{new_block.get_index()})."
                )
            else:
                st.error(f"Prescrição #{pid} NÃO foi validada pela regra on-chain.")
            show_log(add_log)


# ----------------------------------------------------------------------
# Helpers de visualização
# ----------------------------------------------------------------------
CARD_CSS = """
<style>
.bc-card{border:2px solid;border-radius:10px;padding:10px 14px;}
.bc-ok{border-color:#16a34a;background:rgba(22,163,74,.07);}
.bc-bad{border-color:#dc2626;background:rgba(220,38,38,.08);}
.bc-title{font-weight:700;font-size:1.02rem;display:flex;flex-wrap:wrap;gap:6px;align-items:center;margin-bottom:4px;}
.bc-row{font-size:.88rem;margin:2px 0;}
.bc-mono{font-family:ui-monospace,Menlo,Consolas,monospace;font-size:.76rem;opacity:.85;word-break:break-all;}
.badge{display:inline-block;padding:1px 9px;border-radius:999px;font-size:.72rem;font-weight:600;border:1px solid;white-space:nowrap;}
.b-green{color:#15803d;border-color:#16a34a;background:rgba(22,163,74,.12);}
.b-red{color:#b91c1c;border-color:#dc2626;background:rgba(220,38,38,.12);}
.b-amber{color:#b45309;border-color:#d97706;background:rgba(217,119,6,.12);}
.b-gray{color:#6b7280;border-color:#9ca3af;background:rgba(156,163,175,.12);}
.b-blue{color:#1d4ed8;border-color:#3b82f6;background:rgba(59,130,246,.12);}
.bc-link{margin:0 0 0 28px;padding:6px 12px;border-left:3px solid;font-size:.78rem;}
.link-ok{border-color:#16a34a;color:#15803d;}
.link-bad{border-color:#dc2626;color:#b91c1c;font-weight:600;}
.link-gap{border-color:#9ca3af;color:#6b7280;border-left-style:dashed;}
.side-title{font-size:.8rem;font-weight:600;opacity:.75;margin:2px 0 4px;}
.side-item{border:1px solid rgba(128,128,128,.35);border-radius:8px;padding:5px 9px;margin-bottom:5px;font-size:.8rem;}
</style>
"""


def esc(value) -> str:
    return html.escape(str(value))


def short(h: str, n: int = 12) -> str:
    return f"{h[:n]}…" if h else "—"


def badge(text: str, color: str) -> str:
    return f'<span class="badge b-{color}">{esc(text)}</span>'


def silent(func, *args):
    return run_captured(func, *args)[0]


def integrity(blocks: list[Block]) -> list[dict]:
    """Checagem da camada de consenso, separada em 'hash íntegro' e 'ligação com o anterior'."""
    out = []
    for i, block in enumerate(blocks):
        hash_ok = silent(block.validate_hash)
        if i == 0:
            link_ok = block.get_index() == 0 and block.get_previous_hash() == ""
        else:
            prev = blocks[i - 1]
            link_ok = (
                block.get_previous_hash() == prev.get_hash()
                and block.get_index() == prev.get_index() + 1
            )
        out.append({"hash_ok": hash_ok, "link_ok": link_ok, "valid": hash_ok and link_ok})
    return out


def contract_badges(result: dict) -> str:
    status = result["status"]
    if status == "genesis":
        parts = [badge("Bloco gênese", "blue")]
    elif status == "accepted":
        parts = [badge("✔ Contrato: aceita", "green")]
    elif status == "rejected":
        parts = [badge(f"✖ Contrato: recusada — {result['reason']}", "red")]
    else:
        parts = [badge(f"⚠ {result['reason']}", "amber")]
    parts += [badge(f"⚠ {w}", "amber") for w in result["warnings"]]
    return " ".join(parts)


def tx_summary(tx) -> str:
    kind = tx.get_transaction_type()
    if kind == "Prescription":
        crm_v = tx.get_crm()
        cpf_v = tx.get_cpf()
        doc = registry.get(Registry.DOCTORS, crm_v)
        pat = registry.get(Registry.PATIENTS, cpf_v)
        return (
            f'<div class="bc-row">🧾 Receita <b>#{esc(tx.get_prescription_id())}</b></div>'
            f'<div class="bc-row">🩺 CRM <b>{esc(crm_v)}</b>{" · " + esc(doc["nome"]) if doc else ""}</div>'
            f'<div class="bc-row">👤 CPF <b>{esc(format_cpf(cpf_v))}</b>{" · " + esc(pat["nome"]) if pat else ""}</div>'
        )
    if kind == "Validate":
        cnpj_v = tx.get_drugstore_id()
        ph = registry.get(Registry.PHARMACIES, cnpj_v)
        return (
            f'<div class="bc-row">🧾 Valida receita <b>#{esc(tx.get_prescription_id())}</b> → '
            f'{"✔ valid=True" if tx.get_validation() else "✖ valid=False"}</div>'
            f'<div class="bc-row">🏪 CNPJ <b>{esc(format_cnpj(cnpj_v))}</b>{" · " + esc(ph["nome"]) if ph else ""}</div>'
        )
    return f'<div class="bc-row">📦 {esc(kind)}</div>'


def block_card(block: Block, check: dict, result: dict) -> str:
    tx = block.get_transaction()
    state = "bc-ok" if check["valid"] else "bc-bad"
    hash_badge = badge("🔒 Hash íntegro", "green") if check["hash_ok"] else badge("🔓 Hash adulterado", "red")
    return (
        f'<div class="bc-card {state}">'
        f'<div class="bc-title">#{block.get_index()} · {esc(tx.get_transaction_type())} {hash_badge} {contract_badges(result)}</div>'
        f"{tx_summary(tx)}"
        f'<div class="bc-mono">hash: {esc(block.get_hash())}</div>'
        f'<div class="bc-mono">nonce: {block.get_nonce()} · {esc(block.get_timestamp())}</div>'
        f"</div>"
    )


def link_connector(block: Block, previous: Block, check: dict) -> str:
    if check["link_ok"]:
        return (
            f'<div class="bc-link link-ok">↓ #{block.get_index()}.previous_hash = '
            f'#{previous.get_index()}.hash ({esc(short(block.get_previous_hash()))}) ✔</div>'
        )
    return (
        f'<div class="bc-link link-bad">↓ ✖ ligação quebrada: #{block.get_index()}.previous_hash '
        f'({esc(short(block.get_previous_hash()))}) ≠ #{previous.get_index()}.hash ({esc(short(previous.get_hash()))})</div>'
    )


def related_panel(block: Block, blocks: list[Block]) -> str:
    """Coluna lateral: Validates de uma Prescription (via índice prescription_id), ou a receita de um Validate."""
    tx = block.get_transaction()
    kind = tx.get_transaction_type()
    if kind not in ("Prescription", "Validate"):
        return ""
    pid = tx.get_prescription_id()
    related = [blocks[i] for i in blockchain.get_indexes().get(pid, []) if i < len(blocks)]

    if kind == "Prescription":
        validations = [b for b in related if b.get_transaction().get_transaction_type() == "Validate"]
        items = "".join(
            f'<div class="side-item">{"✔" if b.get_transaction().get_validation() else "✖"} '
            f'Bloco #{b.get_index()} · CNPJ {esc(format_cnpj(b.get_transaction().get_drugstore_id()))} · '
            f'{"validada" if b.get_transaction().get_validation() else "recusada"}</div>'
            for b in validations
        ) or '<div class="side-item" style="opacity:.7">Nenhuma validação ainda — receita em aberto</div>'
        return f'<div class="side-title">Validações da receita #{esc(pid)}</div>{items}'

    origin = [b for b in related if b.get_transaction().get_transaction_type() == "Prescription"]
    if origin:
        o = origin[0]
        return (
            f'<div class="side-title">Receita validada</div>'
            f'<div class="side-item">🧾 Receita #{esc(pid)} no bloco #{o.get_index()} · CRM {esc(o.get_transaction().get_crm())}</div>'
        )
    return f'<div class="side-title">Receita</div><div class="side-item">✖ Receita #{esc(pid)} não existe na cadeia</div>'


def matches(block: Block, field: str, term: str) -> bool:
    tx = block.get_transaction()
    kind = tx.get_transaction_type()
    if kind not in ("Prescription", "Validate"):
        return False
    if field == "prescription_id":
        return term.isdigit() and tx.get_prescription_id() == int(term)
    if field == "CRM":
        return kind == "Prescription" and normalize_crm(term) in tx.get_crm()
    if field == "CPF":
        return kind == "Prescription" and normalize_cpf(term) in tx.get_cpf()
    if field == "CNPJ":
        return kind == "Validate" and normalize_cnpj(term) in tx.get_drugstore_id()
    return False


# ----------------------------------------------------------------------
# Blockchain: visualização em linha do tempo + ferramentas de teste
# ----------------------------------------------------------------------
with tab_blockchain:
    st.markdown(CARD_CSS, unsafe_allow_html=True)
    blocks = blockchain.get_blocks()
    checks = integrity(blocks)
    results = [contract.describe_block(b, blockchain) for b in blocks]
    rejections = contract.get_rejections()

    n_presc = sum(b.get_transaction().get_transaction_type() == "Prescription" for b in blocks)
    n_valid = sum(
        b.get_transaction().get_transaction_type() == "Validate" and b.get_transaction().get_validation()
        for b in blocks
    )
    chain_ok = all(c["valid"] for c in checks)

    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("Blocos", len(blocks))
    m2.metric("Prescrições", n_presc)
    m3.metric("Validações aceitas", n_valid)
    m4.metric("Recusas do contrato", len(rejections))
    m5.metric("Integridade da cadeia", "✅ válida" if chain_ok else "❌ inválida")

    st.subheader("Linha do tempo da blockchain")

    f1, f2 = st.columns([1, 3])
    campo = f1.selectbox("Buscar por", ["prescription_id", "CRM", "CNPJ", "CPF"])
    termo = f2.text_input(
        "Termo de busca",
        placeholder="deixe vazio para ver a cadeia inteira",
        help="Mostra o histórico completo (prescrição + validações) das receitas encontradas.",
    ).strip()

    if termo:
        pids = {b.get_transaction().get_prescription_id() for b in blocks if matches(b, campo, termo)}
        visible = [
            i for i, b in enumerate(blocks)
            if b.get_transaction().get_transaction_type() in ("Prescription", "Validate")
            and b.get_transaction().get_prescription_id() in pids
        ]
        st.caption(f"{len(visible)} bloco(s) encontrados para {campo} = “{termo}”.")
    else:
        visible = list(range(len(blocks)))

    if not visible:
        st.info("Nenhum bloco encontrado para esse filtro.")

    previous_shown = None
    for i in visible:
        block = blocks[i]
        if previous_shown is not None:
            if i == previous_shown + 1:
                st.markdown(link_connector(block, blocks[i - 1], checks[i]), unsafe_allow_html=True)
            else:
                hidden = i - previous_shown - 1
                st.markdown(
                    f'<div class="bc-link link-gap">⋮ {hidden} bloco(s) oculto(s) pelo filtro</div>',
                    unsafe_allow_html=True,
                )
        elif i > 0 and not termo:
            st.markdown(link_connector(block, blocks[i - 1], checks[i]), unsafe_allow_html=True)

        col_main, col_side = st.columns([3, 2])
        with col_main:
            st.markdown(block_card(block, checks[i], results[i]), unsafe_allow_html=True)
            with st.expander("JSON do bloco (avançado)"):
                st.json(
                    {
                        "index": block.get_index(),
                        "timestamp": block.get_timestamp(),
                        "hash": block.get_hash(),
                        "previous_hash": block.get_previous_hash(),
                        "nonce": block.get_nonce(),
                        "transaction": block.get_transaction().to_dict(),
                    }
                )
        with col_side:
            panel = related_panel(block, blocks)
            if panel:
                st.markdown(panel, unsafe_allow_html=True)
        previous_shown = i

    st.divider()

    st.subheader("🚫 Chamadas recusadas pelo contrato")
    st.caption(
        "Estas transações foram revertidas pelo contrato antes do proof-of-work — "
        "por isso não aparecem como blocos na linha do tempo acima."
    )
    shown_rejections = rejections
    if termo:
        def rejection_matches(r) -> bool:
            flat = normalize_cnpj(r["dados"])  # tira pontuação/espaços e põe em maiúsculas
            if campo == "prescription_id":
                return re.search(rf"PRESCRIPTION_ID={re.escape(termo)}(,|$)", flat) is not None
            prefix = campo.upper() + "="
            value = {"CRM": normalize_crm, "CPF": normalize_cpf, "CNPJ": normalize_cnpj}[campo](termo)
            return any(p.startswith(prefix) and value in p[len(prefix):] for p in flat.split(","))

        shown_rejections = [r for r in rejections if rejection_matches(r)]
    if shown_rejections:
        st.dataframe(list(reversed(shown_rejections)), use_container_width=True, hide_index=True)
    else:
        st.info("Nenhuma chamada recusada até agora.")

    st.divider()

    st.subheader("Verificar se a blockchain é válida")
    if st.button("Checar validade da blockchain"):
        valida, log = run_captured(blockchain.is_blockchain_valid)
        if valida:
            st.success("Blockchain válida ✅")
        else:
            st.error("Blockchain inválida ❌")
        show_log(log)

    st.divider()

    with st.expander("🧪 [TESTE] Simular adulteração de um bloco"):
        st.caption(
            "Altera o conteúdo da transação de um bloco já minerado, sem refazer o hash — "
            "é o que um atacante faria. O bloco deve ficar vermelho e a cadeia, inválida."
        )
        if len(blocks) < 2:
            st.info("Adicione ao menos um bloco além do gênese para testar.")
        else:
            alvo = st.number_input(
                "Índice do bloco a adulterar", min_value=1, max_value=len(blocks) - 1, step=1, format="%d"
            )
            if st.button("Adulterar transação"):
                tx = blocks[int(alvo)].get_transaction()
                kind = tx.get_transaction_type()
                # acesso direto aos atributos privados (name mangling) — só para teste
                if kind == "Prescription":
                    tx._Prescription__cpf = "00000000000"
                elif kind == "Validate":
                    tx._Validate__valid = not tx.get_validation()
                else:
                    tx._Transaction__transaction = f"{kind} (adulterado)"
                st.rerun()

    # st.subheader("Índices internos (prescription_id → blocos)")
    # st.json(blockchain.get_indexes())

    # st.divider()

    # st.subheader("[TESTE] Adicionar bloco manualmente")

    # tipo = st.selectbox("Tipo de transação", ["Prescription", "Validate"])

    # with st.form("form_bloco_manual"):

    #     m_index = next(reversed(blockchain.get_indexes())) + 2 if blockchain.get_indexes() else 1
    #     st.subheader(m_index)
    #     m_difficulty = 1
    #     col1, col2 = st.columns(2)
    #     with col1:
    #         # m_index = st.number_input("Índice do bloco", min_value=0, step=1, format="%d")
    #         m_previous_hash = st.text_input(
    #             "Hash anterior", value=blockchain.get_last_block_hash()
    #         )
    #     # with col2:
    #     #     m_difficulty = st.number_input(
    #     #         "Dificuldade (nº de zeros)",
    #     #         min_value=0,
    #     #         max_value=5,
    #     #         value=blockchain.get_difficulty_target(),
    #     #         step=1,
    #     #         format="%d",
    #     #     )

    #     if tipo == "Prescription":
    #         m_prescription_id = st.number_input("Prescription id", min_value=0, step=1, format="%d")
    #         m_crm = st.text_input("CRM")
    #         m_cpf = st.text_input("CPF")
    #         m_pdf = st.text_input("Link do PDF")
    #     elif tipo == "Validate":
    #         m_prescription_id = st.number_input("Prescription id", min_value=0, step=1, format="%d")
    #         m_cnpj = st.text_input("CNPJ da farmácia")
    #         m_valid = st.checkbox("Já nasce validado?")
    #     else:
    #         m_conteudo = st.text_input("Conteúdo (tipo da transação base)")

    #     criar_bloco = st.form_submit_button("Criar e adicionar bloco")

    # if criar_bloco:
    #     if tipo == "Prescription":
    #         transacao_manual = Prescription(int(m_prescription_id), m_crm, m_cpf, m_pdf)
    #     elif tipo == "Validate":
    #         transacao_manual = Validate(int(m_prescription_id), m_cnpj, m_valid)

    #     try:
    #         bloco_manual = Block(int(m_index), m_previous_hash, int(m_difficulty), transacao_manual)
    #         _, log = run_captured(blockchain.add, bloco_manual)
    #         st.success(f"Bloco #{bloco_manual.get_index()} criado e adicionado.")
    #         show_log(log)
    #     except Exception as e:
    #         st.error(f"Não foi possível criar o bloco: {e}")

    # st.divider()
    if st.button("🗑️ Reiniciar blockchain (nova blockchain vazia)"):
        st.session_state.blockchain = BlockChain(difficulty_target=1)
        st.session_state.auto_prescription_id = 0
        contract.reset_history()
        st.rerun()


# ----------------------------------------------------------------------
# Cadastro (Admin): o "banco de dados confiável" que o contrato consulta
# ----------------------------------------------------------------------
SAMPLE_DATA = {
    Registry.DOCTORS: [("Dra. Ana Souza", "12345/AM"), ("Dr. Carlos Lima", "67890/AM")],
    Registry.PATIENTS: [("João Pereira", complete_cpf("529982247")), ("Maria Oliveira", complete_cpf("123456789"))],
    Registry.PHARMACIES: [("Farmácia Central", complete_cnpj("112223330001")), ("Drogaria Manaus", complete_cnpj("123456780001"))],
}

CATEGORY_UI = {
    Registry.DOCTORS: {"label": "Médicos", "doc": "CRM", "add": registry.add_doctor, "fmt": str,
                       "placeholder": "ex.: 12345/AM", "empty": "Nenhum médico cadastrado."},
    Registry.PATIENTS: {"label": "Pacientes", "doc": "CPF", "add": registry.add_patient, "fmt": format_cpf,
                        "placeholder": "ex.: 529.982.247-25", "empty": "Nenhum paciente cadastrado."},
    Registry.PHARMACIES: {"label": "Farmácias", "doc": "CNPJ", "add": registry.add_pharmacy, "fmt": format_cnpj,
                          "placeholder": "ex.: 11.222.333/0001-81", "empty": "Nenhuma farmácia cadastrada."},
}

with tab_cadastro:
    st.subheader("Cadastro de médicos, pacientes e farmácias autorizados")
    st.caption(
        "Simula as bases oficiais (CFM e Receita Federal), já que o projeto não usa APIs do governo. "
        "O smart contract só aceita CRM, CPF e CNPJ que estiverem aqui. "
        f"Os dados ficam salvos em `{os.path.relpath(REGISTRY_PATH, BASE_DIR)}`."
    )

    a1, a2, _ = st.columns([1, 1, 3])
    if a1.button("📥 Carregar dados de exemplo"):
        added = 0
        for category, rows in SAMPLE_DATA.items():
            for name, doc in rows:
                try:
                    CATEGORY_UI[category]["add"](name, doc)
                    added += 1
                except RegistryError:
                    pass  # já cadastrado
        st.toast(f"{added} cadastro(s) de exemplo adicionados.")
        st.rerun()
    if a2.button("🧹 Limpar todos os cadastros"):
        registry.clear()
        st.rerun()

    with st.expander("🎲 Gerar CPF/CNPJ válidos para teste"):
        st.caption("Documentos aleatórios com dígito verificador correto (não pertencem a ninguém real).")
        g1, g2 = st.columns(2)
        g1.code(format_cpf(generate_cpf()), language=None)
        g2.code(format_cnpj(generate_cnpj()), language=None)
        st.button("Gerar outros")

    sub_tabs = st.tabs([
        f"{icon} {CATEGORY_UI[c]['label']} ({registry.count(c)})"
        for icon, c in zip(["🩺", "👤", "🏪"], Registry.CATEGORIES)
    ])

    for category, sub_tab in zip(Registry.CATEGORIES, sub_tabs):
        ui = CATEGORY_UI[category]
        key_field = Registry.KEY_FIELD[category]
        with sub_tab:
            with st.form(f"form_add_{category}", clear_on_submit=True):
                c1, c2 = st.columns(2)
                nome = c1.text_input("Nome")
                doc = c2.text_input(ui["doc"], placeholder=ui["placeholder"])
                if st.form_submit_button(f"Cadastrar {ui['label'][:-1].lower()}"):
                    try:
                        key = ui["add"](nome, doc)
                        st.success(f"{nome.strip()} cadastrado(a) com {ui['doc']} {ui['fmt'](key)}.")
                    except RegistryError as e:
                        st.error(str(e))

            rows = registry.list(category)
            if not rows:
                st.info(ui["empty"])
            else:
                h1, h2, h3, h4 = st.columns([3, 3, 2, 1.3])
                h1.markdown("**Nome**")
                h2.markdown(f"**{ui['doc']}**")
                h3.markdown("**Cadastrado em**")
                h4.markdown("**Ação**")
                for row in rows:
                    r1, r2, r3, r4 = st.columns([3, 3, 2, 1.3])
                    r1.write(row["nome"])
                    r2.code(ui["fmt"](row[key_field]), language=None)
                    r3.write(row["cadastrado_em"])
                    if r4.button("Revogar", key=f"rm_{category}_{row[key_field]}"):
                        registry.remove(category, row[key_field])
                        st.rerun()
