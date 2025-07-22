import streamlit as st
import pandas as pd
from PIL import Image
import google.generativeai as genai
import json
import redis
import uuid
import pickle

# Load config and initialize Gemini
def load_config(path="config.json"):
    with open(path, "r") as f:
        return json.load(f)

config = load_config()
genai.configure(api_key=config["gemini_api"])
model = genai.GenerativeModel(config["model"])

# Redis connection
redis_client = redis.Redis(host='localhost', port=6379, db=0, decode_responses=False)

# Streamlit setup
st.set_page_config(page_title=" ChatDoc AI")
st.title("ChatDoc AI")

# Session state init
if "session_id" not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())
if "chat" not in st.session_state:
    st.session_state.chat = model.start_chat(history=[])
if "conversation" not in st.session_state:
    st.session_state.conversation = []


# Redis helpers
def save_to_redis(key, data):
    redis_client.set(key, pickle.dumps(data))

def load_from_redis(key):
    data = redis_client.get(key)
    return pickle.loads(data) if data else None

def save_conversation():
    save_to_redis(
        f"chat_session:{st.session_state.session_id}",
        {
            "gemini_history": st.session_state.chat.history,
            "conversation": st.session_state.conversation
        }
    )

def load_conversation():
    data = load_from_redis(f"chat_session:{st.session_state.session_id}")
    if data:
        st.session_state.chat = model.start_chat(history=data["gemini_history"])
        st.session_state.conversation = data["conversation"]

load_conversation()

# File upload
uploaded_file = st.file_uploader("Upload a CSV or Image File", type=["csv", "png", "jpg", "jpeg"])

if uploaded_file:
    st.session_state.uploaded_file = uploaded_file
    file_type = uploaded_file.type

    if file_type == "text/csv":
        try:
            df = pd.read_csv(uploaded_file)
            st.session_state.uploaded_csv = df
            st.success("CSV Loaded Successfully!")
            st.dataframe(df.head())
        except Exception as e:
            st.error(f"CSV Error: {e}")
    else:
        try:
            image = Image.open(uploaded_file).convert("RGB")
            st.session_state.uploaded_image = image
            st.image(image, caption="Uploaded Image", use_column_width=True)
        except Exception as e:
            st.error(f"Image Error: {e}")

# Handle question input
def submit_question():
    question = st.session_state.widget.strip()
    st.session_state.widget = ""
    if not question:
        return

    try:
        with st.spinner("🔍 Gemini is processing..."):
            content = []

            if st.session_state.conversation:
                prev = st.session_state.conversation[-1]
                prompt = f"Previous Question: {prev['question']}\nPrevious Answer: {prev['answer']}\nCurrent Question: {question}"
            else:
                prompt = question

            content.append(prompt)

            if uploaded_file.type == "text/csv":
                content.append(st.session_state.uploaded_csv.to_csv(index=False))
            else:
                content.append(st.session_state.uploaded_image)

            response = st.session_state.chat.send_message(content)
            answer = response.text.strip()

            st.session_state.conversation.append({"question": question, "answer": answer})
            save_conversation()
    except Exception as e:
        st.error(f"Gemini Error: {e}")



# Display conversation & input
if uploaded_file:
    for msg in st.session_state.conversation:
        st.markdown(f"**Q:** {msg['question']}")
        st.markdown(f"**A:** {msg['answer']}")
        st.markdown("---")

    st.text_input("Ask a question about the uploaded file:", key="widget", on_change=submit_question)

# Optional: reset function
def clear_conversation():
    redis_client.delete(f"chat_session:{st.session_state.session_id}")
    st.session_state.conversation = []
    st.session_state.chat = model.start_chat(history=[])
    st.rerun()
