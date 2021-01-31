import flask
import requests
import argparse
import json
import websockets
import uuid
import asyncio
import logging
import sys
import re
import threading
from flask import Flask, request
from parlai.chat_service.services.api.config import HOST_URL, PARLAI_URL, PARLAI_PORT, HOST_PORT, DEBUG, LOG_FORMAT

# Server configuration
parser = argparse.ArgumentParser(description="API for ParlAI chatbot")
parser.add_argument('--hostname', default=PARLAI_URL, help="ParlAI web server hostname.")
parser.add_argument('--port', type=int, default=PARLAI_PORT, help="ParlAI web server port.")
parser.add_argument('--serving_hostname', default=HOST_URL, help="API web server hostname.")
parser.add_argument('--serving_port', type=int, default=HOST_PORT, help="API web server port.")

args = parser.parse_args()

hostname = args.hostname
port = args.port	
serving_hostname = args.serving_hostname
serving_port = args.serving_port

app = Flask(__name__)
blueprint = flask.Blueprint('parlai_api', __name__, template_folder='templates')

# Log configuration
logging.basicConfig(stream=sys.stdout, level=logging.INFO, format=LOG_FORMAT)

connections = {}
websocket_uri = f"ws://{hostname}:{port}/websocket"

running = False

requests = []
responses = {}


def get_random_id():
    return str(uuid.uuid4())


def format_message(message):
    # Remove all spaces in general for the following chars
    p = re.compile(r"\s(?P<special_char>[$&+,:;=?@#|'<>.-^*()%!])\s?")
    text_response = p.sub(r"\g<special_char>", message)
    print(text_response)
    # Remove only one space from the left for each of the following.
    p = re.compile(r"(?P<special_char>[.,:?!])")
    return p.sub(r"\g<special_char> ", text_response)

class ParlaiAPI:
    @staticmethod
    def parse():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        while True:
            if not requests:
                continue
            request = requests.pop(0)
            result = loop.run_until_complete(request[1]())
            responses[request[0]] = result
    
    @staticmethod
    async def send_message(user_message, message_history=[], persona=False):
        if persona:
            message = "your persona: "
        else:
            message = ""

        message += user_message

        request_dict = {"text": message, "message_history": message_history}
        request_string = json.dumps(request_dict)
        request_bytes = bytes(request_string, encoding="UTF-8")
        print(request_bytes)
        
        try:
            async with websockets.connect(websocket_uri) as ws:
                await ws.send(request_bytes)

                response = await ws.recv()

                response = json.loads(response)
                print(response)

                try:
                    response['text'] = format_message(response.get('text'))
                except Exception as e:
                    print(e)

                return response
        except Exception as e:
            return {'text': str(e), 'error': True}


@blueprint.route('/api/send_message', methods=["POST"])
def send_message():
    request_id = get_random_id()
    data = request.get_json()

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    message_text, message_history = data.get('text', None), data.get('message_history', [])

    requests.append([request_id,
                     lambda: ParlaiAPI.send_message(message_text, message_history)])
    print(str(requests))
    logging.warning(str(requests))
    while request_id not in responses:
        pass

    result = responses[request_id]
    del responses[request_id]
    return result, 200


async def main():
    thread = threading.Thread(target=ParlaiAPI.parse)
    thread.start()
    app.register_blueprint(blueprint)
    app.debug = True
    app.run(host=serving_hostname, threaded=True, port=serving_port, debug=DEBUG)

main_loop = asyncio.get_event_loop()
main_loop.run_until_complete(main())
