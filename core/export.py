import random
import csv
import genanki
from typing import List, Tuple

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
                fields=[question, answer],
            )
            deck.add_note(note)

        return deck

def download_deck(deck: genanki.Deck, output_path: str, save_csv: bool = True):
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
