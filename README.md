# PDF to Anki Flashcard Generator

This script uses AI to automatically create Anki flashcards from your PDF files.

## Features
*	Converts PDF documents directly into Anki decks (apkg).
*	Uses OpenAI’s gpt-4o-mini to create smartquestion-and-answer pairs.
*	Supports multiple languages.
*	Exports a .csv file of your flashcards along with theAnki deck.
*	Can be run as a simple command-line tool.

## Setup

### Clone the repository:

~~~
git clone https://github.com/your-username/pdf-to-anki-converter.git
cd pdf-to-anki-converter
~~~

### Install dependencies:

~~~
pip install PyMuPDF openai genanki pydantic
~~~

### Set your API Key:

You need an OpenAI API key. Set it as an environment variable.

macOS/Linux:
~~~
export OPENAI_API_KEY='your-api-key-here
~~~
Windows (CMD):
~~~
set OPENAI_API_KEY=your-api-key-here
~~~

## How to Use

Run the script from your terminal. The basic command is:
~~~
python main.py <path_to_your_pdf>
~~~
### Example

This command will create an English Anki deck from MyNotes.pdf.
The output files will be MyNotes.apkg and MyNotes.csv.
~~~
python main.py "MyNotes.pdf"
~~~
### Customizing the Output

You can specify the language and deck name:
~~~
python main.py "MyNotes.pdf" --language "German" --deck-name "Meine Notizen"
~~~
