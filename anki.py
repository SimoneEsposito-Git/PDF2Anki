import os
import random
from typing import List, Tuple
import argparse
from pathlib import Path
import concurrent.futures
import csv  # Add CSV module for exporting cards to CSV

import fitz  # PyMuPDF for PDF reading
from openai import OpenAI  # Updated import
import genanki

# We'll initialize the client inside each function to avoid pickle issues

def read_pdf(pdf_path: str) -> List[str]:
    """Extract text from PDF, returning a list of pages"""
    doc = fitz.open(pdf_path)
    pages = []
    for page_num in range(len(doc)):
        page = doc.load_page(page_num)
        pages.append(page.get_text())
    return pages

def split_content(pages: List[str], chunk_size: int = 2500, overlap: int = 500) -> List[str]:
    """Split PDF content into overlapping chunks to ensure context is preserved"""
    chunks = []
    current_chunk = ""
    
    for page in pages:
        if len(current_chunk) + len(page) < chunk_size:
            current_chunk += page
        else:
            # Add current chunk before starting a new one
            if current_chunk:
                chunks.append(current_chunk)
            
            # Start new chunk with overlap from previous
            if current_chunk and len(current_chunk) > overlap:
                current_chunk = current_chunk[-overlap:] + page
            else:
                current_chunk = page
    
    # Add the final chunk if it's not empty
    if current_chunk:
        chunks.append(current_chunk)
        
    return chunks

def generate_qa_pairs(chunk: str, language: str = "English", count: int = 5) -> List[Tuple[str, str]]:
    """Use LLM to generate question-answer pairs from text chunk in specified language"""
    # Create a new client for each call to avoid pickle issues
    api_key = os.environ.get("OPENAI_API_KEY")
    
    if not api_key or api_key.strip() == "":
        raise ValueError("OpenAI API key is missing. Please set the OPENAI_API_KEY environment variable.")
    
    try:
        client = OpenAI(api_key=api_key)
        
        system_prompt = f"""
        You are an expert at creating educational flashcards in {language}.
        Analyze the provided text and extract important concepts.
        For each concept, create a clear question and comprehensive answer pair in {language}.
        If the text is in a different language, translate the content to {language} for the flashcards.
        Focus on key information that would be valuable for a student to learn.
        """
        
        user_prompt = f"""
        Please create up to {count} high-quality {language} flashcards from this text.
        The text may contain educational material, and some content might implicitly 
        have question-answer formats that need to be identified. The answers should be concise 
        but still complete.
        
        If the text is not in {language}, translate the concepts into {language}.
        
        For each flashcard, provide:
        Q: [question in {language}]
        A: [short answer in {language}]
        
        TEXT:
        {chunk}
        """
        
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.5,
            max_tokens=2000
        )
        
        content = response.choices[0].message.content
        qa_pairs = []
    
        # Parse the response for Q: and A: formatted content
        lines = content.split('\n')
        question = None
        answer = []
        
        for line in lines:
            line = line.strip()
            if line.startswith("Q:"):
                # If we have a previous Q-A pair, add it
                if question and answer:
                    qa_pairs.append((question, "\n".join(answer)))
                    answer = []
                question = line[2:].strip()
            elif line.startswith("A:"):
                answer.append(line[2:].strip())
            elif question and answer:  # continuation of an answer
                answer.append(line)
        
        # Add the last pair if it exists
        if question and answer:
            qa_pairs.append((question, "\n".join(answer)))
        
        return qa_pairs
    
    except Exception as e:
        if "auth" in str(e).lower() or "api key" in str(e).lower():
            raise ValueError(f"OpenAI API key error: {str(e)}. Please check your API key.")
        else:
            raise e

def create_anki_deck(qa_pairs: List[Tuple[str, str]], deck_name: str) -> genanki.Deck:
    """Create an Anki deck from the generated QA pairs"""
    # Create unique IDs for model and deck
    model_id = random.randrange(1 << 30, 1 << 31)
    deck_id = random.randrange(1 << 30, 1 << 31)
    
    # Create the model for the cards
    model = genanki.Model(
        model_id,
        'PDF QA Model',
        fields=[
            {'name': 'Question'},
            {'name': 'Answer'},
        ],
        templates=[
            {
                'name': 'Card',
                'qfmt': '{{Question}}',
                'afmt': '{{FrontSide}}<hr id="answer">{{Answer}}',
            },
        ]
    )
    
    # Create the deck
    deck = genanki.Deck(deck_id, deck_name)
    
    # Add cards to the deck
    for question, answer in qa_pairs:
        note = genanki.Note(
            model=model,
            fields=[question, answer]
        )
        deck.add_note(note)
    
    return deck

def save_to_csv(qa_pairs: List[Tuple[str, str]], output_path: str):
    """Save question-answer pairs to a CSV file"""
    csv_path = output_path.replace('.apkg', '.csv')
    print(f"Saving flashcards to CSV: {csv_path}")
    
    with open(csv_path, 'w', newline='', encoding='utf-8') as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(['Question', 'Answer'])
        for question, answer in qa_pairs:
            writer.writerow([question, answer])
    
    print(f"CSV file saved: {csv_path}")

def process_chunk(chunk_info):
    """Process a single chunk to generate QA pairs"""
    chunk, index, total, language = chunk_info
    print(f"Processing chunk {index+1}/{total} in {language}")
    try:
        qa_pairs = generate_qa_pairs(chunk, language, count = 2)
        print(f"Generated {len(qa_pairs)} QA pairs from chunk {index+1}")
        return (index, qa_pairs)  # Return index along with QA pairs to maintain order
    except Exception as e:
        print(f"Error processing chunk {index+1}: {str(e)}")
        # Return an empty list instead of propagating the error
        return (index, [])

def pdf_to_anki(pdf_path: str, output_path: str = None, deck_name: str = None, max_workers: int = None, language: str = "English"):
    """Process a PDF and convert it to Anki cards"""
    # Set default values
    if not deck_name:
        deck_name = Path(pdf_path).stem
    if not output_path:
        output_path = f"{Path(pdf_path).stem}_flashcards.apkg"
    
    print(f"Reading PDF: {pdf_path}")
    pages = read_pdf(pdf_path)
    print(f"Found {len(pages)} pages")
    
    print("Splitting content into chunks...")
    chunks = split_content(pages)
    print(f"Created {len(chunks)} chunks")
    
    ordered_results = []
    
    # Use ThreadPoolExecutor instead of ProcessPoolExecutor
    print(f"Processing chunks in parallel with {max_workers or 'default'} workers...")
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Prepare the chunks with their indices for the worker function
        chunk_data = [(chunk, i, len(chunks), language) for i, chunk in enumerate(chunks)]
        
        # Execute the processing in parallel and collect results
        future_to_chunk = {executor.submit(process_chunk, chunk_info): chunk_info[1] for chunk_info in chunk_data}
        
        for future in concurrent.futures.as_completed(future_to_chunk):
            try:
                index, qa_pairs = future.result()
                ordered_results.append((index, qa_pairs))
            except Exception as e:
                chunk_index = future_to_chunk[future]
                print(f"Error processing chunk {chunk_index+1}: {str(e)}")
                ordered_results.append((chunk_index, []))
    
    # Sort results by chunk index to maintain the original order
    ordered_results.sort(key=lambda x: x[0])
    
    # Extract all QA pairs in the correct order
    all_qa_pairs = []
    for _, qa_pairs in ordered_results:
        all_qa_pairs.extend(qa_pairs)
    
    print(f"Total flashcards generated: {len(all_qa_pairs)}")
    
    # Save to CSV file
    save_to_csv(all_qa_pairs, output_path)
    
    print("Creating Anki deck...")
    deck = create_anki_deck(all_qa_pairs, deck_name)
    
    print(f"Saving deck to {output_path}")
    genanki.Package(deck).write_to_file(output_path)
    print("Done!")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate Anki flashcards from PDF files")
    parser.add_argument("pdf_path", help="Path to the PDF file")
    parser.add_argument("-o", "--output", help="Output file path for the Anki package")
    parser.add_argument("-d", "--deck-name", help="Name for the Anki deck")
    parser.add_argument("-w", "--workers", type=int, help="Number of parallel workers (default: use all available CPUs)", default=None)
    parser.add_argument("-l", "--language", help="Target language for flashcards", default="English")
    
    args = parser.parse_args()
    
    pdf_to_anki(args.pdf_path, args.output, args.deck_name, args.workers, args.language)
