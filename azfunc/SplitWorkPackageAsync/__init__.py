import os
import tempfile
import logging
import asyncio
import json
import azure.functions as func
from azure.storage.blob import BlobServiceClient, BlobClient, ContainerClient

from azure.ai.formrecognizer import DocumentAnalysisClient
from azure.core.credentials import AzureKeyCredential
from timeit import default_timer
from PyPDF2 import PdfFileMerger, PdfFileReader
from shared_code.pdf_splitter import pdf_splitter
from shared_code.combine_results_pdfs import combine_results_pdfs

## This function calls the Forms Recognizer API then calls the write_output function
def analyze_form(form_client: DocumentAnalysisClient, model_id: str, input_form_dict: dict):
    input_form_path = input_form_dict['output_file_path']
    start = default_timer()
    logging.info(f"Submitting {input_form_path}")
    
    with open(input_form_path, "rb") as fd:
        form = fd.read()
    
    try:
        poller = form_client.begin_analyze_document(model=model_id, document=form)
        result = poller.result()
        total = default_timer() - start
        logging.info(f"Completed {input_form_path}: in {round(total, 2)} secs")
    
    except Exception as e:
        total = default_timer() - start
        logging.warning(round(total, 2), e)
        return False

    input_form_dict['form_recognizer_results'] = result.to_dict()
    return input_form_dict

## main function
async def main(myblob: func.InputStream):
    ## Set up some temporary storage  
    file_name = myblob.name.split('/')[-1]
    work_package_name_clean = "".join([c for c in file_name if c.isalpha() or c.isdigit()  or c==' ']).rstrip().replace(' ', '_')

    temporary_path = os.path.join(tempfile.gettempdir())
    
    ## Make a directory for split PDF files
    split_pdf_temp_path = os.path.join(temporary_path, work_package_name_clean, 'split_pdfs')
    if not os.path.exists(split_pdf_temp_path):
        os.makedirs(split_pdf_temp_path, exist_ok=True)


    logging.info("Splitting the PDFs")
    ## Split the PDFs
    page_list = pdf_splitter(file_name=myblob.name, input_blob_bytes=myblob.read(), output_directory=split_pdf_temp_path, pdf_label=work_package_name_clean)

    logging.info("Creating the FR client")
    
    ## Create the FR client
    endpoint = os.environ['FORM_RECOGNIZER_ENDPOINT']
    apim_key = os.environ['FORM_RECOGNIZER_API_KEY']
    model_id = os.environ['FORM_RECOGNIZER_MODEL_ID']
    document_key_field = os.environ['document_key_field']
    
    credential = AzureKeyCredential(apim_key)
    form_recognizer_client = DocumentAnalysisClient(endpoint, credential)

    ## Get the FR results asynchronously
    logging.info("Doing all the async stuff")
    eventloop = asyncio.get_event_loop()
    eventloop.set_debug(True)

    tasks = [
        eventloop.run_in_executor(
            None, 
            analyze_form, 
            form_recognizer_client, 
            model_id, 
            input_form_dict
            )
            for input_form_dict in page_list
        ]

    form_results = [finished_task for finished_task in await asyncio.gather(*tasks)]

    ## Combine the PDFs into workcards
    logging.info('Combining the work cards into their own PDFS')
    
    ## Make a directory for the combined workcards
    work_card_pdfs_temp_path = os.path.join(temporary_path, work_package_name_clean, 'work_card_pdfs')
    if not os.path.exists(work_card_pdfs_temp_path):
        os.makedirs(work_card_pdfs_temp_path, exist_ok=True)    

    results_by_task_card = combine_results_pdfs(form_results=form_results, pdf_output_path=work_card_pdfs_temp_path, document_key_field=document_key_field)
    
    ## Upload finished PDFs to blob
    blob_conn_string = os.environ['ADLS_GEN2_CONNECTION_STRING']
    container = os.environ['STORAGE_OUTPUT_TARGET_CONTAINER']
    blob_service_client = BlobServiceClient.from_connection_string(blob_conn_string)

    for key, item in results_by_task_card.items():
        merger = PdfFileMerger()

        for page in item['doc_names']:    
            merger.append(PdfFileReader(page))
        
        output_file_path = os.path.join(work_card_pdfs_temp_path, f"{key}.pdf")    
        merger.write(output_file_path)
        
        blob_name = "/".join(['processed', work_package_name_clean, f"{key}.pdf"])
        blob_client = blob_service_client.get_blob_client(container=container, blob=blob_name)
        if not blob_client.exists():
            logging.info(f'Uploading blob {blob_name}')
            with open(output_file_path, 'rb') as f:
                blob_client.upload_blob(f)

    summary_file_blob_path = "/".join(['processed', work_package_name_clean, f'{work_package_name_clean}_results.json'])
    blob_client = blob_service_client.get_blob_client(container=container, blob=summary_file_blob_path)
    
    if not blob_client.exists():
        blob_client.upload_blob(json.dumps(results_by_task_card))