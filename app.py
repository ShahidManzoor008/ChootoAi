from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from gradio_client import Client
import time
import logging
import re

# Initialize FastAPI app
app = FastAPI(title="AI Chatbot", version="1.0")

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Mount templates
templates = Jinja2Templates(directory="templates")

# Task-specific prompt templates
PROMPT_TEMPLATES = {
    "leave_application": """You are an expert professional writer. Your task is to write a formal leave application.
Follow this exact format:

[Current Date]

To: [Recipient's Title/Name]
[Department/Organization Name]

Subject: Application for Leave due to [Reason]

Dear Sir/Madam,

I am writing to request leave from [Start Date] to [End Date] due to [Detailed Reason]. [Additional Context if needed].

I will ensure all my responsibilities are properly handled during my absence. I will resume my duties on [Return Date].

Thank you for your consideration.

Sincerely,
[Your Name]
[Your Position]

Use these details to fill the template: {user_message}""",
    
    "letter": """You are an expert professional writer. Your task is to write a formal letter.
Follow this exact format:

[Your Full Name]
[Your Address]
[City, State, ZIP]
[Your Email/Phone]

[Current Date]

[Recipient's Name]
[Recipient's Title]
[Organization Name]
[Address]
[City, State, ZIP]

Dear [Recipient's Name],

[First paragraph: Clear introduction and purpose]

[Second paragraph: Details and main content]

[Third paragraph: Call to action or conclusion]

Sincerely,
[Your Name]
[Your Title]

Use these details to fill the template: {user_message}""",
    
    "email": """You are an expert professional writer. Your task is to write a formal email.
Follow this exact format:

Subject: [Clear and Concise Subject Line]

Dear [Recipient's Name],

I hope this email finds you well.

[First paragraph: Clear introduction and purpose]

[Second paragraph: Details and main content]

[Third paragraph: Clear call to action or next steps]

Thank you for your time and consideration.

Best regards,
[Your Full Name]
[Your Title]
[Your Contact Information]

Use these details to fill the template: {user_message}""",
    
    "article": """You are an expert content writer. Your task is to write a professional article.
Follow this structure:

[Engaging Title]

[Opening paragraph that hooks the reader]

[Main body with clear points and examples]
- Point 1 with supporting details
- Point 2 with supporting details
- Point 3 with supporting details

[Conclusion that summarizes key points]

Word count: Match the requested length
Topic: {user_message}"""
}

def detect_task_type(message):
    """Detect the type of writing task from the user's message."""
    message = message.lower()
    
    # Define task patterns with their corresponding types
    task_patterns = {
        "leave_application": ["leave", "sick", "vacation", "absence", "day off"],
        "letter": ["letter", "formal letter", "write letter", "official letter"],
        "email": ["email", "mail", "write email", "send email", "compose email"],
        "article": ["article", "blog", "post", "write about", "words about"]
    }
    
    # Check each pattern set
    for task_type, patterns in task_patterns.items():
        if any(pattern in message for pattern in patterns):
            return task_type
            
    return None

def enhance_prompt(message):
    """Enhance the user's prompt based on detected task type."""
    task_type = detect_task_type(message)
    if task_type and task_type in PROMPT_TEMPLATES:
        # Add helpful tips for incomplete requests
        if len(message.split()) < 8:  # If request is too short
            tips = {
                "leave_application": "Please provide: reason for leave, start date, end date, and your position.",
                "letter": "Please provide: recipient details, purpose of letter, and key points to address.",
                "email": "Please provide: recipient, subject matter, and main message points.",
                "article": "Please specify: topic, target length, and key points to cover."
            }
            return f"I need more details to help you write a {task_type.replace('_', ' ')}. {tips[task_type]}"
        
        return PROMPT_TEMPLATES[task_type].format(user_message=message)
    
    return "You are a professional writer. Your task is to provide a clear, well-structured response to this request: " + message

# Initialize the Hugging Face client with retries
def get_client(max_retries=3):
    for attempt in range(max_retries):
        try:
            client = Client("ShahidManzoor/chooto.ai")
            logger.info("Successfully connected to Hugging Face Space")
            logger.info(f"Available endpoints: {client.endpoints}")
            return client
        except Exception as e:
            if attempt < max_retries - 1:
                wait_time = 2 ** attempt  # Exponential backoff
                logger.warning(f"Attempt {attempt + 1} failed. Retrying in {wait_time} seconds...")
                time.sleep(wait_time)
            else:
                logger.error("Failed to connect to Hugging Face Space")
                raise e

# Initialize client
try:
    client = get_client()
except Exception as e:
    logger.error(f"Failed to initialize client: {str(e)}")
    client = None

# Store chat history
chat_history = []

# Define request body classes
class ChatRequest(BaseModel):
    message: str

class ResetRequest(BaseModel):
    reset: bool = True

# Reset chat history endpoint
@app.post("/reset_chat")
async def reset_chat(req: ResetRequest):
    global chat_history
    chat_history = []
    return {"status": "success", "message": "Chat history has been reset."}

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.post("/send_message")
async def send_message(req: ChatRequest):
    global chat_history, client
    
    # Check if client is initialized
    if client is None:
        try:
            client = get_client()
        except Exception as e:
            logger.error(f"Failed to initialize client: {str(e)}")
            return {"response": "Sorry, I'm having trouble connecting to the server. Please try again later."}
    
    # If message is asking for a specific task, clear history and enhance prompt
    message = req.message.strip()
    # Only enhance prompt if it's not already a well-formed request
    if not (message.lower().startswith(("write", "create", "generate")) and len(message.split()) >= 8):
        message = enhance_prompt(message)
        logger.info(f"Enhanced prompt: {message}")
    chat_history = []  # Always start fresh for writing tasks
    
    max_retries = 3
    for attempt in range(max_retries):
        try:
            # Separate template from actual message
            task_type = detect_task_type(message)
            actual_message = message
            template = None
            
            if task_type and task_type in PROMPT_TEMPLATES:
                template = PROMPT_TEMPLATES[task_type]
                # Only send the user's actual request to the model
                actual_message = message
            
            # Make API call to the chatbot
            output = client.predict(
                actual_message,
                chat_history if not template else [],  # Clear history if using template
                api_name="/chat_with_bot"
            )
            
            # Post-process the response if template was used
            if template and isinstance(output, list) and len(output) > 0:
                latest = output[-1]
                if isinstance(latest, list) and len(latest) == 2:
                    bot_response = latest[1]
                    if not any(pattern in bot_response.lower() for pattern in ["thank", "insight", "report", "i'll add"]):
                        # Format the response according to the template
                        formatted_response = template.format(user_message=bot_response)
                        output = [[actual_message, formatted_response]]
            
            # Handle the response
            logger.info(f"Raw output: {output}")
            
            try:
                # The output format is a list of all conversations
                if isinstance(output, list) and len(output) > 0:
                    # Get the latest conversation
                    latest_conversation = output[-1]
                    
                    if isinstance(latest_conversation, list) and len(latest_conversation) == 2:
                        bot_response = latest_conversation[1]  # Get the bot's response
                        
                        # Check for empty or invalid responses
                        if not bot_response or bot_response.strip() == "":
                            logger.warning("Received empty response from API")
                            # Reset the chat history
                            chat_history = []
                            return {
                                "response": "I need to restart our conversation. For better results, please be specific about what you need. For example:\n"
                                           "- 'Write a sick leave application for 3 days due to fever'\n"
                                           "- 'Write a formal letter requesting a meeting with the manager'\n"
                                           "- 'Write a professional email to schedule a client meeting'"
                            }
                        
                        # Check for unhelpful responses
                        unhelpful_patterns = [
                            r"^i can'?t",
                            r"^you can'?t",
                            r"^i don'?t",
                            r"^sorry",
                            r"^what if",
                            r"^no[.,]?$",
                            r"heh?e?h?e?",
                            r"^how to",
                            r"^i need more",  # Changed to be more specific
                            r"^i believe",
                            r"read.*guides",
                            r"do your own",
                            r"right sub",
                            r"send him",
                            r"what do you do",
                            r"^help",
                            r"[?]$",  # Responses ending with question mark are often unhelpful
                            r"please provide"  # Added to catch unhelpful "please provide" responses
                        ]
                        
                        # Skip validation for well-formed requests
                        if message.lower().startswith("write a") and len(message.split()) >= 8:
                            return {"response": bot_response}
                            
                        if any(re.search(pattern, bot_response.lower()) for pattern in unhelpful_patterns):
                            logger.warning(f"Detected unhelpful response: {bot_response}")
                            chat_history = []  # Reset the conversation
                            
                            task_type = detect_task_type(message)
                            if task_type:
                                examples = {
                                    "leave_application": "Write a sick leave application for 3 days (Aug 21-23) due to fever, addressed to the HR Manager",
                                    "letter": "Write a formal letter to the Building Manager requesting maintenance for apartment 304, with issues in plumbing",
                                    "email": "Write a professional email to schedule a client meeting for project review on August 25th at 2 PM",
                                    "article": "Write a 200-word article about recent advances in renewable energy, focusing on solar power developments"
                                }
                                return {
                                    "response": f"I'll help you write a {task_type.replace('_', ' ')}. Please provide complete details like this example:\n\n'{examples[task_type]}'"
                                }
                            
                            return {
                                "response": "I'll help you better if you make your request more specific. For example:\n"
                                           "- 'Write a sick leave application for 3 days due to fever'\n"
                                           "- 'Write a formal letter requesting maintenance for my apartment'\n"
                                           "- 'Write a professional email to schedule a client meeting'\n"
                                           "- 'Write a 200-word article about renewable energy'"
                            }
                        
                        # Update chat history only if we got a valid response
                        if len(bot_response.strip()) > 0:
                            # Keep only the last 3 conversation pairs to prevent context overflow
                            chat_history = output[-3:]
                        
                        logger.info(f"Processed bot response: {bot_response}")
                        return {"response": bot_response}
                    else:
                        logger.error(f"Invalid conversation format: {latest_conversation}")
                        chat_history = []  # Reset on error
                        return {
                            "response": "I apologize, but there was an error. Please try being more specific with your request."
                        }
                else:
                    logger.error(f"Invalid output format: {output}")
                    chat_history = []  # Reset on error
                    return {
                        "response": "I encountered an error. Please try being more specific with what you need help with."
                    }
                    
            except Exception as e:
                logger.error(f"Error processing response: {str(e)}")
                chat_history = []  # Reset on error
                return {
                    "response": "I apologize for the technical difficulty. Please try being more specific with your request."
                }
            
        except Exception as e:
            logger.error(f"Attempt {attempt + 1} failed: {str(e)}")
            if attempt < max_retries - 1:
                wait_time = 2 ** attempt
                logger.info(f"Retrying in {wait_time} seconds...")
                time.sleep(wait_time)
                # Try to reinitialize client
                try:
                    client = get_client()
                except Exception:
                    pass
            else:
                chat_history = []  # Reset on error
                error_msg = "I'm having trouble with the connection. Please try again with a specific request."
                return {"response": error_msg}
