import os
from threading import Thread
from flask import Flask

app = Flask('')

@app.route('/')
def home():
    return "Zero Remorse Discord Bot is running! 🤖"

@app.route('/health')
def health():
    return {"status": "healthy", "bot": "Zero Remorse"}

def run():
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port, debug=False)

def keep_alive():
    """Start the Flask web server in a separate thread"""
    t = Thread(target=run)
    t.daemon = True
    t.start()
    print(f"🌐 Web server started for health checks")