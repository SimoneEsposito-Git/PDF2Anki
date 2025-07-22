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

from utils import read_pdf, split_content  # Import utility functions for PDF reading and content splitting
from pydantic import BaseModel

# We'll initialize the client inside each function to avoid pickle issues

class QACArd(BaseModel):
    question: str
    answer: str

class QADeck(BaseModel):
    cards: List[QACArd]

class PDFToAnkiAPI():
    """Class to handle PDF to Anki conversion"""
    
    def __init__(self):
        self.files = []  # Initialize an empty list to store files
        self.client = None  # Placeholder for OpenAI client, initialized in methods
        self.decks = {}  # Initialize an empty list to store question-answer pairs
    def __repr__(self):
        return f"PDFToAnkiAPI(files={self.files})"
    
    def add_files(self, files: List[str]):
        """Add files to the API for processing"""
        self.files.extend(files)
    
    def clear_files(self):
        """Clear the list of files"""
        self.files = []
        self.decks = {}  # Clear the question-answer pairs as well
    
    def process_files(self, language: str = "English", count: int = 5, parallel: bool = True, **kwargs) -> List[Tuple[str, str]]:
        """Process the files and generate question-answer pairs"""
        if not self.files:
            raise ValueError("No files to process. Please add files using add_files method.")
        qa_pairs = {}  # Dictionary to store question-answer pairs for each file
        # if parallel is True, use ThreadPoolExecutor to process each file in parallel
        if parallel:
            with concurrent.futures.ThreadPoolExecutor() as executor:
                futures = {executor.submit(self.generate_qa_pairs, file, language, count): file for file in self.files}
                for future in concurrent.futures.as_completed(futures):
                    try:
                        file = futures[future]
                        qa_pairs[file] = future.result()
                        self.decks[file] = self.create_anki_deck(qa_pairs[file], file)
                    except Exception as e:
                        print(f"Error processing file {futures[future]}: {str(e)}")
        else:
            for file in self.files:
                try:
                    qa_pairs[file] = self.generate_qa_pairs(file, language, count)
                    self.decks[file] = self.create_anki_deck(qa_pairs[file], file)
                    
                except Exception as e:
                    print(f"Error processing file {file}: {str(e)}")
        
        return self.decks
    
    def generate_qa_pairs(self, file: str, language: str = "English", count: int = 5) -> List[Tuple[str, str]]:
        """Generate question-answer pairs from a single file"""
        if not os.path.exists(file):
            raise ValueError(f"File not found: {file}")
        
        try:
            pages = read_pdf(file)
            chunks = split_content(pages)
            qa_pairs = []
            
            for n, chunk in enumerate(chunks):
                print(f"Processing chunk {n+1}/{len(chunks)} of size {len(chunk)} from file {file}")
                qa_pairs.extend(self.process_chunk(chunk, language, count))
            
            return qa_pairs
        
        except Exception as e:
            print(f"Error processing file {file}: {str(e)}")
            return []
        
    def process_chunk(self, chunk: str, language: str = "English", count: int = 5) -> List[Tuple[str, str]]:
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
            Question in {language}
            Short answer in {language}

            TEXT:
            {chunk}
            """

            response = client.responses.parse(
                model="gpt-4o-mini",
                input=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                text_format = QADeck,
            )

            content = response.output_parsed
            qa_pairs = []
            for card in content.cards:
                qa_pairs.append((card.question, card.answer))

            return qa_pairs

        except Exception as e:
            if "auth" in str(e).lower() or "api key" in str(e).lower():
                raise ValueError(f"OpenAI API key error: {str(e)}. Please check your API key.")
            else:
                raise e

    def create_anki_deck(self, qa_pairs: List[Tuple[str, str]], deck_name: str) -> genanki.Deck:
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

    def download_deck(self, deck: genanki.Deck, output_path: str, save_csv: bool = True):
        """Save the Anki deck to a file"""
        if save_csv:
            csv_path = output_path.replace('.apkg', '.csv')
            print(f"Saving flashcards to CSV: {csv_path}")
            with open(csv_path, 'w', newline='', encoding='utf-8') as csvfile:
                writer = csv.writer(csvfile)
                writer.writerow(['Question', 'Answer'])
                for note in deck.notes:
                    writer.writerow([note.fields[0], note.fields[1]])
            print(f"CSV file saved: {csv_path}")
            
        # Save the deck to an Anki package file
        print(f"Saving deck to {output_path}")
        genanki.Package(deck).write_to_file(output_path)
        print("Deck saved successfully!")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate Anki flashcards from PDF files")
    parser.add_argument("pdf_path", help="Path to the PDF file")
    parser.add_argument("-o", "--output", help="Output file path for the Anki package")
    parser.add_argument("-d", "--deck-name", help="Name for the Anki deck")
    parser.add_argument("-w", "--workers", type=int, help="Number of parallel workers (default: use all available CPUs)", default=None)
    parser.add_argument("-l", "--language", help="Target language for flashcards", default="English")
    parser.add_argument("-c", "--count", type=int, help="Number of flashcards to generate per chunk", default=5)
    
    args = parser.parse_args()
    
    # Ensure the output directory exists
    if args.output:
        output_dir = Path(args.output).parent
        output_dir.mkdir(parents=True, exist_ok=True)
    else:
        args.output = "output.apkg"
        output_dir = Path(".")
    # Initialize the API
    api = PDFToAnkiAPI()
    # Add the PDF file to the API
    print(f"Adding PDF file: {args.pdf_path}")
    api.add_files([args.pdf_path])
    # Process the files and generate question-answer pairs
    print(f"Processing files: {api.files}")
    decks = api.process_files(language=args.language, count=args.count, parallel=args.workers is not None)
    # Save the Anki deck to a file
    if args.deck_name is None:
        args.deck_name = Path(args.pdf_path).stem  # Use the PDF filename as the deck name
    if args.output is None:
        args.output = output_dir / f"{args.deck_name}.apkg"
    for file, deck in decks.items():
        print(f"Saving deck for file {file} to {args.output}")
        api.download_deck(deck, args.output)
    
    # pdf_to_anki(args.pdf_path, args.output, args.deck_name, args.workers, args.language)
