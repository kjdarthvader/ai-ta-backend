import os
from pathlib import Path
from re import L, T
from tempfile import TemporaryFile
from typing import Any, Dict, List, Union
from xml.dom.minidom import Document  # PDF to text

import boto3
import fitz
import supabase
from dotenv import load_dotenv
from flask import Flask, jsonify, request
from flask.json import jsonify
from flask_cors import CORS
from langchain import text_splitter
from langchain.document_loaders import TextLoader
from langchain.embeddings import HuggingFaceEmbeddings, OpenAIEmbeddings
from langchain.schema import Document
from langchain.text_splitter import (CharacterTextSplitter, NLTKTextSplitter,
                                     RecursiveCharacterTextSplitter,
                                     SpacyTextSplitter)
from langchain.vectorstores import Pinecone, Qdrant
from qdrant_client import QdrantClient
from regex import F
from sqlalchemy import JSON

# load API keys from globally-availabe .env file
load_dotenv(dotenv_path='../.env', override=True)


class Ingest():
  """
  Contains all methods for building and using vector databases.
  """

  def __init__(self):
    """
    Initialize AWS S3, Qdrant, and Supabase.
    """

    # vector DB
    self.qdrant_client = QdrantClient(
        url=os.environ['QDRANT_URL'],
        api_key=os.environ['QDRANT_API_KEY'],
    )
    self.vectorstore = Qdrant(client=qdrant_client,
                              collection_name=os.environ['QDRANT_COLLECTION_NAME'],
                              embedding_function=OpenAIEmbeddings())

    # S3
    self.s3_client = boto3.client(
          's3',
          aws_access_key_id=os.environ['AWS_ACCESS_KEY_ID'],
          aws_secret_access_key=os.environ['AWS_SECRET_ACCESS_KEY'],
          # aws_session_token=,  # Comment this line if not using temporary credentials
      )

    # Create a Supabase client
    self.supabase_client = supabase.create_client(os.environ.get('SUPABASE_URL'), os.environ.get('SUPABASE_KEY'))
    
    return None

  def read_PDF(self, pdf_tmpfile, s3_pdf_path: str) -> List[Document]:
    """
    Both OCR the PDF, and split the text into chunks. Returns chunks as List[Document].
      LangChain `Documents` have .metadata and .page_content attributes.
    Be sure to use TemporaryFile() to avoid memory leaks!
    """
    ### READ OCR of PDF
    pdf_pages_OCRed: List[Dict] = []
    for i, page in enumerate(fitz.open(pdf_tmpfile)):
      text = page.get_text().encode("utf8").decode('ascii', errors='ignore')  # get plain text (is in UTF-8)
      pdf_pages_OCRed.append(dict(text=text,
                          page_number=i,
                          textbook_name=Path(s3_pdf_path).name))
    print(len(pdf_pages_OCRed))
    metadatas = [dict(page_number=page['page_number'], textbook_name=page['textbook_name']) for page in pdf_pages_OCRed]
    pdf_texts = [page['text'] for page in pdf_pages_OCRed]
    assert len(metadatas) == len(pdf_texts), 'must have equal number of pages and metadata objects'

    #### SPLIT TEXTS
    # good examples here: https://langchain.readthedocs.io/en/latest/modules/utils/combine_docs_examples/textsplitter.html
    text_splitter = RecursiveCharacterTextSplitter.from_tiktoken_encoder(
      chunk_size=1000,
      chunk_overlap=150,
      separators=". ", # try to split on sentences... 
    )
    texts: List[Document] = text_splitter.create_documents(texts=pdf_texts, metadatas=metadatas)

    def remove_small_contexts(texts: List[Document]) -> List[Document]:
      # Remove TextSplit contexts with fewer than 50 chars.
      return [doc for doc in texts if len(doc.page_content) > 50]

    return remove_small_contexts(texts=texts)

  def ingest_PDFs(self, s3_pdf_paths: Union[str, List[str]]): # str | List[str]
    """
    Main function. Ingests single PDF into Qdrant.
    """
    try:
      if isinstance(s3_pdf_paths, str):
        s3_pdf_paths = [s3_pdf_paths]


      for s3_pdf_path in s3_pdf_paths:
        with TemporaryFile() as pdf_tmpfile:
          # download PDF from S3
          self.s3_client.download_fileobj(Bucket=os.environ['S3_BUCKET_NAME'], Key=s3_pdf_path, Fileobj=pdf_tmpfile)


          docs = self.read_PDF(pdf_tmpfile, s3_pdf_path)
          self.vectorstore.add_texts([doc.text for doc in docs], [doc.metadata for doc in docs])

      self.vectorstore.add_texts(docs)

      # for S3
      

      # Upload a file to the S3 bucket
      file_path = 'path/to/your/local/file.txt'
      s3_key = 'path/to/your/s3/object.txt'

      with open(file_path, 'rb') as file:
        s3_client.upload_fileobj(file, S3_BUCKET_NAME, s3_key)

      # Download a file from the S3 bucket
      destination_file_path = 'path/to/your/local/destination/file.txt'
      s3_key_to_download = 'path/to/your/s3/object.txt'

      # with open(destination_file_path, 'wb') as file:
      # use a tempfile instead
      with TemporaryFile() as file:
        s3_client.download_fileobj(S3_BUCKET_NAME, s3_key_to_download, file)


      # qdrant_vectorstore = Qdrant.from_documents(
      #     docs,
      #     OpenAIEmbeddings(),
      #     os.environ['QDRANT_URL'],
      #     prefer_grpc=True,
      #     api_key=os.environ['QDRANT_API_KEY'],
      #     collection_name=os.environ['QDRANT_COLLECTION_NAME'],
      # )
      # self.vectorstore = qdrant_vectorstore

    except Exception as e:
      print(e)
      return "Error"

    return "Success"


  # todo
  def getTopContexts(self,):
    """Here's a summary of the work.

    /GET arguments
      course name (optional) str: A json response with TBD fields.
      
    Returns
      JSON: A json response with TBD fields.

    Raises:
      Exception: Testing how exceptions are handled.
    """
    # todo: best way to handle optional arguments?
    try:
        language: str = request.args.get('course_name')
    except Exception as e:
        print("No course name provided.")
    try:
        language: str = request.args.get('course_name')
    except Exception as e:
        print("No course name provided.")

    language: str = request.args.get('course_name')
    response:str = jsonify({"language": f"You said: {language}"})
    response.headers.add('Access-Control-Allow-Origin', '*')
    if language == 'error':
      raise Exception('This is an error message!')
    return response