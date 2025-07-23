from core.loader import load_pdf_unstructured
from core.chunker import chunk_by_page_number
from core.vectorstore import build_vectorstore
from core.question_gen import generate_questions
from core.answer_rag import generate_answer
from core.export import create_anki_deck, download_deck
import argparse

def main(pdf_path, language="English", count=5, output_path="flashcards.apkg", deck_name="Flashcards"):
    
    print(f"Loading PDF file: {pdf_path}", end="")
    pages = load_pdf_unstructured(pdf_path, chunk = True, languages=[language])
    print(" - done")
    
    print(f"Chunking PDF into pages", end="")    
    chunks = chunk_by_page_number(pages)
    print(" - done")
    
    print(f"Building vectorstore from {len(chunks)} chunks", end="")
    store = build_vectorstore(chunks)
    print(" - done")

    print(f"Generating {count} questions per chunk in {language}", end="")
    questions = generate_questions(chunks, language=language, questions_per_chunk=count)
    print(" - done")
    
    cards = []
    for i, q in enumerate(questions):
        print(f"\rGenerating answer for question {i+1}/{len(questions)}", end="")
        cards.append((q.question, generate_answer(q, store, language=language)))
    print(" - done")
    
    print(f"Creating Anki deck with {len(cards)} cards", end="")
    deck = create_anki_deck(cards, deck_name=deck_name)
    print(" - done")
    
    print(f"Saving Anki deck to {output_path}", end="")
    download_deck(deck, output_path=output_path, save_csv=True)
    print(" - done")
    

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate Anki flashcards from PDF files")
    parser.add_argument("pdf_path", help="Path to the PDF file")
    parser.add_argument("-o", "--output", help="Output file path for the Anki package")
    parser.add_argument("-d", "--deck-name", help="Name for the Anki deck")
    parser.add_argument("-w", "--workers", type=int, help="Number of parallel workers (default: use all available CPUs)", default=None)
    parser.add_argument("-l", "--language", help="Target language for flashcards", default="English")
    parser.add_argument("-c", "--count", type=int, help="Number of flashcards to generate per chunk", default=5)
    
    args = parser.parse_args()
    
    main(pdf_path=args.pdf_path,
         language=args.language,
         count=args.count,
         output_path=args.output if args.output else "flashcards.apkg",
         deck_name=args.deck_name if args.deck_name else "Flashcards")