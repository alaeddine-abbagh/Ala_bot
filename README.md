# AirTech Bot

Aladin Bot is an AI-powered chatbot designed to assist with document analysis and answer questions. It's built using Python, leveraging the power of OpenAI's GPT models and the Chainlit framework for a user-friendly chat interface.

## Features

- Upload and process various document types (PDF, CSV, PowerPoint)
- Summarize uploaded documents
- Answer questions based on the content of uploaded documents
- User-friendly chat interface

## Requirements

- Python 3.7+
- Dependencies listed in `requirements.txt`

## Installation

1. Clone the repository:
   ```
   git clone <repository-url>
   cd <repository-name>
   ```

2. Create a virtual environment and activate it:
   ```
   python -m venv venv
   source venv/bin/activate  # On Windows, use `venv\Scripts\activate`
   ```

3. Install the required dependencies:
   ```
   pip install -r requirements.txt
   ```

4. Set up environment variables:
   Create a `.env` file in the project root and add the following variables:
   ```
   OPENAI_API_KEY=your_openai_api_key

   ```

## Usage

1. Start the Chainlit server:
   ```
   chainlit run app.py
   ```

2. Open your web browser and navigate to `http://localhost:8000` (or the URL provided in the console).

3. Upload a document (PDF, CSV, or PowerPoint) and start interacting with the bot.

## Project Structure

- `app_loc.py`: Main application file containing the Chainlit bot logic
- `requirements.txt`: List of Python dependencies
- `chainlit.md`: Markdown file for Chainlit's welcome message
- `.gitignore`: Specifies intentionally untracked files to ignore

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

[MIT]
