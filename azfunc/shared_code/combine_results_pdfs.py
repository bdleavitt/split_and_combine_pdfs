import os
from PyPDF2 import PdfFileMerger, PdfFileReader

def combine_results_pdfs(form_results: dict, pdf_output_path: str, document_key_field: str):
    ## parse the results
    parsed_results = {}
    for page in form_results:
        work_card_number = page['form_recognizer_results']['documents'][0]['fields'][document_key_field]['value']
        parsed_results[work_card_number] = {"contained_pages": [], "doc_names": [], "work_package" : "", "form_recognizer_results": []}

    for page in form_results:
        work_card_number = page['form_recognizer_results']['documents'][0]['fields'][document_key_field]['value']
        parsed_results[work_card_number]['contained_pages'].append({page['page']: page['form_recognizer_results']})
        parsed_results[work_card_number]['doc_names'].append(page['output_file_path'])

    ## combine into PDFs
    for key, item in parsed_results.items():
        merger = PdfFileMerger()

        for page in item['doc_names']:    
            merger.append(PdfFileReader(page))
        
        output_file_path = os.path.join(pdf_output_path, f"{key}.pdf")    
        merger.write(output_file_path)
        
        ## append the local storage path to the results dict
        parsed_results[key]['output_file_path'] = output_file_path
        
        ## TODO: upload into blob storage
        ## TODO: add the blob URL to the results output

    return(parsed_results)