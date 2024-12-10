# Family Walk In Clinic Voice Assistant

An automated voice response system using Twilio and OpenAI GPT-4.

## Setup

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Create `.env` file with:
```
OPENAI_API_KEY=your_openai_key
TWILIO_ACCOUNT_SID=your_twilio_sid
TWILIO_AUTH_TOKEN=your_twilio_token
TWILIO_PHONE_NUMBER=your_twilio_number
```

3. Run server:
```bash
python main.py
```

## Features
- Voice interaction with natural language processing
- Smart question matching
- Common clinic FAQ handling
- Twilio integration for phone calls

## Configuration
- Customize Q&A in `qa_database`
- Add question variations in `question_variations`