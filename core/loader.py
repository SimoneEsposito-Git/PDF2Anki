from langchain_community.document_loaders import UnstructuredPDFLoader
from langchain_core.globals import set_verbose, set_debug

def load_pdf_unstructured(pdf_path: str, chunk: bool = False, languages: [str] = ['english']) -> UnstructuredPDFLoader:
    """
    Load a PDF file using UnstructuredPDFLoader with specific configurations.
    
    Returns:
        UnstructuredPDFLoader: Configured loader for the PDF file.
    """
    # Create an instance of UnstructuredPDFLoader with specified parameters
    set_verbose(False)
    set_debug(False)
    
    loader = UnstructuredPDFLoader(
        pdf_path,
        infer_table_structure=True,
        strategy="hi_res",
        chunk_strategy = "basic" if chunk else None,
        include_orig_elements=False,
        mode="elements",
        max_characters=10000,               
        languages=languages,
    )
    
    return loader.load()