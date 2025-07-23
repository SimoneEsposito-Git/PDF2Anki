def chunk_by_page_number(pages):
    text_by_page = []
    for doc in pages:
        page = doc.metadata["page_number"]-1
        if page >= len(text_by_page):
            text_by_page.append("")
        if doc.metadata["category"] == "Table":
            text_by_page[page] += doc.metadata["text_as_html"]
        text_by_page[page] += doc.page_content + '\n'
    return text_by_page