import contextlib
import io
import os
import re
import tempfile

import streamlit as st

from classes import BlockChain, Block
from classes.transactions import Prescription, Validate, Transaction
import pdf
import google_drive

ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


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


st.set_page_config(page_title="Blockchain de Prescrições", layout="wide")
init_state()

blockchain: BlockChain = st.session_state.blockchain

st.title("💊 Blockchain de Prescrições")
st.caption(
    "Interface web para o sistema que antes só rodava pelo terminal (cli.py). "
    "Todas as ações disponíveis lá também estão aqui."
)

tab_medico, tab_farmacia, tab_blockchain = st.tabs(
    ["🩺 Médico", "🏪 Farmácia", "⛓️ Blockchain (admin/teste)"]
)

# ----------------------------------------------------------------------
# Médico: escrever prescrição
# ----------------------------------------------------------------------
with tab_medico:
    st.subheader("Escrever prescrição")

    with st.form("form_prescricao"):
        crm = st.text_input("CRM do médico")
        cpf = st.text_input("CPF do paciente")
        corpo = st.text_area(
            "Texto da prescrição",
            help="Use \\n para separar linhas, igual ao CLI original.",
        )
        enviar = st.form_submit_button("Emitir prescrição")

    if enviar:
        if not crm or not cpf or not corpo:
            st.warning("Preencha CRM, CPF e o texto da prescrição.")
        else:
            prescription_id = st.session_state.auto_prescription_id

            filepath = pdf.write_prescription(
                prescription_id, crm, cpf, corpo, output_dir=st.session_state.workdir
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

            prescription = Prescription(prescription_id, crm, cpf, pdf_link)
            new_block = blockchain.create_block(prescription)
            _, add_log = run_captured(blockchain.add, new_block)

            st.session_state.auto_prescription_id += 1

            st.success(f"Prescrição #{prescription_id} registrada no bloco #{new_block.get_index()}.")
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

    with st.form("form_validacao"):
        cnpj = st.text_input("CNPJ da farmácia")
        prescription_id_val = st.number_input(
            "Id da prescrição a validar", min_value=0, step=1, format="%d"
        )
        validar = st.form_submit_button("Validar prescrição")

    if validar:
        if not cnpj:
            st.warning("Preencha o CNPJ da farmácia.")
        else:
            transaction = Validate(int(prescription_id_val), cnpj)
            new_block = blockchain.create_block(transaction)
            _, add_log = run_captured(blockchain.add, new_block)

            resultado = new_block.get_transaction().get_validation()
            if resultado:
                st.success(f"Prescrição #{int(prescription_id_val)} validada com sucesso (bloco #{new_block.get_index()}).")
            else:
                st.error(
                    f"Prescrição #{int(prescription_id_val)} NÃO foi validada "
                    "(não existe ou já havia sido validada antes)."
                )
            show_log(add_log)

# ----------------------------------------------------------------------
# Blockchain: mostrar, checar validade, adicionar bloco manual (opções de teste do CLI)
# ----------------------------------------------------------------------
with tab_blockchain:
    st.subheader("Mostrar blockchain")
    blocks = blockchain.get_blocks()
    st.write(f"Total de blocos: **{len(blocks)}**")

    for block in blocks:
        transaction = block.get_transaction()
        with st.expander(f"Bloco #{block.get_index()} — {transaction.get_transaction_type()}"):
            st.json(
                {
                    "index": block.get_index(),
                    "timestamp": block.get_timestamp(),
                    "hash": block.get_hash(),
                    "previous_hash": block.get_previous_hash(),
                    "nonce": block.get_nonce(),
                    "transaction": transaction.to_dict(),
                }
            )

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
        st.rerun()

