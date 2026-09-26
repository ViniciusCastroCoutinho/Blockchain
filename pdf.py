from reportlab.pdfgen import canvas
import os
import qrcode

def write_prescription(prescription_id, crm, cpf, prescription_body):
    filename = f'receita_{prescription_id}.pdf'
    document_title = title = 'Receita'

    body = [
        f"CRM: {crm}",
        f"CPF do paciente: {cpf}",
        *prescription_body.split("\\n")
    ]

    pdf = canvas.Canvas(filename)
    pdf.setTitle(document_title)

    pdf.setFont("Helvetica-Bold", 36)
    pdf.drawCentredString(300, 770, title)

    pdf.line(30, 710, 550, 710)

    text = pdf.beginText(40, 680)
    text.setFont("Courier", 18)

    for line in body:
        text.textLine(line)

    pdf.drawText(text)

    img = qrcode.make(f'{prescription_id}')
    img.save('qrcode.png')

    width = height = 250
    pdf.drawImage('qrcode.png', 10, 10, 10 + width, 10 + height, mask=[1, 254, 1, 254, 1, 254])
    pdf.showPage()

    os.remove("qrcode.png")

    pdf.save()

    return filename

