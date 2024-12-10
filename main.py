from fastapi import FastAPI, Response, Request
from twilio.twiml.voice_response import VoiceResponse, Gather
import os, openai
from dotenv import load_dotenv
from pyngrok import ngrok
from difflib import SequenceMatcher
import logging

load_dotenv()
app = FastAPI()
openai.api_key = os.getenv("OPENAI_API_KEY")

# Set up logging
logging.basicConfig(level=logging.INFO)

# Store session information keyed by CallSid
call_sessions = {}

# Categories and variations for intent detection
question_variations = {
    "hours": ["when do you open", "closing time", "what time", "operating hours", "are you open"],
    "services": ["what do you do", "help with", "can you treat", "available services", "medical services"],
    "insurance": ["do you take my insurance", "insurance accepted", "covered by insurance", "insurance plans"],
    "cost": ["how much", "price", "fees", "charges", "expensive", "affordable", "payment", "pay"],
    "location": ["where are you", "address", "directions", "how do i get there", "find you"],
    "wait time": ["how long", "wait times", "waiting period", "when will i be seen"],
    "appointment": ["do i need to schedule", "can i walk in", "book appointment", "reservation"],
    "documents": ["what to bring", "what do i need", "required documents", "paperwork"],
    "covid": ["coronavirus", "covid test", "covid-19", "pcr test", "rapid test"],
    "lab": ["blood work", "testing", "laboratory", "blood test", "urine test"],
    "xray": ["x ray", "xrays", "imaging", "radiography"],
    "emergency": ["urgent", "emergency care", "serious condition", "life threatening"],
    "prescriptions": ["medicine", "medications", "refill", "prescription refill"],
    "children": ["pediatric", "kids", "child", "baby", "infant"],
    "languages": ["spanish", "translator", "interpret", "habla español", "speak english"],
    "payment plans": ["financial", "payment options", "installments", "financing", "monthly payments"],
    "providers": ["doctors", "physicians", "medical staff", "healthcare providers"],
    "follow up": ["after visit", "check up", "follow-up care", "subsequent visits"]
}

# Organized Q&A database by category
qa_database = {
    "hours": "Our clinic is open from 8 AM to 4 PM, Monday through Friday.",
    "services": "We provide general check-ups, minor injury treatments, vaccinations, and more. Feel free to ask about specific services.",
    "insurance": "We accept a variety of insurance plans. Please call our billing department for specific details.",
    "cost": "Costs vary depending on the service. We accept insurance and out-of-pocket payments. Contact our front desk for a price estimate.",
    "location": "We are located at 123 Main Street in Springfield. You can find detailed directions on our website.",
    "wait time": "Typical wait times range from 15 to 30 minutes. We do our best to keep your wait as short as possible.",
    "appointment": "You can walk in during operating hours, but we recommend scheduling an appointment online or over the phone.",
    "documents": "Please bring a valid ID, your insurance card, and any relevant medical records you have.",
    "covid": "We offer COVID-19 testing, including PCR and rapid tests. Please call ahead for availability.",
    "lab": "Yes, we have an on-site lab for blood tests and basic diagnostics.",
    "xray": "We offer X-ray imaging services. A technician can assist you if needed during your visit.",
    "emergency": "For life-threatening conditions, please call 911 or visit the nearest emergency room. We handle urgent but not critical emergencies.",
    "prescriptions": "If you need a prescription refill, please call our office and have your pharmacy information ready.",
    "children": "We provide pediatric care for children of all ages.",
    "languages": "We have staff who speak Spanish and we can arrange for interpretation services if needed.",
    "payment plans": "We can discuss payment plans if you are uninsured or need financial assistance.",
    "providers": "Our team includes board-certified physicians, nurse practitioners, and physician assistants with diverse experience.",
    "follow up": "After your visit, we may schedule a follow-up appointment or provide instructions for at-home care."
}

def find_best_match(user_input):
    user_input = user_input.lower().strip()
    best_ratio = 0
    best_answer = None

    # First attempt: direct category match from variations
    for category, variations in question_variations.items():
        if any(var in user_input for var in variations):
            best_answer = qa_database.get(category, None)
            if best_answer:
                return best_answer

    # Fallback: similarity matching against category keys
    for category, answer in qa_database.items():
        ratio = SequenceMatcher(None, user_input, category.lower()).ratio()
        if ratio > best_ratio and ratio > 0.5:
            best_ratio = ratio
            best_answer = answer

    return best_answer  # Could be None if no match

def openai_fallback(user_input):
    """Use OpenAI API to get a fallback response if no match found."""
    try:
        response = openai.Completion.create(
            engine="text-davinci-003",
            prompt=f"You are a helpful receptionist at a Family Walk In Clinic. A caller asks: '{user_input}'. Please respond with a short, helpful answer related to the clinic's operations.",
            max_tokens=50,
            n=1,
            stop=None,
            temperature=0.7
        )
        return response.choices[0].text.strip()
    except Exception as e:
        logging.error(f"OpenAI API Error: {e}")
        return "I'm sorry, I am having trouble retrieving that information at the moment."

@app.post("/voice")
async def handle_call(request: Request):
    form = await request.form()
    call_sid = form.get('CallSid', None)
    if call_sid:
        # Initialize session data
        call_sessions[call_sid] = {
            "no_speech_count": 0,
            "context": []  # You can store last question or categories here if needed
        }

    response = VoiceResponse()
    gather = Gather(input='speech', action='/handle-input', method='POST')
    gather.say('Welcome to the Family Walk-In Clinic. How can I help you today?')
    response.append(gather)
    return Response(content=str(response), media_type="application/xml")

@app.post("/handle-input")
async def handle_input(request: Request):
    form = await request.form()
    user_input = form.get('SpeechResult', '').strip()
    call_sid = form.get('CallSid', None)
    call_data = call_sessions.get(call_sid, {"no_speech_count": 0, "context": []})

    response = VoiceResponse()

    # Check if user_input is empty or the user wants to end the call
    if not user_input:
        call_data["no_speech_count"] += 1
        # If multiple no-speech attempts, end the call
        if call_data["no_speech_count"] > 2:
            response.say("I'm sorry, I couldn't hear you. Goodbye.")
            response.hangup()
            return Response(content=str(response), media_type="application/xml")

        # Prompt again
        gather = Gather(input='speech', action='/handle-input', method='POST')
        gather.say("I didn't quite catch that. Could you please repeat?")
        response.append(gather)
        call_sessions[call_sid] = call_data
        return Response(content=str(response), media_type="application/xml")

    # Reset no speech count since we got an input
    call_data["no_speech_count"] = 0

    # Check if user wants to end the conversation
    end_phrases = ["no", "nothing else", "that's all", "bye", "goodbye", "no thank you"]
    if any(phrase in user_input.lower() for phrase in end_phrases):
        response.say("Thank you for calling. Have a great day!")
        response.hangup()
        return Response(content=str(response), media_type="application/xml")

    # Attempt to find a known answer
    answer = find_best_match(user_input)
    if not answer:
        # Use OpenAI fallback if no known answer
        answer = openai_fallback(user_input)
        logging.info(f"OpenAI fallback used for input: {user_input}")
    else:
        logging.info(f"Matched user input '{user_input}' to answer: {answer}")

    # Store context if needed
    call_data["context"].append({"user": user_input, "assistant": answer})
    call_sessions[call_sid] = call_data

    # Prompt user for more questions or end
    gather = Gather(input='speech', action='/handle-input', method='POST')
    gather.say(answer + " Is there anything else I can help you with?")
    response.append(gather)
    return Response(content=str(response), media_type="application/xml")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
