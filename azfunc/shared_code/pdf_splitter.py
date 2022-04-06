## Splits a multi-page PDF into one file per page. 
import os
import logging
from PyPDF2 import PdfFileReader, PdfFileWriter
from io import BytesIO

def pdf_splitter(file_name, input_blob_bytes, output_directory, pdf_label) -> list:
    logging.info(f'Splitting forms...')
    page_list = []
    
    pdf = PdfFileReader(BytesIO(input_blob_bytes))
    for page in range(pdf.getNumPages()):
        pdf_writer = PdfFileWriter()
        pdf_writer.addPage(pdf.getPage(page))
        output_directory_path = os.path.join(output_directory, pdf_label)

        if not os.path.exists(output_directory_path):
            os.makedirs(output_directory_path)

        output_filename = f'{pdf_label}_page_{page+1}.pdf'
        
        output_file_path = os.path.join(output_directory_path, output_filename)
        
        with open(output_file_path, 'wb') as out:
            pdf_writer.write(out)
        
        page_list.append({
            "work_package": file_name,
            "parent_pdf_label": pdf_label,
            "page": page+1,
            "output_file_name": output_filename,
            "output_file_path": output_file_path,                
        })
    return page_list
